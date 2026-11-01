"""Automatic product lifecycle: no caller advancing individual research stages."""
import asyncio

import pytest

from davcore.adapters import AdapterSpec
from davcore.service import Service
from research_automation.contract import ResearchInput, Problem, Fact, Hypothesis, Prediction
from research_automation.controller import Controller


def controller(tmp_path):
    s=Service(tmp_path/'dav.sqlite3')
    return Controller(s),s


async def settle(c,project,cycles=100):
    for _ in range(cycles):
        changed=await c.tick()
        view=c.status(project)
        if not changed and not view['runnable']:
            return view
    raise AssertionError(c.status(project))


def test_adapter_registration_automatically_repairs_observer(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        r=await s.register('QA',AdapterSpec(kind='gate6',mask=1),'register')
        view=await settle(c,'QA')
        assert len(view['cases'])==1
        case=view['cases'][0]
        assert case['status']=='COMPLETED' and case['result']['outcome']=='FORMAL_REPRESENTATION_REPAIRED'
        assert case['result']['observer_mask']==3 and case['result']['base_registration_id']==r['id']
        assert [x['status'] for x in case['history']][:6]==['QUEUED','DIAGNOSING','PROPOSING','AUDITING','EXPERIMENTING','CHECKING']
        assert case['proof_status']=='unverified' and case['execution_permission']=={'allowed':False}
        assert s.store.integrity()['ok']
    asyncio.run(run())


def test_restart_resumes_and_does_not_duplicate_steps(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('QA',AdapterSpec(kind='gate6',mask=1),'r')
        await c.tick()
        before=c.status('QA')['cases'][0]
        c2=Controller(Service(tmp_path/'dav.sqlite3'))
        final=await settle(c2,'QA')
        assert final['cases'][0]['case_id']==before['case_id']
        assert final['cases'][0]['status']=='COMPLETED'
        rows=c2.service.store.integrity()['rows']
        for _ in range(3):await c2.tick()
        assert c2.service.store.integrity()['rows']==rows
    asyncio.run(run())


def test_input_waiting_automatically_wakes_on_new_source(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        problem=Problem(kind='identify_model',scope='sample',hypotheses=[
            Hypothesis(model_id='A',target='alpha',predictions=[Prediction(feature='color',value='red')]),
            Hypothesis(model_id='B',target='beta',predictions=[Prediction(feature='color',value='blue')])])
        c.ingest('QA',ResearchInput(scope='sample',problems=[problem]),'first')
        waiting=await settle(c,'QA')
        case=waiting['cases'][0]
        assert case['status']=='WAITING_FOR_INPUT' and case['result']['required_features']==['color']
        n=s.store.integrity()['rows']
        for _ in range(3):await c.tick()
        assert s.store.integrity()['rows']==n
        c.ingest('QA',ResearchInput(scope='sample',facts=[Fact(feature='color',value='red')]),'new-data')
        final=await settle(c,'QA')
        assert final['cases'][0]['status']=='COMPLETED'
        assert final['cases'][0]['result']['surviving_models']==['A']
        assert final['cases'][0]['result']['outcome']=='MODEL_IDENTIFIED_UNDER_DECLARED_INPUTS'
        assert any(h['generation']==2 for h in final['cases'][0]['history'])
    asyncio.run(run())


def test_completed_input_case_reopens_on_conflicting_evidence(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        p=Problem(kind='input_gap',scope='material',required_features=['composition'])
        c.ingest('A',ResearchInput(scope='material',problems=[p],facts=[Fact(feature='composition',value='X')]),'v1')
        assert (await settle(c,'A'))['cases'][0]['status']=='COMPLETED'
        c.ingest('A',ResearchInput(scope='material',facts=[Fact(feature='composition',value='Y')]),'v2')
        v=await settle(c,'A')
        assert v['cases'][0]['status']=='REQUIRES_REVIEW'
        assert v['cases'][0]['result']['outcome']=='CONTRADICTORY_REFERENCED_INPUTS'
        assert any(h['status']=='COMPLETED' for h in v['cases'][0]['history'])
        assert s.store.integrity()['ok']
    asyncio.run(run())


def test_input_and_case_request_keys_are_structurally_idempotent(tmp_path):
    c,s=controller(tmp_path)
    p=Problem(kind='input_gap',scope='S',title='first name',required_features=['Q'])
    a=ResearchInput(scope='S',problems=[p])
    one=c.ingest('A',a,'same')
    assert c.ingest('A',a,'same')==one
    changed=ResearchInput(scope='S',problems=[p.model_copy(update={'title':'cosmetic rename'})])
    second=c.ingest('A',changed,'different')
    assert second['case_ids']==one['case_ids']
    with pytest.raises(ValueError,match='CONFLICT'):c.ingest('A',changed,'same')
    with pytest.raises(ValueError,match='FOREIGN'):c.journal.case('B',one['case_ids'][0])
    assert s.store.integrity()['ok']


def test_generic_ca_refinement_has_no_ripley_branch(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('CA',AdapterSpec(kind='ca',width=3,mask=1),'r')
        v=await settle(c,'CA',cycles=150)
        assert len(v['cases'])==1 and v['cases'][0]['status']=='COMPLETED'
        assert v['cases'][0]['result']['observer_mask']==7
        assert v['cases'][0]['result']['counterexamples_preserved']>0
    asyncio.run(run())


def test_fair_scheduling_does_not_spin_waiting_tasks(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        for name in ['wait1','wait2']:
            c.ingest('QA',ResearchInput(scope=name,problems=[Problem(kind='input_gap',scope=name,required_features=['Q'])]),name)
        await s.register('QA',AdapterSpec(kind='gate6',mask=1),'r')
        v=await settle(c,'QA')
        assert sorted(x['status'] for x in v['cases'])==['COMPLETED','WAITING_FOR_INPUT','WAITING_FOR_INPUT']
        n=s.store.integrity()['rows']
        for _ in range(5):assert not await c.tick()
        assert s.store.integrity()['rows']==n
    asyncio.run(run())


def test_independent_checker_rejects_loss_and_assumption_change():
    from research_automation.checker import check_refinement
    from davcore.adapters import Adapter
    from davcore.models import Budget
    base=Adapter(AdapterSpec(kind='gate6',mask=1))
    assert check_refinement(base,Adapter(AdapterSpec(kind='gate6',mask=0)),Budget())['status']=='rejected'
    assert check_refinement(base,Adapter(AdapterSpec(kind='gate6',mask=3,assumption='P_implies_Q_NOT_SOURCE_ATTESTED')),Budget())['status']=='rejected'
    assert check_refinement(base,Adapter(AdapterSpec(kind='gate6',mask=1)),Budget())['status']=='rejected'
    assert check_refinement(base,Adapter(AdapterSpec(kind='gate6',mask=3)),Budget())['status']=='accepted'


def test_nulls_and_bool_are_not_silent_measurement_substitutions(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        p=Problem(kind='input_gap',scope='null',required_features=['Q'])
        c.ingest('A',ResearchInput(scope='null',problems=[p],facts=[Fact(feature='Q',value=None)]),'n')
        assert (await settle(c,'A'))['cases'][0]['status']=='WAITING_FOR_INPUT'
        c.ingest('A',ResearchInput(scope='null',facts=[Fact(feature='Q',value=False)]),'false')
        assert (await settle(c,'A'))['cases'][0]['status']=='COMPLETED'
        c.ingest('A',ResearchInput(scope='null',facts=[Fact(feature='Q',value=0)]),'zero')
        assert (await settle(c,'A'))['cases'][0]['status']=='REQUIRES_REVIEW'
    asyncio.run(run())


def test_new_source_in_other_scope_or_project_does_not_wake_case(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        c.ingest('A',ResearchInput(scope='S',problems=[Problem(kind='input_gap',scope='S',required_features=['Q'])]),'p')
        first=await settle(c,'A');seq=first['cases'][0]['history'][-1]['sequence']
        c.ingest('B',ResearchInput(scope='S',facts=[Fact(feature='Q',value=1)]),'foreign')
        c.ingest('A',ResearchInput(scope='S',facts=[Fact(feature='irrelevant',value=1)]),'irrelevant')
        assert not await c.tick()
        assert c.status('A')['cases'][0]['history'][-1]['sequence']==seq
    asyncio.run(run())


def test_pause_resume_and_cancel_are_not_manual_stage_advancement(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        case=c.status('A')['cases'][0]['case_id']
        c.control('A',case,'pause','pause')
        assert not await c.tick() and c.status('A')['cases'][0]['status']=='PAUSED'
        c.control('A',case,'resume','resume')
        assert (await settle(c,'A'))['cases'][0]['status']=='COMPLETED'
        c.control('A',case,'cancel','cancel')
        assert not await c.tick() and c.status('A')['cases'][0]['status']=='CANCELLED'
    asyncio.run(run())


def test_two_coordinators_use_a_single_process_lock(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        c2=Controller(Service(tmp_path/'dav.sqlite3'))
        with c.journal.leader() as locked:
            assert locked and not await c2.tick()
        assert (await settle(c2,'A'))['cases'][0]['status']=='COMPLETED'
    asyncio.run(run())


def test_canonical_source_feed_is_read_only_and_automatic(tmp_path):
    from research_store import ResearchStore
    from research_automation.intake import Intake
    from davcore.ast import canonical
    async def run():
        c,s=controller(tmp_path)
        ledger=ResearchStore(tmp_path/'research.sqlite3');c.canonical=ledger.path
        p=ResearchInput(scope='S',problems=[Problem(kind='input_gap',scope='S',required_features=['Q'])])
        ledger.record('A','source','new input',canonical({'automation':p.model_dump()}))
        import hashlib
        before=hashlib.sha256(ledger.path.read_bytes()).hexdigest()
        intake=Intake(c);intake.poll()
        assert (await settle(c,'A'))['cases'][0]['status']=='WAITING_FOR_INPUT'
        assert hashlib.sha256(ledger.path.read_bytes()).hexdigest()==before
        f=ResearchInput(scope='S',facts=[Fact(feature='Q',value='declared')])
        ledger.record('A','source','followup',canonical({'automation':f.model_dump()}))
        intake.poll()
        assert (await settle(c,'A'))['cases'][0]['status']=='COMPLETED'
    asyncio.run(run())


def test_persisted_refutation_automatically_becomes_a_research_case(tmp_path):
    from davcore.ast import implication
    async def run():
        c,s=controller(tmp_path)
        r=await s.register('A',AdapterSpec(kind='gate6'),'r')
        result=await s.compute('A',r['id'],'check',formula=implication('P','One','Joint','One'),
            persist=True,request_key='original',expected_binding=r['payload']['binding'])
        assert result['payload']['status']=='refuted'
        v=await settle(c,'A')
        assert v['cases'][0]['status']=='COMPLETED' and v['cases'][0]['result']['outcome']=='LAW_REFUTED'
        assert v['cases'][0]['result']['counterexample']['state']==1
    asyncio.run(run())


def test_resource_retries_are_automatic_bounded_and_not_a_busy_loop(tmp_path,monkeypatch):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        count=0
        async def exhausted(req):
            nonlocal count
            count+=1
            return {'status':'timeout','reason':'QA_RESOURCE_EXHAUSTION'}
        monkeypatch.setattr(s.boundary,'run',exhausted)
        clock=[1000000.0]
        monkeypatch.setattr('research_automation.controller.time.time',lambda:clock[0])
        for _ in range(100):
            await c.tick()
            clock[0]+=100
            if c.status('A')['cases'][0]['status']=='RESOURCE_EXHAUSTED':break
        assert c.status('A')['cases'][0]['status']=='RESOURCE_EXHAUSTED' and count==4
        rows=s.store.integrity()['rows']
        for _ in range(3):assert not await c.tick()
        assert s.store.integrity()['rows']==rows
    asyncio.run(run())


def test_source_policy_change_revalidates_without_rewriting_history(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        original=(await settle(c,'A'))['cases'][0]
        before=c.journal.steps('A',original['case_id'])
        c2=Controller(Service(tmp_path/'dav.sqlite3'));c2.binding='new-reviewed-policy'
        final=(await settle(c2,'A'))['cases'][0]
        assert final['generation']==2 and final['status']=='COMPLETED'
        assert c2.journal.steps('A',original['case_id'])[:len(before)]==before
    asyncio.run(run())


def test_pause_during_a_probe_fences_publication(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        while c.status('A')['cases'][0]['status']!='EXPERIMENTING':await c.tick()
        ident=c.status('A')['cases'][0]['case_id']
        original=s.boundary.run;entered=asyncio.Event();release=asyncio.Event()
        async def pending(req):
            entered.set();await release.wait();return await original(req)
        s.boundary.run=pending
        task=asyncio.create_task(c.tick());await entered.wait()
        c.control('A',ident,'pause','p');release.set();await task
        steps=c.journal.steps('A',ident)
        assert steps[-1]['payload']['status']=='EXPERIMENTING'
        assert c.status('A')['cases'][0]['status']=='PAUSED'
        s.boundary.run=original;c.control('A',ident,'resume','r')
        assert (await settle(c,'A'))['cases'][0]['status']=='COMPLETED'
    asyncio.run(run())


def test_solver_absence_uses_an_independent_finite_checker(tmp_path,monkeypatch):
    from davcore.ast import implication
    async def run():
        c,s=controller(tmp_path)
        r=await s.register('A',AdapterSpec(kind='gate6'),'r')
        await s.compute('A',r['id'],'check',formula=implication('P','One','Joint','One'),persist=True,
            request_key='original',expected_binding=r['payload']['binding'])
        original=s.boundary.run
        async def without_solver(req):
            return {'status':'unknown','reason':'OPTIONAL_Z3_UNAVAILABLE'} if req.get('backend')=='smt' else await original(req)
        monkeypatch.setattr(s.boundary,'run',without_solver)
        result=(await settle(c,'A'))['cases'][0]
        assert result['status']=='COMPLETED' and result['result']['outcome']=='LAW_REFUTED'
        assert result['result']['independent_finite_fallback_evidence_id']
    asyncio.run(run())


def test_bad_planner_cannot_accept_a_noncongruent_observer(tmp_path,monkeypatch):
    async def run():
        c,s=controller(tmp_path)
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'r')
        original=s.boundary.run
        async def lying_audit(req):
            if req['action']=='audit':return {'status':'proved','congruent':True}
            return await original(req)
        monkeypatch.setattr(s.boundary,'run',lying_audit)
        case=(await settle(c,'A'))['cases'][0]
        assert case['status']=='REQUIRES_REVIEW'
        assert case['result']['outcome']=='INDEPENDENT_CHECK_REJECTED'
        assert case['execution_permission']=={'allowed':False}
    asyncio.run(run())


def test_local_inbox_deduplicates_and_rejects_duplicate_json_keys(tmp_path):
    import json
    from research_automation.intake import Intake
    c,s=controller(tmp_path);inbox=tmp_path/'inbox';inbox.mkdir();c.inbox=inbox
    packet=ResearchInput(scope='S',problems=[Problem(kind='input_gap',scope='S',required_features=['Q'])])
    (inbox/'ok.json').write_text(json.dumps({'project':'A','input':packet.model_dump()}))
    intake=Intake(c);intake.poll();count=s.store.integrity()['rows'];intake.poll()
    assert s.store.integrity()['rows']==count
    with pytest.raises(ValueError,match='DUPLICATE'):
        intake.decode('{"input":1,"input":2}')
    (inbox/'symlink.json').symlink_to(tmp_path/'dav.sqlite3')
    intake.poll();assert s.store.integrity()['rows']==count


def test_undefined_model_targets_are_explicit_and_can_arrive_as_source_definitions(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        p=Problem(kind='identify_model',scope='S',hypotheses=[Hypothesis(model_id='A'),Hypothesis(model_id='B')])
        c.ingest('A',ResearchInput(scope='S',problems=[p]),'p')
        assert (await settle(c,'A'))['cases'][0]['result']['outcome']=='MODEL_TARGETS_UNDEFINED'
        c.ingest('A',ResearchInput(scope='S',facts=[Fact(feature='model_target/A',value='same'),Fact(feature='model_target/B',value='same')]),'definitions')
        case=(await settle(c,'A'))['cases'][0]
        assert case['status']=='COMPLETED' and case['result']['multiple_models_can_remain']
        assert case['result']['external_claim_verified'] is False
    asyncio.run(run())


def test_foreign_canonical_event_cannot_be_a_source_reference(tmp_path):
    from research_store import ResearchStore
    c,s=controller(tmp_path);ledger=ResearchStore(tmp_path/'canonical.sqlite3');c.canonical=ledger.path
    event=ledger.record('Foreign','observation','x','y')
    p=Problem(kind='input_gap',scope='S',required_features=['Q'],source_refs=['event:'+str(event['id'])])
    before=s.store.integrity()['rows']
    with pytest.raises(ValueError,match='FOREIGN'):
        c.ingest('A',ResearchInput(scope='S',problems=[p]),'foreign')
    assert s.store.integrity()['rows']==before


def test_legacy_MCP_schemas_stay_unchanged_in_automatic_profile(tmp_path,monkeypatch):
    from mcp_server import create_server
    from research_store import ResearchStore
    monkeypatch.setenv('LIVE_MATH_DAV','1');monkeypatch.setenv('LIVE_MATH_DAV_DB',str(tmp_path/'dav.sqlite3'))
    monkeypatch.delenv('LIVE_MATH_AUTORESEARCH',raising=False)
    ledger=ResearchStore(tmp_path/'research.sqlite3');old=create_server(ledger)
    monkeypatch.setenv('LIVE_MATH_AUTORESEARCH','1');new=create_server(ledger)
    assert len(old._tool_manager.list_tools())==26 and len(new._tool_manager.list_tools())==30
    for tool in old._tool_manager.list_tools():
        assert new._tool_manager.get_tool(tool.name).parameters==tool.parameters
    assert new._tool_manager.get_tool('research_autonomy_ingest').parameters['additionalProperties'] is False


def test_inbox_poll_rotates_beyond_first_128_files(tmp_path):
    import json
    from research_automation.intake import Intake
    c,s=controller(tmp_path);inbox=tmp_path/'inbox';inbox.mkdir();c.inbox=inbox
    for i in range(130):
        p=ResearchInput(scope='S',facts=[Fact(feature='Q',value=i)])
        (inbox/(str(i).zfill(3)+'.json')).write_text(json.dumps({'project':'A','input':p.model_dump()}))
    intake=Intake(c);intake.poll();intake.poll()
    assert len(c.journal.rows(('automation_input',),'A'))==130


def test_repaired_representation_does_not_create_endless_self_jobs(tmp_path):
    async def run():
        c,s=controller(tmp_path)
        # A client-controlled prefix must not let a real source masquerade as an internal result.
        await s.register('A',AdapterSpec(kind='gate6',mask=1),'auto-work:client-key')
        await settle(c,'A')
        c2=Controller(Service(tmp_path/'dav.sqlite3'))
        for _ in range(10):assert not await c2.tick()
        assert len(c2.status('A')['cases'])==1
    asyncio.run(run())
