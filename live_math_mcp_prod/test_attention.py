"""Oracle tests: relations and invariance, without testing the expected model phrase."""
import copy

from attention_fixture import fixture,candidates,relations,semantic_attention,SEEDS
from frontier import ResearchMoveFingerprint


def test_fixture_is_semantically_stable_but_event_and_obligation_orders_change():
    a,b=map(fixture,SEEDS)
    assert a['source_hash']==b['source_hash'] and a['words']==b['words']
    assert a['event_order']!=b['event_order'] and a['obligation_order']!=b['obligation_order']
    assert a['events']==b['events']


def test_cosmetic_alias_has_same_claim_fingerprint_and_scope():
    f=fixture(SEEDS[0]);events={k:i+1 for i,k in enumerate(f['event_order'])};roots={k:i+10 for i,k in enumerate(f['obligation_order'])}
    cs=candidates(f,events,roots)
    assert ResearchMoveFingerprint.build(cs['C']['move']['proposed_operation'])==ResearchMoveFingerprint.build(cs['D']['move']['proposed_operation'])
    assert cs['C']['move']['scope']==cs['D']['move']['scope']
    assert 'p_even' not in cs['A']['depends_on'] and 'p_even' in cs['G']['depends_on']


def test_attention_oracle_uses_relations_not_the_response_wording():
    output={'attention':{'selected_candidate_id':'any-name','considered_event_ids':[71]},'candidates':[
        {'candidate_id':'any-name','depends_on':['p_finite'],'requires_review':False,'purpose':'experiment'}]}
    assert semantic_attention(output,71)['consistent']
    changed=copy.deepcopy(output);changed['candidates'][0]['depends_on'].append('p_even')
    assert not semantic_attention(changed,71)['consistent']
    changed=copy.deepcopy(output);changed['attention']['considered_event_ids']=[]
    assert not semantic_attention(changed,71)['consistent']


def test_negative_scope_is_not_an_active_dependency():
    f=fixture(SEEDS[0]);events={k:i+1 for i,k in enumerate(f['event_order'])};roots={k:i+1 for i,k in enumerate(f['obligation_order'])}
    expected=relations(f,events,roots)
    unrelated=next(edge for edge in expected['edges'] if edge['source_event']==events['unrelated'])
    assert unrelated['target_premise'] not in expected['candidate_dependencies']['A']
    assert unrelated['scope']!=f['scopes']['active']


def test_new_binding_key_can_append_metadata_without_a_duplicate_move(tmp_path):
    from research_store import ResearchStore
    from test_frontier import historical_database,BLUEPRINT
    from test_move_lifecycle import proposal
    path=tmp_path/'history.sqlite3';historical_database(path)
    store=ResearchStore(path);store.frontier.import_history(BLUEPRINT,'oracle regression')
    request=proposal(store)
    first=store.frontier.record_move('RH',request,'original')
    before=store.verify_audit()['entries']
    linked=store.frontier.record_move('RH',request,'another-binding-key')
    assert linked['id']==first['id'] and linked['idempotent']
    assert store.verify_audit()['entries']==before+1
    before_repeat=store.verify_audit()
    assert store.frontier.record_move('RH',request,'another-binding-key')['id']==first['id']
    assert store.verify_audit()==before_repeat
