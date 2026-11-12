"""Independent exact-cell checker: does not import the constructor/planner."""
import hashlib
from fractions import Fraction
from math import gcd, isqrt
from ..core import canonical, digest
from ..symbolic.state import require
from .contracts import OBSERVER, ORIGIN, SCOPE


def reading(pair: list | tuple, x: int, y: int) -> dict:
    require(x != 0 or y != 0, 'ZERO_DIRECTION')
    if pair[1] < pair[0]:
        pair, x, y = pair[::-1], y, x
    relation = 'UNRESOLVED' if x*y == 0 else 'ALIGN' if x*y > 0 else 'TENSION'
    dominance = 'EQUAL' if abs(x) == abs(y) else 'FIRST' if abs(x) > abs(y) else 'SECOND'
    return {'pair': list(pair), 'relation': relation, 'dominance': dominance}


def source_atlas(request: dict) -> dict:
    """Rebuild chart/alias ordering without importing the installed compiler."""
    data = request['encoding']
    raw = data['source']['text'].encode()
    require(hashlib.sha256(raw).hexdigest() == data['source']['sha256'], 'SOURCE_MISMATCH')
    require(request.get('atlas_profile', 'cj_v1') == 'cj_v1', 'COVERAGE_REQUIRES_CJ_V1')
    ids, vectors = set(), set()
    for c in data['concepts']:
        v = c['coordinates']
        require(c['id'] not in ids and bool(c['id']), 'BAD_CONCEPT_ID')
        ids.add(c['id'])
        require(len(v) == 2 and all(type(x) is int and abs(x) <= 1000000 for x in v) and any(v) and tuple(v) not in vectors, 'BAD_COORDINATES')
        vectors.add(tuple(v))
        require(bool(c['evidence']), 'MISSING_EVIDENCE')
        for e in c['evidence']:
            l, r = e['byte_start'], e['byte_end']
            require(type(l) is int and type(r) is int and 0 <= l < r <= len(raw), 'EVIDENCE_MISMATCH')
            require(raw[l:r] == e['quote'].encode() and raw[:l].count(b'\n')+1 == e['line'], 'EVIDENCE_MISMATCH')
    concepts = sorted(data['concepts'], key=lambda c: (min(e['byte_start'] for e in c['evidence']), tuple(c['coordinates'])))
    original, omitted = [], []
    for c in concepts:
        for d in concepts:
            if c is d:
                continue
            m = c['coordinates']+d['coordinates']
            if m[0]*m[3] == m[1]*m[2]:
                omitted.append([c['id'], d['id']])
            else:
                original.append((len(original), [c['id'], d['id']], m))
    charts, lookup = [], {}
    for turn in ('I', 'J'):
        for old, pair, m in original:
            a, b, c, d = m
            key = tuple(m) if turn == 'I' else (b, -a, d, -c)
            if key not in lookup:
                lookup[key] = len(charts)
                charts.append({'view': len(charts), 'matrix': list(key), 'aliases': []})
            charts[lookup[key]]['aliases'].append({'concepts': pair, 'orientation': turn, 'original_view': old, 'original_matrix': m})
    return {'charts': charts, 'semantic_maps': sum(len(c['aliases']) for c in charts), 'old_maps': len(original), 'omitted_collinear_pairs': omitted}


def target_domain(charts: list) -> tuple[set, int]:
    targets, cells = set(), 0
    for chart in charts:
        a, b, c, d = chart['matrix']
        require(a*d != b*c, 'SINGULAR_CHART')
        ends = {Fraction(0), Fraction(1)}
        for one, zero in ((a, b), (c, d), (a-c, b-d), (a+c, b+d)):
            if one != zero:
                t = Fraction(-zero, one-zero)
                if 0 <= t <= 1:
                    ends.add(t)
        points = sorted(ends)
        probes = points+[(l+r)/2 for l, r in zip(points, points[1:])]
        cells += len(probes)
        for t in probes:
            u, v = t.numerator, t.denominator-t.numerator
            for alias in chart['aliases']:
                targets.add(canonical(reading(alias['concepts'], a*u+b*v, c*u+d*v)))
    return targets, cells


