"""Exact finite semantics with scope, concrete witnesses and charged operation budgets."""
from itertools import combinations
import time
from typing import Any

from .adapters import Adapter
from .ast import Apply, Eq, EqualityScope, Formula, Var, digest, implication
from .models import Budget


class Limit(Exception):
    pass


class Meter:
    def __init__(self, budget: Budget):
        self.budget = budget
        self.start = time.monotonic()
        self.operations = 0
        self.cache: dict[tuple[str, int], int] = {}

    def tick(self):
        if (time.monotonic() - self.start) * 1000 >= self.budget.deadline_ms:
            raise Limit('DEADLINE')

    def apply(self, a: Adapter, op: str, x: int) -> int:
        self.tick()
        key = (op, x)
        if key not in self.cache:
            if self.operations >= self.budget.max_operations:
                raise Limit('OPERATION_LIMIT')
            self.operations += 1
            self.cache[key] = a.apply(op, x)
        return self.cache[key]

    def metrics(self):
        return {'operation_applications': self.operations, 'wall_ms': (time.monotonic() - self.start) * 1000}


def validate(a: Adapter, f: Formula):
    if type(a) is not Adapter:
        raise ValueError('UNREGISTERED_ADAPTER_IMPLEMENTATION')
    if a.spec.mask is not None and f.equality == 'full_state':
        raise ValueError('PROJECTED_ADAPTER_CANNOT_CLAIM_FULL_STATE_EQUALITY')

    def visit(t):
        if isinstance(t, Apply):
            if t.operation not in a.ops:
                raise ValueError('UNKNOWN_OPERATION:' + t.operation)
            visit(t.argument)
    atoms = [f.body] if isinstance(f.body, Eq) else [f.body.premise, f.body.conclusion]
    for atom in atoms:
        visit(atom.left)
        visit(atom.right)


def scope(a: Adapter, f: Formula, sampled: bool) -> dict:
    return {'quantifier': f.binder, 'equality': f.equality, 'domain': 'sample' if sampled else 'finite_initial_states',
            'adapter': a.metadata, 'external_world_claim': False, 'dsl_version': f.dsl_version}


def witness(a: Adapter, f: Formula, x: int, m: Meter) -> dict:
    steps = []

    def term(t):
        if isinstance(t, Var):
            return x
        start = term(t.argument)
        out = m.apply(a, t.operation, start)
        steps.append({'operation': t.operation, 'input': start, 'full_output': out,
                      'observed_output': a.observe(out), 'input_sort': 'state', 'output_sort': 'state'})
        return out

    def atom(e):
        left, right = term(e.left), term(e.right)
        observed = [a.observe(left), a.observe(right)]
        compared = observed if f.equality == 'observation' else [left, right]
        return {'full_outputs': [left, right], 'observed_values': observed,
                'actual_equal': compared[0] == compared[1], 'equality_criterion': f.equality}

    p = None if isinstance(f.body, Eq) else atom(f.body.premise)
    c = atom(f.body if isinstance(f.body, Eq) else f.body.conclusion)
    valid = (p is not None and not p['actual_equal']) or c['actual_equal']
    return {'state': x, 'raw_state': x, 'bits': [(x >> i) & 1 for i in range(a.width)],
            'steps': steps, 'premise': p, 'conclusion': c, 'expected_relation': 'formula_holds',
            'actual_relation': bool(valid), 'mismatch_location': None if valid else 'conclusion',
            'snapshot_id': a.metadata['snapshot_id']}


