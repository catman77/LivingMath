"""Proposed local opaque import. Never infer that a file came from SUTI.

No SUTI schema is approved: even authentic byte preservation cannot establish
semantic fidelity. Source bytes and unknown fields remain available unchanged.
"""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .shared import ROOT, Refusal, bytes_hash, canonical_bytes, canonical_hash, check_signature, read_json, statuses

MAX_RAW_BYTES = 4_000_000


def verify_declaration(raw: bytes, declaration: dict, trust: dict) -> dict:
    if not raw or len(raw) > MAX_RAW_BYTES or len(canonical_bytes(declaration)) > 262144:
        raise Refusal('INPUT_BYTE_BOUND')
    schema = read_json(ROOT / 'schemas/intake-proposal.json')
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(declaration))
    if errors:
        raise Refusal('PROPOSAL_SCHEMA_REJECTED', errors[0].message)
    source, rights = declaration['source'], declaration['rights']
    if source['sha256'] != bytes_hash(raw) or source['bytes'] != len(raw):
        raise Refusal('RAW_SOURCE_DRIFT')
    if not {'local_experiment', 'private_storage'} <= set(rights['allowed_uses']):
        raise Refusal('RIGHTS_NOT_GRANTED')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(rights['retention_until'].replace('Z', '+00:00')):
        raise Refusal('CONSENT_EXPIRED')
    signature = declaration['consent']
    body = {k: v for k, v in declaration.items() if k != 'consent'}
    key = check_signature(body, signature['signature_hex'], signature['key_id'], trust,
                          'source_owner', source['id'])
    if key['identity'] != rights['owner_id']:
        raise Refusal('OWNER_IDENTITY_MISMATCH')
    if declaration['origin']['producer'] == 'SYNTHETIC' and key.get('kind') != 'fixture':
        raise Refusal('SYNTHETIC_ORIGIN_MUST_REMAIN_EXPLICIT')
    if declaration['origin']['producer'] == 'SUTI' and key.get('kind') != 'owner_pinned':
        raise Refusal('FIXTURE_KEY_CANNOT_ATTEST_REAL_SOURCE')
    return {'byte_sha256': bytes_hash(raw), 'declaration_sha256': canonical_hash(declaration),
            'owner_identity': key['identity'], 'declared_origin': declaration['origin']['producer'],
            'real_SUTI_origin_verified': False, 'profile_status': 'AWAITING_SUTI_APPROVAL'}


def verify_journal(rows: list[dict]) -> str:
    previous = '0' * 64
    for index, row in enumerate(rows):
        body = {k: v for k, v in row.items() if k != 'sha256'}
        if row['index'] != index or row['previous_sha256'] != previous or canonical_hash(body) != row['sha256']:
            raise Refusal('IMPORT_JOURNAL_DRIFT')
        previous = row['sha256']
    return previous


