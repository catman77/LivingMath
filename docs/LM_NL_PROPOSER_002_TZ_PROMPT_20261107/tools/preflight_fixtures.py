#!/usr/bin/env python3
"""Independent dev fixture sanity check. Not a source-language semantic validator."""
import hashlib,json,pathlib,sys
p=pathlib.Path(__file__).resolve().parents[1]/'fixtures'/'DEV_SOURCE_AND_FOL.json'
f=json.loads(p.read_text(encoding='utf-8'))
S=f['primary_source']['text_utf8']
assert hashlib.sha256(S.encode()).hexdigest()==f['primary_source']['sha256']
for x in f['primary_source']['spans']:
    a,b=x['byte_utf8']; assert S.encode()[a:b].decode()==x['literal']
for z in f['alpha_pair']:
    assert hashlib.sha256(z['text_utf8'].encode()).hexdigest()==z['sha256']
    assert len(z['tokens'])==len(z['alpha_pattern'])
assert f['alpha_pair'][0]['alpha_pattern']==f['alpha_pair'][1]['alpha_pattern']

def typed(node,signature,env):
    if 'quant' in node:
        assert node['sort'] in signature['sorts']; assert node['var'] not in env
        typed(node['body'],signature,{**env,node['var']:node['sort']});return 'Bool'
    if 'var' in node: assert node['var'] in env; return env[node['var']]
    if 'pred' in node:
        assert [typed(a,signature,env) for a in node['args']]==signature['predicates'][node['pred']];return 'Bool'
    if 'eq' in node:
        x,y=node['eq'];assert typed(x,signature,env)==typed(y,signature,env);return 'Bool'
    if 'not' in node:assert typed(node['not'],signature,env)=='Bool';return 'Bool'
    if 'and' in node or 'or' in node:
        for x in node.get('and',node.get('or')):assert typed(x,signature,env)=='Bool'
        return 'Bool'
    raise AssertionError(f'invalid term {node}')

def eval_(x,m,env):
    if 'quant' in x:
        values=m['domains'][x['sort']];assert values
        vals=[eval_(x['body'],m,{**env,x['var']:v}) for v in values]
        return all(vals) if x['quant']=='forall' else any(vals)
    if 'var' in x:return env[x['var']]
    if 'pred' in x:
        return [eval_(v,m,env) for v in x['args']] in m['relations'].get(x['pred'],[])
    if 'eq' in x:return eval_(x['eq'][0],m,env)==eval_(x['eq'][1],m,env)
    if 'and' in x:return all(eval_(t,m,env) for t in x['and'])
    if 'or' in x:return any(eval_(t,m,env) for t in x['or'])
    if 'not' in x:return not eval_(x['not'],m,env)
    raise AssertionError('invalid formula')

by_id={x['id']:x['formula_ast'] for x in f['formal_candidates']}
for v in by_id.values(): assert typed(v,f['target_signature'],{})=='Bool'
for obj in f['finite_models']:
    for id,truth in obj['expected_truth_vector'].items():assert eval_(by_id[id],obj['model'],{})==truth,(obj['id'],id)
assert f['negative_span']['claimed_literal']!=S.encode()[slice(*f['negative_span']['incorrect_byte_utf8'])].decode()
print('DEV_FIXTURES_PASS',len(by_id),'formulas',len(f['finite_models']),'model_truth_vectors','UTF8_SHA_AND_SPANS_PASS')