def check(a: Adapter, f: Formula, states: list[int] | None = None, budget: Budget | None = None) -> dict:
    validate(a, f)
    b = budget or Budget()
    m = Meter(b)
    sampled = states is not None or a.spec.fidelity == 'empirical'
    xs = list(a.states()) if states is None else states
    if len(xs) != len(set(xs)) or any(not a.valid_state(x) for x in xs):
        raise ValueError('INVALID_OR_DUPLICATE_INITIAL_STATE')
    out: dict[str, Any] = {'status': 'unknown', 'reason': 'EMPTY_OBSERVATION_SET', 'scope': scope(a, f, sampled),
           'formula': f.canonical_ast(), 'tested': 0, 'support': 0, 'nontrivial_conclusion_failures': 0,
           'checked_state_ids': [], 'evaluation_trace': [], 'counterexample': None, 'sample_witness': None,
           'proof_status': 'unverified', 'execution_permission': {'allowed': False},
           'backend': 'finite_exact/1'}
    try:
        for x in xs:
            if out['tested'] >= b.max_states:
                raise Limit('STATE_LIMIT')
            m.tick()
            w = witness(a, f, x, m)
            out['tested'] += 1
            out['checked_state_ids'].append(x)
            out['evaluation_trace'].append(w)
            out['support'] += int(w['premise'] is None or w['premise']['actual_equal'])
            out['nontrivial_conclusion_failures'] += int(not w['conclusion']['actual_equal'])
            if out['sample_witness'] is None:
                out['sample_witness'] = w
            if not w['actual_relation']:
                out.update(status='refuted', reason='CONCRETE_COUNTEREXAMPLE', counterexample=w)
                break
        else:
            if xs:
                out.update(status='consistent_with_observations' if sampled else 'proved',
                           reason='SAMPLE_ONLY' if sampled else 'EXHAUSTIVE_FINITE_INITIAL_STATE_SEMANTICS')
    except Limit as exc:
        out.update(status='timeout', reason=str(exc))
    out['metrics'] = m.metrics()
    return out


def audit(a: Adapter, budget: Budget | None = None) -> dict:
    if type(a) is not Adapter:
        return {'status': 'invalid_adapter', 'reason': 'UNREGISTERED_IMPLEMENTATION'}
    b = budget or Budget()
    groups: dict[int, list[int]] = {}
    m = Meter(b)
    try:
        if len(a.states()) > b.max_states:
            raise Limit('STATE_LIMIT')
        for x in a.states():
            m.tick()
            groups.setdefault(a.observe(x), []).append(x)
        for op in a.ops:
            for xs in groups.values():
                first = xs[0]
                left = m.apply(a, op, first)
                for second in xs[1:]:
                    right = m.apply(a, op, second)
                    if a.observe(left) != a.observe(right):
                        return {'status': 'invalid_adapter', 'reason': 'OBSERVATION_NOT_CONGRUENT',
                                'congruent': False, 'full_semantics_valid': True,
                                'congruence_witness': {'operation': op, 'states': [first, second],
                                    'same_observation': a.observe(first), 'full_outputs': [left, right],
                                    'observed_continuations': [a.observe(left), a.observe(right)]},
                                'metrics': m.metrics(), 'scope': a.metadata}
        # Check every declared operation on every initial state, even for singleton observation classes.
        for x in a.states():
            for op in a.ops:
                m.apply(a, op, x)
        return {'status': 'proved', 'reason': 'FINITE_OPERATION_CONTRACT_AND_CONGRUENCE',
                'congruent': True, 'congruence_witness': None, 'scope': a.metadata, 'metrics': m.metrics()}
    except Limit as exc:
        return {'status': 'timeout', 'reason': str(exc), 'congruent': None, 'metrics': m.metrics()}
    except (ValueError, TypeError) as exc:
        return {'status': 'invalid_adapter', 'reason': str(exc), 'congruent': None, 'metrics': m.metrics()}


def candidates(a: Adapter, budget: Budget | None = None, offset: int = 0) -> dict:
    b = budget or Budget()
    pairs = list(combinations(a.ops, 2))
    total = len(pairs) * (len(pairs) - 1)
    if type(offset) is not int or not 0 <= offset <= total:
        raise ValueError('INVALID_CANDIDATE_CURSOR')
    laws, index = [], 0
    for p in pairs:
        for c in pairs:
            if p == c:
                continue
            if offset <= index < offset + b.max_candidates:
                laws.append(implication(*p, *c, equality='observation' if a.spec.mask is not None else 'full_state').canonical_ast())
            index += 1
    end = offset + len(laws)
    return {'laws': laws, 'total_in_restricted_grammar': total, 'next_cursor': end if end < total else None,
            'search_complete': offset == 0 and end == total, 'scope': a.metadata}


