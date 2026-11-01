"""Versioned source annotations, not a mathematical language or truth oracle."""
from typing import Literal

from pydantic import Field, model_validator

from davcore.models import StrictModel

Polarity = Literal['POSITIVE', 'NEGATIVE', 'UNKNOWN', 'CONFLICT']
Modality = Literal['ASSERTED', 'NARRATED', 'PRESCRIBED', 'CONDITIONAL', 'POSSIBLE', 'UNKNOWN']
Quantifier = Literal['ALL', 'SOME', 'NAMED_CASE', 'UNKNOWN']
Tense = Literal['PAST', 'PRESENT', 'FUTURE', 'ATEMPORAL', 'UNKNOWN']
Projection = Literal['FULL_STATE', 'SEQUENCE', 'MULTISET', 'SET', 'PARTIAL_SET', 'UNKNOWN']
RelationKind = Literal['TRANSITION', 'SEQUENCE', 'ORDER', 'REPEAT', 'IDENTICAL',
                       'EQUIVALENT_O', 'SIMILAR_O', 'REORDERED', 'NEGATED',
                       'CONDITION', 'COOCCUR', 'UNKNOWN']


class Citation(StrictModel):
    ref: str = Field(min_length=1, max_length=160)
    quote: str = Field(min_length=1, max_length=4096)


class CitedFeature(StrictModel):
    feature: str = Field(min_length=1, max_length=100)
    evidence: Citation


