"""One staging controller reusing014 I/T, normalization, precommit and011 history."""
import copy
import json
import sqlite3
from normalizer import canonical, digest, read_history, normalize_context
from research_store import ResearchStore
from law_validation014_engine import LawCycle014
from law_validation014_contract import Request014
from typed_cycle011 import TypedCycle
from typed_cycle011_contract import denied
from typed_cycle011_store import connect
from live_transfer006 import endpoint, initial_cache
from engine017_contract import Query017
from engine017_store import registered, proposal_lock
from engine017_receipt import ReceiptValidator017


class EngineController017(LawCycle014, ReceiptValidator017):
    def registered(self, project):
        with connect(self.database) as c:
            return registered(c, project)

    def projection(self, project):
        with connect(self.database) as c:
            row = c.execute('SELECT payload_json FROM engine017_projections WHERE project=? ORDER BY version DESC LIMIT 1', (project,)).fetchone()
        return json.loads(row[0]) if row else {'version': 0, 'state': 'SOURCE_BOUND', 'applicability': {'excluded': [], 'independent_branch_preserved': True}}

    def authoritative(self, request):
        project = request['project']
        manifest, binding = self.registered(project)
        if manifest['inspection_status'] != 'COMPUTABLE_CHECKED':
            raise ValueError('UNKNOWN_SOURCE_SEMANTICS_DECLARED_UNINSPECTED')
        query = Query017.model_validate(request) if 'question' not in request else None
        if (query.context_level if query else request['question'].get('context_level', 'C2')) == 'C4':
            raise ValueError('C4_IS_NOT_AUDIT_SUFFICIENT')
        if query:
            if query.source_id is not None and query.source_id != manifest['source_id']:
                raise ValueError('SOURCE_ID_REBIND')
            if query.version is not None and query.version != manifest['version']:
                raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER')
            if query.observer is not None and query.observer.model_dump() != manifest['observer']:
                raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER')
        with connect(self.database) as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM events WHERE project=? ORDER BY id', (project,))]
            root = json.loads(next(r for r in rows if r['id'] == binding['root_event_id'])['content'])
            latest = c.execute('SELECT event_id FROM typed011_receipts WHERE project=? ORDER BY id DESC LIMIT 1', (project,)).fetchone()
        histories = root['source_spec']['histories']
        result = {'project': project, 'active_frontier_id': binding['obligation_id'], 'active_frontier_version': manifest['version'],
            'source_event_ids': [r['id'] for r in rows], 'source_bindings': [{'event_id': r['id'], 'sha256': digest(r)} for r in rows],
            'source_adapter_id': 'source014-native/v1', 'observer': manifest['observer'],
            'question': {'root_event_id': binding['root_event_id'], 'left_history_id': int(histories[0].split(':')[1]),
                'right_history_id': int(histories[1].split(':')[1]), 'mode': 'constructive', 'max_suffix_length': 4,
                'feedback_event_id': latest['event_id'] if latest else None, 'known_fingerprints': []}}
        result = Request014.model_validate(result).model_dump()
        if not query:
            supplied = Request014.model_validate(request).model_dump()
            for field in ('active_frontier_id', 'active_frontier_version', 'source_event_ids', 'source_bindings', 'source_adapter_id', 'observer'):
                if supplied[field] != result[field]:
                    raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER_HASH')
            for field in ('root_event_id', 'left_history_id', 'right_history_id', 'mode', 'context_level'):
                if supplied['question'][field] != result['question'][field]:
                    raise ValueError('SOURCE_QUESTION_REBIND')
            result['budget'] = supplied['budget']
        return result

    def context(self, req):
        values = list(super().context(req))
        _, history, _, spec, _, frame, _, law_fp, _, _, _ = values
        events = {e['id']: e for e in history['tables']['events']}
        immutable = json.loads(events[req.question.root_event_id]['content'])
        fresh = copy.deepcopy(immutable['source_spec'])
        frame.spec['hypotheses'] = fresh['hypotheses']
        spec['hypotheses'] = frame.spec['hypotheses']
        observed = json.loads(events[immutable['observations_event_id']]['content'])
        executed, covered, review = copy.deepcopy(observed['executed_words']), [], False
        with connect(self.database) as c:
            receipts = [json.loads(r[0]) for r in c.execute('SELECT payload_json FROM typed011_receipts WHERE project=? ORDER BY id', (req.project,))]
        # Only definitive committed outcomes change hypotheses. No synthetic
        # observation from ERROR/INCONCLUSIVE is fed back into native I/T.
        frame._seal = digest([frame.declaration, frame.spec, frame.query, frame.words])
        port = frame.port()
        actions = spec['parameters']['actions']
        for receipt in receipts:
            env = json.loads(events[receipt['event_id']]['content'])['measurement_binding']
            if env['law_fingerprint'] != law_fp:
                raise ValueError('FEEDBACK_LAW_REBIND')
            if env['outcome'] not in ('SUCCESS', 'FAILURE'):
                continue
            if env['purpose'] == 'VALIDATE_TRANSFER':
                executed.append(env['context_word'] + env['suffix_ordinals'])
                covered.extend(zip(env['suffix_ordinals'], env['suffix_ordinals'][1:]))
                review |= env['outcome'] == 'FAILURE'
                continue
            any_match = False
            for hypothesis in frame.spec['hypotheses']:
                if hypothesis['question'] != 'current' or not hypothesis['predictive']:
                    continue
                predicted = endpoint(port, initial_cache(port, frame.words[hypothesis['ref']]),
                    [actions[i] for i in env['suffix_ordinals']], spec['observer'])
                if predicted != env['observed']:
                    hypothesis['predictive'] = False
                    hypothesis['excluded_by'] = receipt['event_id']
                else:
                    any_match = True
            review |= not any_match
            frame._seal = digest([frame.declaration, frame.spec, frame.query, frame.words])
        values[8:11] = [executed, covered, review]
        return tuple(values)

    def preview(self, request):
        try:
            args = self.authoritative(request)
            projection = self.projection(args['project'])
            if projection['state'] in ('AWAITING_INCONCLUSIVE_EVIDENCE', 'ERROR_REQUIRES_OPERATOR_REVIEW', 'REQUIRES_REVIEW'):
                return denied(projection['state'], 'Latest committed bound outcome requires explicit owner attention; no automatic retry.',
                    feedback=projection, caller_memory_ignored=True)
            out = super().preview(args)
            out.update(controller_version='017.1', source_protocol='typed017/v1',
                feedback=projection, applicability_version=projection['version'], caller_memory_ignored=True,
                canonical_request=args, controller_state='NEXT_PROPOSAL' if out['status'] == 'PROPOSAL_READY' else out['status'])
            if out['status'] == 'PROPOSAL_READY':
                history = read_history(self.database, args['project'])
                view = normalize_context(history, 'engine-owned context', [{'id': '017', 'project': args['project'],
                    'root_ref': 'event:' + str(args['question']['root_event_id']), 'scope': self.registered(args['project'])[0]['scope'],
                    'version': args['active_frontier_version']}], 'C2')
                out['normalization'].update(loss_ledger=view['loss_ledger'], input_digest=view['input_digest'], certificate=view['certificate'])
            return out
        except (ValueError, KeyError, TypeError, sqlite3.Error) as error:
            return denied('INSUFFICIENT_CONTEXT', str(error), controller_version='017.1')

    def precommit(self, request, request_key):
        if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128:
            raise ValueError('INVALID_REQUEST_KEY')
        intent = copy.deepcopy(request)
        for field in ('known_fingerprints', 'latest_feedback', 'display_label'):
            intent.pop(field, None)
        if 'question' in intent:
            intent['question'].pop('known_fingerprints', None)
            intent['question'].pop('feedback_event_id', None)
        intent_sha = digest(intent)
        project = request['project']
        with proposal_lock(self.database):
            with connect(self.database) as c:
                prior = c.execute('SELECT * FROM engine017_requests WHERE project=? AND request_key=?', (project, request_key)).fetchone()
                if prior:
                    if prior['intent_sha256'] != intent_sha:
                        raise ValueError('PRECOMMIT_KEY_CONFLICT')
                    row = dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?', (prior['precommit_id'],)).fetchone())
                    return self._link(row)
            args = self.authoritative(request)
            result = super().precommit(args, request_key)
            store = ResearchStore(self.database)
            with connect(self.database, True) as c:
                c.execute('INSERT INTO engine017_requests VALUES (?,?,?,?)', (project, request_key, intent_sha, result['precommit_id']))
                store._audit(c, 'engine017_proposal_intent_bound', {'project': project, 'key': request_key,
                    'intent_sha256': intent_sha, 'precommit_id': result['precommit_id']})
            return result

    def novelty(self, request):
        args = self.authoritative(request)
        manifest, _ = self.registered(args['project'])
        with connect(self.database) as c:
            rows = [dict(r) for r in c.execute('SELECT id,claim_fingerprint,raw_sha256,receipt_id FROM typed011_journal WHERE project=? AND scope=? ORDER BY id', (args['project'], manifest['scope']))]
        return denied('AUTHORITATIVE_SNAPSHOT', 'Caller memory does not determine novelty.', snapshot_complete=True,
            caller_known_ignored=True, journal=rows, feedback=self.projection(args['project']))

    def history(self, project):
        manifest, _ = self.registered(project)
        store = ResearchStore(self.database)
        with connect(self.database) as c:
            move_ids = [r[0] for r in c.execute('SELECT move_id FROM typed011_moves JOIN research_moves ON id=move_id WHERE project=? ORDER BY move_id', (project,))]
            projections = [json.loads(r[0]) for r in c.execute('SELECT payload_json FROM engine017_projections WHERE project=? ORDER BY version', (project,))]
            receipts = [json.loads(r[0]) for r in c.execute('SELECT payload_json FROM typed011_receipts WHERE project=? ORDER BY id', (project,))]
            executions = [{'move_id': r['move_id'], 'event_id': r['event_id'],
                'envelope': json.loads(r['content'])['measurement_binding']} for r in c.execute(
                'SELECT x.move_id,x.event_id,e.content FROM typed011_executions x JOIN events e ON e.id=x.event_id WHERE x.move_id IN (SELECT id FROM research_moves WHERE project=?)', (project,))]
            precommits = [{'id': r['id'], 'sha256': r['digest'], 'payload': json.loads(r['payload_json']),
                'preview': json.loads(r['preview_json'])} for r in c.execute('SELECT * FROM typed011_precommits WHERE project=? ORDER BY id', (project,))]
            activations = [dict(r) for r in c.execute('SELECT move_id,audit_id,operation_id FROM typed011_activations WHERE move_id IN (SELECT id FROM research_moves WHERE project=?)', (project,))]
        moves = [store.moves.inspect(project, i) for i in move_ids]
        routes = []
        for move in moves:
            stages = ['SOURCE_BOUND', 'NORMALIZED', 'HYPOTHESES_OR_LAW_BOUND', 'I_PREVIEWED', 'T_SELECTED', 'PRECOMMITTED']
            if move['audits']:
                stages.append('AUDITED')
            if any(a['move_id'] == move['id'] for a in activations):
                stages.append('OPERATOR_ACTIVATED')
            execution = next((e for e in executions if e['move_id'] == move['id']), None)
            if execution:
                stages.append('EXTERNAL_ATTEMPT_RECORDED')
                if execution['envelope']['observed']['defined']:
                    stages.append('EXTERNALLY_MEASURED')
            if any(r['move_id'] == move['id'] for r in receipts):
                stages.extend(['TYPED_VALIDATED', 'OPERATOR_COMMITTED', 'FEEDBACK_PROJECTED'])
            routes.append({'move_id': move['id'], 'stages': stages, 'interpretation': 'Derived from durable records; not claim truth or new audit events.'})
        return denied('AUTHORITATIVE_HISTORY', 'State representation is not claim truth.', source=manifest,
            moves=moves, receipts=receipts, executions=executions, activations=activations,
            precommits=precommits, state_routes=routes,
            projections=projections, feedback=self.projection(project))
