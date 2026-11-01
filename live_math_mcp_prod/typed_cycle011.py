"""Server-owned bounded source contracts. No environment/oracle or executor import."""
import copy
import json
from pathlib import Path
import sqlite3
import time

from pydantic import ValidationError
from frontier import ResearchMoveFingerprint
from normalizer import canonical, digest, read_history
from native_preview008_contract import NativeRequest, NormalizeRequest, ADAPTER_ID
from native_preview008_engine import check_sources, frontier, source_budget
from native_preview008_server import PreviewBoundary
from research_cycle009 import operation, proposal, selected_claim, material
from research_store import ResearchStore
from typed_cycle011_contract import CyclePrecommit, MeasurementEnvelope, ReceiptRequest, denied
from typed_cycle011_store import connect, scope, assert_isolated


def ordinal_parameters(parameters):
    p = copy.deepcopy(parameters); p['actions'] = list(range(len(p['actions'])))
    return p


def journal_state(c, project, scoped, family, claim, raw):
    rows = c.execute('SELECT * FROM typed011_journal WHERE project=? AND scope=? AND source_family_id=? AND claim_fingerprint=?',
                     (project, scoped, family, claim)).fetchall()
    if any(r['raw_sha256'] != raw for r in rows): return 'REQUIRES_REVIEW'
    return 'NO_NEW_DISTINCTION_BOUNDED' if rows else 'NEW_DISTINCTION'


def require_ledger_order(precommit, audit, activation, event):
    if not precommit < audit < activation < event:
        raise ValueError('PRECOMMIT_AUDIT_ACTIVATION_EVENT_ORDER')


