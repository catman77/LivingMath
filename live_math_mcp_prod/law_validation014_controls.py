"""Adversarial binding/stale-permission checks on a disposable active snapshot."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from normalizer import canonical
from native_preview008_qa import readonly_state
from research_store import ResearchStore
from law_validation014_receipt import ReceiptValidator014


def active_controls(database,project,move_id,event_id,directory,unexecuted_snapshot):
    directory.mkdir(parents=True,exist_ok=False);clone=directory/'active.sqlite3'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(clone) as target:source.backup(target)
    clone.chmod(0o600);store=ResearchStore(clone);validator=ReceiptValidator014(clone);checks=[]
    with store._connect() as c:
        original=dict(c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone())
    data=json.loads(original['content'])
    mutations={
        'purpose':lambda e:e.update(purpose='DISCRIMINATE'),
        'law':lambda e:e.update(law_fingerprint='0'*64),
        'context':lambda e:e.update(context_word=[1,0]),
        'order':lambda e:e['suffix_ordinals'].reverse(),
        'observer':lambda e:e['observer'].update(mod=2),
        'source_hash':lambda e:e['source_bindings'][0].update(sha256='0'*64),
        'activation':lambda e:e.update(activation_operation_id=e['activation_operation_id']+1),
        'version':lambda e:e.update(obligation_version=e['obligation_version']+1),
    }
    for name,mutation in mutations.items():
        forged=copy.deepcopy(data);mutation(forged['measurement_binding'])
        event=store.record(project,'qa_source','Fault injection '+name,canonical(forged),'experiment',parent_id=original['parent_id'],request_key='014:fault:'+name)
        before=readonly_state(clone);out=validator.validate(project,move_id,event['id'])
        checks.append({'case':name,'PASS':out['status']=='REJECTED' and out.get('reason')=='MEASUREMENT_BINDING_MISMATCH' and readonly_state(clone)==before,'response':out})
    immutable={}
    for table in ('typed011_journal','typed011_precommits','events','operations'):
        with sqlite3.connect(clone) as c:
            c.execute('BEGIN')
            try:c.execute('DELETE FROM '+table);blocked=False
            except sqlite3.IntegrityError:blocked=True
            finally:c.rollback()
        immutable[table]=blocked
    checks.append({'case':'empty_journal_and_backfill_SQL_blocked','PASS':all(immutable.values()),'evidence':immutable})
    stale_store=ResearchStore(unexecuted_snapshot)
    view=stale_store.moves.inspect(project,move_id);oid=view['active_frontier_id'];version=view['active_frontier_version']
    stale_store.frontier.update(oid,version,{'statement':'Version changed: fresh audit and bound source projection required.'})
    view=stale_store.moves.inspect(project,move_id)
    checks.append({'case':'stale_grant_revoked','PASS':view['status']=='REQUIRES_REVIEW' and not view['execution_permission']['allowed']})
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('law_validation014_executor.py')),'--db',str(unexecuted_snapshot)],
        input=canonical({'project':project,'move_id':move_id,'environment_file':'/nonexistent/must-not-be-opened'}),capture_output=True,text=True,timeout=10)
    checks.append({'case':'executor_checks_stale_before_seal','PASS':result.returncode!=0 and 'STALE_OBLIGATION_VERSION' in result.stdout,'stdout':result.stdout})
    stale_store.moves.transition(project,move_id,'abandon','stale-control-cleanup',reason='Unexecuted stale014 control finished.')
    with store._connect() as c:moves=[dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project LIKE ?',('LM_QA_TYPED011_LV014_%',))]
    for move in moves:
        if store.moves.inspect(move['project'],move['id'])['status'] not in {'COMPLETED','ABANDONED','REJECTED'}:
            store.moves.transition(move['project'],move['id'],'abandon','fault-cleanup:'+str(move['id']),reason='Disposable014 fault snapshot finished.')
    (directory/'result.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    return checks
