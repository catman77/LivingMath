"""Integrated source/target/dataflow controls; synthetic cases do not count as real n."""
from copy import deepcopy
import json

import pytest

from artifact_genesis.journal import Journal
from artifact_genesis.source import packet_from_text
from davcore.ast import digest
from semantic_repair import alignment as a
from semantic_repair.compiler import compile_family
from semantic_repair.experiment import derive007, controls007
from semantic_repair.observe005 import observe
from semantic_repair.query import evaluate, target_contract, verify_target_contract
from semantic_repair.scoped import Claim, compare, from_query
from semantic_repair.search import enumerate_bindings
from semantic_repair.source import ObligationQueue
from test_source_alignment006 import calibration


def chain():
    obs=observe(packet_from_text('effects','A implies B.\nB implies C.\n'),strategy='discourse005/1')
    ds=[{'id':'role','kind':'referent','scope':'local','values':['same','other']},
        {'id':'colour','kind':'irrelevant','scope':'local','values':['red','blue']}]
    obs['premises'][1]['requires_binding']={'role':'same'}
    f=enumerate_bindings(ds);return obs,compile_family(obs['premises'],f,ds)


def test_binding_effects_and_projection_equivalence_are_executed():
    obs,p=chain()
    assert p['source_binding_count']==4 and p['distinct_target_models']==2
    assert any(w['kind']=='DISTINGUISHING_EXECUTION' for w in p['binding_effects'][0]['execution_witnesses'])
    assert all(w['kind']=='EXHAUSTIVE_TARGET_PROJECTION_EQUIVALENCE' for w in p['binding_effects'][1]['execution_witnesses'])
    branch=next(b for b in p['branches'] if b['queries']);q=branch['queries'][0]
    assert {evaluate(m,q)['value'] for m in p['models']}=={True,False}
    assert any(not b['queries'] for b in p['branches'])


def test_target_formula_mapping_premise_substitution_after_seal():
    obs,p=chain();b=next(b for b in p['branches'] if b['queries']);m=next(m for m in p['models'] if m['compiled_hash']==b['model_hash'])
    q=b['queries'][0];c=from_query(q,obs['premises'],'synthetic',role_bound=True)
    contract=target_contract(c,obs['premises'],b['binding'],m,q)
    assert verify_target_contract(contract,contract['contract_sha256'],c,obs['premises'],b['binding'],m)['target_query_verified']
    for kind in ['formula','mapping']:
        bad=deepcopy(contract)
        if kind=='formula':bad['query']['formula']['body']['conclusion']['right']['operation']='Zero'
        else:bad['source_to_target']['subject']='some_other_atom'
        bad['contract_sha256']=digest({k:v for k,v in bad.items() if k!='contract_sha256'})
        with pytest.raises(ValueError):verify_target_contract(bad,contract['contract_sha256'],c,obs['premises'],b['binding'],m)
    changed=deepcopy(obs['premises']);changed[0]['src']['predicate']='p_'+'a'*24
    with pytest.raises(ValueError):verify_target_contract(contract,contract['contract_sha256'],c,changed,b['binding'],m)


def test_K_C_is_query_independent_and_goal_not_an_assumed_premise():
    req,ev,_,_=calibration(forward_evidence=True);candidate=a.candidates(req,ev)['candidates'][0]
    model=a.compile_transport(req['source_frame'],ev,candidate)
    assert model['compiler_received_query_formula'] is False and model['compiler_received_verdict'] is False
    positive=a.check_transport(model,req)
    assert positive['entails'] and positive['active_antecedent_states']
    reverse,other,_,_=calibration();candidate=a.candidates(reverse,other)['candidates'][0]
    reverse_model=a.compile_transport(reverse['source_frame'],other,candidate)
    proof=a.check_transport(reverse_model,reverse)
    assert not proof['entails'] and proof['evidence']['counterexample']
    assert not any(c['from']==0 and c['to']==1 for c in model['constraints'])
    tampered=deepcopy(model);tampered['constraints'].pop()
    with pytest.raises(ValueError,match='AFTER_SEAL'):a.check_transport(tampered,req)


def test_context_view_changes_source_model_not_only_hash():
    train,ev=p3_fixture();f=next(f for f in a.observe(train)['frames'] if 'гром' in f['stimulus'])
    req=a.request(f,a.claim_for_frame(f),'tag_only',train)
    before=a.assess(req,a.observe(ev));after=a.assess(req,a.observe(ev,strategy=a.CONTEXT_STRATEGY))
    assert before['conditional_source_models']==0 and after['conditional_source_models']==1
    left=before['branches'][0]['source_transport'];right=after['branches'][0]['source_transport']
    assert len(left['compiled']['constraints'])<len(right['compiled']['constraints'])
    assert left['model_states']!=right['model_states']
    assert not left['entails'] and right['entails']


def p3_fixture():
    from artifact_genesis.contract import RawPacket
    raw=packet_from_text('transfer','Ревет ли зверь,\nГремит ли гром —\nНа всякий звук\nСвой отклик\nРодишь ты вдруг.\nТы внемлешь грохоту громов,\nИ шлешь ответ;\nТебе ж нет отзыва...\n',language='ru').model_dump()
    return RawPacket.model_validate({**raw,'spans':raw['spans'][:5]}),RawPacket.model_validate({**raw,'spans':raw['spans'][5:]})


