"""018 private-only backup, additive migration and immutable-history inventory.

Never imports or mutates a running service. File/DDL owners remain trusted.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3

from normalizer import canonical, digest

SQL_DIR = Path(__file__).with_name('migrations')
LIVE = (Path.home() / '.local/share/livingmath/research.sqlite3',
        Path.home() / '.local/share/livingmath/typed011/research.sqlite3')


def private_path(path: Path) -> Path:
    path = Path(path).resolve()
    for live in LIVE:
        if path == live.resolve() or (path.exists() and live.exists() and path.samefile(live)):
            raise ValueError('018_PRODUCTION_WRITE_NOT_AUTHORIZED')
    return path


def fault(point: str) -> None:
    """Local QA failpoint; the HTTP service never accepts it as input."""
    if os.environ.get('LM018_FAULT') == point:
        os.kill(os.getpid(), signal.SIGKILL)


@contextmanager
def writer(path: Path):
    path = private_path(path)
    with Path(str(path) + '.018-writer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('018_OPERATOR_WRITER_BUSY') from error
        yield path


def inventory(path: Path) -> dict:
    from operational013_report import chain
    path = Path(path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
        c.execute('BEGIN')
        schema = c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        tables = [r[1] for r in schema if r[0] == 'table' and not r[1].startswith('sqlite_')]
        rows = {t: c.execute('SELECT * FROM "' + t + '" ORDER BY rowid').fetchall() for t in tables}
        result = {'user_version': c.execute('PRAGMA user_version').fetchone()[0],
            'schema': schema, 'schema_sha256': digest(schema),
            'tables': {t: {'count': len(rs), 'sha256': digest(rs)} for t, rs in rows.items()},
            'sequence': c.execute('SELECT * FROM sqlite_sequence ORDER BY name').fetchall(),
            'logical_sha256': digest(rows), 'triggers': [r[1] for r in schema if r[0] == 'trigger']}
    return {**result, 'chain': chain(path), 'inode': path.stat().st_ino,
        'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def backup(source: Path, target: Path) -> dict:
    source, target = Path(source).resolve(strict=True), private_path(target)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Fail closed instead of silently replacing an accepted backup.
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    state = inventory(target)
    if state['chain']['sqlite_integrity'] != 'ok' or state['chain']['foreign_key_errors'] or not state['chain']['hash_chain_ok']:
        raise ValueError('018_BACKUP_INTEGRITY_FAILURE')
    return state


def restore(source: Path, target: Path) -> dict:
    """Restore an already consistent BackupAPI snapshot to a NEW path."""
    source, target = Path(source).resolve(strict=True), private_path(target)
    wal = Path(str(source) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('018_RESTORE_REQUIRES_CLOSED_BACKUP_API_SNAPSHOT')
    before = inventory(source)
    if before['chain']['sqlite_integrity'] != 'ok' or before['chain']['foreign_key_errors'] or not before['chain']['hash_chain_ok']:
        raise ValueError('018_RESTORE_SOURCE_INVALID')
    if target.exists():
        raise ValueError('018_RESTORE_TARGET_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = target.with_name(target.name + '.partial')
    with partial.open('xb') as stream:
        os.chmod(partial, 0o600)
        stream.write(source.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    checked = inventory(partial)
    if any(before[k] != checked[k] for k in ('logical_sha256', 'schema_sha256', 'sequence', 'file_sha256', 'chain')):
        raise ValueError('018_RESTORE_PARTIAL_MISMATCH_NOT_PUBLISHED')
    fault('restore_before_publish')
    # link is atomic and refuses a concurrently created destination.
    os.link(partial, target)
    partial.unlink()
    fd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    after = inventory(target)
    if any(before[k] != after[k] for k in ('logical_sha256', 'schema_sha256', 'sequence', 'file_sha256', 'chain')) or before['inode'] == after['inode']:
        raise ValueError('018_RESTORE_MISMATCH')
    return {'status': 'PASS', 'before': before, 'after': after}


def statements(path: Path) -> list[str]:
    buf, out = '', []
    for line in path.read_text().splitlines(True):
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ''
    if buf.strip():
        raise ValueError('018_INCOMPLETE_SQL')
    return out


def migration_plan(c) -> tuple[list[str], list[str]]:
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    core = {r.split(' ON ')[1].split(' ')[0] for r in statements(SQL_DIR / '018_core.sql')}
    if not core <= tables:
        raise ValueError('018_MISSING_CORE_SCHEMA:' + ','.join(sorted(core - tables)))
    profiles = ['core']
    for profile, prefix, expected in [('typed', 'typed011_', 8), ('engine', 'engine017_', 3)]:
        found = {t for t in tables if t.startswith(prefix)}
        if found:
            required = {r.split(' ON ')[1].split(' ')[0] for r in statements(SQL_DIR / ('018_' + profile + '.sql'))}
            if found != required or len(found) != expected or (profile == 'engine' and 'typed' not in profiles):
                raise ValueError('018_PARTIAL_EXTENSION_SCHEMA:' + profile)
            profiles.append(profile)
    expected_schema = json.loads((SQL_DIR / '018_schema.json').read_text())
    for profile in profiles:
        for table, expected in expected_schema[profile].items():
            actual = {'columns': c.execute('PRAGMA table_info(' + table + ')').fetchall(),
                'foreign_keys': c.execute('PRAGMA foreign_key_list(' + table + ')').fetchall()}
            if digest(actual) != digest(expected):
                raise ValueError('018_SCHEMA_DEFINITION_MISMATCH:' + table)
    return profiles, [s for p in profiles for s in statements(SQL_DIR / ('018_' + p + '.sql'))]


def migrate(database: Path, dry_run: bool = False) -> dict:
    from research_store import ResearchStore
    if not Path(database).is_file():
        raise ValueError('018_EXISTING_DATABASE_REQUIRED')
    with writer(database) as path, sqlite3.connect(path, timeout=1) as c:
        c.execute('PRAGMA foreign_keys=ON')
        if c.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise ValueError('018_SCHEMA_VERSION_5_REQUIRED')
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or c.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('018_PRE_MIGRATION_INTEGRITY')
        fault('migration_prepare')
        c.execute('BEGIN IMMEDIATE')
        profiles, sql = migration_plan(c)
        definitions = {s[s.index('CREATE TRIGGER '):].split()[2]: s[s.index('CREATE TRIGGER '):].rstrip(';') for s in sql}
        existing = dict(c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        for name, definition in definitions.items():
            if name in existing and existing[name] != definition:
                raise ValueError('018_TRIGGER_CONFLICT:' + name)
        missing = [s for s in sql if s[s.index('CREATE TRIGGER '):].split()[2] not in existing]
        result = {'profiles': profiles, 'typed_present': 'typed' in profiles, 'idempotent': not missing,
            'definitions_sha256': digest(definitions), 'added_triggers': len(missing), 'dry_run': dry_run}
        if dry_run:
            c.rollback()
            return result
        for statement in missing:
            c.execute(statement)
            fault('migration_transaction')
        if missing:
            reader = ResearchStore.__new__(ResearchStore)
            reader.path = path
            reader._audit(c, 'deploy018_guards_installed', result)
        fault('migration_before_commit')
        c.commit()
        fault('migration_after_commit')
        return result
