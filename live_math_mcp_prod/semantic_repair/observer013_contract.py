"""Versioned observation metadata only; no executable expressions or operations."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator


class EvidenceValue(StrictModel):
    value: str = Field(min_length=1,max_length=160)
    negative: bool
    addresses: list[dict] = Field(min_length=1,max_length=4)


class Cell(StrictModel):
    status: Literal['KNOWN','EXPLICIT_NEGATIVE','UNKNOWN','CONFLICT']
    value: str | None = Field(max_length=160)
    conflicts: list[EvidenceValue] = Field(max_length=4)
    addresses: list[dict] = Field(max_length=4)

    @model_validator(mode='after')
    def coherent(self):
        if self.status in {'KNOWN','EXPLICIT_NEGATIVE'}:
            if self.value is None or not self.addresses or self.conflicts:raise ValueError('ADDRESSED_SINGLE_VALUE_REQUIRED')
        elif self.value is not None:raise ValueError('UNKNOWN_OR_CONFLICT_NOT_A_VALUE')
        if self.status=='UNKNOWN' and self.conflicts:raise ValueError('UNKNOWN_NOT_CONFLICT')
        if self.status=='CONFLICT':
            pos={c.value for c in self.conflicts if not c.negative};neg={c.value for c in self.conflicts if c.negative}
            if not (len(pos)>1 or pos&neg):raise ValueError('ACTUAL_CONTRADICTORY_ASSIGNMENTS_REQUIRED')
        return self


class Sample(StrictModel):
    state_key: str
    values: dict[str,Cell]
    scope: str | None
    time: str | None
    referent: str | None
    binding_addresses: list[dict] = Field(max_length=4)


class Profile(StrictModel):
    id: str
    owner: str
    features: list[str] = Field(min_length=1,max_length=16)
    criterion: Literal['SEQUENCE','MULTISET','SET','PARTIAL_SET','UNKNOWN']
    source_status: Literal['HYPOTHESIS','CONFLICT','UNSUPPORTED','UNKNOWN']
    addresses: list[dict] = Field(max_length=4)
    samples: list[Sample] = Field(max_length=8)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.features))!=len(self.features) or len({s.state_key for s in self.samples})!=len(self.samples):raise ValueError('DUPLICATE_OBSERVATION_COORDINATE')
        if any(set(s.values)!=set(self.features) for s in self.samples):raise ValueError('ALL_MASK_COORDINATES_REQUIRED')
        return self


class Report(StrictModel):
    id: str
    observer_id: str | None
    speaker: str
    source: str
    target: str
    comparison: Literal['EQUALITY','RETURN','UNSPECIFIED']
    reported_value: Literal['TRUE','FALSE','UNKNOWN']
    scope: str | None
    time: str | None
    addresses: list[dict] = Field(min_length=1,max_length=16)


class ObserverInference(StrictModel):
    version: Literal['observer-inference013/1']
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    profiles: list[Profile] = Field(max_length=4)
    reports: list[Report] = Field(max_length=12)

    @model_validator(mode='after')
    def refs(self):
        ids={p.id for p in self.profiles}
        if len(ids)!=len(self.profiles):raise ValueError('DUPLICATE_OBSERVER_ID')
        if any(r.observer_id is not None and r.observer_id not in ids for r in self.reports):raise ValueError('FOREIGN_OBSERVER_REPORT')
        return self
