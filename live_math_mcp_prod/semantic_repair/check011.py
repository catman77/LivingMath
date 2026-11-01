"""Exact declared-domain witnesses; source support never follows from the model."""
from collections import deque

from davcore.ast import digest
from .realization import observe_state
from .trace008 import adapter, trace


def reference_step(network: dict, operation: int, state: int) -> int:
    """Independent integer-count implementation, not Network.fire/Adapter.apply."""
    names = [s['id'] for s in network['species']]
    reaction = network['reactions'][operation]
    values = [(state >> i) & 1 for i in range(len(names))]
    remaining = [v - reaction['reactants'].get(name, 0) for name, v in zip(names, values)]
    if min(remaining) < 0:
        return state
    after = [v + reaction['products'].get(name, 0) for name, v in zip(names, remaining)]
    if any(v not in (0, 1) for v in after):
        return state
    return sum(v << i for i, v in enumerate(after))


def analyze(model: dict) -> dict:
    a = adapter(model)
    network = model['spec']['reaction_network']
    n = len(model['premise_ids'])
    independent = {str(i): [reference_step(network, i, s) for s in a.states()] for i in range(n)}
    if any(a.apply('R' + str(i), s) != independent[str(i)][s] for s in a.states() for i in range(n)):
        raise ValueError('INDEPENDENT_SOURCE_TRANSITION_TABLE_DISAGREEMENT')
    reached = set(model['initial_states'])
    queue = deque(reached)
    while queue:
        state = queue.popleft()
        for i in range(n):
            after = independent[str(i)][state]
            if after not in reached:
                reached.add(after)
                queue.append(after)
    returns = []
    cycles = []
    walks = []
    truncated = False
    for start in model['initial_states']:
        origin = observe_state(model, start)
        pending = [(start, [], {start})]
        while pending:
            state, operations, seen = pending.pop()
            if len(walks) >= 128:
                truncated = True
                break
            if len(operations) >= min(model['coordinate_count'] + 1, 9):
                continue
            for i, pid in enumerate(model['premise_ids']):
                after = independent[str(i)][state]
                if after == state:
                    continue
                path = operations + [pid]
                witness = trace(model, start, path)
                walks.append(witness)
                final = observe_state(model, after)
                known = origin.get('observation_known') and final.get('observation_known')
                if known and final['projection'] == origin['projection']:
                    returns.append({'trace': witness, 'relation': 'Equivalent_O',
                        'criterion': model['observer']['criterion'], 'full_state_identity': start == after,
                        'source_cycle_status': model['observer']['source_cycle_status'],
                        'source_support': 'HYPOTHESIS_ONLY', 'source_claim_verified': False})
                if after == start and len(path) >= 2:
                    cycles.append(witness)
                if after not in seen:
                    pending.append((after, path, seen | {after}))
    comparisons = []
    states = model['observer']['states']
    positions = {s['key']: i for i, s in enumerate(states)}
    for rel in model['observer']['source_annotations']:
        ls, rs = states[positions[rel['source']['key']]], states[positions[rel['target']['key']]]
        left, right = ls['features'], rs['features']
        order_known = all(s.get('feature_order_known', True) and s.get('feature_multiplicity_known', True) for s in (ls, rs))
        multiset_known = all(s.get('feature_multiplicity_known', True) for s in (ls, rs))
        x = 1 << positions[rel['source']['key']]
        y = 1 << positions[rel['target']['key']]
        ox, oy = observe_state(model, x), observe_state(model, y)
        equivalent = (ox['projection'] == oy['projection']) if ox['observation_known'] and oy['observation_known'] else None
        comparisons.append({'premise_id': rel['premise_id'], 'relation_kind': rel['relation_kind'],
            'polarity': rel['polarity'], 'critic_status': rel['critic_status'],
            'assumption_withdrawn': rel['assumption_withdrawn'],
            'full_state_equal': x == y, 'sequence_equal': left == right if left and right and order_known else None,
            'multiset_equal': sorted(left) == sorted(right) if left and right and multiset_known else None,
            'set_equal': set(left) == set(right) if left and right else None,
            'shared_features': sorted(set(left) & set(right)),
            'named_projection': model['observer']['criterion'], 'Equivalent_O': equivalent,
            'comparison_scope': 'DECLARED_SOURCE_STATE_ENDPOINTS_NOT_A_REACHABILITY_CLAIM',
            'source_equivalence': 'HYPOTHESIS_NOT_VERIFIED'})
    closure = all(independent[str(i)][s] in reached for s in reached for i in range(n))
    one_hot = all(s > 0 and s & (s - 1) == 0 for s in reached)
    return {'source_transition_analysis': {'independent_full_table_sha256': digest(independent),
        'semantic_projection_sha256': digest({'transitions': independent,
            'observations': [{k: v for k, v in observe_state(model, s).items() if k not in {'state_key', 'full_state'}} for s in a.states()]}),
        'independent_transition_count': len(a.states()) * n, 'full_state_tables_agree': True,
        'registered_initial_states': model['initial_states'], 'reachable_states': sorted(reached),
        'T_C_subset_C': closure, 'one_hot_in_declared_domain': one_hot,
        'observation_comparisons': comparisons, 'observed_returns': returns,
        'full_state_cycles': cycles, 'walks': walks, 'walk_witnesses_truncated': truncated,
        'cycle_search_scope': 'SIMPLE_FIRED_PATHS_FROM_REGISTERED_INITIALS_UP_TO_STATE_BOUND',
        'source_cycle_status': model['observer']['source_cycle_status'],
        'performance': 'UNKNOWN', 'source_claim_verified': False},
        'invariants': {'single_source_state_in_registered_reachable_domain': one_hot,
            'successor_closed_in_registered_domain': closure,
            'no_performance_attested': True, 'unknown_projection_does_not_imply_equality': True}}


def ablations(premises, binding, model, context) -> list[dict]:
    from .compiler import compile_model
    a = adapter(model)
    result = []
    for premise in premises:
        deleted = compile_model(premises, binding, profile='typed008/1', context=context,
            disabled=(premise['id'],))
        b = adapter(deleted)
        witness = next(({'state': s, 'operation': op, 'before': a.apply(op, s), 'after': b.apply(op, s)}
            for s in a.states() for op in a.ops if a.apply(op, s) != b.apply(op, s)), None)
        annotation = next(p for p in deleted['observer']['source_annotations'] if p['premise_id'] == premise['id'])
        result.append({'kind': 'SOURCE_UNIT_DELETION', 'source_operation_id': premise['id'],
            'source_refs': premise['source_refs'], 'changed': witness is not None,
            'target_witness': witness, 'source_assumption_withdrawn': annotation['assumption_withdrawn'],
            'historical_source_annotation_retained': True,
            'effect': 'TARGET_OPERATION_CHANGED' if witness else 'SOURCE_ANNOTATION_ONLY_NO_EXECUTABLE_EFFECT',
            'scope': 'All finite markings for target effect; source interpretation not verified'})
    return result
