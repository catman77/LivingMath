"""Orchestration guards and append-only source projections; mathematical cores unchanged."""
import copy
import json
from pathlib import Path
import sqlite3

from normalizer import digest, read_history
from live_constructive007_native import native_fingerprint
from native_preview008_contract import ADAPTER_ID

MECHANISM = 'qa_cycle_measurement'
VERSION = '009.3'


def qa_closure_changes(evidence_id: int) -> dict:
    return {'status': 'RESOLVED', 'closure_reason': 'Finite QA campaign ended; no mathematical truth claim.',
            'evidence_refs': ['event:' + str(evidence_id)],
            'reopen_conditions': ['A new explicitly authorized source/measurement requires a new version.']}


def event_rows(db: Path, project: str) -> dict:
    return {e['id']: e for e in read_history(db, project)['tables']['events']}


def requests(db: Path, world: dict, binding: dict, feedback_id=None, mode='constructive') -> tuple:
    events = event_rows(db, world['project']); ids = sorted(events)
    refs = binding['histories']; active = binding['active']
    q = {'root_event_id': binding['root_id'], 'left_history_id': refs[active[0]],
         'right_history_id': refs[active[1] if len(active) > 1 else active[0]],
         'certificate_event_id': binding['law_id'], 'mode': mode}
    if feedback_id is not None:
        q['feedback_event_id'] = feedback_id
    hashes = [{'event_id': i, 'sha256': digest(events[i])} for i in ids]
    native = {'project': world['project'], 'active_frontier_id': binding['obligation_id'],
        'active_frontier_version': binding['version'], 'source_event_ids': ids, 'source_adapter_id': ADAPTER_ID,
        'source_bindings': hashes, 'observer': world['observer'], 'question': q, 'budget': {}}
    candidate = {'id': 'native-preview008', 'project': world['project'], 'root_ref': 'event:' + str(binding['root_id']),
        'scope': world['scope'], 'version': binding['version'], 'move': {'active_frontier_id': binding['obligation_id'],
        'parent_event_ids': ids, 'proposed_operation': {'mechanism': 'readonly_source_law_interpretation', 'intent': 'advisory'}}}
    normal = {'project': world['project'], 'focus': 'source-certified interpretation', 'source_event_ids': ids,
        'query_scope': {'level': 'C2', 'candidates': [candidate], 'expected_hashes': hashes,
            'obligation_id': binding['obligation_id'], 'version': binding['version'], 'scope': world['scope']}, 'budget': {}}
    return normal, native


def source_spec(world: dict, histories: dict, independent: int, active: list[str], version: int, failures: list) -> dict:
    hypotheses = [{'id': name, 'ref': 'event:' + str(histories[name]), 'weight': 1, 'predictive': True,
                   'question': 'current', 'depends_on': []} for name in active]
    hypotheses += [{'id': 'D' + name[1:], 'ref': 'event:' + str(histories[name]), 'weight': 1,
                    'predictive': False, 'question': 'current', 'depends_on': [name]} for name in active]
    hypotheses += [{'id': 'IND', 'ref': 'event:' + str(independent), 'weight': 1, 'predictive': False,
                    'question': 'independent', 'depends_on': []}]
    return {'family': world['id'], 'parameters': world['parameters'], 'histories': ['event:' + str(histories[n]) for n in world['histories']],
        'independent_ref': 'event:' + str(independent), 'tests': world['tests'], 'hypotheses': hypotheses,
        'observer': world['observer'], 'current_observation': world['current_observation'], 'scope': world['scope'],
        'version': version, 'representation': 'native_007/v1', 'primitive_sha256': native_fingerprint(),
        'known_failures': failures, 'unknowns': world['unknowns']}


def law_payload(world: dict, root: dict, version: int) -> dict:
    cert = {'schema': 'separating-coordinate/v1', 'source_ref': 'event:' + str(root['id']), 'source_hash': digest(root),
        'project': world['project'], 'scope': world['scope'], 'version': version, 'observer_hash': digest(world['observer']),
        'native_hash': native_fingerprint(), 'kind': world['law_kind'], 'coverage': list(range(world['width'])),
        'guard': {'total_admissibility': True, 'width': world['width']}}
    return {'claim_type': 'FORMAL_CLAIM', 'statement': 'Operator-supplied reviewed finite source law; no theorem/verified status.',
            'scope': world['scope'], 'version': version, 'representation': 'native_007/v1', 'source_certificate': cert}


