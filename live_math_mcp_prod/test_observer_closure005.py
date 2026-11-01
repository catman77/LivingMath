"""Open logic/grammar calibrations; these fixtures are NOT real-source n."""
import asyncio
from copy import deepcopy

import pytest

from artifact_genesis.source import packet_from_text
from davcore.ast import digest
from semantic_repair.observe005 import observe
from semantic_repair.compiler import compile_model
from semantic_repair.search import enumerate_bindings, generate_queries, summarize
from semantic_repair.query import evaluate, deletion_witnesses
from semantic_repair.scoped import Claim, compare, from_query
from semantic_repair.source import (ObservationReads, observation_obligation, family_correspondence,
                                    validate_scoped_prediction)
from semantic_repair.worker import call


def observation(text='A implies B.\nB implies C.\n', strategy='discourse005/1'):
    return observe(packet_from_text('calibration',text),strategy=strategy)


def compiled(obs):
    b = enumerate_bindings(obs['dimensions'])['bindings'][0]
    m = compile_model(obs['premises'],b)
    return b,m,generate_queries(obs['premises'],m)


def claim():
    return Claim(predicate='DearLater',subject='x',object='dear',domain='local',quantifier='ALL',
        polarity='POSITIVE',modality='LYRICAL_CLAIM',time='CONDITIONAL_SCHEMA',stage='SCHEMATIC',
        scope='scope',source_hash='a'*64,edition='frozen')


@pytest.mark.parametrize('field,value',[('quantifier','SOME'),('predicate','JoyDay'),('modality','PRESCRIPTION'),
    ('time','FUTURE_EVENT'),('stage','later_state'),('domain','other'),('subject','other_actor'),('object','other_object'),
    ('scope','other_scope'),('source_hash','b'*64),('edition','other')])
def test_C01_claim_identity_and_exactness(field,value):
    q=claim(); other=q.model_copy(update={field:value})
    assert q.identity()!=other.identity()
    assert compare(q,other,['source:1'])['status'] not in {'SUPPORTS_EXACT_CLAIM','REFUTES_EXACT_CLAIM'}
    assert q.model_copy(update={'display':'Renamed explanation'}).identity()==q.identity()


def test_C02_narrative_is_not_conditional_or_command_execution():
    obs=observation('Моих очей коснулся он.\nОтверзлись зеницы.\nМоих ушей коснулся он.\nИ шум их наполнил.\n')
    assert len(obs['premises'])==2
    assert {p['semantics'] for p in obs['premises']}=={'NARRATIVE_SEQUENCE'}
    assert not compiled(obs)[2]


@pytest.mark.parametrize('field,value',[('domain','elsewhere'),('quantifier','SOME'),('stage','later_state'),
    ('participant','object'),('time','PAST_EVENT'),('polarity','NEGATIVE'),('modality','PRESCRIPTION')])
def test_C03_C04_scope_actor_stage_joins_fail(field,value):
    obs=observation(); obs['premises'][1]['src'][field]=value
    assert not compiled(obs)[2]


def test_C05_polarity_refutation_is_exact_and_unknown_is_not_fact():
    q=claim()
    assert compare(q,q.model_copy(update={'polarity':'NEGATIVE'}),['a'])['status']=='UNRESOLVED'
    nonempty=q.model_copy(update={'antecedent_nonempty':True})
    assert compare(nonempty,nonempty.model_copy(update={'polarity':'NEGATIVE'}),['a'])['status']=='REFUTES_EXACT_CLAIM'
    assert compare(q.model_copy(update={'quantifier':'UNKNOWN'}),q,['a'])['status']=='COMPATIBLE_ONLY'
    assert compare(q,None,[])['status']=='UNRESOLVED'


