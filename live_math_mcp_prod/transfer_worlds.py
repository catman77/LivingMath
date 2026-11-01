"""Finite QA data, not a server ontology or an expression language."""
import hashlib
import itertools
import json
import random

SEEDS = (49127, 49139)
STATES = list(itertools.product((0, 1), repeat=4))
PROFILES = ('expanded_word_count', 'word_boundaries', 'cycle_reach', 'diamond_reach',
            'weighted_table', 'matrix_product', 'parallel_rewrite', 'two_pass_rewrite', 'pilot_word')


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def base_value(index: int, bits: tuple) -> int:
    b = tuple(bits)
    kind = index % 8
    text = ''.join('b' if x else 'a' for x in b)
    if kind == 0:
        return sum(len('ab' if c == 'a' else 'b') for c in text)
    if kind == 1:
        return sum(text[i] != text[i + 1] for i in range(3))
    if kind in (2, 3):
        edges = ((0, 1), (1, 2), (2, 3), (3, 0)) if kind == 2 else ((0, 1), (0, 2), (1, 3), (2, 3))
        found, todo = {0}, [0]
        while todo:
            node = todo.pop()
            for flag, (a, z) in zip(b, edges):
                if flag and a == node and z not in found:
                    found.add(z)
                    todo.append(z)
        return len(found) - 1
    if kind == 4:
        return sum((i + 1) * value for i, value in enumerate(b))
    if kind == 5:
        return b[0] * b[3] + b[1] * b[2]
    if kind == 6:
        expanded = ''.join('ba' if c == 'a' else 'abb' for c in text)
        return expanded.count('b')
    first = ''.join('ab' if c == 'a' else 'ba' for c in text)
    second = ''.join('aab' if c == 'a' else 'b' for c in first)
    return len(second)


def reference_base(index: int, bits: tuple) -> int:
    """Separate arithmetic/path-closure implementation for exhaustive cross-checks."""
    x = list(bits)
    k = index % 8
    if k == 0:
        return 8 - sum(x)
    if k == 1:
        return sum(abs(x[i] - x[i + 1]) for i in range(3))
    if k in (2, 3):
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)] if k == 2 else [(0, 1), (0, 2), (1, 3), (2, 3)]
        matrix = [[a == z for z in range(4)] for a in range(4)]
        for enabled, (a, z) in zip(x, edges):
            matrix[a][z] |= bool(enabled)
        for via in range(4):
            for a in range(4):
                for z in range(4):
                    matrix[a][z] |= matrix[a][via] and matrix[via][z]
        return sum(matrix[0]) - 1
    if k == 4:
        return x[0] + 2 * x[1] + 3 * x[2] + 4 * x[3]
    if k == 5:
        return sum(a * z for a, z in zip(x[:2], reversed(x[2:])))
    if k == 6:
        return 4 + sum(x)
    return 16


