"""Source transport boundaries: real worker tests use temporary authorized stores."""
import asyncio
from copy import deepcopy

import pytest
from artifact_translation.contract import SourceGraph, ProposalRequest
from artifact_translation.network import Network
from davcore.ast import digest
from davcore.service import Service
from research_automation import artifact
from research_automation.controller import Controller
from semantic_repair.check009 import check_model
from semantic_repair.check012 import compare_observer
from semantic_repair.compiler import compile_model
from semantic_repair.context009 import packets, resolve
from semantic_repair.observe012 import align
from semantic_repair.runtime009 import assemble
from semantic_repair.worker import call
from test_general_interpretation011 import raw, toy, settle


def annotation(packet):
    p, r = toy(packet)
    p['version'] = 'source-relations012/1'; r['version'] = 'source-critic012/1'
    for h in p['readings']:
        for s in h['states']: s['level'] = 'WORLD_STATE'
        for edge in h['relations']:
            edge['source_claim'] = {'mode': 'DIRECT', 'speaker': 'source narrator', 'observer_id': None,
                'stance': 'ASSERTS', 'connective': 'NONE', 'evidence': edge['evidence'], 'speaker_evidence': []}
            edge['interpretation_assumptions'] = ['CONDITIONAL_EXECUTABLE_CHANGE', 'SYMBOLIC_STATES_NOT_PHYSICAL_IDENTITIES']
        h.update(observers=[], initial_state_ids=['A'])
    for a in r['assessments']: a.update(attribution_checked=True, observer_mask_checked=True, executable_assumption_supported=True)
    return p, r


def prepared(tmp_path, mutate=None):
    c = Controller(Service(tmp_path/'dav.sqlite3'))
    receipt = c.ingest('QA012', raw('State A becomes B.\nState B becomes A.\n'), 'source')
    ctx = resolve(c.service.store, 'QA012', receipt['source_snapshot']['id'])
    packet = packets(ctx)[0][0]; p, r = annotation(packet)
    if mutate: mutate(p, r)
    obs = align(packet, p, r)
    plans = assemble([obs], 'QA012')['plans']; assert plans
    item = plans[0]
    m = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
    return c, ctx, item, m


def test_real_fired_cycle_and_no_source_verification(tmp_path):
    _, ctx, item, m = prepared(tmp_path)
    checked = check_model(item['premises'], item['binding'], m, ctx)
    analysis = checked['analysis']['source_transition_analysis']
    assert analysis['full_state_cycles'] and analysis['cycle_status'] == 'MODEL_CYCLE_REACHABLE'
    assert all(t['actual_round_trip'] and t['registered_initial'] for t in analysis['full_state_cycles'])
    assert checked['source_claim_verified'] is False and checked['execution_permission'] == {'allowed': False}
    assert len(checked['deletions']) == 2 and all(x['changed'] for x in checked['deletions'])
    assert checked['full_formalization'] is False


@pytest.mark.parametrize('field,value', [('mode', 'ATTRIBUTED'), ('mode', 'QUOTED'), ('stance', 'DENIES')])
def test_speaker_asserts_not_world_truth(tmp_path, field, value):
    def mutate(p, r):
        for edge in p['readings'][0]['relations']:
            edge['source_claim'][field] = value
            edge['source_claim']['speaker_evidence'] = edge['evidence']
    _, ctx, item, m = prepared(tmp_path, mutate)
    assert m['target_model'] == 'NOT_APPLICABLE' and 'spec' not in m
    result = check_model(item['premises'], item['binding'], m, ctx)
    assert all(x['world_truth'] == 'UNKNOWN' for x in result['analysis']['source_meta_obligations'])
    assert not result['analysis']['all_operations_independently_replayed']
    assert result['analysis']['target_check'] == 'NOT_APPLICABLE'


def test_negative_only_no_fictitious_network(tmp_path):
    def mutate(p, r):
        for edge in p['readings'][0]['relations']: edge.update(kind='NEGATED', polarity='NEGATIVE')
    _, ctx, item, m = prepared(tmp_path, mutate)
    assert m['source_graph']['interpretation'] == 'META_ONLY' and 'spec' not in m
    result = check_model(item['premises'], item['binding'], m, ctx)
    assert len(result['analysis']['source_meta_obligations']) >= 4
    assert all(d['source_assumption_withdrawn'] and not d['changed'] for d in result['deletions'])
    with pytest.raises(ValueError): Network.model_validate({'species': [{'id': 'x', 'label': 'x', 'source_refs': ['x']}], 'reactions': []})
    with pytest.raises(ValueError): ProposalRequest.model_validate({'source_graph': m['source_graph']})


