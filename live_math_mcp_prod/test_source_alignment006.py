"""Actual correspondence/feedback controls. Synthetic fixtures are not real n."""
import asyncio
from copy import deepcopy

import pytest

from artifact_genesis.contract import RawPacket
from artifact_genesis.source import packet_from_text
from artifact_genesis.journal import Journal
from semantic_repair import alignment as a
from semantic_repair.source import effective_method, evidence_use, require_current_alignment, ObservationReads
from semantic_repair.worker import call
from semantic_repair.compiler import compile_model
from semantic_repair.search import enumerate_bindings, generate_queries
from semantic_repair.observe005 import observe
from semantic_repair.query import evaluate, deletion_witnesses


def calibration(actor='keeper', stimulus='bell', response='reply', clause='Whenever', negative=False, recipient_actor=None, forward_evidence=False):
    text=(f'Whenever a {stimulus} reaches {actor}, {actor} sends an echo.\n'
          f'{clause} a {stimulus} reaches {actor}, {recipient_actor or actor} '+('does not send' if negative else 'sends')+f' a {response}.\n'
          +(f'Here, {response} means echo.\n' if forward_evidence else f'Here, echo means {response}.\n'))
    raw=packet_from_text('calibration',text).model_dump()
    train=RawPacket.model_validate({**raw,'spans':raw['spans'][:1]})
    evidence=RawPacket.model_validate({**raw,'spans':raw['spans'][1:]})
    source=a.observe(train);ev=a.observe(evidence)
    req=a.request(source['frames'][0],a.claim_for_frame(source['frames'][0]),'q_target',train)
    return req,ev,train,evidence


def method(**changes):
    fields={'claim_ids':['s'],'query_ids':['t'],'model_hashes':['model'],'observer_hash':'observer',
        'correspondence_hash':'mapper','resources':{'lexicon':'v1'},'criterion':'exact with source-backed bases'}
    return effective_method(**(fields|changes))


def test_R01_R02_original_controls_still_preserve_P1_R1():
    # Exercise the actual unchanged 005 control tests and compare contracts.
    from test_observer_closure005 import (test_P1_dear_all_is_not_some_joy_day_and_neither_direction_entails,
        test_C13_R1_normative_support_does_not_upgrade_operational_claim)
    test_P1_dear_all_is_not_some_joy_day_and_neither_direction_entails()
    test_C13_R1_normative_support_does_not_upgrade_operational_claim()


def test_R03_positive_local_mapping_and_basis_deletion():
    req,ev,_,_=calibration(forward_evidence=True);r=a.assess(req,ev)
    assert r['status']=='SUPPORTS_EXACT_CLAIM' and r['robust_in_registered_family']
    assert r['branches'][0]['source_transport']['satisfiable']
    assert r['branches'][0]['source_transport']['entails']
    basis=ev['definitions'][0]['source_refs'][0]
    cut=a.assess(req,ev,disabled_basis=(basis,))
    assert cut['status']=='UNRESOLVED' and not cut['conditional_support']


def test_R03b_no_basis_signature_or_model_proof_cannot_promote_mapping():
    req,ev,train,evidence=calibration()
    evidence=evidence.model_copy(update={'spans':evidence.spans[:1]});ev=a.observe(evidence)
    r=a.assess(req,ev)
    assert r['status']=='UNRESOLVED' and not r['conditional_support']
    assert r['conditional_source_models']==0
    assert a.assess(req,a.observe(evidence,strategy=a.CONTEXT_STRATEGY))['conditional_source_models']==1
    assert not r['robust_in_registered_family']
    with pytest.raises(ValueError,match='UNREGISTERED_OR_MUTATED'):
        c=deepcopy(r['family']['candidates'][0]);c['basis_kind']='SOURCE_LOCAL_PARSE';a.verify(req,ev,c)


@pytest.mark.parametrize('field,value',[('actor','someone_else'),('recipient','another_recipient'),
    ('direction','BACK_TO_ADDRESSEE'),('domain','different_domain'),('modality','PRESCRIPTION'),
    ('quantifier','SOME'),('time','PAST')])
def test_R04_R05_R09_R10_role_scope_and_direction_are_effective(field,value):
    req,ev,_,_=calibration()
    # A fabricated observed field is rejected against independent raw parsing.
    changed=deepcopy(ev);changed['frames'][0][field]=value
    with pytest.raises(ValueError,match='OBSERVATION_OR_SOURCE'):
        a.assess(req,changed)


def test_R05_actual_actor_mutation_same_words_no_support():
    req,ev,_,_=calibration(recipient_actor='sailor')
    result=a.assess(req,ev)
    assert result['status']=='UNRESOLVED' and not result['conditional_support']
    assert 'PARTICIPANT_BINDING_MISMATCH' in result['obligations']
    assert 'SOURCE_HASH_MISMATCH' not in result['obligations']


