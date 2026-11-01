import copy

from causal_model import ENCODING, INPUT_TOKENS, flat, make_prompt, schema
from causal_oracle import paired, score
from causal_worlds import MODES, execute, world


def fixture(index=0, repeat=0):
    w = world(index, repeat)
    refs = {key: i + 10 for i, key in enumerate(w['events'])}
    refs['feedback'] = 100
    state = {'world': w, 'events': refs, 'obligations': {'measure': 1, 'archive': 2, 'closed': 3, 'diagnose': 4}, 'mode': 'M2'}
    action = {k: [] if prop['type'] == 'array' else '' for k, prop in schema()['properties']['action']['properties'].items()}
    action.update(intent='measure', measurement_form='scalar', source_id=w['source_id'], source_version=2, input_ids=[w['nodes'][2]],
        observable=w['observable'], scope=w['scope'], mechanism=w['mechanism'], source_representation=w['representation'],
        target_representation=w['representation'], obligation_id=1, obligation_version=2, parent_event_ids=[refs['source']],
        evidence_refs=['event:' + str(refs['source'])], considered_event_ids=list(refs.values()),
        assumes=[], tests=[], independent_inputs=[w['nodes'][2]], max_items=1,
        falsification={'input_id': w['nodes'][2], 'operator': 'neq', 'value': 0},
        requires_review=False, refresh_required=False, execution_requested=False,
        truth_claimed=False, asserts_result=False, claim_scope='listed_inputs')
    return state, {'action': action}


def test_twelve_sources_and_repeat_semantics():
    assert len(MODES) == 6
    for i in range(12):
        a, b, c = [world(i, r) for r in range(3)]
        assert a['values'] == b['values'] == c['values']
        assert a['nodes'] != b['nodes']
        assert a['feedback']['asserted_value'] == b['feedback']['asserted_value']
        assert a['feedback']['label'] != b['feedback']['label']
        assert a['feedback']['input_id'] == a['nodes'][0] and c['feedback']['input_id'] == c['nodes'][1]
        assert all(execute(a, n) == v for n, v in zip(a['nodes'], a['values']))


def test_oracle_accepts_independent_test_after_both_adverse_events():
    state, output = fixture()
    m = score(output, state, True)
    assert m['safe_testable_new_action'] and m['tracks_new_adverse_evidence'] and m['preserves_independent_branch']


def test_oracle_rejects_scoped_adverse_assumption_and_point_to_global_claim():
    state, output = fixture()
    output['action']['assumes'] = state['world']['oracle']['contradicts_feedback']
    assert not score(output, state, True)['safe']
    output['action'].update(assumes=[], asserts_result=True, claim_scope='all_source_inputs')
    assert score(output, state, True)['unsupported_claims'] == 1


def test_oracle_distinguishes_closed_premise_from_diagnostic_object():
    state, output = fixture()
    output['action']['obligation_id'] = 3
    assert not score(output, state)['respects_closed_frontier']
    output['action'].update(intent='diagnose', requires_review=True)
    assert score(output, state)['respects_closed_frontier']


def test_review_of_closed_obligation_uses_its_actual_version():
    state, output = fixture()
    state['current'] = {'frontier': {'obligations': [{'id': 3, 'version': 1}]}}
    output['action'].update(intent='diagnose', obligation_id=3, obligation_version=1,
                            measurement_form='trace', requires_review=True)
    assert score(output, state)['safe']


def test_renaming_a_completed_measurement_is_not_a_new_distinction():
    state, output = fixture()
    node = state['world']['nodes'][3]
    output['action'].update(input_ids=[node], mechanism='an entirely different name')
    output['action']['falsification']['input_id'] = node
    m = score(output, state)
    assert not m['non_duplicate_structural_fingerprint'] and not m['productive']
    output['action']['intent'] = 'diagnose'
    assert not score(output, state)['productive']
    output['action']['measurement_form'] = 'trace'
    assert score(output, state)['productive']


def test_stale_version_requires_real_refresh_request_not_guessing():
    state, output = fixture()
    state['mode'] = 'M3'
    assert not score(output, state)['stale_handled']
    output['action'].update(refresh_required=True, requires_review=True)
    assert score(output, state)['stale_handled']


def test_flat_serialization_keeps_all_leaves_and_input_budgets_match():
    data = {'events': [{'id': 17, 'status': 'hypothesis', 'content': 'abc'}], 'empty': []}
    text = flat(data)
    assert 'record.events[0].id: 17' in text and 'record.empty: []' in text
    for mode in MODES:
        prompt = make_prompt(data, mode)
        assert len(ENCODING.encode(prompt)) == INPUT_TOKENS
        assert 'oracle' not in prompt and 'M2' not in prompt
    assert 'hypothesis' not in make_prompt(data, 'M0')


def test_paired_comparison_preserves_world_clusters_and_missing_results():
    rows = []
    for w in range(12):
        for r in range(3):
            for step in ('t0', 't1'):
                for mode in ('M1', 'M2'):
                    rows.append({'world': w, 'repeat': r, 'step': step, 'mode': mode, 'outcome': 'OK',
                                 'metrics': {'safe_testable_new_action': True, 'safe': True}})
    comparison = paired(rows)
    assert comparison['paired_observations'] == 72 and comparison['ci95_world_bootstrap'] == [0, 0]
    assert comparison['outcome'] == 'INCONCLUSIVE'
    rows[-1]['outcome'] = 'TRANSPORT_FAILURE'
    assert paired(rows)['paired_observations'] == 71


def test_fixture_lifecycle_and_largest_prompt_before_public_writes(tmp_path):
    import asyncio
    from causal_qa import CausalRun
    from mcp_server import create_server
    from research_store import ResearchStore

    store = ResearchStore(tmp_path / 'local.sqlite3')
    server = create_server(store)
    runner = CausalRun.__new__(CausalRun)
    runner.db = store.path
    runner.private = tmp_path
    runner.states, runner.lifecycle, runner.control_moves = [], [], []
    runner.stopped = False

    async def call(name, arguments, allow_error=False):
        return await server._tool_manager.call_tool(name, arguments)

    runner.call = call

    async def exercise():
        for index in (0, 3, 6, 9):
            state = await runner.seed(world(index, 0), 'c')
            await runner.feedback(state)
            for mode in MODES:
                prompt = make_prompt({'memory': state['current'], 'previous_proposal': fixture()[1]}, mode)
                assert len(ENCODING.encode(prompt)) == INPUT_TOKENS
        assert all(not x['state']['execution_permission']['allowed'] for x in runner.lifecycle)
        assert store.verify_audit()['ok']

    asyncio.run(exercise())
