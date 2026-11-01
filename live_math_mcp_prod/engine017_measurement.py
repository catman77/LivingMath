"""Bounded reviewed native instrument semantics; never an independent oracle."""
from law_validation014_native import Port, native_sha
from operational013_native import Ledger


def calculate(declaration, target, suffix, observer, mode):
    if mode not in ('exact', 'withheld_sensor', 'instrument_error'):
        raise ValueError('UNKNOWN_INSTRUMENT_SEMANTICS')
    if declaration.get('algebra') not in ('affine', 'permutation', 'stack'):
        raise ValueError('UNKNOWN_SOURCE_SEMANTICS')
    if len(target) > 3 or not 1 <= len(suffix) <= 4 or any(type(a) is not int or a not in range(declaration['arity']) for a in target + suffix):
        raise ValueError('ORDERED_SOURCE_WORD_GUARD')
    if mode == 'instrument_error':
        return {'observed': {'defined': False, 'observation': None, 'admissibility': []},
            'coordinate': [], 'trace': [], 'quality': 'NO_OBSERVATION_INSTRUMENT_ERROR', 'native_costs': {}}
    ledger = Ledger(2048)
    ledger.stage = 'external017_measurement'
    port = Port(declaration, ledger)
    state = port.load(target)
    flags = []
    for action in suffix:
        allowed = port.guard_image(port.inspect(state), action)
        flags.append(allowed)
        if not allowed:
            raise ValueError('ACTUAL_SOURCE_GUARD_DENIED')
        state = port.extend(state, action)
        if not port.within_guard(port.inspect(state)):
            raise ValueError('ACTUAL_SOURCE_OUTSIDE_SCOPE')
    value, coordinate = port.observe(state, observer), port.inspect(state)
    return {'observed': {'defined': mode == 'exact', 'observation': value if mode == 'exact' else None, 'admissibility': flags},
        'coordinate': coordinate if mode == 'exact' else [], 'trace': ledger.rows,
        'quality': 'COMPUTABLE_CHECKED' if mode == 'exact' else 'DECLARED_SENSOR_WITHHELD',
        'native_costs': ledger.summary()}


def outcome_of(attempt, pc, mode):
    if mode == 'instrument_error':
        return 'ERROR'
    if mode == 'withheld_sensor':
        return 'INCONCLUSIVE'
    matches = attempt['observed'] == pc['expected_readout']
    if pc['purpose'] == 'VALIDATE_TRANSFER':
        matches = matches and attempt['coordinate'] == pc['expected_coordinate']
    return 'SUCCESS' if matches else 'FAILURE'
