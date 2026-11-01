"""Adversarial source/observer checks, using authorized temporary stores."""
import asyncio
from copy import deepcopy

import pytest

from davcore.ast import digest
from davcore.service import Service
from research_automation.artifact_contract import ArtifactInput
from research_automation.controller import Controller
from research_automation import artifact
from semantic_repair.context009 import packets, resolve
from semantic_repair.inference011 import canonical_packet
from semantic_repair.observe011 import align, source_critic
from semantic_repair.runtime009 import assemble
from semantic_repair.compiler import compile_model
from semantic_repair.trace008 import adapter, trace
from semantic_repair.check011 import analyze, reference_step
from semantic_repair.realization import observe_state
from semantic_repair.worker import call


def raw(text, **extra):
    return ArtifactInput.model_validate({'format': 'livingmath-artifact/1', 'scope': 'development/toy',
        'source_name': 'Authorized development source', 'edition': 'Original development toy',
        'language': 'en', 'rights': {'basis': 'USER_SESSION', 'origin': 'Authorized QA source'},
        'raw_text': text, **extra})


def toy(packet, *, negative=False, dishonest=False, prescription=False, unrelated_negative=False):
    source, _ = canonical_packet(packet)
    spans = source['spans']
    def cite(i, quote):
        return {'ref': spans[i]['id'], 'quote': quote}
    def state(name):
        return {'id': name, 'label': name, 'evidence': [cite(0, name)],
            'features': [{'feature': name, 'evidence': cite(0, name)}],
            'participant': 'same named state', 'referent': name, 'polarity': 'POSITIVE',
            'tense': 'ATEMPORAL', 'modality': 'ASSERTED', 'quantifier': 'NAMED_CASE', 'scope': 'toy'}
    relations = []
    for i, (a, b) in enumerate([('A', 'B'), ('B', 'A')]):
        relations.append({'id': 'e' + str(i), 'kind': 'TRANSITION', 'src': a, 'dst': b,
            'evidence': [cite(i, spans[i]['text'])], 'predicate': a + ' to ' + b,
            'participant': 'same named state', 'referent': 'the named state',
            'polarity': 'NEGATIVE' if i == 1 and negative and not dishonest else 'POSITIVE',
            'tense': 'ATEMPORAL', 'modality': 'PRESCRIBED' if prescription else 'ASSERTED',
            'quantifier': 'NAMED_CASE', 'scope': 'toy', 'order_kind': 'EVENT_ORDER',
            'projection': 'SEQUENCE', 'projection_features': [],
            'interpretation_note': 'Conditional reading of the exact named transitions.'})
    if unrelated_negative:
        relations.append({**relations[0], 'id': 'no_exit', 'kind': 'NEGATED', 'src': 'A', 'dst': 'A',
            'evidence': [cite(2, spans[2]['text'])], 'polarity': 'NEGATIVE', 'predicate': 'no exit stated'})
    proposal = {'version': 'source-relations011/1', 'readings': [
        {'id': 'h', 'states': [state('A'), state('B')], 'relations': relations, 'unknowns': []}], 'losses': []}
    review = {'version': 'source-critic011/1', 'assessments': [
        {'reading_id': 'h', 'relation_id': r['id'], 'status': 'HYPOTHESIS',
            'evidence': r['evidence'], 'reason': 'The exact addressed words support this conditional annotation.',
            'distinctions_checked': ['participant', 'referent', 'predicate', 'quantifier', 'polarity',
                'tense', 'modal', 'scope', 'text_order_vs_event_order', 'projection'], 'alternative': ''}
        for r in relations], 'losses': []}
    return proposal, review


def prepared(tmp_path, *, text='State A becomes B.\nState B becomes A.\n', **variants):
    c = Controller(Service(tmp_path/'dav.sqlite3'))
    receipt = c.ingest('NEW_SOURCE_PROJECT', raw(text), 'raw')
    ctx = resolve(c.service.store, 'NEW_SOURCE_PROJECT', receipt['source_snapshot']['id'])
    packet = packets(ctx)[0][0]
    proposal, review = toy(packet, **variants)
    obs = align(packet, proposal, review)
    plan = assemble([obs], 'NEW_SOURCE_PROJECT')
    assert plan['plans']
    item = next(p for p in plan['plans'] if p['binding']['assignments']['observation'] == 'SEQUENCE')
    return c, ctx, packet, proposal, review, item


def model_for(item, ctx):
    return compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)