@pytest.mark.parametrize('kind,order', [('REPEAT', 'EVENT_ORDER'), ('REORDERED', 'TEXT_ORDER'), ('ORDER', 'TEXT_ORDER')])
def test_reported_repeat_and_narrative_order_not_executable(tmp_path, kind, order):
    def mutate(p, r):
        for edge in p['readings'][0]['relations']: edge.update(kind=kind, order_kind=order)
    _, ctx, item, m = prepared(tmp_path, mutate)
    assert m['premise_ids'] == [] and m['initial_states'] == []
    checked = check_model(item['premises'], item['binding'], m, ctx)
    assert checked['analysis']['traces'] == []
    assert any(o['kind'] in {'RECURRENCE_NOT_RETURN_COMMAND', 'TEXT_ORDER_NOT_CAUSALITY'} for o in checked['analysis']['source_meta_obligations'])


def test_disabled_operation_cannot_fire_and_one_way_no_converse(tmp_path):
    _, ctx, item, m = prepared(tmp_path)
    disabled = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx, disabled=(m['premise_ids'][1],))
    from semantic_repair.check012 import dynamics
    a = dynamics(disabled)['source_transition_analysis']
    assert not a['full_state_cycles']
    assert len(disabled['premise_ids']) == 1
    assert not any(s['before'] == s['after'] for t in dynamics(disabled)['traces'] for s in t['steps'])


def profile(x, y, criterion='SET'):
    return {'id': 'O1', 'criterion': criterion, 'features': ['color', 'shape'],
        'samples': [{'state_key': 's', 'values': x}, {'state_key': 't', 'values': y}]}


def test_unknown_mask_shared_features_and_observer_disagreement():
    p = profile({'color': 'red', 'shape': None}, {'color': 'red', 'shape': None})
    a = compare_observer(p, 's', 't')
    assert a['status'] == 'CONSISTENT_ON_SHARED_FEATURES' and a['unknown_mask'] == ['shape']
    assert not a['full_state_equality_inferred']
    assert compare_observer(profile({}, {}), 's', 't')['status'] == 'UNKNOWN'
    assert compare_observer(profile({'color': 'red'}, {'color': 'blue'}), 's', 't')['status'] == 'DISTINGUISHABLE_ON_NAMED_OBSERVER'
    assert compare_observer(profile({'color': 'red', 'shape': 'round'}, {'color': 'red', 'shape': 'round'}), 's', 't')['status'] == 'EQUIVALENT_ON_NAMED_OBSERVER'


def test_every_distinction_keeps_counterfactual_ledger(tmp_path):
    _, ctx, item, m = prepared(tmp_path)
    r = check_model(item['premises'], item['binding'], m, ctx)
    assert r['loss_ledger'] and all(x['status'].startswith('PRESERVED') for x in r['loss_ledger'])
    for x in r['loss_ledger']:
        assert x['witness']
        if x['status'] == 'PRESERVED_IN_TARGET':
            w = x['witness']['target_counterfactual']; assert w['before'] != w['after_command_withdrawal']
    tampered = deepcopy(m); tampered['observer']['source_annotations'][0]['claim']['quantifier'] = 'ALL'
    with pytest.raises(ValueError, match='STALE'): check_model(item['premises'], item['binding'], tampered, ctx)


def test_012_real_worker_has_same_io_firewall(tmp_path):
    async def run():
        _, ctx, item, _ = prepared(tmp_path)
        payload = {k: item[k] for k in ('premises', 'binding')}; payload['profile'] = 'typed008/1'
        m = await call('artifact_compile', payload, context=ctx)
        assert m.pop('isolation')['probes'] == {'file': 'DENIED', 'socket': 'DENIED'}
        r = await call('artifact_check', {**payload, 'model': m}, context=ctx)
        assert r['analysis']['all_operations_independently_replayed']
    asyncio.run(run())


