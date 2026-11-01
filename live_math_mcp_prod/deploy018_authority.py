"""Local018 authority overlay. No entrypoint in MCP; no new mathematics.

017 signed measurements remain immutable. A separate signed018 attestation
binds a one-shot expiring nonce to that exact measurement and activation.
Interrupted attempts are retained and revoked, never reconstructed as success.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011_store import connect, assert_isolated
from engine017_store import registered
from engine017_receipt import ReceiptValidator017
from deploy018_storage import private_path, statements, SQL_DIR, fault, writer

SOURCE = Path(__file__).resolve().parent


def template(name: str):
    # Fixed repository implementation, never a client-supplied import/path.
    if name not in ('engine017_operator', 'engine017_server', 'http_server', 'typed_cycle011_operator'):
        raise ValueError('018_UNREVIEWED_TEMPLATE')
    spec = importlib.util.spec_from_file_location('_018_' + name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install(database: Path) -> None:
    private_path(database)
    assert_isolated(database)
    with connect(database, True) as c:
        if c.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise ValueError('018_SCHEMA_VERSION_5_REQUIRED')
        for sql in statements(SQL_DIR / '018_authority.sql'):
            start = sql[sql.index('CREATE '):].rstrip(';')
            kind, name = start.split()[1:3]
            name = name.split('(')[0]
            row = c.execute('SELECT sql FROM sqlite_master WHERE name=? AND type=?', (name, kind.lower())).fetchone()
            if row and row[0] != start:
                raise ValueError('018_AUTHORITY_SCHEMA_CONFLICT:' + name)
            if not row:
                c.execute(sql)


def lease_in(c, project: str, move_id: int, now: float | None = None) -> dict:
    row = c.execute('SELECT payload_json,expires FROM deploy018_leases WHERE move_id=?', (move_id,)).fetchone()
    if not row:
        raise ValueError('018_LEASE_MISSING')
    body = json.loads(row['payload_json'])
    if body['project'] != project:
        raise ValueError('018_FOREIGN_LEASE')
    if row['expires'] <= (time.time() if now is None else now):
        raise ValueError('018_LEASE_EXPIRED_REAUDIT_REQUIRED')
    if c.execute('SELECT 1 FROM deploy018_revocations WHERE move_id=?', (move_id,)).fetchone():
        raise ValueError('018_LEASE_REVOKED')
    if c.execute('SELECT 1 FROM deploy018_consumptions WHERE move_id=?', (move_id,)).fetchone():
        raise ValueError('018_LEASE_CONSUMED')
    activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
    pc = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (move_id,)).fetchone()
    _, binding = registered(c, project)
    if not activation or not pc or any(body[k] != v for k, v in {
        'activation_operation_id': activation['operation_id'], 'audit_id': activation['audit_id'],
        'precommit_sha256': pc['digest'], 'key_id': digest(binding['executor_public_key']),
        'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}.items()):
        raise ValueError('018_LEASE_BINDING_OR_KEY_DRIFT')
    return body


def activate(database: Path, project: str, move_id: int, request_key: str, ttl: int = 300) -> dict:
    if not isinstance(ttl, int) or not 1 <= ttl <= 900:
        raise ValueError('018_LEASE_TTL_1_TO_900_REQUIRED')
    with writer(database):
        fault('activation_before_audit')
        op = template('typed_cycle011_operator')
        class AuditedStore(ResearchStore):
            def _audit(self, c, action, details):
                result = super()._audit(c, action, details)
                if action == 'research_move_audited':
                    fault('audit_transaction')
                return result
        op.ResearchStore = AuditedStore
        result = op.activate(database, project, move_id, request_key)
        fault('activation_after_audit')
        fault('activation_after_grant')
        with connect(database, True) as c:
            prior = c.execute('SELECT 1 FROM deploy018_leases WHERE move_id=?', (move_id,)).fetchone()
            if prior:
                return {**result, 'lease': lease_in(c, project, move_id), 'idempotent': True}
            _, binding = registered(c, project)
            act = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
            pc = c.execute('SELECT p.digest FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (move_id,)).fetchone()
            lease = {'protocol': 'execution-lease018/v1', 'project': project, 'move_id': move_id,
                'nonce': secrets.token_hex(32), 'issued_at': time.time(), 'expires': time.time() + ttl,
                'activation_operation_id': act['operation_id'], 'audit_id': act['audit_id'],
                'precommit_sha256': pc['digest'], 'key_id': digest(binding['executor_public_key']),
                'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            c.execute('INSERT INTO deploy018_leases VALUES (?,?,?,?)', (move_id, lease['nonce'], lease['expires'], canonical(lease)))
            ResearchStore(database)._audit(c, 'deploy018_lease_issued', {'move_id': move_id, 'lease_sha256': digest(lease)})
            fault('activation_transaction')
        return {**result, 'lease': lease, 'idempotent': False}


def execute(database: Path, project: str, move_id: int, environment_file: str, private_key_file: str) -> dict:
    # Imported only in the separately launched local executor process.
    import engine017_executor as original
    # Preserve the accepted017 error/binding checks before opening any secret.
    original.checked_grant(database, project, move_id)
    with writer(database), connect(database, True) as c:
        lease = lease_in(c, project, move_id)
        if c.execute('SELECT 1 FROM deploy018_attempts WHERE move_id=?', (move_id,)).fetchone():
            raise ValueError('018_ATTEMPT_ALREADY_PREPARED_NO_AUTOMATIC_RETRY')
        c.execute('INSERT INTO deploy018_attempts VALUES (?,?)', (move_id, canonical({'lease_sha256': digest(lease), 'prepared_at': time.time()})))
    fault('execution_prepared')
    measured = original.execute(database, project, move_id, environment_file, private_key_file)
    fault('execution_after_event')
    with connect(database, True) as c:
        lease_in(c, project, move_id)
        env = measured['envelope']
        body = {'protocol': 'measurement-attestation018/v1', 'lease': lease,
            'event_id': measured['event_id'], 'envelope_sha256': digest(env),
            'artifact_sha256': env['artifact_sha256'], 'outcome': env['outcome']}
        key = Ed25519PrivateKey.from_private_bytes(Path(private_key_file).read_bytes())
        attestation = {'body': body, 'signature': key.sign(canonical(body).encode()).hex()}
        c.execute('INSERT INTO deploy018_attestations VALUES (?,?,?)', (move_id, measured['event_id'], canonical(attestation)))
        ResearchStore(database)._audit(c, 'deploy018_attempt_attested', {'move_id': move_id, 'sha256': digest(attestation)})
    return {**measured, 'attestation': attestation}


class ReceiptValidator018(ReceiptValidator017):
    def validate_in(self, c, project, move_id, event_id):
        result = super().validate_in(c, project, move_id, event_id)
        if result['status'] != 'VALID_BOUND_MEASUREMENT':
            return result
        lease = lease_in(c, project, move_id)
        row = c.execute('SELECT payload_json FROM deploy018_attestations WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()
        if not row:
            raise ValueError('018_ATTESTATION_MISSING_REVIEW_REQUIRED')
        signed = json.loads(row[0])
        expected = {'protocol': 'measurement-attestation018/v1', 'lease': lease, 'event_id': event_id,
            'envelope_sha256': digest(result['envelope']), 'artifact_sha256': result['envelope']['artifact_sha256'],
            'outcome': result['envelope']['outcome']}
        if signed['body'] != expected:
            raise ValueError('018_NONCE_OR_MEASUREMENT_REBIND')
        _, binding = registered(c, project)
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(binding['executor_public_key'])).verify(
                bytes.fromhex(signed['signature']), canonical(expected).encode())
        except (InvalidSignature, ValueError) as error:
            raise ValueError('018_ATTESTATION_SIGNATURE_INVALID') from error
        return {**result, 'lease018_verified': True, 'proof_status': 'unverified'}


def commit(database: Path, request: dict) -> dict:
    private_path(database)
    op = template('engine017_operator')
    op.ReceiptValidator017 = ReceiptValidator018
    original = op.project_feedback

    def feedback(c, project, receipt_id, pc, event):
        projection = original(c, project, receipt_id, pc, event)
        c.execute('INSERT INTO deploy018_consumptions VALUES (?,?)', (request['move_id'], receipt_id))
        fault('commit_transaction')
        return projection

    op.project_feedback = feedback
    fault('commit_before_transaction')
    result = op.commit(database, request)
    fault('commit_after_commit')
    return result


def reconcile(database: Path, reason: str = '018 owner restart: outstanding permits revoked; new audited proposal required') -> list[int]:
    """Conservative restart policy: retain partial evidence, revoke every old grant.

    A fresh proposal/request is required; never resume or synthesize a measurement.
    Called by the local supervisor BEFORE mounting HTTP, never by a model tool.
    """
    with writer(database), connect(database, True) as c:
        store = ResearchStore(database)
        rows = c.execute('SELECT a.move_id,m.project FROM typed011_activations a JOIN research_moves m ON m.id=a.move_id').fetchall()
        retired = []
        for row in rows:
            if c.execute('SELECT 1 FROM typed011_receipts WHERE move_id=?', (row['move_id'],)).fetchone():
                continue
            view = store.moves._view(c, store.moves._row(c, row['project'], row['move_id']))
            if not c.execute('SELECT 1 FROM deploy018_revocations WHERE move_id=?', (row['move_id'],)).fetchone():
                c.execute('INSERT INTO deploy018_revocations VALUES (?,?)', (row['move_id'], reason))
                retired.append(row['move_id'])
            if view['status'] not in ('ABANDONED', 'REJECTED', 'COMPLETED'):
                store.moves._append(c, row['move_id'], 'ABANDONED', reason, decision={'allowed': False, 'needs_reaudit': True}, request_key='018:recovery:' + str(row['move_id']))
        return retired


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('action', choices=['activate', 'execute', 'commit', 'reconcile'])
    args = parser.parse_args()
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    try:
        payload = json.loads(sys.stdin.read(65537))
        fn = globals()[args.action]
        result = fn(args.db, payload) if args.action == 'commit' else fn(args.db, **payload)
        print(canonical({'ok': True, 'result': result}))
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        print(canonical({'ok': False, 'error': str(error)}))
        raise SystemExit(2)
