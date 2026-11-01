"""Human-readable reverse mapping, retaining losses and independent branches."""
from .canonical import canonical_hash, statuses


def reverse(envelope: dict, projection: dict, audited: dict) -> dict:
    losses = [x for x in audited['loss_ledger'] if x['state'] != 'PRESERVED']
    explanation = [
        'Investigated: ' + projection['candidate']['question'],
        'Declared model: ' + projection['candidate']['model_kind'],
        'Operation order: ' + ' -> '.join(projection['operation_order']),
        'Each retained declaration has an exact source address; this does not prove author recognition.',
        'Losses/uncertainties: ' + ('; '.join(x['id'] + ': ' + x['state'] + ' (' + x['reason'] + ')' for x in losses) or 'No declared structural loss; reader meaning remains unreviewed.'),
        'Mandatory-loss refusal: ' + ', '.join(audited['mandatory_losses']),
        'Possible substitution: ' + '; '.join(audited['failure_reasons']),
        'Author review: ' + audited['author_review_status'],
        'No new theorem, mathematical verification or permission to execute LivingMath follows from this local demo.',
    ]
    return {'explanation': '\n'.join(explanation), 'loss_ledger': audited['loss_ledger'],
            'source_ref': envelope['X']['source_ref'], 'revision': envelope['revision'],
            'source_id': envelope['source_id'], 'projection_sha256': canonical_hash(projection),
            'observed': projection['observations'], 'review_options': ['RECOGNIZED', 'PARTIAL', 'REJECTED', 'NO_REVIEW'],
            **statuses(semantic=audited['semantic_status'], mathematical=audited['mathematical_status'],
                       execution=audited['execution_status'], author=audited['author_review_status'],
                       provenance=audited['source_provenance'], unknowns=audited['unknowns'])}