def verify_row(plan: dict, row: dict) -> None:
    charts = plan['atlas']['charts']
    j, i = row['view'], row['alias_index']
    require(type(j) is int and 0 <= j < len(charts), 'BAD_VIEW')
    chart = charts[j]
    require(type(i) is int and 0 <= i < len(chart['aliases']), 'BAD_ALIAS')
    require(row['matrix'] == chart['matrix'] and row['aliases'] == chart['aliases'], 'ALIAS_BINDING_MISMATCH')
    require(row['pair'] == sorted(chart['aliases'][i]['concepts']), 'PAIR_MISMATCH')
    w = row['witness']
    require(len(w) == 2 and all(type(x) is int and x >= 0 for x in w) and any(w), 'BAD_WITNESS')
    a, b, c, d = chart['matrix']
    x, y = a*w[0]+b*w[1], c*w[0]+d*w[1]
    require(len(row['coordinates']) == 2 and all(type(v) is int for v in row['coordinates']), 'PROJECTED_COORDINATES_MISMATCH')
    require(row['coordinates'] == [x, y], 'PROJECTED_COORDINATES_MISMATCH')
    require(row['target'] == reading(chart['aliases'][i]['concepts'], x, y), 'TARGET_MISMATCH')
    require(sum(w) <= plan['witness_l1_bound'] and max(abs(x), abs(y)) <= plan['coordinate_abs_bound'], 'WITNESS_BOUND_EXCEEDED')
    t = row['orbit_index']
    require(type(t) is int and t >= 0, 'BAD_ORBIT_INDEX')
    s = (isqrt(8*t+1)-1)//2
    pos = t-s*(s+1)//2
    stride = 2*(plan['seed'] % 19)+1
    while gcd(stride, s+1) != 1:
        stride += 2
    aa = (pos*stride+plan['seed']) % (s+1)
    require(w == [aa, s-aa], 'ORBIT_MEMBERSHIP_MISMATCH')
    require(row['witness_origin'] == ORIGIN and row['prefix_was_executed'] is False, 'FALSE_DISCOVERY_CLAIM')
    for field in ('source_ref', 'source_sha256', 'encoding_ref', 'atlas_ref', 'observer_version'):
        require(row[field] == plan[field], 'SOURCE_BINDING_MISMATCH')
    task = {k: v for k, v in row.items() if k != 'task_id'}
    require(row['task_id'] == digest([plan['scope_id'], task]), 'TASK_BINDING_MISMATCH')


def verify_plan(request: dict, plan: dict, expected_binding: str) -> dict:
    require(plan['schema'] == 'white-star-certified-coverage/1' and plan['scope'] == SCOPE and plan['observer_version'] == OBSERVER, 'SCOPE_MISMATCH')
    require(plan['kernel_binding'] == expected_binding, 'KERNEL_BINDING_MISMATCH')
    require(plan['plan_sha256'] == digest({k: v for k, v in plan.items() if k != 'plan_sha256'}), 'PLAN_HASH_MISMATCH')
    require(plan['request_sha256'] == digest(request), 'REQUEST_BINDING_MISMATCH')
    data = request['encoding']
    for field, value in [('source_ref', digest(data['source'])), ('source_sha256', data['source']['sha256']), ('encoding_ref', digest(data)), ('seed', data['protocol']['seed'])]:
        require(plan[field] == value, 'SOURCE_BINDING_MISMATCH')
    atlas = source_atlas(request)
    require(atlas == plan['atlas'] and digest(atlas) == plan['atlas_ref'], 'ATLAS_BINDING_MISMATCH')
    require(0 < len(atlas['charts']) <= 4096, 'ATLAS_LIMIT_EXCEEDED')
    refs = {k: plan[k] for k in ('source_ref', 'source_sha256', 'encoding_ref', 'atlas_ref', 'observer_version')}
    require(plan['scope_id'] == digest({'request_sha256': digest(request), 'scope': SCOPE, 'kernel_binding': expected_binding, **refs}), 'SCOPE_BINDING_MISMATCH')
    h = max(abs(x) for c in data['concepts'] for x in c['coordinates'])
    require(plan['coefficient_bound_H'] == h and plan['witness_l1_bound'] == 6*h and plan['coordinate_abs_bound'] == 6*h*h, 'BOUND_MISMATCH')
    expected, cells = target_domain(atlas['charts'])
    seen = []
    for i, row in enumerate(plan['obligations']):
        require(type(row['obligation']) is int and row['obligation'] == i, 'NONCONTIGUOUS_OBLIGATIONS')
        verify_row(plan, row)
        seen.append(canonical(row['target']))
    require(len(seen) == len(set(seen)) == plan['total_count'] and seen == sorted(seen) and set(seen) == expected, 'INCOMPLETE_OR_EXTRANEOUS_TARGET_DOMAIN')
    require(plan['execution_permission'] is False and plan['source_truth'] == 'NOT_VERIFIED' and plan['orbit_prefix_actually_executed'] is False, 'FALSE_VERIFICATION_CLAIM')
    return {'status': 'INTEGER_GEOMETRY_CHECKED', 'targets': len(expected), 'exact_partition_cells': cells, 'numeric_charts': len(atlas['charts']), 'source_semantics': 'NOT_VERIFIED'}
