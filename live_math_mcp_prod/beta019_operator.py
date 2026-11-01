"""Local019 owner CLI. The original018 lease authority is retained unchanged."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from deploy018_authority import activate, reconcile, template
from deploy018_storage import fault, private_path
from beta019_receipt import Receipt019
from normalizer import canonical


def commit(database: Path, request: dict) -> dict:
    private_path(database)
    op = template('engine017_operator')
    op.ReceiptValidator017 = Receipt019
    original = op.project_feedback
    def feedback(c, project, receipt_id, pc, event):
        result = original(c, project, receipt_id, pc, event)
        c.execute('INSERT INTO deploy018_consumptions VALUES (?,?)', (request['move_id'], receipt_id))
        fault('019_commit_transaction')
        return result
    op.project_feedback = feedback
    result = op.commit(database, request)
    fault('019_commit_after_commit')
    return result


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824)); resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    parser = argparse.ArgumentParser(); parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('action', choices=['activate', 'commit', 'reconcile']); args = parser.parse_args()
    try:
        request = json.loads(sys.stdin.read(65537))
        result = commit(args.db, request) if args.action == 'commit' else globals()[args.action](args.db, **request)
        print(canonical({'ok': True, 'result': result}))
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        print(canonical({'ok': False, 'error': str(error)})); raise SystemExit(2)
