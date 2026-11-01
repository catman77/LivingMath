"""010 Phase-A guards. Synthetic schema examples never stand in for measurements."""
import asyncio
import copy
import json
import sqlite3

import pytest
from pydantic import ValidationError

from normalizer import digest
from normalization_oracle import materialize
from native_preview008_contract import NativeRequest
from native_preview008_qa import readonly_state
from research_engine010 import PhaseAEngine
from research_engine010_contract import BoundMeasurementReceipt, MeasurementBinding, ReceiptValidationRequest
from research_engine010_qa import Acceptance, PRIOR009, inspection


@pytest.fixture
def isolated(tmp_path):
    history = json.loads((PRIOR009 / 'source-snapshots/affine-step1-after.json').read_text())
    db = tmp_path / 'isolated.sqlite3'
    materialize(history, db)
    calls = json.loads((PRIOR009 / 'mcp-transcript.json').read_text())['calls']
    native = copy.deepcopy(next(c['arguments'] for c in calls if c['tool'] == 'research_native_preview'))
    # Use the exact current version and source set from this snapshot.
    native['source_event_ids'] = [e['id'] for e in history['tables']['events']]
    native['source_bindings'] = [{'event_id': e['id'], 'sha256': digest(e)} for e in history['tables']['events']]
    return db, native, history


def example_receipt():
    """Data-only schema example, not a generated measurement or accepted receipt."""
    return {'binding': {'contract_version': 'livingmath.bound-measurement/v1', 'project': 'QA',
        'obligation_id': 1, 'obligation_version': 1, 'move_id': 2, 'proposal_fingerprint': '1' * 64,
        'audit_id': 3, 'activation_operation_id': 4, 'source_event_ids': [5],
        'source_bindings': [{'event_id': 5, 'sha256': '2' * 64}], 'scope': 'finite QA only',
        'observer': {'projection': 'primary', 'mod': None},
        'question': {'root_event_id': 5, 'left_history_id': 6, 'right_history_id': 7},
        'test_id': 't1', 'suffix': ['a0'], 'predictions': [{'defined': True, 'observation': 0, 'admissibility': [True]}],
        'measured_source': {'source_event_id': 5, 'source_sha256': '2' * 64,
            'source_adapter_id': 'schema-example-only', 'native_definition_sha256': '3' * 64},
        'observed': {'defined': True, 'observation': 1, 'admissibility': [True]},
        'executor_id': 'schema-example-only', 'origin': 'external_measurement', 'outcome': 'FAILURE'},
        'measurement_event_id': 8, 'summary': 'Schema example, not a measurement',
        'reason': 'Schema validation only', 'request_key': 'example'}


@pytest.mark.parametrize('outcome', ['SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR'])
def test_four_outcomes_are_structured_unverified_declarations(outcome):
    data = example_receipt(); data['binding']['outcome'] = outcome
    receipt = BoundMeasurementReceipt.model_validate(data)
    assert receipt.proof_status == receipt.binding.proof_status == 'unverified'
    assert 'execution_permission' not in receipt.model_dump()


@pytest.mark.parametrize('field', [k for k, f in MeasurementBinding.model_fields.items() if f.is_required()])
def test_missing_binding_fact_cannot_be_defaulted(field):
    data = example_receipt()['binding']; del data[field]
    with pytest.raises(ValidationError): MeasurementBinding.model_validate(data)


@pytest.mark.parametrize('field', ['summary', 'reason', 'request_key'])
def test_blank_receipt_metadata_rejected(field):
    data = example_receipt(); data[field] = ' '
    with pytest.raises(ValidationError): BoundMeasurementReceipt.model_validate(data)


@pytest.mark.parametrize('mutation', ['verified', 'prediction_origin', 'duplicate_source', 'foreign_identity', 'mismatched_source_sha'])
def test_caller_cannot_change_authority_by_schema_fields(mutation):
    data = example_receipt(); binding = data['binding']
    if mutation == 'verified': binding['proof_status'] = 'verified'
    elif mutation == 'prediction_origin': binding['origin'] = 'I_T_prediction'
    elif mutation == 'duplicate_source': binding['source_event_ids'].append(5)
    elif mutation == 'foreign_identity': binding['measured_source']['source_event_id'] = 99
    else: binding['measured_source']['source_sha256'] = '9' * 64
    with pytest.raises(ValidationError): BoundMeasurementReceipt.model_validate(data)