def test_existing_network_roundtrip_is_scoped_and_noncommutative(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path)
    model = model_for(item, ctx)
    evidence = analyze(model)['source_transition_analysis']
    assert evidence['full_state_cycles'] and evidence['T_C_subset_C']
    assert evidence['one_hot_in_declared_domain']
    a = adapter(model)
    assert a.apply('R1', a.apply('R0', 1)) == 1
    assert a.apply('R0', a.apply('R1', 1)) == 2
    assert any(a.apply('R1', a.apply('R0', s)) != s for s in a.states())
    assert all(a.apply('R' + str(i), s) == reference_step(model['spec']['reaction_network'], i, s)
        for i in range(2) for s in a.states())


@pytest.mark.parametrize('dishonest', [False, True])
def test_negative_transition_never_becomes_positive_cycle(tmp_path, dishonest):
    _, ctx, _, _, _, item = prepared(tmp_path,
        text='State A becomes B.\nState B does not become A.\n', negative=True, dishonest=dishonest)
    model = model_for(item, ctx)
    evidence = analyze(model)['source_transition_analysis']
    assert not evidence['full_state_cycles']
    assert adapter(model).apply('R1', 2) == 2
    assert model['proof_status'] == 'unverified' and model['execution_permission'] == {'allowed': False}


def test_unrelated_negative_does_not_permanently_block_return(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path,
        text='State A becomes B.\nState B becomes A.\nThere is no exit.\n', unrelated_negative=True)
    model = model_for(item, ctx)
    assert analyze(model)['source_transition_analysis']['full_state_cycles']
    assert model['observer']['source_cycle_status'] == 'HYPOTHESIS_ONLY'


def test_source_critic_rejects_fabricated_quotes_and_foreign_addresses(tmp_path):
    _, _, packet, proposal, review, _ = prepared(tmp_path)
    for citation in [{'ref': 'foreign:1', 'quote': 'A'},
                     {'ref': proposal['readings'][0]['relations'][0]['evidence'][0]['ref'], 'quote': 'A always proves B'}]:
        mutated = deepcopy(proposal)
        mutated['readings'][0]['relations'][0]['evidence'] = [citation]
        result = source_critic(packet, mutated, review)
        assert result['relations'][0]['status'] == 'UNSUPPORTED'


def test_empty_partial_projection_is_unknown_not_vacuous_equality(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path)
    item = deepcopy(item)
    item['binding']['assignments']['observation'] = 'PARTIAL_SET'
    model = model_for(item, ctx)
    assert not observe_state(model, 1)['observation_known']
    evidence = analyze(model)['source_transition_analysis']
    assert not evidence['observed_returns']
    assert all(c['Equivalent_O'] is None for c in evidence['observation_comparisons'])


def test_unmapped_partial_features_cannot_produce_empty_set_return(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path)
    item = deepcopy(item)
    item['binding']['assignments']['observation'] = 'PARTIAL_SET'
    for p in item['premises']:
        p['realization']['transition']['projection_features'] = ['never-mentioned-observer-coordinate']
    model = model_for(item, ctx)
    evidence = analyze(model)['source_transition_analysis']
    assert not observe_state(model, 1)['observation_known']
    assert not evidence['observed_returns']
    assert all(c['Equivalent_O'] is None for c in evidence['observation_comparisons'])


def test_reordered_features_distinguish_sequence_set_and_full_state(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path)
    item = deepcopy(item)
    for p in item['premises']:
        t = p['realization']['transition']
        for key in ('source', 'target'):
            t[key]['features'] = ['lamp', 'street'] if t[key]['key'].endswith(':A') else ['street', 'lamp']
        t['projection_features'] = ['lamp', 'street']
    sequential = model_for(item, ctx)
    a, b = observe_state(sequential, 1), observe_state(sequential, 2)
    assert a['projection'] != b['projection'] and a['full_state'] != b['full_state']
    item['binding']['assignments']['observation'] = 'SET'
    unordered = model_for(item, ctx)
    assert observe_state(unordered, 1)['projection'] == observe_state(unordered, 2)['projection']
    assert unordered['observer']['equal_observations_imply_full_identity'] is False


def test_prescription_does_not_attest_performance(tmp_path):
    _, ctx, _, _, _, item = prepared(tmp_path, prescription=True)
    model = model_for(item, ctx)
    evidence = analyze(model)
    assert evidence['invariants']['no_performance_attested']
    assert all(observe_state(model, s)['performance'] == 'UNKNOWN' for s in adapter(model).states())


