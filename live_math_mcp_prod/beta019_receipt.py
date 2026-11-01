"""Exact014 structural checks plus actual019 upstream-source and018 lease checks."""
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from normalizer import canonical, digest
from law_validation014_receipt import ReceiptValidator014
from engine017_store import registered
from typed_cycle011 import ordinal_parameters
from engine017_measurement import outcome_of
from deploy018_authority import lease_in
import beta019_source as source


class Receipt019(ReceiptValidator014):
    def validate_in(self, c, project, move_id, event_id):
        result = super().validate_in(c, project, move_id, event_id)
        if result['status'] != 'VALID_BOUND_MEASUREMENT':
            return result
        manifest, binding = registered(c, project)
        if hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest() != binding['measurement_code_sha256'] or source.definition_sha() != manifest['native_definition_sha256']:
            raise ValueError('019_INSTRUMENT_OR_NATIVE_DRIFT')
        local = json.loads(c.execute('SELECT payload_json FROM typed011_executions WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()[0])
        artifact = json.loads(Path(local['artifact_path']).read_text())
        body, env = artifact['source_receipt'], result['envelope']
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(binding['executor_public_key']))
        try:
            key.verify(bytes.fromhex(artifact['signature']), canonical(body).encode())
        except (InvalidSignature, ValueError) as error:
            raise ValueError('019_EXECUTOR_SIGNATURE_INVALID') from error
        lease = lease_in(c, project, move_id)
        if set(body) != {'protocol', 'source_manifest_sha256', 'precommit_sha256', 'move_id', 'lease_sha256', 'environment', 'attempt'} or (
            body['protocol'], body['source_manifest_sha256'], body['precommit_sha256'], body['move_id'], body['lease_sha256']) != (
                'source-attempt019/v1', digest(manifest), result['precommit_sha256'], move_id, digest(lease)):
            raise ValueError('019_SOURCE_RECEIPT_REBIND')
        environment = body['environment']
        if set(environment) != {'project', 'declaration', 'target_word', 'mode', 'salt'} or environment['project'] != project:
            raise ValueError('019_FOREIGN_ENVIRONMENT')
        accepted = json.loads(c.execute('SELECT payload_json FROM typed011_scopes WHERE project=?', (project,)).fetchone()[0])
        if hashlib.sha256(canonical(environment).encode()).hexdigest() != accepted['environment_sha256']:
            raise ValueError('019_ENVIRONMENT_COMMITMENT_MISMATCH')
        row = c.execute('SELECT p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (move_id,)).fetchone()
        pc = json.loads(row[0])
        if digest(ordinal_parameters({**environment['declaration'], 'actions': source.OBJECT['input_symbols']})) != pc['operation_definition_sha256']:
            raise ValueError('019_SOURCE_DEFINITION_REBIND')
        if pc['purpose'] == 'VALIDATE_TRANSFER' and environment['target_word'] != pc['context_word']:
            raise ValueError('019_FOREIGN_SOURCE_CONTEXT')
        actual = source.calculate(environment['declaration'], environment['target_word'], pc['suffix_ordinals'], pc['observer'], environment['mode'])
        if actual != body['attempt'] or outcome_of(actual, pc, environment['mode']) != env['outcome'] or (
                actual['observed'], actual['coordinate']) != (env['observed'], env['observed_coordinate']):
            raise ValueError('019_NATIVE_MEASUREMENT_MISMATCH')
        signed = c.execute('SELECT payload_json FROM deploy018_attestations WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()
        if not signed:
            raise ValueError('019_ATTESTATION_MISSING')
        attestation = json.loads(signed[0])
        expected = {'protocol': 'measurement-attestation018/v1', 'lease': lease, 'event_id': event_id,
            'envelope_sha256': digest(env), 'artifact_sha256': env['artifact_sha256'], 'outcome': env['outcome']}
        if attestation['body'] != expected:
            raise ValueError('019_NONCE_OR_ATTESTATION_REBIND')
        try:
            key.verify(bytes.fromhex(attestation['signature']), canonical(expected).encode())
        except (InvalidSignature, ValueError) as error:
            raise ValueError('019_ATTESTATION_SIGNATURE_INVALID') from error
        return {**result, 'reason': 'Original014 binding/order plus signed019 native source and expiring018 nonce.',
            'measurement_authenticity': 'SIGNED_INDEPENDENT_SOFTWARE_SOURCE; not physical authenticity or mathematical proof',
            'inspection_status': actual['quality'], 'signature_verified': True, 'lease018_verified': True,
            'semantic_measurement_bound': True, 'source_manifest_sha256': digest(manifest), 'proof_status': 'unverified'}
