"""Private engineering boundaries; no research or production writes."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from research_store import ResearchStore
from qa_positive_acceptance import snapshot
from test_engine017 import context
from engine017_fixtures import seed
from engine017_controller import EngineController017
from deploy018_storage import migrate, backup, restore, inventory, private_path
from deploy018_authority import install, activate, execute, commit, ReceiptValidator018, reconcile


@pytest.fixture
def bound(context):
    policy, legacy, db, workspace, seals = context
    migrate(db)
    install(db)
    world = seed(db, workspace, seals, policy['families'][0], policy['cases'][0], 'UNIT018')
    pc = EngineController017(db).precommit({'project': world['project']}, '018-unit')
    return db, world, pc


def request_for(world, pc, measured):
    env = measured['envelope']
    return {'project': world['project'], 'move_id': pc['move_id'], 'event_id': measured['event_id'], 'request_key': '018-complete',
        **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}


def measure(bound):
    db, world, pc = bound
    activate(db, world['project'], pc['move_id'], '018-unit')
    value = execute(db, world['project'], pc['move_id'], world['environment'], world['private_key_file'])
    return value, request_for(world, pc, value)


def test_migration_legacy_idempotent_and_preserves_all_rows(tmp_path):
    db = tmp_path / 'legacy.sqlite3'
    ResearchStore(db).record('LM_QA_018_UNIT', 'qa_source', 'fixture', 'finite control', 'hypothesis')
    before = snapshot(db)
    assert migrate(db, dry_run=True)['added_triggers'] == 32
    assert snapshot(db) == before
    assert migrate(db)['profiles'] == ['core']
    after = snapshot(db)
    assert all(after['tables'][t][:len(rs)] == rs for t, rs in before['tables'].items())
    assert migrate(db)['idempotent']
    assert snapshot(db) == after


@pytest.mark.parametrize('point', ['migration_prepare', 'migration_transaction', 'migration_before_commit', 'migration_after_commit'])
def test_sigkill_migration_atomic(tmp_path, point):
    db = tmp_path / 'db.sqlite3'
    ResearchStore(db)
    before = snapshot(db)
    code = 'from pathlib import Path;from deploy018_storage import migrate;migrate(Path(__import__("sys").argv[1]))'
    proc = subprocess.run([sys.executable, '-c', code, str(db)], env={**os.environ, 'LM018_FAULT': point}, capture_output=True)
    assert proc.returncode == -9, proc.stderr
    after = snapshot(db)
    if point != 'migration_after_commit':
        assert before == after
    else:
        assert migrate(db)['idempotent']
    assert inventory(db)['chain']['hash_chain_ok']


def test_partial_schema_conflict_and_version_fail_closed(tmp_path):
    db = tmp_path / 'db.sqlite3'
    ResearchStore(db)
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE typed011_moves(dummy)')
    before = snapshot(db)
    with pytest.raises(ValueError, match='PARTIAL_EXTENSION_SCHEMA'):
        migrate(db)
    assert snapshot(db) == before
    with sqlite3.connect(db) as c:
        c.execute('DROP TABLE typed011_moves')
        c.execute("CREATE TRIGGER lm018_events_update BEFORE UPDATE ON events BEGIN SELECT 1; END")
    before = snapshot(db)
    with pytest.raises(ValueError, match='TRIGGER_CONFLICT'):
        migrate(db)
    assert snapshot(db) == before
    with sqlite3.connect(db) as c:
        c.execute('PRAGMA user_version=4')
    with pytest.raises(ValueError, match='SCHEMA_VERSION_5_REQUIRED'):
        migrate(db)


def test_backup_two_new_restores_and_exclusive_destinations(tmp_path):
    source = tmp_path / 'source.sqlite3'
    ResearchStore(source).record('LM_QA_018_UNIT', 'qa_source', 'fixture', 'finite control', 'hypothesis')
    snap = tmp_path / 'backup.sqlite3'
    before = backup(source, snap)
    for n in (1, 2):
        target = tmp_path / str(n) / 'restore.sqlite3'
        result = restore(snap, target)
        assert result['after']['file_sha256'] == before['file_sha256']
        assert result['after']['inode'] != before['inode']
        migrate(target)
        with pytest.raises(ValueError, match='TARGET_EXISTS'):
            restore(snap, target)
    with pytest.raises(FileExistsError):
        backup(source, snap)


def test_live_db_and_hardlink_migrations_forbidden(tmp_path, monkeypatch):
    import deploy018_storage as storage
    live = tmp_path / 'live.sqlite3'
    ResearchStore(live)
    alias = tmp_path / 'hardlink.sqlite3'
    os.link(live, alias)
    monkeypatch.setattr(storage, 'LIVE', (live,))
    for path in (live, alias):
        with pytest.raises(ValueError, match='PRODUCTION_WRITE_NOT_AUTHORIZED'):
            private_path(path)


def test_schema5_with_changed_columns_rejected_without_delta(tmp_path):
    db = tmp_path / 'schema.sqlite3'
    ResearchStore(db)
    with sqlite3.connect(db) as c:
        c.execute('ALTER TABLE events ADD COLUMN unreviewed TEXT')
    before = inventory(db)
    with pytest.raises(ValueError, match='SCHEMA_DEFINITION_MISMATCH:events'):
        migrate(db)
    assert inventory(db) == before
    missing = tmp_path / 'missing.sqlite3'
    with pytest.raises(ValueError, match='EXISTING_DATABASE_REQUIRED'):
        migrate(missing)
    assert not missing.exists()


def test_backup_api_accepts_hot_wal_restore_requires_closed_snapshot(tmp_path):
    db = tmp_path / 'wal.sqlite3'
    store = ResearchStore(db)
    with sqlite3.connect(db) as hold:
        hold.execute('PRAGMA journal_mode=WAL')
        store.record('LM_QA_018_WAL', 'qa_source', 'WAL', 'Committed hot source', 'hypothesis')
        snap = tmp_path / 'closed-snapshot.sqlite3'
        state = backup(db, snap)
        assert state['tables']['events']['count'] == 1
        with pytest.raises(ValueError, match='CLOSED_BACKUP_API_SNAPSHOT'):
            restore(db, tmp_path / 'forbidden-raw.sqlite3')
    assert restore(snap, tmp_path / 'valid-restore.sqlite3')['status'] == 'PASS'


def test_full_lease_commit_and_immutable_history(bound):
    db, world, pc = bound
    measured, request = measure(bound)
    checked = ReceiptValidator018(db).validate(world['project'], pc['move_id'], measured['event_id'])
    assert checked['lease018_verified']
    one = commit(db, request)
    before = snapshot(db)
    two = commit(db, request)
    assert one['receipt_id'] == two['receipt_id'] and two['idempotent']
    assert snapshot(db) == before
    with pytest.raises(ValueError, match='CONFLICT'):
        commit(db, {**request, 'outcome': 'FAILURE'})
    assert snapshot(db) == before
    with pytest.raises(ValueError, match='TERMINAL_OR_REVOKED_ACTIVATION'):
        activate(db, world['project'], pc['move_id'], 'repeat')
    assert not ResearchStore(db).moves.inspect(world['project'], pc['move_id'])['execution_permission']['allowed']
    with sqlite3.connect(db) as c:
        for table in ['events', 'operations', 'typed011_receipts', 'typed011_journal', 'engine017_sources',
                      'engine017_projections', 'deploy018_leases', 'deploy018_attempts', 'deploy018_attestations', 'deploy018_consumptions']:
            for action in ['UPDATE', 'DELETE']:
                col = c.execute('PRAGMA table_info(' + table + ')').fetchone()[1]
                with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                    c.execute('DELETE FROM ' + table if action == 'DELETE' else 'UPDATE ' + table + ' SET ' + col + '=' + col)
                c.rollback()
    assert inventory(db)['chain']['hash_chain_ok']


@pytest.mark.parametrize('mutation', ['nonce', 'key_id', 'foreign_project', 'signature', 'expiry'])
def test_signed_tamper_denied_without_commit_delta(bound, mutation):
    db, world, pc = bound
    measured, request = measure(bound)
    with sqlite3.connect(db) as c:
        table = 'deploy018_leases' if mutation == 'expiry' else 'deploy018_attestations'
        c.execute('DROP TRIGGER lm018_' + table + '_update')
        if mutation == 'expiry':
            c.execute('UPDATE deploy018_leases SET expires=0')
        else:
            value = json.loads(c.execute('SELECT payload_json FROM deploy018_attestations').fetchone()[0])
            if mutation == 'signature':
                value['signature'] = '00' * 64
            else:
                field = {'foreign_project': 'project'}.get(mutation, mutation)
                value['body']['lease'][field] = 'tampered'
            c.execute('UPDATE deploy018_attestations SET payload_json=?', (json.dumps(value),))
    before = snapshot(db)
    with pytest.raises(ValueError, match='018_'):
        commit(db, request)
    assert snapshot(db) == before


@pytest.mark.parametrize('point', ['activation_before_audit', 'audit_transaction', 'activation_after_grant', 'activation_transaction', 'execution_prepared', 'execution_after_event', 'commit_transaction', 'commit_after_commit'])
def test_kill_reconcile_preserves_evidence_without_ghost_grant(bound, point):
    db, world, pc = bound
    action, payload = 'activate', {'project': world['project'], 'move_id': pc['move_id'], 'request_key': 'kill'}
    if point.startswith('execution'):
        activate(db, world['project'], pc['move_id'], 'kill')
        action, payload = 'execute', {'project': world['project'], 'move_id': pc['move_id'],
            'environment_file': world['environment'], 'private_key_file': world['private_key_file']}
    elif point.startswith('commit'):
        _, payload = measure(bound)
        action = 'commit'
    before = snapshot(db)
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name('deploy018_authority.py')),
        '--db', str(db), action], input=json.dumps(payload), text=True, capture_output=True,
        env={**os.environ, 'LM018_FAULT': point}, timeout=15)
    assert proc.returncode == -9, proc.stdout + proc.stderr
    after = snapshot(db)
    assert all(after['tables'][t][:len(rs)] == rs for t, rs in before['tables'].items())
    if point == 'commit_transaction':
        assert snapshot(db) == before
    if point == 'commit_after_commit':
        assert commit(db, payload)['idempotent']
    reconcile(db)
    assert not ResearchStore(db).moves.inspect(world['project'], pc['move_id'])['execution_permission']['allowed']
    assert inventory(db)['chain']['hash_chain_ok']
