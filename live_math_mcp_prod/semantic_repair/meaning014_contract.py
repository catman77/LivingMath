"""A readable account and bounded alternatives; metadata, not a new DSL."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator

from .relations011 import Citation
from .relations013 import Reading013, SourceReview013


class Contrast(StrictModel):
    id: str=Field(min_length=1,max_length=64)
    left_reading: str
    right_reading: str
    dimension: Literal['referent','participant','predicate','polarity','quantifier','tense','modality','scope','attribution','projection','order_kind']
    observable: str=Field(min_length=1,max_length=500)
    left_prediction: Literal['TRUE','FALSE','UNKNOWN']
    right_prediction: Literal['TRUE','FALSE','UNKNOWN']
    differing_assumption: str=Field(min_length=1,max_length=1000)
    evidence: list[Citation]=Field(min_length=1,max_length=6)
    witness_needed: str=Field(min_length=1,max_length=800)

class SourceProposals014(StrictModel):
    version: Literal['source-relations014/1']
    readable_model: str=Field(min_length=1,max_length=12000)
    readings: list[Reading013]=Field(max_length=3)
    contrasts: list[Contrast]=Field(max_length=6)
    losses: list[str]=Field(max_length=24)
    @model_validator(mode='after')
    def refs(self):
        ids={r.id for r in self.readings}
        if len(ids)!=len(self.readings):raise ValueError('DUPLICATE_MEANING_READING')
        if len({c.id for c in self.contrasts})!=len(self.contrasts):raise ValueError('DUPLICATE_SOURCE_CONTRAST')
        if any(c.left_reading not in ids or c.right_reading not in ids or c.left_reading==c.right_reading for c in self.contrasts):raise ValueError('FOREIGN_OR_IDENTICAL_CONTRAST_READING')
        return self

class ContrastReview(StrictModel):
    contrast_id: str
    status: Literal['SUBSTANTIVE_SOURCE_DISTINCTION','SEMANTIC_DISPUTED','NOT_SUPPORTED']
    reason: str=Field(min_length=1,max_length=1400)
    evidence: list[Citation]=Field(max_length=6)

class SourceIssue(StrictModel):
    id: str
    reading_id: str
    location: str=Field(min_length=1,max_length=200)
    reason: str=Field(min_length=1,max_length=1200)
    evidence: list[Citation]=Field(min_length=1,max_length=6)

class SourceReview014(SourceReview013):
    version: Literal['source-critic014/1']  # type: ignore[assignment]  # Separately versioned serialized model
    contrasts: list[ContrastReview]=Field(max_length=6)
    issues: list[SourceIssue]=Field(max_length=12)


def source013(proposal: dict) -> dict:
    p=SourceProposals014.model_validate(proposal).model_dump()
    p.pop('readable_model');p.pop('contrasts');p['version']='source-relations013/1';return p


def review013(review: dict) -> dict:
    r=SourceReview014.model_validate(review).model_dump()
    r.pop('contrasts');r.pop('issues');r['version']='source-critic013/1';return r