def test_R06_negated_response_and_conflict_do_not_explode():
    req,ev,_,_=calibration(negative=True)
    assert a.assess(req,ev)['status']=='REFUTES_EXACT_CLAIM'
    raw=packet_from_text('conflict','Whenever a bell reaches keeper, keeper sends an echo.\nWhenever a bell reaches keeper, keeper sends a reply.\nWhenever a bell reaches keeper, keeper does not send a reply.\nHere, echo means reply.\n').model_dump()
    train=RawPacket.model_validate({**raw,'spans':raw['spans'][:1]});e=RawPacket.model_validate({**raw,'spans':raw['spans'][1:]})
    f=a.observe(train)['frames'][0];request=a.request(f,a.claim_for_frame(f),'t',train);r=a.assess(request,a.observe(e))
    assert r['conflict'] and r['status']=='UNRESOLVED' and not r['conditional_support']


def test_R07_analogy_not_identity_and_inverse_stays_negative():
    p=packet_from_text('analogy','Ты внемлешь грохоту громов,\nИ шлешь ответ;\nТебе ж нет отзыва... Таков\nИ ты, поэт!\n',language='ru')
    frames=a.observe(p)['frames']
    assert any(f['direction']=='BACK_TO_ADDRESSEE' and f['polarity']=='NEGATIVE' for f in frames)
    assert not any('поэт' in f['actor'] for f in frames)


def test_R08_ground_or_other_antecedent_not_universal():
    req,ev,_,_=calibration(clause='When')
    r=a.assess(req,ev)
    assert r['status']=='UNRESOLVED' and not r['conditional_support']
    req2,_,_,_=calibration(stimulus='horn')
    assert not a.assess(req2,ev)['branches']


def test_R11_R20_local_synonym_and_alpha_names_preserve_only_direction():
    for actor,stimulus,response in [('keeper','bell','reply'),('watcher','horn','signal')]:
        req,ev,_,_=calibration(actor,stimulus,response,forward_evidence=True)
        assert a.assess(req,ev)['status']=='SUPPORTS_EXACT_CLAIM'
    req,ev,train,e=calibration()
    # Reverse local definition does not license forward lexical transport.
    raw=packet_from_text('reverse','Whenever a bell reaches keeper, keeper sends an echo.\nWhenever a bell reaches keeper, keeper sends a reply.\nHere, echo means reply.\n').model_dump()
    t=RawPacket.model_validate({**raw,'spans':raw['spans'][:1]});v=RawPacket.model_validate({**raw,'spans':raw['spans'][1:]})
    f=a.observe(t)['frames'][0]
    assert a.assess(a.request(f,a.claim_for_frame(f),'t',t),a.observe(v))['status']=='UNRESOLVED'


def test_R12_R14_empty_truncated_and_selected_family_not_robust():
    req,ev,_,e=calibration();e=e.model_copy(update={'spans':e.spans[:1]});ev=a.observe(e)
    family=a.candidates(req,ev)
    for changed in [{**family,'candidates':[]},{**family,'truncated':True},
                    {**family,'candidates':family['candidates'][:1]}]:
        r=a.assess(req,ev,changed)
        assert not r['robust_in_registered_family'] and r['status']=='UNRESOLVED'


def test_R13_premise_deletion_different_from_alignment_deletion():
    obs=observe(packet_from_text('chain','A implies B.\nB implies C.\n'),strategy='discourse005/1')
    b=enumerate_bindings(obs['dimensions'])['bindings'][0];m=compile_model(obs['premises'],b);q=generate_queries(obs['premises'],m)[0]
    assert all(w['essential'] for w in deletion_witnesses(obs['premises'],b,m,q))
    req,ev,_,_=calibration();basis=ev['definitions'][0]['source_refs'][0]
    assert a.assess(req,ev,disabled_basis=(basis,))['status']=='UNRESOLVED'
    assert evaluate(m,q)['value']  # Source transport changed, mathematical model did not.


def test_R15_R21_actual_query_free_observer_and_registered_modes():
    _,_,_,e=calibration()
    out=asyncio.run(call('alignment',{'packet':e.model_dump(),'strategy':a.STRATEGY}))
    assert out['frames'] and not out['query_received'] and not out['model_proof_received']
    assert out['isolation']['probes']=={'file':'DENIED','socket':'DENIED'}
    with pytest.raises(ValueError,match='WORKER_FAILED'):
        asyncio.run(call('alignment',{'packet':e.model_dump(),'strategy':a.STRATEGY,'q_t':{'expected':True}}))
    with pytest.raises(ValueError,match='UNREGISTERED'):a.observe(e,strategy='eval_python')
    obs=observe(packet_from_text('compile','A implies B.\nB implies C.\n'));b=enumerate_bindings([])['bindings'][0]
    assert compile_model(obs['premises'],b)['compiled_hash']==compile_model(obs['premises'],b)['compiled_hash']


