"""Reproducible exact baseline comparison and equal-cap probe-order experiments."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import time

from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import implication
from davcore.baseline import Engine, Eq, Implies
from davcore.explorer import ProbeContext, probes
from davcore.finite import check, library
from davcore.models import Budget


def semantic_classes(a, laws, old=False):
    engine = Engine(a.base)
    out = set()
    for f in laws:
        if old:
            obj = Implies(Eq(**f['premise']), Eq(**f['conclusion']))
        else:
            b = f['body']
            obj = Implies(Eq(b['premise']['left']['operation'], b['premise']['right']['operation']),
                          Eq(b['conclusion']['left']['operation'], b['conclusion']['right']['operation']))
        out.add((engine.signature(obj.premise, a.states()), engine.signature(obj.conclusion, a.states())))
    return out


def run():
    rows = []
    for kind in ['ca', 'graph']:
        a = Adapter(AdapterSpec(kind=kind))
        old_engine = Engine(a.base)
        applications = 0
        original = a.base.apply

        def counted(op, x):
            nonlocal applications
            applications += 1
            return original(op, x)
        a.base.apply = counted
        start, cpu = time.perf_counter(), time.process_time()
        old = old_engine.library(complete=True)
        old_metrics = {'wall_seconds': time.perf_counter() - start, 'cpu_seconds': time.process_time() - cpu,
                       'operation_applications': applications}
        a.base.apply = original
        start, cpu = time.perf_counter(), time.process_time()
        new = library(a)
        new_metrics = {'wall_seconds': time.perf_counter() - start, 'cpu_seconds': time.process_time() - cpu,
                       **new['metrics']}
        equivalent = semantic_classes(a, old['laws'], True) == semantic_classes(a, new['laws'])
        assert equivalent and new['search_complete']
        rows.append({'domain': kind, 'baseline_count': old['count'], 'integrated_count': new['count'],
                     'independent_semantic_classes': len(semantic_classes(a, new['laws'])),
                     'candidate_count': new['candidates_considered'], 'semantic_classes_equal': equivalent,
                     'baseline_metrics': old_metrics, 'integrated_metrics': new_metrics})
    a = Adapter(AdapterSpec(kind='ca'))
    f = implication('T0', 'T1', 'T0', 'T2')
    arms = []
    for seed in range(24):
        context = ProbeContext(a.metadata['snapshot_id'], a.states(), 64, seed)
        for policy, xs in [('symbolic_finite_order', list(a.states())[:64]),
                           ('random_baseline', probes(context)['states'])]:
            out = check(a, f, states=xs, budget=Budget(max_states=64, max_operations=256))
            arms.append({'seed': seed, 'policy': policy, 'common_caps': asdict(context) | {'admissible_states': '256 finite states', 'max_operations': 256},
                         'status': out['status'], 'counterexample_count': int(out['counterexample'] is not None),
                         'tested': out['tested'], 'metrics': out['metrics']})
    summary = {policy: {'trials': len(part := [r for r in arms if r['policy'] == policy]),
                       'counterexamples_found': sum(r['counterexample_count'] for r in part),
                       'mean_operations': statistics.mean(r['metrics']['operation_applications'] for r in part),
                       'mean_wall_ms': statistics.mean(r['metrics']['wall_ms'] for r in part)}
               for policy in ['symbolic_finite_order', 'random_baseline']}
    return {'status': 'PASS_EXACT_BASELINE_EQUIVALENCE', 'domains': rows, 'equal_budget_probe_trials': arms,
            'probe_summary': summary, 'neural_W': {'status': 'NOT_RUN_NO_TRAINED_POLICY_SHIPPED', 'incremental_value': None,
                                                  'enabled': False, 'reason': 'Handoff includes no trained compatible W; no neural result invented.'},
            'warning': 'Two builtin finite domains and one held-out width in tests; no universal world-discovery or historical interpretation claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'status': result['status'], 'domains': [(x['domain'], x['integrated_count']) for x in result['domains']]}))
