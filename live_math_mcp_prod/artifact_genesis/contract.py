"""Lightweight source/H records. Mathematical expressions remain DAV's existing AST."""
from typing import Literal
from pydantic import Field, model_validator
from davcore.models import StrictModel


class RawSpan(StrictModel):
    id: str = Field(min_length=1,max_length=140)
    document_id: str
    document_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    edition: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = Field(min_length=1,max_length=4096)
    source_address: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def width(self):
        if self.end-self.start!=len(self.text.encode()):raise ValueError('SOURCE_SPAN_BYTE_WIDTH')
        return self


class RawPacket(StrictModel):
    id: str
    document_id: str
    document_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    edition: str
    language: Literal['en','ru']
    spans: list[RawSpan] = Field(min_length=1,max_length=8)
    context: list[RawSpan] = Field(default_factory=list,max_length=8)
    grammar: dict[str,list[str]] = Field(default_factory=dict)

    @model_validator(mode='before')
    @classmethod
    def no_editor_answers(cls,value):
        if isinstance(value,cls):return value
        forbidden={'relations','roles','expected_labels','expected_answer','target_graph','source_graph','expected_mappings','oracle','checker'}
        pending=[value]
        while pending:
            item=pending.pop()
            if isinstance(item,dict):
                if forbidden.intersection(item):raise ValueError('EDITOR_GRAPH_TARGET_OR_ANSWER_NOT_ALLOWED')
                pending.extend(item.values())
            elif isinstance(item,list):pending.extend(item)
        return value

    @model_validator(mode='after')
    def binding(self):
        rows=self.spans+self.context
        if len({s.id for s in rows})!=len(rows):raise ValueError('DUPLICATE_SOURCE_SPAN')
        if any((s.document_id,s.document_sha256,s.edition)!=(self.document_id,self.document_sha256,self.edition) for s in rows):
            raise ValueError('CROSS_SOURCE_CONTEXT_FORBIDDEN')
        allowed={'negation','coordination','contrast','order','condition','directive_phrases','time','subject_pronouns','object_pronouns'}
        if set(self.grammar)-allowed or any(len(v)>20 for v in self.grammar.values()):raise ValueError('UNREVIEWED_GRAMMAR_CUES')
        return self
