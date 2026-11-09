"""Sufficient exact rules on existing typed FOL; never a FOL decision procedure."""
from itertools import product
from ...core import canonical, digest
from .alpha import canonicalize
from .checker import check_certificate


def negation_normal_form(tree, tick=None):
    """Push classical negation, preserving lexical binder addresses and sorts."""
    nodes = 0
    def visit(p, negative=False, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 256 or depth > 32:
            raise ValueError('NNF_BOUND')
        if tick:
            tick()
        op = p[0]
        if op == 'not':
            return visit(p[1], not negative, depth + 1)
        if op in ('pred', 'eq'):
            return ['not', p] if negative else p
        if op == 'quant':
            q = ('exists' if p[1] == 'forall' else 'forall') if negative else p[1]
            return ['quant', q, p[2], visit(p[3], negative, depth + 1)]
        connective = ('or' if op == 'and' else 'and') if negative else op
        return [connective, [visit(x, negative, depth + 1) for x in p[1]]]
    return visit(tree)


def prove_entailment(left, right, signature, max_atoms=10, work=None):
    """Same mixed prefix + Boolean implication, or independently checked NNF identity."""
    tick = work.tick if work else None
    base = {'model_enumerations': 0, 'models_checked': 0, 'halt_reason': None}
    a, b = canonicalize(left, signature), canonicalize(right, signature)
    a, b = negation_normal_form(a, tick), negation_normal_form(b, tick)
    common = {'input_formula_sha256_left': digest(left), 'input_formula_sha256_right': digest(right), 'signature_sha256': digest(signature)}
    if canonical(a) == canonical(b):
        cert = {'rule': 'NEGATION_NORMAL_FORM_EQUIVALENCE', 'checker_version': 'sb-nnf/1', **common,
                'normal_sha256_left': digest(a), 'normal_sha256_right': digest(b), 'result': 'PROVED_NEGATION_NORMAL_FORM_EQ'}
    else:
        def strip(p):
            prefix = []
            while p[0] == 'quant':
                prefix.append([p[1], p[2]])
                p = p[3]
            return prefix, p
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
        try:
            pa, a = strip(a)
            pb, b = strip(b)
            if pa != pb:
                raise ValueError('DIFFERENT_PREFIX_QUANTIFIERS_OR_SORTS')
            collect(a)
            collect(b)
            if len(atoms) > min(max_atoms, 10):
                raise ValueError('ATOM_BOUND')
        except ValueError as exc:
            return {**base, 'status': 'UNKNOWN_UNSUPPORTED_PROOF_CLASS', 'reason': str(exc)}
        keys = sorted(atoms)
        def evaluate(p, values):
            if p[0] in ('pred', 'eq'):
                return values[canonical(p)]
            if p[0] == 'not':
                return not evaluate(p[1], values)
            return (all if p[0] == 'and' else any)(evaluate(x, values) for x in p[1])
        rows = []
        for bits in product([False, True], repeat=len(keys)):
            if tick:
                tick()
            values = dict(zip(keys, bits))
            x, y = evaluate(a, values), evaluate(b, values)
            rows.append([list(bits), x, y])
            if x and not y:
                return {**base, 'status': 'UNKNOWN_NOT_TAUTOLOGY', 'rows_checked': len(rows), 'reason': 'Boolean counterassignment is not a FOL countermodel'}
        cert = {'rule': 'SAME_PREFIX_BOOLEAN_MONOTONICITY', 'checker_version': 'sb-prefix-boolean/2', **common,
                'prefix_quantifiers_and_sorts': pa, 'matrix_sha256_left': digest(a), 'matrix_sha256_right': digest(b),
                'atoms': [atoms[k] for k in keys], 'rows_checked': len(rows), 'truth_table_sha256': digest(rows),
                'equality_treatment': 'INDEPENDENT_BOOLEAN_ATOM_SUFFICIENT_ONLY', 'result': 'PROVED_ENTAILMENT'}
    if not check_certificate(left, right, signature, cert, tick=tick):
        raise ValueError('INDEPENDENT_CERTIFICATE_REJECTED')
    return {**base, 'status': 'PROVED_ENTAILMENT', 'proof_kind': cert['rule'], 'proof_rule': cert['rule'],
            'certificate': cert, 'certificate_sha256': digest(cert), 'independent_check': 'PASS'}
