import copy,hashlib,itertools,json
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.formal_bridge.ir import grammar, limits
from lm_suti_assurance.formal_bridge.chart import parse
from lm_suti_assurance.formal_bridge.proof_checker import verify
from lm_suti_assurance.formal_bridge.search import fit
from lm_suti_assurance.formal_bridge.dfa import fit as fit_dfa


def rec(word,y=None):
 tokens=list(word);text=' '.join(tokens);r={'id':digest(tokens),'tokens':tokens,'source':{'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'rights':'ORIGINAL_TEST','edition':'formal001/1'}}
 if y is not None:r['accepted']=y
 return r


def g(rules,start='N0'):
 return grammar({'schema':'formal-grammar-ir/1','terminals':sorted({s[2:] for rr in rules.values() for rhs in rr for s in rhs if s.startswith('t:')}),'nonterminals':list(rules),'start':start,'productions':[{'id':'p'+str(i),'lhs':n,'rhs':[{'op':'TERM','value':s[2:]} if s.startswith('t:') else {'op':'NT_REF','name':s[2:]} for s in rhs] or [{'op':'EPS'}]} for i,(n,rhs) in enumerate((n,rhs) for n,rr in rules.items() for rhs in rr)]})


def test_independent_start_does_not_inherit_epsilon():
 ast=g({'N0':[['t:a','n:N1','t:b']],'N1':[[],['t:a','n:N1','t:b']]})
 assert parse(ast,rec(''),limits())['status']=='REJECT_COMPLETE'
 for w in ['ab','aabb']:
  p=parse(ast,rec(w),limits());assert p['status']=='ACCEPT_WITH_WITNESS';assert verify(ast,rec(w),limits(),p)['status']=='CHECKED_INSTANCE'


def test_packed_ambiguity_and_cycles():
 ast=g({'N0':[['n:N0','n:N0'],['t:a']]});p=parse(ast,rec('aaa'),limits())
 assert p['status']=='ACCEPT_WITH_WITNESS' and len(p['trees'])==2
 assert verify(ast,rec('aaa'),limits(),p)['status']=='CHECKED_INSTANCE'
 cyclic=g({'N0':[[],['n:N0']]});p=parse(cyclic,rec(''),limits());assert p['status']=='UNKNOWN_CYCLE';assert p['decision'] is None


@pytest.mark.parametrize('mutation',['grammar','source','span','production','terminal','child_order','start'])
def test_forged_forest_rejected(mutation):
 ast=g({'N0':[[],['t:a','n:N0','t:b','n:N0']]});r=rec('aabb');p=parse(ast,r,limits());bad=copy.deepcopy(p)
 if mutation=='grammar':bad['grammar_sha256']='0'*64
 elif mutation=='source':bad['source_sha256']='0'*64
 elif mutation=='span':bad['token_spans'][0][0]+=1
 elif mutation=='production':bad['forest'][0]['families'][0]['production_id']='not-a-rule'
 elif mutation=='terminal':bad['tokens'][0]='alien'
 elif mutation=='child_order':next(f for row in bad['forest'] for f in row['families'] if len(f['children'])>1)['children'].reverse()
 elif mutation=='start':bad['start_symbol']='alien'
 assert verify(ast,r,limits(),bad)['status']=='REJECTED_PROOF'


def test_bound_is_not_negative():
 ast=g({'N0':[[],['t:a','n:N0','t:b']]});b=limits({'max_steps':1});p=parse(ast,rec('aabb'),b)
 assert p['status']=='UNKNOWN_BOUND' and p['decision'] is None


def test_search_retains_nullable_rival_and_no_query_input():
 train=[rec(w,tuple(w)==tuple('a'*(len(w)//2)+'b'*(len(w)//2))) for n in [2,4] for w in itertools.product('ab',repeat=n)]
 model=fit(train,{},limits());assert len(model['candidates'])>=2
 values={parse(c['ast'],rec(''),limits())['decision'] for c in model['candidates']};assert values=={True,False}
 assert all(c['origin']=='TRAIN_PRIMITIVE_SEARCH' for c in model['candidates'])


def test_dfa_learns_table_not_scalar_shortcut():
 train=[rec(w,sum(t=='a' for t in w)%2==0) for n in range(4) for w in itertools.product('ab',repeat=n)]
 m=fit_dfa(train,limits());ast=m['candidates'][0]['ast'];assert len(ast['states'])==2
 from lm_suti_assurance.formal_bridge.dfa import run
 for n in range(7):
  for w in itertools.product('ab',repeat=n):
   p=run(ast,rec(w),limits());assert p['decision']==(sum(t=='a' for t in w)%2==0);assert verify(ast,rec(w),limits(),p)['status']=='CHECKED_INSTANCE'
 bad=run(ast,rec('aba'),limits());bad['trace'][1]['target']=99;assert verify(ast,rec('aba'),limits(),bad)['status']=='REJECTED_PROOF'


def test_three_proposed_fol_readings_two_models_and_countermodels():
 from pathlib import Path
 from lm_suti_assurance.formal_bridge import fol
 raw=json.loads((Path(__file__).parents[1]/'docs/LivingMath_Formal_Bridge_v1_20261107/livingmath_formal_bridge_v1/fixtures/quantifier_ambiguity.json').read_text())
 sig={'sorts':raw['nonempty_sorts'],'predicates':raw['signature']};source={'text_utf8':raw['source']['text'],'sha256':raw['source']['sha256'],'spans':[],'context_refs':[],'rights':raw['source']['rights']}
 props=[{'formula_ast':c['formula_ast'],'assumptions':[],'token_role_links':[{'byte_utf8':x['byte_utf8'],'literal':x['literal']} for x in c['source_token_links']],'construction_trace':[{'origin':'HUMAN_FIXTURE','annotation_id':c['candidate_id']}]} for c in raw['candidates']]
 out=fol.propose(source,{'kind':'human','provenance':{'origin':'fixture'}},sig,props)
 assert len(out['candidates'])==3 and all(c['type_status']=='TYPED' and c['proof_status']=='PROPOSED' for c in out['candidates'])
 for model in raw['finite_models']:
  got=[fol.evaluate(c['formula_ast'],sig,{**model['model'],'world':'closed'},limits())['truth'] for c in out['candidates']]
  assert got==list(model['truth_vector'].values())
 for i,j in [(0,1),(0,2),(1,2)]:assert fol.countermodels([out['candidates'][i],out['candidates'][j]],limits())['status']=='FINITE_COUNTERMODEL'
 bad=copy.deepcopy(props[0]['formula_ast']);bad['body']['body']['args'].reverse();assert fol.typecheck(bad,sig)['status']=='TYPE_REJECTED'
 assert fol.typecheck({'pred':'Checked','args':[{'var':'r'},{'var':'h'}]},sig)['status']=='TYPE_REJECTED'
 assert fol.evaluate(props[0]['formula_ast'],sig,{**raw['finite_models'][0]['model'],'world':'open'},limits())['status']=='UNKNOWN'


def test_fol_source_span_tamper_rejected():
 from lm_suti_assurance.formal_bridge.fol import check_source
 s={'text_utf8':'Ж','sha256':hashlib.sha256('Ж'.encode()).hexdigest(),'rights':'original','context_refs':[],'spans':[{'byte_utf8':[0,1],'literal':'Ж'}]}
 with pytest.raises(ValueError):check_source(s)


def test_actual_worker_and_service_idempotency_isolation(tmp_path):
 import asyncio
 from lm_suti_assurance.service import Service
 from lm_suti_assurance.formal_bridge.service import FormalService
 from lm_suti_assurance.symbolic.executor import Executor
 from lm_suti_assurance.errors import AssuranceError
 from lm_suti_assurance.workspace import validate_history
 pool=Executor();Service(tmp_path).new('qa-formal','project');Service(tmp_path).new('other','project')
 svc=FormalService(tmp_path,pool)
 async def run():
  p={'kind':'record','data':rec('aabb')}
  a=await svc.operation('qa-formal','one','store',p);b=await svc.operation('qa-formal','one','store',p)
  assert a==b and a['status']=='COMPLETED'
  with pytest.raises(AssuranceError):await svc.operation('qa-formal','one','store',{'kind':'record','data':rec('ab')})
  with pytest.raises(AssuranceError):svc.owned(svc.ext.workspace('other'),a['stored_object_ref'])
  ast=g({'N0':[[],['t:a','n:N0','t:b']]});stored=await svc.operation('qa-formal','grammar','store',{'kind':'grammar','data':ast})
  v=await svc.operation('qa-formal','check','verify',{'run_ref':stored['run_ref'],'source_ref':a['stored_object_ref']})
  assert v['status']=='COMPLETED' and v['result_status']=='CHECKED_INSTANCE'
  replay=await svc.operation('qa-formal','replay','replay',{'run_ref':v['run_ref']});assert replay['result_status']=='REPLAY_MATCH'
  journal=svc.ext.workspace('qa-formal').history();validate_history(journal);assert len(journal)==9
 try:asyncio.run(run())
 finally:pool.close()


def test_center_base_is_not_eliminated_by_short_negative_pair():
 train=[rec('a#b',True),rec('ab',False),rec('#',False)]
 m=fit(train,{},limits());assert m['candidates']
 assert any(parse(c['ast'],rec('aa#bb'),limits())['decision'] is True for c in m['candidates'])


def test_unknown_catalog_does_not_claim_incompatibility():
 m=fit([rec(w,w==('a','b')) for w in itertools.product('ab',repeat=2)],{},limits({'max_tokens':1}))
 assert m['status'].startswith('UNKNOWN_BOUND') and m['search_status'].startswith('UNKNOWN_BOUND')


def test_catalog_generation_itself_is_bounded():
 import time
 t=time.process_time();m=fit([rec('abc',True)],{},limits({'max_cpu_ms':1}));assert m['status'].startswith('UNKNOWN_BOUND')
 assert time.process_time()-t<0.2
 assert m['catalog']['catalog_generation_status'].startswith('UNKNOWN_BOUND')


def test_dfa_long_prefix_trie_uses_no_python_recursion():
 train=[rec(w+tuple('aaaa'),True) for w in itertools.product('ab',repeat=8)]
 m=fit_dfa(train,limits({'max_states':1}));assert m['candidates'] and len(m['candidates'][0]['ast']['states'])==1


def test_countermodel_respects_shared_assumptions():
 from lm_suti_assurance.formal_bridge.fol import countermodels
 sig={'sorts':['x'],'predicates':{'P':['x']}}
 atom={'pred':'P','args':[{'var':'v'}]};all_p={'quant':'forall','var':'v','sort':'x','body':atom};tautology={'quant':'forall','var':'v','sort':'x','body':{'eq':[{'var':'v'},{'var':'v'}]}}
 cs=[{'candidate_id':str(i),'signature':sig,'formula_ast':f,'assumptions':[all_p],'type_status':'TYPED'} for i,f in enumerate([all_p,tautology])]
 out=countermodels(cs,limits());assert out['status']=='NO_COUNTERMODEL_WITHIN_BOUND' and out['equivalence_claim'] is False
