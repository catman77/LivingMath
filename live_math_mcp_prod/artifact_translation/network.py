"""Bounded symbolic reaction data and explicit, total guarded command semantics."""
from typing import Annotated, Literal

from pydantic import Field, model_validator
from davcore.models import StrictModel

Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[\w.:/-]+$')]


class Species(StrictModel):
    id: Identifier
    label: str = Field(min_length=1, max_length=120)
    provenance_kind: Literal['symbolic_species'] = 'symbolic_species'
    source_refs: list[Identifier] = Field(min_length=1, max_length=30)


class Reaction(StrictModel):
    id: Identifier
    reactants: dict[Identifier, Annotated[int, Field(ge=1, le=1)]] = Field(min_length=1, max_length=8)
    products: dict[Identifier, Annotated[int, Field(ge=1, le=1)]] = Field(min_length=1, max_length=8)
    source_relation_ids: list[Identifier] = Field(min_length=1, max_length=8)


class Network(StrictModel):
    signature: Literal['symbolic-reaction-network/1'] = 'symbolic-reaction-network/1'
    capacity: Literal[1] = 1
    species: list[Species] = Field(min_length=1, max_length=8)
    reactions: list[Reaction] = Field(min_length=1, max_length=12)
    interpretation: Literal['ANALOGICAL_MODEL_NOT_PHYSICAL_CHEMISTRY'] = 'ANALOGICAL_MODEL_NOT_PHYSICAL_CHEMISTRY'

    @model_validator(mode='after')
    def well_typed(self):
        ids=[s.id for s in self.species]
        if len(ids)!=len(set(ids)) or len({r.id for r in self.reactions})!=len(self.reactions):
            raise ValueError('DUPLICATE_NETWORK_IDENTIFIER')
        if any(not (set(r.reactants)|set(r.products))<=set(ids) for r in self.reactions):
            raise ValueError('COMPLEX_REFERENCES_UNKNOWN_SPECIES')
        return self


def state_vector(network: Network, state: int) -> dict[str,int]:
    if type(state) is not int or not 0<=state<2**len(network.species):
        raise ValueError('INVALID_FINITE_MARKING')
    return {s.id:(state>>i)&1 for i,s in enumerate(network.species)}


def enabled(network: Network, reaction: int, state: int) -> bool:
    if not 0<=reaction<len(network.reactions):
        raise ValueError('UNKNOWN_REACTION')
    r=network.reactions[reaction];v=state_vector(network,state)
    return (all(v[s]>=n for s,n in r.reactants.items()) and
            all(0<=v[s]-r.reactants.get(s,0)+r.products.get(s,0)<=1 for s in v))


def fire(network: Network, reaction: int, state: int) -> int:
    """Fire if enabled AND within capacity, otherwise identity; no physical kinetics."""
    if not enabled(network,reaction,state):
        return state
    r=network.reactions[reaction];v=state_vector(network,state)
    return sum((v[s.id]-r.reactants.get(s.id,0)+r.products.get(s.id,0))<<i
               for i,s in enumerate(network.species))


def operations(network: Network) -> tuple[str,...]:
    return ('Id','One','Zero',*(f'S{i}' for i in range(len(network.species))),
            *(f'E{i}' for i in range(len(network.reactions))),*(f'R{i}' for i in range(len(network.reactions))))


def apply(network: Network, operation: str, state: int) -> int:
    state_vector(network,state)
    if operation not in operations(network):
        raise ValueError('UNKNOWN_REACTION_OPERATION')
    if operation in {'Id','One','Zero'}:
        return {'Id':state,'One':1,'Zero':0}[operation]
    i=int(operation[1:])
    if operation.startswith('R'):return fire(network,i,state)
    if operation.startswith('E'):return int(enabled(network,i,state))
    return (state>>i)&1