class TypedCycle:
    def __init__(self, database):
        self.database = Path(database).resolve(strict=True)

    def context(self, req):
        if len(canonical(req.model_dump()).encode()) > req.budget.input_bytes: raise ValueError('INPUT_BYTE_BOUND')
        if req.source_adapter_id != ADAPTER_ID: raise ValueError('UNSUPPORTED_ADAPTER')
        if req.question.context_level == 'C4': raise ValueError('C4_IS_NOT_AUDIT_SUFFICIENT')
        history = read_history(self.database, req.project, source_budget(req.budget))
        check_sources(history, req.source_event_ids, req.source_bindings, exact=True)
        current = frontier(history, req.active_frontier_id, req.active_frontier_version)
        events = {e['id']: e for e in history['tables']['events']}
        spec = json.loads(events[req.question.root_event_id]['content'])['source_spec']
        if req.observer.model_dump() != spec['observer']: raise ValueError('OBSERVER_MISMATCH')
        actions = spec['parameters']['actions']; ordinal = lambda word: [actions.index(a) for a in word]
        with connect(self.database) as c:
            registered = scope(c, req.project)
            latest = c.execute('SELECT payload_json FROM typed011_receipts WHERE project=? ORDER BY id DESC LIMIT 1', (req.project,)).fetchone()
        if current['scope'] != registered['scope']: raise ValueError('SCOPE_MISMATCH')
        # The journal owns feedback selection. Caller omission cannot revive an excluded guard.
        if latest:
            committed = json.loads(latest[0])
            if committed['outcome'] in {'SUCCESS','FAILURE'}:
                source = events[committed['event_id']]
                if req.question.feedback_event_id is None and source['kind'] == 'counterexample' and json.loads(source['content'])['version'] == req.active_frontier_version:
                    req.question.feedback_event_id = source['id']
                feedback = events.get(req.question.feedback_event_id)
                if feedback is None: raise ValueError('CURRENT_MEASUREMENT_FEEDBACK_PROJECTION_REQUIRED')
                data = json.loads(feedback['content']); observed = data.get('observation', {})
                envelope = json.loads(source['content'])['measurement_binding']
                if any(observed.get(k) != v for k,v in {'test_id':envelope['test_id'],'readout':envelope['observed'],
                        'scope':current['scope'],'version':req.active_frontier_version,'observer':req.observer.model_dump()}.items()):
                    raise ValueError('STALE_OR_FORGED_FEEDBACK_PROJECTION')
                cursor = feedback; visited = set()
                while cursor['id'] != source['id']:
                    if cursor['id'] in visited or len(visited) >= 8: raise ValueError('FEEDBACK_PROVENANCE_BOUND')
                    visited.add(cursor['id'])
                    links = [r.get('target_ref','') for r in json.loads(cursor['content']).get('relations',[]) if r.get('type') == 'derived_from']
                    if len(links) != 1 or not links[0].startswith('event:'): raise ValueError('FEEDBACK_HAS_NO_COMMITTED_SOURCE')
                    cursor = events.get(int(links[0].split(':')[1]))
                    if cursor is None: raise ValueError('FOREIGN_FEEDBACK_PROVENANCE')
        op_sha = digest(ordinal_parameters(spec['parameters']))
        if op_sha != registered['operation_definition_sha256'] or spec['primitive_sha256'] != registered['native_definition_sha256']:
            raise ValueError('SOURCE_DEFINITION_DRIFT')
        fixture = events.get(registered['fixture_id'])
        if fixture is None or digest(fixture) != registered['fixture_sha256']: raise ValueError('SOURCE_IDENTITY_DRIFT')
        words = [ordinal(json.loads(events[i]['content'])['word']) for i in (req.question.left_history_id, req.question.right_history_id)]
        identity = {'source_family_id': registered['source_family_id'], 'parameters': ordinal_parameters(spec['parameters']),
            'native_definition_sha256': spec['primitive_sha256'], 'observer': req.observer.model_dump(),
            'words': sorted(words), 'domain': [ordinal(t['suffix']) for t in spec['tests']],
            'scope': current['scope'], 'project': req.project}
        return history, current, spec, registered, digest(identity), ordinal

    def preview(self, request):
        req = NativeRequest.model_validate(request)
        if len(canonical(req.model_dump()).encode()) > req.budget.input_bytes:
            return denied('INSUFFICIENT_CONTEXT', 'INPUT_BYTE_BOUND')
        if req.question.context_level == 'C4': return denied('INSUFFICIENT_CONTEXT', 'C4_IS_NOT_AUDIT_SUFFICIENT')
        started = time.perf_counter_ns()
        try:
            history, current, spec, registered, claim, ordinal = self.context(req)
        except (ValueError, KeyError, sqlite3.Error) as error:
            return denied('NOVELTY_CONTEXT_INCOMPLETE' if 'NOVELTY_CONTEXT_INCOMPLETE' in str(error) or 'no such table' in str(error)
                          else 'INSUFFICIENT_CONTEXT', str(error))
        source_ns = time.perf_counter_ns() - started
        # Actual004 normalization and native007 I + independent006 T run under008 caps.
        candidate = {'id': 'native-preview008', 'project': req.project, 'root_ref': 'event:' + str(req.question.root_event_id),
            'scope': current['scope'], 'version': req.active_frontier_version,
            'move': {'active_frontier_id': req.active_frontier_id, 'parent_event_ids': req.source_event_ids,
                     'proposed_operation': {'mechanism': 'readonly_source_law_interpretation', 'intent': 'advisory'}}}
        normal_req = NormalizeRequest(project=req.project, focus='source-certified interpretation', source_event_ids=req.source_event_ids,
            query_scope={'level': req.question.context_level, 'candidates': [candidate],
                'expected_hashes': [s.model_dump() for s in req.source_bindings], 'obligation_id': req.active_frontier_id,
                'version': req.active_frontier_version, 'scope': current['scope']}, budget=req.budget)
        normalized = PreviewBoundary(self.database).run('normalize', normal_req.model_dump())
        if normalized['status'] != 'COMPLETE' or not normalized.get('audit_sufficient'):
            return denied('INSUFFICIENT_CONTEXT', 'NORMALIZATION_INCOMPLETE', normalization=normalized)
        args = req.model_dump(); args['question']['known_fingerprints'] = []
        out = PreviewBoundary(self.database).run('native', args)
        if out['status'] not in {'NEW_DISTINCTION', 'NO_NEW_DISTINCTION_BOUNDED', 'UNKNOWN_BOUNDED'}:
            return out
        w = out.get('witness')
        raw = {'suffix_ordinals': ordinal(w['suffix']), 'readouts': w['readouts']} if w else {'witness': None}
        if w:
            events={e['id']:e for e in history['tables']['events']}
            pairs=[(tuple(ordinal(json.loads(events[int(ref.split(':')[1])]['content'])['word'])), readout)
                   for ref,readout in zip(w['histories'],w['readouts'])]
            raw['readouts']=[readout for _,readout in sorted(pairs,key=lambda pair:pair[0])]
        raw_sha = digest(raw)
        with connect(self.database) as c:
            status = journal_state(c, req.project, current['scope'], registered['source_family_id'], claim, raw_sha)
            known = [dict(r) for r in c.execute('SELECT id,claim_fingerprint,raw_sha256,receipt_id FROM typed011_journal WHERE project=? AND scope=? AND source_family_id=? ORDER BY id',
                (req.project, current['scope'], registered['source_family_id']))]
        if w: out['status'] = status
        # Identity is structural and version-invariant; source addresses remain explicit provenance.
        out.update(claim_fingerprint=claim, raw_distinction_sha256=raw_sha, raw_distinction=raw,
            source_family_id=registered['source_family_id'], operation_definition_sha256=registered['operation_definition_sha256'],
            authoritative_novelty={'snapshot_complete': True, 'journal': known, 'caller_known_ignored': True},
            normalization=normalized, source_lookup_wall_ns=source_ns,
            execution_permission={'allowed': False}, proof_status='unverified', controller_version='011.1')
        out['preview_digest'] = digest({'claim': claim, 'raw': raw_sha, 'request': {**args, 'question': args['question']},
            'attention': material(out['attention']), 'source_hashes': out['source_hashes']})
        if len(canonical(out).encode()) > req.budget.output_bytes: return denied('RESOURCE_LIMIT','CONTROLLER_OUTPUT_BYTE_BOUND')
        return out

    def precommit(self, request, request_key):
        assert_isolated(self.database)
        req = NativeRequest.model_validate(request)
        if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128: raise ValueError('INVALID_REQUEST_KEY')
        args = req.model_dump(); args['question']['known_fingerprints'] = []
        request_sha = digest(args)
        with connect(self.database) as c:
            prior = c.execute('SELECT * FROM typed011_precommits WHERE project=? AND request_key=?', (req.project, request_key)).fetchone()
            if prior is None:
                prior = c.execute('SELECT * FROM typed011_precommits WHERE project=? AND request_sha=?', (req.project, request_sha)).fetchone()
            if prior:
                if prior['request_sha'] != request_sha: raise ValueError('PRECOMMIT_KEY_CONFLICT')
                return self._link(dict(prior))
            equivalent = c.execute('SELECT * FROM typed011_precommits WHERE project=? AND request_sha=?', (req.project, request_sha)).fetchone()
            if equivalent: return self._link(dict(equivalent))
        out = self.preview(args)
        if out['status'] not in {'NEW_DISTINCTION', 'NO_NEW_DISTINCTION_BOUNDED'} or not out.get('witness') or out['attention']['status'] != 'ATTENTION_PROPOSED':
            raise ValueError('PRECOMMIT_REQUIRES_BOUNDED_SOURCE_WITNESS_AND_INFORMATIVE_T:' + out['status'])
        history, current, spec, registered, claim_fp, ordinal = self.context(req)
        args = req.model_dump(); args['question']['known_fingerprints'] = []
        test, chosen = selected_claim(out['attention'])
        if any(not r['readout']['defined'] or not all(r['readout']['admissibility']) for r in test['counterfactuals']):
            raise ValueError('NONEXECUTABLE_READOUT')
        world = {'project': req.project, 'scope': current['scope'], 'fixture_sha256': registered['fixture_content_sha256']}
        op = operation(world, test['test_id'], chosen['readout'], 'typed011 bounded cycle')
        op['premises'].append('Exact typed action context ' + request_sha)
        pc = CyclePrecommit(project=req.project, obligation_id=req.active_frontier_id, obligation_version=req.active_frontier_version,
            scope=current['scope'], native_request=NativeRequest.model_validate(args), source_bindings=req.source_bindings,
            source_family_id=registered['source_family_id'], native_definition_sha256=spec['primitive_sha256'],
            operation_definition_sha256=registered['operation_definition_sha256'], observer=req.observer, test_id=test['test_id'],
            suffix=test['suffix'], suffix_ordinals=ordinal(test['suffix']), admissibility_guard=[True] * len(test['suffix']),
            alternatives=test['counterfactuals'], tested_hypothesis=chosen['hypothesis'], expected_readout=chosen['readout'],
            proposal_fingerprint=ResearchMoveFingerprint.build(op).digest, claim_fingerprint=claim_fp,
            raw_distinction_sha256=out['raw_distinction_sha256'], preview_digest=out['preview_digest'])
        store = ResearchStore(self.database); payload = pc.model_dump()
        with connect(self.database, True) as c:
            self._sources_current(c, payload)
            prior = c.execute('SELECT * FROM typed011_precommits WHERE project=? AND request_key=?', (req.project, request_key)).fetchone()
            if prior is None:
                prior = c.execute('SELECT * FROM typed011_precommits WHERE project=? AND request_sha=?', (req.project, request_sha)).fetchone()
            if prior:
                if prior['request_sha'] != request_sha: raise ValueError('PRECOMMIT_KEY_CONFLICT')
                row = dict(prior)
            else:
                cur = c.execute('INSERT INTO typed011_precommits(project,request_key,request_sha,digest,payload_json,operation_json,preview_json) VALUES (?,?,?,?,?,?,?)',
                    (req.project, request_key, request_sha, digest(payload), canonical(payload), canonical(op), canonical(out)))
                row = dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?', (cur.lastrowid,)).fetchone())
                store._audit(c, 'typed011_precommitted', {'precommit_id': row['id'], 'digest': row['digest']})
        return self._link(row)

    def _link(self, row):
        pc = json.loads(row['payload_json']); op = json.loads(row['operation_json'])
        with connect(self.database) as c:
            registered = scope(c, pc['project'])
            existing = c.execute('SELECT move_id FROM typed011_moves WHERE precommit_id=?', (row['id'],)).fetchone()
        if existing:
            return {'precommit_id': row['id'], 'precommit_sha256': row['digest'], 'move_id': existing['move_id'],
                    'proposal_fingerprint': pc['proposal_fingerprint'], 'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
        op['cycle_binding'] = {'precommit_id': row['id'], 'sha256': row['digest']}
        adverse = [e['id'] for e in read_history(self.database, pc['project'])['tables']['events'] if e['kind'] in {'failure', 'failed_check', 'counterexample', 'rca'} or e['status'] in {'refuted', 'counterexample'}]
        move = proposal({'scope': pc['scope'], 'fixture_sha256': registered['fixture_content_sha256']},
            {'obligation_id': pc['obligation_id'], 'version': pc['obligation_version'], 'fixture_id': registered['fixture_id'],
             'root_id': pc['native_request']['question']['root_event_id']}, op, adverse)
        store = ResearchStore(self.database)
        recorded = store.moves.record(pc['project'], move, 'typed011:propose:' + str(row['id']))
        with connect(self.database, True) as c:
            c.execute('INSERT OR IGNORE INTO typed011_moves VALUES (?,?)', (recorded['id'], row['id']))
        return {'precommit_id': row['id'], 'precommit_sha256': row['digest'], 'move_id': recorded['id'],
                'proposal_fingerprint': recorded['fingerprint']['digest'], 'proof_status': 'unverified', 'execution_permission': {'allowed': False}}

    @staticmethod
    def _sources_current(c, pc):
        registered = scope(c, pc['project'])
        ob = c.execute('SELECT * FROM research_obligations WHERE id=? AND project=?', (pc['obligation_id'], pc['project'])).fetchone()
        if not ob or ob['current_version'] != pc['obligation_version']: raise ValueError('STALE_OBLIGATION_VERSION')
        ver = c.execute('SELECT payload_json FROM research_obligation_versions WHERE obligation_id=? AND version=?', (pc['obligation_id'], pc['obligation_version'])).fetchone()
        current = json.loads(ver[0])
        if current['status'] not in {'OPEN', 'TESTING'} or current['scope'] != pc['scope'] or pc['scope'] != registered['scope']:
            raise ValueError('CLOSED_OR_WRONG_SCOPE')
        for binding in pc['source_bindings']:
            source = c.execute('SELECT * FROM events WHERE id=? AND project=?', (binding['event_id'], pc['project'])).fetchone()
            if source is None or digest(dict(source)) != binding['sha256']: raise ValueError('SOURCE_HASH_OR_PROJECT_DRIFT')

    def validate(self, project, move_id, event_id):
        try:
            with connect(self.database) as c: return self.validate_in(c, project, move_id, event_id)
        except (ValueError, KeyError, TypeError, OSError, ValidationError, sqlite3.Error) as error:
            return denied('REJECTED', str(error))

    def validate_in(self, c, project, move_id, event_id):
        event = c.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
        if not event or event['project'] != project: raise ValueError('MISSING_OR_FOREIGN_EVENT')
        data = json.loads(event['content'])
        if not isinstance(data, dict) or 'measurement_binding' not in data:
            return denied('INSUFFICIENT_MEASUREMENT_BINDING', 'LEGACY_EVENT_WITHOUT_BINDING')
        env = MeasurementEnvelope.model_validate(data['measurement_binding']).model_dump()
        row = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?', (move_id, project)).fetchone()
        if row is None: raise ValueError('MISSING_OR_FOREIGN_PRECOMMIT')
        pc = json.loads(row['payload_json']); self._sources_current(c, pc)
        move = c.execute('SELECT * FROM research_moves WHERE id=? AND project=?', (move_id, project)).fetchone()
        if move is None or move['fingerprint'] != pc['proposal_fingerprint']: raise ValueError('MOVE_FINGERPRINT_MISMATCH')
        mp = json.loads(move['payload_json'])
        if mp['proposed_operation']['cycle_binding'] != {'precommit_id': row['id'], 'sha256': row['digest']}: raise ValueError('MOVE_PRECOMMIT_DRIFT')
        activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
        latest = c.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence DESC LIMIT 1', (move_id,)).fetchone()
        if not activation or not latest or latest['status'] != 'EXPERIMENT_ALLOWED' or latest['audit_id'] != activation['audit_id']:
            raise ValueError('NO_CURRENT_BOUND_GRANT')
        # Reuse the existing read-only permission projection without running migrations.
        reader = ResearchStore.__new__(ResearchStore); reader.path = self.database
        if not reader.moves._view(c, move)['execution_permission']['allowed']: raise ValueError('CURRENT_LEGACY_PERMISSION_DENIED')
        decision = json.loads(latest['decision_json'])
        if not decision.get('allowed') or decision['scope'] != pc['scope'] or decision['frontier_versions'] != {str(pc['obligation_id']): pc['obligation_version']}:
            raise ValueError('STALE_OR_WRONG_GRANT')
        audit = c.execute('SELECT * FROM research_move_audits WHERE id=? AND move_id=? ORDER BY id', (activation['audit_id'], move_id)).fetchone()
        newest = c.execute('SELECT max(id) FROM research_move_audits WHERE move_id=?', (move_id,)).fetchone()[0]
        if audit is None or newest != audit['id'] or json.loads(audit['report_json'])['verdict'] != 'EXPERIMENT_ALLOWED': raise ValueError('STALE_OR_UNSUCCESSFUL_AUDIT')
        activation_op = c.execute('SELECT * FROM operations WHERE id=?', (activation['operation_id'],)).fetchone()
        act = json.loads(activation_op['details_json']) if activation_op else {}
        if not activation_op or activation_op['action'] != 'research_move_status_changed' or any(act.get(k) != v for k,v in
                {'move_id': move_id, 'status': 'EXPERIMENT_ALLOWED', 'audit_id': audit['id'], 'sequence': latest['sequence']}.items()):
            raise ValueError('FORGED_ACTIVATION_OPERATION')
        if act.get('decision_sha256') != digest(decision): raise ValueError('ACTIVATION_DECISION_DIGEST_MISMATCH')
        expected = {k: pc[k] for k in ('project', 'proposal_fingerprint', 'obligation_id', 'obligation_version', 'scope',
            'source_family_id', 'source_bindings', 'native_definition_sha256', 'operation_definition_sha256', 'observer', 'test_id', 'suffix', 'suffix_ordinals')}
        expected.update(precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id,
            audit_id=audit['id'], activation_operation_id=activation_op['id'], predictions=pc['alternatives'])
        if any(env[k] != v for k,v in expected.items()): raise ValueError('MEASUREMENT_BINDING_MISMATCH')
        if (data.get('observation') != {'test_id': pc['test_id'], 'readout': env['observed'], 'scope': pc['scope'],
                'version': pc['obligation_version'], 'observer': pc['observer']}
                or data.get('outcome') != env['outcome'] or data.get('proof_status') != 'unverified'):
            raise ValueError('RESULT_EVENT_CONFLICT')
        order = {'precommit': [], 'audit': [], 'event': []}
        for op in c.execute('SELECT * FROM operations WHERE id<=? ORDER BY id', (c.execute('SELECT max(id) FROM operations').fetchone()[0],)):
            d = json.loads(op['details_json'])
            if op['action'] == 'typed011_precommitted' and d.get('precommit_id') == row['id'] and d.get('digest') == row['digest']: order['precommit'].append(op['id'])
            if op['action'] == 'research_move_audited' and d.get('audit_id') == audit['id']: order['audit'].append(op['id'])
            event_digest = digest({k:event[k] for k in ('project','kind','focus','content','status','evidence','parent_id')})
            if op['action'] == 'event_created' and d.get('id') == event_id and d.get('digest') == event_digest:
                order['event'].append(op['id'])
        if any(len(v) != 1 for v in order.values()):
            raise ValueError('PRECOMMIT_AUDIT_ACTIVATION_EVENT_ORDER')
        require_ledger_order(order['precommit'][0], order['audit'][0], activation_op['id'], order['event'][0])
        execution = c.execute('SELECT * FROM typed011_executions WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()
        if execution is None: raise ValueError('NO_OPERATOR_LOCAL_EXECUTOR_RECEIPT')
        local = json.loads(execution['payload_json']); registered = scope(c, project)
        if env['executor_code_sha256'] != registered['executor_code_sha256'] or local['envelope_sha256'] != digest(env): raise ValueError('EXECUTOR_IDENTITY_OR_PAYLOAD_CONFLICT')
        artifact = Path(local['artifact_path']).resolve(strict=True)
        if not artifact.is_relative_to(Path(registered['artifact_directory']).resolve(strict=True)) or artifact.stat().st_size > 1_000_000:
            raise ValueError('ARTIFACT_OUTSIDE_INSPECTABLE_LOCAL_BOUNDARY')
        import hashlib
        artifact_data = artifact.read_bytes()
        if hashlib.sha256(artifact_data).hexdigest() != env['artifact_sha256']: raise ValueError('ARTIFACT_DIGEST_MISMATCH')
        artifact_value = json.loads(artifact_data)
        if artifact_value['precommit_sha256'] != row['digest'] or artifact_value['move_id'] != move_id or artifact_value['observed'] != env['observed']:
            raise ValueError('ARTIFACT_MEASUREMENT_MISMATCH')
        calculated = 'SUCCESS' if env['observed'] == pc['expected_readout'] else 'FAILURE'
        if env['outcome'] not in {calculated, 'INCONCLUSIVE', 'ERROR'}: raise ValueError('OUTCOME_PREDICTION_CONFLICT')
        if artifact_value['outcome'] != env['outcome']: raise ValueError('ARTIFACT_OUTCOME_MISMATCH')
        raw = json.loads(row['preview_json'])
        journal = journal_state(c, project, pc['scope'], pc['source_family_id'], pc['claim_fingerprint'], pc['raw_distinction_sha256'])
        if journal == 'REQUIRES_REVIEW': return denied('REQUIRES_REVIEW', 'JOURNAL_RAW_DISTINCTION_CONFLICT')
        return denied('VALID_BOUND_MEASUREMENT', 'Structural binding and local synthetic executor artifact checked; not physical authenticity or mathematical truth.',
            precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id, event_id=event_id,
            event_sha256=digest(dict(event)), audit_id=audit['id'], activation_operation_id=activation_op['id'],
            event_operation_id=order['event'][0], envelope=env, artifact_inspection='LOCAL_EXECUTOR_ARTIFACT_HASH_CHECKED',
            measurement_authenticity='LOCAL_SYNTHETIC_TRUST_BOUNDARY_ONLY', novelty=journal,
            preview_replay_digest=raw['preview_digest'])
