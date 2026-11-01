"""Source proposals extend012 records, preserving every previous contract."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator

from .relations011 import Citation
from .relations012 import (
    ObservationSample,
    ObserverProfile,
    SemanticRelation012,
    SourceAssessment012,
    SourceClaim,
    SourceReading012,
)


class ValueEvidence(StrictModel):
    value: str=Field(min_length=1,max_length=160)
    negative: bool
    evidence: list[Citation]=Field(min_length=1,max_length=4)


class ObservationValue013(StrictModel):
    feature: str=Field(min_length=1,max_length=80)
    status: Literal['KNOWN','EXPLICIT_NEGATIVE','UNKNOWN','CONFLICT']
    value: str | None=Field(max_length=160)
    evidence: list[Citation]=Field(max_length=4)
    conflicts: list[ValueEvidence]=Field(max_length=4)

    @model_validator(mode='after')
    def coherent(self):
        if self.status in {'KNOWN','EXPLICIT_NEGATIVE'} and (self.value is None or not self.evidence or self.conflicts):raise ValueError('KNOWN_OR_NEGATIVE_VALUE_NEEDS_LITERAL_EVIDENCE')
        if self.status in {'UNKNOWN','CONFLICT'} and self.value is not None:raise ValueError('UNKNOWN_IS_NOT_A_VALUE')
        if self.status=='UNKNOWN' and self.conflicts:raise ValueError('CONFLICT_MUST_BE_EXPLICIT')
        if self.status=='CONFLICT':
            pos={c.value for c in self.conflicts if not c.negative};neg={c.value for c in self.conflicts if c.negative}
            if not (len(pos)>1 or pos&neg):raise ValueError('NO_ACTUAL_CONFLICT')
        return self


class Sample013(ObservationSample):
    values: list[ObservationValue013]=Field(max_length=16)  # type: ignore[assignment]  # Separate versioned Pydantic contract
    scope: str | None=Field(max_length=160)
    time: str | None=Field(max_length=160)
    referent: str | None=Field(max_length=160)
    binding_evidence: list[Citation]=Field(max_length=4)


class Profile013(ObserverProfile):
    samples: list[Sample013]=Field(max_length=8)  # type: ignore[assignment]  # Separate versioned Pydantic contract


class Claim013(SourceClaim):
    comparison: Literal['EQUALITY','RETURN','UNSPECIFIED']
    reported_value: Literal['TRUE','FALSE','UNKNOWN']
    comparison_scope: str | None=Field(max_length=160)
    comparison_time: str | None=Field(max_length=160)


class Relation013(SemanticRelation012):
    source_claim: Claim013


class Reading013(SourceReading012):
    relations: list[Relation013]=Field(min_length=1,max_length=12)  # type: ignore[assignment]  # Narrowed versioned field
    observers: list[Profile013]=Field(max_length=4)  # type: ignore[assignment]  # Narrowed versioned field


class SourceProposals013(StrictModel):
    version: Literal['source-relations013/1']
    readings: list[Reading013]=Field(max_length=3)
    losses: list[str]=Field(max_length=24)


class ObservationReview(StrictModel):
    reading_id: str
    observer_id: str
    status: Literal['HYPOTHESIS','CONFLICT','UNSUPPORTED','UNKNOWN']
    explicit_values_checked: bool
    binding_time_scope_checked: bool
    evidence: list[Citation]=Field(max_length=8)
    reason: str=Field(min_length=1,max_length=1400)


class SourceReview013(StrictModel):
    version: Literal['source-critic013/1']
    assessments: list[SourceAssessment012]=Field(max_length=36)
    observations: list[ObservationReview]=Field(max_length=12)
    losses: list[str]=Field(max_length=24)


def legacy(proposals: SourceProposals013) -> dict:
    value=proposals.model_dump();value['version']='source-relations012/1'
    for h in value['readings']:
        for r in h['relations']:
            for k in ('comparison','reported_value','comparison_scope','comparison_time'):r['source_claim'].pop(k)
        for p in h['observers']:
            for s in p['samples']:
                for k in ('scope','time','referent','binding_evidence'):s.pop(k)
                s['values']=[{'feature':v['feature'],'value':v['value'] if v['status']=='KNOWN' else None,
                    'evidence':v['evidence']} for v in s['values']]
    return value
