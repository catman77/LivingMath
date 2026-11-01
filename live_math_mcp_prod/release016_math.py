"""Source-derived n/h maps, not a new law learner or fundamental operation."""
from decimal import Decimal, localcontext
from normalizer import digest

ARCHIVE_SHA = '19e3112882242fd8f686bfaf12b888bd7a8abe930e07b542fe298720044b14dd'
HS = ['0', '0.001', '0.0005', '0.002']
T = '15'


def identity(n, branch):
    if n not in range(1, 5) or branch not in ('+', '-'):
        raise ValueError('SOURCE_ADDRESS_MISMATCH')
    origin = n - 1
    return {'index': 2 * origin + (branch == '-'), 'origin_id': origin,
            'source_address': {'cell': 0, 'node': 0, 'n': n, 'branch': branch}}


def validate_inputs(data):
    if data['t'] != T or data['archive_sha256'] != ARCHIVE_SHA:
        raise ValueError('SOURCE_PARAMETER_REBIND')
    if set(data) != {'t', 'archive_sha256', 'node', 'anchors', 'pre_registration_sha256', 'legacy_frame'}:
        raise ValueError('INPUT_NOT_ALLOWLISTED')
    if set(data['node']) != {'u', 'quadrature_weight', 'cell', 'node', 'id', 'exact_u'}:
        raise ValueError('METADATA_NOT_ALLOWLISTED')
    if len(data['anchors']) != 8:
        raise ValueError('ANCHOR_COMPLETENESS')
    seen = set()
    for row in data['anchors']:
        a = row['source_address']
        if a['n'] not in (1, 2):
            raise ValueError('TARGET_ANCHOR_FORBIDDEN')
        expected = identity(a['n'], a['branch'])
        if any(row[k] != v for k, v in expected.items()) or row['h'] not in HS[:2] or row['t'] != T:
            raise ValueError('SOURCE_ADDRESS_MISMATCH')
        seen.add((row['h'], row['index']))
    if len(seen) != 8:
        raise ValueError('ANCHOR_COMPLETENESS')


def ratio(native, node, n):
    if n not in (1, 2, 3):
        raise ValueError('N_GUARD')
    I = native.I
    u = I(*node['u'])
    a = native.pi_interval() * n * n * (2 * u).exp()
    b = native.pi_interval() * (n + 1) ** 2 * (2 * u).exp()
    denominator = 4 * a * a - 6 * a
    if u.lo <= 0 or denominator.lo <= 0:
        raise ValueError('UNPROVEN_NONZERO_DENOMINATOR')
    return (4 * b * b - 6 * b) / denominator * (-(b - a)).exp()


def shift(native, node, value, branch, h):
    if h not in HS or Decimal(h) ** 2 + Decimal(T) ** 2 > 27 ** 2:
        raise ValueError('H_T_GUARD')
    if branch not in ('+', '-'):
        raise ValueError('BRANCH_GUARD')
    factor = (native.I(*node['u']) * (1 if branch == '+' else -1) * native.I(h)).exp()
    return {c: (native.I(*value[c]) * factor).json() for c in ('re', 'im')}


def transfer(native, node, value, target_n):
    if target_n not in (3, 4):
        raise ValueError('N_GUARD')
    out = value
    for n in range(2, target_n):
        factor = ratio(native, node, n)
        out = {c: (native.I(*out[c]) * factor).json() for c in ('re', 'im')}
    return out


def enclosure(native, value):
    # Frozen relative padding widens a sound source-identity interval. It is
    # never fitted to oracle widths, error or revealed values.
    scale = max(abs(Decimal(x)) for v in value.values() for x in v)
    padding = native.I(str(scale)) * native.I('1e-45')
    return {c: native.I(*value[c]).widen(padding.hi).json() for c in ('re', 'im')}


def score(predicted, actual):
    with localcontext() as context:
        context.prec = 90
        scale = max(abs(Decimal(x)) for v in predicted.values() for x in v)
        tolerance = scale * Decimal('1e-40')
        components = {}
        for c in ('re', 'im'):
            lo, hi = map(Decimal, actual[c])
            pl, ph = map(Decimal, predicted[c])
            components[c] = {'containment': pl <= lo <= hi <= ph,
                'overlap': max(pl, lo) <= min(ph, hi), 'width_ok': ph - pl <= tolerance,
                'prediction_width': str(ph - pl), 'reference_width': str(hi - lo),
                'midpoint_error': str(abs((pl + ph - lo - hi) / 2)), 'tolerance': str(tolerance)}
        return {'containment_PASS': all(c['containment'] and c['width_ok'] for c in components.values()),
                'overlap_PASS': all(c['overlap'] and c['width_ok'] for c in components.values()),
                'components': components}


def binding(row, h, pre_sha):
    return {**identity(row['source_address']['n'], row['source_address']['branch']), 'h': h,
            't': T, 'observer': 'native-complex-interval-containment/v1', 'version': 1,
            'definition_sha256': ARCHIVE_SHA, 'pre_registration_sha256': pre_sha}


def binding_sha(row):
    return digest({k: v for k, v in row.items() if k != 'display_label'})
