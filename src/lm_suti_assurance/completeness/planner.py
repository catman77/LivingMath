"""Construct witnesses using the existing atlas, never a selector score."""
import json
from itertools import combinations
from math import gcd
from ..core import canonical, digest
from ..symbolic.state import require
from .contracts import OBSERVER, ORIGIN, SCOPE


def qualitative(pair: list | tuple, coordinates: list | tuple) -> dict:
    x, y = coordinates
    require((x, y) != (0, 0), 'ZERO_DIRECTION')
    if pair[0] > pair[1]:
        pair, x, y = pair[::-1], y, x
    return {'pair': list(pair), 'relation': 'ALIGN' if x*y > 0 else 'TENSION' if x*y < 0 else 'UNRESOLVED',
            'dominance': 'FIRST' if abs(x) > abs(y) else 'SECOND' if abs(x) < abs(y) else 'EQUAL'}


def address(seed: int, witness: list | tuple) -> int:
    a, b = witness
    s = a+b
    stride = 2*(seed % 19)+1
    while gcd(stride, s+1) != 1:
        stride += 2
    return s*(s+1)//2 + ((a-seed)*pow(stride, -1, s+1) % (s+1) if s else 0)


def construct(matrix: tuple, target: tuple) -> tuple:
    a, b, c, d = matrix
    u, v = target
    z = (d*u-b*v, -c*u+a*v)
    if z[1] < 0 or z[1] == 0 and z[0] < 0:
        z = (-z[0], -z[1])
    if z[0] >= 0:
        w, turn, m = z, 'I', matrix
    else:
        w, turn, m = (z[1], -z[0]), 'J', (b, -a, d, -c)
    g = gcd(*w)
    return tuple(m), [w[0]//g, w[1]//g], turn


def compile_plan(request: dict, binding: dict, adapter) -> dict:
    from rotated_atlas import expand
    adapter.validate(request['encoding'])
    require(request.get('atlas_profile', 'cj_v1') == 'cj_v1', 'COVERAGE_REQUIRES_CJ_V1')
    atlas = json.loads(canonical(expand(request['encoding'])))
    require(0 < len(atlas['charts']) <= 4096, 'ATLAS_LIMIT_EXCEEDED')
    data = request['encoding']
    seed = data['protocol']['seed']
    refs = {'source_ref': digest(data['source']), 'source_sha256': data['source']['sha256'],
            'encoding_ref': digest(data), 'atlas_ref': digest(atlas), 'observer_version': OBSERVER}
    scope_id = digest({'request_sha256': digest(request), 'scope': SCOPE, 'kernel_binding': binding['sha256'], **refs})
    lookup = {tuple(c['matrix']): c for c in atlas['charts']}
    vectors = {c['id']: tuple(c['coordinates']) for c in data['concepts']}
    # These representatives exhaust this observer's two nonzero signs with
    # three dominance cases and its two zero-coordinate cases.
    rays = [(2, 1), (1, 2), (1, 1), (2, -1), (1, -2), (1, -1), (1, 0), (0, 1)]
    rows = []
    for pair in combinations(sorted(vectors), 2):
        m = (*vectors[pair[0]], *vectors[pair[1]])
        if m[0]*m[3] == m[1]*m[2]:
            continue
        for ray in rays:
            mat, w, turn = construct(m, ray)
            chart = lookup[mat]
            alias = next(i for i, a in enumerate(chart['aliases']) if a['concepts'] == list(pair) and a['orientation'] == turn)
            xy = [mat[0]*w[0]+mat[1]*w[1], mat[2]*w[0]+mat[3]*w[1]]
            target = qualitative(pair, xy)
            require(target == qualitative(pair, ray), 'CONSTRUCTOR_TARGET_MISMATCH')
            rows.append({**refs, 'pair': list(pair), 'view': chart['view'], 'alias_index': alias,
                         'target': target, 'witness': w, 'coordinates': xy, 'orbit_index': address(seed, w),
                         'matrix': list(mat), 'aliases': chart['aliases'], 'witness_origin': ORIGIN,
                         'prefix_was_executed': False})
    rows.sort(key=lambda r: canonical(r['target']))
    for i, row in enumerate(rows):
        row['obligation'] = i
        row['task_id'] = digest([scope_id, row])
    h = max(abs(v) for c in vectors.values() for v in c)
    plan = {'schema': 'white-star-certified-coverage/1', 'scope': SCOPE, 'scope_id': scope_id,
            **refs, 'request_sha256': digest(request), 'kernel_binding': binding['sha256'], 'seed': seed,
            'atlas': atlas, 'obligations': rows, 'total_count': len(rows), 'coefficient_bound_H': h,
            'witness_l1_bound': 6*h, 'coordinate_abs_bound': 6*h*h,
            'compiler': 'ADJUGATE_CJ_EXISTING_ATLAS', 'execution_permission': False,
            'source_truth': 'NOT_VERIFIED', 'orbit_prefix_actually_executed': False}
    plan['plan_sha256'] = digest(plan)
    return plan
