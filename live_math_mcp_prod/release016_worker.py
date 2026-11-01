"""Separate permitted-anchor/native readers and Landlock-confined forecasts."""
import argparse
import json
from decimal import Decimal, localcontext
from pathlib import Path
import resource
import time

from real_xi015_source import load_native
from real_xi015_stream import records
from release016_math import (HS, T, ARCHIVE_SHA, identity, validate_inputs, ratio,
    transfer, shift, enclosure, binding, binding_sha)


def native_rows(native, source, h, n_count):
    """Original evaluate on original prefix. Anchor calls never include n3/4."""
    if n_count not in (2, 4) or h not in HS:
        raise ValueError('NATIVE_QUERY_GUARD')
    node = None
    atoms = []
    for kind, key, row in records(Path(source) / 'cases.json'):
        if kind == 'source_nodes' and key == 0:
            node = row
        if kind == 'origins' and key < n_count:
            if row['id'] != key or row['node_id'] != 0 or row['n'] != key + 1:
                raise ValueError('ORIGINAL_ORIGIN_PREFIX_MISMATCH')
            atoms.append((0, row['n'], native.I(*node['u']), native.I(*row['amplitude'])))
            if len(atoms) == n_count:
                break
    if not node or len(atoms) != n_count:
        raise ValueError('MISSING_SOURCE_PREFIX')
    _, rows = native.evaluate([(native.I(*node['u']), native.I(*node['quadrature_weight']))], atoms, h, native.I(T))
    for row in rows:
        if any(row[k] != v for k, v in identity(row['source_address']['n'], row['source_address']['branch']).items()):
            raise ValueError('NATIVE_ADDRESS_RENUMBERED')
    return [{**r, 'h': h, 't': T} for r in rows]


def formula(native, node, n, branch, h):
    I = native.I
    u, q = I(*node['u']), I(*node['quadrature_weight'])
    a = native.pi_interval() * n * n * (2 * u).exp()
    amp = q * (4 * a * a - 6 * a) * (u / 2 - a).exp()
    eh = ((1 if branch == '+' else -1) * u * I(h)).exp()
    co, sn = native.exp_i(u * I(T))
    return enclosure(native, {'re': (amp * eh * co).json(),
        'im': (amp * eh * sn * (1 if branch == '+' else -1)).json()})


def forecasts(native, data):
    from real_xi015_baseline import geometric
    from real_xi015_math import interpolation
    validate_inputs(data)
    node = data['node']
    anchors = {(r['h'], r['source_address']['n'], r['source_address']['branch']): r for r in data['anchors']}
    rows = []
    for h in HS:
        for n in (3, 4):
            for branch in ('+', '-'):
                anchor = anchors['0', 2, branch]
                n_then_h = shift(native, node, transfer(native, node, anchor['value'], n), branch, h)
                h_then_n = transfer(native, node, shift(native, node, anchor['value'], branch, h), n)
                # B3: integer powers in n, principal-root guard only for h=.0005.
                # It never uses target anchors or target-source amplitude tables.
                with localcontext() as ctx:
                    ctx.prec = 90
                    values, linear = [], []
                    for an in (1, 2):
                        a, b = anchors['0', an, branch], anchors['0.001', an, branch]
                        if h in HS[:2]:
                            r = anchors[h, an, branch]
                            values.append(complex_decimal(r['value']))
                        else:
                            p = geometric(a, b, h)
                            values.append((Decimal(p['re']), Decimal(p['im'])))
                        p = interpolation(a, b, h, True)
                        linear.append((Decimal(p['re']), Decimal(p['im'])))
                    x, y = values
                    denominator = x[0] ** 2 + x[1] ** 2
                    if not denominator:
                        raise ValueError('B3_ZERO_ANCHOR')
                    r = ((y[0] * x[0] + y[1] * x[1]) / denominator,
                         (y[1] * x[0] - y[0] * x[1]) / denominator)
                    z = x
                    for _ in range(n - 1):
                        z = (z[0] * r[0] - z[1] * r[1], z[0] * r[1] + z[1] * r[0])
                    pol = tuple(linear[0][i] + (n - 1) * (linear[1][i] - linear[0][i]) for i in (0, 1))
                    point = lambda v: {c: [str(v[i]), str(v[i])] for i, c in enumerate(('re', 'im'))}
                    b3, b4 = point(z), point(pol)
                row = identity(n, branch)
                bound = binding(row, h, data['pre_registration_sha256'])
                rows.append({**row, 'binding': bound, 'binding_sha256': binding_sha(bound),
                    'C': enclosure(native, n_then_h), 'B2_source_formula': formula(native, node, n, branch, h),
                    'B3_geometric': b3, 'B4_linear_n_Hermite_h': b4,
                    'cocycle': {'n_then_h': n_then_h, 'h_then_n': h_then_n,
                                'classification': 'SOURCE_IDENTITY_REPLAY'}, 'proof_status': 'unverified'})
    return rows


def complex_decimal(value):
    return tuple((Decimal(value[c][0]) + Decimal(value[c][1])) / 2 for c in ('re', 'im'))


def legacy_infer(data):
    from real_xi015_legacy import XiTrainingFrame, Ledger
    from live_transfer006 import interpret, attend
    from live_constructive007 import interpret_constructive
    from operational013 import LinearTransport
    f = data['legacy_frame']
    frame = XiTrainingFrame(f['spec'], f['query'], {int(k): v for k, v in f['events'].items()},
        f['words'], data=f['data'], ledger=Ledger())
    refs = f['spec']['histories']
    a = data['anchors'][0]
    try:
        LinearTransport.fit([a['value']['re'], a['value']['im']], [], {'observer': 'complex theta intervals'})
        result = {'status': 'UNEXPECTED_ACCEPT'}
    except ValueError as error:
        result = {'status': 'UNKNOWN_UNSUPPORTED_COMPLEX_INTERVALS', 'reason': str(error)}
    return {'I006': interpret(frame, *refs), 'T006': attend(frame),
        'I007': interpret_constructive(frame, *refs), '013': result,
        'classification': 'UNKNOWN is not a mathematical FAIL'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['anchors', 'predict', 'target'])
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deny', type=Path, action='append', default=[])
    args = p.parse_args()
    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
    native = load_native(args.native)
    data = json.loads(args.input.read_text())
    isolation = None
    if args.mode == 'predict':
        from law_validation014_isolation import restrict_reads
        # Load immutable baseline modules before the file-read allowlist closes.
        from real_xi015_legacy import XiTrainingFrame
        from live_constructive007 import interpret_constructive
        from operational013 import LinearTransport
        from real_xi015_baseline import geometric
        from real_xi015_math import interpolation
        resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
        isolation = restrict_reads(args.input.parent, args.deny)
        def forbidden(*args, **kwargs):
            raise ValueError('NATIVE_EVALUATOR_FORBIDDEN_IN_LEARNER')
        native.evaluate = forbidden
        value = {'predictions': forecasts(native, data), 'B5': legacy_infer(data), 'native_evaluate_calls': 0}
    else:
        if data['t'] != T:
            raise ValueError('TARGET_PARAMETER_DRIFT')
        count = 2 if args.mode == 'anchors' else 4
        value = {'rows': native_rows(native, args.native, data['h'], count), 'native_evaluate_calls': 1,
                 'n_in_native_input': list(range(1, count + 1))}
    value['costs'] = {'CPU_ns': time.process_time_ns() - cpu, 'wall_ns': time.perf_counter_ns() - wall,
                      'peak_RSS_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    value['isolation'] = isolation
    args.output.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