def claim(**changes):
    return Claim(**({'predicate':'P','subject':'x','object':'true','domain':'D','quantifier':'ALL','polarity':'POSITIVE',
        'modality':'TEXTUAL_CLAIM','time':'GENERIC','stage':'S','scope':'local','source_hash':'a'*64,'edition':'e'}|changes))


def test_quantified_compatibility_membership_and_empty_antecedent():
    q=claim(quantifier='SOME');assert compare(q,q.model_copy(update={'polarity':'NEGATIVE'}),[])['status']=='COMPATIBLE_ONLY'
    q=claim(domain_members=('w1',));e=claim(quantifier='NAMED_CASE',polarity='NEGATIVE',witness_id='w1')
    assert compare(q,e,['event:1'])['status']=='REFUTES_EXACT_CLAIM'
    assert compare(q,e.model_copy(update={'witness_id':'foreign'}),[])['status']=='UNRESOLVED'
    q=claim(antecedent_nonempty=False)
    assert compare(q,q.model_copy(update={'polarity':'NEGATIVE'}),[])['status']!='REFUTES_EXACT_CLAIM'
    assert compare(claim(),None,[])['status']=='UNRESOLVED'
    q=claim(quantifier='NAMED_CASE',witness_id='one')
    assert compare(q,q.model_copy(update={'witness_id':'two'}),[])['status']=='UNRESOLVED'


def test_quote_and_actor_changes_are_real_source_perturbations():
    raw=packet_from_text('quoted','«Ревет ли зверь,\nНа всякий звук\nСвой отклик\nРодишь ты вдруг.»\n',language='ru')
    frames=a.observe(raw)['frames'];assert frames and all(f['discourse']=='QUOTED_OR_REPORTED' for f in frames)
    assert all(f['modality']=='REPORTED_SPEECH' for f in frames)
    one=packet_from_text('roles','Ты внемлешь шуму,\nОн не шлешь ответ.\n',language='ru')
    f=a.observe(one)['frames'][0];assert f['actor']=='он' and f['stimulus_actor']=='local_second_person' and f['polarity']=='NEGATIVE'


def test_obligation_queue_selection_budget_and_persistence(tmp_path):
    q=ObligationQueue(2);actions=[{'id':'a','covers':['one'],'cost':2},{'id':'b','covers':['one','two'],'cost':1}]
    d=q.choose([{'kind':'one'},{'kind':'two'}],actions);assert d['action']['id']=='b'
    q.complete(d['action']);j=Journal(tmp_path/'journal.jsonl');j.append('COMPLETED_ACTION',d)
    persisted=json.loads(j.path.read_text())['payload'];restored=ObligationQueue(2);restored.complete(persisted['action'])
    assert restored.choose([{'kind':'one'}],actions)['action']['id']=='a'
    restored.complete(actions[0]);assert restored.choose([{'kind':'one'}],actions)['stop']=='CATALOGUE_EXHAUSTED'
    assert restored.choose([{'kind':'one'}],actions+[{'id':'c','covers':['one']}])['stop']=='BUDGET_EXHAUSTED'
    assert Journal.verify(j.path)['ok']


def result_row(definition):
    from artifact_genesis.contract import RawPacket
    link='reply means echo' if definition else 'echo means reply'
    raw=packet_from_text('gate',f'Whenever a bell reaches keeper, keeper sends an echo.\nbell implies middle.\nmiddle implies echo.\nWhenever a bell reaches keeper, keeper sends a reply.\nHere, {link}.\n').model_dump()
    train=RawPacket.model_validate({**raw,'spans':raw['spans'][:3]});ev=RawPacket.model_validate({**raw,'spans':raw['spans'][3:]})
    obs=observe(train,strategy='discourse005/1');p=compile_family(obs['premises'],enumerate_bindings([]),[])
    b=p['branches'][0];m=p['models'][0];q=b['queries'][0];frame=a.observe(train)['frames'][0]
    c=a.claim_for_frame(frame);req=a.request(frame,c,q['query_id'],train);view=a.observe(ev)
    contract=target_contract(c,obs['premises'],b['binding'],m,q)
    return {'task_id':'synthetic','kind':'alignment','claim':c.model_dump(),'request':req,'view':view,
        'premises':obs['premises'],'binding':b['binding'],'model':m,'target_contract':contract,
        'contract_commit':contract['contract_sha256'],'target_check':verify_target_contract(contract,contract['contract_sha256'],c,obs['premises'],b['binding'],m),
        'outcome':a.assess(req,view),'legacy_control':False}


def test_measured_controls_and_semantic_status_changes_with_evidence():
    assert all(c['passed'] for c in controls007())
    positive=result_row(True);negative=result_row(False)
    assert derive007([positive],[],[],controls007())['SOURCE_CLAIM_SUPPORT']['new_exact']==1
    assert derive007([negative],[],[],controls007())['SOURCE_CLAIM_SUPPORT']['new_exact']==0
    damaged=deepcopy(negative);damaged['outcome']=positive['outcome']
    with pytest.raises(ValueError,match='WITHOUT_MATCHING'):derive007([damaged],[],[],controls007())


def test_derive_rejects_outcomes_without_artifacts():
    with pytest.raises((KeyError,ValueError)):
        derive007([{'claim':claim().model_dump(),'outcome':{'status':'SUPPORTS_EXACT_CLAIM'}}],[],[],[])
    result=derive007([],[],[],[])
    assert result['SOURCE_CLAIM_SUPPORT']['exact']==0 and result['ENGINEERING_SOUNDNESS']=='FAIL'
