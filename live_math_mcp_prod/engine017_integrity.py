"""Private017 integrity/cleanup helpers; never operate on a deployed database."""
import json
from pathlib import Path
import sqlite3
from normalizer import canonical
from research_store import ResearchStore
from qa_positive_acceptance import snapshot
from operational013_report import chain


def append_only(database, require_engine=True):
    tables = ['events', 'operations', 'research_moves', 'research_move_audits', 'research_move_status_history',
        'research_obligation_versions', 'typed011_configuration', 'typed011_scopes', 'typed011_precommits', 'typed011_moves',
        'typed011_activations', 'typed011_executions', 'typed011_receipts', 'typed011_journal',
        'engine017_sources', 'engine017_requests', 'engine017_projections']
    results = {}
    with sqlite3.connect(database) as c:
        available = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if require_engine and set(tables) - available:
        raise ValueError('INCOMPLETE_ENGINE_SCHEMA:' + ','.join(sorted(set(tables) - available)))
    for table in tables:
        if table not in available:
            continue
        with sqlite3.connect(database) as c:
            row = c.execute('SELECT rowid FROM ' + table + ' LIMIT 1').fetchone()
            if not row:
                continue
            column = c.execute('PRAGMA table_info(' + table + ')').fetchone()[1]
            for action in ('UPDATE', 'DELETE'):
                c.execute('BEGIN')
                try:
                    statement = 'UPDATE ' + table + ' SET ' + column + '=' + column + ' WHERE rowid=?' if action == 'UPDATE' else 'DELETE FROM ' + table + ' WHERE rowid=?'
                    c.execute(statement, row)
                    blocked = False
                except sqlite3.IntegrityError:
                    blocked = True
                finally:
                    c.rollback()
                results[table + ':' + action] = blocked
    return results


def own_permissions(database):
    store = ResearchStore(database)
    with store._connect() as c:
        moves = [dict(r) for r in c.execute("SELECT * FROM research_moves WHERE project LIKE 'LM_QA_TYPED011_ENGINE017_%'")]
    return [m['id'] for m in moves if store.moves.inspect(m['project'], m['id'])['execution_permission']['allowed']]


def cleanup_fault_copies(private):
    """Retire copied grants; preserve every deliberately corrupted row for RCA."""
    retired = []
    files = list((private / 'active-controls').glob('*.sqlite3')) + list((private / 'workspace').glob('artifact-*.sqlite3'))
    for database in files:
        store = ResearchStore(database)
        with store._connect() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM research_moves WHERE project LIKE 'LM_QA_TYPED011_ENGINE017_%'")]
        for move in rows:
            view = store.moves.inspect(move['project'], move['id'])
            if view['status'] not in ('COMPLETED', 'ABANDONED', 'REJECTED'):
                store.moves.transition(move['project'], move['id'], 'abandon', '017:fault-copy-cleanup:' + str(move['id']),
                    reason='Owner ends disposable fault control; original successful/failed evidence remains untouched.')
        left = own_permissions(database)
        if left:
            raise ValueError('REMAINING_FAULT_COPY_GRANTS:' + str(database))
        retired.append({'file': str(database), 'remaining_own_grants': left, 'integrity_subject': 'Deliberate corruption copy, not accepted ledger'})
    return retired


def verify_private(original, database, require_engine=True):
    before, after = snapshot(original), snapshot(database)
    prefixes = {t: after['tables'][t][:len(rows)] == rows for t, rows in before['tables'].items()}
    return {'all_original_table_prefixes': prefixes, 'chain': chain(database),
        'own_active_permissions': own_permissions(database), 'append_only': append_only(database, require_engine),
        'schema_scope': 'engine017_required' if require_engine else 'legacy_compatibility_only',
        'new_verified_events': [r['id'] for r in after['tables']['events'][len(before['tables']['events']):] if r['status'] == 'verified']}
