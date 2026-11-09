#!/usr/bin/env python3
"""Independent, dependency-free check for Semantic Bridge exp01.
No production LivingMath imports; frozen ASTs only. All cases are synthetic.
"""
import json, itertools, pathlib, hashlib
ROOT=pathlib.Path(__file__).resolve().parent
PACK=json.loads((ROOT/'frozen_input.json').read_text(encoding='utf-8'))
H=PACK['hypotheses']
SIG=PACK['signature']

def alpha_normal(phi,stack=()):
    if 'quant' in phi:
        key=(phi['quant'],phi['sort'])
        return ('quant',*key,alpha_normal(phi['body'],stack+(phi['var'],)))
    if 'pred' in phi:
        return ('pred',phi['pred'],tuple(len(stack)-1-stack[::-1].index(t['var']) for t in phi['args']))
    if 'eq' in phi:
        return ('eq',tuple(len(stack)-1-stack[::-1].index(t['var']) for t in phi['eq']))
    if 'not' in phi:return ('not',alpha_normal(phi['not'],stack))
    if 'and' in phi:return ('and',tuple(alpha_normal(p,stack) for p in phi['and']))
    if 'or' in phi:return ('or',tuple(alpha_normal(p,stack) for p in phi['or']))
    return ('UNSUPPORTED',tuple(sorted(phi)))

def evaluate(ast,model,env=None):
    env={} if env is None else env
    if 'pred' in ast:
        return [env[v['var']] for v in ast['args']] in model['relations'][ast['pred']]
    if 'eq' in ast:
        return env[ast['eq'][0]['var']]==env[ast['eq'][1]['var']]
    if 'not' in ast:return not evaluate(ast['not'],model,env)
    if 'and' in ast:return all(evaluate(x,model,env) for x in ast['and'])
    if 'or' in ast:return any(evaluate(x,model,env) for x in ast['or'])
    if 'quant' in ast:
        f=[evaluate(ast['body'],model,{**env,ast['var']:v}) for v in model['domains'][ast['sort']]]
        return all(f) if ast['quant']=='forall' else any(f)
    raise ValueError('unsupported formula node')

def mk(sup,checked,planned,reported,open=False):
    return {'domains':{'researcher':['r0'],'manager':['m0'],'hypothesis':['h0']},'relations':{
        'Supervises':[['m0','r0']] if sup else [],
        'Checked':[['r0','h0']] if checked else [],
        'Planned':[['r0','h0']] if planned else [],
        'Reported':[['r0','m0','h0']] if reported else []}, 'world':'open' if open else 'closed'}
models={
    'M1_planned_checked_reported':mk(1,1,1,1),
    'M2_unverified_reported':mk(1,0,0,1),
    'M3_checked_unreported':mk(1,1,0,0),
    'M4_supervisor_absent':mk(0,0,0,0),
    'M5_open_world':mk(1,1,1,1,True),
}
for m in models.values():
    assert set(m['relations'])==set(SIG['predicates'])
    assert set(m['domains'])==set(SIG['sorts'])
truths={name:{h:None if model['world']=='open' else evaluate(H[h],model) for h in ('H0','H1','H2','H3')} for name,model in models.items()}
assert list(truths['M1_planned_checked_reported'].values())==[True,False,True,True]
assert list(truths['M2_unverified_reported'].values())==[True,True,True,False]
assert list(truths['M3_checked_unreported'].values())==[False,False,False,True]
assert list(truths['M4_supervisor_absent'].values())==[True,True,True,True]
assert all(x is None for x in truths['M5_open_world'].values())
assert alpha_normal(H['H0'])==alpha_normal(H['H2'])
assert alpha_normal(H['H0'])!=alpha_normal(H['H1'])

# Exhaust all possible one-element closed finite relational structures in this signature.
rows=[]
for values in itertools.product((False,True),repeat=4):
    model=mk(*values)
    out={key:evaluate(H[key],model) for key in ('H0','H1','H2','H3')}
    assert (not out['H1']) or out['H0']  # H1 -> H0
    assert out['H0']==out['H2'] # alpha-renaming
    rows.append({'S,C,P,R':values,**out})
assert len(rows)==16
assert any(r['H0'] and not r['H1'] for r in rows)
assert any(r['H0'] and not r['H3'] for r in rows)
assert any(r['H3'] and not r['H0'] for r in rows)
# H1->H0 is also a propositional tautology per (r,m,h); hence holds on all structures.
def body1(S,C,P,R):return (not S) or (((not C) or R) and ((not P) or (not R)))
def body0(S,C,P,R):return (not S) or (((not C) or R) and ((not P) or C or (not R)))
assert all((not body1(*v)) or body0(*v) for v in itertools.product((False,True),repeat=4))
output={'schema':'semantic-bridge-v0-exp01-independent-check/1',
 'source_sha256':PACK['source']['sha256'],
 'alpha_equivalence_proved_by_normal_form':['H0','H2'],
 'global_entailment_proved_by_16_boolean_assignments':'H1 => H0',
 'finite_structures_checked':16,
 'truth_table':truths,
 'countermodels':{
  'H0_true_H1_false':'M1_planned_checked_reported',
  'H0_true_H3_false':'M2_unverified_reported',
  'H3_true_H0_false':'M3_checked_unreported',
  'vacuous_supervisor':'M4_supervisor_absent'},
 'limits':['No author intent oracle','Presupposed manager existence is not represented','The 16-valuation tautology is propositional (not exhaustive FOL for 2+ element sorts)']}
(ROOT/'independent_result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in output.items() if k not in ('truth_table','limits')},ensure_ascii=False,indent=2))