def immutable_write(path: Path, raw: bytes) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != raw:
            raise Refusal('IMMUTABLE_OBJECT_DRIFT', path.name)
        return
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def ingest(raw: bytes, declaration: dict, trust: dict, state: Path, request_key: str) -> dict:
    checked = verify_declaration(raw, declaration, trust)
    if not request_key.strip() or len(request_key) > 128:
        raise Refusal('INVALID_REQUEST_KEY')
    state = state.resolve()
    if state.is_relative_to(ROOT) or state.is_relative_to(ROOT.parent / 'bridge001'):
        raise Refusal('PRIVATE_SOURCE_STORAGE_REQUIRED')
    if state.exists() and any(state.iterdir()) and not (state / '.bridge002-state').is_file():
        raise Refusal('EXISTING_NON_BRIDGE_STATE_FORBIDDEN')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_mode & 0o077:
        raise Refusal('STATE_MUST_BE_OWNER_ONLY')
    immutable_write(state / '.bridge002-state', b'OPAQUE_BRIDGE002_PRIVATE_STATE\n')
    for name in ('raw', 'declarations', 'receipts'):
        (state / name).mkdir(mode=0o700, exist_ok=True)
    intent = checked['declaration_sha256']
    with (state / 'journal.jsonl').open('a+', encoding='utf-8') as stream:
        os.chmod(state / 'journal.jsonl', 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        rows = [json.loads(line) for line in stream if line.strip()]
        previous = verify_journal(rows)
        for row in rows:
            if row['request_key'] == request_key:
                if row['intent_sha256'] != intent:
                    raise Refusal('REQUEST_KEY_CONFLICT')
                receipt = read_json(state / 'receipts' / (row['receipt_sha256'] + '.json'))
                if canonical_hash(receipt) != row['receipt_sha256']:
                    raise Refusal('RECEIPT_DRIFT')
                if bytes_hash((state / 'raw' / (checked['byte_sha256'] + '.bin')).read_bytes()) != checked['byte_sha256']:
                    raise Refusal('RAW_SOURCE_DRIFT')
                return {**receipt, 'idempotent': True}
        same_source = [r for r in rows if r['source_id'] == declaration['source']['id']]
        if same_source and declaration['source']['revision'] <= max(r['revision'] for r in same_source):
            raise Refusal('REVISION_REPLAY_OR_PAYLOAD_CONFLICT')
        ledger = [{'section': section, 'source_item_id': item['id'], 'state': 'UNKNOWN',
                   'source_item_sha256': canonical_hash(item), 'reason': 'Opaque preservation is not a semantic mapping.',
                   'must_preserve': item['must_preserve'], 'admissible_for_audit': False}
                  for section in ('D', 'R', 'T', 'O') for item in declaration['annotations'][section]]
        receipt = {'status': 'OPAQUE_INGEST_ONLY', **checked, 'source_id': declaration['source']['id'],
                   'revision': declaration['source']['revision'], 'loss_ledger': ledger,
                   'source_roundtrip': {'status': 'BYTES_PRESERVED_ONLY', 'source_sha256': checked['byte_sha256']},
                   'opaque_extension_sha256': canonical_hash(declaration['opaque_extensions']),
                   'G1_SOURCE_FIDELITY': 'NOT_RUN', 'native_status': 'PENDING_ADAPTER_REVIEW',
                   **statuses(semantic='INSUFFICIENT_CONTRACT' if not declaration['annotations']['D'] else 'UNKNOWN',
                              execution='LOCAL_OPAQUE_IMPORT_ONLY', author='NO_REVIEW',
                              provenance={'raw_sha256': checked['byte_sha256'], 'declaration_sha256': intent},
                              unknowns=['No approved SUTI export reader, semantic mapping or author recognition.'])}
        digest = canonical_hash(receipt)
        immutable_write(state / 'raw' / (checked['byte_sha256'] + '.bin'), raw)
        immutable_write(state / 'declarations' / (intent + '.json'), canonical_bytes(declaration))
        immutable_write(state / 'receipts' / (digest + '.json'), canonical_bytes(receipt))
        body = {'index': len(rows), 'previous_sha256': previous, 'source_id': receipt['source_id'],
                'revision': receipt['revision'], 'request_key': request_key, 'intent_sha256': intent,
                'receipt_sha256': digest}
        stream.seek(0, 2);stream.write(json.dumps({**body, 'sha256': canonical_hash(body)}) + '\n')
        stream.flush();os.fsync(stream.fileno())
        return {**receipt, 'idempotent': False}


def restore_raw(state: Path, declaration_sha256: str, destination: Path, trust: dict) -> dict:
    if len(declaration_sha256) != 64 or any(c not in '0123456789abcdef' for c in declaration_sha256):
        raise Refusal('INVALID_SOURCE_HASH')
    declaration = read_json(state / 'declarations' / (declaration_sha256 + '.json'))
    if canonical_hash(declaration) != declaration_sha256:
        raise Refusal('DECLARATION_DRIFT')
    source_sha256 = declaration['source']['sha256']
    path = state / 'raw' / (source_sha256 + '.bin')
    raw = path.read_bytes()
    verify_declaration(raw, declaration, trust)
    if (destination.resolve().is_relative_to(ROOT.parent)
            or destination.parent.stat().st_mode & 0o077):
        raise Refusal('PRIVATE_RESTORE_DESTINATION_REQUIRED')
    immutable_write(destination, raw)
    return {'status': 'EXACT_BYTES_RESTORED_ONLY', 'source_sha256': source_sha256,
            'semantic_fidelity': 'NOT_RUN', 'real_SUTI_integration': 'NOT_TESTED'}
