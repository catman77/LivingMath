"""Source relation and proposal data; no source parser or new expression DSL."""
from typing import Literal

from davcore.models import StrictModel
from pydantic import Field, model_validator

from .network import Identifier

Edit = Literal['transition','catalytic','reverse_orientation','merge_roles','split_roles',
               'latent_guard','split_intermediate']


def default_edits() -> list[Edit]:
    return ['transition','catalytic','reverse_orientation','merge_roles','split_roles',
            'latent_guard','split_intermediate']


class SourceNode(StrictModel):
    id: Identifier
    kind: Literal['symbolic_role','textual_clause','predicate'] = 'symbolic_role'
    source_refs: list[Identifier] = Field(min_length=1,max_length=20)


class SourceRelation(StrictModel):
    id: Identifier
    kind: Literal['sequence','contrast','role','cooccur','repeat','condition','conjunction','order']
    src: Identifier
    dst: Identifier
    source_refs: list[Identifier] = Field(min_length=1,max_length=30)
    grade: Literal['A','B'] = 'B'


class SourceGraph(StrictModel):
    id: Identifier
    nodes: list[SourceNode] = Field(min_length=2,max_length=8)
    relations: list[SourceRelation] = Field(min_length=1,max_length=12)
    scope: Literal['textual_relations_not_physical_time'] = 'textual_relations_not_physical_time'
    interpretation: Literal['EXECUTABLE_TARGET', 'META_ONLY', 'MIXED'] = Field(
        default='EXECUTABLE_TARGET', exclude_if=lambda v: v == 'EXECUTABLE_TARGET')
    semantics_version: Literal['source-graph012/1'] | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode='after')
    def addresses(self):
        ns={n.id for n in self.nodes}
        if len(ns)!=len(self.nodes) or len({r.id for r in self.relations})!=len(self.relations):
            raise ValueError('DUPLICATE_SOURCE_IDENTIFIER')
        if any(r.src not in ns or r.dst not in ns for r in self.relations):
            raise ValueError('RELATION_REFERENCES_UNKNOWN_SOURCE_NODE')
        if self.interpretation != 'EXECUTABLE_TARGET' and self.semantics_version != 'source-graph012/1':
            raise ValueError('VERSIONED_META_ONLY_CONTRACT_REQUIRED')
        if self.interpretation == 'EXECUTABLE_TARGET' and any(r.src==r.dst and r.kind in {'contrast','role','order'} for r in self.relations):
            raise ValueError('DISTINCT_SOURCE_ROLES_REQUIRED')
        if self.interpretation == 'EXECUTABLE_TARGET' and not any(r.kind not in {'contrast','order','repeat'} for r in self.relations):
            raise ValueError('NO_RELATION_WITH_DECLARED_TARGET_INTERPRETATION')
        return self


class ProposalRequest(StrictModel):
    graph: SourceGraph
    target_signature: Literal['symbolic-reaction-network/1'] = 'symbolic-reaction-network/1'
    max_candidates: int = Field(default=12,ge=1,le=12)
    allowed_edits: list[Edit] = Field(default_factory=default_edits,min_length=1,max_length=7)

    @model_validator(mode='after')
    def executable_graph(self):
        if self.graph.interpretation != 'EXECUTABLE_TARGET':
            raise ValueError('META_ONLY_HAS_NO_EXECUTABLE_TRANSLATION')
        return self
