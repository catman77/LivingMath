"""Optional W suggestion port. No learned policy, training or proof reward dependency."""
from dataclasses import dataclass
import random
from typing import Protocol


@dataclass(frozen=True)
class ProbeContext:
    adapter_binding: str
    admissible_states: tuple[int, ...]
    budget: int
    seed: int


class Explorer(Protocol):
    def suggest(self, context: ProbeContext) -> tuple[int, ...]: ...


def probes(context: ProbeContext, explorer: Explorer | None = None) -> dict:
    if explorer is None:
        states = list(context.admissible_states)
        random.Random(context.seed).shuffle(states)
        return {'policy': 'random_baseline', 'states': states[:context.budget],
                'neural_W_status': 'NOT_RUN_NO_TRAINED_POLICY_SHIPPED'}
    suggestions = explorer.suggest(context)
    if (not isinstance(suggestions, tuple) or len(suggestions) > context.budget
            or len(suggestions) != len(set(suggestions))
            or any(type(s) is not int or s not in context.admissible_states for s in suggestions)):
        raise ValueError('INVALID_W_SUGGESTIONS')
    return {'policy': 'optional_trusted_explorer', 'adapter_binding': context.adapter_binding,
            'states': list(suggestions), 'proof_authority': False}
