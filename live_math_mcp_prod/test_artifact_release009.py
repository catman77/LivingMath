"""Changed source/ownership/persistence boundaries, using actual finite workers."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from davcore.service import Service
from davcore.ast import digest
from research_automation.controller import Controller
from research_automation.artifact_contract import ArtifactInput
from research_automation import artifact
from semantic_repair.context009 import resolve,packets
from semantic_repair.compiler import compile_model
from semantic_repair.trace008 import certify,evaluate,questions

ROOT=Path(__file__).resolve().parent.parent/'artifact_release009/frozen'


def inputs():return json.loads((ROOT/'known-cases.json').read_text())


def raw(text='Скажи слово.\n',**changes):
    return ArtifactInput(**({'format':'livingmath-artifact/1','scope':'raw-test','source_name':'unseen',
        'edition':'owner-test','language':'ru','rights':{'basis':'USER_SESSION','origin':'test owner'},'raw_text':text}|changes))


async def settle(c,project,maximum=250):
    for _ in range(maximum):
        v=c.status(project)
        if not v['runnable']:return v['cases'][0]
        await c.tick()
    raise AssertionError(c.status(project))


@pytest.mark.parametrize('name',['R4','P3','P4','R1','R2','R3','P1','P2'])
def test_real_raw_known_cases_use_new_project_and_preserve_scope(tmp_path,name):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'));i=next(x for x in inputs() if x['id']==name)
        receipt=c.ingest('PROJECT_OUTSIDE_QA',ArtifactInput.model_validate(i['input']),'raw')
        case=await settle(c,'PROJECT_OUTSIDE_QA');assert case['status']=='COMPLETED'
        records=[c.service.store.get('PROJECT_OUTSIDE_QA',j)['payload'] for j in case['result']['artifact_result_ids']]
        assert all(r['model']['source_context']['project']=='PROJECT_OUTSIDE_QA' for r in records)
        assert not any(r['check']['source_claim_verified'] for r in records)
        assert case['execution_permission']=={'allowed':False}
        if name=='R4':
            assert len(records)==4
            assert {r['binding']['assignments']['middle_policy'] for r in records}=={'LINK_LOCAL_ROLE','SEPARATE_OCCURRENCES'}
            linked=[r for r in records if r['binding']['assignments']['middle_policy']=='LINK_LOCAL_ROLE']
            assert any(t['all_steps_fired'] for r in linked for t in r['check']['analysis']['traces'])
            assert all(d['changed'] for r in linked for d in r['check']['deletions'])
            assert {r['binding']['assignments']['update_mode'] for r in linked}=={'REPLACE','ACCUMULATE'}
            assert any(s['payload']['result'].get('outcome')=='I_T_ATTENTION_REVISION' for s in c.journal.steps('PROJECT_OUTSIDE_QA',receipt['case_ids'][0]))
        if name=='P4':
            assert case['result']['distinct_target_projections']==1 and len(records)==4
            assert all(t['final_observation']['prescription']=='ATTESTED' and t['final_observation']['performance']=='UNKNOWN' for r in records for t in r['check']['analysis']['traces'])
            assert all(r['check']['analysis']['full_state_count']==256 for r in records)
        if name=='P3':
            obs=[t['final_observation'] for r in records for t in r['check']['analysis']['traces']]
            assert any(o['back_status']=='NEGATIVE' and o['outgoing_any_actor'] for o in obs)
            assert any(o['back_status']=='UNKNOWN' for o in obs)
        if name in {'P1','R3'}:assert case['result']['outcome']=='UNSUPPORTED_ARTIFACT'
        assert c.service.store.integrity()['ok']
    asyncio.run(run())


def test_idempotence_cross_project_context_and_snapshot_pins(tmp_path):
    c=Controller(Service(tmp_path/'dav.sqlite3'));a=raw();r=c.ingest('A',a,'same');n=c.service.store.integrity()['rows']
    assert c.ingest('A',a,'same')==r and c.service.store.integrity()['rows']==n
    with pytest.raises(ValueError,match='CONFLICT'):c.ingest('A',raw('Скажи другое.\n'),'same')
    ref=r['source_snapshot']
    for project,reference in [('B',ref),('A',{**ref,'sha256':'a'*64}),('A',{**ref,'version':2})]:
        with pytest.raises(ValueError):
            c.ingest(project,raw(None,snapshot=reference),'ref-'+project+str(reference['version']))
    context=resolve(c.service.store,'A',ref['id'])
    assert context.public()['project']=='A'
    reused=c.ingest('A',ArtifactInput(format='livingmath-artifact/1',scope='registered-reuse',snapshot=ref),'reuse-without-renewing-rights')
    assert reused['source_snapshot']==ref
    with pytest.raises(ValueError):context.require('B')
    for bad in ['a'*64]:
        with pytest.raises(ValueError,match='SHA256'):c.ingest('A',raw(expected_sha256=bad),'bad-sha')


def test_UTF8_CRLF_and_namespace_boundaries(tmp_path):
    c=Controller(Service(tmp_path/'dav.sqlite3'));a=raw('Скажи слово.\r\n\r\nСлушай голос.\r\n')
    rs=[c.ingest(p,a,'same') for p in ['A','B']]
    cs=[resolve(c.service.store,p,r['source_snapshot']['id']) for p,r in zip(['A','B'],rs)]
    assert cs[0].public()['sha256']==cs[1].public()['sha256'] and cs[0].public()['namespace']!=cs[1].public()['namespace']
    for context in cs:
        ps,_=packets(context);assert len(ps)==2
        data=a.raw_text.encode()
        assert all(data[s['start']:s['end']]==s['text'].encode() for p in ps for s in p['spans'])
    forged=deepcopy(cs[0].record);forged['payload']['raw_text']='substituted'
    from semantic_repair.context009 import from_server_record
    with pytest.raises(ValueError):from_server_record('A',forged)


@pytest.mark.parametrize('field',['query','gold','desired_conclusion','target_graph','path','module','network','premises','server_source_context'])
def test_raw_intake_does_not_accept_target_or_trusted_context(field):
    value=raw().model_dump();value[field]='injected'
    with pytest.raises(ValueError):ArtifactInput.model_validate(value)


def test_atomicity_after_compute_resume_and_fragmented_export(tmp_path,monkeypatch):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'));receipt=c.ingest('A',raw(),'one');case_id=receipt['case_ids'][0]
        original=c.service.store.append;failed=[]
        def fault(project,kind,*args):
            if kind=='artifact_result' and not failed:
                failed.append(True);raise OSError('CONTROLLED_PERSISTENCE_FAULT')
            return original(project,kind,*args)
        monkeypatch.setattr(c.service.store,'append',fault)
        with pytest.raises(OSError,match='CONTROLLED'):
            for _ in range(30):await c.tick()
        assert c.status('A')['cases'][0]['status']!='COMPLETED'
        attempts_before=len(artifact.rows(c,c.journal.case('A',case_id),'artifact_worker_attempt'))
        restored=Controller(Service(tmp_path/'dav.sqlite3'));case=await settle(restored,'A')
        assert case['status']=='COMPLETED'
        rr=restored.journal.rows(('artifact_result',),'A',case_id=case_id)
        assert len(rr)==4 and len({r['payload']['model']['compiled_hash'] for r in rr})==4
        assert attempts_before>=2
        cursor=0;offset=0;assembled={}
        for _ in range(1024):
            page=artifact.export(restored,'A',case_id,cursor,offset,2,4096)
            assert len(json.dumps(page,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())<=4096
            for f in page['fragments']:assembled.setdefault(f['record_id'],[]).append(f['json_ascii'])
            next_cursor,next_offset=page['next_after_record_id'],page['next_byte_offset']
            assert not page['more'] or (next_cursor,next_offset)>(cursor,offset)
            cursor,offset=next_cursor,next_offset
            if not page['more']:break
        else:raise AssertionError('export did not terminate')
        for chunks in assembled.values():
            row=json.loads(''.join(chunks));entry=row.pop('entry_hash');assert digest(row)==entry
        assert any(json.loads(''.join(chunks))['kind']=='artifact_result' for chunks in assembled.values())
        assert any(json.loads(''.join(chunks))['kind']=='automation_artifact_input' for chunks in assembled.values())
        with pytest.raises(ValueError):artifact.export(restored,'B',case_id,0,0,10,4096)
        assert restored.service.store.integrity()['ok']
    asyncio.run(run())


def test_pause_cancel_repeated_events_and_timeout_bound(tmp_path,monkeypatch):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'));r=c.ingest('A',raw('Скажи слово.\nСкажи слово.\n'),'one');ident=r['case_ids'][0]
        c.control('A',ident,'pause','p');assert not await c.tick()
        c.control('A',ident,'resume','r');v=await settle(c,'A');assert v['status']=='COMPLETED'
        results=[c.service.store.get('A',i)['payload'] for i in v['result']['artifact_result_ids']]
        assert all(t['all_steps_fired'] and len(t['steps'])==2 for r in results for t in r['check']['analysis']['traces'])
        c.control('A',ident,'cancel','c')
        with pytest.raises(ValueError,match='TERMINAL'):c.control('A',ident,'resume','no')
        c.ingest('B',raw(budget={'workers':2,'models':2,'source_views':1,'retries':0}),'timeout')
        async def timeout(*args,**kwargs):raise TimeoutError('CONTROLLED_WORKER_TIMEOUT')
        monkeypatch.setattr(artifact,'call',timeout)
        case=await settle(c,'B');assert case['status']=='RESOURCE_EXHAUSTED'
        assert len(c.journal.rows(('artifact_worker_attempt',),'B'))==1
    asyncio.run(run())


def test_source_revision_and_code_binding_make_old_certificates_stale(tmp_path):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'));r=c.ingest('A',raw(),'one');case=await settle(c,'A')
        ids=case['result']['artifact_result_ids'];old=c.service.store.get('A',ids[0]);before=old['entry_hash']
        assert c.service.export('A',ids[0])['certificate_current'] is True
        assert c.service.export('A',r['source_snapshot']['id'])['certificate_current'] is False
        fabricated=deepcopy(old['payload']);fabricated['checker_checkpoint_id']=r['source_snapshot']['id']
        json_only=c.service.store.append('A','artifact_result','owner-only-negative-control',{'fake_checker':True},fabricated)
        assert c.service.export('A',json_only['id'])['certificate_current'] is False
        ctx=resolve(c.service.store,'A',r['source_snapshot']['id']);payload=old['payload'];m=payload['model'];b=payload['binding'];ps=payload['premises']
        q=questions(m)[0];certificate=certify(ps,b,m,q,context=ctx)
        altered=deepcopy(certificate);altered['query']['observer_version']='future'
        with pytest.raises(ValueError):evaluate(ps,b,m,altered,context=ctx)
        foreign=deepcopy(b);foreign['project']='B'
        with pytest.raises(ValueError):compile_model(ps,foreign,profile='typed008/1',context=ctx)
        c.ingest('A',raw('Скажи другое.\n',replaces_snapshot=r['source_snapshot']),'new-version')
        assert not artifact.current_source(c,ctx)
        assert c.service.export('A',ids[0])['certificate_current'] is False
        page=artifact.export(c,'A',case['case_id'],0,0,20,128000)
        assert any(f['kind']=='artifact_result' and f['certificate_current'] is False for f in page['fragments'])
        assert c.service.store.get('A',ids[0])['entry_hash']==before
    asyncio.run(run())


def test_preregistered010_inputs_and_unsupported_are_not_reselected(tmp_path):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'))
        sources=json.loads((ROOT/'product010-selection.json').read_text())['sources']
        for row in sources:
            project='PRODUCT_'+row['id'].replace('-','_')
            c.ingest(project,ArtifactInput.model_validate(row['input']),'first')
            case=await settle(c,project)
            assert case['status']=='COMPLETED'
            if row['id']=='010-U':assert case['result']['outcome']=='UNSUPPORTED_ARTIFACT'
            else:assert case['result']['artifact_result_ids']
    asyncio.run(run())


def test_incomplete_family_and_unsupported_slice_preserve_independent_results(tmp_path):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'))
        c.ingest('BUDGET',raw(budget={'workers':8,'models':1,'source_views':1,'retries':0}),'short')
        case=await settle(c,'BUDGET')
        assert case['result']['outcome']=='PARTIAL_MODEL' and case['result']['checked_family_complete'] is False
        assert any(x['reason']=='INCOMPLETE_CHECKED_FAMILY' for x in case['result']['losses'])
        text='Whenever a bell reaches listener, listener does not send reply.\nWhenever a horn reaches listener, listener sends reply.\n'
        c.ingest('MIXED',raw(text,language='en'),'mixed')
        case=await settle(c,'MIXED')
        assert case['status']=='COMPLETED' and case['result']['outcome']=='PARTIAL_MODEL'
        assert case['result']['artifact_result_ids'] and any('NEGATIVE_FORWARD' in x['reason'] for x in case['result']['losses'])
        assert c.service.store.integrity()['ok']
    asyncio.run(run())


def test_same_source_under_new_policy_rebinds_without_rewriting_old_certificate(tmp_path):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'));r=c.ingest('A',raw(),'first');case=await settle(c,'A')
        before={i:c.service.store.get('A',i)['entry_hash'] for i in case['result']['artifact_result_ids']}
        c2=Controller(Service(tmp_path/'dav.sqlite3'));c2.binding=digest(['a new reviewed implementation',c2.binding])
        exported=artifact.export(c2,'A',r['case_ids'][0],0,0,20,128000)
        assert any(f['kind']=='artifact_result' and f['certificate_current'] is False for f in exported['fragments'])
        after=await settle(c2,'A')
        assert after['generation']>case['generation'] and set(before).isdisjoint(after['result']['artifact_result_ids'])
        assert all(c2.service.store.get('A',i)['entry_hash']==h for i,h in before.items())
    asyncio.run(run())


def test_incomplete_quote_window_reports_loss_and_bounded_source_coverage(tmp_path):
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'))
        text='«Скажи слово.\n'+'И далее,\n'*7+'Скажи снова».\n'
        c.ingest('Q',raw(text),'quote-window');case=await settle(c,'Q')
        assert case['result']['outcome']=='PARTIAL_MODEL'
        assert any(x['reason']=='QUOTE_CROSSES_SOURCE_WINDOW' for x in case['result']['losses'])
        c.ingest('LONG',raw('x\n'*1000,budget={'source_views':1}),'many-lines')
        case=await settle(c,'LONG')
        coverage=case['result']['coverage']
        assert coverage['unsupported_ref_count']==1000 and coverage['unsupported_refs_truncated']
        assert len(coverage['unsupported_or_unparsed_refs'])==256 and coverage['unsupported_byte_ranges']
    asyncio.run(run())


def test_production_callable_does_not_import_study_or_qa_fixtures():
    import ast
    root=Path(__file__).resolve().parent
    forbidden={'study008','experiment','test_artifact_release009','pytest','bundle','replay'}
    files=[root/'research_automation/artifact.py',root/'semantic_repair/runtime009.py',root/'semantic_repair/check009.py']
    for path in files:
        tree=ast.parse(path.read_text())
        imports=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module]
        assert not any(forbidden.intersection(module.split('.')) for module in imports)
