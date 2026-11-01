"""Explicit source-local traces, not an invented executable formal language."""
from copy import deepcopy

from .canonical import Refusal, canonical_hash, statuses
from .demos import MODEL_KINDS, evaluate
from .intake import validate_schema


def fingerprint(candidate: dict) -> str:
    # Names/questions cannot turn the same mechanism into structural novelty.
    return canonical_hash({k: candidate[k] for k in ('model_kind', 'observer_id', 'source_ref',
                                                    'contract_sha256', 'revision')})


def candidates(envelope: dict, family: str) -> list[dict]:
    rows = []
    for kind, (group, _, question) in MODEL_KINDS.items():
        if group == family:
            rows.append({'id': kind, 'title': kind.replace('_', ' '), 'question': question,
                         'model_kind': kind, 'interpretation_kind': 'semantic_interpretation' if family == 'poetry' else 'mathematical_model',
                         'observer_id': envelope['observer_id'], 'assumptions': ['Only the explicitly declared finite model is evaluated.'],
                         'source_ref': envelope['X']['source_ref'], 'revision': envelope['revision'],
                         'contract_sha256': canonical_hash(envelope)})
    return rows


def project(envelope: dict, candidate: dict, settings: dict) -> dict:
    validate_schema(candidate, 'candidate')
    if (candidate['contract_sha256'] != canonical_hash(envelope)
            or candidate['revision'] != envelope['revision']
            or candidate['source_ref'] != envelope['X']['source_ref']
            or candidate['observer_id'] != envelope['observer_id']):
        raise Refusal('CANDIDATE_BINDING_MISMATCH')
    model = MODEL_KINDS[candidate['model_kind']]
    if envelope['X']['declared_reader'] != 'bridge-fixture/' + model[0]:
        raise Refusal('UNSUPPORTED_SOURCE', 'No reviewed local adapter binds this source to the requested model family.')
    bindings = []
    for section in ('D', 'R', 'T', 'O'):
        for item in envelope[section]:
            distinction_ids = [item['id']] if section == 'D' else item['distinction_ids']
            bindings.append({'section': section, 'item_id': item['id'], 'model_element_id': 'element:' + item['id'],
                             'source_address': deepcopy(item['source_address']), 'source_item_sha256': canonical_hash(item),
                             'distinction_ids': distinction_ids, 'declared_statement': item['statement'],
                             'test_id': item['test_oracle']['test_id'], 'claim': item['test_oracle']['expected']})
    return {'schema_version': 'bridge-projection/v0.1', 'source_ref': envelope['X']['source_ref'],
            'source_id': envelope['source_id'], 'revision': envelope['revision'],
            'contract_sha256': canonical_hash(envelope), 'source_hash': envelope['source_hash'],
            'rights_sha256': canonical_hash(envelope['rights']), 'observer_id': envelope['observer_id'],
            'candidate': deepcopy(candidate), 'structural_fingerprint': fingerprint(candidate),
            'model_family': model[0], 'operation_order': model[1], 'bindings': bindings,
            'observations': evaluate(candidate['model_kind'], settings),
            'settings_sha256': canonical_hash(settings),
            'equality_layers': {'object': 'Same model state within one declared domain only.',
                                'source': 'Only identical source hash, revision and address.',
                                'coordinate': 'Explicit observer coordinates, not source equality.',
                                'observation': 'Same projected observation may hide distinct states.',
                                'scalar': 'Equal scalar or cancellation does not identify sources.'},
            'loss_ledger': [{'section': section, 'id': item['id'], 'state': 'UNKNOWN',
                            'reason': 'Awaiting independent audit; mapping is not evidence.',
                            'must_preserve': item['must_preserve'], 'source_address': deepcopy(item['source_address']),
                            'recovery_pointer': envelope['X']['source_ref'], 'admissible_for_audit': False}
                           for section in ('D', 'R', 'T', 'O') for item in envelope[section]],
            'admissible_for_audit': False,
            'recovery_pointer': envelope['X']['source_ref'],
            **statuses(semantic='PENDING_AUDIT', provenance={'contract_sha256': canonical_hash(envelope)})}
