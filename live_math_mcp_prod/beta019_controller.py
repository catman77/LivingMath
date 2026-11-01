"""Beta-only source dependency injection;004/006/013/014 mathematics unchanged."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3

from normalizer import canonical, digest, read_history, normalize_context
from engine017_controller import EngineController017
from engine017_store import proposal_lock
from typed_cycle011_store import connect
from typed_cycle011_contract import denied
from live_transfer006 import endpoint, initial_cache
from research_store import ResearchStore
import beta019_source


def reviewed_law_template():
    """Fixed reviewed repository path; no client-selected module or code."""
    path = Path(__file__).with_name('law_validation014_engine.py')
    spec = importlib.util.spec_from_file_location('_beta019_law014', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.Port = beta019_source.Port
    module.native_sha = beta019_source.definition_sha
    module.ADAPTER = beta019_source.ADAPTER
    return module.LawCycle014


Law019 = reviewed_law_template()


class Controller019(EngineController017):
    def authoritative(self, request):
        supplied = request
        if 'question' in request:
            if request.get('source_adapter_id') != beta019_source.ADAPTER:
                raise ValueError('019_UNSUPPORTED_SOURCE_ADAPTER')
            supplied = {**request, 'source_adapter_id': 'source014-native/v1'}
        result = super().authoritative(supplied)
        result['source_adapter_id'] = beta019_source.ADAPTER
        return result

    def context(self, req):
        values = list(Law019.context(self, req))
        req, history, current, spec, registered, frame, law, law_fp, _, _, _ = values
        events = {e['id']: e for e in history['tables']['events']}
        immutable = json.loads(events[req.question.root_event_id]['content'])
        fresh = copy.deepcopy(immutable['source_spec'])
        frame.spec['hypotheses'] = fresh['hypotheses']
        spec['hypotheses'] = frame.spec['hypotheses']
        observed = json.loads(events[immutable['observations_event_id']]['content'])
        executed, covered, review = copy.deepcopy(observed['executed_words']), [], False
        with connect(self.database) as c:
            receipts = [json.loads(r[0]) for r in c.execute('SELECT payload_json FROM typed011_receipts WHERE project=? ORDER BY id', (req.project,))]
        frame._seal = digest([frame.declaration, frame.spec, frame.query, frame.words])
        port, actions = frame.port(), spec['parameters']['actions']
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
                return denied(projection['state'], 'Committed feedback requires owner review; no automatic retry.', feedback=projection)
            out = Law019.preview(self, args)
            out.update(controller_version='019.1-beta', source_protocol=beta019_source.ADAPTER, feedback=projection,
                applicability_version=projection['version'], caller_memory_ignored=True, canonical_request=args)
            if out['status'] == 'PROPOSAL_READY':
                history = read_history(self.database, args['project'])
                view = normalize_context(history, 'external source-owned context', [{'id': '019', 'project': args['project'],
                    'root_ref': 'event:' + str(args['question']['root_event_id']), 'scope': self.registered(args['project'])[0]['scope'],
                    'version': args['active_frontier_version']}], 'C2')
                out['normalization'].update(loss_ledger=view['loss_ledger'], input_digest=view['input_digest'], certificate=view['certificate'],
                    source_coordinates='Injective one-hot source configuration; acceptance observer intentionally loses configuration identity')
            return out
        except (ValueError, KeyError, TypeError, sqlite3.Error) as error:
            return denied('INSUFFICIENT_CONTEXT', str(error), controller_version='019.1-beta')

    def precommit(self, request, request_key):
        if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 128:
            raise ValueError('INVALID_REQUEST_KEY')
        intent = {k: v for k, v in request.items() if k not in ('known_fingerprints', 'latest_feedback', 'display_label')}
        intent_sha, project = digest(intent), request['project']
        with proposal_lock(self.database):
            with connect(self.database) as c:
                prior = c.execute('SELECT * FROM engine017_requests WHERE project=? AND request_key=?', (project, request_key)).fetchone()
                if prior:
                    if prior['intent_sha256'] != intent_sha:
                        raise ValueError('PRECOMMIT_KEY_CONFLICT')
                    return self._link(dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?', (prior['precommit_id'],)).fetchone()))
            result = Law019.precommit(self, self.authoritative(request), request_key)
            with connect(self.database, True) as c:
                c.execute('INSERT INTO engine017_requests VALUES (?,?,?,?)', (project, request_key, intent_sha, result['precommit_id']))
                ResearchStore(self.database)._audit(c, 'beta019_intent_bound', {'project': project, 'request_key': request_key,
                    'precommit_id': result['precommit_id'], 'intent_sha256': intent_sha})
            return result

    def validate_in(self, c, project, move_id, event_id):
        from beta019_receipt import Receipt019
        return Receipt019(self.database).validate_in(c, project, move_id, event_id)

    def history(self, project):
        from deploy018_authority import lease_in
        history = super().history(project)
        with connect(self.database) as c:
            for move in history['moves']:
                if move['execution_permission']['allowed']:
                    try:
                        lease_in(c, project, move['id'])
                    except ValueError as error:
                        move['execution_permission'] = {'allowed': False, 'needs_reaudit': True, 'reason': str(error)}
        return history
