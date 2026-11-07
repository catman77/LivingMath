"""Real SDK HTTPS/OAuth experiment. Never imports a fixture gold into inference."""
import argparse,asyncio,base64,hashlib,json,os,sys,time
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'live_math_mcp_prod'))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from lm_suti_assurance.core import digest

POLICY={'mode':'source_only','max_candidates':4,'max_model_calls':1,'max_tokens':60000,'max_cpu_ms':4000,'max_frames':4,'seed':2211}
REQ={k:True for k in ['exact_source_bindings','typed_ast','independent_checker','no_gold_labels']}

def symbolic(s,seed):
 return {'schema':'levinmas-white-star-symbolic-request/1','source':{'text':s['text'],'sha256':s['sha256'],'rights':s['rights'],'edition':'nl002-frozen-source','language':'ru','title':'Untrusted source'},'normalization':'none','segmentation':{'unit':'whitespace','record_boundaries':'lines','renaming_scope':'local'},'algebra':{'kind':'FREE','allow_reduce':False,'preserve_history':True},'operators':['REVERSE','SPLIT','CONCAT'],'observers':['literal','alpha_pattern','adjacency'],'search':{'max_steps':12,'max_candidates_per_step':3,'max_nodes':128,'max_word_tokens':100,'history_identity':'provenance','seed':seed,'strategy':'local_structural_novelty'},'task':{'mode':'discover_relations','max_rules':4}}

def numeric(s,alternate=False):
 import re
 base=json.loads((ROOT/'docs/LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json').read_text());e=base['encoding'];e['source']={'author':'Independent synthetic fixture author','title':'Source without gold','text':s['text'],'sha256':s['sha256'],'rights':'ORIGINAL_TEST_FIXTURE'}
 e['axes']=[{'id':'position','minus':'earlier token','plus':'later token'},{'id':'ordering','minus':'alternative A','plus':'alternative B'}];e['concepts']=[]
 for i,m in enumerate(re.finditer(r'\S+',s['text'])):
  a=len(s['text'][:m.start()].encode());b=len(s['text'][:m.end()].encode());x=i+1;y=(i%3)+1
  e['concepts'].append({'id':'t'+str(i),'label':m.group(),'coordinates':[x, -y if alternate else y],'encoding_rationale':'Positional unadjudicated encoder; no semantic or truth interpretation. Alternate reflects the second coordinate.','evidence':[{'byte_start':a,'byte_end':b,'line':s['text'][:m.start()].count('\n')+1,'quote':m.group()}]})
 while len(e['concepts'])<3:
  c=dict(e['concepts'][0]);c.update(id='aux'+str(len(e['concepts'])),coordinates=[-len(e['concepts'])-1,1]);e['concepts'].append(c)
 e['source_relations']=[];e['uncertainties']=['Coordinates are explicit extra assumptions'];e['coordinate_status']='HUMAN_ASSUMED';e['provenance']={'encoder':'positional-token-order/1','alternate':alternate};e['protocol'].update(steps=24,candidates_per_step=3,frame_size=3,seed=42,decode_first_frames=4)
 return base

