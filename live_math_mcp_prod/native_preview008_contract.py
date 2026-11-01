"""Data-only, bounded public contracts; no source code or caller proof authority."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = '008.2'
ADAPTER_ID = 'livingmath.native007.reviewed.v1'
EventID = Annotated[int, Field(strict=True, ge=1)]
Checksum = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Project = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[\w.-]+$')]


class DataModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PreviewBudget(DataModel):
    input_bytes: int = Field(default=65536, ge=256, le=65536)
    source_bytes: int = Field(default=4_000_000, ge=4096, le=4_000_000)
    max_events: int = Field(default=2000, ge=1, le=2000)
    output_bytes: int = Field(default=1_000_000, ge=4096, le=1_000_000)
    max_tokens: int = Field(default=100_000, ge=1024, le=100_000)
    native_calls: int = Field(default=2048, ge=1, le=2048)
    deadline_ms: int = Field(default=5000, ge=50, le=10000)
    memory_mb: int = Field(default=1024, ge=256, le=1024)


class SourceBinding(DataModel):
    event_id: EventID
    sha256: Checksum


class QueryScope(DataModel):
    level: Literal['C0', 'C1', 'C2', 'C3', 'C4'] = 'C2'
    candidates: list[dict] = Field(default_factory=list, max_length=64)
    expected_hashes: list[SourceBinding] = Field(default_factory=list, max_length=128)
    obligation_id: EventID | None = None
    version: EventID | None = None
    scope: str | None = Field(default=None, max_length=4096)

    @model_validator(mode='after')
    def paired_version(self):
        if (self.obligation_id is None) != (self.version is None):
            raise ValueError('obligation_id and version must be supplied together')
        return self


class Observer(DataModel):
    projection: Literal['primary'] = 'primary'
    mod: Annotated[int, Field(ge=1, le=2**31)] | None = None


class NativeQuestion(DataModel):
    root_event_id: EventID
    left_history_id: EventID
    right_history_id: EventID
    certificate_event_id: EventID | None = None
    feedback_event_id: EventID | None = None
    mode: Literal['constructive', 'bounded'] = 'constructive'
    context_level: Literal['C0', 'C1', 'C2', 'C3', 'C4'] = 'C2'
    known_fingerprints: list[Checksum] = Field(default_factory=list, max_length=16)
    max_suffix_length: int = Field(default=2, ge=2, le=2)


class NormalizeRequest(DataModel):
    project: Project
    focus: str = Field(min_length=1, max_length=4096)
    source_event_ids: list[EventID] = Field(min_length=1, max_length=128)
    query_scope: QueryScope = Field(default_factory=QueryScope)
    budget: PreviewBudget = Field(default_factory=PreviewBudget)


class NativeRequest(DataModel):
    project: Project
    active_frontier_id: EventID
    active_frontier_version: EventID
    source_event_ids: list[EventID] = Field(min_length=1, max_length=128)
    source_adapter_id: str = Field(min_length=1, max_length=100)
    source_bindings: list[SourceBinding] = Field(min_length=1, max_length=128)
    observer: Observer
    question: NativeQuestion
    budget: PreviewBudget = Field(default_factory=PreviewBudget)


def refusal(status: str, reason: str) -> dict:
    return {'status': status, 'reason': reason, 'proof_status': 'unverified',
            'epistemic_status': 'unverified', 'execution_permission': {'allowed': False},
            'audit_sufficient': False, 'preview_version': VERSION}