def library(a: Adapter, states: list[int] | None = None, budget: Budget | None = None) -> dict:
    """Group exact atom vectors and retain weakest true premises. Not a minimal axiom basis."""
    b = budget or Budget()
    m = Meter(b)
    xs = list(a.states()) if states is None else states
    if not xs or len(xs) != len(set(xs)) or any(not a.valid_state(x) for x in xs):
        raise ValueError('NONEMPTY_DISTINCT_VALID_STATES_REQUIRED')
    if len(xs) > b.max_states:
        return {'status': 'timeout', 'reason': 'STATE_LIMIT', 'laws': [], 'metrics': m.metrics()}
    equality: EqualityScope = 'observation' if a.spec.mask is not None else 'full_state'
    pairs = [(left, right) for left, right in combinations(a.ops, 2)]
    sigs: dict[tuple[str, str], tuple[bool, ...]] = {}
    groups: dict[tuple[bool, ...], dict[tuple[bool, ...], tuple[tuple[str, str], tuple[str, str]]]] = {}
    relations: list[dict[str, Any]] = []
    try:
        for pair in pairs:
            vector = tuple((a.observe(m.apply(a, pair[0], x)) == a.observe(m.apply(a, pair[1], x)))
                           if equality == 'observation' else (m.apply(a, pair[0], x) == m.apply(a, pair[1], x)) for x in xs)
            sigs[pair] = vector
        by_vector: dict[tuple[bool, ...], list[tuple[str, str]]] = {}
        for pair, vector in sigs.items():
            by_vector.setdefault(vector, []).append(pair)
        for vector, members in by_vector.items():
            relations.append({'relation': 'equal_truth_vector', 'members': members, 'truth_vector_sha256': digest(vector)})
        count = 0
        total = len(pairs) * (len(pairs) - 1)
        for p in pairs:
            for c in pairs:
                if p == c:
                    continue
                m.tick()
                if count >= b.max_candidates:
                    break
                count += 1
                sp, sc = sigs[p], sigs[c]
                if not any(sp) or all(sc) or any(x and not y for x, y in zip(sp, sc)):
                    continue
                groups.setdefault(sc, {}).setdefault(sp, (p, c))
        laws = []
        for sc, by_premise in groups.items():
            for sp, (p, c) in by_premise.items():
                weaker = next((other for other in by_premise if other != sp and all(not x or y for x, y in zip(sp, other))), None)
                if weaker is not None:
                    relations.append({'relation': 'premise_strict_subset_same_conclusion',
                                      'removed_premise': digest(sp), 'retained_weaker_premise': digest(weaker),
                                      'conclusion_vector': digest(sc)})
                else:
                    laws.append(implication(*p, *c, equality=equality).canonical_ast())
        sampled = states is not None or a.spec.fidelity == 'empirical'
        return {'status': 'consistent_with_observations' if sampled else 'proved', 'laws': laws, 'count': len(laws),
                'relations': relations, 'tested': len(xs), 'checked_state_ids': xs, 'candidates_considered': count,
                'atom_truth_vectors': [{'operations': pair, 'values': vector} for pair, vector in sigs.items()],
                'operation_evidence': [{'operation': op, 'input': x, 'full_output': value,
                                        'observed_output': a.observe(value)} for (op, x), value in sorted(m.cache.items())],
                'search_complete': count == total, 'scope': scope(a, implication(*pairs[0], *pairs[1], equality=equality), sampled),
                'warning': 'Bounded grammar; representative reduction, not a globally minimal independent basis.',
                'metrics': m.metrics()}
    except Limit as exc:
        return {'status': 'timeout', 'reason': str(exc), 'laws': [], 'metrics': m.metrics()}
