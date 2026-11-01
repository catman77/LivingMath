"""Immutable equation AST with explicit binder and equality scope, not a source DSL."""
from typing import Annotated, Literal, Union
import hashlib
import json

from pydantic import Field, model_validator
from .models import StrictModel

EqualityScope = Literal['full_state', 'observation']

def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Var(StrictModel):
    tag: Literal['var'] = 'var'
    name: Literal['x'] = 'x'
    sort: Literal['state'] = 'state'


class Apply(StrictModel):
    tag: Literal['apply'] = 'apply'
    operation: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z][A-Za-z0-9_]*$')
    argument: Annotated[Union[Var, 'Apply'], Field(discriminator='tag')]


Term = Annotated[Union[Var, Apply], Field(discriminator='tag')]
Apply.model_rebuild()


class Eq(StrictModel):
    tag: Literal['eq'] = 'eq'
    left: Term
    right: Term


class Implies(StrictModel):
    tag: Literal['implies'] = 'implies'
    premise: Eq
    conclusion: Eq


class Formula(StrictModel):
    dsl_version: Literal['dav-equations/1'] = 'dav-equations/1'
    binder: Literal['forall x:state'] = 'forall x:state'
    equality: Literal['full_state', 'observation'] = 'full_state'
    body: Annotated[Union[Eq, Implies], Field(discriminator='tag')]

    @model_validator(mode='before')
    @classmethod
    def bounds(cls, value):
        if isinstance(value, cls):
            value = value.model_dump()
        pending = [(value, 0)]
        nodes = 0
        while pending:
            part, depth = pending.pop()
            if depth > 12:
                raise ValueError('AST_DEPTH_LIMIT')
            if isinstance(part, dict):
                nodes += 1
                pending.extend((v, depth + 1) for v in part.values() if isinstance(v, (dict, list)))
            elif isinstance(part, list):
                pending.extend((v, depth + 1) for v in part)
            if nodes > 64:
                raise ValueError('AST_NODE_LIMIT')
        return value

    def canonical_ast(self) -> dict:
        def visit(node):
            if isinstance(node, dict):
                out = {k: visit(v) for k, v in node.items()}
                if out.get('tag') == 'eq' and canonical(out['left']) > canonical(out['right']):
                    out['left'], out['right'] = out['right'], out['left']
                return out
            return node
        return visit(self.model_dump())


def term(operation: str) -> Apply:
    return Apply(operation=operation, argument=Var())


def eq(left: str, right: str, equality: EqualityScope = 'full_state') -> Formula:
    return Formula(equality=equality, body=Eq(left=term(left), right=term(right)))


def implication(a: str, b: str, c: str, d: str, equality: EqualityScope = 'full_state') -> Formula:
    return Formula(equality=equality, body=Implies(premise=Eq(left=term(a), right=term(b)),
                   conclusion=Eq(left=term(c), right=term(d))))
