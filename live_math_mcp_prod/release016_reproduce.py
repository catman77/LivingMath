"""Replay the frozen016 calculation and its source-owned private feedback."""
import argparse
import json
from pathlib import Path

from normalizer import canonical
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore
from operational013_report import chain
from typed_cycle011 import journal_state
from typed_cycle011_store import connect
from release016_typed import execute
from release016_run import run, append


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    args = p.parse_args()
    base = args.work.resolve()
    base.mkdir(parents=True, mode=0o700, exist_ok=False)
    origin = base / 'disposable-origin.sqlite3'
    ResearchStore(origin)
    out = base / 'P0'
    run(base, out, args.source.resolve(), origin, args.package / 'pre-registration.json')
    db = base / 'private-QA.sqlite3'
    rows = [json.loads(s) for s in (out / 'typed-ledger.jsonl').read_text().splitlines()]
    receipt = next(r['data'] for r in rows if r['stage'] == 'receipt')
    project, mid = receipt['project'], receipt['move_id']
    with connect(db) as c:
        pc = json.loads(c.execute('SELECT p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (mid,)).fetchone()[0])
        state = journal_state(c, project, pc['scope'], pc['source_family_id'], pc['claim_fingerprint'], pc['raw_distinction_sha256'])
    try:
        execute(db, project, mid, base / 'raw/RH_XI_ROUTES_EXPORT_001')
        denial = 'UNEXPECTED_EXECUTION'
    except ValueError as error:
        denial = str(error)
    if denial != 'STALE_OBLIGATION_VERSION':
        raise ValueError('STALE_GRANT_CONTROL_FAILED:' + denial)
    store = ResearchStore(db)
    feedback = store.record(project, 'interpretation', 'Bound source feedback from receipt', canonical({
        'claim_type': 'EXPERIMENT_OBSERVATION', 'statement': 'n/h source containment and explicit-formula baseline both pass; no autonomous discovery or structural advantage.',
        'receipt_id': receipt['receipt_id'], 'measurement_event_id': receipt['event_id'], 'proof_status': 'unverified',
        'known_distinction': state, 'next_action': 'Review source-owned result; no new grant or execution.'}),
        'observation', parent_id=receipt['event_id'], request_key=project + ':feedback')
    append(out / 'typed-ledger.jsonl', {'stage': 'feedback_and_stale_denial', 'data': {
        'journal_state_after_receipt': state, 'feedback': feedback, 'stale_execution_denial': denial, 'new_native_calls': 0}})
    before, after = snapshot(origin), snapshot(db)
    view = store.moves.inspect(project, mid)
    integrity = chain(db)
    checks = {'P0_pass': json.loads((out / 'experiment-result.json').read_text())['status'] == 'PASS_SOURCE_BOUND_N_H_TRANSFER',
        'source_owned_journal': state == 'NO_NEW_DISTINCTION_BOUNDED', 'stale_grant_denied': denial == 'STALE_OBLIGATION_VERSION',
        'no_active_QA_permission': not view['execution_permission']['allowed'],
        'original_prefix_preserved': all(after['tables'][t][:len(r)] == r for t, r in before['tables'].items()),
        'sqlite': integrity['sqlite_integrity'] == 'ok' and not integrity['foreign_key_errors'],
        'hash_chain': integrity['hash_chain_ok'], 'proof_unverified': receipt['proof_status'] == 'unverified'}
    result = {'result': 'PASS_REPLAY' if all(checks.values()) else 'FAIL', 'checks': checks,
        'scientific_status': 'NO_STRUCTURAL_ADVANTAGE', 'autonomous_discovery': False,
        'receipt': receipt, 'chain': integrity, 'production_used': False, 'independent_new_scientific_evidence': False}
    write_json(base / 'replay-result.json', result)
    print(canonical(result))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
