"""Isolated append-only content-bound certificates; never migrates the research ledger."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time

from .ast import canonical, digest


class Store:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as c:
            existing = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if existing and 'dav_records' not in {r[0] for r in existing}:
                raise ValueError('DAV_REQUIRES_ITS_OWN_DATABASE')
            if c.execute('PRAGMA user_version').fetchone()[0] > 1:
                raise ValueError('DAV_DATABASE_SCHEMA_NEWER_THAN_SERVER')
            c.executescript('''
              CREATE TABLE IF NOT EXISTS dav_records(
                id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL,
                request_key TEXT NOT NULL, request_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_ns INTEGER NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
                UNIQUE(project,request_key));
              CREATE TRIGGER IF NOT EXISTS dav_no_update BEFORE UPDATE ON dav_records
                BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
              CREATE TRIGGER IF NOT EXISTS dav_no_delete BEFORE DELETE ON dav_records
                BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
              CREATE INDEX IF NOT EXISTS dav_kind_project_id ON dav_records(kind,project,id);
              CREATE INDEX IF NOT EXISTS dav_project_kind_case_id ON dav_records(
                project,kind,json_extract(payload_json,'$.case_id'),id);
              PRAGMA user_version=1;
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        # Keep bounded JSON-history sorts inside the service memory limit. The
        # read allowlist intentionally does not grant arbitrary /tmp access.
        c.execute('PRAGMA temp_store=MEMORY')
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def decode(row):
        if not row:
            return None
        data = dict(row)
        entry = data.pop('entry_hash')
        if digest(data) != entry:
            raise ValueError('DAV_RECORD_HASH_MISMATCH')
        return {**dict(row), 'payload': json.loads(row['payload_json'])}

    def counterexample_links(self, project, registration_id):
        with self.connect() as c:
            rows = c.execute("SELECT * FROM dav_records WHERE project=? AND kind='evidence' ORDER BY id", (project,)).fetchall()
        out = []
        for row in rows:
            value = self.decode(row)
            p = value['payload']
            if p.get('status') == 'refuted' and p.get('evidence_provenance', {}).get('registration_id') == registration_id:
                out.append({'evidence_id': value['id'], 'law_fingerprint': p.get('law_fingerprint'),
                            'counterexample_state': p['counterexample']['state']})
        return out

    def repeated(self, project, key, request):
        with self.connect() as c:
            row = c.execute('SELECT * FROM dav_records WHERE project=? AND request_key=?', (project, key)).fetchone()
        if row and row['request_hash'] != digest(request):
            raise ValueError('REQUEST_KEY_CONTENT_CONFLICT')
        return self.decode(row)

    def append(self, project, kind, key, request, payload):
        if not isinstance(key, str) or not key.strip() or len(key) > 200:
            raise ValueError('EXPLICIT_REQUEST_KEY_REQUIRED')
        raw = canonical(payload)
        if len(raw.encode()) > 2000000:
            raise ValueError('EVIDENCE_OUTPUT_LIMIT')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM dav_records WHERE project=? AND request_key=?', (project, key)).fetchone()
            if old:
                if old['request_hash'] != digest(request):
                    raise ValueError('REQUEST_KEY_CONTENT_CONFLICT')
                return self.decode(old)
            if c.execute('SELECT count(*) FROM dav_records').fetchone()[0] >= 20000:
                raise ValueError('DAV_DATABASE_RECORD_LIMIT')
            used = c.execute('SELECT coalesce(sum(length(CAST(payload_json AS BLOB))),0) FROM dav_records').fetchone()[0]
            if used + len(raw.encode()) > 64 * 1024 * 1024:
                raise ValueError('DAV_DATABASE_PAYLOAD_BYTE_LIMIT')
            last = c.execute('SELECT id,entry_hash FROM dav_records ORDER BY id DESC LIMIT 1').fetchone()
            row = {'id': last['id'] + 1 if last else 1, 'project': project, 'kind': kind, 'request_key': key,
                   'request_hash': digest(request), 'payload_json': raw, 'created_ns': time.time_ns(),
                   'previous_hash': last['entry_hash'] if last else '0' * 64}
            row['entry_hash'] = digest(row)
            c.execute('INSERT INTO dav_records VALUES(:id,:project,:kind,:request_key,:request_hash,:payload_json,:created_ns,:previous_hash,:entry_hash)', row)
            return self.decode(row)

    def get(self, project, ident):
        with self.connect() as c:
            row = c.execute('SELECT * FROM dav_records WHERE project=? AND id=?', (project, ident)).fetchone()
        if not row:
            raise ValueError('MISSING_OR_FOREIGN_DAV_RECORD')
        return self.decode(row)

    def integrity(self):
        previous = '0' * 64
        with self.connect() as c:
            integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
            rows = c.execute('SELECT * FROM dav_records ORDER BY id').fetchall()
        for row in rows:
            data = dict(row)
            entry = data.pop('entry_hash')
            if data['previous_hash'] != previous or digest(data) != entry:
                return {'ok': False, 'failed_id': row['id'], 'sqlite_integrity': integrity}
            previous = entry
        return {'ok': integrity == 'ok', 'rows': len(rows), 'head_hash': previous, 'sqlite_integrity': integrity}