def test_real_general_worker_firewall_and_every_premise_ablation(tmp_path):
    async def run():
        _, ctx, _, _, _, item = prepared(tmp_path)
        payload = {'premises': item['premises'], 'binding': item['binding'], 'profile': 'typed008/1'}
        model = await call('artifact_compile', payload, context=ctx)
        assert model.pop('isolation')['probes'] == {'file': 'DENIED', 'socket': 'DENIED'}
        result = await call('artifact_check', {**payload, 'model': model}, context=ctx)
        assert result['analysis']['all_operations_independently_replayed']
        assert len(result['deletions']) == len(item['premises'])
        assert all(d['source_assumption_withdrawn'] and d['changed'] for d in result['deletions'])
        assert not result['source_claim_verified']
        with pytest.raises(ValueError, match='WORKER_FAILED'):
            await call('artifact_compile', {**payload, 'query': {'desired': True}}, context=ctx)
    asyncio.run(run())


class ToyInference:
    model = 'UNIT_TEST_SOURCE_ANNOTATOR_NOT_LLM'
    fingerprint = digest(['unit-test-inference', 1])
    assurance = 'UNIT_TEST_ANNOTATION_NOT_A_LIVE_LLM'
    def __init__(self):
        self.calls = []
    async def infer(self, role, packet, proposals=None, feedback=None):
        self.calls.append(role)
        p, c = toy(packet)
        return {'status': 'OK', 'output': c if role == 'critic' else p,
            'model': self.model, 'cache_hit': False, 'usage': None}


async def settle(controller, project, maximum=120):
    for _ in range(maximum):
        status = controller.status(project)
        if not status['runnable']:
            return status['cases'][0]
        await controller.tick()
    raise AssertionError(controller.status(project))


def test_opt_in_controller_lifecycle_deduplication_and_project_isolation(tmp_path):
    async def run():
        provider = ToyInference()
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=provider)
        value = raw('State A becomes B.\nState B becomes A.\n', interpretation='general011')
        first = c.ingest('A', value, 'same')
        assert c.ingest('A', value, 'same') == first
        with pytest.raises(ValueError):
            c.ingest('B', ArtifactInput(format='livingmath-artifact/1', scope='foreign',
                snapshot=first['source_snapshot'], interpretation='general011'), 'foreign')
        final = await settle(c, 'A')
        assert final['status'] == 'COMPLETED' and final['result']['artifact_result_ids']
        assert provider.calls == ['proposer', 'critic']
        for ident in final['result']['artifact_result_ids']:
            record = c.service.store.get('A', ident)
            assert artifact.certificate_current(c, 'A', record)
        assert c.service.store.integrity()['ok']
    asyncio.run(run())


def test_general_persistence_failure_restores_without_repeating_model_call(tmp_path, monkeypatch):
    async def run():
        provider = ToyInference()
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=provider)
        c.ingest('A', raw('State A becomes B.\nState B becomes A.\n', interpretation='general011'), 'same')
        original = c.service.store.append
        failed = []
        def fault(project, kind, *args):
            if kind == 'artifact_result' and not failed:
                failed.append(True)
                raise OSError('PERSIST_GENERAL_RESULT_FAULT')
            return original(project, kind, *args)
        monkeypatch.setattr(c.service.store, 'append', fault)
        with pytest.raises(OSError, match='PERSIST_GENERAL'):
            for _ in range(50):
                await c.tick()
        calls = list(provider.calls)
        restored = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=provider)
        case = await settle(restored, 'A')
        assert case['status'] == 'COMPLETED' and provider.calls == calls
        assert len(case['result']['artifact_result_ids']) == 4
        assert restored.service.store.integrity()['ok']
    asyncio.run(run())


def test_no_model_backend_retains_legacy_partial_and_reports_actual_gap(tmp_path):
    async def run():
        c = Controller(Service(tmp_path/'dav.sqlite3'))
        c.ingest('A', raw('Скажи слово.\n', language='ru', interpretation='general011'), 'raw')
        case = await settle(c, 'A')
        assert case['result']['artifact_result_ids']
        assert any('NO_GENERAL_SEMANTIC_PROPOSER' in str(x) for x in case['result']['losses'])
        assert case['status'] != 'INPUT_REQUIRED'
    asyncio.run(run())


def test_legacy_default_serialization_and_forbidden_client_model_args():
    assert 'interpretation' not in raw('State A becomes B.').model_dump()
    for key in ['semantic_provider', 'model', 'proposals', 'critic', 'network', 'query', 'gold']:
        data = raw('State A becomes B.').model_dump()
        data[key] = 'injected'
        with pytest.raises(ValueError):
            ArtifactInput.model_validate(data)