@pytest.mark.parametrize('index', range(6))
def test_original009_measurements_remain_insufficient_without_backfill(tmp_path, index):
    finding = inspection()[index]
    path = PRIOR009 / 'source-snapshots' / (finding['world'] + '-step' + str(finding['cycle_index']) + '-after.json')
    source = json.loads(path.read_text()); db = tmp_path / 'history.sqlite3'; materialize(source, db)
    before = readonly_state(db)
    out = PhaseAEngine(db).validate_receipt(ReceiptValidationRequest(project=source['project'],
        move_id=finding['move_id'], measurement_event_id=finding['measurement_event_id']))
    assert out['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING'
    assert out['no_reconstruction_from_caller_or_harness_trace'] is True
    assert out['execution_permission'] == {'allowed': False} and out['proof_status'] == 'unverified'
    assert readonly_state(db) == before


@pytest.mark.parametrize('case', ['absent', 'empty', 'known', 'foreign', 'stale', 'hash', 'C4', 'quota'])
def test_novelty_never_trusts_caller_or_partial_context(isolated, case):
    db, native, _ = isolated
    if case == 'absent': native['question'].pop('known_fingerprints', None)
    elif case == 'empty': native['question']['known_fingerprints'] = []
    elif case == 'known': native['question']['known_fingerprints'] = ['f' * 64]
    elif case == 'foreign': native['project'] = 'FOREIGN'
    elif case == 'stale': native['active_frontier_version'] += 99
    elif case == 'hash': native['source_bindings'][0]['sha256'] = 'f' * 64
    elif case == 'C4': native['question']['context_level'] = 'C4'
    else: native['budget'] = {**native.get('budget', {}), 'max_events': 1}
    before = readonly_state(db)
    out = PhaseAEngine(db).cycle_preview(NativeRequest.model_validate(native))
    assert out['status'] == ('NOVELTY_CONTEXT_INCOMPLETE' if case in ('absent', 'empty', 'known') else 'INSUFFICIENT_CONTEXT')
    assert out['next_step'] is None and not out['I_T_executed']
    assert not out['execution_permission']['allowed'] and out['proof_status'] == 'unverified'
    assert readonly_state(db) == before


def test_connection_cannot_write_and_receipt_cannot_supply_missing_event_facts(isolated):
    db, native, history = isolated; before = readonly_state(db); engine = PhaseAEngine(db)
    with engine.connection() as conn, pytest.raises(sqlite3.DatabaseError):
        conn.execute('DELETE FROM events')
    finding = inspection()[0]
    supplied = example_receipt(); supplied['measurement_event_id'] = finding['measurement_event_id']
    request = ReceiptValidationRequest(project=history['project'], move_id=finding['move_id'],
        measurement_event_id=finding['measurement_event_id'], receipt=BoundMeasurementReceipt.model_validate(supplied))
    result = engine.validate_receipt(request)
    assert result['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING'
    assert readonly_state(db) == before


def test_real_mcp_tools_schema_and_readonly_error_path(isolated, tmp_path):
    db, native, history = isolated
    acceptance = Acceptance(tmp_path); finding = inspection()[0]
    async def work(client, tools):
        assert {t['name'] for t in tools['tools']} == {'research_cycle_validate_receipt', 'research_novelty_snapshot', 'research_cycle_preview'}
        assert all(t['inputSchema']['additionalProperties'] is False for t in tools['tools'])
        out = await acceptance.call(client, db, 'research_cycle_validate_receipt', {'request': {
            'project': history['project'], 'move_id': finding['move_id'], 'measurement_event_id': finding['measurement_event_id']}}, 'actual-event', True)
        assert out['status'] == 'INSUFFICIENT_MEASUREMENT_BINDING'
        out = await acceptance.call(client, db, 'research_cycle_preview', {'request': native}, 'preview', True)
        assert out['status'] == 'NOVELTY_CONTEXT_INCOMPLETE'
        out = await acceptance.call(client, db, 'research_cycle_preview', {'request': {**native, 'verified': True}}, 'invalid', True)
        assert out is None
    asyncio.run(acceptance.session(db, 'real-mcp', work, phase_a=True))