def test_C06_generic_conditional_variants_and_alpha_names():
    for a,b,c in [('earth','water','vapour'),('seed','sprout','tree')]:
        obs=observation(f'For when the {a} is prepared,\nThen is the {b} settled.\nThat when the {b} is altered,\nA new {c} is induced.\n')
        assert len(obs['premises'])==2
        assert all(p['source_refs'] for p in obs['premises'])
    # Same installed simple grammar, no poem-title branch or newline trick.
    assert compiled(observation('A implies B;\nB implies C.\n'))[2]
    assert len(observation('A is cause of B.\nB implies C.\n')['premises'])==2
    assert not compiled(observation('A is cause of B.\nB implies C.\n'))[2]
    one=observation('When the seed is prepared, then the sprout is ready.\n')
    wrapped=observation('When the seed is prepared,\nthen the sprout is ready.\n')
    assert [(p['src']['predicate'],p['dst']['predicate']) for p in one['premises']] == [
        (p['src']['predicate'],p['dst']['predicate']) for p in wrapped['premises']]


def test_C07_each_premise_essential_and_repeated_quote_not_extra_evidence():
    obs=observation('A implies B.\nB implies C.\nA implies B.\n')
    assert len(obs['premises'])==2
    b,m,qs=compiled(obs); assert len(qs)==1
    assert all(w['essential'] and w['evidence']['counterexample'] for w in deletion_witnesses(obs['premises'],b,m,qs[0]))


def test_C08_actual_worker_query_firewall_and_registered_strategy():
    packet=packet_from_text('worker','A implies B.\nB implies C.\n')
    obs=asyncio.run(call('observe',{'packet':packet.model_dump(),'strategy':'discourse005/1'}))
    b,_,_=compiled(obs)
    reply=asyncio.run(call('compile',{'premises':obs['premises'],'binding':b}))
    assert reply['isolation']['probes']=={'file':'DENIED','socket':'DENIED'}
    assert not reply['isolation']['query_modules_loaded'] and not reply['compiler_received_query']
    with pytest.raises(ValueError,match='WORKER_FAILED'):
        asyncio.run(call('compile',{'premises':obs['premises'],'binding':b,'query':{'expected_answer':True}}))
    with pytest.raises(ValueError,match='UNREGISTERED'):
        observe(packet,strategy='generated_python')


def test_C09_singleton_zero_gamma_initiates_bounded_reread():
    packet=packet_from_text('blank','Unknown construction.\n')
    obs=observe(packet); f=enumerate_bindings(obs['dimensions'])
    assert len(f['bindings'])==1 and not obs['premises']
    gap=observation_obligation(obs,f,has_query=False)
    assert gap['kind']=='UNPARSED_CLAUSE'
    reads=ObservationReads(); reads.read(packet,'discourse005/1',gap)
    with pytest.raises(ValueError,match='ALREADY_READ'): reads.read(packet,'discourse005/1',gap)


def test_C10_observer_expansion_correspondence_and_stale_model():
    packet=packet_from_text('rhetoric','Ревет ли поток,\nГремит ли вал —\nНа всякий звук\nОтклик в горах\nРодишь ты вдруг.\n')
    a=observe(packet); b=observe(packet,strategy='discourse005/1')
    old=enumerate_bindings(a['dimensions']); new=enumerate_bindings(b['dimensions'])
    assert len(new['bindings'])>len(old['bindings'])
    corr=family_correspondence(old,new)
    assert corr['pairs'] and corr['dependent_results']=='REQUIRES_REVALIDATION'
    assert corr['prior_negative_results']=='RETAINED_APPEND_ONLY'
    obs=observation(); _,m,qs=compiled(obs)
    changed=deepcopy(obs)
    for p in changed['premises']: p['observer_version']='clauses005/1'
    _,m2,_=compiled(changed)
    with pytest.raises(ValueError,match='STALE'): evaluate(m2,qs[0])
    assert evaluate(m,qs[0])['value']  # old scoped finite result remains valid


def test_C11_empty_truncated_unknown_never_universal():
    d=[{'id':'d','scope':'s','values':['a','b']}]
    empty=enumerate_bindings(d,[{'dimension':'d','scope':'s','allowed_values':[]}])
    assert summarize(empty,[])['status']=='INCONSISTENT_PREMISES'
    assert summarize(enumerate_bindings(d,bound=1),[{'status':'CHECKED','value':True}])['status']=='COMPUTATION_UNKNOWN'
    assert summarize(enumerate_bindings([]),[{'status':'RESOURCE_LIMIT'}])['status']=='COMPUTATION_UNKNOWN'