def test_alternative_view_cannot_erase_prior_useful_reading(tmp_path):
    _, ctx, packet, proposal, review, _ = prepared(tmp_path)
    first = align(packet, proposal, review)
    uncertain = deepcopy(review)
    for a in uncertain['assessments']:
        a['status'] = 'UNKNOWN'
        a['reason'] = 'A competing scoped reading remains unresolved.'
    second = align(packet, proposal, uncertain)
    second['observer'] = 'general011-contrast/1'
    frontier = assemble([first, second], 'NEW_SOURCE_PROJECT')
    models = [compile_model(p['premises'], p['binding'], profile='typed008/1', context=ctx) for p in frontier['plans']]
    assert len(models) == 8
    assert any(analyze(m)['source_transition_analysis']['full_state_cycles'] for m in models)
    assert any(not analyze(m)['source_transition_analysis']['full_state_cycles'] for m in models)


def test_duplicate_feature_quote_does_not_invent_multiplicity_or_order(tmp_path):
    _, ctx, packet, proposal, review, _ = prepared(tmp_path)
    proposal = deepcopy(proposal)
    state = proposal['readings'][0]['states'][0]
    state['features'].append(deepcopy(state['features'][0]))
    observation = align(packet, proposal, review)
    family = assemble([observation], 'NEW_SOURCE_PROJECT')
    for item in family['plans']:
        model = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
        if item['binding']['assignments']['observation'] in {'SEQUENCE', 'MULTISET'}:
            assert not observe_state(model, 1)['observation_known']
        if item['binding']['assignments']['observation'] == 'SET':
            assert observe_state(model, 1)['projection'] == ['A']


def test_source_relations_about_transition_occurrences_are_reified_not_discarded(tmp_path):
    _, ctx, packet, proposal, review, _ = prepared(tmp_path)
    proposal = deepcopy(proposal)
    relation = {**proposal['readings'][0]['relations'][0], 'id': 'presentation',
        'kind': 'SEQUENCE', 'src': 'e0', 'dst': 'e1', 'order_kind': 'TEXT_ORDER',
        'predicate': 'The first transition is presented before the second.'}
    proposal['readings'][0]['relations'].append(relation)
    review = deepcopy(review)
    review['assessments'].append({**review['assessments'][0], 'relation_id': 'presentation'})
    observation = align(packet, proposal, review)
    family = assemble([observation], 'NEW_SOURCE_PROJECT')
    model = model_for(family['plans'][0], ctx)
    assert len(model['premise_ids']) == 3
    assert len(model['source_graph']['nodes']) == 4
    assert sum(n['kind'] == 'textual_clause' for n in model['source_graph']['nodes']) == 2
    assert analyze(model)['source_transition_analysis']['full_state_cycles']
    assert not model['observer']['source_annotations'][-1]['executable_transition']


def test_invalid_endpoint_preserves_valid_relations_and_original_output(tmp_path):
    from semantic_repair.relations011 import decode_proposals
    _, _, _, proposal, _, _ = prepared(tmp_path)
    raw = deepcopy(proposal)
    raw['readings'][0]['relations'].append({**raw['readings'][0]['relations'][0],
        'id': 'bad', 'src': 'undeclared'})
    frozen = deepcopy(raw)
    decoded, losses = decode_proposals(raw)
    assert raw == frozen
    assert decoded.model_dump() == proposal
    assert losses[0]['relation_id'] == 'bad'
    assert losses[0]['reason'] == 'UNRESOLVED_SOURCE_RELATION_ENDPOINT'


def test_reified_event_never_invents_observation_features(tmp_path):
    _, ctx, packet, proposal, review, _ = prepared(tmp_path)
    proposal = deepcopy(proposal)
    proposal['readings'][0]['relations'].append({**proposal['readings'][0]['relations'][0],
        'id': 'repeat_event', 'src': 'e0', 'dst': 'e0', 'kind': 'REPEAT'})
    review = deepcopy(review)
    review['assessments'].append({**review['assessments'][0], 'relation_id': 'repeat_event'})
    observation = align(packet, proposal, review)
    model = model_for(assemble([observation], 'NEW_SOURCE_PROJECT')['plans'][0], ctx)
    index = next(i for i, s in enumerate(model['observer']['states']) if s['node_kind'] == 'textual_clause')
    assert observe_state(model, 1 << index)['projection'] is None


def test_negative_only_source_graph_requires_existing_target_anchor(tmp_path):
    from artifact_translation.contract import SourceGraph
    _, ctx, _, _, _, plan = prepared(tmp_path)
    graph = deepcopy(model_for(plan, ctx)['source_graph'])
    for relation in graph['relations']:
        relation['kind'] = 'contrast'
    with pytest.raises(ValueError, match='NO_RELATION_WITH_DECLARED_TARGET_INTERPRETATION'):
        SourceGraph.model_validate(graph)


