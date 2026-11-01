"""Real source acceptance plus adversarial typed realization controls."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from artifact_genesis.contract import RawPacket
from artifact_genesis.source import packet_from_text
from davcore.ast import digest
from semantic_repair.compiler import compile_model
from semantic_repair.contract import CompilerRequest, coordinate
from semantic_repair.observe005 import observe as old_observe
from semantic_repair.observe008 import observe
from semantic_repair.realization import PROFILE, observe_state
from semantic_repair.study008 import merge_slices
from semantic_repair.trace008 import adapter, trace, study_model, questions, certify, evaluate, compare
from semantic_repair.worker import call
from semantic_repair.search import enumerate_bindings, summarize


def packet(task, part='proposal_packet'):
    root=Path(__file__).resolve().parent.parent/'typed_realization008'
    catalog=json.loads((root/'frozen/catalog.json').read_text())
    t=next(t for t in json.loads((root/'frozen/tasks.json').read_text()) if t['id']==task)
    return RawPacket.model_validate_json((root/catalog[t[part]]['path']).read_text())


def setup_r4(mode='REPLACE',middle='LINK_LOCAL_ROLE'):
    obs=observe(packet('R4'),strategy='typed008-middle/1');ps=obs['slices'][0]['premises']
    b={'id':'candidate','assignments':{'update_mode':mode,'middle_policy':middle}}
    return ps,b,compile_model(ps,b,profile=PROFILE)


def setup_p4():
    obs=[observe(packet('P4')),observe(packet('P4','validation_packet'))]
    ps=merge_slices(obs)[0]['premises']
    b={'id':'candidate','assignments':{'narrative_referent':'CONTINUED_SUBJECT','story_time':'NARRATED_ORDER'}}
    return ps,b,compile_model(ps,b,profile=PROFILE)


def setup_p3(subject='CONTINUED_SUBJECT',part='validation_packet'):
    ps=observe(packet('P3',part))['slices'][0]['premises']
    b={'id':'candidate','assignments':{'response_subject':subject}}
    return ps,b,compile_model(ps,b,profile=PROFILE)


def test_legacy_stage_and_default_compiler_stay_intact():
    p=packet('R4');old=old_observe(p,strategy='discourse005/1')
    before=[coordinate(r) for x in old['premises'] for r in (x['src'],x['dst'])]
    ps,b,m=setup_r4()
    assert before==[coordinate(r) for x in ps for r in (x['src'],x['dst'])]
    assert len(set(before))==4 and m['coordinate_count']==5
    legacy=compile_model(old['premises'],{'id':'old','assignments':{}})
    assert 'profile' not in legacy and legacy['coordinate_count']==4
    assert all(set(r['reactants'])<=set(r['products']) for r in legacy['spec']['reaction_network']['reactions'])
    assert [p['id'] for p in ps]==[p['id'] for p in old['premises']]


@pytest.mark.parametrize('mode',['REPLACE','ACCUMULATE'])
def test_R4_both_guards_and_missing_guard_are_executable(mode):
    ps,b,m=setup_r4(mode);a=adapter(m);analysis=study_model(m)
    assert len(m['guards'])==2 and len({g['id'] for g in m['guards']})==2
    t=next(t for t in analysis['traces'] if t['all_steps_fired'])
    assert len(t['steps'])==2 and t['steps'][0]['after']==t['steps'][1]['before']
    assert analysis['invariants']['guards_conserved']
    for g in m['guards']:
        missing=trace(m,t['initial_state']&~(1<<g['coordinate']),m['premise_ids'])
        assert not missing['all_steps_fired'] and any(not s['enabled'] for s in missing['steps'])
    first=m['observer']['role_pairs'][0][0]
    assert a.apply('S'+str(first),t['final_state'])==int(mode=='ACCUMULATE')
    assert analysis['order_witnesses'] and not analysis['real_round_trips']


def test_R4_binding_and_update_have_computed_effects():
    _,_,linked=setup_r4();_,_,separate=setup_r4(middle='SEPARATE_OCCURRENCES')
    assert compare(linked,separate)['kind']=='REGISTERED_TRACE_DIFFERENCE'
    assert study_model(separate)['outcome']=='NO_ENABLED_COMPLETE_TRACE'
    _,_,accumulate=setup_r4('ACCUMULATE')
    w=compare(linked,accumulate)
    assert w['kind']=='DISTINGUISHING_EXECUTION_OR_OBSERVER' and w['witness']
    assert all(not r['entity_identity'] for r in linked['role_map'])


def test_each_R4_source_unit_is_a_real_dependency():
    ps,b,m=setup_r4();t=next(t for t in study_model(m)['traces'] if t['all_steps_fired'])
    for p in ps:
        d=compile_model(ps,b,profile=PROFILE,disabled=(p['id'],))
        neg=trace(d,t['initial_state'],m['premise_ids'])
        assert neg['final_state']!=t['final_state'] and not neg['all_steps_fired']


def test_disabled_capacity_and_preexisting_endpoint_are_not_firing():
    _,_,m=setup_r4();i,j=m['observer']['role_pairs'][0]
    both_guards=sum(1<<g['coordinate'] for g in m['guards'])
    t=trace(m,(1<<i)|(1<<j)|both_guards,[m['premise_ids'][0]])
    assert not t['steps'][0]['enabled'] and not t['steps'][0]['fired']
    t=trace(m,0,m['premise_ids'])
    assert t['initial_state']==t['final_state'] and not t['actual_round_trip']


def test_real_round_trip_needs_two_enabled_changes():
    ps,b,_=setup_r4();ps=deepcopy(ps)
    ps[1]['src']=deepcopy(ps[0]['dst']);ps[1]['dst']=deepcopy(ps[0]['src'])
    m=compile_model(ps,b,profile=PROFILE)
    assert any(t['actual_round_trip'] for t in study_model(m)['traces'])


def test_P4_command_parser_and_order_are_source_bound():
    p=packet('P4','validation_packet');o=observe(p)
    commands=[x for s in o['slices'] for x in s['premises'] if x['realization']['kind']=='PRESCRIPTION']
    assert len(commands)==1 and set(commands[0]['source_refs'])=={s.id for s in p.spans}
    ps,b,m=setup_p4();assert len(ps)==5 and m['coordinate_count']==8
    t=study_model(m)['traces'][0];assert t['all_steps_fired']
    assert t['final_observation']['prescription']=='ATTESTED' and t['final_observation']['performance']=='UNKNOWN'
    assert study_model(m)['invariants']['no_performance_attested']
    assert study_model(m)['order_witnesses']
    for p in ps:
        disabled=compile_model(ps,b,profile=PROFILE,disabled=(p['id'],))
        assert not trace(disabled,m['initial_states'][0],m['premise_ids'])['all_steps_fired']
    swapped=deepcopy(ps);swapped[0],swapped[1]=swapped[1],swapped[0]
    alt=compile_model(swapped,b,profile=PROFILE)
    assert not trace(alt,m['initial_states'][0],m['premise_ids'])['all_steps_fired']
    assert alt['observer']['occurrences']!=m['observer']['occurrences']


def test_narrative_uncertainty_has_scoped_full_projection_equivalence():
    ps,b,m=setup_p4();other=deepcopy(b);other['assignments']['narrative_referent']='OTHER_PARTICIPANT'
    alt=compile_model(ps,other,profile=PROFILE);w=compare(m,alt)
    assert w['kind']=='EXHAUSTIVE_TARGET_PROJECTION_EQUIVALENCE' and w['states_checked']==256
    assert m['binding_assignments']!=alt['binding_assignments']


def test_P3_signed_direction_unknown_and_conditional_binding():
    _,_,m=setup_p3();t=study_model(m)['traces'][0];o=t['final_observation']
    assert t['all_steps_fired'] and o['back_status']=='NEGATIVE' and o['outgoing_any_actor']
    _,_,initial=setup_p3(part='proposal_packet')
    assert study_model(initial)['traces'][0]['final_observation']['back_status']=='UNKNOWN'
    _,_,other=setup_p3('OTHER_PARTICIPANT');w=compare(m,other)
    assert w['kind']=='DISTINGUISHING_EXECUTION_OR_OBSERVER'
    assert study_model(other)['traces'][0]['final_observation']['outgoing_for_original_addressee']=='UNKNOWN'
    assert 'FACT' not in m['binding_assignments'].values()


@pytest.mark.parametrize('positive,negative,status',[(0,0,'UNKNOWN'),(1,0,'POSITIVE'),(0,1,'NEGATIVE'),(1,1,'CONFLICT')])
def test_all_signed_markings_explicit_without_explosion(positive,negative,status):
    _,_,m=setup_p3();o=m['observer'];s=1<<o['tokens']['outgoing']
    s|=positive<<o['tokens']['back_positive'];s|=negative<<o['tokens']['back_negative']
    result=observe_state(m,s)
    assert result['back_status']==status and result['outgoing_any_actor']


def test_full_vs_subset_and_stale_contracts():
    ps,b,m=setup_r4();q=next(q for q in questions(m) if q['kind']=='PERSISTENCE' and q['coordinate']==m['guards'][0]['coordinate'])
    c=certify(ps,b,m,q);full=evaluate(ps,b,m,c);sample=evaluate(ps,b,m,c,states=[m['initial_states'][0]])
    assert full['dav']['status']=='proved' and sample['dav']['status']=='consistent_with_observations'
    assert sample['dav']['scope']['domain']=='sample' and not full['source_claim_verified']
    for field in ('formula','model_hash','observer_version','profile'):
        bad=deepcopy(c)
        if field=='formula':bad['query'][field]['body']['left']['operation']='Zero'
        else:bad['query'][field]='other'
        bad['seal']=digest({k:v for k,v in bad.items() if k!='seal'})
        with pytest.raises(ValueError):evaluate(ps,b,m,bad)
    foreign=deepcopy(ps);foreign[0]['source_hash']='a'*64
    with pytest.raises(ValueError):certify(foreign,b,m,q)


@pytest.mark.parametrize('key',['q','query','gold','answer','expected_answer','expected_labels','rationale','metadata','cache','transitive_closure','desired_conclusion'])
def test_query_compiler_firewall_recurses_into_realizations(key):
    ps,b,_=setup_r4();ps=deepcopy(ps);ps[0]['realization'][key]='injected'
    with pytest.raises(ValueError,match='QUERY_COMPILER_FIREWALL'):
        CompilerRequest.model_validate({'premises':ps,'binding':b,'profile':PROFILE})


def test_alpha_renaming_is_not_task_dispatch():
    ps,b,m=setup_r4();other=deepcopy(ps)
    renames={r['predicate']:'p_'+digest(['renamed',r['predicate']])[:24] for p in other for r in (p['src'],p['dst'])}
    for p in other:
        p['realization']['label']='Unseen title and words'
        for r in (p['src'],p['dst']):r['predicate']=renames[r['predicate']]
    renamed=compile_model(other,b,profile=PROFILE)
    assert [t['final_state'] for t in study_model(m)['traces']]==[t['final_state'] for t in study_model(renamed)['traces']]


def test_raw_parser_applies_to_unseen_document_ids_and_unattested_text():
    p=packet('P4','validation_packet');o=observe(p)
    renamed=p.model_copy(update={'id':'new_packet','document_id':'unseen'})
    assert observe(renamed)['slices']==o['slices']
    arbitrary=observe(packet_from_text('nothing','A quiet stone lies here.\n'))
    assert arbitrary['slices']==[]


def test_bound_instead_of_silent_narrative_truncation():
    ps,b,_=setup_p4();extended=deepcopy(ps)
    for i in range(4):
        p=deepcopy(ps[0]);p['id']='u_'+digest(i)[:24];extended.append(p)
    model=compile_model(extended,b,profile=PROFILE)
    assert model['status']=='BOUND_INSUFFICIENT_FOR_QUERY'
    with pytest.raises(ValueError):questions(model)


def test_real_worker_isolated_typed_observer_and_compiler():
    async def exercise():
        p=packet('R4');o=await call('observe',{'packet':p.model_dump(),'strategy':'typed008-middle/1'})
        ps,b,m=setup_r4()
        response=await call('compile',{'premises':o['slices'][0]['premises'],'binding':b,'profile':PROFILE})
        isolation=response.pop('isolation');assert response==m
        assert isolation['probes']=={'file':'DENIED','socket':'DENIED'} and isolation['query_modules_loaded']==[]
        assert o['isolation']['query_modules_loaded']==[]
    asyncio.run(exercise())


def test_no_empty_or_truncated_universal_family_credit():
    empty=enumerate_bindings([{'id':'unresolved','values':[]}])
    assert summarize(empty,[])['universal_claim'] is False
    large=enumerate_bindings([{'id':'d','values':[str(i) for i in range(33)]}])
    assert large['truncated'] and summarize(large,[{'status':'CHECKED'}]*32)['universal_claim'] is False


@pytest.mark.parametrize('field',['scope','domain'])
def test_foreign_target_role_rejected(field):
    ps,b,_=setup_r4();ps=deepcopy(ps)
    ps[1]['dst'][field]='s_'+'f'*24 if field=='scope' else 'foreign_domain'
    with pytest.raises(ValueError,match='CROSS_SOURCE_SCOPE'):compile_model(ps,b,profile=PROFILE)


def test_unaddressed_guard_and_unsupported_signed_roles_rejected():
    ps,b,_=setup_r4();ps=deepcopy(ps);ps[0]['realization']['guards'][0]['source_refs']=['foreign:99']
    with pytest.raises(ValueError,match='UNADDRESSED_GUARD'):compile_model(ps,b,profile=PROFILE)
    ps,b,_=setup_p3();ps=deepcopy(ps);ps[0]['realization']['sign']='NEGATIVE'
    with pytest.raises(ValueError,match='NEGATIVE_INPUT_NOT_SUPPORTED'):compile_model(ps,b,profile=PROFILE)


def test_multiple_prescriptions_remain_readable_without_performance():
    p=packet_from_text('directions','Скажи слово.\nТишина.\nСлушай голос.\n',language='ru')
    o=observe(p);s=o['slices'][0]
    b={'id':'b','assignments':{d['id']:d['values'][0] for d in s['dimensions']}}
    m=compile_model(s['premises'],b,profile=PROFILE)
    t=study_model(m)['traces'][0]
    assert len(t['steps'])==2 and t['all_steps_fired'] and t['final_observation']['performance']=='UNKNOWN'
