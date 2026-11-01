"""Versioned research records and conservative checks of declared research moves.

This module checks references, lifecycle state, and structured claims. It does
not decide mathematical equivalence or validate a proof from its description.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import re
import time
import unicodedata


OBLIGATION_STATUSES = {'OPEN', 'TESTING', 'RESOLVED', 'REFUTED', 'SUPERSEDED', 'BLOCKED'}
CLOSED_STATUSES = {'RESOLVED', 'REFUTED', 'SUPERSEDED'}
PRESERVATION_PROPERTIES = ('point_value', 'analytic_function', 'observables',
                           'source_provenance', 'rule_applicability')
SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS event_fingerprints(
 digest TEXT PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id));
CREATE TABLE IF NOT EXISTS research_obligations(
 id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
 current_version INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS research_obligation_versions(
 obligation_id INTEGER NOT NULL REFERENCES research_obligations(id),
 version INTEGER NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
 created_at INTEGER NOT NULL, PRIMARY KEY(obligation_id,version));
CREATE TRIGGER IF NOT EXISTS obligation_versions_no_update
 BEFORE UPDATE ON research_obligation_versions BEGIN
 SELECT RAISE(ABORT,'obligation versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS obligation_versions_no_delete
 BEFORE DELETE ON research_obligation_versions BEGIN
 SELECT RAISE(ABORT,'obligation versions are immutable'); END;
CREATE TABLE IF NOT EXISTS research_moves(
 id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
 fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS moves_project_fingerprint ON research_moves(project,fingerprint);
CREATE TABLE IF NOT EXISTS transformation_contracts(
 id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
 payload_json TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS frontier_constraints(
 id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
 obligation_id INTEGER REFERENCES research_obligations(id),
 kind TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS frontier_imports(
 import_key TEXT PRIMARY KEY, digest TEXT NOT NULL, summary_json TEXT NOT NULL);
'''


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, field, allow_empty=False):
    if not isinstance(value, str) or len(value) > 20000 or (not allow_empty and not value.strip()):
        raise ValueError(field + ': expected a non-empty string of at most 20000 characters')
    return value.strip()


def string_list(value, field):
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError(field + ': expected a list of at most 200 strings')
    return [text(item, field) for item in value]


ALIASES = {
    'x4': 'x4_arithmetic_source', 'x4 arithmetic source': 'x4_arithmetic_source',
    'x4/sigma_coord': 'x4_arithmetic_source',
    'длина маршрута': 'route_arclength', 'длина пути': 'route_arclength',
    'path length': 'route_arclength', 'route length': 'route_arclength',
    'global arclength': 'route_arclength', 'route arclength': 'route_arclength',
    'erase point loop': 'erase_point_loop', 'point loop erasure': 'erase_point_loop',
    'source address matching': 'theta_edge_address_match',
}


def normalize_claim(value):
    # Preserve mathematical case, operators, and formula structure. Only known
    # complete labels are aliases; this is not an equivalence solver or DSL.
    value = ' '.join(unicodedata.normalize('NFC', text(value, 'claim')).split())
    key = value.casefold().replace('_', ' ').replace('-', ' ')
    return ALIASES.get(key, value)


@dataclass(frozen=True)
class ResearchObligation:
    project: str
    statement: str
    scope: str
    source_event_ids: list
    evidence_refs: list
    status: str = 'OPEN'
    closure_reason: str = ''
    reopen_conditions: list | None = None
    version: int = 1
    reopen_reason: str = ''
    id: int | None = None
    proof_status: str = 'unverified'


@dataclass(frozen=True)
class ResearchMoveFingerprint:
    digest: str
    claims: dict
    complete: bool
    normalization_version: int = 1

    @classmethod
    def build(cls, operation):
        if not isinstance(operation, dict):
            raise ValueError('proposed_operation must be an object')
        claims = {}
        complete = True
        for field in ('premises', 'mathematical_properties', 'required_evidence'):
            values = string_list(operation.get(field, []), field)
            claims[field] = sorted(set(normalize_claim(value) for value in values))
            complete = complete and bool(values)
        consequence = operation.get('testable_consequence', '')
        claims['testable_consequence'] = normalize_claim(consequence) if consequence else ''
        complete = complete and bool(consequence)
        return cls(fingerprint_hash({'version': 1, 'claims': claims}), claims, bool(complete))


class ResearchFrontier:
    def __init__(self, store):
        self.store = store

    def _events(self, connection, project, ids):
        if not isinstance(ids, list) or len(ids) > 200 or any(type(i) is not int or i < 1 for i in ids):
            raise ValueError('source event IDs must be a list of positive integers')
        for event_id in set(ids):
            row = connection.execute('SELECT project FROM events WHERE id=?', (event_id,)).fetchone()
            if row is None or row['project'] != project:
                raise ValueError('source event missing or belongs to another project: ' + str(event_id))

    def _obligation(self, connection, obligation_id, version=None):
        root = connection.execute('SELECT * FROM research_obligations WHERE id=?', (obligation_id,)).fetchone()
        if root is None:
            raise ValueError('unknown research obligation')
        version = root['current_version'] if version is None else version
        row = connection.execute('SELECT payload_json FROM research_obligation_versions WHERE obligation_id=? AND version=?',
                                 (obligation_id, version)).fetchone()
        if row is None:
            raise ValueError('unknown research obligation version')
        return json.loads(row['payload_json'])

    def _evidence_refs(self, connection, project, refs):
        refs = string_list(refs, 'evidence_refs')
        ids = [int(match) for ref in refs for match in re.findall(r'(?<!\w)event:(\d+)(?=\D|$)', ref)]
        self._events(connection, project, ids)
        return refs

    def _move_refs(self, connection, project, value):
        if isinstance(value, dict):
            for key, entry in value.items():
                if key in {'evidence_refs', 'required_evidence'}:
                    self._evidence_refs(connection, project, entry)
                else:
                    self._move_refs(connection, project, entry)
        elif isinstance(value, list):
            for entry in value:
                self._move_refs(connection, project, entry)

    def _validate_obligation(self, connection, payload):
        ResearchObligation(**payload)
        if payload['status'] not in OBLIGATION_STATUSES:
            raise ValueError('invalid obligation status')
        for field in ('project', 'statement', 'scope'):
            payload[field] = text(payload[field], field)
        self._events(connection, payload['project'], payload['source_event_ids'])
        payload['evidence_refs'] = self._evidence_refs(connection, payload['project'], payload['evidence_refs'])
        payload['reopen_conditions'] = string_list(payload['reopen_conditions'], 'reopen_conditions')
        payload['closure_reason'] = text(payload['closure_reason'], 'closure_reason', allow_empty=True)
        if payload['status'] == 'BLOCKED' and not payload['closure_reason']:
            raise ValueError('blocking an obligation requires an explicit reason')
        if payload['status'] in CLOSED_STATUSES:
            if not payload['closure_reason'] or not payload['evidence_refs'] or not payload['source_event_ids']:
                raise ValueError('closing an obligation requires a reason, evidence references, and source events')
            if not payload['reopen_conditions']:
                raise ValueError('closing an obligation requires explicit reopen conditions')

    def _create(self, connection, project, statement, scope, source_event_ids, evidence_refs,
                status='OPEN', closure_reason='', reopen_conditions=None):
        payload = dict(project=project, statement=statement, scope=scope,
                       source_event_ids=source_event_ids, evidence_refs=evidence_refs,
                       status=status, closure_reason=closure_reason,
                       reopen_conditions=reopen_conditions or [], version=1, reopen_reason='', proof_status='unverified')
        self._validate_obligation(connection, payload)
        now = int(time.time())
        cursor = connection.execute('INSERT INTO research_obligations(project,current_version,created_at) VALUES (?,1,?)',
                                    (payload['project'], now))
        payload['id'] = cursor.lastrowid
        connection.execute('INSERT INTO research_obligation_versions VALUES (?,?,?,?,?)',
                           (payload['id'], 1, status, canonical(payload), now))
        self.store._audit(connection, 'obligation_created', {'id': payload['id'], 'version': 1,
                          'status': status, 'payload_sha256': fingerprint_hash(payload)})
        return payload

    def create(self, project, statement, scope, source_event_ids, evidence_refs=None,
               status='OPEN', closure_reason='', reopen_conditions=None):
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            return self._create(connection, project, statement, scope, source_event_ids,
                                evidence_refs or [], status, closure_reason, reopen_conditions)

    def update(self, obligation_id, expected_version, changes, reopen_reason=''):
        if not isinstance(changes, dict) or not changes:
            raise ValueError('changes must be a non-empty object')
        allowed = {'statement', 'scope', 'source_event_ids', 'evidence_refs', 'status',
                   'closure_reason', 'reopen_conditions'}
        if set(changes) - allowed:
            raise ValueError('unsupported obligation fields')
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            previous = self._obligation(connection, obligation_id)
            if previous['version'] != expected_version:
                raise ValueError('stale obligation version')
            payload = {**previous, **changes, 'version': expected_version + 1}
            reopening = previous['status'] in CLOSED_STATUSES and payload['status'] not in CLOSED_STATUSES
            if reopening:
                if payload['status'] != 'OPEN' or not text(reopen_reason, 'reopen_reason'):
                    raise ValueError('reopening requires OPEN status and an explicit reason')
                if not set(payload['source_event_ids']) - set(previous['source_event_ids']) and payload['evidence_refs'] == previous['evidence_refs']:
                    raise ValueError('reopening requires a new source event or new evidence reference')
                payload['reopen_reason'] = reopen_reason.strip()
                payload['closure_reason'] = ''
            elif reopen_reason:
                raise ValueError('reopen_reason is only valid when reopening a closed obligation')
            self._validate_obligation(connection, payload)
            connection.execute('INSERT INTO research_obligation_versions VALUES (?,?,?,?,?)',
                               (obligation_id, payload['version'], payload['status'], canonical(payload), int(time.time())))
            connection.execute('UPDATE research_obligations SET current_version=? WHERE id=?',
                               (payload['version'], obligation_id))
            self.store._audit(connection, 'obligation_reopened' if reopening else 'obligation_updated',
                              {'id': obligation_id, 'version': payload['version'],
                               'payload_sha256': fingerprint_hash(payload)})
            self.store.moves.invalidate(connection, obligation_id, payload['version'])
            return payload

    def history(self, obligation_id):
        with self.store._connect() as connection:
            self._obligation(connection, obligation_id)
            return [json.loads(row['payload_json']) for row in connection.execute(
                'SELECT payload_json FROM research_obligation_versions WHERE obligation_id=? ORDER BY version', (obligation_id,))]

    def inspect(self, project, include_closed=False):
        with self.store._connect() as connection:
            rows = connection.execute('SELECT id FROM research_obligations WHERE project=? ORDER BY id', (project,)).fetchall()
            obligations = [self._obligation(connection, row['id']) for row in rows]
            if not include_closed:
                obligations = [item for item in obligations if item['status'] not in CLOSED_STATUSES]
            constraints = [dict(json.loads(row['payload_json']), id=row['id'], kind=row['kind'],
                                obligation_id=row['obligation_id']) for row in connection.execute(
                'SELECT * FROM frontier_constraints WHERE project=? ORDER BY id', (project,))]
            contracts = [dict(json.loads(row['payload_json']), id=row['id']) for row in connection.execute(
                'SELECT * FROM transformation_contracts WHERE project=? ORDER BY id', (project,))]
        return {'project': project, 'obligations': obligations, 'constraints': constraints,
                'transformation_contracts': contracts,
                'evidence_reviews':self.store.evidence_reviews.inspect(project),
                'epistemic_status': 'Research state and review claims; not mathematical verification.'}

    def _record_move(self, connection, project, move):
        text(project, 'project')
        self._events(connection, project, move.get('parent_event_ids', []))
        fp = ResearchMoveFingerprint.build(move.get('proposed_operation', {}))
        payload = {**move, 'fingerprint': asdict(fp)}
        cursor = connection.execute('INSERT INTO research_moves(project,fingerprint,payload_json,created_at) VALUES (?,?,?,?)',
                                    (project, fp.digest, canonical(payload), int(time.time())))
        self.store._audit(connection, 'research_move_recorded', {'id': cursor.lastrowid, 'project': project,
                          'payload_sha256': fingerprint_hash(payload)})
        self.store.moves.import_legacy(connection, connection.execute(
            'SELECT * FROM research_moves WHERE id=?', (cursor.lastrowid,)).fetchone())
        return {'id': cursor.lastrowid, **payload}

    def record_move(self, project, move, request_key):
        return self.store.moves.record(project, move, request_key)

    def transformation_contract(self, project, source, operation, result, preservation, source_event_ids):
        for field, value in [('source', source), ('result', result)]:
            text(value, field)
        if not isinstance(operation, dict) or not operation:
            raise ValueError('operation must be a non-empty object')
        if not isinstance(preservation, dict) or set(preservation) != set(PRESERVATION_PROPERTIES):
            raise ValueError('preservation must declare all five preservation properties independently')
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._events(connection, project, source_event_ids)
            obligations = []
            for prop in PRESERVATION_PROPERTIES:
                entry = preservation[prop]
                if not isinstance(entry, dict) or not entry.get('statement'):
                    raise ValueError('each preservation property requires a statement')
                obligations.append(self._create(connection, project, entry['statement'], prop,
                                   source_event_ids, entry.get('evidence_refs', [])))
            payload = {'source': source, 'operation': operation, 'result': result,
                       'preservation': preservation, 'obligation_ids': [item['id'] for item in obligations],
                       'source_event_ids': source_event_ids, 'verification_status': 'UNVERIFIED'}
            cursor = connection.execute('INSERT INTO transformation_contracts(project,payload_json,created_at) VALUES (?,?,?)',
                                        (project, canonical(payload), int(time.time())))
            self.store._audit(connection, 'transformation_contract_recorded',
                              {'id': cursor.lastrowid, 'payload_sha256': fingerprint_hash(payload)})
            return {'id': cursor.lastrowid, **payload}

    def import_history(self, blueprint, operator):
        """Explicit operator import of scoped claims extracted from source events."""
        text(operator, 'operator')
        digest = fingerprint_hash(blueprint)
        project = blueprint['project']
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            prior = connection.execute('SELECT * FROM frontier_imports WHERE import_key=?', (blueprint['import_key'],)).fetchone()
            if prior:
                if prior['digest'] != digest:
                    raise ValueError('history import key reused with a different blueprint')
                return json.loads(prior['summary_json'])
            for source in blueprint['sources']:
                row = connection.execute('SELECT * FROM events WHERE id=?', (source['id'],)).fetchone()
                if row is None or row['project'] != project or fingerprint_hash(dict(row)) != source['sha256']:
                    raise ValueError('history import source hash mismatch: ' + str(source['id']))
            ids = {}
            for entry in blueprint['obligations']:
                entry = dict(entry)
                key = entry.pop('key')
                ids[key] = self._create(connection, project=project, **entry)['id']
            for entry in blueprint['constraints']:
                payload = dict(entry)
                kind = payload.pop('kind')
                obligation_id = ids[payload.pop('obligation_key')]
                self._events(connection, project, payload['source_event_ids'])
                if kind not in {'obsolete_mechanism', 'preservation_required', 'allowed_experiment'}:
                    raise ValueError('unsupported history constraint kind')
                connection.execute('INSERT INTO frontier_constraints(project,obligation_id,kind,payload_json) VALUES (?,?,?,?)',
                                   (project, obligation_id, kind, canonical(payload)))
            for move in blueprint.get('moves', []):
                self._record_move(connection, project, move)
            summary = {'import_key': blueprint['import_key'], 'project': project, 'obligation_ids': ids,
                       'source_event_ids': [row['id'] for row in blueprint['sources']], 'operator': operator,
                       'epistemic_status': 'Scoped history claims; no mathematical truth inferred.'}
            connection.execute('INSERT INTO frontier_imports VALUES (?,?,?)',
                               (blueprint['import_key'], digest, canonical(summary)))
            self.store._audit(connection, 'research_history_imported',
                              {'import_key': blueprint['import_key'], 'blueprint_sha256': digest, 'operator': operator})
            return summary

    def audit(self, project, proposal='', evidence='', **move):
        findings = []
        def finding(code, ids, reason, condition, missing=None):
            findings.append({'code': code, 'source_event_ids': ids, 'constraint': reason,
                             'reason': reason, 'reopen_conditions': condition,
                             'missing_data': missing or []})
        parents = move.get('parent_event_ids') or []
        operation = move.get('proposed_operation') or {}
        evidence_refs = string_list(move.get('evidence_refs', []), 'evidence_refs')
        fp = ResearchMoveFingerprint.build(operation)
        mechanism = normalize_claim(operation.get('mechanism', 'unspecified'))
        intent = operation.get('intent')
        frontier = self.inspect(project, include_closed=True)
        adverse_evidence = []
        with self.store._connect() as connection:
            self._events(connection, project, parents)
            self._move_refs(connection, project, move)
            adverse_evidence = self.store.evidence_reviews.assess(connection,project,move)
            for item in adverse_evidence:
                if item['status']=='REVIEW_REQUIRED':
                    finding('ADVERSE_EVIDENCE_REQUIRES_REVIEW',[item['event_id']],item['reason'],item['reopen_conditions'])
            active_id = move.get('active_frontier_id')
            if active_id is not None:
                active = self._obligation(connection, active_id)
                if active['project'] != project:
                    raise ValueError('active frontier belongs to another project')
                if active['status'] in CLOSED_STATUSES:
                    finding('OBSOLETE_FRONTIER', active['source_event_ids'], active['closure_reason'], active['reopen_conditions'])
                if active['status'] == 'BLOCKED':
                    finding('BLOCKED_FRONTIER', active['source_event_ids'], active['closure_reason'],
                            active['reopen_conditions'] or ['Resolve the documented blocking conditions.'])
                if active.get('reopen_reason'):
                    finding('REOPEN_REQUIRES_SEMANTIC_REVIEW', active['source_event_ids'],
                            'Reopening grounds are recorded, not independently established.', active['reopen_conditions'])
            else:
                finding('MISSING_ACTIVE_FRONTIER', parents, 'No active obligation was identified.',
                        ['Identify the current scoped research obligation.'], ['active_frontier_id'])
            if not parents:
                finding('MISSING_PARENT_EVENTS', [], 'No historical research inputs were identified.',
                        ['Link source events from this project.'], ['parent_event_ids'])
            prior_moves = [json.loads(row['payload_json']) for row in connection.execute(
                'SELECT payload_json FROM research_moves WHERE project=? AND fingerprint=? AND id!=?',
                (project, fp.digest, move.get('_exclude_move_id', -1)))]
            for prior in prior_moves:
                if not fp.complete:
                    continue
                prior_refs = prior.get('evidence_refs', [])
                refs = evidence_refs
                changed = move.get('claimed_new_distinction')
                # A new description/reference is a review request, never proof of novelty.
                if not changed and not set(refs) - set(prior_refs):
                    finding('NO_NEW_DISTINCTION', prior.get('parent_event_ids', []),
                            'The declared premises, properties, consequence, and required evidence match a recorded move.',
                            ['Supply new source data or a precisely changed mathematical claim.'])
                else:
                    finding('REQUIRES_SEMANTIC_REVIEW', prior.get('parent_event_ids', []),
                            'A matching historical mechanism has a claimed distinction that needs independent review.',
                            ['Check the new data and distinguish the new scoped claim.'])
        for constraint in frontier['constraints']:
            if mechanism not in constraint.get('mechanisms', []):
                continue
            if constraint['kind'] == 'obsolete_mechanism':
                obligation = next(item for item in frontier['obligations'] if item['id'] == constraint['obligation_id'])
                if obligation['status'] in CLOSED_STATUSES:
                    finding('OBSOLETE_FRONTIER', constraint['source_event_ids'], constraint['reason'], constraint['reopen_conditions'])
                else:
                    finding('REOPEN_REQUIRES_SEMANTIC_REVIEW', constraint['source_event_ids'],
                            'The historical branch was reopened; its new grounds still require semantic review.',
                            constraint['reopen_conditions'])
            elif constraint['kind'] == 'preservation_required':
                finding('UNPROVEN_SEMANTIC_PRESERVATION', constraint['source_event_ids'],
                        constraint['reason'], constraint['reopen_conditions'], constraint['required_properties'])
        preservation = move.get('preserved_properties') or {}
        if not isinstance(preservation, dict):
            raise ValueError('preserved_properties must be an object keyed by preservation property')
        unknown = set(preservation) - set(PRESERVATION_PROPERTIES)
        if unknown:
            raise ValueError('unknown preservation properties: ' + ', '.join(sorted(unknown)))
        source = move.get('source_representation', '')
        target = move.get('target_representation', '')
        transforms = intent == 'transformation' or (bool(source and target) and source != target)
        contract_id = move.get('transformation_contract_id')
        if contract_id is not None:
            with self.store._connect() as connection:
                contract = connection.execute('SELECT * FROM transformation_contracts WHERE id=?', (contract_id,)).fetchone()
            if contract is None or contract['project'] != project:
                raise ValueError('transformation contract missing or belongs to another project')
            payload = json.loads(contract['payload_json'])
            if payload['source'] != source or payload['result'] != target or payload['operation'] != operation:
                finding('TRANSFORMATION_CONTRACT_MISMATCH', parents,
                        'The stored contract does not match the proposed source, operation, and result.',
                        ['Provide the exact contract for this transformation.'])
        elif transforms:
            finding('MISSING_TRANSFORMATION_CONTRACT', parents,
                    'A representation change needs a persistent source → operation → result contract.',
                    ['Record the transformation contract and its five preservation obligations.'],
                    ['transformation_contract_id'])
        preservation_checks = []
        for prop in PRESERVATION_PROPERTIES:
            claim = preservation.get(prop, {})
            if not isinstance(claim, dict):
                raise ValueError('each preservation property must be an object')
            refs = string_list(claim.get('evidence_refs', []), 'preservation evidence_refs')
            status = 'NOT_CLAIMED' if claim.get('claim') == 'not_claimed' else ('REFERENCE_REQUIRES_REVIEW' if refs else 'MISSING_WITNESS')
            preservation_checks.append({'property': prop, 'status': status, 'evidence_refs': refs,
                                        'established': False})
            if transforms and status != 'NOT_CLAIMED':
                finding('UNPROVEN_SEMANTIC_PRESERVATION', parents,
                        'Preservation of ' + prop + ' is not established by its declaration or a reference alone.',
                        ['Provide a checkable witness for this property in this transformation scope.'], [prop])
        plan = move.get('verification_plan') or {}
        plan_ok = isinstance(plan, dict) and all(plan.get(key) for key in ('method', 'failure_condition'))
        if not fp.complete or not source or not target or not plan_ok:
            finding('REQUIRES_SEMANTIC_REVIEW', parents, 'The structured research contract is incomplete.',
                    ['Declare premises, properties, a testable consequence, required evidence, representations and a falsifying test.'],
                    [key for key, value in [('fingerprint_claims', fp.complete), ('source_representation', source),
                      ('target_representation', target), ('verification_plan', plan_ok)] if not value])
        if intent != 'experiment' or operation.get('proof_claim', False):
            finding('REQUIRES_SEMANTIC_REVIEW', parents, 'No mathematical proof is approved by this auditor.',
                    ['Use independent semantic review and an appropriate proof checker.'])
        experiment_constraints = [item for item in frontier['constraints']
                                  if item['kind'] == 'allowed_experiment' and mechanism in item.get('mechanisms', [])]
        known = False
        for constraint in experiment_constraints:
            in_scope = (set(constraint['source_event_ids']).issubset(parents)
                        and move.get('active_frontier_id') == constraint['obligation_id']
                        and source in constraint.get('source_representations', [])
                        and target == source)
            if in_scope:
                known = True
            else:
                finding('EXPERIMENT_SCOPE_REQUIRES_REVIEW', constraint['source_event_ids'],
                        'The known experiment name does not establish that this move uses its recorded source and scope.',
                        ['Use the matching active obligation, source representation, and source events, or obtain semantic review.'])
        if not known and not findings:
            finding('REQUIRES_SEMANTIC_REVIEW', parents,
                    'A structurally specified new hypothesis is not yet established as a genuinely new mechanism.',
                    ['Review its claimed distinction and relevance to the active frontier.'])
        codes = list(dict.fromkeys(item['code'] for item in findings))
        if findings:
            verdict = 'REQUIRES_SEMANTIC_REVIEW'
            priority = ('TRANSFORMATION_CONTRACT_MISMATCH', 'OBSOLETE_FRONTIER', 'NO_NEW_DISTINCTION', 'UNPROVEN_SEMANTIC_PRESERVATION')
            classification = next((code for code in priority if code in codes), 'REQUIRES_SEMANTIC_REVIEW')
            if (classification == 'REQUIRES_SEMANTIC_REVIEW' and codes == ['REQUIRES_SEMANTIC_REVIEW']
                    and fp.complete and source and target and plan_ok and intent == 'experiment'):
                classification = 'NEW_TESTABLE_HYPOTHESIS'
        else:
            verdict = 'EXPERIMENT_ALLOWED'
            classification = 'ACTIVE_CONTINUATION' if known else 'NEW_TESTABLE_HYPOTHESIS'
        return {'candidate': proposal, 'verdict': verdict, 'classification': classification, 'warnings': codes,
                'adverse_evidence':adverse_evidence, 'audit_contract_version':'0.4.2',
                'findings': findings, 'fingerprint': asdict(fp), 'preservation_checks': preservation_checks,
                'formal_checks': {'source_event_references_valid': True, 'compares_declared_claims_only': True,
                                  'mathematical_equivalence_decided': False},
                'permitted_use': 'bounded_experiment' if verdict == 'EXPERIMENT_ALLOWED' else 'review_or_reopen',
                'activation_required': True, 'execution_permission': {'allowed': False},
                'proof_status': 'unverified', 'semantic_review_required': bool(findings)}