def test_R16_R17_effective_version_and_output_difference(tmp_path):
    journal=Journal(tmp_path/'journal.jsonl');_,_,_,e=calibration();rows=[];m=method()
    v=evidence_use(journal,e,'validation',m['effective_version'],rows)
    assert v['fresh_for_this_prediction']
    # Computing a mapping with fixed code is an output, not method revision.
    req,ev,_,_=calibration();a.assess(req,ev)
    assert method()['effective_version']==m['effective_version']
    changed=method(observer_hash='newobserver')
    record=evidence_use(journal,e,'development',changed['effective_version'],rows,method_changed=True)
    assert not record['fresh_for_this_prediction']
    cert={'effective_version':m['effective_version'],'family_version':'a1'}
    with pytest.raises(ValueError,match='STALE'):require_current_alignment(cert,changed,'a1')
    with pytest.raises(ValueError,match='STALE'):require_current_alignment(cert,m,'a2')
    assert Journal.verify(journal.path)['entries']==2


def test_R18_copy_hash_nonce_signature_and_replay_are_not_unused(tmp_path):
    journal=Journal(tmp_path/'journal.jsonl');_,_,_,e=calibration();rows=[];m=method()
    evidence_use(journal,e,'alignment-acquisition',m['effective_version'],rows)
    copied=deepcopy(e.model_dump());copied['id']='another/path/signed-copy';copied['document_sha256']='d'*64
    for s in copied['spans']:
        s['document_sha256']='d'*64;s['source_address'].update({'nonce':'new','signature':'signed'})
    v=evidence_use(journal,RawPacket.model_validate(copied),'validation',m['effective_version'],rows)
    assert not v['fresh_for_this_prediction'] and v['assessment']=='SOURCE_INTERNAL_RECHECK'
    reads=ObservationReads();reads.read(e,a.STRATEGY,{'kind':'PREDICATE_ALIGNMENT_MISSING'})
    with pytest.raises(ValueError,match='ALREADY_READ'):reads.read(e,a.STRATEGY,{})


def test_R19_real_shape_four_antecedents_are_individual():
    p=packet_from_text('rhetoric','Ревет ли зверь,\nТрубит ли рог, гремит ли гром,\nПоет ли дева —\nНа всякий звук\nСвой отклик\nРодишь ты вдруг.\nТы внемлешь грохоту громов,\nИ шлешь ответ;\n',language='ru').model_dump()
    t=RawPacket.model_validate({**p,'spans':p['spans'][:6]});e=RawPacket.model_validate({**p,'spans':p['spans'][6:]})
    results=[a.assess(a.request(f,a.claim_for_frame(f),'target_'+str(i),t),a.observe(e,strategy=a.CONTEXT_STRATEGY)) for i,f in enumerate(a.observe(t)['frames'])]
    assert len(results)==4
    assert sum(r['conditional_support'] for r in results)==0
    assert sum(r['conditional_source_models']>0 for r in results)==1
    assert not any(r['status']=='SUPPORTS_EXACT_CLAIM' for r in results)


def test_R22_semantic_regression_excludes_only_metrics_not_raw_evidence():
    req,ev,_,_=calibration();left=a.assess(req,ev);right=a.assess(req,ev)
    from artifact_translation.replay import normalized
    assert normalized(left)==normalized(right)
    assert left['branches'][0]['source_transport']['evidence']['metrics']


def test_claim_signature_and_translation_id_cannot_be_substituted():
    req,ev,t,_=calibration();frame=req['source_frame'];claim=a.claim_for_frame(frame)
    with pytest.raises(ValueError,match='SOURCE_CLAIM_FRAME_SIGNATURE'):
        a.request(frame,claim.model_copy(update={'quantifier':'SOME'}),'target',t)
    altered=deepcopy(req);altered['q_s_id']='some_other_claim'
    with pytest.raises(ValueError,match='CLAIM_TRANSLATION_BINDING'):
        a.assess(altered,ev)


def test_volatile_metrics_do_not_randomize_later_provenance(tmp_path):
    from semantic_repair.source import journal_revalidation
    req,ev,_,_=calibration();row={'outcome':a.assess(req,ev)};other=deepcopy(row)
    other['outcome']['branches'][0]['finite_K_V_and_C_a']['evidence']['metrics']['wall_ms']=999
    left=Journal(tmp_path/'left.jsonl');right=Journal(tmp_path/'right.jsonl')
    journal_revalidation(left,row);journal_revalidation(right,other)
    l=left.append('NEXT_EVIDENCE_USE',{'origin':'same-source','role':'source-internal-recheck'})
    r=right.append('NEXT_EVIDENCE_USE',{'origin':'same-source','role':'source-internal-recheck'})
    assert l['entry_hash']==r['entry_hash']
    assert row!=other  # Full raw measurement records remain different/preserved.
    assert Journal.verify(left.path)['ok'] and Journal.verify(right.path)['ok']
