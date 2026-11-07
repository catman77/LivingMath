"""Independent finite FOL interpreter for QA receipts. No production imports."""
import itertools,json,hashlib

def evaluate(p,model,env=None):
 env={} if env is None else env
 if 'pred' in p:return [env[t['var']] for t in p['args']] in model['relations'][p['pred']]
 if 'eq' in p:return env[p['eq'][0]['var']]==env[p['eq'][1]['var']]
 if 'not' in p:return not evaluate(p['not'],model,env)
 if 'and' in p:return all(evaluate(x,model,env) for x in p['and'])
 if 'or' in p:return any(evaluate(x,model,env) for x in p['or'])
 values=[evaluate(p['body'],model,{**env,p['var']:x}) for x in model['domains'][p['sort']]]
 return all(values) if p['quant']=='forall' else any(values)

def vectors(ast,signature):
 output=[]
 for size in (1,2):
  domains={s:[s+':'+str(i) for i in range(size)] for s in signature['sorts']};cells=[(name,list(x)) for name,sorts in sorted(signature['predicates'].items()) for x in itertools.product(*(domains[s] for s in sorts))]
  if len(cells)>10:return None
  for bits in itertools.product([False,True],repeat=len(cells)):
   m={'domains':domains,'relations':{p:[] for p in signature['predicates']}}
   for (p,row),yes in zip(cells,bits):
    if yes:m['relations'][p].append(row)
   output.append(evaluate(ast,m))
 return output
