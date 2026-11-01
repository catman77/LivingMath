"""Staging-only registration and append-only projections; no automatic migrations."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import time
from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011_store import assert_isolated, connect, scope
from engine017_contract import SourceEnvelope017, source_identity


def content_material(spec, observations):
    from typed_cycle011 import ordinal_parameters
    return {'parameters': ordinal_parameters(spec['parameters']),
        'observations': {k: observations[k] for k in ('origin', 'transitions', 'executed_words')},
        'observer': spec['observer']}

TABLES = {
    'engine017_sources': 'project TEXT NOT NULL, version INTEGER NOT NULL, source_id TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, binding_json TEXT NOT NULL, PRIMARY KEY(project,version)',
    'engine017_requests': 'project TEXT NOT NULL, request_key TEXT NOT NULL, intent_sha256 TEXT NOT NULL, precommit_id INTEGER NOT NULL REFERENCES typed011_precommits(id), PRIMARY KEY(project,request_key)',
    'engine017_projections': 'id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, version INTEGER NOT NULL, receipt_id INTEGER NOT NULL UNIQUE REFERENCES typed011_receipts(id), payload_json TEXT NOT NULL, UNIQUE(project,version)',
}


def install(database):
    assert_isolated(database)
    with connect(database, True) as c:
        for name, columns in TABLES.items():
            c.execute('CREATE TABLE IF NOT EXISTS ' + name + '(' + columns + ')')
            for action in ('UPDATE', 'DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT,'engine017 append-only'); END")


def registered(c, project):
    row = c.execute('SELECT * FROM engine017_sources WHERE project=? ORDER BY version DESC LIMIT 1', (project,)).fetchone()
    if row is None:
        raise ValueError('SOURCE_CONTRACT_NOT_REGISTERED')
    return json.loads(row['payload_json']), json.loads(row['binding_json'])


def register(database, envelope, binding):
    """Local owner only. The envelope contains no executable capability."""
    envelope = SourceEnvelope017.model_validate(envelope).model_dump()
    project = envelope['project']
    if not project.startswith('LM_QA_TYPED011_ENGINE017_'):
        raise ValueError('017_STAGING_NAMESPACE_REQUIRED')
    store = ResearchStore(database)
    with connect(database, True) as c:
        accepted = scope(c, project)
        root = c.execute('SELECT * FROM events WHERE id=? AND project=?', (binding['root_event_id'], project)).fetchone()
        if not root:
            raise ValueError('FOREIGN_SOURCE_ROOT')
        content = json.loads(root['content'])
        spec = content['source_spec']
        observation = c.execute('SELECT content FROM events WHERE id=? AND project=?', (content['observations_event_id'], project)).fetchone()
        if not observation:
            raise ValueError('INCOMPLETE_SOURCE_PAYLOAD')
        material = content_material(spec, json.loads(observation[0]))
        if envelope['content_sha256'] != digest(material):
            raise ValueError('SOURCE_CONTENT_HASH_MISMATCH')
        if (envelope['scope'], envelope['version'], envelope['observer']) != (spec['scope'], spec['version'], spec['observer']):
            raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER')
        if (envelope['native_definition_sha256'], envelope['operation_definition_sha256']) != (accepted['native_definition_sha256'], accepted['operation_definition_sha256']):
            raise ValueError('SOURCE_DEFINITION_REBIND')
        operations = envelope['operations']
        if [op['ordinal'] for op in operations] != list(range(spec['parameters']['arity'])) or [op['name'] for op in operations] != spec['parameters']['actions']:
            raise ValueError('ORDERED_OPERATIONS_MISMATCH')
        if any(op['definition_sha256'] != envelope['native_definition_sha256'] for op in operations):
            raise ValueError('OPERATION_DEFINITION_REBIND')
        if len(bytes.fromhex(binding['executor_public_key'])) != 32 or len(binding['executor_sha256']) != 64:
            raise ValueError('EXECUTOR_IDENTITY_REQUIRED')
        if accepted['executor_code_sha256'] != binding['executor_sha256']:
            raise ValueError('EXECUTOR_CODE_REBIND')
        current = store.frontier._obligation(c, binding['obligation_id'])
        if (current['project'], current['scope'], current['version']) != (project, envelope['scope'], envelope['version']):
            raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER')
        prior = c.execute('SELECT * FROM engine017_sources WHERE project=? AND version=?', (project, envelope['version'])).fetchone()
        payload, data = canonical(envelope), canonical(binding)
        if prior:
            if prior['payload_json'] != payload or prior['binding_json'] != data:
                raise ValueError('IMMUTABLE_SOURCE_REGISTRATION_CONFLICT')
            return {'idempotent': True, 'manifest_sha256': prior['manifest_sha256']}
        # Registered family identity is source-owned, independent of labels/versions.
        if binding['source_identity'] != source_identity(envelope):
            raise ValueError('SOURCE_IDENTITY_MISMATCH')
        c.execute('INSERT INTO engine017_sources VALUES (?,?,?,?,?,?)',
            (project, envelope['version'], envelope['source_id'], digest(envelope), payload, data))
        store._audit(c, 'engine017_source_registered', {'project': project, 'source_id': envelope['source_id'],
            'version': envelope['version'], 'manifest_sha256': digest(envelope), 'identity': binding['source_identity']})
    return {'idempotent': False, 'manifest_sha256': digest(envelope)}


@contextmanager
def proposal_lock(database):
    # Short lock across existing014's transaction boundaries; process-crash safe.
    path = Path(str(Path(database).resolve()) + '.017-proposal.lock')
    with path.open('a') as lock:
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start > 10:
                    raise ValueError('PROPOSAL_LOCK_TIMEOUT')
                time.sleep(.01)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def project_feedback(c, project, receipt_id, pc, env):
    """Called INSIDE the operator's receipt/journal transaction, never by a model."""
    prior = c.execute('SELECT * FROM engine017_projections WHERE project=? ORDER BY version DESC LIMIT 1', (project,)).fetchone()
    previous = json.loads(prior['payload_json']) if prior else {}
    root = json.loads(c.execute('SELECT content FROM events WHERE id=? AND project=?',
        (pc['native_request']['question']['root_event_id'], project)).fetchone()[0])
    original = [h['ref'] for h in root['source_spec']['hypotheses'] if h['question'] == 'current' and h['predictive']]
    outcome = env['outcome']
    matched, excluded = [], []
    if outcome in ('SUCCESS', 'FAILURE') and pc['purpose'] == 'DISCRIMINATE':
        for alternative in pc['alternatives']:
            ref = alternative.get('source_ref')
            if ref:
                (matched if alternative['readout'] == env['observed'] else excluded).append(ref)
    wait = 'AWAITING_INCONCLUSIVE_EVIDENCE' if outcome == 'INCONCLUSIVE' else 'ERROR_REQUIRES_OPERATOR_REVIEW' if outcome == 'ERROR' else None
    review = outcome == 'FAILURE' and (pc['purpose'] == 'VALIDATE_TRANSFER' or not matched)
    version = (prior['version'] if prior else 0) + 1
    payload = {'version': version, 'source_version': pc['obligation_version'], 'receipt_id': receipt_id,
        'outcome': outcome, 'purpose': pc['purpose'], 'state': wait or ('REQUIRES_REVIEW' if review else 'FEEDBACK_PROJECTED'),
        'applicability': {'retained': matched if matched else previous.get('applicability', {}).get('retained', original),
            'excluded': sorted(set(previous.get('applicability', {}).get('excluded', []) + excluded)),
            'independent_branch_preserved': True, 'not_global_refutation': True},
        'measurement_event_id': env.get('event_id'), 'proof_status': 'unverified'}
    c.execute('INSERT INTO engine017_projections(project,version,receipt_id,payload_json) VALUES (?,?,?,?)',
        (project, version, receipt_id, canonical(payload)))
    return payload
