"""Strict source-bound compiler inputs, deliberately without query or free metadata."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator

from .relations011 import TransitionDescriptor
from .relations012 import TransitionDescriptor012


class Role(StrictModel):
    predicate: str = Field(pattern=r'^p_[a-f0-9]{24}$')
    mention_ref: str
    scope: str = Field(pattern=r'^s_[a-f0-9]{24}$')
    stage: str = 'SCHEMATIC'
    modality: Literal['TEXTUAL_CLAIM', 'PRESCRIPTION', 'LYRICAL_CLAIM', 'NARRATED_EVENT', 'UNKNOWN']
    # Absent fields retain the exact legacy coordinate contract. Explicit UNKNOWN
    # is deliberately different from an unscoped legacy reading.
    domain: str | None = None
    quantifier: Literal['ALL', 'SOME', 'NAMED_CASE', 'UNKNOWN'] | None = None
    polarity: Literal['POSITIVE', 'NEGATIVE', 'UNKNOWN'] | None = None
    participant: str | None = None
    time: str | None = None


class Guard(StrictModel):
    id: str
    text: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class Realization(StrictModel):
    version: Literal['typed008/1'] = 'typed008/1'
    kind: Literal['GUARDED_TRANSFORMATION', 'NARRATIVE_OCCURRENCE', 'PRESCRIPTION', 'SIGNED_ASSERTION', 'STATE_TRANSITION']
    guards: list[Guard] = Field(default_factory=list, max_length=4)
    source_order: int = Field(ge=0)
    occurrence_id: str
    label: str = Field(min_length=1)
    direction: Literal['INCOMING', 'FORWARD', 'BACK_TO_ADDRESSEE'] | None = None
    sign: Literal['POSITIVE', 'NEGATIVE'] | None = None
    actor: str | None = None
    transition: TransitionDescriptor | TransitionDescriptor012 | None = Field(default=None, exclude_if=lambda v: v is None)


class Premise(StrictModel):
    id: str = Field(pattern=r'^u_[a-f0-9]{24}$')
    src: Role
    dst: Role
    relation: Literal['condition', 'role'] = 'condition'
    source_refs: list[str] = Field(min_length=1)
    premise_unit: str
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    observer_version: Literal['local-clauses004/1', 'clauses005/1', 'discourse005/1'] = 'local-clauses004/1'
    semantics: Literal['CONDITIONAL', 'NORMATIVE_CONNECTIVITY', 'CLASS_INSTANTIATION', 'NARRATIVE_SEQUENCE', 'UNKNOWN'] | None = None
    assumptions: list[str] | None = None
    requires_binding: dict[str, str] | None = None
    realization: Realization | None = None


class Binding(StrictModel):
    id: str
    assignments: dict[str, str]
    status: Literal['HYPOTHESIS'] = 'HYPOTHESIS'
    assumptions: list[str] = Field(default_factory=list)
    project: str = 'LM_QA_REPAIR004'


class CompilerRequest(StrictModel):
    premises: list[Premise]
    binding: Binding
    profile: Literal['legacy007', 'typed008/1'] = 'legacy007'

    @model_validator(mode='before')
    @classmethod
    def firewall(cls, value):
        denied = {'q', 'query', 'gold', 'answer', 'expected_answer', 'expected_labels',
                  'rationale', 'metadata', 'cache', 'transitive_closure', 'desired_conclusion'}
        stack = [value]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if denied.intersection(x):
                    raise ValueError('QUERY_COMPILER_FIREWALL')
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
        return value


def coordinate(role: dict) -> tuple:
    # Neither mention nor referent identity alone is a state equality.
    base = (role['predicate'], role['scope'], role['stage'], role['modality'])
    fields = ('domain', 'quantifier', 'polarity', 'participant', 'time')
    return base + tuple(role.get(k) or 'UNKNOWN' for k in fields) if any(role.get(k) is not None for k in fields) else base
