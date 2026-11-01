"""F1/F2 controls: result declarations and scoped adverse-evidence review."""
import copy
import json
import sqlite3

import pytest

from test_frontier import store
from test_move_lifecycle import proposal


def allowed(store):
    record=store.frontier.record_move('RH',proposal(store),'propose')
    return store.moves.transition('RH',record['id'],'activate_experiment','activate')


def adverse_request(store, role=None):
    event=store.record('RH','counterexample','QA conflict','Conflicting readings of one source.','counterexample',parent_id=15)
    request=proposal(store)
    request['parent_event_ids'].append(event['id'])
    request['evidence_refs']=['event:'+str(event['id'])]
    if role:
        request['evidence_roles']={str(event['id']):{'role':role,'reason':'Explicit scoped QA disposition.'}}
    return event['id'],request


def review(store,event_id,request,disposition,key='review'):
    return store.evidence_reviews.record(project='RH',event_id=event_id,
        obligation_id=request['active_frontier_id'],expected_version=1,
        proposed_operation=request['proposed_operation'],disposition=disposition,
        reason='QA-only scoped review, not mathematical validation.',evidence_refs=['event:15'],
        request_key=key,operator='local QA operator')


@pytest.mark.parametrize('result',[None,{}, {'outcome':'VERIFIED','summary':'x'}, {'outcome':'SUCCESS','summary':' '}])
def test_complete_rejects_missing_or_invalid_structured_result(store,result):
    record=allowed(store)
    before=store.verify_audit()
    with pytest.raises(ValueError):
        store.moves.transition('RH',record['id'],'complete','missing-result',
            evidence_refs=['event:15'],reason='A reference to the source alone is not an outcome.',result=result)
    assert store.verify_audit()==before


@pytest.mark.parametrize('outcome',['SUCCESS','FAILURE','INCONCLUSIVE','ERROR'])
def test_all_outcomes_are_completed_but_never_verified_and_keys_bind_result(store,outcome):
    record=allowed(store)
    result={'outcome':outcome,'summary':'Finite software test outcome.','data':{'value':0}}
    args=dict(evidence_refs=['event:15'],reason='Protocol outcome recorded.',result=result)
    done=store.moves.transition('RH',record['id'],'complete','done',**args)
    assert done['status']=='COMPLETED' and done['completion']['result']['outcome']==outcome
    assert not done['completion']['legacy'] and done['proof_status']=='unverified'
    assert not done['execution_permission']['allowed']
    before=store.verify_audit()
    assert store.moves.transition('RH',record['id'],'complete','done',**args)['idempotent']
    assert store.verify_audit()==before
    args['result']={**result,'summary':'Changed result under the same request key'}
    with pytest.raises(ValueError):store.moves.transition('RH',record['id'],'complete','done',**args)
    assert store.verify_audit()==before


@pytest.mark.parametrize('refs',[[],['artifact:missing'],['event:99999'],['event:2'],['event:15junk']])
def test_completion_needs_an_existing_project_local_event_reference(store,refs):
    record=allowed(store)
    with pytest.raises(ValueError):
        store.moves.transition('RH',record['id'],'complete','bad-ref',refs,'A test outcome.',
            result={'outcome':'ERROR','summary':'Expected reference rejection.'})


def test_direct_adverse_evidence_requires_review_and_cannot_activate(store):
    event_id,request=adverse_request(store)
    record=store.frontier.record_move('RH',request,'adverse')
    assert record['status']=='REQUIRES_REVIEW'
    finding=next(f for f in record['audit']['findings'] if f['code']=='ADVERSE_EVIDENCE_REQUIRES_REVIEW')
    assert event_id in finding['source_event_ids'] and finding['reason'] and finding['reopen_conditions']
    with pytest.raises(ValueError):store.moves.transition('RH',record['id'],'activate_experiment','deny')


@pytest.mark.parametrize('disposition',['diagnostic_subject','label_error'])
def test_scoped_diagnostic_or_label_review_preserves_source_and_allows_audit(store,disposition):
    event_id,request=adverse_request(store,disposition)
    before=[row for row in store.events('RH',200) if row['id']==event_id][0]
    initial=store.audit('RH','Scope declaration alone is insufficient',**{k:v for k,v in request.items() if k not in {'scope','active_frontier_version'}})
    assert 'ADVERSE_EVIDENCE_REQUIRES_REVIEW' in initial['warnings']
    recorded=review(store,event_id,request,disposition)
    audit_before=store.verify_audit()
    assert review(store,event_id,request,disposition)['id']==recorded['id']
    assert store.verify_audit()==audit_before
    record=store.frontier.record_move('RH',request,'reviewed-proposal')
    assert record['status']=='AUDITED' and record['audit']['verdict']=='EXPERIMENT_ALLOWED'
    assert store.moves.transition('RH',record['id'],'activate_experiment','reviewed-activation')['execution_permission']['allowed']
    assert [row for row in store.events('RH',200) if row['id']==event_id][0]==before
    changed=copy.deepcopy(request)
    changed['proposed_operation']['testable_consequence']='A materially different claim'
    report=store.audit('RH',**{k:v for k,v in changed.items() if k not in {'scope','active_frontier_version'}})
    assert 'ADVERSE_EVIDENCE_REQUIRES_REVIEW' in report['warnings']
    store.frontier.update(request['active_frontier_id'],1,{'status':'TESTING'})
    assert store.moves.audit('RH',record['id'],'new-version')['status']=='REQUIRES_REVIEW'


