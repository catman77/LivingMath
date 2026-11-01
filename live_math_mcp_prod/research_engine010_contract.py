"""Phase-A typed source contract. A declaration is not measurement authenticity."""
from typing import Annotated, Literal

from pydantic import Field, model_validator
from native_preview008_contract import DataModel, EventID, Checksum, Project, Observer, SourceBinding, NativeQuestion

VERSION = '010.1-phase-a'
Text = Annotated[str, Field(min_length=1, max_length=20000)]


class Readout(DataModel):
    defined: bool
    observation: int | Annotated[str, Field(max_length=4096)] | bool | None
    admissibility: list[bool] = Field(min_length=1, max_length=2)


class SourceIdentity(DataModel):
    source_event_id: EventID
    source_sha256: Checksum
    source_adapter_id: str = Field(min_length=1, max_length=100)
    native_definition_sha256: Checksum


class ArtifactDeclaration(DataModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    sha256: Checksum
    inspection_status: Literal['DECLARED_UNINSPECTED'] = 'DECLARED_UNINSPECTED'


class MeasurementBinding(DataModel):
    """Must originate in the external event; absent historical facts are not filled in."""
    contract_version: Literal['livingmath.bound-measurement/v1']
    project: Project
    obligation_id: EventID
    obligation_version: EventID
    move_id: EventID
    proposal_fingerprint: Checksum
    audit_id: EventID
    activation_operation_id: EventID
    source_event_ids: list[EventID] = Field(min_length=1, max_length=128)
    source_bindings: list[SourceBinding] = Field(min_length=1, max_length=128)
    scope: str = Field(min_length=1, max_length=4096)
    observer: Observer
    question: NativeQuestion
    test_id: str = Field(min_length=1, max_length=80)
    suffix: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=2)
    preview_digest: Checksum | None = None
    predictions: list[Readout] = Field(min_length=1, max_length=32)
    measured_source: SourceIdentity
    observed: Readout
    executor_id: str = Field(min_length=1, max_length=200)
    origin: Literal['external_measurement']
    outcome: Literal['SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR']
    artifact: ArtifactDeclaration | None = None
    proof_status: Literal['unverified'] = 'unverified'

    @model_validator(mode='after')
    def exact_source_set(self):
        ids = self.source_event_ids
        bindings = {r.event_id for r in self.source_bindings}
        if len(set(ids)) != len(ids) or len(bindings) != len(self.source_bindings) or set(ids) != bindings:
            raise ValueError('source IDs must exactly match unique bindings')
        if self.measured_source.source_event_id not in bindings:
            raise ValueError('measured source must be explicitly bound')
        actual_hash = next(r.sha256 for r in self.source_bindings if r.event_id == self.measured_source.source_event_id)
        if self.measured_source.source_sha256 != actual_hash:
            raise ValueError('measured source identity must match its explicit source hash')
        return self


class BoundMeasurementReceipt(DataModel):
    binding: MeasurementBinding
    measurement_event_id: EventID
    summary: Text
    reason: Text
    request_key: str = Field(min_length=1, max_length=128)
    proof_status: Literal['unverified'] = 'unverified'

    @model_validator(mode='after')
    def nonblank(self):
        if not self.summary.strip() or not self.reason.strip() or not self.request_key.strip():
            raise ValueError('summary/reason/request_key cannot be blank')
        return self


class ReceiptValidationRequest(DataModel):
    project: Project
    move_id: EventID
    measurement_event_id: EventID
    receipt: BoundMeasurementReceipt | None = None


def refusal(status: str, reason: str, **details) -> dict:
    return {'status': status, 'reason': reason, 'engine_version': VERSION, 'validation_only': True,
        'commit_enabled': False, 'proof_status': 'unverified', 'execution_permission': {'allowed': False},
        'measurement_authenticity': 'NOT_ESTABLISHED', **details}
