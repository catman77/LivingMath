"""Small reviewed local models. No dynamic operation evaluator or source DSL."""
from collections import Counter
from fractions import Fraction

from .canonical import Refusal, canonical_hash

MODEL_KINDS = {
    'poetry_A_then_B': ('poetry', ['read_A', 'read_B'], 'Order A then B, reader meaning unresolved'),
    'poetry_B_then_A': ('poetry', ['read_B', 'read_A'], 'Order B then A, reader meaning unresolved'),
    'pythagoras_orthogonality': ('pythagoras', ['orthogonal_vectors'], 'Does the cross term vanish?'),
    'pythagoras_quadratic': ('pythagoras', ['quadratic_form'], 'Which quadratic form is invariant?'),
    'boa_first_order': ('boa', ['first_order'], 'What body histories merge under G?'),
    'boa_second_order': ('boa', ['second_order'], 'Can a pair preserve reversible history?'),
}
G_DEFINITION = 'G(s) = ((s << 1) XOR (s >> 3)) AND 127; s in 0..255'


def g(s):
    return ((s << 1) ^ (s >> 3)) & 127


def reversible_step(pair):
    previous, current = pair
    return current, previous ^ g(current)


def reversible_inverse(pair):
    current, following = pair
    return following ^ g(current), current


def poetry(order):
    # Declared illustrative attention coordinates: repetition and boundary.
    # No claim that these coordinates determine the meaning of either text.
    state = (1, 1)
    trace = [{'state': list(state), 'operation': 'initial'}]
    for operation in order:
        a, b = state
        if operation == 'read_A':
            state = (a + 1, b + a)
        elif operation == 'read_B':
            state = (a + b, b + 1)
        else:
            raise Refusal('FORBIDDEN_OPERATION', operation)
        trace.append({'operation': operation, 'state': list(state)})
    return {'coordinates': list(state), 'trace': trace,
            'interpretation': 'A privileges repetition; B privileges boundary, in this declared attention model only.',
            'reader_semantics': 'UNKNOWN', 'reference_six_readings': 'NOT_REPRODUCED'}


def pythagoras(perspective):
    a, b, c = 3, 4, 5
    u, v = (3, 0), (0, 4)
    dot = sum(x * y for x, y in zip(u, v))
    norm_sum = sum((x + y) ** 2 for x, y in zip(u, v))
    q = lambda vector: sum(Fraction(x) ** 2 for x in vector)
    identity = a * a + b * b == c * c
    if 'orthogonality' in perspective:
        model = {'objects': 'two orthogonal vectors and their vector sum',
                 'vectors': [list(u), list(v)], 'dot_product': dot,
                 'cross_term': 2 * dot, 'sum_vector': [a, b]}
    else:
        rotation = ((Fraction(3, 5), Fraction(-4, 5)),
                    (Fraction(4, 5), Fraction(3, 5)))
        rotated = tuple(sum(row[j] * (a, b)[j] for j in range(2)) for row in rotation)
        model = {'objects': 'positive quadratic form and rational isometry',
                 'Q_matrix': [[1, 0], [0, 1]],
                 'rational_rotation': [[str(x) for x in row] for row in rotation],
                 'rotated_vector': [str(x) for x in rotated],
                 'q_rotation_invariant': q(rotated) == q((a, b))}
    return {'perspective': perspective, 'model': model, 'triangle': [a, b, c], 'orthogonal_dot': dot,
            'quadratic_diagonal': [1, 1], 'q_sum': str(q((a, b))),
            'norm_of_vector_sum_squared': norm_sum, 'invariant': identity,
            'exact_checks': {'cross_term_zero': dot == 0, 'identity_3_4_5': identity,
                             'parallelogram_identity': q((a + b, a - b)) == 2 * q((a, b))},
            'scope': 'Exact finite example and algebraic identity; established theorem retained, no new theorem.'}


def trajectory(mode, initial, steps):
    state = tuple(initial) if mode == 'second_order' else initial[1]
    seen, bodies, rules = {}, [], []
    cycle = None
    for t in range(steps + 1):
        if state in seen and cycle is None:
            cycle = {'transient': seen[state], 'period': t - seen[state]}
        seen.setdefault(state, t)
        body = state[1] if mode == 'second_order' else state
        bodies.append(body)
        rules.append(g(body) & 15)
        state = reversible_step(state) if mode == 'second_order' else g(state)
    multiplicity = Counter(bodies)
    return {'initial_pair': initial, 'distinct_bodies': len(multiplicity),
            'distinct_rule_bins': len(set(rules)), 'body_repeats': len(bodies) - len(multiplicity),
            'max_body_multiplicity': max(multiplicity.values()), 'cycle_within_horizon': cycle,
            'trajectory_sha256': canonical_hash(bodies), 'body_sequence': bodies}


def boa(mode, seeds, steps):
    if not 1 <= len(seeds) <= 32 or not 1 <= steps <= 512:
        raise Refusal('DEMO_BUDGET_EXCEEDED')
    if any(len(p) != 2 or any(type(x) is not int or not 0 <= x < 256 for x in p) for p in seeds):
        raise Refusal('INVALID_BIT_SEED')
    rows = [trajectory(mode, pair, steps) for pair in seeds]
    return {'mode': mode, 'G': G_DEFINITION, 'G_sha256': canonical_hash(G_DEFINITION),
            'seed_commitment': canonical_hash(seeds), 'steps': steps, 'starts': len(seeds),
            'state_domain_size': 65536 if mode == 'second_order' else 256,
            'observation_domain_size': 256, 'rule_observable': 'G(body) & 15; fixed bins, not discovered laws',
            'mean_distinct_bodies': sum(x['distinct_bodies'] for x in rows) / len(rows),
            'mean_distinct_rule_bins': sum(x['distinct_rule_bins'] for x in rows) / len(rows),
            'seed_dependence': len({x['trajectory_sha256'] for x in rows}), 'runs': rows,
            'slide_numbers': 'NOT_REPRODUCED_MISSING_ORIGINAL_G_SEED_CORPUS'}


def evaluate(model_kind, settings):
    if model_kind not in MODEL_KINDS:
        raise Refusal('UNSUPPORTED_MODEL')
    if model_kind.startswith('poetry_'):
        return poetry(MODEL_KINDS[model_kind][1])
    if model_kind.startswith('pythagoras_'):
        return pythagoras(model_kind)
    return boa('second_order' if model_kind.endswith('second_order') else 'first_order',
               settings['seeds'], settings['steps'])


def independent_oracles(settings):
    first = poetry(['read_A', 'read_B'])['coordinates']
    second = poetry(['read_B', 'read_A'])['coordinates']
    inverse_ok = all(reversible_inverse(reversible_step((a, b))) == (a, b)
                     for a in range(256) for b in range(256))
    outputs = {}
    collision = None
    for value in range(256):
        if g(value) in outputs:
            collision = [outputs[g(value)], value, g(value)]
            break
        outputs[g(value)] = value
    return {'poetry_noncommutative_in_declared_model': first != second,
            'poetry_outputs': [first, second], 'reader_recognition': 'NOT_TESTED',
            'pythagorean_checks': pythagoras('independent')['exact_checks'],
            'boa_inverse_all_65536_pairs': inverse_ok,
            'first_order_collision': collision,
            'state_vs_observation': 'Bijective pair dynamics does not imply scalar body observations are invertible.',
            'seeds_sha256': canonical_hash(settings['seeds'])}
