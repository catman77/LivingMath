"""Pinned local source instrument. Never imported or exposed by the MCP server."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011 import TypedCycle, ordinal_parameters
from typed_cycle011_store import assert_isolated, connect, scope
from law_validation014_contract import Envelope014
from law_validation014_native import native_sha
from engine017_store import registered
from engine017_measurement import calculate, outcome_of
import engine017_measurement


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_grant(database, project, move_id):
    """All public binding checks precede opening environment/private key."""
    assert_isolated(database)
    with connect(database) as c:
        accepted = scope(c, project)
        manifest, binding = registered(c, project)
        row = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?', (move_id, project)).fetchone()
        activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
        if not row or not activation:
            raise ValueError('NO_TYPED_ACTIVATION')
        if c.execute('SELECT 1 FROM typed011_executions WHERE move_id=?', (move_id,)).fetchone():
            raise ValueError('EXECUTION_ALREADY_CONSUMED')
        pc = json.loads(row['payload_json'])
        if digest(pc) != row['digest']:
            raise ValueError('PRECOMMIT_PAYLOAD_DIGEST_MISMATCH')
        TypedCycle._sources_current(c, pc)
        if sha(__file__) != accepted['executor_code_sha256'] or sha(__file__) != binding['executor_sha256']:
            raise ValueError('EXECUTOR_CODE_DRIFT')
        if sha(engine017_measurement.__file__) != binding['measurement_code_sha256']:
            raise ValueError('INSTRUMENT_CODE_DRIFT')
        if native_sha() != pc['native_definition_sha256'] or native_sha() != manifest['native_definition_sha256']:
            raise ValueError('NATIVE_DEFINITION_DRIFT')
        reader = ResearchStore.__new__(ResearchStore)
        reader.path = Path(database)
        view = reader.moves._view(c, reader.moves._row(c, project, move_id))
        if not view['execution_permission']['allowed'] or view['audits'][-1]['id'] != activation['audit_id']:
            raise ValueError('STALE_OR_WRONG_TYPED_GRANT')
        latest = view['history'][-1]
        op = c.execute('SELECT * FROM operations WHERE id=?', (activation['operation_id'],)).fetchone()
        data = json.loads(op['details_json']) if op else {}
        if not op or op['action'] != 'research_move_status_changed' or any(data.get(k) != v for k, v in
            {'move_id': move_id, 'status': 'EXPERIMENT_ALLOWED', 'audit_id': activation['audit_id'], 'sequence': latest['sequence']}.items()):
            raise ValueError('ACTIVATION_OPERATION_MISMATCH')
        if data['decision_sha256'] != digest(latest['decision']):
            raise ValueError('ACTIVATION_DECISION_MISMATCH')
        preview = json.loads(row['preview_json'])
        root = json.loads(c.execute('SELECT content FROM events WHERE id=? AND project=?', (binding['root_event_id'], project)).fetchone()[0])
        spec = root['source_spec']
        if pc['observer'] != manifest['observer'] or pc['observer'] != spec['observer']:
            raise ValueError('OBSERVER_REBIND')
        if pc['test_id'] != preview['selected_test']['test_id'] or pc['suffix'] != preview['selected_test']['suffix']:
            raise ValueError('TEST_OR_SUFFIX_REBIND')
        if pc['suffix'] != [spec['parameters']['actions'][a] for a in pc['suffix_ordinals']]:
            raise ValueError('ORDERED_SUFFIX_REBIND')
        if pc['operation_definition_sha256'] != digest(ordinal_parameters(spec['parameters'])):
            raise ValueError('OPERATION_DEFINITION_REBIND')
    return dict(row), dict(activation), pc, accepted, manifest, binding


def execute(database, project, move_id, environment_file, private_key_file):
    row, activation, pc, accepted, manifest, binding = checked_grant(database, project, move_id)
    raw = Path(environment_file).read_bytes()
    if hashlib.sha256(raw).hexdigest() != accepted['environment_sha256']:
        raise ValueError('ENVIRONMENT_COMMITMENT_DRIFT')
    environment = json.loads(raw)
    if environment['project'] != project:
        raise ValueError('WRONG_NATIVE_SOURCE')
    parameters = {**environment['declaration'], 'actions': ['a' + str(i) for i in range(environment['declaration']['arity'])]}
    if digest(ordinal_parameters(parameters)) != pc['operation_definition_sha256']:
        raise ValueError('WRONG_REGISTERED_SOURCE')
    if pc['purpose'] == 'VALIDATE_TRANSFER' and environment['target_word'] != pc['context_word']:
        raise ValueError('ENVIRONMENT_OUTSIDE_CONTEXT')
    key = Ed25519PrivateKey.from_private_bytes(Path(private_key_file).read_bytes())
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    if key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex() != binding['executor_public_key']:
        raise ValueError('EXECUTOR_SIGNING_KEY_MISMATCH')
    attempt = calculate(environment['declaration'], environment['target_word'], pc['suffix_ordinals'], pc['observer'], environment['mode'])
    outcome = outcome_of(attempt, pc, environment['mode'])
    body = {'protocol': 'source-attempt017/v1', 'source_manifest_sha256': digest(manifest),
        'precommit_sha256': row['digest'], 'move_id': move_id, 'environment': environment, 'attempt': attempt}
    artifact = {'schema': 'signed-native017/v1', 'precommit_sha256': row['digest'], 'move_id': move_id,
        'observed': attempt['observed'], 'observed_coordinate': attempt['coordinate'], 'outcome': outcome,
        'source_receipt': body, 'signature': key.sign(canonical(body).encode()).hex(), 'proof_status': 'unverified'}
    path = Path(accepted['artifact_directory']) / ('move-' + str(move_id) + '.json')
    with path.open('x') as stream:
        stream.write(canonical(artifact))
    env = {k: pc[k] for k in ('project', 'proposal_fingerprint', 'obligation_id', 'obligation_version', 'scope', 'source_family_id',
        'source_bindings', 'native_definition_sha256', 'operation_definition_sha256', 'observer', 'test_id', 'suffix', 'suffix_ordinals',
        'purpose', 'law_fingerprint', 'context_word')}
    env.update(precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id, audit_id=activation['audit_id'],
        activation_operation_id=activation['operation_id'], predictions=pc['alternatives'], observed=attempt['observed'],
        observed_coordinate=attempt['coordinate'], outcome=outcome, executor_id='qa.external.native011/v1',
        executor_code_sha256=sha(__file__), artifact_sha256=sha(path),
        summary='Source-bound native017 attempt: ' + outcome + '; never mathematical verification.',
        reason='Fresh authorized instrument attempt; inspection=' + attempt['quality'])
    envelope = Envelope014.model_validate(env).model_dump()
    content = {'claim_type': 'EXPERIMENT_RESULT', 'statement': env['summary'], 'scope': pc['scope'],
        'version': pc['obligation_version'], 'outcome': outcome, 'proof_status': 'unverified', 'measurement_binding': envelope,
        'observation': {'test_id': pc['test_id'], 'readout': attempt['observed'], 'scope': pc['scope'],
            'version': pc['obligation_version'], 'observer': pc['observer']}}
    # Recheck after source read; a concurrently superseded grant cannot publish evidence.
    checked_grant(database, project, move_id)
    store = ResearchStore(database)
    event = store.record(project, 'counterexample' if outcome == 'FAILURE' else 'experiment', 'Signed native017 attempt',
        canonical(content), 'experiment', parent_id=pc['native_request']['question']['root_event_id'], request_key='017:measurement:' + str(move_id))
    local = {'artifact_path': str(path), 'artifact_sha256': sha(path), 'envelope_sha256': digest(envelope)}
    with connect(database, True) as c:
        TypedCycle._sources_current(c, pc)
        c.execute('INSERT INTO typed011_executions VALUES (?,?,?)', (move_id, event['id'], canonical(local)))
        store._audit(c, 'typed011_executor_receipt', {'move_id': move_id, 'event_id': event['id'], 'digest': digest(local)})
    return {'event_id': event['id'], 'envelope': envelope, 'artifact_path': str(path), 'quality': attempt['quality']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    try:
        print(canonical({'ok': True, 'result': execute(args.db, **json.loads(sys.stdin.read(65537)))}))
    except (ValueError, KeyError, OSError) as error:
        print(canonical({'ok': False, 'error': str(error)}))
        raise SystemExit(2)
