"""Automatic intake from typed canonical events and an explicitly configured local inbox."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from davcore.ast import digest
from .contract import ResearchInput
from .artifact_contract import ArtifactInput


def decode_input(value):
    return ArtifactInput.model_validate(value) if value.get('format')=='livingmath-artifact/1' else ResearchInput.model_validate(value)


class Intake:
    def __init__(self, controller):
        self.controller = controller
        self.seen_files = set()
        self.file_cursor = 0

    @staticmethod
    def decode(raw):
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError('DUPLICATE_INPUT_KEY')
                out[key] = value
            return out
        return json.loads(raw, object_pairs_hook=pairs)

    def _error(self, project: str, identity: dict, error: Exception) -> None:
        self.controller.journal.append(project, 'automation_intake_error', 'auto-intake-error:' + digest(identity), identity,
            {'reason': str(error), 'input_identity': identity, 'status': 'REQUIRES_REVIEW', 'raw_input_executed': False})

    def poll(self) -> None:
        if self.controller.canonical is not None:
            self._canonical(Path(self.controller.canonical))
        if self.controller.inbox is not None:
            self._inbox(Path(self.controller.inbox))

    def _canonical(self, path: Path) -> None:
        markers = self.controller.journal.rows(('automation_canonical_cursor',))
        cursor = max((r['payload']['last_event_id'] for r in markers if r['payload']['source_database'] == str(path)), default=0)
        with sqlite3.connect(path.resolve(strict=True).as_uri() + '?mode=ro', uri=True) as c:
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA query_only=ON')
            rows = c.execute('SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100', (cursor,)).fetchall()
        for row in rows:
            identity = {'source_database': str(path), 'event_id': row['id'], 'event_sha256': digest(dict(row))}
            try:
                value = self.decode(row['content'])
                if not isinstance(value, dict) or 'automation' not in value:
                    continue
                packet = decode_input(value['automation'])
                self.controller.ingest(row['project'], packet, 'canonical:' + digest(identity), provenance={
                    'kind': 'CANONICAL_EVENT_DECLARATION', **identity, 'kind_in_source': row['kind'],
                    'status_in_source': row['status'], 'source_not_independently_verified': True})
            except (ValueError, TypeError, KeyError) as exc:
                # Ordinary non-JSON legacy content is not an automation request.
                if isinstance(row['content'], str) and '"automation"' in row['content']:
                    self._error(row['project'], identity, exc)
        if rows:
            identity = {'source_database': str(path), 'last_event_id': rows[-1]['id']}
            self.controller.journal.append('_automation_system', 'automation_canonical_cursor',
                'auto-canonical-cursor:' + digest(identity), identity, identity)

    def _inbox(self, path: Path) -> None:
        root = path.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('AUTOMATION_INBOX_MUST_BE_A_DIRECTORY')
        files = sorted(root.glob('*.json'))
        if not files:
            return
        start = self.file_cursor % len(files)
        batch = [files[(start + i) % len(files)] for i in range(min(128, len(files)))]
        self.file_cursor = (start + len(batch)) % len(files)
        for source in batch:
            try:
                fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
            except OSError:
                continue
            with os.fdopen(fd, 'rb') as stream:
                st = os.fstat(stream.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_size > 256000:
                    continue
                raw = stream.read(256001)
            if len(raw) > 256000:
                continue
            token = (str(source), hashlib.sha256(raw).hexdigest())
            if token in self.seen_files:
                continue
            identity = {'inbox_file': source.name, 'sha256': token[1]}
            try:
                value = self.decode(raw)
                if set(value) != {'project', 'input'}:
                    raise ValueError('INBOX_REQUIRES_ONLY_PROJECT_AND_INPUT')
                project = value['project']
                self.controller.service.project(project)
                packet = decode_input(value['input'])
                self.controller.ingest(project, packet, 'inbox:' + digest(identity), provenance={
                    'kind': 'OPERATOR_CONFIGURED_LOCAL_INBOX_DECLARATION', **identity})
            except (ValueError, TypeError, KeyError) as exc:
                self._error('_automation_system', identity, exc)
            self.seen_files.add(token)
