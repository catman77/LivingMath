"""Sealed external oracles and balanced holdouts, never imported by runtime."""
import argparse,hashlib,itertools,json,shutil
from pathlib import Path
from lm_suti_assurance.core import digest
from role006_fixture import record


def expected(name,w):
 w=tuple(w)
 if name.startswith('cfg_anbn'):
  n=len(w)//2;return n>=1 and w==tuple('a'*n+'b'*n)
 if name.startswith('cfg_even_palindrome'):return bool(w) and len(w)%2==0 and w==w[::-1]
 if name.startswith('cfg_marked_palindrome'):
  return w.count('#')==1 and w.index('#')>0 and w[:w.index('#')]==w[w.index('#')+1:][::-1]
 if name=='regular_even_a':return w.count('a')%2==0
 if name=='regular_ab_plus':return bool(w) and len(w)%2==0 and w==tuple('ab'*(len(w)//2))
 if name=='noncfg_anbncn_canary':
  n=len(w)//3;return n>=1 and w==tuple('a'*n+'b'*n+'c'*n)
 pairs={'a':'b'} if name=='cfg_dyck1' else {'S':'P','A':'B'};stack=[]
 for token in w:
  if token in pairs:stack.append(pairs[token])
  elif not stack or stack.pop()!=token:return False
 return not stack


def prepare(previous,spec,out):
 out.mkdir(mode=0o700,parents=True,exist_ok=False);cases={};gold={}
 names=['cfg_anbn','cfg_even_palindrome','cfg_dyck1','cfg_dyck2_new_stratified','cfg_marked_palindrome','regular_even_a','regular_ab_plus','noncfg_anbncn_canary']
 for name in names:
  tr=json.loads((previous/(name+'.train.json')).read_text());qu=json.loads((previous/(name+'.queries.json')).read_text())
  assert tr['sha256']==digest({k:v for k,v in tr.items() if k!='sha256'}) and qu['sha256']==digest({k:v for k,v in qu.items() if k!='sha256'})
  assert all(r['accepted']==expected(name,r['tokens']) for r in tr['records']) and all('accepted' not in r for r in qu['records'])
  cases[name]={'train':tr['records'],'queries':qu['records'],'original_train_sha256':tr['sha256'],'original_query_sha256':qu['sha256']}
  gold[name]={r['id']:expected(name,r['tokens']) for r in qu['records']}
 # Query-only challenging sets. No labels are sent to the MCP inference API.
 holdouts={}
 holdouts['cfg_anbn']=[tuple('a'*n+'b'*n) for n in [4,5,6]]+[tuple('a'*(n-1)+'b'+'a'+'b'*(n-1)) for n in [4,5,6]]
 all2=list(itertools.product('SPAB',repeat=6));pos=[w for w in all2 if expected('cfg_dyck2_new_stratified',w)]
 neg=[w for w in all2 if w.count('S')==w.count('P') and w.count('A')==w.count('B') and not expected('cfg_dyck2_new_stratified',w)]
 holdouts['cfg_dyck2_new_stratified']=pos+neg[:len(pos)]
 allp=list(itertools.product('ab',repeat=8));pos=[w for w in allp if expected('cfg_even_palindrome',w)];neg=[w for w in allp if w.count('a')%2==0 and not expected('cfg_even_palindrome',w)]
 holdouts['cfg_even_palindrome']=pos+neg[:len(pos)]
 pos=[w+('#',)+w[::-1] for w in itertools.product('ab',repeat=4)];neg=[w[:5]+w[6:]+w[5:6] for w in pos if w[5:6]!=w[-1:]]
 # Fill strict delimiter-preserving mismatches, with equal symbol multisets where possible.
 for left in itertools.product('ab',repeat=4):
  for right in itertools.product('ab',repeat=4):
   w=left+('#',)+right
   if not expected('cfg_marked_palindrome',w) and w not in neg and sorted(left)==sorted(right):neg.append(w)
 holdouts['cfg_marked_palindrome']=pos+neg[:16]
 holdouts['regular_even_a']=list(itertools.product('ab',repeat=7))
 holdouts['regular_ab_plus']=list(itertools.product('ab',repeat=7))+[tuple('ab'*4),tuple('ab'*5),()]
 for name,words in holdouts.items():
  cases[name]['enriched_queries']=[record(list(w),prefix='fh') for w in words]
  gold[name+'-enriched']={r['id']:expected(name,r['tokens']) for r in cases[name]['enriched_queries']}
 # Explicit external annotation is a NEW generation; original records/labels remain unchanged.
 cases['cfg_anbn']['annotation']=[record([],False,'annotation')]
 cases['cfg_even_palindrome']['annotation']=[record([],False,'annotation')]
 cases['cfg_marked_palindrome']['annotation']=[record(['#'],False,'annotation'),record(['a','b'],False,'annotation')]
 cases['regular_even_a']['annotation']=[record(['a'],False,'annotation')]
 cases['regular_ab_plus']['annotation']=[record([],False,'annotation'),record(['a'],False,'annotation')]
 data={'schema':'formal001-sealed-inputs/1','cases':cases,'fol':json.loads((spec/'fixtures/quantifier_ambiguity.json').read_text()),'grammar_controls':json.loads((spec/'fixtures/grammar_oracles.json').read_text())}
 annotations={name:{digest(list(w)):expected(name,w) for n in range(7) for w in itertools.product('ab',repeat=n)} for name in ['regular_even_a','regular_ab_plus']}
 (out/'external-annotations.json').write_text(json.dumps(annotations,indent=2)+'\n')
 for n,v in [('inputs.json',data),('external-gold.json',gold)]: (out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 protocol={'schema':'formal001-protocol/1','files':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['inputs.json','external-gold.json','external-annotations.json']},'conditions':'Original train/query exact; new enriched query-only, optional external annotation is a distinct new train generation. No gold available to runtime fit.','finite_only':True,'anbn_positive_limit':'Within12tokens, only3 unseen nonempty positives remain beyond train lengths2/4/6; not padded/duplicated to16.','spec_discrepancy':'SAPB/ASBP reject under supplied typed pair grammar; SABP/ASPB positive.','seed_policy':'Formal search canonical/deterministic, no random seed; old comparisons use137/42, same input refs.'};(out/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2)+'\n');print(json.dumps(protocol))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--previous',type=Path,required=True);a.add_argument('--spec',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();prepare(v.previous,v.spec,v.output)
