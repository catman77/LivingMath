"""Same fixed fork isolation and quotas, supplied CAD; no heuristic lane."""
import sys
from pathlib import Path
if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lm_suti_assurance.core import canonical, strict_json, digest
from lm_suti_assurance.symbolic import worker as supervisor
from lm_suti_assurance.symbolic.state import require
from lm_suti_assurance.completeness import planner, verify
from lm_suti_assurance.completeness.contracts import kernel_binding


def evaluate(request: dict, adapter, binding: dict) -> dict:
    if request['operation'] == 'plan':
        plan = planner.compile_plan(request['source_request'], binding, adapter)
        check = verify.verify_plan(request['source_request'], plan, binding['sha256'])
        return {'plan': plan, 'independent_check': check}
    require(request['operation'] == 'execute', 'INVALID_OPERATION')
    plan = request['plan']
    check = verify.verify_plan(request['source_request'], plan, binding['sha256'])
    start, budget = request['index'], request['budget']
    require(type(start) is int and 0 <= start <= plan['total_count'] and type(budget) is int and 0 <= budget <= 128, 'INVALID_WORK_BUDGET')
    import cad
    from divzero_core import zero_over_zero_witness
    from udav import WhiteStarOrbit
    old, records = cad.CHARTS, []
    cad.CHARTS = tuple(tuple(c['matrix']) for c in plan['atlas']['charts'])
    try:
        for row in plan['obligations'][start:start+budget]:
            witness = zero_over_zero_witness(*row['witness'])
            require(witness.verify(), 'ZERO_FIBRE_MISMATCH')
            orbit = WhiteStarOrbit(plan['seed'])
            orbit.t = row['orbit_index']
            require(list(orbit.next().direction) == row['witness'], 'ORBIT_MEMBERSHIP_MISMATCH')
            p = cad.project(witness, row['view'])
            require([p.a, p.b] == row['coordinates'], 'CAD_PROJECTION_MISMATCH')
            require(verify.reading(row['aliases'][row['alias_index']]['concepts'], p.a, p.b) == row['target'], 'TARGET_MISMATCH')
            r = {**row, 'plan_sha256': plan['plan_sha256'], 'kernel_binding': binding['sha256'],
                 'work_unit_key': digest([plan['plan_sha256'], row['task_id']]),
                 'integer_projection_checked': True, 'zero_fibre_checked': True,
                 'primitive': 'SUPPLIED_cad.project', 'auxiliary_signature': list(p.signature),
                 'auxiliary_phase': p.quantile, 'auxiliary_quotients': list(p.quotients),
                 'auxiliary_gcd': p.gcd, 'clock_scope': 'CERTIFICATE_SERVICE_ORDER_NOT_HEURISTIC_TIME',
                 'source_truth': 'NOT_VERIFIED', 'execution_permission': False}
            r['receipt_sha256'] = digest(r)
            records.append(r)
    finally:
        cad.CHARTS = old
    return {'records': records, 'independent_check': check}


def main() -> int:
    try:
        from lm_suti_assurance.white_star.runtime import load
        from lm_suti_assurance.white_star.isolation import restrict
        adapter, _, identity = load()
        from udav import ReversibleUDAV
        binding = kernel_binding()
        supervisor.run = lambda packet, clock: evaluate(packet, adapter, binding)
        isolation = restrict()
        print(canonical({'ready': True, 'engine': 'certified-cj-coverage/1', 'kernel_binding': binding['sha256'], 'numeric': identity, 'isolation': isolation}), flush=True)
    except Exception as e:
        print(canonical({'ready': False, 'message': str(e)[:512]}), flush=True)
        return 2
    for raw in sys.stdin.buffer:
        packet = strict_json(raw.decode())
        reply = supervisor.bounded({'action': 'explore', 'request': packet}, ReversibleUDAV)
        print(canonical(reply), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
