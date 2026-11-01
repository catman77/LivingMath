"""Strict local intake. Source content is data, never instructions or code."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker

from .canonical import MAX_BYTES, Refusal, bytes_hash, canonical_bytes, canonical_hash, read_json, statuses

ROOT = Path(__file__).resolve().parent.parent


def validate_schema(value, name: str) -> None:
    validator = Draft202012Validator(read_json(ROOT / 'schemas' / (name + '.json')),
                                     format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        raise Refusal('SCHEMA_REJECTED', str(list(errors[0].path)) + ': ' + errors[0].message)


def consent_digest(envelope: dict) -> str:
    unsigned = deepcopy(envelope)
    unsigned['P']['attestations'] = []
    return canonical_hash(unsigned)


def check_signature(payload: dict, signature: str, key_id: str, trust: dict, role: str, source_id: str) -> dict:
    entry = trust.get(key_id)
    if (not entry or entry.get('revoked', True) or role not in entry.get('roles', [])
            or source_id not in entry.get('source_ids', [])):
        raise Refusal('UNTRUSTED_SIGNER_OR_SCOPE', key_id)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry['public_key_hex'])).verify(
            bytes.fromhex(signature), canonical_bytes(payload))
    except Exception as error:
        raise Refusal('SIGNATURE_MISMATCH', key_id) from error
    return entry


def intake(envelope: dict, source_bytes: bytes, trust: dict, purpose: str = 'local_process',
           now: datetime | None = None) -> dict:
    if len(source_bytes) > MAX_BYTES or len(canonical_bytes(envelope)) > MAX_BYTES:
        raise Refusal('INPUT_BYTE_LIMIT')
    validate_schema(envelope, 'contract-envelope')
    if bytes_hash(source_bytes) != envelope['source_hash']:
        raise Refusal('SOURCE_HASH_MISMATCH')
    if envelope['X']['sha256'] != envelope['source_hash']:
        raise Refusal('EXPRESSION_HASH_MISMATCH')
    if purpose not in envelope['rights']['scope']:
        raise Refusal('RIGHTS_SCOPE_DENIED', purpose)
    now = now or datetime.now(timezone.utc)
    if now >= datetime.fromisoformat(envelope['rights']['retention']['expires_at'].replace('Z', '+00:00')):
        raise Refusal('RETENTION_EXPIRED')
    if purpose == 'remote_source' and envelope['rights']['redaction']['mode'] != 'none':
        raise Refusal('REDACTION_REQUIRED_NO_RAW_EXPORT')
    if envelope['P']['revoked_attestation_ids']:
        raise Refusal('CONSENT_REVOKED_REATTEST_REQUIRED')
    if envelope['P']['confirmed_revision'] != envelope['revision']:
        raise Refusal('REVISION_NOT_CONFIRMED')
    digest = consent_digest(envelope)
    consent = False
    for attestation in envelope['P']['attestations']:
        if attestation['contract_sha256'] != digest:
            raise Refusal('CONSENT_BINDING_MISMATCH')
        signed = {k: v for k, v in attestation.items() if k != 'signature_hex'}
        entry = check_signature(signed, attestation['signature_hex'], attestation['key_id'],
                                trust, attestation['role'], envelope['source_id'])
        if entry['identity'] != attestation['identity']:
            raise Refusal('SIGNER_IDENTITY_MISMATCH')
        consent = consent or attestation['role'] in ('operator', 'author')
    if not consent:
        raise Refusal('SIGNED_MANUAL_CONSENT_REQUIRED')
    ids = set()
    distinctions = {d['id'] for d in envelope['D']}
    operations = {t['id'] for t in envelope['T']}
    text = source_bytes.decode('utf-8') if envelope['X']['mime_type'] == 'text/plain' else None
    for section in ('D', 'R', 'T', 'O'):
        for item in envelope[section]:
            if item['id'] in ids:
                raise Refusal('DUPLICATE_SOURCE_LOCAL_ID', item['id'])
            ids.add(item['id'])
            address = item['source_address']
            if address['source_id'] != envelope['source_id']:
                raise Refusal('FOREIGN_SOURCE_ADDRESS')
            if text is not None:
                if address['kind'] != 'text_span':
                    raise Refusal('TEXT_SPAN_KIND_REQUIRED')
                if address['end'] > len(text) or address['start'] >= address['end']:
                    raise Refusal('INVALID_SOURCE_SPAN')
                if text[address['start']:address['end']] != address['quote']:
                    raise Refusal('SOURCE_SPAN_MISMATCH')
            elif address['kind'] != 'opaque':
                raise Refusal('OPAQUE_SOURCE_READER_REQUIRED')
            if not set(item.get('distinction_ids', [])) <= distinctions:
                raise Refusal('UNBOUND_DISTINCTION')
            if section == 'T' and not set(item['composition_order']) <= operations:
                raise Refusal('UNBOUND_OPERATION_ORDER')
    result = {'contract_sha256': canonical_hash(envelope), 'source_hash': envelope['source_hash'],
              'revision': envelope['revision'], 'source_id': envelope['source_id'],
              'intake_status': 'ACCEPTED' if envelope['D'] else 'INSUFFICIENT_CONTRACT',
              'content_forwarded': False}
    result.update(statuses(semantic='PENDING_MAPPING' if envelope['D'] else 'INSUFFICIENT_CONTRACT',
                           provenance={'source_id': envelope['source_id'], 'contract_sha256': canonical_hash(envelope)},
                           unknowns=envelope['unknowns']))
    return result
