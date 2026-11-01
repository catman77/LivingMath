"""Append-only proposal, audit and permission records; no mathematical operations."""
from dataclasses import asdict
import json
import re
import time

from frontier import ResearchMoveFingerprint, canonical, fingerprint_hash, text, string_list


MOVE_STATUSES = {'PROPOSED', 'AUDITED', 'EXPERIMENT_ALLOWED', 'REJECTED',
                 'REQUIRES_REVIEW', 'COMPLETED', 'ABANDONED'}
HARD_FAILURES = {'TRANSFORMATION_CONTRACT_MISMATCH', 'OBSOLETE_FRONTIER',
                 'UNPROVEN_SEMANTIC_PRESERVATION', 'MISSING_TRANSFORMATION_CONTRACT'}
AUDIT_FIELDS = ('active_frontier_id', 'parent_event_ids', 'proposed_operation',
                'source_representation', 'target_representation', 'preserved_properties',
                'claimed_new_distinction', 'verification_plan', 'evidence_refs',
                'transformation_contract_id', 'evidence_roles')
RESULT_OUTCOMES = {'SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR'}


def experiment_result(value):
    if not isinstance(value, dict) or not value or set(value)-{'outcome','summary','data'}:
        raise ValueError('result must be a structured outcome, summary and optional data object')
    if not isinstance(value.get('outcome'),str) or value['outcome'] not in RESULT_OUTCOMES:
        raise ValueError('result.outcome must be SUCCESS, FAILURE, INCONCLUSIVE or ERROR')
    summary = text(value.get('summary'), 'result.summary')
    data = value.get('data', {})
    if not isinstance(data, dict): raise ValueError('result.data must be an object')
    result = {'outcome':value['outcome'], 'summary':summary, 'data':data}
    if len(canonical(result))>20000: raise ValueError('result is too large')
    return result
SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS research_move_bindings(
 move_id INTEGER PRIMARY KEY REFERENCES research_moves(id), scope TEXT NOT NULL,
 frontier_id INTEGER REFERENCES research_obligations(id), frontier_version INTEGER NOT NULL,
 identity_hash TEXT NOT NULL, request_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_move_keys(
 identity_hash TEXT PRIMARY KEY, move_id INTEGER NOT NULL REFERENCES research_moves(id));
CREATE TABLE IF NOT EXISTS research_move_request_keys(
 project TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 move_id INTEGER NOT NULL REFERENCES research_moves(id), PRIMARY KEY(project,request_key));
CREATE TABLE IF NOT EXISTS research_move_audits(
 id INTEGER PRIMARY KEY AUTOINCREMENT, move_id INTEGER NOT NULL REFERENCES research_moves(id),
 frontier_versions_json TEXT NOT NULL, report_json TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS research_move_status_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT, move_id INTEGER NOT NULL REFERENCES research_moves(id),
 sequence INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN
 ('PROPOSED','AUDITED','EXPERIMENT_ALLOWED','REJECTED','REQUIRES_REVIEW','COMPLETED','ABANDONED')),
 reason TEXT NOT NULL, audit_id INTEGER REFERENCES research_move_audits(id),
 decision_json TEXT NOT NULL, request_key TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(move_id,sequence));