def test_evidence_reviews_are_project_scoped_and_immutable(store):
    event_id,request=adverse_request(store,'diagnostic_subject')
    review(store,event_id,request,'diagnostic_subject')
    with pytest.raises(ValueError):
        store.evidence_reviews.record(project='OTHER',event_id=event_id,obligation_id=request['active_frontier_id'],
            expected_version=1,proposed_operation=request['proposed_operation'],disposition='diagnostic_subject',
            reason='Cannot borrow another project.',evidence_refs=['event:15'],request_key='other',operator='QA')
    with store._connect() as c:
        for sql in ('DELETE FROM adverse_evidence_reviews','UPDATE adverse_evidence_reviews SET event_id=event_id'):
            with pytest.raises(sqlite3.IntegrityError):c.execute(sql)


def test_schema4_upgrade_preserves_all_rows_and_legacy_completions(store,tmp_path):
    record=allowed(store)
    # This is a historical v0.4.1 completion, copied without modifying the real ledger.
    with store._connect() as c:
        store.moves._append(c,record['id'],'COMPLETED','Old outcome reason',
            decision={'allowed':False,'evidence_refs':['event:15'],'completion_claim':True,'proof_status':'unverified'})
    path=tmp_path/'v041.sqlite3'
    with sqlite3.connect(store.path) as source,sqlite3.connect(path) as target:source.backup(target)
    with sqlite3.connect(path) as c:
        c.execute('DROP TABLE adverse_evidence_reviews')
        c.execute('PRAGMA user_version=4')
        c.row_factory=sqlite3.Row
        names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={name:[dict(r) for r in c.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in names}
    from research_store import ResearchStore
    upgraded=ResearchStore(path)
    with upgraded._connect() as c:
        for name,rows in before.items():assert [dict(r) for r in c.execute('SELECT * FROM '+name+' ORDER BY rowid')]==rows
        assert c.execute('PRAGMA user_version').fetchone()[0]==5
    assert upgraded.moves.inspect('RH',record['id'])['completion']['legacy']
    assert upgraded.verify_audit()['ok']


@pytest.mark.parametrize('outcome',['SUCCESS','FAILURE','INCONCLUSIVE','ERROR'])
def test_v042_completion_schema_and_outcomes_over_authenticated_http(tmp_path,outcome):
    from starlette.testclient import TestClient
    from http_server import create_app
    from test_http import PUBLIC_URL,PASSWORD,register,approve,exchange
    from test_frontier import historical_database,BLUEPRINT
    from research_store import ResearchStore
    historical_database(tmp_path/'research.sqlite3')
    data=ResearchStore(tmp_path/'research.sqlite3')
    data.frontier.import_history(BLUEPRINT,'HTTP regression fixture')
    with TestClient(create_app(PUBLIC_URL,tmp_path,PASSWORD),base_url=PUBLIC_URL) as client:
        registration=register(client)
        code,verifier=approve(client,registration)
        token=exchange(client,registration,code,verifier).json()['access_token']
        headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}
        def call(name,args):
            response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
            assert response.status_code==200
            raw=response.json()['result']
            return raw,None if raw.get('isError') else (raw.get('structuredContent') or json.loads(raw['content'][0]['text']))
        _,record=call('record_research_move',{'project':'RH','move':proposal(data),'request_key':'http-propose'})
        _,permitted=call('transition_research_move',{'project':'RH','move_id':record['id'],'action':'activate_experiment','request_key':'http-activate'})
        assert permitted['execution_permission']['allowed']
        arguments={'project':'RH','move_id':record['id'],'action':'complete','request_key':'http-complete',
                   'reason':'HTTP protocol outcome.','evidence_refs':['event:15']}
        missing,_=call('transition_research_move',arguments)
        assert missing['isError']
        raw,done=call('transition_research_move',{**arguments,'result':{'outcome':outcome,'summary':'Controlled HTTP outcome.'}})
        assert not raw.get('isError') and done['completion']['result']['outcome']==outcome
        assert done['proof_status']=='unverified' and not done['execution_permission']['allowed']


def test_superseded_evidence_disposition_revokes_prior_permission(store):
    event_id,request=adverse_request(store,'diagnostic_subject')
    review(store,event_id,request,'diagnostic_subject')
    record=store.frontier.record_move('RH',request,'first-disposition')
    assert store.moves.transition('RH',record['id'],'activate_experiment','first-grant')['execution_permission']['allowed']
    review(store,event_id,request,'label_error','changed-disposition')
    current=store.moves.inspect('RH',record['id'])
    assert current['status']=='REQUIRES_REVIEW' and not current['execution_permission']['allowed']
    assert store.moves.audit('RH',record['id'],'reaudit-disposition')['status']=='REQUIRES_REVIEW'
