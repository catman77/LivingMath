#!/usr/bin/env python3
"""Independent stdlib-only finite regression oracle for PATCH002.

This script is a small independent FOL evaluator; finite checks are NOT a
complete theorem prover and do not validate Russian author intent.
"""
from itertools import product
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
fixture=json.loads((HERE/'PATCH002_CASES.json').read_text(encoding='utf-8'))

def ev(formula, model, env=None):
    env = env or {}
    if 'pred' in formula:
        return tuple(env[a['var']] for a in formula['args']) in {tuple(x) for x in model['relations'][formula['pred']]}
    if 'eq' in formula:
        return env[formula['eq'][0]['var']]==env[formula['eq'][1]['var']]
    if 'not' in formula:return not ev(formula['not'],model,env)
    if 'and' in formula:return all(ev(q,model,env) for q in formula['and'])
    if 'or' in formula:return any(ev(q,model,env) for q in formula['or'])
    if formula['quant']=='forall':
        return all(ev(formula['body'],model,{**env,formula['var']:x}) for x in model['domains'][formula['sort']])
    return any(ev(formula['body'],model,{**env,formula['var']:x}) for x in model['domains'][formula['sort']])

def models(signature, size):
    domains={s:[f'{s}:{j}' for j in range(size)] for s in signature['sorts']}
    cells=[(name,combo) for name,arg_sorts in sorted(signature['predicates'].items()) for combo in product(*[domains[t] for t in arg_sorts])]
    for bits in product([0,1],repeat=len(cells)):
        rel={p:[] for p in signature['predicates']}
        for (p,values),b in zip(cells,bits):
            if b:rel[p].append(list(values))
        yield {'domains':domains,'relations':rel,'world':'closed'}

def inspect_case(case):
    c=case['formulas'];sig=case['signature'];names=list(c);states={key:[] for key in names}
    witnesses={}
    n=0
    for size in [1,2]:
        for world in models(sig,size):
            n+=1
            vals={k:ev(phi,world) for k,phi in c.items()}
            for k,v in vals.items():states[k].append(v)
            for direction in case['directions']:
                a,b=direction['left'],direction['right']
                if vals[a] and not vals[b] and f'{a}!=>{b}' not in witnesses:
                    witnesses[f'{a}!=>{b}']=world
    for direction in case['directions']:
        a,b=direction['left'],direction['right'];exists=any(x and not y for x,y in zip(states[a],states[b]))
        want=direction['finite_counterexample_exists']
        assert exists==want,(case['id'],a,b,exists,want)
    return {'case':case['id'],'worlds_checked':n,'counterexamples':list(witnesses),'PASS':True}

def main():
    out=[inspect_case(c) for c in fixture['logical_cases']]
    print(json.dumps({'status':'PASS','scope':'FINITE_MODELS_1_2_ONLY_NOT_SOURCE_SEMANTICS','checks':out},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
