"""Real backup restore pairs and per-table UPDATE/DELETE refusal probes."""
import argparse
import json
from pathlib import Path
import sqlite3
from deploy018_storage import inventory, migrate, restore, backup
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore


def probes(database: Path, disposable: Path) -> dict:
    backup(database, disposable)
    # Reviews is legitimately empty in the live source. Seed a structurally
    # valid local review in the disposable copy only, not a verified event.
    with sqlite3.connect(disposable) as c:
        event = c.execute('SELECT id FROM events ORDER BY id LIMIT 1').fetchone()
        if event and not c.execute('SELECT 1 FROM reviews LIMIT 1').fetchone():
            c.execute('INSERT INTO reviews(event_id,verdict,reviewer,artifact_sha256,notes,created_at) VALUES (?,?,?,?,?,?)',
                (event[0], 'rejected', '018 disposable guard probe', '0' * 64, 'Engineering probe; no mathematical verification', 0))
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='deploy018_revocations'").fetchone() and not c.execute('SELECT 1 FROM deploy018_revocations LIMIT 1').fetchone():
            activation = c.execute('SELECT move_id FROM typed011_activations LIMIT 1').fetchone()
            if activation:
                c.execute('INSERT INTO deploy018_revocations VALUES (?,?)', (activation[0], '018 disposable SQL guard fixture; not an accepted ledger decision'))
        protected = sorted({r[0] for r in c.execute("SELECT tbl_name FROM sqlite_master WHERE type='trigger' AND name LIKE 'lm018_%'")})
    before = snapshot(disposable)
    records = []
    for table in protected:
        with sqlite3.connect(disposable) as c:
            populated = c.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone() is not None
            col = c.execute('PRAGMA table_info("' + table + '")').fetchone()[1]
            for action in ('UPDATE', 'DELETE'):
                if not populated:
                    records.append({'table': table, 'action': action, 'result': 'NOT_RUN', 'reason': 'Empty table; schema guard inventoried, no row trigger execution claimed'})
                    continue
                try:
                    c.execute('DELETE FROM "' + table + '"' if action == 'DELETE' else 'UPDATE "' + table + '" SET "' + col + '"="' + col + '"')
                    blocked = False
                except sqlite3.IntegrityError:
                    blocked = True
                finally:
                    c.rollback()
                records.append({'table': table, 'action': action, 'result': 'PASS' if blocked else 'FAIL'})
    assert snapshot(disposable) == before
    return {'records': records, 'rows_and_hashes_unchanged': True, 'all_exercised_pass': all(r['result'] == 'PASS' for r in records),
        'DDL_owner_trusted': True}


def run(base: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    states, pairs = {}, []
    for label in ('canonical', 'typed'):
        src = base / (label + '.sqlite3')
        initial = inventory(src)
        before = snapshot(src)
        for index in ('A', 'B'):
            dst = base / 'restores' / index / (label + '.sqlite3')
            restored = restore(src, dst)
            dry = migrate(dst, dry_run=True)
            assert snapshot(dst)['tables'] == before['tables']
            first = migrate(dst)
            once = snapshot(dst)
            second = migrate(dst)
            assert second['idempotent'] and snapshot(dst) == once
            assert all(once['tables'][t][:len(rows)] == rows for t, rows in before['tables'].items())
            guarded = probes(dst, base / 'restores' / index / (label + '-probe.sqlite3'))
            assert guarded['all_exercised_pass']
            pairs.append({'database': label, 'restore_set': index, 'restore': restored, 'migration': first,
                'second_migration': second, 'guards': guarded, 'all_old_rows_preserved': True})
            states[label + index] = {'before': initial, 'after': inventory(dst)}
    result = {'status': 'PASS', 'production_writes': False, 'restored_database_count': len(pairs), 'pairs': pairs}
    write_json(out / 'backup-restore.json', result)
    write_json(out / 'schema-before-after.json', states)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = run(a.base, a.out)
    print(json.dumps({'status': result['status'], 'restored_database_count': result['restored_database_count']}))
