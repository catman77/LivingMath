"""Allowlisted deterministic adapters. Client Python, modules and paths are never accepted."""
from pathlib import Path
from typing import Literal
import hashlib

from pydantic import Field, model_validator
from .ast import digest
from .models import StrictModel
from .baseline import CyclicCA, GraphBits
from artifact_translation.network import Network, apply as reaction_apply, operations as reaction_operations


class AdapterSpec(StrictModel):
    kind: Literal['ca', 'graph', 'gate6', 'reaction_network']
    width: int = Field(default=8, ge=3, le=10)
    mask: int | None = Field(default=None, ge=0, le=1023)
    fidelity: Literal['full', 'empirical'] = 'full'
    assumption: Literal['none', 'P_implies_Q_NOT_SOURCE_ATTESTED'] = 'none'
    reaction_network: Network | None = None

    @model_validator(mode='after')
    def consistent(self):
        if (self.kind == 'reaction_network') != (self.reaction_network is not None):
            raise ValueError('REACTION_DESCRIPTOR_REQUIRED_ONLY_FOR_REGISTERED_REACTION_KIND')
        if self.kind != 'ca' and self.width != 8:
            raise ValueError('FIXED_WIDTH_ADAPTER')
        if self.kind != 'gate6' and self.assumption != 'none':
            raise ValueError('ASSUMPTION_ONLY_FOR_EXPLICIT_BOOLEAN_MODEL')
        actual_width = len(self.reaction_network.species) if self.reaction_network else 2 if self.kind == 'gate6' else self.width
        if self.mask is not None and self.mask >= (1 << actual_width):
            raise ValueError('MASK_OUTSIDE_STATE_SORT')
        return self


def implementation_sha() -> str:
    return digest({name: hashlib.sha256(path.read_bytes()).hexdigest() for name,path in [
        ('baseline.py',Path(__file__).with_name('baseline.py')),('adapters.py',Path(__file__)),
        ('reaction_network.py',Path(__file__).parent.parent/'artifact_translation/network.py')]})


class Adapter:
    """No public factory for arbitrary implementations. State/output sort is a finite bit word."""
    def __init__(self, spec: AdapterSpec):
        self.spec = spec
        self.width = len(spec.reaction_network.species) if spec.reaction_network else 2 if spec.kind == 'gate6' else spec.width
        self.base = CyclicCA(spec.width) if spec.kind == 'ca' else GraphBits() if spec.kind == 'graph' else None
        self.ops = reaction_operations(spec.reaction_network) if spec.reaction_network else tuple(self.base.operations()) if self.base else ('P', 'Q', 'Joint', 'One', 'Zero')
        self._states = tuple(x for x in range(1 << self.width)
                             if spec.assumption == 'none' or not (x & 1) or (x & 2))
        code = implementation_sha()
        self.metadata = {
            'adapter_id': 'dav_builtin_' + spec.kind, 'version': '1', 'source_checksum': code,
            'snapshot_id': digest({'spec': spec.model_dump(), 'implementation': code}),
            'spec': spec.model_dump(), 'observation_fidelity': 'projection' if spec.mask is not None else spec.fidelity,
            'state_space_cardinality': len(self._states), 'enumeration': 'EXACT_FINITE_ALLOWLIST',
            'operation_catalogue': [{'name': op, 'input_sort': 'state', 'output_sort': 'state',
                                     'total': True, 'deterministic': True} for op in self.ops],
            'comparison_semantics': 'bit_word_identity' if spec.mask is None else 'masked_observation_only',
            'assumptions': [spec.assumption] if spec.assumption != 'none' else [],
            'provenance': 'supplied DAV baseline; gate6 is a conditional propositional model, not a material process',
            'resource_limits': {'max_states': 1024, 'max_ast_nodes': 64, 'max_ast_depth': 12},
        }
        if spec.reaction_network:
            self.metadata.update(provenance='Declarative symbolic reaction network; not physical chemistry.',
                guarded_commands='Disabled or capacity-overflow reactions are identity; enabling is an explicit E operation.',
                state_space='All capacity-one markings; no material state filter',kinetics=None,empirically_realized='UNKNOWN')

    def states(self) -> tuple[int, ...]:
        return self._states

    def valid_state(self, x: int) -> bool:
        return type(x) is int and x in self._states

    def apply(self, op: str, state: int) -> int:
        if op not in self.ops:
            raise ValueError('UNKNOWN_OPERATION:' + op)
        if type(state) is not int or not 0 <= state < 1 << self.width:
            raise ValueError('INVALID_STATE_SORT')
        if self.spec.reaction_network:
            out = reaction_apply(self.spec.reaction_network,op,state)
        elif self.base:
            out = self.base.apply(op, state)
        else:
            out = {'P': int(bool(state & 1)), 'Q': int(bool(state & 2)),
                   'Joint': int(bool(state & 1) and bool(state & 2)), 'One': 1, 'Zero': 0}[op]
        if type(out) is not int or not 0 <= out < 1 << self.width:
            raise ValueError('INVALID_ADAPTER_OUTPUT')
        return out

    def observe(self, state: int) -> int:
        return state if self.spec.mask is None else state & self.spec.mask
