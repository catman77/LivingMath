"""Independent storage gate against a fresh private production Backup-API copy."""
import json
from pathlib import Path
import sqlite3
from normalizer import digest
from research_store import ResearchStore
from native_preview008_qa import readonly_state
from qa_positive_acceptance import snapshot,write_json
from typed_cycle011_store import install as install011
from law_validation014_store import install,SQL


def probe(database):
    before=readonly_state(database);results=[]
    for table in ('events','operations'):
        with sqlite3.connect(database) as c:
            first=c.execute('SELECT rowid FROM '+table+' LIMIT 1').fetchone()
            for operation in ('UPDATE','DELETE'):
                c.execute('BEGIN')
                command=('UPDATE '+table+' SET id=id WHERE rowid=?') if operation=='UPDATE' else ('DELETE FROM '+table+' WHERE rowid=?')
                try:c.execute(command,first);blocked=False;reason=None
                except sqlite3.IntegrityError as error:blocked=True;reason=str(error)
                finally:c.rollback()
                results.append({'table':table,'operation':operation,'blocked':blocked,'reason':reason,
                    'rollback':True,'foreign_keys':c.execute('PRAGMA foreign_keys').fetchone()[0]})
    return {'checks':results,'no_DB_delta':readonly_state(database)==before}


def run(base):
    config=json.loads((base/'metadata.json').read_text());database=base/'storage-security.sqlite3'
    with sqlite3.connect((base/'canonical.sqlite3').as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(database) as target:source.backup(target)
    database.chmod(0o600);original=snapshot(database);before=probe(database)
    install011(database,config['canonical']);installation=install(database);installed_state=readonly_state(database)
    again=install(database);idempotent=again['idempotent'] and readonly_state(database)==installed_state
    after=probe(database)
    source=ResearchStore(database).record('LM_QA_STORAGE014','qa_source','New append is allowed','{}','hypothesis',request_key='storage014:insert')
    final=snapshot(database);retention={table:final['tables'][table][:len(rows)]==rows for table,rows in original['tables'].items()}
    result={'status':'PASS' if all(not c['blocked'] for c in before['checks']) and all(c['blocked'] for c in after['checks'])
        and before['no_DB_delta'] and after['no_DB_delta'] and idempotent and all(retention.values()) else 'FAIL',
        'before':before,'after':after,'installation':installation,'idempotent':idempotent,'INSERT_event_id':source['id'],
        'retained_original_tables':retention,'production_deployment':False,
        'boundary':'Raw SQLite default connection has foreign_keys=OFF; triggers independently enforce immutability. Schema/file owner can remove guards; no claim against that actor.'}
    write_json(base/'security-before-after.json',result)
    (base/'production-review.sql').write_text('-- REVIEW ONLY: not automatically applied to production. Backup and operator approval required.\nBEGIN IMMEDIATE;\n'+
        ';\n'.join(SQL.values())+';\nCOMMIT;\n')
    return result,database


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path);args=p.parse_args()
    result,db=run(args.baseline or Path(Path('/tmp/lm014_path').read_text().strip()))
    print(json.dumps({'status':result['status'],'database':str(db)}))