class AnnotationProvider:
    fingerprint = digest(['unit-annotation012']); assurance = 'UNIT_TEST_NOT_LLM'; model = 'unit'
    async def infer(self, role, packet, proposals=None, feedback=None):
        p, r = annotation(packet)
        for edge in p['readings'][0]['relations']: edge.update(kind='NEGATED', polarity='NEGATIVE')
        return {'status': 'OK', 'output': r if role == 'critic012' else p, 'usage': None}


def test_meta_controller_restart_report_export_dedup_and_no_grant(tmp_path):
    async def run():
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=AnnotationProvider())
        source = raw('State A becomes B.\nState B becomes A.\n', interpretation='observer012')
        first = c.ingest('QA_META', source, 'same'); assert c.ingest('QA_META', source, 'same') == first
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=AnnotationProvider())
        final = await settle(c, 'QA_META')
        assert final['result']['outcome'] == 'SOURCE_META_FORMALIZATION'
        assert final['result']['distinct_target_projections'] == 0
        assert len(final['result']['meta_only_result_ids']) == 1
        row = c.service.store.get('QA_META', final['result']['meta_only_result_ids'][0])
        assert artifact.certificate_current(c, 'QA_META', row)
        generic = c.service.export('QA_META', row['id'])
        assert generic['meta_contract_current'] and not generic['certificate_current']
        assert generic['effective_status'] == 'SCOPED_META_TRANSPORT_CHECKED'
        report = artifact.report(c, 'QA_META', first['case_ids'][0]); assert 'NOT_APPLICABLE' in report['report_ru']
        exp = artifact.export(c, 'QA_META', first['case_ids'][0], row['id']-1, 0, 1, 60000)
        f = exp['fragments'][0]; assert f['meta_contract_current'] and not f['certificate_current']
        assert c.service.store.integrity()['ok']
    asyncio.run(run())


def test_source_coordinates_or_and_some_all_have_separate_meta_constraints(tmp_path):
    _, ctx, item, m = prepared(tmp_path)
    a = deepcopy(item); b = deepcopy(item)
    for v, connective, quantifier in [(a, 'DISJUNCTION', 'SOME'), (b, 'CONJUNCTION', 'ALL')]:
        d = v['premises'][0]['realization']['transition']
        d['source_claim']['connective'] = connective; d['claim']['quantifier'] = quantifier
    ma = compile_model(a['premises'], a['binding'], profile='typed008/1', context=ctx)
    mb = compile_model(b['premises'], b['binding'], profile='typed008/1', context=ctx)
    assert ma['spec'] == mb['spec']
    assert ma['observer']['source_annotations'] != mb['observer']['source_annotations']
    for v, model in [(a, ma), (b, mb)]:
        r = check_model(v['premises'], v['binding'], model, ctx)
        rows = [x for x in r['loss_ledger'] if x['distinction'] in {'claim.quantifier', 'source_claim.connective'}]
        assert rows and all(x['status'] == 'PRESERVED_META_ONLY' for x in rows)


def test_not_repeat_and_reordered_are_distinct_source_obligations(tmp_path):
    def mutate(p, r):
        a, b = p['readings'][0]['relations']
        a.update(kind='NEGATED', polarity='NEGATIVE', predicate='no repetition')
        b.update(kind='REORDERED', order_kind='TEXT_ORDER')
    _, ctx, item, m = prepared(tmp_path, mutate)
    r = check_model(item['premises'], item['binding'], m, ctx)
    kinds = {x['kind'] for x in r['analysis']['source_meta_obligations']}
    assert {'SOURCE_NEGATIVE_NOT_ABSENCE', 'TEXT_ORDER_NOT_CAUSALITY'} <= kinds
    assert not m['premise_ids']


def test_no_vacuous_closure_of_unreachable_cycle(tmp_path):
    _, ctx, item, _ = prepared(tmp_path)
    # Chosen initial has no token; complete mathematical graph still has A<->B,
    # but registered reachability may not be replaced by arbitrary graph nodes.
    from semantic_repair.check012 import dynamics
    m = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
    m['initial_states'] = [0]
    a = dynamics(m)['source_transition_analysis']
    assert not a['nonvacuous_enabled_reachable_edge'] and not a['full_state_cycles']
    assert a['reachable_states'] == [0]


