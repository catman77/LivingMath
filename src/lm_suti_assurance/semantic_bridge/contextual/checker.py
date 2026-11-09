"""Independent reconstruction from original typed AST, never producer normal forms."""
from itertools import product
from ...core import digest, canonical
from ...formal_bridge.fol import typecheck


def normal(p, environment=None, depth=0):
    env = {} if environment is None else environment
    if 'quant' in p:
        return ['quant', p['quant'], p['sort'], normal(p['body'], {**env, p['var']: depth}, depth + 1)]
    def addresses(terms):
        return [depth - env[t['var']] - 1 for t in terms]
    if 'pred' in p:
        return ['pred', p['pred'], addresses(p['args'])]
    if 'eq' in p:
        return ['eq', addresses(p['eq'])]
    if 'not' in p:
        return ['not', normal(p['not'], env, depth)]
    key = next(k for k in ['and', 'or'] if k in p)
    return [key, [normal(x, env, depth) for x in p[key]]]


def checked_nnf(formula, tick=None):
    """Independent raw-AST traversal: address binders while pushing a polarity."""
    count = 0
    def walk(node, bindings, negative=False, nesting=0):
        nonlocal count
        count += 1
        if count > 256 or nesting > 32:
            raise ValueError('CHECKER_NNF_BOUND')
        if tick:
            tick()
        if 'not' in node:
            return walk(node['not'], bindings, not negative, nesting + 1)
        if 'quant' in node:
            q = node['quant']
            if negative:
                q = {'forall': 'exists', 'exists': 'forall'}[q]
            return ['quant', q, node['sort'], walk(node['body'], [node['var'], *bindings], negative, nesting + 1)]
        if 'pred' in node:
            atom = ['pred', node['pred'], [bindings.index(v['var']) for v in node['args']]]
        elif 'eq' in node:
            atom = ['eq', [bindings.index(v['var']) for v in node['eq']]]
        else:
            key = 'and' if 'and' in node else 'or'
            operator = {'and': 'or', 'or': 'and'}[key] if negative else key
            return [operator, [walk(v, bindings, negative, nesting + 1) for v in node[key]]]
        return ['not', atom] if negative else atom
    return walk(formula, [])


def check_certificate(left, right, signature, certificate, tick=None):
    try:
        if any(typecheck(p, signature)['status'] != 'TYPED' for p in [left, right]):
            return False
        common = {'input_formula_sha256_left': digest(left), 'input_formula_sha256_right': digest(right), 'signature_sha256': digest(signature)}
        if any(certificate[k] != v for k, v in common.items()):
            return False
        if certificate['rule'] == 'ALPHA_NORMALIZATION':
            a, b = normal(left), normal(right)
            expected = {'rule': 'ALPHA_NORMALIZATION', 'checker_version': 'sb-alpha/1', **common,
                        'canonical_sha256_left': digest(a), 'canonical_sha256_right': digest(b), 'result': 'PROVED_ALPHA_EQ'}
            return canonical(a) == canonical(b) and canonical(certificate) == canonical(expected)
        a, b = checked_nnf(left, tick), checked_nnf(right, tick)
        if certificate['rule'] == 'NEGATION_NORMAL_FORM_EQUIVALENCE':
            expected = {'rule': 'NEGATION_NORMAL_FORM_EQUIVALENCE', 'checker_version': 'sb-nnf/1', **common,
                        'normal_sha256_left': digest(a), 'normal_sha256_right': digest(b), 'result': 'PROVED_NEGATION_NORMAL_FORM_EQ'}
            return canonical(a) == canonical(b) and canonical(certificate) == canonical(expected)
        if certificate['rule'] != 'SAME_PREFIX_BOOLEAN_MONOTONICITY':
            return False
        def strip(p):
            prefix = []
            while p[0] == 'quant':
                prefix.append([p[1], p[2]])
                p = p[3]
            return prefix, p
        sa, a = strip(a)
        sb, b = strip(b)
        if sa != sb:
            return False
        atoms = {}
        def collect(p):
            if p[0] in ('pred', 'eq'):
                atoms[canonical(p)] = p
            elif p[0] == 'not':
                collect(p[1])
            elif p[0] in ('and', 'or'):
                for child in p[1]:
                    collect(child)
            else:
                raise ValueError('INTERNAL_QUANTIFIER')
        collect(a)
        collect(b)
        keys = sorted(atoms)
        if len(keys) > 10:
            return False
        def evaluate(p, values):
            if p[0] in ('pred', 'eq'):
                return values[canonical(p)]
            if p[0] == 'not':
                return not evaluate(p[1], values)
            answers = [evaluate(child, values) for child in p[1]]
            return all(answers) if p[0] == 'and' else any(answers)
        rows = []
        for bits in product([False, True], repeat=len(keys)):
            if tick:
                tick()
            values = dict(zip(keys, bits))
            x, y = evaluate(a, values), evaluate(b, values)
            if x and not y:
                return False
            rows.append([list(bits), x, y])
        expected = {'rule': 'SAME_PREFIX_BOOLEAN_MONOTONICITY', 'checker_version': 'sb-prefix-boolean/2', **common,
                    'prefix_quantifiers_and_sorts': sa, 'matrix_sha256_left': digest(a), 'matrix_sha256_right': digest(b),
                    'atoms': [atoms[k] for k in keys], 'rows_checked': len(rows), 'truth_table_sha256': digest(rows),
                    'equality_treatment': 'INDEPENDENT_BOOLEAN_ATOM_SUFFICIENT_ONLY', 'result': 'PROVED_ENTAILMENT'}
        return canonical(certificate) == canonical(expected)
    except (ValueError, KeyError, TypeError, RecursionError):
        return False
