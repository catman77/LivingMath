"""Independent finite evaluator. Never imported by the generator or MCP server."""
from fractions import Fraction
from itertools import product
import json


def run(parameters: dict, history: list, suffix: list, observer: dict) -> dict:
    visible = parameters['initial'][0]
    value = parameters['initial'][1]
    actions = parameters['actions']; flags = []
    for number, label in enumerate(history + suffix):
        role = actions.index(label); family = parameters['algebra']; permitted = True
        if family == 'coloured_stack':
            permitted = len(value) < parameters['capacity'] if role < 2 else (bool(value) and value[-1] == role-2 if role < 4 else True)
        elif family == 'annihilation':
            permitted = len(value) < parameters['capacity'] if role < 2 else bool(value) if role == 4 else True
        if number >= len(history): flags.append(permitted)
        if not permitted:
            if number < len(history): raise ValueError('INVALID_ORACLE_HISTORY')
            return {'defined': False, 'observation': None, 'admissibility': flags}
        if family == 'boolean_relations':
            if role < 2:
                g = parameters['generators'][role]
                a,b,c,d = value[0][0],value[0][1],value[1][0],value[1][1]
                value = [[int(bool(g[0][0]*a + g[0][1]*c)), int(bool(g[0][0]*b + g[0][1]*d))],
                         [int(bool(g[1][0]*a + g[1][1]*c)), int(bool(g[1][0]*b + g[1][1]*d))]]
            else: visible = value[0][1] if role == 2 else value[1][0]
        elif family == 'annihilation':
            if role < 2:
                value = list(value) + [role]
                i = 0
                while i < len(value)-1:
                    if value[i] == 0 and value[i+1] == 0:
                        value = value[:i] + value[i+2:]; i = 0
                    elif value[i] == 0 and value[i+1] == 1:
                        value = value[:i] + value[i+1:]; i = 0
                    else: i += 1
            elif role == 2: visible = value[0]+1 if value else 0
            elif role == 3: visible = len(value)
            else: value = value[1:]
        elif family == 'coloured_stack':
            if role < 2: value = list(value) + [role]
            elif role < 4: value = value[:-1]
            else: visible = len(value)
        elif family == 'quadratic_residues':
            if role < 2: value = (pow(value,2)+parameters['offsets'][role]) % parameters['modulus']
            else: visible = value % parameters['read_moduli'][role-2]
        else: raise ValueError('UNKNOWN_ORACLE_SOURCE')
    return {'defined': True, 'observation': visible if observer['mod'] is None else visible % observer['mod'], 'admissibility': flags}


def signatures(world: dict) -> dict:
    return {name: {t['id']: run(world['parameters'], word, t['suffix'], world['observer']) for t in world['tests']}
            for name, word in world['histories'].items()}


def attention(world: dict, active: list[str]) -> dict:
    table = signatures(world); ranked = []
    for test in world['tests']:
        values = [table[name][test['id']] for name in active]
        if any(not r['defined'] or not all(r['admissibility']) for r in values): continue
        groups = {}
        for value in values:
            key=json.dumps(value, sort_keys=True); groups[key]=groups.get(key,0)+1
        if len(groups)<2: continue
        remaining=Fraction(sum(n*n for n in groups.values()),len(active));loss=Fraction(test['cost'])+Fraction(7,3)*remaining
        ranked.append({'test_id':test['id'],'cost':test['cost'],'ordinal':test['ordinal'],'expected_remaining':str(remaining),'loss':str(loss)})
    ranked.sort(key=lambda r:(Fraction(r['loss']),r['cost'],r['ordinal']))
    return {'status':'ATTENTION_PROPOSED' if ranked else 'NO_INFORMATIVE_TEST','test_id':ranked[0]['test_id'] if ranked else None,'ranking':ranked}


def freeze_oracle(world: dict) -> dict:
    # This includes all registered and held-out source histories; it is QA-only after freeze.
    heldout = [list(w) for w in product(world['parameters']['actions'][:2],repeat=3)]
    heldout_values = {}
    for i, word in enumerate(heldout):
        try: heldout_values[str(i)]={t['id']:run(world['parameters'],word,t['suffix'],world['observer']) for t in world['tests']}
        except ValueError: heldout_values[str(i)]={'inadmissible_history':True}
    return {'source':world['name'],'signatures':signatures(world),'T':attention(world,list(world['histories'])),
            'heldout_words':heldout,'heldout':heldout_values,'interpretation':'Finite source truth only, not physical truth.'}
