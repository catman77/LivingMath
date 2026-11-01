"""Independent human recognition receipts; never mathematical verification."""
from .canonical import Refusal, canonical_hash
from .intake import check_signature, validate_schema


def validate_review(receipt: dict, envelope: dict, projection: dict, trust: dict) -> str:
    validate_schema(receipt, 'author-review')
    if (receipt['contract_sha256'] != canonical_hash(envelope)
            or receipt['projection_sha256'] != canonical_hash(projection)
            or receipt['revision'] != envelope['revision']
            or receipt['source_id'] != envelope['source_id']):
        raise Refusal('AUTHOR_REVIEW_BINDING_MISMATCH')
    payload = {k: v for k, v in receipt.items() if k != 'signature_hex'}
    key = check_signature(payload, receipt['signature_hex'], receipt['key_id'], trust,
                          'author', envelope['source_id'])
    if key['identity'] != receipt['reviewer_id'] or key['identity'] != envelope['creator_id']:
        raise Refusal('AUTHOR_REVIEW_IDENTITY_MISMATCH')
    return receipt['decision']