def test_new_meta_version_does_not_relax_legacy_source_graph(tmp_path):
    _, _, _, m = prepared(tmp_path)
    g = deepcopy(m['source_graph'])
    for e in g['relations']: e['kind'] = 'contrast'
    g['interpretation'] = 'META_ONLY'; assert SourceGraph.model_validate(g)
    g.pop('interpretation'); g.pop('semantics_version')
    with pytest.raises(ValueError, match='NO_RELATION_WITH_DECLARED_TARGET_INTERPRETATION'):
        SourceGraph.model_validate(g)


def test_quote_inside_full_sentence_cannot_hide_attribution(tmp_path):
    c = Controller(Service(tmp_path/'dav.sqlite3'))
    receipt = c.ingest('QA012', raw('An observer says: “State A becomes B.”\nState B becomes A.\n'), 'source')
    ctx = resolve(c.service.store, 'QA012', receipt['source_snapshot']['id'])
    packet = packets(ctx)[0][0]; p, r = annotation(packet)
    obs = align(packet, p, r); item = assemble([obs], 'QA012')['plans'][0]
    m = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
    assert len(m['premise_ids']) == 1
    assert m['observer']['source_annotations'][0]['source_claim']['quotation_guard'] != 'NOT_QUOTED'


def test_named_observers_disagree_without_full_state_identity(tmp_path):
    def mutate(p, r):
        h = p['readings'][0]; e = h['states'][0]['evidence']
        h['observers'] = [{'id': 'color', 'owner': 'color reader', 'evidence': e,
            'criterion': 'SET', 'features': ['color', 'missing'], 'samples': [
                {'state_id': k, 'values': [{'feature': 'color', 'value': 'red', 'evidence': e}]} for k in ['A', 'B']]},
            {'id': 'shape', 'owner': 'shape reader', 'evidence': e,
            'criterion': 'SET', 'features': ['shape'], 'samples': [
                {'state_id': k, 'values': [{'feature': 'shape', 'value': v, 'evidence': e}]}
                for k, v in [('A', 'round'), ('B', 'square')]]}]
    _, ctx, item, m = prepared(tmp_path, mutate)
    r = check_model(item['premises'], item['binding'], m, ctx)
    statuses = {x['status'] for x in r['analysis']['observer_comparisons']}
    assert statuses == {'CONSISTENT_ON_SHARED_FEATURES', 'DISTINGUISHABLE_ON_NAMED_OBSERVER'}
    assert all(not x['full_state_equality_inferred'] for x in r['analysis']['observer_comparisons'])
    assert m['observer']['source_annotations'][0]['source']['source_coordinates']['participant'] != 'color reader'


@pytest.mark.parametrize('violation', ['attribution', 'negative', 'text_order', 'repeat', 'unknown_modality', 'source_event'])
def test_independent_scope_checker_kills_compiler_admission_mutants(tmp_path, monkeypatch, violation):
    from semantic_repair import realization012
    def mutate(p, r):
        h = p['readings'][0]
        for edge in h['relations']:
            if violation == 'attribution': edge['source_claim'].update(mode='ATTRIBUTED', speaker_evidence=edge['evidence'])
            if violation == 'negative': edge['polarity'] = 'NEGATIVE'
            if violation == 'text_order': edge['order_kind'] = 'TEXT_ORDER'
            if violation == 'repeat': edge['kind'] = 'REPEAT'
            if violation == 'unknown_modality': edge['modality'] = 'UNKNOWN'
        if violation == 'source_event': h['states'][0]['level'] = 'SOURCE_EVENT'
    _, ctx, item, good = prepared(tmp_path, mutate)
    if violation == 'source_event':
        # Network must never absorb a source speech/event node as a world species.
        monkeypatch.setattr(realization012, 'command_eligible', lambda d: True)
        with pytest.raises((ValueError, KeyError)):
            compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
    else:
        monkeypatch.setattr(realization012, 'command_eligible', lambda d: True)
        bad = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
        with pytest.raises(ValueError, match='SOURCE_EXECUTION_SCOPE_COUNTERMODEL'):
            check_model(item['premises'], item['binding'], bad, ctx)
    assert good['target_model'] == 'NOT_APPLICABLE'


