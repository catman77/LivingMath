"""Typed workflows; proposals, review, checks and permissions remain separate."""
import copy
import json
from jsonschema import Draft202012Validator
from . import RELEASE
from . import core
from .core import digest, canonical
from .errors import AssuranceError
from .validation import validate, parse, inspect, MAX_JSON_BYTES, safe_source_schema
from .workspace import Workspace


def require(condition, code, field=None):
    if not condition:
        raise AssuranceError(code, field)


class Service:
    def __init__(self, root):
        self.root = root

    def workspace(self, project):
        return Workspace(self.root, project)

    def new(self, project, request_key):
        w = self.workspace(project)
        def create(rows):
            require(not rows, 'PROJECT_ALREADY_EXISTS')
            return {'project': project, 'release': RELEASE, 'status': 'CREATED',
                    'execution_permission': False}, []
        return w.transact('project.new', request_key, {'project': project}, create)

    def source(self, project, snapshot, policy, request_key):
        w = self.workspace(project)
        inspect(snapshot)
        schema = json.loads((core.FROZEN / 'checker001/SOURCE_SNAPSHOT_V1.schema.json').read_text())
        require(isinstance(snapshot, dict) and snapshot.get('schema') == schema['properties']['schema']['const'],
                'MIGRATION_REQUIRED', '/snapshot/schema')
        errors = list(Draft202012Validator(schema).iter_errors(snapshot))
        if errors:
            e = errors[0]
            raise AssuranceError('SOURCE_SCHEMA_INVALID', '/snapshot/' + '/'.join(map(str, e.path)), e.message)
        require(isinstance(snapshot.get('content_utf8'), str), 'SOURCE_BYTES_REQUIRED')
        require(len(snapshot['content_utf8'].encode()) <= MAX_JSON_BYTES // 2, 'SOURCE_TOO_LARGE')
        require(core.byte_digest(snapshot['content_utf8'].encode()) == snapshot['sha256'], 'SOURCE_SHA_MISMATCH')
        require(bool(snapshot['rights'].get('origin')), 'SOURCE_RIGHTS_ORIGIN_REQUIRED')
        safe_source_schema(snapshot)
        validate('publication-policy', policy)
        artifact = {'schema': 'lm-suti.assurance.source/0.1', 'project': project,
                    'snapshot': snapshot, 'publication_policy': policy}
        def save(rows):
            ref = w.put(artifact)
            return {'source_ref': ref, 'snapshot_digest': digest(snapshot),
                    'source_id': snapshot['source_id'], 'execution_permission': False}, [ref]
        return w.transact('source.add', request_key, artifact, save)

    def task(self, project, artifact, request_key):
        validate('task', artifact)
        require(artifact['project'] == project, 'CROSS_PROJECT_REFERENCE')
        w = self.workspace(project)
        def save(rows):
            t = artifact['task']
            require(t['scope']['task_id'] == t['task_id'], 'TASK_SCOPE_ID_MISMATCH')
            require(set(t['source_ids']) == set(t['scope']['source_snapshots']), 'SOURCE_BINDINGS_INCOMPLETE')
            sources = self._sources(w, rows, t)
            require(len(sources) == len(t['source_ids']), 'MISSING_SOURCE_DEPENDENCY')
            for source in sources.values():
                schema_id = source.get('schema_id')
                if schema_id:
                    require(schema_id in sources, 'SOURCE_SCHEMA_MISSING')
                    require(sources[schema_id].get('kind') == 'schema', 'SCHEMA_SOURCE_KIND_REQUIRED')
                    safe_source_schema(sources[schema_id])
            ref = w.put(artifact)
            return {'task_ref': ref, 'task_id': t['task_id'], 'review_status': 'DRAFT',
                    'execution_permission': False}, [ref]
        return w.transact('task.import', request_key, artifact, save)

    def review(self, project, task_ref, actor, reason, request_key):
        require(isinstance(actor, str) and bool(actor.strip()), 'REVIEW_ACTOR_REQUIRED')
        require(isinstance(reason, str) and bool(reason.strip()), 'REVIEW_REASON_REQUIRED')
        w = self.workspace(project)
        payload = {'task_ref': task_ref, 'actor': actor, 'reason': reason}
        def save(rows):
            self._known(rows, 'task.import', 'task_ref', task_ref)
            t = w.get(task_ref)
            require(t['project'] == project, 'CROSS_PROJECT_REFERENCE')
            # Explicit confirmation freezes the *entire* task, not just its title.
            record = {**payload, 'schema': 'lm-suti.assurance.task-review/0.1',
                      'project': project, 'scope_digest': digest(t['task']['scope']),
                      'assumptions_digest': digest(t['task']['assumptions']), 'execution_permission': False}
            ref = w.put(record)
            return {'review_ref': ref, 'task_ref': task_ref, 'review_status': 'REVIEWED',
                    'execution_permission': False}, [ref]
        return w.transact('task.review', request_key, payload, save)

    def candidate(self, project, artifact, request_key):
        validate('candidate', artifact)
        require(artifact['project'] == project, 'CROSS_PROJECT_REFERENCE')
        w = self.workspace(project)
        def save(rows):
            self._known(rows, 'task.import', 'task_ref', artifact['task_ref'])
            if artifact.get('supersedes'):
                self._known(rows, 'candidate.import', 'candidate_ref', artifact['supersedes'])
            # Untrusted raw submissions survive even when parsing/checking fails.
            ref = w.put(artifact)
            return {'candidate_ref': ref, 'status': 'PROPOSED', 'execution_permission': False}, [ref]
        return w.transact('candidate.import', request_key, artifact, save)

    def check(self, project, candidate_ref, engine, request_key):
        require(engine in ('direct', 'compiled'), 'UNKNOWN_EVALUATOR')
        w = self.workspace(project)
        payload = {'candidate_ref': candidate_ref, 'engine': engine}
        def evaluate(rows):
            self._known(rows, 'candidate.import', 'candidate_ref', candidate_ref)
            record = w.get(candidate_ref)
            task_ref = record['task_ref']
            require(any(r['action'] == 'task.review' and r['result']['task_ref'] == task_ref for r in rows),
                    'TASK_REVIEW_REQUIRED')
            task = w.get(task_ref)['task']
            sources = self._sources(w, rows, task)
            evaluated = evaluate_record(record, task, sources, engine)
            ref = w.put({'schema': 'lm-suti.assurance.check/0.1', 'project': project,
                         **payload, **evaluated})
            return {'check_ref': ref, 'candidate_ref': candidate_ref, 'status': evaluated['status'],
                    'reason_code': evaluated['reason_code'], 'execution_permission': False}, [ref]
        return w.transact('check', request_key, payload, evaluate)

    @staticmethod
    def _known(rows, action, field, ref):
        require(any(r['action'] == action and r['result'].get(field) == ref for r in rows),
                'REFERENCE_NOT_IN_PROJECT', '/' + field)

    @staticmethod
    def _sources(w, rows, task):
        sources = {}
        for row in rows:
            if row['action'] != 'source.add':
                continue
            artifact = w.get(row['result']['source_ref'])
            s = artifact['snapshot']; sid = s['source_id']
            if sid in task['source_ids'] and digest(s) == task['scope']['source_snapshots'].get(sid):
                sources[sid] = s
        require(set(sources) == set(task['source_ids']), 'MISSING_SOURCE_DEPENDENCY')
        return sources


def evaluate_record(record, task, sources, engine):
    binding = None
    candidate = None
    try:
        parsed = parse(record['raw'])
        require(isinstance(parsed, dict), 'CANDIDATE_OBJECT_REQUIRED')
        expected_schema = ('symseq.assurance.proposal-delta.v1' if record['format'] == 'delta'
                           else 'symseq.assurance.candidate.v1')
        if parsed.get('schema') is not None and parsed['schema'] != expected_schema:
            raise AssuranceError('MIGRATION_REQUIRED', '/raw/schema', {'expected': expected_schema})
        if record['format'] == 'delta':
            binding = core.compile_delta(record['raw'], task, sources,
                {'call_id': 'manual:' + digest(record)[:16], 'kind': 'SYMBOLIC',
                 'model_id': 'manual-import', 'config_digest': digest({'adapter': 'manual/0.1'})})
            candidate = binding['candidate']
            if candidate is None:
                return {'status': 'NO_PROPOSAL', 'reason_code': 'MODEL_ABSTAINED',
                        'binding': binding, 'candidate': None, 'decision': None, 'witnesses': {}}
        else:
            candidate = parsed
        decision, witnesses = core.check(candidate, task, sources, engine)
        require(decision['assurance_status'] != 'PROVED_FORMAL', 'FORMAL_ADAPTER_UNAVAILABLE')
        return {'status': decision['assurance_status'], 'reason_code': decision['reason_code'],
                'binding': binding, 'candidate': candidate, 'decision': decision, 'witnesses': witnesses}
    except AssuranceError as exc:
        return {'status': exc.status, 'reason_code': exc.code, 'validation_error': exc.as_dict(),
                'binding': binding, 'candidate': candidate, 'decision': None, 'witnesses': {}}
    except core.module('proposal_schema').ProposalError as exc:
        return {'status': 'HOLD', 'reason_code': exc.reason, 'binding': binding,
                'candidate': candidate, 'decision': None, 'witnesses': {}}
