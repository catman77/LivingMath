"""011 bounded data contracts. No field can assert mathematical verification."""
from typing import Annotated, Literal
from pydantic import Field
from native_preview008_contract import DataModel, EventID, Checksum, NativeRequest, Observer, SourceBinding
from research_engine010_contract import Readout

VERSION = '011.1'
EXECUTOR = 'qa.external.native011/v1'
Text = Annotated[str, Field(min_length=1, max_length=4096, pattern=r'\S')]


class CyclePrecommit(DataModel):
    schema_version: Literal['cycle-precommit/v1'] = 'cycle-precommit/v1'
    project: Text
    obligation_id: EventID
    obligation_version: EventID
    scope: Text
    native_request: NativeRequest
    source_bindings: list[SourceBinding] = Field(min_length=1, max_length=128)
    source_family_id: Checksum
    native_definition_sha256: Checksum
    operation_definition_sha256: Checksum
    observer: Observer
    test_id: Text
    suffix: list[Text] = Field(min_length=1, max_length=2)
    suffix_ordinals: list[int] = Field(min_length=1, max_length=2)
    admissibility_guard: list[bool] = Field(min_length=1, max_length=2)
    alternatives: list[dict] = Field(min_length=2, max_length=32)
    tested_hypothesis: Text
    expected_readout: Readout
    expected_measurement_shape: Literal['native-readout/v1'] = 'native-readout/v1'
    proposal_fingerprint: Checksum
    claim_fingerprint: Checksum
    raw_distinction_sha256: Checksum
    preview_digest: Checksum


class MeasurementEnvelope(DataModel):
    schema_version: Literal['bound-measurement/v1'] = 'bound-measurement/v1'
    project: Text
    precommit_id: EventID
    precommit_sha256: Checksum
    move_id: EventID
    proposal_fingerprint: Checksum
    audit_id: EventID
    activation_operation_id: EventID
    obligation_id: EventID
    obligation_version: EventID
    scope: Text
    source_family_id: Checksum
    source_bindings: list[SourceBinding] = Field(min_length=1, max_length=128)
    native_definition_sha256: Checksum
    operation_definition_sha256: Checksum
    observer: Observer
    test_id: Text
    suffix: list[Text] = Field(min_length=1, max_length=2)
    suffix_ordinals: list[int] = Field(min_length=1, max_length=2)
    predictions: list[dict] = Field(min_length=2, max_length=32)
    observed: Readout
    outcome: Literal['SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR']
    summary: Text
    reason: Text
    executor_id: Literal['qa.external.native011/v1']
    executor_code_sha256: Checksum
    artifact_sha256: Checksum
    artifact_status: Literal['DECLARED_UNINSPECTED'] = 'DECLARED_UNINSPECTED'
    proof_status: Literal['unverified'] = 'unverified'


class ReceiptRequest(DataModel):
    project: Text
    move_id: EventID
    event_id: EventID
    request_key: Annotated[str, Field(min_length=1, max_length=128, pattern=r'\S')]
    outcome: Literal['SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR']
    observed: Readout
    summary: Text
    reason: Text
    proof_status: Literal['unverified'] = 'unverified'


def denied(status, reason, **details):
    return {'status': status, 'reason': reason, 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}, **details}