CREATE INDEX IF NOT EXISTS move_history_order ON research_move_status_history(move_id,sequence);
'''
for _table in ('research_moves', 'research_move_bindings', 'research_move_keys',
               'research_move_request_keys', 'research_move_audits', 'research_move_status_history'):
    for _action in ('UPDATE', 'DELETE'):
        SCHEMA_SQL += f'''CREATE TRIGGER IF NOT EXISTS {_table}_no_{_action.lower()}
 BEFORE {_action} ON {_table} BEGIN
 SELECT RAISE(ABORT,'research move records are append-only'); END;\n'''


class ResearchMoveLifecycle:
    def __init__(self, store):
        self.store = store

    def _row(self, connection, project, move_id):
        row = connection.execute('SELECT * FROM research_moves WHERE id=?', (move_id,)).fetchone()
        if row is None or row['project'] != project:
            raise ValueError('research move missing or belongs to another project')
        return row

    def _latest(self, connection, move_id):
        row = connection.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence DESC LIMIT 1',
                                 (move_id,)).fetchone()
        if row is None:
            raise ValueError('move has no lifecycle record; explicit migration is required')
        return row

    def _append(self, connection, move_id, status, reason, audit_id=None, decision=None, request_key=''):
        if status not in MOVE_STATUSES:
            raise ValueError('invalid move lifecycle status')
        sequence = connection.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM research_move_status_history WHERE move_id=?',
                                      (move_id,)).fetchone()[0]
        decision = decision or {'allowed': False}
        now = int(time.time())
        cursor = connection.execute('''INSERT INTO research_move_status_history
            (move_id,sequence,status,reason,audit_id,decision_json,request_key,created_at) VALUES (?,?,?,?,?,?,?,?)''',
            (move_id, sequence, status, reason, audit_id, canonical(decision), request_key, now))
        self.store._audit(connection, 'research_move_status_changed',
            {'move_id': move_id, 'sequence': sequence, 'status': status, 'reason': reason,
             'audit_id': audit_id, 'decision_sha256': fingerprint_hash(decision)})
        return cursor.lastrowid

    @staticmethod
    def _request_key(value):
        key = text(value, 'request_key')
        if len(key) > 128:
            raise ValueError('request_key must have at most 128 characters')
        return key

    def _repeat(self, connection, project, request_key, digest):
        prior = connection.execute('SELECT * FROM research_move_request_keys WHERE project=? AND request_key=?',
                                   (project, request_key)).fetchone()
        if prior and prior['request_hash'] != digest:
            raise ValueError('request key reused for a different lifecycle request')
        return prior['move_id'] if prior else None

    def _bind_request(self, connection, project, key, digest, move_id):
        connection.execute('INSERT INTO research_move_request_keys VALUES (?,?,?,?)',
                           (project, key, digest, move_id))

    def _versions(self, connection, move):
        ids = [move['active_frontier_id']] if move.get('active_frontier_id') else []
        contract_id = move.get('transformation_contract_id')
        if contract_id is not None:
            contract = connection.execute('SELECT payload_json FROM transformation_contracts WHERE id=?', (contract_id,)).fetchone()
            if contract:
                ids.extend(json.loads(contract['payload_json'])['obligation_ids'])
        return {str(i): self.store.frontier._obligation(connection, i)['version'] for i in sorted(set(ids))}

    def _current_versions(self, connection, versions):
        return all(self.store.frontier._obligation(connection, int(i))['version'] == version
                   for i, version in versions.items())

    def _view(self, connection, row, idempotent=False):
        payload = json.loads(row['payload_json'])
        history = []
        for item in connection.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence', (row['id'],)):
            history.append({**dict(item), 'decision': json.loads(item['decision_json'])})
            del history[-1]['decision_json']
        audits = []
        for item in connection.execute('SELECT * FROM research_move_audits WHERE move_id=? ORDER BY id', (row['id'],)):
            audits.append({'id': item['id'], 'frontier_versions': json.loads(item['frontier_versions_json']),
                           'report': json.loads(item['report_json']), 'created_at': item['created_at']})
        if not history:
            raise ValueError('move has no lifecycle history')
        latest = history[-1]
        latest_audit = audits[-1] if audits else None
        versions = latest_audit['frontier_versions'] if latest_audit else {}
        versions_current = bool(versions) and self._current_versions(connection, versions)
        active = self.store.frontier._obligation(connection, payload['active_frontier_id']) if payload.get('active_frontier_id') else None
        evidence_current = self.store.evidence_reviews.matches_report(connection,row['project'],payload,
                                                                      latest_audit['report'] if latest_audit else None)
        allowed = (latest['status'] == 'EXPERIMENT_ALLOWED' and versions_current
                   and evidence_current
                   and active is not None and active['status'] in {'OPEN', 'TESTING'}
                   and latest['decision'].get('allowed') is True)
        permission = {'allowed': bool(allowed), 'operation': 'bounded_experiment' if allowed else None,
                      'scope': latest['decision'].get('scope') if allowed else None,
                      'frontier_versions': versions, 'needs_reaudit': not versions_current or not evidence_current,
                      'transformation_allowed': False, 'proof_allowed': False,
                      'reason': 'Explicit current scoped experiment grant.' if allowed else latest['reason']}
        completion = None
        if latest['status']=='COMPLETED':
            completion = {'legacy':not bool(latest['decision'].get('result')),
                          'result':latest['decision'].get('result'), 'proof_status':'unverified'}
        return {**payload, 'id': row['id'], 'project': row['project'], 'status': latest['status'], 'completion':completion,
                'history': history, 'audits': audits, 'audit': latest_audit['report'] if latest_audit else None,
                'execution_permission': permission, 'proof_status': 'unverified', 'idempotent': idempotent}

    def inspect(self, project, move_id):
        with self.store._connect() as connection:
            return self._view(connection, self._row(connection, project, move_id))

    def _save_audit(self, connection, row, report, versions, key, legacy=False):
        cursor = connection.execute('INSERT INTO research_move_audits(move_id,frontier_versions_json,report_json,created_at) VALUES (?,?,?,?)',
                                    (row['id'], canonical(versions), canonical(report), int(time.time())))
        audit_id = cursor.lastrowid
        self.store._audit(connection, 'research_move_audited',
            {'move_id': row['id'], 'audit_id': audit_id, 'report_sha256': fingerprint_hash(report),
             'frontier_versions': versions, 'legacy_import': legacy})
        self._append(connection, row['id'], 'AUDITED', 'Audit recorded independently of execution authorization.', audit_id, request_key=key)
        codes = set(report.get('warnings', [])) | {item['code'] for item in report.get('findings', [])}
        if codes & HARD_FAILURES:
            self._append(connection, row['id'], 'REJECTED', ', '.join(sorted(codes & HARD_FAILURES)), audit_id, request_key=key)
        elif legacy or report.get('verdict') != 'EXPERIMENT_ALLOWED':
            self._append(connection, row['id'], 'REQUIRES_REVIEW',
                         'Legacy permission was not established.' if legacy else 'Semantic review or missing evidence.', audit_id, request_key=key)

    def _assess(self, connection, row, key):
        payload = json.loads(row['payload_json'])
        fields = {field: payload[field] for field in AUDIT_FIELDS if field in payload}
        report = self.store.frontier.audit(row['project'], payload.get('proposal', ''),
                                          _exclude_move_id=row['id'], **fields)
        active = self.store.frontier._obligation(connection, payload['active_frontier_id']) if payload.get('active_frontier_id') else None
        binding = connection.execute('SELECT * FROM research_move_bindings WHERE move_id=?', (row['id'],)).fetchone()
        if not active or binding['scope'] != active['scope']:
            reason = 'The requested experiment scope differs from the active obligation scope.'
            report['findings'].append({'code': 'EXPERIMENT_SCOPE_REQUIRES_REVIEW', 'reason': reason,
                'constraint': reason, 'source_event_ids': payload.get('parent_event_ids', []),
                'reopen_conditions': ['Review the changed applicability scope explicitly.'], 'missing_data': []})
            report['warnings'] = list(dict.fromkeys(report['warnings'] + ['EXPERIMENT_SCOPE_REQUIRES_REVIEW']))
            report.update(verdict='REQUIRES_SEMANTIC_REVIEW', semantic_review_required=True, permitted_use='review_or_reopen')
        versions = self._versions(connection, payload)
        self._save_audit(connection, row, report, versions, key)

    @staticmethod
    def _context(move, fingerprint, scope, frontier_id, version):
        # Cosmetic names are not new claims. Representations, intent, evidence,
        # and preservation requirements remain part of the immutable request.
        context = {k: v for k, v in move.items() if k not in
                   {'proposal', 'proposed_operation', 'scope', 'active_frontier_id', 'active_frontier_version'}}
        operation = {k: v for k, v in move['proposed_operation'].items() if k not in
                     {'mechanism', 'display_name', 'name', 'title', 'label', 'premises', 'mathematical_properties',
                      'required_evidence', 'testable_consequence'}}
        return fingerprint_hash({'context': context, 'operation': operation, 'fingerprint': fingerprint,
                                 'scope': scope, 'frontier_id': frontier_id, 'frontier_version': version})

    def record(self, project, move, request_key):
        key = self._request_key(request_key)
        if not isinstance(move, dict) or set(move) - set(AUDIT_FIELDS + ('proposal', 'scope', 'active_frontier_version')):
            raise ValueError('unsupported research move fields')
        scope = text(move.get('scope'), 'scope')
        version = move.get('active_frontier_version')
        if type(version) is not int or version < 1:
            raise ValueError('active_frontier_version must be a positive integer')
        fp = ResearchMoveFingerprint.build(move.get('proposed_operation', {}))
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            active = self.store.frontier._obligation(connection, move.get('active_frontier_id'))
            if active['project'] != project:
                raise ValueError('active frontier belongs to another project')
            self.store.frontier._events(connection, project, move.get('parent_event_ids', []))
            self.store.frontier._move_refs(connection, project, move)
            identity = fingerprint_hash({'project': project, 'fingerprint': fp.digest, 'scope': scope,
                                         'frontier_id': active['id'], 'frontier_version': version})
            digest = self._context(move, fp.digest, scope, active['id'], version)
            repeated = self._repeat(connection, project, key, digest)
            if repeated is not None:
                return self._view(connection, self._row(connection, project, repeated), True)
            prior = connection.execute('SELECT move_id FROM research_move_keys WHERE identity_hash=?', (identity,)).fetchone()
            if prior:
                binding = connection.execute('SELECT request_hash FROM research_move_bindings WHERE move_id=?', (prior['move_id'],)).fetchone()
                if binding['request_hash'] != digest:
                    raise ValueError('structural identity already exists with different substantive input; revise the claim or frontier version')
                self._bind_request(connection, project, key, digest, prior['move_id'])
                self.store._audit(connection, 'research_move_request_bound', {'move_id': prior['move_id'], 'request_hash': digest})
                return self._view(connection, self._row(connection, project, prior['move_id']), True)
            if active['version'] != version:
                raise ValueError('stale active frontier version')
            payload = {**move, 'scope': scope, 'fingerprint': asdict(fp)}
            cursor = connection.execute('INSERT INTO research_moves(project,fingerprint,payload_json,created_at) VALUES (?,?,?,?)',
                                        (project, fp.digest, canonical(payload), int(time.time())))
            move_id = cursor.lastrowid
            connection.execute('INSERT INTO research_move_bindings VALUES (?,?,?,?,?,?)',
                               (move_id, scope, active['id'], version, identity, digest))
            connection.execute('INSERT INTO research_move_keys VALUES (?,?)', (identity, move_id))
            self._bind_request(connection, project, key, digest, move_id)
            self._append(connection, move_id, 'PROPOSED', 'Proposal recorded; execution is not authorized.', request_key=key)
            row = self._row(connection, project, move_id)
            self._assess(connection, row, key)
            return self._view(connection, row)

    def audit(self, project, move_id, request_key):
        key = self._request_key(request_key)
        digest = fingerprint_hash({'action': 'audit', 'move_id': move_id})
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._row(connection, project, move_id)
            if self._repeat(connection, project, key, digest) is not None:
                return self._view(connection, row, True)
            if self._latest(connection, move_id)['status'] in {'COMPLETED', 'ABANDONED'}:
                raise ValueError('terminal move cannot be audited or reactivated')
            self._assess(connection, row, key)
            self._bind_request(connection, project, key, digest, move_id)
            return self._view(connection, row)

    def transition(self, project, move_id, action, request_key, evidence_refs=None, reason='', result=None):
        if action not in {'activate_experiment', 'complete', 'abandon'}:
            raise ValueError('allowed actions: activate_experiment, complete, abandon; no verified transition')
        key = self._request_key(request_key)
        refs = string_list(evidence_refs or [], 'evidence_refs')
        reason = text(reason, 'reason', allow_empty=True)
        request = {'action':action,'move_id':move_id,'evidence_refs':refs,'reason':reason}
        if result is not None:
            if action!='complete': raise ValueError('result is only valid for complete')
            result = experiment_result(result)
            request['result']=result
        digest = fingerprint_hash(request)
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._row(connection, project, move_id)
            self.store.frontier._evidence_refs(connection, project, refs)
            if self._repeat(connection, project, key, digest) is not None:
                return self._view(connection, row, True)
            view = self._view(connection, row)
            current = view['status']
            audit_id = view['audits'][-1]['id'] if view['audits'] else None
            if action == 'activate_experiment':
                if current != 'AUDITED' or not view['audit'] or view['audit']['verdict'] != 'EXPERIMENT_ALLOWED':
                    raise ValueError('activation requires a new successful audit; current status is ' + current)
                versions = view['audits'][-1]['frontier_versions']
                active = self.store.frontier._obligation(connection, view['active_frontier_id'])
                operation = view.get('proposed_operation', {})
                if (not versions or not self._current_versions(connection, versions) or view['execution_permission']['needs_reaudit']
                        or active['status'] not in {'OPEN', 'TESTING'}
                        or operation.get('intent') != 'experiment' or operation.get('proof_claim')
                        or view['source_representation'] != view['target_representation']
                        or set(view['audit']['warnings']) & HARD_FAILURES):
                    raise ValueError('activation needs re-audit of the current scoped experiment')
                decision = {'allowed': True, 'operation': 'bounded_experiment', 'scope': view['scope'],
                            'frontier_versions': versions, 'transformation_allowed': False, 'proof_allowed': False}
                self._append(connection, move_id, 'EXPERIMENT_ALLOWED', 'Explicit bounded experiment activation.', audit_id, decision, key)
            elif action == 'complete':
                if current != 'EXPERIMENT_ALLOWED' or not view['execution_permission']['allowed']:
                    raise ValueError('completion requires a current experiment permission')
                result = experiment_result(result)
                valid_refs = [int(m[1]) for ref in refs if (m := re.fullmatch(r'event:([1-9]\d*)', ref))]
                if not valid_refs or not reason:
                    raise ValueError('completion requires reason and an existing project-local event evidence_ref')
                self.store.frontier._events(connection,project,valid_refs)
                self._append(connection, move_id, 'COMPLETED', reason, audit_id,
                             {'allowed': False, 'result':result, 'evidence_refs': refs, 'completion_claim': True,
                              'completion_contract':'v0.4.2','proof_status': 'unverified'}, key)
            else:
                if current in {'COMPLETED', 'ABANDONED'}:
                    raise ValueError('terminal move cannot be changed')
                self._append(connection, move_id, 'ABANDONED', reason or 'Proposal withdrawn.', audit_id, request_key=key)
            self._bind_request(connection, project, key, digest, move_id)
            return self._view(connection, row)

    def invalidate(self, connection, obligation_id, new_version):
        for row in connection.execute('SELECT * FROM research_moves ORDER BY id').fetchall():
            latest = self._latest(connection, row['id'])
            if latest['status'] not in {'AUDITED', 'EXPERIMENT_ALLOWED'}:
                continue
            audit = connection.execute('SELECT frontier_versions_json FROM research_move_audits WHERE id=?', (latest['audit_id'],)).fetchone()
            versions = json.loads(audit[0]) if audit else {}
            if str(obligation_id) in versions and versions[str(obligation_id)] != new_version:
                self._append(connection, row['id'], 'REQUIRES_REVIEW',
                    f'FRONTIER_VERSION_CHANGED: obligation {obligation_id} is now version {new_version}; re-audit required.', latest['audit_id'])

    def import_legacy(self, connection, row):
        """Add conservative lifecycle metadata without rewriting the original row."""
        if connection.execute('SELECT 1 FROM research_move_bindings WHERE move_id=?', (row['id'],)).fetchone():
            return
        payload = json.loads(row['payload_json'])
        active_id = payload.get('active_frontier_id')
        active = self.store.frontier._obligation(connection, active_id) if active_id else None
        scope = payload.get('scope') or (active['scope'] if active else 'Legacy scope not recorded.')
        identity = fingerprint_hash({'legacy_move_id': row['id'], 'project': row['project']})
        request_hash = fingerprint_hash(payload)
        if active and isinstance(payload.get('proposed_operation'), dict):
            # A current identity can deduplicate a legacy proposal, but version
            # zero below still means no historical audit/permission is known.
            identity = fingerprint_hash({'project': row['project'], 'fingerprint': row['fingerprint'],
                'scope': scope, 'frontier_id': active_id, 'frontier_version': active['version']})
            original = {key: value for key, value in payload.items() if key in AUDIT_FIELDS + ('proposal',)}
            request_hash = self._context(original, row['fingerprint'], scope, active_id, active['version'])
        connection.execute('INSERT INTO research_move_bindings VALUES (?,?,?,?,?,?)',
                           (row['id'], scope, active_id, 0, identity, request_hash))
        connection.execute('INSERT OR IGNORE INTO research_move_keys VALUES (?,?)', (identity, row['id']))
        self._append(connection, row['id'], 'PROPOSED', 'Migration/import of existing proposal; no historical permission inferred.')
        if payload.get('audit'):
            self._save_audit(connection, row, payload['audit'], {}, '', legacy=True)
        else:
            self._append(connection, row['id'], 'REQUIRES_REVIEW', 'Legacy record lacks a version-bound audit and execution grant.')
