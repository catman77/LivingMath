"""QA-only append-only extension; production/user_version5 remain unchanged."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from normalizer import canonical, digest

TABLES = {
    'typed011_configuration': 'id INTEGER PRIMARY KEY CHECK(id=1), payload_json TEXT NOT NULL',
    'typed011_scopes': 'project TEXT PRIMARY KEY, payload_json TEXT NOT NULL',
    'typed011_precommits': 'id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, request_key TEXT NOT NULL, request_sha TEXT NOT NULL, digest TEXT NOT NULL, payload_json TEXT NOT NULL, operation_json TEXT NOT NULL, preview_json TEXT NOT NULL, UNIQUE(project,request_key), UNIQUE(project,request_sha)',
    'typed011_moves': 'move_id INTEGER PRIMARY KEY REFERENCES research_moves(id), precommit_id INTEGER NOT NULL UNIQUE REFERENCES typed011_precommits(id)',
    'typed011_activations': 'move_id INTEGER PRIMARY KEY REFERENCES typed011_moves(move_id), audit_id INTEGER NOT NULL REFERENCES research_move_audits(id), operation_id INTEGER NOT NULL UNIQUE REFERENCES operations(id), payload_json TEXT NOT NULL',
    'typed011_executions': 'move_id INTEGER PRIMARY KEY REFERENCES typed011_moves(move_id), event_id INTEGER NOT NULL UNIQUE REFERENCES events(id), payload_json TEXT NOT NULL',
    'typed011_receipts': 'id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, move_id INTEGER NOT NULL UNIQUE REFERENCES typed011_moves(move_id), event_id INTEGER NOT NULL UNIQUE REFERENCES events(id), request_key TEXT NOT NULL, request_digest TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(project,request_key)',
    'typed011_journal': 'id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, scope TEXT NOT NULL, source_family_id TEXT NOT NULL, claim_fingerprint TEXT NOT NULL, raw_sha256 TEXT NOT NULL, receipt_id INTEGER NOT NULL REFERENCES typed011_receipts(id), payload_json TEXT NOT NULL',
}


def assert_isolated(database):
    path=Path(database).resolve(strict=True)
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as c:
            row=c.execute('SELECT payload_json FROM typed011_configuration WHERE id=1').fetchone()
    except sqlite3.Error as error:raise ValueError('MISSING_ISOLATED_SCHEMA') from error
    if row is None:raise ValueError('MISSING_ISOLATION_CONFIGURATION')
    canonical_db=Path(json.loads(row[0])['canonical_database'])
    if path==canonical_db.resolve() or (canonical_db.exists() and path.samefile(canonical_db)):
        raise ValueError('PRODUCTION_WRITE_FORBIDDEN')


@contextmanager
def connect(database, write=False, initializing=False):
    path = Path(database).resolve(strict=True)
    if write and not initializing:assert_isolated(path)
    c = sqlite3.connect(str(path) if write else path.as_uri() + '?mode=ro', uri=not write, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    if write: c.execute('BEGIN IMMEDIATE')
    else:
        c.execute('PRAGMA query_only=ON')
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION}
        c.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    try:
        with c: yield c
    finally: c.close()


def install(database, canonical_database):
    if Path(database).resolve(strict=True).samefile(Path(canonical_database).resolve(strict=True)):
        raise ValueError('PRODUCTION_MIGRATION_FORBIDDEN')
    with connect(database, True, initializing=True) as c:
        for name, columns in TABLES.items():
            c.execute('CREATE TABLE IF NOT EXISTS ' + name + '(' + columns + ')')
            for action in ('UPDATE', 'DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT,'typed011 append-only'); END")
        config=canonical({'canonical_database':str(Path(canonical_database).resolve(strict=True)),'extension_version':1})
        prior=c.execute('SELECT payload_json FROM typed011_configuration WHERE id=1').fetchone()
        if prior and prior[0]!=config:raise ValueError('ISOLATION_CONFIGURATION_CONFLICT')
        c.execute('INSERT OR IGNORE INTO typed011_configuration VALUES (1,?)',(config,))


def scope(c, project):
    if not project.startswith('LM_QA_TYPED011_'): raise ValueError('QA_NAMESPACE_REQUIRED')
    row = c.execute('SELECT * FROM typed011_scopes WHERE project=?', (project,)).fetchone()
    if row is None: raise ValueError('NOVELTY_CONTEXT_INCOMPLETE')
    return json.loads(row['payload_json'])


def register_scope(database, project, payload):
    assert_isolated(database)
    from research_store import ResearchStore
    store = ResearchStore(database)
    with connect(database, True) as c:
        if not project.startswith('LM_QA_TYPED011_'): raise ValueError('QA_NAMESPACE_REQUIRED')
        fixture = c.execute('SELECT * FROM events WHERE id=? AND project=?', (payload['fixture_id'], project)).fetchone()
        if fixture is None or digest(dict(fixture)) != payload['fixture_sha256']: raise ValueError('REGISTERED_FIXTURE_HASH_MISMATCH')
        declared = json.loads(fixture['content'])
        if declared.get('environment_commitment') != payload['environment_sha256'] or declared.get('fixture_sha256') != payload['fixture_content_sha256']:
            raise ValueError('REGISTERED_SOURCE_COMMITMENT_MISMATCH')
        prior = c.execute('SELECT payload_json FROM typed011_scopes WHERE project=?', (project,)).fetchone()
        if prior:
            if json.loads(prior[0]) != payload: raise ValueError('SCOPE_IDENTITY_CONFLICT')
            return
        c.execute('INSERT INTO typed011_scopes VALUES (?,?)', (project, canonical(payload)))
        store._audit(c, 'typed011_scope_registered', {'project': project, 'digest': digest(payload)})
