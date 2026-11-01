"""Optional direct bit-vector semantics. No truth-table encoding or unsat shortcuts."""
from .adapters import Adapter
from .ast import Eq, Var
from .finite import validate, scope, witness, Meter
from .models import Budget


def translate_operation(z3, a, op, x):
    n = a.width
    if a.spec.kind == 'graph':
        mapping = a.base.maps[op]
        return sum((z3.ZeroExt(n - 1, z3.Extract(i, i, x)) << j) for i, j in enumerate(mapping))
    if a.spec.kind == 'gate6':
        p = x & 1
        q = z3.LShR(x, 1) & 1
        return {'P': p, 'Q': q, 'Joint': p & q, 'One': z3.BitVecVal(1, n), 'Zero': z3.BitVecVal(0, n)}[op]
    k = int(op[1:])
    if op.startswith('R'):
        return z3.RotateRight(x, k % n)
    # The eight-bit rule is READ FROM THE CURRENT STATE; it is not a fixed CA rule.
    rule = sum((z3.ZeroExt(7, z3.Extract((k + j) % n, (k + j) % n, x)) << j) for j in range(8))
    bits = []
    for j in range(n):
        triple = (z3.Concat(z3.Extract((j - 1) % n, (j - 1) % n, x),
                            z3.Extract(j, j, x), z3.Extract((j + 1) % n, (j + 1) % n, x)))
        bit = z3.Extract(0, 0, z3.LShR(rule, z3.ZeroExt(5, triple)))
        bits.append(z3.ZeroExt(n - 1, bit) << j)
    return sum(bits)


def check_smt(a: Adapter, f, budget: Budget | None = None) -> dict:
    validate(a, f)
    b = budget or Budget()
    out = {'status': 'unknown', 'reason': 'OPTIONAL_Z3_UNAVAILABLE', 'formula': f.canonical_ast(),
           'scope': scope(a, f, a.spec.fidelity == 'empirical'), 'backend': 'direct_bitvector_z3/1',
           'counterexample': None, 'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
    if a.spec.kind == 'reaction_network':
        out['reason'] = 'REACTION_SMT_NOT_IMPLEMENTED_USE_EXACT_FINITE'
        return out
    if a.spec.fidelity == 'empirical':
        out['reason'] = 'EMPIRICAL_ADAPTER_HAS_NO_FULL_WORLD_SMT_PROOF'
        return out
    try:
        import z3
    except ImportError:
        return out
    meter = Meter(b)
    x = z3.BitVec('bound_state_x', a.width)
    applications = 0

    def term(t):
        nonlocal applications
        if isinstance(t, Var):
            return x
        applications += 1
        if applications > b.max_operations:
            raise ValueError('OPERATION_LIMIT')
        return translate_operation(z3, a, t.operation, term(t.argument))

    def atom(e):
        left, right = term(e.left), term(e.right)
        if f.equality == 'observation' and a.spec.mask is not None:
            left, right = left & a.spec.mask, right & a.spec.mask
        return left == right
    try:
        proposition = atom(f.body) if isinstance(f.body, Eq) else z3.Implies(atom(f.body.premise), atom(f.body.conclusion))
    except ValueError as exc:
        out.update(status='timeout', reason=str(exc))
        return out
    solver = z3.Solver()
    solver.set(timeout=b.deadline_ms, rlimit=min(5000000, b.max_operations * 100))
    if a.spec.assumption != 'none':
        solver.add(z3.Implies(x & 1 == 1, x & 2 == 2))
    solver.add(z3.Not(proposition))
    verdict = solver.check()
    out['solver_version'] = z3.get_version_string()
    out['solver_result'] = str(verdict)
    if verdict == z3.unsat:
        out.update(status='proved', reason='UNSAT_NEGATED_FORMULA_IN_DIRECT_ENCODED_FINITE_MODEL')
    elif verdict == z3.sat:
        state = solver.model().eval(x, model_completion=True).as_long()
        if not a.valid_state(state):
            out.update(status='invalid_adapter', reason='SMT_STATE_OUTSIDE_INITIAL_DOMAIN')
        else:
            w = witness(a, f, state, meter)
            if w['actual_relation']:
                out.update(status='invalid_adapter', reason='SMT_COUNTEREXAMPLE_DISAGREES_WITH_FINITE_ORACLE')
            else:
                out.update(status='refuted', reason='SAT_MODEL_INDEPENDENTLY_REPLAYED', counterexample=w)
    else:
        why = solver.reason_unknown()
        out.update(status='timeout' if 'timeout' in why.lower() else 'unknown', reason=why)
    out['metrics'] = {**meter.metrics(), 'smt_operation_nodes': applications}
    return out
