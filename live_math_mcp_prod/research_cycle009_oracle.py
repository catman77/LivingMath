"""Independent raw finite truth and rational T evaluator, never imported by I/T."""
from fractions import Fraction

from live_constructive007_oracle import run


def signatures(world: dict) -> dict:
    return {name: {test['id']: run(word, test['suffix'], world['parameters'], world['observer'])
                   for test in world['tests']} for name, word in world['histories'].items()}


def rank(world: dict, active: list[str]) -> dict:
    table = signatures(world)
    ranked = []
    for test in world['tests']:
        groups = []
        for name in active:
            value = table[name][test['id']]
            if not value['defined'] or not all(value['admissibility']):
                break
            group = next((g for g in groups if g['value'] == value), None)
            if group is None:
                groups.append({'value': value, 'count': 1})
            else:
                group['count'] += 1
        else:
            if len(groups) > 1:
                remaining = sum(Fraction(g['count']**2, len(active)) for g in groups)
                loss = Fraction(test['cost']) + Fraction(7, 3) * remaining
                ranked.append({'test_id': test['id'], 'cost': test['cost'], 'ordinal': test['ordinal'],
                               'expected_remaining': str(remaining), 'loss': str(loss)})
    ranked.sort(key=lambda row: (Fraction(row['loss']), row['cost'], row['ordinal']))
    return {'status': 'ATTENTION_PROPOSED' if ranked else 'NO_INFORMATIVE_TEST',
            'test_id': ranked[0]['test_id'] if ranked else None, 'ranking': ranked,
            'ties': [r['test_id'] for r in ranked if r['loss'] == ranked[0]['loss']] if ranked else []}


def sequence(world: dict, environment: dict) -> dict:
    active = list(world['histories']); table = signatures(world); steps = []
    for index in (1, 2):
        decision = rank(world, active)
        test = next(t for t in world['tests'] if t['id'] == decision['test_id'])
        readout = run(environment['target_word'], test['suffix'], world['parameters'], world['observer'])
        groups = {name: sum(table[name][test['id']] == table[other][test['id']] for other in active) for name in active}
        hypothesis = min(active, key=lambda name: (groups[name], name))
        expected = table[hypothesis][test['id']]
        survivors = [name for name in active if table[name][test['id']] == readout]
        steps.append({'cycle_index': index, 'active_before': active, 'attention': decision,
                      'tested_hypothesis': hypothesis, 'declared_prediction': expected, 'measurement': readout,
                      'outcome': 'SUCCESS' if expected == readout else 'FAILURE', 'active_after': survivors})
        active = survivors
    assert len(steps[0]['active_after']) == 2 and len(active) == 1
    assert steps[0]['attention']['test_id'] != steps[1]['attention']['test_id']
    return {'world': world['id'], 'raw_signatures': table, 'steps': steps, 'final_attention': rank(world, active)}
