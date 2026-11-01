"""Versioned source/problem interchange; coordination introduces no new mathematical primitive."""
from typing import Annotated, Literal

from davcore.ast import Formula
from davcore.models import StrictModel
from pydantic import Field, model_validator

from .artifact_contract import ArtifactBudget

Name = Annotated[str, Field(min_length=1, max_length=160, pattern=r'^[\w][\w .:/-]*$')]
Atom = Annotated[str, Field(max_length=4096)] | Annotated[int, Field(ge=-(2**63), le=2**63-1)] | bool
Reference = Annotated[str, Field(min_length=1, max_length=240)]


class Prediction(StrictModel):
    feature: Name
    value: Atom
    unit: Name | None = None


class Fact(StrictModel):
    feature: Name
    value: Atom | None = None
    unit: Name | None = None
    source_refs: list[Reference] = Field(default_factory=list, max_length=32)


class Hypothesis(StrictModel):
    model_id: Name
    target: Atom | None = None
    predictions: list[Prediction] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def distinct_features(self):
        if len({p.feature for p in self.predictions}) != len(self.predictions):
            raise ValueError('DUPLICATE_MODEL_FEATURE')
        return self


class Problem(StrictModel):
    kind: Literal['observer_refinement', 'law_check', 'identify_model', 'input_gap','artifact_reconstruction']
    scope: Name
    title: str = Field(default='', max_length=500)
    registration_id: int | None = Field(default=None, ge=1)
    adapter_binding: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    formula: Formula | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=32)
    required_features: list[Name] = Field(default_factory=list, max_length=32)
    source_refs: list[Reference] = Field(default_factory=list, max_length=128)
    unknown_refs: list[Reference] = Field(default_factory=list, max_length=128)
    artifact_snapshot_id: int | None = Field(default=None,ge=1,exclude_if=lambda v:v is None)
    artifact_profile: Literal['typed008/1'] | None = Field(default=None,exclude_if=lambda v:v is None)
    artifact_budget: ArtifactBudget | None = Field(default=None,exclude_if=lambda v:v is None)
    artifact_interpretation: Literal['general011', 'observer012', 'observer013', 'meaning014'] | None = Field(default=None,exclude_if=lambda v:v is None)

    @model_validator(mode='after')
    def applicable(self):
        fields=(self.artifact_snapshot_id,self.artifact_profile,self.artifact_budget)
        if self.kind=='artifact_reconstruction' and any(v is None for v in fields):
            raise ValueError('ARTIFACT_SNAPSHOT_PROFILE_BUDGET_REQUIRED')
        if self.kind!='artifact_reconstruction' and any(v is not None for v in fields):
            raise ValueError('ARTIFACT_FIELDS_REQUIRE_ARTIFACT_TASK')
        if self.kind != 'artifact_reconstruction' and self.artifact_interpretation is not None:
            raise ValueError('ARTIFACT_FIELDS_REQUIRE_ARTIFACT_TASK')
        if self.kind in {'observer_refinement', 'law_check'} and (self.registration_id is None or self.adapter_binding is None):
            raise ValueError('PINNED_ADAPTER_REQUIRED')
        if self.kind == 'law_check' and self.formula is None:
            raise ValueError('LAW_FORMULA_REQUIRED')
        if self.kind == 'identify_model' and (len(self.hypotheses) < 2 or len({h.model_id for h in self.hypotheses}) != len(self.hypotheses)):
            raise ValueError('AT_LEAST_TWO_DISTINCT_MODELS_REQUIRED')
        if self.kind == 'input_gap' and not self.required_features:
            raise ValueError('EXPLICIT_INPUT_REQUIREMENTS_REQUIRED')
        return self

    def structural(self) -> dict:
        out = self.model_dump(exclude={'title'})
        if self.formula:
            out['formula'] = self.formula.canonical_ast()
        for key in ['required_features', 'source_refs', 'unknown_refs']:
            out[key] = sorted(set(out[key]))
        out['hypotheses'] = sorted(out['hypotheses'], key=lambda h: h['model_id'])
        for h in out['hypotheses']:
            h['predictions'].sort(key=lambda p: p['feature'])
        return out


class ResearchInput(StrictModel):
    format: Literal['livingmath-autoresearch/1'] = 'livingmath-autoresearch/1'
    scope: Name
    origin: str = Field(default='DECLARED_CLIENT_INPUT', min_length=1, max_length=500)
    artifact_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    source_refs: list[Reference] = Field(default_factory=list, max_length=128)
    problems: list[Problem] = Field(default_factory=list, max_length=128)
    facts: list[Fact] = Field(default_factory=list, max_length=128)

    @model_validator(mode='after')
    def same_scope(self):
        if any(p.scope != self.scope for p in self.problems):
            raise ValueError('INPUT_AND_PROBLEM_SCOPE_MUST_MATCH')
        if not self.problems and not self.facts:
            raise ValueError('PROBLEMS_OR_FACTS_REQUIRED')
        return self