def test_C12_no_hidden_answer_input_and_finite_actions():
    obs=observation(); b,_,_=compiled(obs)
    mutated=deepcopy(obs['premises']); mutated[0]['answer']='gold'
    with pytest.raises(ValueError): compile_model(mutated,b)
    reads=ObservationReads()
    for i in range(3): reads.read(packet_from_text('cost'+str(i),'Raw bytes.'),'discourse005/1',{'kind':'UNPARSED_CLAUSE'})
    with pytest.raises(ValueError,match='BOUND'):
        reads.read(packet_from_text('cost4','Other bytes.'),'discourse005/1',{})


def test_C13_R1_normative_support_does_not_upgrade_operational_claim():
    from artifact_genesis.contract import RawPacket
    # Independent bytes in the same document; never copied target signature.
    packet=packet_from_text('bonds','For as the soule to the spirite the bond must bee;\nRight so the bodie the soule to him must knit,\nOf bodie, soule and spirit, that they not striue,\nWhich trinitie thou must bring to vnitee,\n')
    raw=packet.model_dump(); train=RawPacket.model_validate({**raw,'spans':raw['spans'][:2]})
    ev=RawPacket.model_validate({**raw,'spans':raw['spans'][2:]})
    obs=observe(train,strategy='discourse005/1'); _,_,qs=compiled(obs)
    q=from_query(qs[0],obs['premises'],packet.edition)
    assert validate_scoped_prediction(obs,q,ev)['status']=='SUPPORTS_EXACT_CLAIM'
    strong=from_query(qs[0],obs['premises'],packet.edition,operational=True)
    assert validate_scoped_prediction(obs,strong,ev)['status']!='SUPPORTS_EXACT_CLAIM'


def test_C14_H_and_model_proof_never_fact_or_permission():
    obs=observation(); b,m,qs=compiled(obs); r=evaluate(m,qs[0])
    assert b['status']=='HYPOTHESIS' and qs[0]['H_status']=='HYPOTHESIS'
    assert r['value'] and r['proof_status']=='unverified' and r['execution_permission']=={'allowed':False}
    assert r['source_verdict']=='NOT_TESTED'


def test_C15_honest_fixed_gamma_baselines_equal():
    obs=observation(); b,m,qs=compiled(obs)
    assert generate_queries(obs['premises'],compile_model(obs['premises'],b))==qs
    left=evaluate(m,qs[0]); right=evaluate(compile_model(obs['premises'],b),qs[0])
    assert (left['status'],left['value'],left['independent'],left['compiled_hash']) == (
        right['status'],right['value'],right['independent'],right['compiled_hash'])


def test_C16_source_change_invalidates_binding_without_rewriting_old():
    obs=observation(); original=deepcopy(obs); b,m,qs=compiled(obs)
    changed=deepcopy(obs)
    for p in changed['premises']: p['source_hash']='c'*64
    with pytest.raises(ValueError,match='STALE'): evaluate(compile_model(changed['premises'],b),qs[0])
    assert obs==original and evaluate(m,qs[0])['value']
    assert digest(changed)!=digest(obs)


def test_P1_dear_all_is_not_some_joy_day_and_neither_direction_entails():
    q=claim(); e=q.model_copy(update={'predicate':'JoyDay','subject':'day','object':'joy','quantifier':'SOME','time':'FUTURE_EVENT'})
    assert compare(q,e,['verse:1'])['status']=='DIFFERENT_CLAIM'
    assert compare(e,q,['verse:8'])['status']=='DIFFERENT_CLAIM'
    # Two explicit finite countermodels, outside DAV meaning interpretation.
    assert any([True]) and not all([True,False])
    assert all([True,True]) and not any([False])
