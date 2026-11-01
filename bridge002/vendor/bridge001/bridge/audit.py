"""Independent audit recomputes model results; declarations are not evidence."""
from .canonical import Refusal, canonical_hash, read_json, statuses
from .demos import MODEL_KINDS, evaluate
from .intake import ROOT, intake, validate_schema
from .mapping import candidates, fingerprint, project
from .review import validate_review


def audit(envelope: dict, projection: dict, settings: dict, *, source_bytes: bytes,
          trust: dict, review: dict | None = None) -> dict:
    intake(envelope, source_bytes, trust)
    failures, ledger = [], []
    c = projection['candidate']
    validate_schema(c, 'candidate')
    if envelope['X']['declared_reader'] != 'bridge-fixture/' + MODEL_KINDS[c['model_kind']][0]:
        failures.append('UNSUPPORTED_SOURCE_MODEL_BINDING')
    if canonical_hash(settings) != canonical_hash(read_json(ROOT / 'eval/settings.json')):
        failures.append('UNAPPROVED_MODEL_SETTINGS')
    approved_candidate = next(x for x in candidates(envelope, MODEL_KINDS[c['model_kind']][0])
                              if x['model_kind'] == c['model_kind'])
    if any(c[k] != approved_candidate[k] for k in ('question', 'interpretation_kind', 'assumptions')):
        failures.append('UNSUPPORTED_RESEARCH_CLAIM')
    expected_projection = project(envelope, c, settings)
    for field in ('model_family', 'equality_layers', 'recovery_pointer', 'loss_ledger', 'admissible_for_audit',
                  'semantic_status', 'mathematical_status', 'execution_status', 'author_review_status',
                  'source_provenance', 'unknowns', 'schema_version'):
        if projection.get(field) != expected_projection[field]:
            failures.append('PROJECTION_DECLARATION_SUBSTITUTION:' + field)
    if set(projection) != set(expected_projection):
        failures.append('UNQUARANTINED_PROJECTION_EXTENSION')
    binding = {'source_ref': envelope['X']['source_ref'], 'source_id': envelope['source_id'],
               'revision': envelope['revision'], 'contract_sha256': canonical_hash(envelope),
               'source_hash': envelope['source_hash'], 'rights_sha256': canonical_hash(envelope['rights']),
               'observer_id': envelope['observer_id'], 'settings_sha256': canonical_hash(settings)}
    for key, value in binding.items():
        if projection.get(key) != value:
            failures.append('PROJECTION_BINDING_MISMATCH:' + key)
    if (c['contract_sha256'] != binding['contract_sha256'] or c['source_ref'] != binding['source_ref']
            or c['revision'] != binding['revision'] or c['observer_id'] != binding['observer_id']):
        failures.append('CANDIDATE_BINDING_MISMATCH')
    if projection.get('structural_fingerprint') != fingerprint(c):
        failures.append('STRUCTURAL_FINGERPRINT_MISMATCH')
    if projection.get('operation_order') != MODEL_KINDS[c['model_kind']][1]:
        failures.append('NONCOMMUTATIVE_ORDER_SUBSTITUTION')
    expected = evaluate(c['model_kind'], settings)
    if projection.get('observations') != expected:
        failures.append('MODEL_OBSERVATION_SUBSTITUTION')
    if projection.get('proof_status') != 'unverified' or projection.get('execution_permission') != {'allowed': False}:
        failures.append('FALSE_VERIFIED_OR_PERMISSION')
    indexed = {}
    allowed_ids = {(section, item['id']) for section in ('D', 'R', 'T', 'O') for item in envelope[section]}
    for mapped in projection['bindings']:
        key = (mapped['section'], mapped['item_id'])
        if key in indexed or key not in allowed_ids:
            failures.append('DUPLICATE_OR_FOREIGN_MAPPING')
        indexed[key] = mapped
    for section in ('D', 'R', 'T', 'O'):
        for item in envelope[section]:
            mapped = indexed.get((section, item['id']))
            state, reason = 'UNKNOWN', 'No supported independent semantic oracle.'
            if mapped is None:
                state, reason = 'LOST', 'No model binding; source retained by recovery pointer.'
            elif (mapped['source_item_sha256'] != canonical_hash(item)
                  or mapped['source_address'] != item['source_address']
                  or mapped['declared_statement'] != item['statement']
                  or mapped['claim'] != item['test_oracle']['expected']
                  or mapped['test_id'] != item['test_oracle']['test_id']
                  or mapped['distinction_ids'] != ([item['id']] if section == 'D' else item['distinction_ids'])):
                state, reason = 'REJECTED', 'A declared source-local distinction, relation, operation or observation was substituted.'
            elif item['test_oracle']['kind'] == 'structural':
                state, reason = 'PRESERVED', 'Exact source-local declaration and trace retained; semantic adequacy is a separate review.'
            elif item['test_oracle']['kind'] == 'reader_judgment':
                state, reason = 'UNKNOWN', 'Independent author recognition not yet available.'
            elif item['test_oracle']['test_id'] == 'pythagorean_identity' and expected.get('invariant') is True:
                state, reason = 'PRESERVED', 'Exact 3,4,5 integer oracle recomputed independently.'
            else:
                state, reason = 'NARROWED', 'The numeric claim is not covered by this fixed finite oracle.'
            ledger.append({'section': section, 'id': item['id'], 'state': state, 'reason': reason,
                           'must_preserve': item['must_preserve'], 'source_address': item['source_address'],
                           'recovery_pointer': envelope['X']['source_ref'],
                           'admissible_for_audit': state == 'PRESERVED'})
    mandatory_losses = [x['id'] for x in ledger if x['must_preserve'] and x['state'] != 'PRESERVED']
    author = validate_review(review, envelope, projection, trust or {}) if review is not None else 'NO_REVIEW'
    if author == 'REJECTED':
        failures.append('AUTHOR_REJECTED_FORMALIZATION')
    if not envelope['D']:
        failures.append('INSUFFICIENT_CONTRACT')
    okay = not failures and not mandatory_losses
    return {'status': 'PASS_DECLARED_STRUCTURE' if okay else 'REFUSED', 'failure_reasons': failures,
            'mandatory_losses': mandatory_losses, 'loss_ledger': ledger,
            'projection_sha256': canonical_hash(projection), 'contract_sha256': canonical_hash(envelope),
            'successful_formalization_claim_allowed': okay and author == 'RECOGNIZED',
            **statuses(semantic='DECLARED_STRUCTURE_PRESERVED' if okay else 'REQUIRES_REVIEW',
                       mathematical='FINITE_MODEL_CHECKED' if not failures else 'NOT_ESTABLISHED',
                       execution='LOCAL_DEMO_ONLY', author=author,
                       provenance={'source_hash': envelope['source_hash'], 'contract_sha256': canonical_hash(envelope)},
                       unknowns=envelope['unknowns'] + ['Author recognition and global mathematical originality are not established.'])}
