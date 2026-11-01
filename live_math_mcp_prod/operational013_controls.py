"""Post-stop diagnostic boundary checks; cannot promote the stopped typed gate."""
import asyncio
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical,digest
from normalization_regression import Tap
from qa_positive_acceptance import write_json,snapshot
from native_preview008_qa import readonly_state
from typed_cycle011_store import connect
from typed_cycle011_operator import activate,commit
from research_store import ResearchStore
from operational013_cycle_qa import Acceptance,SOURCE
from operational013_store import install_append_only


async def run(base):
    metadata=json.loads((base/'typed-current.json').read_text());old=Path(metadata['attempt'])
    suffix=datetime.now(timezone.utc).strftime('%H%M%S%f')
    output=old.parent/('post-stop-controls-'+suffix);output.mkdir(exist_ok=False)
    db=base/('post-stop-controls-'+suffix+'.sqlite3')
    with sqlite3.connect(Path(metadata['database']).as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(db) as dst:src.backup(dst)
    db.chmod(0o600);before=snapshot(db)
    install_append_only(db)
    runner=Acceptance.__new__(Acceptance);runner.base=base;runner.p0=old.parent;runner.out=output;runner.db=db
    runner.checks=[];runner.trace=[];runner.cycles=[];runner.scopes=[]
    with connect(db) as c:
        projects=[r[0] for r in c.execute('SELECT project FROM typed011_scopes ORDER BY project')]
        scopes={p:json.loads(c.execute('SELECT payload_json FROM typed011_scopes WHERE project=?',(p,)).fetchone()[0]) for p in projects}
        bindings=[]
        for p in projects:
            root=[dict(r) for r in c.execute('SELECT * FROM events WHERE project=?',(p,)) if 'source_spec' in json.loads(r['content'])][0]
            spec=json.loads(root['content'])['source_spec']
            oid=c.execute('SELECT id FROM research_obligations WHERE project=?',(p,)).fetchone()[0]
            bindings.append({'project':p,'scope':spec['scope'],'obligation_id':oid,'version':1,'root_id':root['id'],
                'left':int(spec['histories'][0].split(':')[1]),'right':int(spec['histories'][1].split(':')[1])})
    a=next(b for b in bindings if b['project'].endswith('_A_main'))
    b=runner.seed('B','diagnostic')
    bindings.append(b)
    stale=next(b for b in bindings if b['project'].endswith('_A_stale'))
    params=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'operational013_cycle_server.py'),'--db',str(db)],
        env={**os.environ,'LM013_COST_LEDGER':str(output/'native-costs.jsonl')})
    with (output/'server-stderr.txt').open('w') as errors:
        async with stdio_client(params,errlog=errors) as (read,write):
            async with ClientSession(Tap(read,output/'mcp-wire.jsonl','response'),Tap(write,output/'mcp-wire.jsonl','request')) as client:
                await client.initialize()
                # Reproduce the exact substantive stop; do not replace it with a passing scenario.
                preview=await runner.call(client,'operational_cycle_preview',{'request':runner.request(a)},True)
                runner.check('reproduced_missing_second_informative_test',preview['status']=='NO_INFORMATIVE_TEST' and not preview['execution_permission']['allowed'])
                active=[h for h in preview['attention']['hypotheses'] if h['question']=='current' and h['predictive']]
                runner.check('exact_singleton_after_first_measurement',len(active)==1,active)
                runner.check('independent_branch_survives_negative_feedback',all(h['status']=='ACTIVE' for h in preview['independent_branch']))
                store=ResearchStore(db)
                for label,change in [('observer',lambda req:req.update(observer={'projection':'primary','mod':2})),
                    ('version',lambda req:req.update(active_frontier_version=2)),
                    ('C4',lambda req:req['question'].update(context_level='C4')),
                    ('foreign_root',lambda req:req['question'].update(root_event_id=b['root_id'])),
                    ('foreign_history',lambda req:req['question'].update(left_history_id=b['left'])),
                    ('foreign_feedback',lambda req:req['question'].update(feedback_event_id=b['left'])),
                    ('foreign_source',lambda req:req['source_bindings'][0].update(event_id=b['root_id']))]:
                    req=runner.request(a);change(req)
                    denied=await runner.call(client,'operational_cycle_preview',{'request':req},True)
                    runner.check(label+':denied_without_grant',denied['status']=='INSUFFICIENT_CONTEXT' and not denied['execution_permission']['allowed'],denied)
                # A fresh B measurement remains diagnostic only; it does not repair A's stop.
                req=runner.request(b);preview=await runner.call(client,'operational_cycle_preview',{'request':req},True)
                runner.check('B_source_preview',preview['status']=='NEW_DISTINCTION')
                pc=await runner.call(client,'operational_cycle_precommit',{'request':req,'request_key':'diagnostic-B'})
                act=runner.local('activate',{'project':b['project'],'move_id':pc['move_id'],'request_key':'diagnostic-B'})
                environment=base/(b['project']+'-environment.json')
                executed=subprocess.run([sys.executable,str(SOURCE/'operational013_executor.py'),'--db',str(db)],input=canonical(
                    {'project':b['project'],'move_id':pc['move_id'],'environment_file':str(environment)}),text=True,capture_output=True,timeout=12)
                measured=json.loads(executed.stdout)['result'];env=measured['envelope']
                runner.trace.append({'authority':'external-native013-process','response':json.loads(executed.stdout)})
                shutil.copy2(measured['artifact_path'],output/'B-measurement.json')
                valid=await runner.call(client,'operational_cycle_validate',{'project':b['project'],'move_id':pc['move_id'],'event_id':measured['event_id']},True)
                runner.check('B_fresh_binding',valid['status']=='VALID_BOUND_MEASUREMENT')
                with connect(db) as c:
                    foreign=c.execute('SELECT event_id FROM typed011_receipts WHERE project=?',(a['project'],)).fetchone()[0]
                denied=await runner.call(client,'operational_cycle_validate',{'project':b['project'],'move_id':pc['move_id'],'event_id':foreign},True)
                runner.check('foreign_measurement_refused',denied['status']=='REJECTED')
                receipt=runner.local('commit',{'project':b['project'],'move_id':pc['move_id'],'event_id':measured['event_id'],'request_key':'diagnostic-B',
                    **{k:env[k] for k in ('outcome','observed','summary','reason','proof_status')}})
                runner.check('B_completion_unverified',receipt['proof_status']=='unverified' and not receipt['execution_permission']['allowed'])
                # Stale-version grant rejection must precede ANY environment file access.
                req=runner.request(stale);pc=await runner.call(client,'operational_cycle_precommit',{'request':req,'request_key':'diagnostic-stale'})
                runner.local('activate',{'project':stale['project'],'move_id':pc['move_id'],'request_key':'diagnostic-stale'})
                store.frontier.update(stale['obligation_id'],1,{'statement':'New version requires re-audit of source applicability.'})
                view=store.moves.inspect(stale['project'],pc['move_id'])
                runner.check('version_revokes_grant',view['status']=='REQUIRES_REVIEW' and not view['execution_permission']['allowed'])
                before_denial=readonly_state(db)
                execution=subprocess.run([sys.executable,str(SOURCE/'operational013_executor.py'),'--db',str(db)],input=canonical(
                    {'project':stale['project'],'move_id':pc['move_id'],'environment_file':'/nonexistent/not-opened'}),text=True,capture_output=True,timeout=12)
                runner.check('stale_executor_before_environment',execution.returncode!=0 and 'STALE_OBLIGATION_VERSION' in execution.stdout,execution.stdout)
                runner.check('stale_executor_no_DB_delta',before_denial==readonly_state(db))
                store.moves.transition(stale['project'],pc['move_id'],'abandon','controls-abandon',reason='Stale diagnostic canary abandoned.')
    # Close all new QA scopes, preserving every version, audit, event and decision.
    for binding in bindings:
        store=ResearchStore(db);version=2 if binding is stale else 1
        store.frontier.update(binding['obligation_id'],version,{'status':'RESOLVED','closure_reason':'Diagnostic QA finished; 013 full gate remains stopped.',
            'reopen_conditions':['A new independently frozen cohort and explicit operator review are required.']})
    with connect(db) as c:
        reader=ResearchStore.__new__(ResearchStore);reader.path=db
        moves=[dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project LIKE ?',('LM_QA_TYPED011_OP013_%',))]
        runner.check('zero_active_QA_grants',not any(reader.moves._view(c,m)['execution_permission']['allowed'] for m in moves))
        histories=[dict(r) for r in c.execute('SELECT h.* FROM research_move_status_history h JOIN research_moves m ON m.id=h.move_id WHERE m.project LIKE ? ORDER BY h.id',('LM_QA_TYPED011_OP013_%',))]
        runner.check('all_terminal_results_unverified',all(not r['decision_json'].find('"proof_status":"verified"')>=0 for r in histories))
        journals=[dict(r) for r in c.execute('SELECT * FROM typed011_journal')]
    write_json(output/'status-history.json',histories);write_json(output/'novelty-journal.json',journals)
    after=snapshot(db);preserved={t:after['tables'][t][:len(rows)]==rows for t,rows in before['tables'].items()}
    # Existing obligation heads are projections and legitimately advance; immutable versions/prefixes must remain.
    preserved.pop('research_obligations',None)
    runner.check('immutable_original_rows_preserved',all(preserved.values()),preserved)
    write_json(output/'mcp-transcript.json',runner.trace)
    write_json(output/'result.json',{'status':'PASS_DIAGNOSTIC_CONTROLS','does_not_repair_typed_stop':True,'checks':runner.checks})
    write_json(output/'metadata.json',{'database':str(db),'source_attempt':str(old)})
    write_json(base/'controls-current.json',{'output':str(output),'database':str(db)})
    print(canonical({'output':str(output),'checks':len(runner.checks),'scientific_status':'FULL_GATE_STILL_STOPPED'}))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path);args=parser.parse_args()
    asyncio.run(run(args.baseline or Path(Path('/tmp/lm013_path').read_text().strip())))