def material(value):
    """Only timing/process-cost fields are excluded; all mathematical/provenance data remain."""
    ignored = {'seconds', 'cold_wall_ns', 'cold_cpu_ns', 'parent_cpu_ns', 'worker_total_wall_ns', 'worker_total_cpu_ns',
        'worker_max_rss_KiB', 'child_cpu_ns', 'child_peak_rss_KiB', 'validation_wall_seconds', 'wall_ns',
        'source_snapshot_wall_ns', 'interpretation_ns', 'attention_ns'}
    if isinstance(value, dict):
        return {k: material(v) for k, v in value.items() if k not in ignored}
    if isinstance(value, list):
        return [material(v) for v in value]
    return value


def selected_claim(attention: dict) -> tuple:
    test = attention['ranking'][0]
    rows = test['counterfactuals']
    choice = min(rows, key=lambda r: (sum(r['readout'] == other['readout'] for other in rows), r['hypothesis']))
    return test, choice


def survivors(attention: dict, readout: dict) -> list[str]:
    return [r['hypothesis'] for r in attention['ranking'][0]['counterfactuals'] if r['readout'] == readout]


def validate_witness(world: dict, binding: dict, out: dict, raw_replay) -> None:
    witness = out.get('witness')
    if witness is None:
        return
    suffix = witness['suffix']
    if not any(t['id'] == witness['test_id'] and t['suffix'] == suffix for t in world['tests']):
        raise ValueError('WITNESS_OUTSIDE_REGISTERED_D')
    reverse = {eid: name for name, eid in binding['histories'].items()}
    expected = [raw_replay(world['histories'][reverse[int(ref.split(':')[1])]], suffix,
                           world['parameters'], world['observer']) for ref in witness['histories']]
    if witness['readouts'] != expected or expected[0] == expected[1]:
        raise ValueError('RETURNED_WITNESS_NATIVE_MISMATCH')


def validate_executable_readout(world: dict, test: dict, attention: dict) -> None:
    if not any(t['id'] == test['test_id'] and all(t[k] == test[k] for k in ('suffix', 'cost', 'ordinal')) for t in world['tests']):
        raise ValueError('TEST_OUTSIDE_REGISTERED_D')
    if test['test_id'] != attention['test_id']:
        raise ValueError('EXECUTION_NOT_SELECTED_BY_T')
    if any(not r['readout']['defined'] or not all(r['readout']['admissibility']) for r in test['counterfactuals']):
        raise ValueError('PERMISSION_ONLY_WITNESS_IS_NOT_EXECUTABLE')


def validate_completion(event: dict, world: dict, binding: dict, test_id: str, result: dict) -> None:
    if event.get('project') != world['project']:
        raise ValueError('FOREIGN_COMPLETION_EVIDENCE')
    data = json.loads(event['content'])
    if (data.get('claim_type') != 'EXPERIMENT_RESULT' or data.get('fixture_sha256') != world['fixture_sha256']
            or data.get('scope') != world['scope'] or data.get('version') != binding['version']
            or data.get('test_id') != test_id or not isinstance(data.get('observation'), dict)
            or data.get('measurement_origin') != 'external_bounded_native_executor'
            or data.get('outcome') != result['outcome'] or data['observation']['readout'] != result['data']['readout']):
        raise ValueError('ACTUAL_MATCHING_MEASUREMENT_EVIDENCE_REQUIRED')


def operation(world: dict, test_id: str, prediction: dict, purpose='cycle') -> dict:
    return {'mechanism': MECHANISM, 'intent': 'experiment',
        'premises': ['Exact operator fixture ' + world['fixture_sha256'], 'Purpose ' + purpose],
        'mathematical_properties': ['Finite declared test ' + test_id],
        'testable_consequence': 'Readout for ' + test_id + ' matches the declared finite candidate ' + json.dumps(prediction, sort_keys=True),
        'required_evidence': ['Actual project-local measurement of ' + test_id]}


def proposal(world, binding, op, adverse=()):
    ids = [binding['fixture_id'], binding['root_id'], *adverse]
    return {'active_frontier_id': binding['obligation_id'], 'active_frontier_version': binding['version'],
        'scope': world['scope'], 'parent_event_ids': list(dict.fromkeys(ids)), 'proposed_operation': op,
        'source_representation': 'fixture009:' + world['fixture_sha256'], 'target_representation': 'fixture009:' + world['fixture_sha256'],
        'evidence_refs': ['event:' + str(i) for i in ids],
        'evidence_roles': {str(i): {'role': 'diagnostic_subject', 'reason': 'Bounded diagnosis of the excluded finite guard, not support for that rejected premise.'} for i in adverse},
        'verification_plan': {'method': 'External bounded native readout under an explicit current scoped grant.',
                              'failure_condition': 'Mismatch with candidate readout or fixture/source/observer/version drift.'}}
