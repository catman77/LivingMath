"""Meaning-family boundaries: finite validity must not certify a source mapping."""
from copy import deepcopy
import pytest
from test_general_interpretation011 import raw
from test_observer_inference013 import annotation013,raw013
from davcore.service import Service
from research_automation.controller import Controller
from semantic_repair.context009 import resolve,packets


def data(tmp_path):
    c=Controller(Service(tmp_path/'dav.sqlite3'));receipt=c.ingest('MEANING_QA',raw013(),'source');ctx=resolve(c.service.store,'MEANING_QA',receipt['source_snapshot']['id']);packet=packets(ctx)[0][0]
    p,r=annotation013(packet);p.update(version='source-relations014/1',readable_model='A0: Two distinct samples. C records equal color, M unequal masses. Eq_color does not imply full identity.',contrasts=[])
    a=p['readings'][0];b=deepcopy(a);b['id']='other';b['relations'][0]['referent']='all properties of the entire sample, conditional hypothesis';p['readings'].append(b)
    evidence=a['relations'][0]['evidence']
    p['contrasts']=[{'id':'c','left_reading':a['id'],'right_reading':b['id'],'dimension':'referent','observable':'Does equal color alone identify all properties of these two samples?','left_prediction':'FALSE','right_prediction':'TRUE','differing_assumption':'The competing reading promotes an observed projection to whole-state identity.','evidence':evidence,'witness_needed':'An independently supported identity criterion covering the other properties.'}]
    r.update(version='source-critic014/1',contrasts=[{'contrast_id':'c','status':'SUBSTANTIVE_SOURCE_DISTINCTION','reason':'Different identity criteria, not different labels; source alone need not decide them.','evidence':evidence}],issues=[])
    return c,ctx,packet,p,r


def test_a0_preserved_and_actual_forecasts_discriminate(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);out=family(packet,p,r)
    assert out['baseline_A0']==p['readable_model']
    assert out['questions'] and out['questions'][0]['predictions'][0]!=out['questions'][0]['predictions'][1]
    assert out['source_grounding']=='SOURCE_GROUNDING_NOT_ESTABLISHED'
    assert not out['source_verified'] and out['execution_permission']=={'allowed':False}


def test_cosmetic_hypothesis_rename_is_not_discovery(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);p['readings'][1]=deepcopy(p['readings'][0]);p['readings'][1]['id']='other'
    out=family(packet,p,r);assert out['status']=='FAIL_NON_DISCRIMINATING_FAMILY'
    assert out['baseline_A0']==p['readable_model']


def test_false_source_reading_finite_pass_never_source_verified(tmp_path):
    from semantic_repair.meaning014 import family
    from test_observer_inference013 import model,profile,value,infer
    finite=infer(model([profile('C',['color'],{'color':value('red')},{'color':value('red')})]))
    assert finite['consequences'][0]['verdict']=='ENTAILED_UNDER_ASSUMPTIONS'
    _,_,packet,p,r=data(tmp_path)
    # Deliberately bogus interpretation, even though a finite model of it passes.
    p['readable_model']='A0 hypothesis wrongly treats equal color as complete physical identity.'
    out=family(packet,p,r)
    assert out['source_grounding']=='SOURCE_GROUNDING_NOT_ESTABLISHED' and not out['source_verified']


def test_foreign_or_nonexact_quote_cannot_adjudicate(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);p['contrasts'][0]['evidence'][0]['quote']='This sentence does not occur in the source.'
    out=family(packet,p,r);assert not out['questions']
    assert any(x['reason']=='NOT_SUPPORTED_QUOTE' for x in out['losses'])


def test_no_selected_query_or_proof_in_source_critic_prompt(tmp_path):
    import json
    from semantic_repair.prompts014 import request
    _,_,packet,p,r=data(tmp_path);v=json.loads(request('critic014',packet,p))
    assert set(v)=={'task','source_window','source_candidates'}
    assert 'selected_question' not in v and 'target_model' not in v


class Provider014:
    from davcore.ast import digest
    fingerprint=digest('meaning014-annotation-not-LLM');assurance='UNIT_ANNOTATIONS_NOT_LLM';model='unit'
    async def infer(self,role,packet,proposals=None,feedback=None):
        p,r=annotation013(packet);p.update(version='source-relations014/1',readable_model='Complete A0: Two samples are compared by color and mass. Eq_color is conditional; mass differs. No full identity is proved.',contrasts=[])
        r.update(version='source-critic014/1',contrasts=[],issues=[])
        return {'status':'OK','output':r if role=='critic014' else p,'usage':None,'request_sha256':'unit-'+role}


