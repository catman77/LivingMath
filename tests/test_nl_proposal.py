import asyncio,copy,hashlib,json
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.nl_proposal.decoder import source_packet,decode,build_move,replay_bundle,build_request
from lm_suti_assurance.nl_proposal.provenance import traces
from lm_suti_assurance.formal_bridge.fol import typecheck

SIG={'sorts':['agent','item'],'predicates':{'P':['agent','item']}}
AST={'quant':'forall','var':'x','sort':'agent','body':{'quant':'exists','var':'y','sort':'item','body':{'pred':'P','args':[{'var':'x'},{'var':'y'}]}}}
POLICY={'mode':'source_only','max_candidates':4,'max_model_calls':1,'max_tokens':60000,'max_cpu_ms':4000,'max_frames':4,'seed':21}
def source(text='Любой мастер выбрал предмет.'):
 return {'text_utf8':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'rights':'ORIGINAL_TEST_FIXTURE','spans':[],'context_refs':[]}
def answer(s,ast=None):
 return {'source_sha256':s['sha256'],'observations':[{'token_index':0,'role':'quantifier','interpretation':'proposed universal'}],'proposals':[{'formula_json':json.dumps(ast or AST),'reading':'possible reading','token_indices':[0,1,2,3],'binder_links':[{'var':'x','token_index':0},{'var':'y','token_index':3}],'added_assumptions':[]}],'open_alternatives':[],'unsupported':[]}

def test_exact_source_and_reverse_normalization():
 s=source('е\u0308ж выбрал вещь');p=source_packet(s,'NFC');assert p['normalized_text'].startswith('ёж');assert ''.join(x['original_literal'] for x in p['reverse_map'])==s['text_utf8']
 assert p['tokens'][0]['byte_utf8']==[0,len('е\u0308ж'.encode())]

@pytest.mark.parametrize('mutation',['sha','span','quote','rights'])
def test_source_tamper(mutation):
 s=source()
 if mutation=='sha':s['sha256']='0'*64
 if mutation=='span':s['spans']=[{'byte_utf8':[1,9],'literal':'Любой'}]
 if mutation=='quote':s['spans']=[{'byte_utf8':[0,10],'literal':'другой'}]
 if mutation=='rights':s['rights']=''
 with pytest.raises((ValueError,UnicodeDecodeError)):source_packet(s)

@pytest.mark.parametrize('kind',['wrong_sort','free_var','unknown_predicate'])
def test_type_failures_are_retained(kind):
 s=source();a=copy.deepcopy(AST)
 if kind=='wrong_sort':a['body']['body']['args'].reverse()
 if kind=='free_var':a['body']['body']['args'][0]['var']='free'
 if kind=='unknown_predicate':a['body']['body']['pred']='alien'
 d=decode(source_packet(s),SIG,answer(s,a),{},[],POLICY)
 assert not d['candidates'] and d['status']=='NO_WELL_TYPED_DECODING' and d['rejected_moves'][0]['status']=='TYPE_REJECTED'

def test_trace_causally_generates_different_ast_without_semantic_claim():
 s=source();p=source_packet(s);trace={'trace_sha256':'1'*64,'source_order':[{'byte_utf8':t['byte_utf8'],'literal':t['literal']} for t in reversed(p['tokens'])]}
 d=decode(p,SIG,answer(s),{},[trace],{**POLICY,'mode':'white_star_structural'})
 assert len(d['candidates'])==2
 c=d['candidates'][0];m=c['structural_move_log'][0]
 assert c['origin_status']=='TRACE_LINK_CHECKED' and m['before_ast_sha256']!=m['after_ast_sha256']
 assert c['semantic_alignment_status']=='PROPOSED' and not c['execution_permission']
 assert build_move(m['before_ast'],SIG,m['binder_links'],trace)==m

def test_universal_overstrength_is_proposed_not_refuted_or_verified():
 s=source();a=copy.deepcopy(AST);a['body']['quant']='forall'
 c=decode(source_packet(s),SIG,answer(s,a),{},[],POLICY)['candidates'][0]
 assert c['type_status']=='TYPED' and c['semantic_alignment_status']=='PROPOSED'

def test_exact_ast_only_dedup_and_frozen_replay():
 s=source();a=answer(s);a['proposals']*=2;p=source_packet(s);raw=json.dumps({'items':[a]});items=[{'source_ref':'1'*64,'packet':p,'signature':SIG,'answer':a,'traces':[]}];request=build_request(items,POLICY);r={'request':request,'request_sha256':digest(request),'raw_output':raw,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest()};d=decode(p,SIG,a,r,[],POLICY)
 assert len(d['raw_proposals'])==2 and len(d['candidates'])==1
 b={'receipt':r,'receipt_digest':digest(r),'policy':POLICY,'items':items,'decoded_sha256':digest([d])}
 assert replay_bundle(b)['LLM_calls']==0
 b['decoded_sha256']='0'*64
 with pytest.raises(AssuranceError,match='REJECTED_PROVENANCE'):replay_bundle(b)

