"""Counterexample-driven finite representation proposals, independent of the acceptance checker."""
from davcore.adapters import Adapter, AdapterSpec


def initial_observer_state(metadata: dict) -> dict:
    spec = AdapterSpec.model_validate(metadata['spec'])
    a = Adapter(spec)
    mask = (1 << a.width) - 1 if spec.mask is None else spec.mask
    return {'original_mask': mask, 'pending_masks': [mask], 'tested_masks': [],
            'current_mask': mask, 'counterexamples': [], 'candidate_failures': [],
            'search_family_size': 1 << (a.width - mask.bit_count())}


def next_candidate(state: dict) -> int | None:
    tested = set(state['tested_masks'])
    pending = set(state['pending_masks']) - tested
    return min(pending, key=lambda n: ((n ^ state['original_mask']).bit_count(), n)) if pending else None


def refine_from_counterexample(state: dict, witness: dict, width: int) -> dict:
    """Any congruent refinement must separate this raw-state pair on at least one hidden bit."""
    mask = state['current_mask']
    x, y = witness['states']
    differing_hidden = (x ^ y) & ~mask & ((1 << width) - 1)
    if not differing_hidden:
        raise ValueError('COUNTEREXAMPLE_HAS_NO_HIDDEN_DISTINCTION')
    proposals = [mask | (1 << bit) for bit in range(width) if differing_hidden & (1 << bit)]
    return {**state, 'tested_masks': sorted(set(state['tested_masks']) | {mask}),
            'pending_masks': sorted((set(state['pending_masks']) | set(proposals)) - {mask}),
            'counterexamples': state['counterexamples'] + [witness],
            'last_RCA': {'reason': 'OBSERVED_CLASS_MERGES_DIVERGENT_CONTINUATIONS',
                         'raw_states': [x, y], 'differing_hidden_mask': differing_hidden,
                         'proposed_masks': proposals, 'domain_and_assumptions_changed': False}}