def test_meaning_real_controller_restart_a0_report_export_and_isolation(tmp_path):
    import asyncio,json
    from research_automation import artifact
    from test_general_interpretation011 import settle
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Provider014());source=raw013().model_dump();source['interpretation']='meaning014'
        first=c.ingest('MEANING_QA',__import__('research_automation.artifact_contract',fromlist=['ArtifactInput']).ArtifactInput.model_validate(source),'same')
        assert c.ingest('MEANING_QA',__import__('research_automation.artifact_contract',fromlist=['ArtifactInput']).ArtifactInput.model_validate(source),'same')==first
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Provider014());state=await settle(c,'MEANING_QA')
        assert state['status']=='COMPLETED'
        cid=first['case_ids'][0];bs=c.journal.rows(('artifact_baseline_A0',),'MEANING_QA',case_id=cid);assert len(bs)==1
        commits=c.journal.rows(('artifact_interpretation_commit',),'MEANING_QA',case_id=cid);assert bs[0]['id']<commits[0]['id']
        ds=c.journal.rows(('artifact_discriminator',),'MEANING_QA',case_id=cid);assert commits[0]['id']<ds[0]['id']
        report=artifact.report(c,'MEANING_QA',cid);assert report['report_ru'].startswith('# Полная исходная формализация A0')
        assert bs[0]['payload']['readable_model'] in report['report_ru']
        assert state['result']['primary_workflow']=='B_PLUS'
        with pytest.raises(ValueError,match='MISSING_OR_FOREIGN'):artifact.report(c,'OTHER',cid)
        page=artifact.export(c,'MEANING_QA',cid,bs[0]['id']-1,0,1,128000);assert page['fragments'][0]['kind']=='artifact_baseline_A0'
        row=json.loads(page['fragments'][0]['json_ascii']);assert row['entry_hash']==bs[0]['entry_hash']
        assert c.service.store.integrity()['ok']
        with c.service.store.connect() as db:
            with pytest.raises(Exception,match='APPEND_ONLY'):db.execute('UPDATE dav_records SET payload_json=? WHERE id=?',('{}',bs[0]['id']))
    asyncio.run(run())


def test_mapping_error_keeps_readable_a0_instead_of_empty_input_required(tmp_path):
    import asyncio
    from research_automation import artifact
    from test_general_interpretation011 import settle
    from research_automation.artifact_contract import ArtifactInput
    class Bad(Provider014):
        async def infer(self,*args,**kw):return {'status':'ERROR','reason':'INVALID_SOURCE_MAPPING','preserved_readable_A0':'Full readable model survives even though the mapping failed.'}
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Bad());s=raw013().model_dump();s['interpretation']='meaning014'
        first=c.ingest('MEANING_QA',ArtifactInput.model_validate(s),'bad');state=await settle(c,'MEANING_QA')
        assert state['status']=='COMPLETED' and state['result']['outcome']=='READABLE_A0_WITH_UNRESOLVED_SOURCE_MODEL'
        assert 'Full readable model survives' in artifact.report(c,'MEANING_QA',first['case_ids'][0])['report_ru']
    asyncio.run(run())


def test_repair_does_not_inherit_approval_for_changed_source_fields(tmp_path):
    from research_automation.semantic014 import filtered_review
    _,_,packet,p,r=data(tmp_path);q=deepcopy(p);q['readings'][0]['observers'][0]['samples'][0]['time']='invented'
    checked=filtered_review(p,q,r)
    assert not any(x['observer_id']=='C' for x in checked['observations'])
    assert p['readable_model']==q['readable_model']


def test_unknown_forecasts_do_not_turn_into_dav_proofs(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);p['contrasts'][0]['left_prediction']='UNKNOWN'
    product=family(packet,p,r)
    assert product['questions'] and not product['formal_witnesses']


def test_source_premise_withdrawal_never_changes_original_bytes(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);original=deepcopy(packet)
    product=family(packet,p,r);assert product['source_premise_ablations'] and packet==original
    assert all(x['necessity_status']=='NOT_INDEPENDENTLY_ESTABLISHED' for x in product['source_premise_ablations'])