async def main(a):
 out=a.output;out.mkdir(mode=0o700,parents=True,exist_ok=True);save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 sources=json.loads(a.sources.read_text())['sources'];auth=authenticate(a.origin,Path.home()/'.config/livingmath/login-password',out/'oauth.private.json',a.loopback_port)
 headers={'Authorization':'Bearer '+auth['token']['access_token']}
 if a.loopback_port:headers['Host']='livingmath.example'
 checks=[];results={};save('SOURCE_MANIFEST.json',sources)
 async with httpx.AsyncClient(headers=headers,timeout=180) as http:
  from mcp_retry_transport import install
  install(http,out/'HTTP_RETRIES.jsonl')
  async with streamable_http_client(a.endpoint,http_client=http) as (read,write,_):
   async with ClientSession(TappedStream(read,out/'wire.jsonl','server_to_client'),TappedStream(write,out/'wire.jsonl','client_to_server')) as c:
    init=await c.initialize();listing=await c.list_tools();save('initialize.json',init.model_dump(mode='json'));save('tools.json',listing.model_dump(mode='json'))
    async def call(name,args,error=False):
     r=await c.call_tool(name,args);v=r.structuredContent or json.loads(r.content[0].text)
     with (out/'transcript.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'arguments':args,'response':r.model_dump(mode='json')},ensure_ascii=False)+'\n')
     if bool(r.isError)!=error:raise AssertionError((name,v))
     return v.get('data',v)
    async def read(run,view='result',tool='formal_nl_inspect',project=None):
     chunks=[];offset=0
     while True:
      v=await call(tool,{'project':project or a.project,'run_ref':run,'view':view,'offset':offset,'limit':48 if tool=='formal_nl_inspect' else 128})
      if v.get('encoding')!='base64':return v
      chunks.append(base64.b64decode(v['data']))
      if v['next_offset'] is None:
       raw=b''.join(chunks);assert hashlib.sha256(raw).hexdigest()==v['sha256'];return json.loads(raw)
      offset=v['next_offset']
    async def poll(run):
     while True:
      v=await call('formal_nl_inspect',{'project':a.project,'run_ref':run,'view':'summary'})
      if v['status']!='RUNNING':return v
      await asyncio.sleep(5)
    await call('assurance_project_new',{'project':a.project,'request_key':'init'})
    owned=[]
    for s in sources:
     f=await call('formal_store',{'project':a.project,'request_key':'source:'+s['id'],'kind':'source','data':{'text_utf8':s['text'],'sha256':s['sha256'],'rights':s['rights'],'spans':[],'context_refs':[]}})
     owned.append({'source_ref':f['stored_object_ref'],'target_signature':s['signature'],'expected_source_sha256':s['sha256']})
    for arm in a.arms.split(','):
     arm_items=[]
     for s,item in zip(sources,owned):
      refs=[]
      if arm=='B' and a.structural:
       r=await call('white_star_symbolic_explore',{'project':a.project,'request_key':'symbolic:'+s['id'],'request':symbolic(s,2211)});refs=[{'engine':'symbolic_v1','run_id':r['run_id']}]
      elif arm in ('B','C','D','N'):
       # C is a same-source permuted-frame control of N; D uses an alternate real encoder.
       r=await call('white_star_explore',{'project':a.project,'request_key':'numeric:'+('D' if arm=='D' else 'N')+':'+s['id'],'request':numeric(s,arm=='D')});refs=[{'engine':'white_star','run_id':r['run_id']}]
      arm_items.append({**item,'structural_run_refs':refs})
     outputs=[]
     for start in range(0,len(sources),6):
      key='arm:'+arm+':batch:'+str(start//6)
      args={'project':a.project,'request_key':key,'items':arm_items[start:start+6],'provider':{'kind':'owner_hosted'},'policy':{**POLICY,'mode':{'A':'source_only','B':'white_star_structural' if a.structural else 'white_star_numeric','C':'matched_ablation','D':'white_star_numeric','N':'white_star_numeric'}[arm]},'requirements':REQ}
      begun=await call('formal_nl_propose',args);end=await poll(begun['run_ref']);save('LATEST.json',{'arm':arm,'batch':start,'summary':end})
      if end['status']!='COMPLETED':raise AssertionError(end)
      result=await read(end['run_ref']);contrasts=[]
      for item in result.get('items',[]):
       if item.get('contrast_ref'):
        value=await read(item['contrast_ref'],'result','formal_inspect')
        contrasts.append({'run_ref':item['contrast_ref'],'source_sha256':item['source_sha256'],'signature':next(q['target_signature'] for q in arm_items if q['expected_source_sha256']==item['source_sha256']),'result':value,'candidate_asts':[c['formula_ast'] for c in item['candidates']]})
      outputs.append({'run_ref':end['run_ref'],'request':args,'result':result,'contrasts':contrasts})
      save('arm-'+arm+'.json',outputs);results[arm]=outputs;save('CANDIDATES_IN_PROGRESS.json',results)
      repeated=await call('formal_nl_propose',args);assert repeated['run_ref']==end['run_ref']
      replay=await read(end['run_ref'],'replay');assert replay['status']=='REPLAY_MATCH' and replay['LLM_calls']==0
      print(arm,start,'DONE',result.get('status'),flush=True)
     save('arm-'+arm+'.json',outputs)
    save('CANDIDATES_FROZEN.json',results);save('CANDIDATES_FREEZE.json',{'sha256':hashlib.sha256((out/'CANDIDATES_FROZEN.json').read_bytes()).hexdigest(),'sources_sha256':hashlib.sha256(a.sources.read_bytes()).hexdigest(),'gold_visible':False,'arms':a.arms,'human_adjudication':'NOT_EXECUTED'})
    save('result.json',{'status':'PASS_REAL_MCP_COMPLETED','sources':len(sources),'arms':a.arms,'execution_permission':False})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--endpoint',required=True);p.add_argument('--loopback-port',type=int);p.add_argument('--project',required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--arms',default='A,B,C,D');p.add_argument('--structural',action='store_true');a=p.parse_args()
 async def resilient():
  for attempt in range(5):
   try:return await main(a)
   except BaseException as exc:
    def transient(e):
     if isinstance(e,BaseExceptionGroup):return all(transient(x) for x in e.exceptions)
     return isinstance(e,(httpx.ReadError,httpx.RemoteProtocolError,httpx.ConnectError))
    if not transient(exc) or attempt==4:raise
    import traceback
    (a.output/('CLIENT_INTERRUPTION_'+str(attempt)+'.txt')).write_text(''.join(traceback.format_exception(exc)))
    await asyncio.sleep(2)
 asyncio.run(resilient())