def test_real_symbolic_trace_spoofing_project_isolation_and_idempotency(tmp_path):
 from lm_suti_assurance.symbolic.executor import Executor
 from lm_suti_assurance.symbolic.service import SymbolicService
 from lm_suti_assurance.nl_proposal.service import NLService
 from lm_suti_assurance.service import Service
 from lm_suti_assurance.workspace import validate_history
 pool=Executor();s=source()
 async def run():
  root=tmp_path/'state';base=Service(root);base.new('qa-nl','new');base.new('other','new');nl=NLService(root,pool)
  f=await nl.formal.operation('qa-nl','source','store',{'kind':'source','data':s});ref=f['stored_object_ref']
  req={'schema':'levinmas-white-star-symbolic-request/1','source':{'text':s['text_utf8'],'sha256':s['sha256'],'rights':s['rights'],'edition':'qa','language':'ru','title':'QA'},'normalization':'none','segmentation':{'unit':'whitespace','record_boundaries':'lines','renaming_scope':'local'},'algebra':{'kind':'FREE','allow_reduce':False,'preserve_history':True},'operators':['REVERSE','SPLIT'],'observers':['literal','alpha_pattern'],'search':{'max_steps':4,'max_candidates_per_step':2,'max_nodes':32,'max_word_tokens':32,'history_identity':'provenance','seed':21,'strategy':'local_structural_novelty'},'task':{'mode':'discover_relations','max_rules':4}}
  sy=SymbolicService(root,pool);r=await sy.explore('qa-nl','sy',req);assert r['status']=='COMPLETED'
  spec={'engine':'symbolic_v1','run_id':r['run_id']};ts=traces(root,'qa-nl',s,[spec],4);assert ts
  attacks=[('fake_run',{**spec,'run_id':'0'*64},s,'qa-nl'),('fake_node',{**spec,'node_refs':['0'*64]},s,'qa-nl'),('fake_parent',{**spec,'node_refs':[ts[0]['node_ref']],'parent_ids':['0'*64]},s,'qa-nl'),('input_sha',{**spec,'input_sha256':'0'*64},s,'qa-nl'),('source_sha',spec,source('Другой исходник.'),'qa-nl'),('foreign_project',spec,s,'other')]
  for name,attack,src,project in attacks:
   with pytest.raises(AssuranceError):traces(root,project,src,[attack],4)
  args={'source_ref':ref,'target_signature':SIG,'provider':{'kind':'owner_hosted'},'requirements':{k:True for k in ['exact_source_bindings','typed_ast','independent_checker','no_gold_labels']},'policy':POLICY}
  traced=await asyncio.wait_for(nl.propose('qa-nl','traced-key',{**args,'structural_run_refs':[spec],'policy':{**POLICY,'mode':'white_star_structural'}}),timeout=3)
  await asyncio.gather(*list(nl.tasks))
  a=await nl.propose('qa-nl','key',args);await asyncio.gather(*list(nl.tasks));b=await nl.propose('qa-nl','key',args)
  assert a['run_ref']==b['run_ref'] and b['status']=='COMPLETED'
  out=nl.inspect('qa-nl',b['run_ref'],'result');assert out['status']=='PROVIDER_UNAVAILABLE' and out['model_calls']==0
  with pytest.raises(AssuranceError,match='REQUEST_KEY_CONFLICT'):await nl.propose('qa-nl','key',{**args,'policy':{**POLICY,'seed':22}})
  with pytest.raises(AssuranceError):nl.inspect('other',b['run_ref'])
  class WaitingProvider:
   def __init__(self):self.release=asyncio.Event()
   async def generate(self,request):
    await self.release.wait();return {'status':'PROVIDER_UNAVAILABLE','reason':'explicit test double'}
  waiting=WaitingProvider();nl.provider=waiting
  attempts=await asyncio.gather(*(nl.propose('qa-nl','concurrent-'+str(i),args) for i in range(12)),return_exceptions=True)
  assert sum(not isinstance(x,Exception) for x in attempts)==4 and len(nl.tasks)==4
  assert all(x.code=='NL_RESOURCE_BUSY' for x in attempts if isinstance(x,Exception))
  assert (await nl.propose('qa-nl','key',args))['run_ref']==b['run_ref']
  waiting.release.set();await asyncio.gather(*list(nl.tasks))
  validate_history(base.workspace('qa-nl').history())
 try:asyncio.run(run())
 finally:pool.close()

@pytest.mark.parametrize('field',['normalization','policy','source_ref','answer','raw_output'])
def test_offline_replay_binds_provider_request_and_receipt(field):
 s=source();a=answer(s);packet=source_packet(s);items=[{'source_ref':'1'*64,'packet':packet,'signature':SIG,'answer':a,'traces':[]}]
 request=build_request(items,POLICY);raw=json.dumps({'items':[a]});r={'request':request,'request_sha256':digest(request),'raw_output':raw,'raw_output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
 b={'receipt':r,'receipt_digest':digest(r),'policy':dict(POLICY),'items':items,'decoded_sha256':digest([decode(packet,SIG,a,r,[],POLICY)])}
 assert replay_bundle(b)['status']=='REPLAY_MATCH'
 if field=='normalization':b['items'][0]['packet']['normalization']='NFC'
 if field=='policy':b['policy']['max_tokens']=1000
 if field=='source_ref':b['items'][0]['source_ref']='0'*64
 if field=='answer':b['items'][0]['answer']['open_alternatives']=['forged']
 if field=='raw_output':b['receipt']['raw_output']='{}'
 with pytest.raises(AssuranceError):replay_bundle(b)
