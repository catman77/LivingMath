"""Local owner authority. Reuses011 activation and014 atomic receipt discipline."""
import argparse
import json
from pathlib import Path
import sys
from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011_operator import activate
from typed_cycle011_store import assert_isolated, connect, scope
from law_validation014_contract import ReceiptRequest014
from engine017_receipt import ReceiptValidator017
from engine017_store import project_feedback


def commit(database, request):
    assert_isolated(database)
    req = ReceiptRequest014.model_validate(request)
    payload = req.model_dump()
    request_digest = digest({k: v for k, v in payload.items() if k != 'request_key'})
    store = ResearchStore(database)
    validator = ReceiptValidator017(database)
    with connect(database, True) as c:
        scope(c, req.project)
        prior_key = c.execute('SELECT * FROM typed011_receipts WHERE project=? AND request_key=?', (req.project, req.request_key)).fetchone()
        if prior_key and prior_key['request_digest'] != request_digest:
            raise ValueError('RECEIPT_REQUEST_KEY_CONFLICT')
        prior = c.execute('SELECT * FROM typed011_receipts WHERE project=? AND move_id=?', (req.project, req.move_id)).fetchone()
        if prior:
            if prior['request_digest'] != request_digest:
                raise ValueError('TERMINAL_RECEIPT_CONFLICT')
            return {**json.loads(prior['payload_json']), 'receipt_id': prior['id'], 'idempotent': True}
        checked = validator.validate_in(c, req.project, req.move_id, req.event_id)
        if checked['status'] != 'VALID_BOUND_MEASUREMENT':
            raise ValueError(checked['status'] + ':' + checked['reason'])
        env = checked['envelope']
        if any(payload[k] != env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')):
            raise ValueError('RECEIPT_RESULT_EVENT_CONFLICT')
        row = c.execute('SELECT * FROM typed011_precommits WHERE id=?', (checked['precommit_id'],)).fetchone()
        pc = json.loads(row['payload_json'])
        result = {'outcome': req.outcome, 'summary': req.summary, 'data': {'observed': payload['observed'],
            'measurement_event_id': req.event_id, 'measurement_sha256': checked['event_sha256'], 'precommit_sha256': row['digest']}}
        store.moves._append(c, req.move_id, 'COMPLETED', req.reason, checked['audit_id'],
            {'allowed': False, 'result': result, 'evidence_refs': ['event:' + str(req.event_id)],
             'completion_contract': 'typed017/v1', 'proof_status': 'unverified'}, 'typed017:commit:' + req.request_key)
        receipt = {**payload, **{k: checked[k] for k in ('precommit_id', 'precommit_sha256', 'audit_id', 'activation_operation_id', 'event_sha256')},
            'status': 'COMPLETED', 'execution_permission': {'allowed': False}, 'artifact_inspection': checked['artifact_inspection'],
            'measurement_authenticity': checked['measurement_authenticity'], 'inspection_status': checked['inspection_status']}
        cursor = c.execute('INSERT INTO typed011_receipts(project,move_id,event_id,request_key,request_digest,payload_json) VALUES (?,?,?,?,?,?)',
            (req.project, req.move_id, req.event_id, req.request_key, request_digest, canonical(receipt)))
        receipt_id = cursor.lastrowid
        journal = {'receipt_id': receipt_id, 'event_id': req.event_id, 'event_sha256': checked['event_sha256'],
            'outcome': req.outcome, 'obligation_version': pc['obligation_version'], 'source_bindings': pc['source_bindings'],
            'raw_distinction': json.loads(row['preview_json'])['raw_distinction'], 'proof_status': 'unverified',
            'meaning': 'Committed bound attempt and actual outcome, not truth of a forecast.'}
        c.execute('INSERT INTO typed011_journal(project,scope,source_family_id,claim_fingerprint,raw_sha256,receipt_id,payload_json) VALUES (?,?,?,?,?,?,?)',
            (req.project, pc['scope'], pc['source_family_id'], pc['claim_fingerprint'], pc['raw_distinction_sha256'], receipt_id, canonical(journal)))
        projection = project_feedback(c, req.project, receipt_id, pc, {**env, 'event_id': req.event_id})
        store._audit(c, 'typed011_receipt_committed', {'receipt_id': receipt_id, 'request_digest': request_digest,
            'receipt_sha256': digest(receipt), 'journal_sha256': digest(journal)})
        store._audit(c, 'engine017_feedback_projected', {'project': req.project, 'receipt_id': receipt_id,
            'version': projection['version'], 'projection_sha256': digest(projection)})
        return {**receipt, 'receipt_id': receipt_id, 'idempotent': False, 'feedback_projection': projection}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('action', choices=['activate', 'commit'])
    args = parser.parse_args()
    try:
        request = json.loads(sys.stdin.read(65537))
        result = activate(args.db, **request) if args.action == 'activate' else commit(args.db, request)
        print(canonical({'ok': True, 'result': result}))
    except (ValueError, KeyError, OSError, __import__('sqlite3').Error) as error:
        print(canonical({'ok': False, 'error': str(error)}))
        raise SystemExit(2)
