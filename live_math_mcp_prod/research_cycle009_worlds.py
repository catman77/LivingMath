"""Literal operator declarations; no target selector or oracle answers in sources."""
import hashlib
import json


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def declarations(namespace: str) -> list[dict]:
    definitions = [
        ('affine', {'initial': [1, 0], 'modulus': 12, 'coefficients': [0, 2, 6, 1]},
         {'H0': [], 'H1': [2], 'H2': [1]}, [20, 0, 20, 4], 'affine-injective', 2),
        ('permutation', {'initial': [0, 1, 2, 3], 'permutations': [
            [0, 1, 2, 3], [0, 2, 1, 3], [0, 1, 3, 2], [1, 0, 2, 3], [2, 1, 0, 3]]},
         {'H0': [], 'H1': [1], 'H2': [2]}, [20, 20, 20, 0, 4], 'right-projection', 4),
        ('erasure', {'initial': list('aabaacad'), 'cuts': [0, 1, 2, 3, 6, 8]},
         {'H0': [], 'H1': [3], 'H2': [4]}, [20, 0, 4, 20, 20, 20], 'prefix-projection', 8),
    ]
    worlds = []
    for family, parameters, histories, costs, law, width in definitions:
        actions = ['a' + str(i) for i in range(len(costs))]
        parameters.update(family=family, actions=actions)
        world = {'id': family, 'project': 'LM_QA_CYCLE009_' + namespace + '_' + family,
            'parameters': parameters, 'histories': {k: [actions[i] for i in word] for k, word in histories.items()},
            'tests': [{'id': 't' + str(i), 'ordinal': i, 'suffix': [action], 'cost': costs[i]}
                      for i, action in enumerate(actions)],
            'observer': {'projection': 'primary', 'mod': None}, 'law_kind': law, 'width': width,
            'current_observation': 'a' if family == 'erasure' else (1 if family == 'affine' else 0),
            'unknowns': ['The actual environment history is unknown to I/T.', 'No equivalence or truth outside registered D.'],
            'independent_branch': {'id': 'IND', 'word': [], 'scope': 'independent'},
            'instrument_policy': 'Bounded exact readout; separate INCONCLUSIVE control never changes applicability.',
            'source_provenance': 'Operator-supplied finite source operations, hypotheses, costs and reviewed law schema.'}
        world['fixture_sha256'] = checksum(world)
        world['scope'] = 'QA009/' + namespace + '/' + family + '/' + world['fixture_sha256']
        worlds.append(world)
    return worlds


def environments(worlds: list[dict], salts: list[str]) -> list[dict]:
    """Privileged, separate operator fixtures. Never attach these to project sources."""
    return [{'schema': 'cycle009-sealed-environment/v1', 'fixture_sha256': w['fixture_sha256'],
             'parameters': w['parameters'], 'target_word': w['histories']['H0'], 'salt': salt}
            for w, salt in zip(worlds, salts)]
