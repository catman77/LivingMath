"""017 semantic measurement check layered on every immutable014 binding check."""
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from normalizer import canonical, digest
from law_validation014_receipt import ReceiptValidator014
from engine017_store import registered
from engine017_measurement import calculate, outcome_of
import engine017_measurement


class ReceiptValidator017(ReceiptValidator014):
    def validate_in(self, c, project, move_id, event_id):
        result = super().validate_in(c, project, move_id, event_id)
        if result['status'] != 'VALID_BOUND_MEASUREMENT':
            return result
        manifest, binding = registered(c, project)
        if hashlib.sha256(Path(engine017_measurement.__file__).read_bytes()).hexdigest() != binding['measurement_code_sha256']:
            raise ValueError('INSTRUMENT_CODE_DRIFT')
        local = c.execute('SELECT payload_json FROM typed011_executions WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()
        artifact = json.loads(Path(json.loads(local[0])['artifact_path']).read_text())
        body = artifact['source_receipt']
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(binding['executor_public_key'])).verify(
                bytes.fromhex(artifact['signature']), canonical(body).encode())
        except InvalidSignature as error:
            raise ValueError('EXECUTOR_SIGNATURE_INVALID') from error
        pc_row = c.execute('SELECT p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (move_id,)).fetchone()
        pc = json.loads(pc_row[0])
        environment = body['environment']
        if set(environment) != {'project', 'declaration', 'target_word', 'mode', 'salt'}:
            raise ValueError('UNREVIEWED_ENVIRONMENT_FIELDS')
        accepted = json.loads(c.execute('SELECT payload_json FROM typed011_scopes WHERE project=?', (project,)).fetchone()[0])
        if hashlib.sha256(canonical(environment).encode()).hexdigest() != accepted['environment_sha256']:
            raise ValueError('ENVIRONMENT_COMMITMENT_MISMATCH')
        if (body['source_manifest_sha256'], body['precommit_sha256'], body['move_id']) != (digest(manifest), result['precommit_sha256'], move_id):
            raise ValueError('SOURCE_RECEIPT_BINDING_MISMATCH')
        root = json.loads(c.execute('SELECT content FROM events WHERE id=?', (binding['root_event_id'],)).fetchone()[0])
        parameters = {**environment['declaration'], 'actions': ['a' + str(i) for i in range(environment['declaration']['arity'])]}
        if parameters != root['source_spec']['parameters'] or environment['project'] != project:
            raise ValueError('WRONG_REGISTERED_SOURCE')
        if pc['purpose'] == 'VALIDATE_TRANSFER' and environment['target_word'] != pc['context_word']:
            raise ValueError('FOREIGN_SOURCE_CONTEXT')
        expected = calculate(environment['declaration'], environment['target_word'], pc['suffix_ordinals'], pc['observer'], environment['mode'])
        if expected != body['attempt'] or outcome_of(expected, pc, environment['mode']) != artifact['outcome']:
            raise ValueError('NATIVE_SEMANTIC_MEASUREMENT_MISMATCH')
        env = result['envelope']
        if (expected['observed'], expected['coordinate'], artifact['outcome']) != (env['observed'], env['observed_coordinate'], env['outcome']):
            raise ValueError('OBSERVATION_ENVELOPE_MISMATCH')
        result.update(reason='All014 structural checks plus signed source commitment and pinned native calculation replay.',
            measurement_authenticity='HASH_BOUND_SIGNED_LOCAL_COMPUTATION; not physical authenticity or mathematical verification',
            inspection_status=expected['quality'], signature_verified=True,
            semantic_measurement_bound=True, source_manifest_sha256=digest(manifest))
        return result
