"""Only an owner-pinned human review may recognize a real explanation."""
from .shared import Refusal, canonical_hash, check_signature


def validate_review(receipt: dict, declaration: dict, explanation: dict, trust: dict) -> dict:
    fields = {'source_sha256', 'revision', 'explanation_sha256', 'explanation_version',
              'reviewer_id', 'decision', 'reason', 'key_id', 'signature_hex'}
    if set(receipt) != fields or receipt['decision'] not in ('RECOGNIZED', 'PARTIAL', 'REJECTED', 'NO_REVIEW'):
        raise Refusal('REVIEW_SCHEMA_REJECTED')
    if (receipt['source_sha256'] != declaration['source']['sha256']
            or receipt['revision'] != declaration['source']['revision']
            or receipt['explanation_sha256'] != canonical_hash(explanation)
            or receipt['explanation_version'] != explanation['version']):
        raise Refusal('REVIEW_SOURCE_REVISION_EXPLANATION_DRIFT')
    if not isinstance(receipt['reason'], str) or not receipt['reason'].strip():
        raise Refusal('REVIEW_REASON_REQUIRED')
    body = {k: v for k, v in receipt.items() if k != 'signature_hex'}
    entry = check_signature(body, receipt['signature_hex'], receipt['key_id'], trust,
                            'author', declaration['source']['id'])
    if (entry.get('kind') != 'owner_pinned' or entry['identity'] != receipt['reviewer_id']
            or entry['identity'] not in declaration['authorized_reviewers']):
        raise Refusal('FIXTURE_OR_UNAUTHORIZED_AUTHOR_REVIEW')
    return {'author_review_status': receipt['decision'], 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}, 'receipt_sha256': canonical_hash(receipt),
            'joint_GO_established': False}