def test_nonkinetic_reading_finishes_as_useful_source_partial_without_certificate(tmp_path):
    class StaticAnnotation(ToyInference):
        fingerprint = digest(['unit-static-annotation-not-LLM'])
        async def infer(self, role, packet, proposals=None, feedback=None):
            p, c = toy(packet)
            p['readings'][0]['relations'] = p['readings'][0]['relations'][:1]
            p['readings'][0]['relations'][0].update(kind='NEGATED', polarity='NEGATIVE',
                predicate='Image similarity does not identify A and B')
            c['assessments'] = c['assessments'][:1]
            return {'status': 'OK', 'output': c if role == 'critic' else p,
                'model': self.model, 'usage': None}
    async def run():
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=StaticAnnotation())
        value = raw('Images do not identify A and B.\nThe comparison is limited.\n', interpretation='general011')
        receipt = c.ingest('STATIC_PARTIAL', value, 'raw')
        state = await settle(c, 'STATIC_PARTIAL')
        assert state['status'] == 'COMPLETED'
        assert state['result']['outcome'] == 'SOURCE_GRAPH_PARTIAL'
        assert state['result']['source_reading_refs']
        assert not state['result']['artifact_result_ids']
        assert not state['result']['external_execution_grant']
        report = artifact.report(c, 'STATIC_PARTIAL', receipt['case_ids'][0])
        assert 'SOURCE_SUPPORT' in report['report_ru'] and 'MODEL_DERIVATION' in report['report_ru']
        assert 'target-модель не построена' in report['report_ru']
        assert c.service.store.integrity()['ok']
    asyncio.run(run())


@pytest.mark.parametrize('size', [2, 3, 4, 5, 8])
def test_arbitrary_named_finite_graphs_match_independent_integer_executor(tmp_path, size):
    from random import Random
    rng = Random(11000 + size)
    names = ['k' + str(i) for i in range(size)]
    edges = [(i, (i + 1) % size) for i in range(size)]
    edges += [(rng.randrange(size), rng.randrange(size)) for _ in range(min(12 - size, 3))]
    text = '; '.join(names) + '. ' + '; '.join(names[a] + ' becomes ' + names[b] for a, b in edges) + '.\n'
    c = Controller(Service(tmp_path/'dav.sqlite3'))
    receipt = c.ingest('PROPERTY_GRAPH', raw(text), 'source')
    ctx = resolve(c.service.store, 'PROPERTY_GRAPH', receipt['source_snapshot']['id'])
    packet = packets(ctx)[0][0]
    canonical, _ = canonical_packet(packet)
    ref = canonical['spans'][0]['id']
    base_state = {
        'participant': 'named symbolic state', 'referent': 'state', 'polarity': 'POSITIVE',
        'tense': 'ATEMPORAL', 'modality': 'ASSERTED', 'quantifier': 'NAMED_CASE', 'scope': 'property'}
    states = [{**base_state, 'id': name, 'label': name,
        'evidence': [{'ref': ref, 'quote': name}],
        'features': [{'feature': name, 'evidence': {'ref': ref, 'quote': name}}]} for name in names]
    relations = [{'id': 'e' + str(i), 'kind': 'TRANSITION', 'src': names[a], 'dst': names[b],
        'evidence': [{'ref': ref, 'quote': names[a] + ' becomes ' + names[b]}],
        'predicate': 'named transition', **base_state, 'order_kind': 'EVENT_ORDER',
        'projection': 'SEQUENCE', 'projection_features': [], 'interpretation_note': 'Explicit development edge.'}
        for i, (a, b) in enumerate(edges)]
    proposal = {'version': 'source-relations011/1', 'readings': [{'id': 'h', 'states': states,
        'relations': relations, 'unknowns': []}], 'losses': []}
    dimensions = ['participant', 'referent', 'predicate', 'quantifier', 'polarity', 'tense',
        'modal', 'scope', 'text_order_vs_event_order', 'projection']
    review = {'version': 'source-critic011/1', 'assessments': [{'reading_id': 'h', 'relation_id': r['id'],
        'status': 'HYPOTHESIS', 'evidence': r['evidence'], 'reason': 'Exact artificial source edge.',
        'distinctions_checked': dimensions, 'alternative': ''} for r in relations], 'losses': []}
    family = assemble([align(packet, proposal, review)], 'PROPERTY_GRAPH')
    for item in family['plans'][:1]:
        model = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
        a = adapter(model)
        assert model['coordinate_count'] <= 8
        for state in a.states():
            for i in range(len(edges)):
                assert a.apply('R' + str(i), state) == reference_step(model['spec']['reaction_network'], i, state)