class SemanticState(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[\w.-]+$')
    label: str = Field(min_length=1, max_length=200)
    evidence: list[Citation] = Field(min_length=1, max_length=8)
    features: list[CitedFeature] = Field(max_length=16)
    participant: str = Field(min_length=1, max_length=120)
    referent: str = Field(min_length=1, max_length=120)
    polarity: Polarity
    tense: Tense
    modality: Modality
    quantifier: Quantifier
    scope: str = Field(min_length=1, max_length=160)


class SemanticRelation(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[\w.-]+$')
    kind: RelationKind
    src: str = Field(min_length=1, max_length=64)
    dst: str = Field(min_length=1, max_length=64)
    evidence: list[Citation] = Field(min_length=1, max_length=8)
    predicate: str = Field(min_length=1, max_length=200)
    participant: str = Field(min_length=1, max_length=120)
    referent: str = Field(min_length=1, max_length=120)
    polarity: Polarity
    tense: Tense
    modality: Modality
    quantifier: Quantifier
    scope: str = Field(min_length=1, max_length=160)
    order_kind: Literal['TEXT_ORDER', 'EVENT_ORDER', 'INFERRED_EVENT_ORDER', 'UNKNOWN']
    projection: Projection
    projection_features: list[str] = Field(max_length=16)
    interpretation_note: str = Field(min_length=1, max_length=1000)


class SourceReading(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    states: list[SemanticState] = Field(min_length=2, max_length=8)
    relations: list[SemanticRelation] = Field(min_length=1, max_length=12)
    unknowns: list[str] = Field(max_length=16)

    @model_validator(mode='after')
    def references(self):
        nodes = {s.id for s in self.states}
        events = {r.id for r in self.relations}
        if len(nodes) != len(self.states) or len(events) != len(self.relations) or nodes & events:
            raise ValueError('DUPLICATE_SOURCE_ANNOTATION_ID')
        if any(r.src not in nodes | events or r.dst not in nodes | events for r in self.relations):
            raise ValueError('UNRESOLVED_SOURCE_RELATION_ENDPOINT')
        return self


class SourceProposals(StrictModel):
    version: Literal['source-relations011/1']
    readings: list[SourceReading] = Field(max_length=3)
    losses: list[str] = Field(max_length=24)


class SourceAssessment(StrictModel):
    reading_id: str = Field(min_length=1, max_length=64)
    relation_id: str = Field(min_length=1, max_length=64)
    status: Literal['HYPOTHESIS', 'CONFLICT', 'UNSUPPORTED', 'UNKNOWN']
    evidence: list[Citation] = Field(max_length=8)
    reason: str = Field(min_length=1, max_length=1400)
    distinctions_checked: list[Literal['participant', 'referent', 'predicate', 'quantifier',
        'polarity', 'tense', 'modal', 'scope', 'text_order_vs_event_order', 'projection']] = Field(min_length=10, max_length=10)
    alternative: str = Field(max_length=1400)


class SourceReview(StrictModel):
    version: Literal['source-critic011/1']
    assessments: list[SourceAssessment] = Field(max_length=36)
    losses: list[str] = Field(max_length=24)


def decode_proposals(value: dict) -> tuple[SourceProposals, list[dict]]:
    """Retain valid readings/relations without guessing missing annotations.

    The caller retains the original raw model answer. Every omitted fragment is
    addressed by its output index; this is validation, not a semantic repair.
    """
    try:
        return SourceProposals.model_validate(value), []
    except ValueError:
        pass
    if not isinstance(value, dict) or set(value) != {'version', 'readings', 'losses'} or value['version'] != 'source-relations011/1':
        raise ValueError('INVALID_SOURCE_PROPOSAL_ENVELOPE')
    if not isinstance(value['readings'], list) or len(value['readings']) > 3:
        raise ValueError('SOURCE_READING_BOUND')
    kept, losses = [], []
    for i, raw in enumerate(value['readings']):
        try:
            kept.append(SourceReading.model_validate(raw))
            continue
        except ValueError as exc:
            first = str(exc)[:700]
        try:
            states = [SemanticState.model_validate(s) for s in raw['states']]
            if len({s.id for s in states}) != len(states):
                raise ValueError('AMBIGUOUS_STATE_IDS')
            relations = []
            for j, relation in enumerate(raw['relations']):
                try:
                    relations.append((j, SemanticRelation.model_validate(relation)))
                except ValueError as exc:
                    losses.append({'reading_index': i, 'relation_index': j, 'reason': str(exc)[:700]})
            if len({r.id for _, r in relations}) != len(relations) or {s.id for s in states} & {r.id for _, r in relations}:
                raise ValueError('AMBIGUOUS_ANNOTATION_IDS')
            while True:
                names = {s.id for s in states} | {r.id for _, r in relations}
                invalid = [(j, r) for j, r in relations if r.src not in names or r.dst not in names]
                if not invalid:
                    break
                for j, r in invalid:
                    losses.append({'reading_index': i, 'relation_index': j,
                        'reason': 'UNRESOLVED_SOURCE_RELATION_ENDPOINT', 'relation_id': r.id})
                relations = [(j, r) for j, r in relations if (j, r) not in invalid]
            kept.append(SourceReading.model_validate({**raw, 'states': states,
                'relations': [r for _, r in relations]}))
        except (ValueError, KeyError, TypeError) as exc:
            losses.append({'reading_index': i, 'reason': 'READING_NOT_ADMITTED:' + str(exc)[:700],
                'original_validation': first})
    result = SourceProposals.model_validate({**value, 'readings': kept})
    return result, losses


class StateDescriptor(StrictModel):
    """Finite observation labels derived from already critiqued source spans."""
    key: str = Field(min_length=1, max_length=140)
    label: str = Field(min_length=1, max_length=200)
    features: list[str] = Field(max_length=16)
    source_refs: list[str] = Field(min_length=1, max_length=16)
    feature_order_known: bool = True
    feature_multiplicity_known: bool = True
    node_kind: Literal['predicate', 'textual_clause'] = 'predicate'


class ClaimCoordinates(StrictModel):
    predicate: str = Field(min_length=1, max_length=200)
    participant: str = Field(min_length=1, max_length=120)
    referent: str = Field(min_length=1, max_length=120)
    quantifier: Quantifier
    tense: Tense
    scope: str = Field(min_length=1, max_length=160)


class TransitionDescriptor(StrictModel):
    version: Literal['source-transition011/1']
    source: StateDescriptor
    target: StateDescriptor
    relation_kind: RelationKind
    polarity: Polarity
    modality: Modality
    order_kind: Literal['TEXT_ORDER', 'EVENT_ORDER', 'INFERRED_EVENT_ORDER', 'UNKNOWN']
    projection_features: list[str] = Field(max_length=16)
    critic_status: Literal['HYPOTHESIS', 'CONFLICT', 'UNSUPPORTED', 'UNKNOWN']
    review_flags: list[str] = Field(default_factory=list, max_length=12)
    claim: ClaimCoordinates | None = Field(default=None, exclude_if=lambda v: v is None)


def strict_response_schema(model) -> dict:
    """The inference transport requires every response key, including empty lists."""
    schema = model.model_json_schema()
    def visit(value):
        if isinstance(value, dict):
            if value.get('type') == 'object' and 'properties' in value:
                value['required'] = list(value['properties'])
                value['additionalProperties'] = False
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(schema)
    return schema
