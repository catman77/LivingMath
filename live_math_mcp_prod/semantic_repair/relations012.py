"""Versioned source annotations; no additional mathematical operations or DSL."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator

from .observer013_contract import ObserverInference
from .relations011 import (
    Citation,
    ClaimCoordinates,
    Modality,
    Polarity,
    RelationKind,
    SemanticRelation,
    SemanticState,
    SourceAssessment,
    SourceReading,
    StateDescriptor,
)


class SourceClaim(StrictModel):
    mode: Literal['DIRECT', 'NARRATION', 'ATTRIBUTED', 'QUOTED', 'UNKNOWN']
    speaker: str = Field(min_length=1, max_length=120)
    observer_id: str | None
    stance: Literal['ASSERTS', 'DENIES', 'QUESTIONS', 'UNKNOWN']
    connective: Literal['CONJUNCTION', 'DISJUNCTION', 'NONE', 'UNKNOWN']
    evidence: list[Citation] = Field(min_length=1, max_length=4)
    speaker_evidence: list[Citation] = Field(max_length=4)


class SemanticState012(SemanticState):
    level: Literal['WORLD_STATE', 'SOURCE_EVENT', 'OBSERVATION_RECORD', 'UNKNOWN']


class StateDescriptor012(StateDescriptor):
    level: Literal['WORLD_STATE', 'SOURCE_EVENT', 'OBSERVATION_RECORD', 'UNKNOWN']
    source_coordinates: dict
    addresses: list[dict]
    feature_addresses: list[dict]


class ObservationValue(StrictModel):
    feature: str = Field(min_length=1, max_length=80)
    value: str | None = Field(max_length=160)
    evidence: list[Citation] = Field(max_length=4)


class ObservationSample(StrictModel):
    state_id: str = Field(min_length=1, max_length=64)
    values: list[ObservationValue] = Field(max_length=16)

    @model_validator(mode='after')
    def unique(self):
        if len({v.feature for v in self.values}) != len(self.values):
            raise ValueError('DUPLICATE_OBSERVATION_FEATURE')
        return self


class ObserverProfile(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    owner: str = Field(min_length=1, max_length=120)
    evidence: list[Citation] = Field(min_length=1, max_length=4)
    criterion: Literal['SEQUENCE', 'MULTISET', 'SET', 'PARTIAL_SET', 'UNKNOWN']
    features: list[str] = Field(min_length=1, max_length=16)
    samples: list[ObservationSample] = Field(max_length=8)

    @model_validator(mode='after')
    def vocabulary(self):
        if len(set(self.features)) != len(self.features) or len({s.state_id for s in self.samples}) != len(self.samples):
            raise ValueError('DUPLICATE_OBSERVER_COORDINATE_OR_SAMPLE')
        if any(v.feature not in self.features for s in self.samples for v in s.values):
            raise ValueError('UNDECLARED_OBSERVER_COORDINATE')
        if any(v.value is not None and not v.evidence for s in self.samples for v in s.values):
            raise ValueError('KNOWN_OBSERVATION_REQUIRES_SOURCE_EVIDENCE')
        return self


Assumption = Literal['CONDITIONAL_EXECUTABLE_CHANGE', 'SCOPED_SOURCE_READING',
    'SYMBOLIC_STATES_NOT_PHYSICAL_IDENTITIES', 'OBSERVER_COORDINATES_ARE_INTERPRETIVE']


class SemanticRelation012(SemanticRelation):
    source_claim: SourceClaim
    interpretation_assumptions: list[Assumption] = Field(max_length=4)


class SourceReading012(SourceReading):
    states: list[SemanticState012] = Field(min_length=2, max_length=8)  # type: ignore[assignment]  # Pydantic versioned field narrows validated elements
    relations: list[SemanticRelation012] = Field(min_length=1, max_length=12)  # type: ignore[assignment]  # Separate serialized012 contract
    observers: list[ObserverProfile] = Field(max_length=4)
    initial_state_ids: list[str] = Field(max_length=4)

    @model_validator(mode='after')
    def observer_references(self):
        ids = {o.id for o in self.observers}
        if len(ids) != len(self.observers):
            raise ValueError('DUPLICATE_NAMED_OBSERVER')
        if any(r.source_claim.observer_id is not None and r.source_claim.observer_id not in ids for r in self.relations):
            raise ValueError('FOREIGN_OBSERVER_REFERENCE')
        nodes = {s.id for s in self.states}
        if not set(self.initial_state_ids) <= nodes:
            raise ValueError('INITIAL_REFERENCES_UNKNOWN_SOURCE_STATE')
        if any(s.state_id not in nodes for o in self.observers for s in o.samples):
            raise ValueError('OBSERVATION_REFERENCES_UNKNOWN_STATE')
        return self


class SourceProposals012(StrictModel):
    version: Literal['source-relations012/1']
    readings: list[SourceReading012] = Field(max_length=3)
    losses: list[str] = Field(max_length=24)


class SourceAssessment012(SourceAssessment):
    attribution_checked: bool
    observer_mask_checked: bool
    executable_assumption_supported: bool


class SourceReview012(StrictModel):
    version: Literal['source-critic012/1']
    assessments: list[SourceAssessment012] = Field(max_length=36)
    losses: list[str] = Field(max_length=24)


class ClaimDescriptor(StrictModel):
    id: str
    mode: Literal['DIRECT', 'NARRATION', 'ATTRIBUTED', 'QUOTED', 'UNKNOWN']
    speaker: str
    observer_id: str | None
    stance: Literal['ASSERTS', 'DENIES', 'QUESTIONS', 'UNKNOWN']
    connective: Literal['CONJUNCTION', 'DISJUNCTION', 'NONE', 'UNKNOWN']
    addresses: list[dict] = Field(min_length=1, max_length=16)
    source_status: Literal['HYPOTHESIS', 'CONFLICT', 'UNSUPPORTED', 'UNKNOWN']
    quotation_guard: Literal['REPORTED', 'NOT_QUOTED', 'AMBIGUOUS', 'UNKNOWN']


class TransitionDescriptor012(StrictModel):
    version: Literal['source-transition012/1']
    source: StateDescriptor012
    target: StateDescriptor012
    relation_kind: RelationKind
    polarity: Polarity
    modality: Modality
    order_kind: Literal['TEXT_ORDER', 'EVENT_ORDER', 'INFERRED_EVENT_ORDER', 'UNKNOWN']
    critic_status: Literal['HYPOTHESIS', 'CONFLICT', 'UNSUPPORTED', 'UNKNOWN']
    review_flags: list[str]
    claim: ClaimCoordinates
    source_claim: ClaimDescriptor
    interpretation_assumptions: list[Assumption] = Field(max_length=4)
    executable_assumption_supported: bool
    source_projection: dict
    inference: ObserverInference | None = Field(default=None, exclude_if=lambda v: v is None)
    # One copy per reading, not repeated for each relation/operation.
    observers: list[dict] | None = Field(default=None, exclude_if=lambda v: v is None)
    declared_states: list[dict] | None = Field(default=None, exclude_if=lambda v: v is None)
    initial_keys: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)


def legacy_reading(reading: SourceReading012) -> dict:
    return {'id': reading.id, 'states': [s.model_dump(exclude={'level'}) for s in reading.states],
        'relations': [SemanticRelation.model_validate({k: v for k, v in r.model_dump().items()
            if k not in {'source_claim', 'interpretation_assumptions'}}).model_dump() for r in reading.relations],
        'unknowns': reading.unknowns}


def decode_proposals012(value: dict) -> tuple[SourceProposals012, list[dict]]:
    try:
        return SourceProposals012.model_validate(value), []
    except ValueError:
        pass
    if not isinstance(value, dict) or set(value) != {'version', 'readings', 'losses'} or value['version'] != 'source-relations012/1':
        raise ValueError('INVALID_012_SOURCE_ENVELOPE')
    kept, losses = [], []
    if not isinstance(value['readings'], list) or len(value['readings']) > 3:
        raise ValueError('SOURCE_READING_BOUND_EXCEEDED')
    for index, raw in enumerate(value['readings']):
        try:
            states = [SemanticState012.model_validate(s) for s in raw['states']]
            observers = []
            for j, o in enumerate(raw['observers']):
                try:
                    profile = ObserverProfile.model_validate(o)
                    if any(s.state_id not in {n.id for n in states} for s in profile.samples):
                        raise ValueError('UNKNOWN_OBSERVER_STATE')
                    observers.append(profile)
                except ValueError as exc:
                    losses.append({'reading_index': index, 'observer_index': j, 'reason': str(exc)[:400]})
            relations = []
            for j, r in enumerate(raw['relations']):
                try:
                    relation = SemanticRelation012.model_validate(r)
                    if relation.source_claim.observer_id is not None and relation.source_claim.observer_id not in {o.id for o in observers}:
                        raise ValueError('UNRESOLVED_SOURCE_OBSERVER')
                    relations.append(relation)
                except ValueError as exc:
                    losses.append({'reading_index': index, 'relation_index': j, 'reason': str(exc)[:400]})
            while True:
                names = {s.id for s in states} | {r.id for r in relations}
                invalid = [r for r in relations if r.src not in names or r.dst not in names]
                if not invalid: break
                for r in invalid:
                    losses.append({'reading_index': index, 'relation_id': r.id, 'reason': 'UNRESOLVED_SOURCE_ENDPOINT'})
                relations = [r for r in relations if r not in invalid]
            kept.append(SourceReading012.model_validate({**raw, 'states': states, 'observers': observers, 'relations': relations}))
        except (ValueError, KeyError, TypeError) as exc:
            losses.append({'reading_index': index, 'reason': str(exc)[:500]})
    return SourceProposals012.model_validate({**value, 'readings': kept}), losses
