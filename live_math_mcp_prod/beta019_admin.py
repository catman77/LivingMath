"""Owner-only beta init/export/exact-snapshot namespace restore and inspection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011_store import install as install011
from engine017_store import install as install017
from deploy018_storage import private_path, backup, inventory, fault
from deploy018_authority import install as install018, reconcile
from deploy018_storage import migrate


def write(path, payload):
    path = Path(path)
    temp = path.with_name(path.name + '.new')
    with temp.open('w') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def state_paths(root):
    state = Path(root).resolve() / 'state'
    canonical, typed = state / 'research.sqlite3', state / 'beta.sqlite3'
    private_path(canonical); private_path(typed)
    return state, canonical, typed


def recover_restore(root):
    root = Path(root).resolve()
    journal = root / 'restore-plan.json'
    if not journal.exists():
        return {'recovered': False}
    plan = json.loads(journal.read_text())
    state, prepared, preserved = root / 'state', root / plan['prepared'], root / plan['preserved']
    if prepared.parent != root or preserved.parent != root or not prepared.name.startswith('state.restore-') or not preserved.name.startswith('state.preserved-'):
        raise ValueError('019_INVALID_RESTORE_JOURNAL')
    if state.exists() and prepared.exists() and not preserved.exists():
        state.rename(preserved)
        fault('019_restore_after_rename')
    if not state.exists() and prepared.exists() and preserved.exists():
        prepared.rename(state)
    if not state.exists() or prepared.exists() or not preserved.exists():
        raise ValueError('019_RESTORE_REQUIRES_OPERATOR_REVIEW')
    for name, expected in plan['databases'].items():
        actual = inventory(state / name)
        if any(digest(actual[k]) != digest(expected[k]) for k in ('logical_sha256', 'schema_sha256', 'sequence', 'chain')):
            raise ValueError('019_RESTORED_SNAPSHOT_MISMATCH:' + name)
    # Journal is retired only after both DBs and every public source artifact
    # are present at their original namespace; no SQLite row/path is rewritten.
    for name, expected in plan['artifacts'].items():
        if hashlib.sha256((state / name).read_bytes()).hexdigest() != expected:
            raise ValueError('019_RESTORED_ARTIFACT_MISMATCH')
    completed = root / 'exports' / ('restore-completed-' + plan['operation'] + '.json')
    journal.rename(completed)
    return {'recovered': True, 'operation': plan['operation'], 'preserved_original_state': str(preserved),
        'snapshot_hashes_match': True, 'credentials': 'TLS/OAuth recreated separately; executor seals outside state retained'}


def initialise(root):
    root = Path(root).resolve(); root.mkdir(parents=True, mode=0o700, exist_ok=True)
    recovery = recover_restore(root)
    state, canonical, typed = state_paths(root)
    marker = state / '.beta019-state.json'
    if state.exists() and any(state.iterdir()) and not marker.exists():
        raise ValueError('019_REFUSE_UNOWNED_NONEMPTY_STATE')
    state.mkdir(mode=0o700, exist_ok=True)
    ResearchStore(canonical); ResearchStore(typed)
    install011(typed, canonical); install017(typed)
    migrations = {'canonical': migrate(canonical), 'typed': migrate(typed)}
    install018(typed)
    if not marker.exists():
        write(marker, {'release': '1.0.0b1', 'scope': 'new isolated private beta', 'canonical': str(canonical), 'typed': str(typed)})
    return {'status': 'PASS', 'state': str(state), 'migrations': migrations, 'recovery': recovery}


def export_snapshot(root):
    root = Path(root).resolve(); state, canonical, typed = state_paths(root)
    if not (state / '.beta019-state.json').exists():
        raise ValueError('019_OWNED_BETA_STATE_REQUIRED')
    retired = reconcile(typed, '019 owner export: revoke unfinished permits before snapshot')
    destination = root / 'exports' / ('snapshot-' + stamp()); destination.mkdir(parents=True, mode=0o700)
    states = {name: backup(path, destination / name) for name, path in [('research.sqlite3', canonical), ('beta.sqlite3', typed)]}
    artifacts = {}
    for p in (state / 'artifacts').rglob('*.json'):
        rel = p.relative_to(state); dst = destination / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst); artifacts[str(rel)] = hashlib.sha256(dst.read_bytes()).hexdigest()
    shutil.copy2(state / '.beta019-state.json', destination / '.beta019-state.json')
    manifest = {'scope': 'private scientific DB/public signed artifact snapshot; no OAuth/TLS/password/private executor key',
        'databases': states, 'artifacts': artifacts, 'retired_move_ids': retired}
    write(destination / 'snapshot-manifest.json', manifest)
    return {'status': 'PASS', 'snapshot': str(destination), 'manifest_sha256': hashlib.sha256((destination / 'snapshot-manifest.json').read_bytes()).hexdigest()}


def restore_snapshot(root, snapshot):
    root, snapshot = Path(root).resolve(), Path(snapshot).resolve(strict=True)
    state, _, _ = state_paths(root)
    if (root / 'restore-plan.json').exists():
        return recover_restore(root)
    manifest = json.loads((snapshot / 'snapshot-manifest.json').read_text())
    if set(manifest['databases']) != {'research.sqlite3', 'beta.sqlite3'}:
        raise ValueError('019_INCOMPLETE_PAIRED_SNAPSHOT')
    # Never roll back newer append-only records. This operation is only an
    # exact-state recovery rehearsal; original namespace is retained aside.
    for name, expected in manifest['databases'].items():
        actual, saved = inventory(state / name), inventory(snapshot / name)
        if any(digest(actual[k]) != digest(expected[k]) or digest(saved[k]) != digest(expected[k]) for k in ('logical_sha256', 'schema_sha256', 'sequence', 'chain')):
            raise ValueError('019_REFUSE_STALE_OR_INVALID_SNAPSHOT')
    token = stamp(); prepared = root / ('state.restore-' + token); preserved = root / ('state.preserved-' + token)
    prepared.mkdir(mode=0o700)
    from deploy018_storage import restore
    for name in manifest['databases']:
        restore(snapshot / name, prepared / name)
    for name, expected in manifest['artifacts'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or rel.parts[0] != 'artifacts' or hashlib.sha256((snapshot / rel).read_bytes()).hexdigest() != expected:
            raise ValueError('019_INVALID_SNAPSHOT_ARTIFACT')
        target = prepared / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(snapshot / rel, target)
    shutil.copy2(snapshot / '.beta019-state.json', prepared / '.beta019-state.json')
    plan = {'operation': token, 'prepared': prepared.name, 'preserved': preserved.name,
        'databases': manifest['databases'], 'artifacts': manifest['artifacts'], 'meaning': 'exact snapshot only, not destructive rollback'}
    write(root / 'restore-plan.json', plan)
    fault('019_restore_prepared')
    return recover_restore(root)


def inspect(root):
    state, canonical_db, typed = state_paths(root)
    if not (state / '.beta019-state.json').exists():
        raise ValueError('019_OWNED_BETA_STATE_REQUIRED')
    result = {'canonical': inventory(canonical_db), 'typed': inventory(typed), 'proof_status': 'unverified'}
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from engine017_store import registered
    from typed_cycle011_store import connect
    with connect(typed) as c:
        receipts = c.execute('SELECT r.project,r.move_id,r.event_id,x.payload_json FROM typed011_receipts r JOIN typed011_executions x ON x.move_id=r.move_id ORDER BY r.id').fetchall()
        checked = []
        for row in receipts:
            local = json.loads(row['payload_json']); raw = Path(local['artifact_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != local['artifact_sha256']:
                raise ValueError('019_ARCHIVE_ARTIFACT_DIGEST_MISMATCH')
            artifact = json.loads(raw); _, binding = registered(c, row['project'])
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(binding['executor_public_key'])).verify(bytes.fromhex(artifact['signature']), canonical(artifact['source_receipt']).encode())
            checked.append({'move_id': row['move_id'], 'event_id': row['event_id'], 'artifact_hash_and_signature': 'PASS', 'proof_status': 'unverified'})
        result['committed_artifacts'] = checked
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=['init', 'export', 'restore', 'recover', 'inspect']); parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    try:
        fn = {'init': initialise, 'export': export_snapshot, 'restore': restore_snapshot, 'recover': recover_restore, 'inspect': inspect}[args.action]
        result = fn(args.root, args.snapshot) if args.action == 'restore' else fn(args.root)
        print(canonical({'ok': True, 'result': result}))
    except (ValueError, OSError, KeyError, sqlite3.Error) as error:
        print(canonical({'ok': False, 'error': str(error)})); raise SystemExit(2)
