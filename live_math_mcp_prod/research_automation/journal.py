"""Durable append-only orchestration in the existing isolated DAV journal."""
from contextlib import contextmanager
import fcntl
import os

from davcore.ast import digest


class Journal:
    def __init__(self, service):
        self.service = service
        self.store = service.store

    def rows(self, kinds: tuple[str, ...], project: str | None = None, *, case_id: int | None = None,
             after_id: int = 0, limit: int | None = None) -> list[dict]:
        query = 'SELECT * FROM dav_records WHERE kind IN (' + ','.join('?' for _ in kinds) + ')'
        params: list[str | int] = list(kinds)
        if project is not None:
            query += ' AND project=?'
            params.append(project)
        if case_id is not None:
            query += " AND json_extract(payload_json,'$.case_id')=?"
            params.append(case_id)
        if after_id:
            query += ' AND id>?'
            params.append(after_id)
        query += ' ORDER BY id'
        if limit is not None:
            if not 1<=limit<=200:raise ValueError('JOURNAL_PAGE_BOUND')
            query+=' LIMIT ?';params.append(limit)
        with self.store.connect() as c:
            return [self.store.decode(row) for row in c.execute(query, params)]

    @contextmanager
    def leader(self):
        path = str(self.store.path) + '.automation.lock'
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        locked = False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                pass
            yield locked
        finally:
            if locked:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def append(self, project: str, kind: str, key: str, identity: dict, payload: dict) -> dict:
        return self.store.append(project, kind, key, identity, {
            **payload, 'proof_status': 'unverified', 'execution_permission': {'allowed': False}})

    def create(self, project: str, problem, sources: list[int], binding: str) -> dict:
        structural = problem.structural()
        fp = digest({'project': project, 'problem': structural})
        row = self.append(project, 'automation_case', 'auto-case:' + fp, {'fingerprint': fp},
                          {'problem': structural, 'title': problem.title, 'fingerprint': fp, 'source_record_ids': sources})
        if not self.steps(project, row['id']):
            self.step(row, None, 'QUEUED', {'generation': 1, 'coordinator_binding': binding})
        return row

    def steps(self, project: str, case_id: int) -> list[dict]:
        return self.rows(('automation_step',), project, case_id=case_id)

    def controls(self, project: str, case_id: int) -> list[dict]:
        return self.rows(('automation_control',), project, case_id=case_id)

    def step(self, case: dict, previous: dict | None, status: str, state: dict, result: dict | None = None) -> dict:
        seq = previous['payload']['sequence'] + 1 if previous else 0
        identity = {'case_id': case['id'], 'previous_step_id': previous['id'] if previous else None, 'sequence': seq}
        return self.append(case['project'], 'automation_step', f"auto-step:{case['id']}:{seq}", identity,
            {**identity, 'status': status, 'state': state, 'result': result or {}, 'source_fingerprint': case['payload']['fingerprint']})

    def inputs(self, project: str, scope: str) -> list[dict]:
        return [r for r in self.rows(('automation_input',), project) if r['payload']['input']['scope'] == scope]

    def case(self, project: str, ident: int) -> dict:
        row = self.store.get(project, ident)
        if row['kind'] != 'automation_case':
            raise ValueError('EXPECTED_AUTOMATION_CASE')
        return row