def test_actual_source_list_witness_uses_bytes_not_feature_labels():
    from semantic_repair.meaning014 import source_list_witnesses
    text='Night, street, lamp, pharmacy,\nA plain separate sentence.\nNight, icy ripple,\nPharmacy, street, lamp.\n'
    spans=[];offset=0
    for i,line in enumerate(text.splitlines(keepends=True)):
        v=line.rstrip('\n');spans.append({'id':'s'+str(i),'start':offset,'end':offset+len(v.encode()),'text':v});offset+=len(line.encode())
    ws=source_list_witnesses({'spans':spans});assert len(ws)==1
    w=ws[0];assert w['shared_literal_features']==['lamp','night','pharmacy','street']
    assert w['added_literal_features']==['icy ripple'] and w['sequence_equal'] is False
    assert w['conditional_counterexample']['actual_relation'] is False and not w['source_verified']
    for a in w['left']+w['right']:
        lo,hi=a['byte_ranges'][0];assert text.encode()[lo:hi].decode()==a['quote']


def test_unknown_does_not_invent_record_session(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path)
    p['readings'][0]['observers'][0]['samples'][0]['time']=None
    old=deepcopy(p);family(packet,p,r)
    assert p==old and p['readings'][0]['observers'][0]['samples'][0]['time'] is None


def test_primary_B_checks_function_simulation_without_claiming_event_chronology(tmp_path):
    from semantic_repair.meaning014_reference import finite_models
    _,_,packet,p,r=data(tmp_path)
    h=p['readings'][0]
    for edge in h['relations']:edge.update(kind='TRANSITION',order_kind='UNKNOWN',interpretation_assumptions=['CONDITIONAL_EXECUTABLE_CHANGE'])
    models=finite_models(p)
    assert models[0]['actual_fired_cycles'] and all(x['fired'] for x in models[0]['actual_fired_cycles'][0]['steps'])
    assert not models[0]['source_verified'] and not models[0]['execution_grant']
    for edge in h['relations']:edge['source_claim']['mode']='QUOTED'
    assert not finite_models(p)[0]['actual_fired_cycles']


def test_primary_B_valued_records_and_explicit_negative(tmp_path):
    from semantic_repair.meaning014_reference import observation_checks
    from semantic_repair.inference011 import canonical_packet
    _,_,packet,p,r=data(tmp_path);source=canonical_packet(packet)[0]
    qs=observation_checks(p,source)
    assert any(q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS' for q in qs)
    assert any(q['verdict']=='REFUTED_UNDER_ASSUMPTIONS' for q in qs)
    v=p['readings'][0]['observers'][0]['samples'][0]['values'][0];v['status']='EXPLICIT_NEGATIVE'
    qs=observation_checks(p,source)
    assert any(q['observer']=='C' and q['verdict']=='REFUTED_UNDER_ASSUMPTIONS' for q in qs)


def test_critic_conflict_does_not_automatically_refute_a_source_claim(tmp_path):
    from semantic_repair.meaning014 import family
    _,_,packet,p,r=data(tmp_path);r['assessments'][0]['status']='CONFLICT'
    product=family(packet,p,r)
    assert not any(c['claim_status']=='CONTRADICTED_BY_SOURCE' for c in product['source_claim_ledger'])
    assert any(c.get('review_status')=='CONFLICT' for c in product['source_claim_ledger'])


def test_upstream_wall_bound_is_cost_bound_not_unsupported_source(tmp_path):
    import asyncio
    from research_automation import artifact
    from test_general_interpretation011 import settle
    from research_automation.artifact_contract import ArtifactInput
    class Bound(Provider014):
        async def infer(self,*args,**kwargs):return {'status':'ERROR','reason':'MODEL_CALL_WALL_BOUND','preserved_readable_A0':None}
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Bound());s=raw013().model_dump();s['interpretation']='meaning014'
        receipt=c.ingest('MEANING_QA',ArtifactInput.model_validate(s),'bounded');state=await settle(c,'MEANING_QA')
        assert state['result']['outcome']=='COST_BOUND' and not state['result']['baseline_A0_refs'][0]['available']
        assert 'COST_BOUND' in artifact.report(c,'MEANING_QA',receipt['case_ids'][0])['report_ru']
        assert c.service.store.integrity()['ok']
    asyncio.run(run())