def test_compact_private_transport_still_rejects_substituted_frozen_model(tmp_path):
    async def run():
        _, ctx, item, m = prepared(tmp_path)
        m['observer']['source_annotations'][0]['source_claim']['speaker'] = 'substitution'
        with pytest.raises(ValueError, match='STALE_ARTIFACT_MODEL_CONTRACT'):
            await call('artifact_check', {'premises': item['premises'], 'binding': item['binding'],
                'profile': 'typed008/1', 'model': m}, context=ctx)
    asyncio.run(run())


def test_registered_middle_view_does_not_enter_llm_strategy_dispatch(tmp_path):
    async def run():
        from research_automation.contract import Problem
        provider = AnnotationProvider()
        c = Controller(Service(tmp_path/'dav.sqlite3'), semantic_provider=provider)
        first = c.ingest('MIDDLE_QA', raw('State A becomes B.\nState B becomes A.\n', interpretation='observer012'), 'source')
        case = c.journal.case('MIDDLE_QA', first['case_ids'][0])
        for _ in range(3):
            last = c.journal.steps('MIDDLE_QA', case['id'])[-1]
            if last['payload']['status'] == 'PROPOSING': break
            await c.tick()
        last = c.journal.steps('MIDDLE_QA', case['id'])[-1]
        assert last['payload']['status'] == 'PROPOSING'
        state = deepcopy(last['payload']['state'])
        state['pending_action']['strategy'] = 'artifact009-middle/1'
        await artifact.advance(c, case, last, state, Problem.model_validate(case['payload']['problem']), None)
        checkpoints = c.journal.rows(('artifact_checkpoint',), 'MIDDLE_QA', case_id=case['id'])
        assert checkpoints[-1]['payload']['action'] == 'observe'
        assert checkpoints[-1]['payload']['result']['observer'] == 'artifact009-middle/1'
    asyncio.run(run())


def test_registered_middle_view_cannot_change_012_attention_profile():
    from research_automation.semantic011 import attention_actions
    views = [{'source_packet': {'id': 'p'}, 'observer': 'observer012/1',
        'general_source_loss_ledger': [{'reason': 'UNKNOWN_LINK'}], 'unparsed_refs': ['r']},
        {'source_packet': {'id': 'p'}, 'observer': 'artifact009-middle/1'}]
    _, actions = attention_actions(views, [{'id': 'p'}], {'next_window': 1})
    assert actions and actions[0]['strategy'] == 'observer012-contrast/1'


def test_cross_line_feature_evidence_stays_in_authenticated_context(tmp_path):
    c = Controller(Service(tmp_path/'dav.sqlite3'))
    first = c.ingest('QA012', raw('State A becomes B.\nState B becomes A.\nThe color is red.\n'), 'source')
    ctx = resolve(c.service.store, 'QA012', first['source_snapshot']['id'])
    packet = packets(ctx)[0][0]; p, r = annotation(packet)
    from semantic_repair.inference011 import canonical_packet
    canonical, _ = canonical_packet(packet)
    p['readings'][0]['states'][0]['features'].append({'feature': 'red', 'evidence': {'ref': canonical['spans'][2]['id'], 'quote': 'red'}})
    item = assemble([align(packet, p, r)], 'QA012')['plans'][0]
    m = compile_model(item['premises'], item['binding'], profile='typed008/1', context=ctx)
    assert any(ref.endswith(':line3') for ref in item['premises'][0]['source_refs'])
    assert check_model(item['premises'], item['binding'], m, ctx)['analysis']['all_operations_independently_replayed']


def test_unsampled_referenced_observer_endpoint_is_explicitly_unknown(tmp_path):
    def mutate(p, r):
        h=p['readings'][0]; e=h['states'][0]['evidence']
        h['observers']=[{'id':'O','owner':'QA source reader','evidence':e,'criterion':'SET','features':['color'],
            'samples':[{'state_id':'B','values':[{'feature':'color','value':'red','evidence':e}]}]}]
        for edge in h['relations']: edge['source_claim']['observer_id']='O'
    _,ctx,item,m=prepared(tmp_path,mutate)
    rows=check_model(item['premises'],item['binding'],m,ctx)['analysis']['observer_comparisons']
    assert rows and all(x['status']=='UNKNOWN' and x['unknown_mask']==['color'] for x in rows)