def world(index: int, repeat: int) -> dict:
    if index not in range(9) or repeat not in (0, 1):
        raise ValueError('Eight main worlds and one excluded pilot; two repetitions only')
    semantic = random.Random(73003 + 137 * index)
    coefficients = semantic.sample(list(itertools.product(range(-3, 4), repeat=3)), 4)
    # Retry deterministic fixture construction, never model inference, until every rule is distinguishable.
    def table(c):
        return [base_value(index, b) + c[0] * (b[0] ^ b[1]) + c[1] * (b[2] ^ b[3])
                + c[2] * (b[0] ^ b[2]) for b in STATES]
    while True:
        predictions = [table(c) for c in coefficients]
        candidates = [s for s, b in enumerate(STATES) if s not in (0, 15)
                      and len({p[s] for p in predictions}) == 4 and (b[2] ^ b[3]) == 1]
        isolated = all(any(all(predictions[k][s] != predictions[j][s] for j in range(4) if j != k)
                           for s in range(16)) for k in range(4))
        if candidates and isolated:
            break
        coefficients = semantic.sample(list(itertools.product(range(-3, 4), repeat=3)), 4)
    target = semantic.choice(candidates)
    permutation = semantic.sample(range(4), 4)
    costs = [1 + ((s * (3 + 2 * (index % 3)) + 5 * index) % 11) for s in range(16)]
    rename = random.Random(SEEDS[repeat] + index * 1009)
    used = set()
    def name():
        while True:
            result = 'u' + str(rename.randrange(100000, 999999))
            if result not in used:
                used.add(result)
                return result
    source, scope, query, independent = (name() for _ in range(4))
    features = [name() for _ in range(5)]
    gates = [name(), name()]
    theories = []
    b = STATES[target]
    before = permutation[(0 ^ b[0] ^ b[1]) + 2 * (b[2] ^ b[3])]
    for slot in range(4):
        code = permutation.index(slot)
        theories.append({'id': name(), 'version': 1, 'origin': slot,
            'preconditions': [[gates[0], code % 2], [gates[1], code // 2]],
            'predictions': predictions[slot], 'derived_from': source})
    alias = dict(theories[before])
    alias.update(id=name(), derived_from=theories[before]['id'])
    theories.append(alias)
    tests = [name() for _ in range(16)]
    refs = {key: name() for key in ('source', 'observation0', 'observation1', 'independent', 'feedback')}
    w = {'index': index, 'repeat': repeat, 'seed': SEEDS[repeat], 'profile': PROFILES[index],
         'source_id': source, 'scope_id': scope, 'query_id': query, 'independent_id': independent,
         'features': features, 'gates': gates, 'coefficients': coefficients, 'permutation': permutation,
         'target': target, 'theories': theories, 'tests': tests, 'costs': costs, 'refs': refs,
         'alias_of': theories[before]['id'], 'mechanism': 'qa_microtheory_bounded_observation'}
    w['representation'] = 'finite_source:' + digest({'index': index, 'coefficients': coefficients, 'permutation': permutation})
    return w


def atoms(w: dict, time: int) -> list:
    """Visible facts only. No active-theory, best-test, regret or oracle categories."""
    facts = []
    def add(subject, relation, value):
        facts.append([subject, relation, value])
    source, refs = w['source_id'], w['refs']
    add(source, 'record_ref', refs['source'])
    add(refs['source'], 'source', source)
    for key, val in [('profile', w['profile']), ('version', 1), ('scope', w['scope_id']),
                     ('representation', w['representation']), ('mechanism', w['mechanism'])]:
        add(source, key, val)
    add(w['query_id'], 'derived_from', source)
    add(w['query_id'], 'requires_version', time + 1)
    bits = STATES[w['target']]
    for i, feature in enumerate(w['features']):
        add(feature, 'channel', ['physical', i] if i < 4 else ['environment', 0])
        add(feature, 'current_value', bits[i] if i < 4 else time)
        add(w['query_id'], 'depends_on', feature)
    for gate, deps in [(w['gates'][0], [w['features'][4], *w['features'][:2]]),
                       (w['gates'][1], w['features'][2:4])]:
        add(gate, 'depends_on', deps)
        add(gate, 'finite_relation', [[list(values), sum(values) % 2]
                                    for values in itertools.product((0, 1), repeat=len(deps))])
    for s, test in enumerate(w['tests']):
        add(test, 'physical_input', list(STATES[s]))
        add(test, 'cost', w['costs'][s])
        add(test, 'derived_from', source)
    for theory in w['theories']:
        tid = theory['id']
        add(tid, 'version', 1)
        add(tid, 'domain', source)
        add(tid, 'depends_on', theory['preconditions'])
        add(tid, 'excludes', [[gate, 1 - value] for gate, value in theory['preconditions']])
        add(tid, 'derived_from', theory['derived_from'])
        add(tid, 'requires_version', [source, 1])
        add(tid, 'supports', [refs['observation0'], refs['observation1']])
        add(tid, 'predicted_observation', list(zip(w['tests'], theory['predictions'])))
        add(tid, 'independent_of', w['independent_id'])
    for j, state in enumerate((0, 15)):
        ref = refs['observation' + str(j)]
        add(ref, 'source', source)
        add(ref, 'observed', [w['tests'][state], w['theories'][0]['predictions'][state]])
    add(w['independent_id'], 'source', refs['independent'])
    add(w['independent_id'], 'observable', 'sum of the four physical input bits')
    add(w['independent_id'], 'value', sum(bits))
    if time:
        old = next(t for t in w['theories'] if t['id'] == w['alias_of'])
        code = (1 ^ bits[0] ^ bits[1]) + 2 * (bits[2] ^ bits[3])
        new = w['theories'][w['permutation'][code]]
        add(refs['feedback'], 'kind', 'counterexample')
        add(refs['feedback'], 'changes_measurement', [w['features'][4], 0, 1])
        add(refs['feedback'], 'observed', [w['tests'][w['target']], new['predictions'][w['target']]])
        add(refs['feedback'], 'contradicts_at_context', [old['id'], w['query_id'], old['predictions'][w['target']]])
        add(refs['feedback'], 'independent_of', w['independent_id'])
    random.Random(w['seed'] + 3 * w['index'] + time).shuffle(facts)
    return facts


def render(facts: list, mode: str) -> str:
    if mode == 'F':
        return '\n'.join(json.dumps(f, separators=(',', ':')) for f in facts)
    if mode != 'S':
        raise ValueError('Only F and S are LLM treatments')
    groups = {}
    for subject, relation, value in facts:
        groups.setdefault(subject, {}).setdefault(relation, []).append(value)
    return json.dumps({'records': [{'id': s, **attrs} for s, attrs in sorted(groups.items())]}, separators=(',', ':'))


def canonical_atoms(text: str, mode: str) -> list:
    if mode == 'F':
        facts = [json.loads(line) for line in text.splitlines()]
    else:
        facts = [[record['id'], relation, value] for record in json.loads(text)['records']
                 for relation, values in record.items() if relation != 'id' for value in values]
    return sorted(json.dumps(f, sort_keys=True, separators=(',', ':')) for f in facts)
