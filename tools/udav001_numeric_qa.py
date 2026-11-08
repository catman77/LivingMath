"""Finite real MCP comparison; independent references are evaluation only."""
import argparse,asyncio,copy,json,base64,hashlib,sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'live_math_mcp_prod'))
from dav_acceptance import TappedStream
sys.path.insert(0,str(ROOT/'docs/UDAV_CORE_PATCH001_20261108/reference_oracles'))
from independent_native_reference import EXPECTED,signature
from frozen_counterfactual import run_policy

async def main(a):
 out=a.output;out.mkdir(mode=0o700,parents=True,exist_ok=False);save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');checks=[];runs=[];rows=[]
 def check(name,ok,**details):
  checks.append({'name':name,'status':'PASS' if ok else 'FAIL','evidence':'REAL_MCP_EXECUTED',**details});save('checks.json',checks);assert ok,(name,details)
 base=json.loads((ROOT/'docs/udav-core001/fixtures/numeric-request.json').read_text());sealed=ROOT/'docs/udav-core001/fixtures/NUMERIC_NEW_PRECOMMIT.json';new=json.loads(sealed.read_text());save('PRECOMMIT_CHECK.json',{'sha256':hashlib.sha256(sealed.read_bytes()).hexdigest(),'protocol':new})
 headers={'Host':'livingmath.example'} if a.loopback else {}
 async with httpx.AsyncClient(headers=headers,timeout=180) as h:
  async with streamable_http_client(a.endpoint,http_client=h) as (rd,wr,_):
   async with ClientSession(TappedStream(rd,out/'wire.jsonl','server_to_client'),TappedStream(wr,out/'wire.jsonl','client_to_server')) as c:
    init=await c.initialize();tools=(await c.list_tools()).model_dump(mode='json');save('initialize.json',init.model_dump(mode='json'));save('tools.json',tools)
    old={x['name']:x for x in json.loads(a.baseline.read_text())['tools']};now={x['name']:x for x in tools['tools']};check('G0 all94 old schemas unchanged',all(now.get(n)==v for n,v in old.items()) and len(now)==98)
    async def call(tool,args,error=False):
     r=await c.call_tool(tool,args);v=r.structuredContent or json.loads(r.content[0].text)
     with (out/'transcript.jsonl').open('a') as f:f.write(json.dumps({'tool':tool,'arguments':args,'response':r.model_dump(mode='json')},ensure_ascii=False)+'\n')
     assert bool(r.isError)==error,(tool,v);return v.get('data',v)
    async def udav_read(ref):
     parts=[];offset=0
     while True:
      r=await call('udav_inspect',{'project':a.project,'run_id':ref,'view':'result','offset':offset,'limit':48});parts.append(base64.b64decode(r['data']))
      if r['next_offset'] is None:
       raw=b''.join(parts);assert hashlib.sha256(raw).hexdigest()==r['sha256'];return json.loads(raw)
      offset=r['next_offset']
    async def legacy_read(ref,view):
     out=[];offset=0
     while True:
      r=await call('white_star_inspect',{'project':a.project,'run_id':ref,'view':view,'offset':offset,'limit':128});assert not r['requires_artifact'];out+=r['items']
      if r['next_offset'] is None:return out
      offset=r['next_offset']
    await call('assurance_project_new',{'project':a.project,'request_key':'init'})
    for seed,k in [(21,3),(21,8),(22,3),(22,8)]:
     q=copy.deepcopy(base);q['encoding']['protocol'].update(seed=seed,candidates_per_step=k);r=await call('white_star_explore',{'project':a.project,'request_key':a.tag+':legacy96:'+str(seed)+':'+str(k),'request':q});trace=await legacy_read(r['run_id'],'trace');check('G0 native24 exact '+str((seed,k)),[t['view'] for t in trace]==EXPECTED[seed,k]);save('legacy96-'+str(seed)+'-'+str(k)+'.json',{'record':r,'trace':trace});runs.append({'engine':'legacy','run_id':r['run_id']})
    cases=[('known-quadratic',seed,None) for seed in range(23,53)]
    cases += [(name,seed,coords) for name,coords in new['geometries'].items() for seed in new['seeds']]
    atlas_cache={}
    for name,seed,coords in cases:
     q=copy.deepcopy(base);q['encoding']['protocol'].update(seed=seed,candidates_per_step=8)
     if coords:
      for concept,xy in zip(q['encoding']['concepts'],coords):concept['coordinates']=xy
     args={'project':a.project,'request_key':a.tag+':'+name+':'+str(seed),'selection_policy':'cat_distinction_tiebreak_v1','request':q}
     rec=await call('white_star_explore_v2',args);check('completed '+name+str(seed),rec['status']=='COMPLETED');res=await udav_read(rec['run_id']);save(name+'-'+str(seed)+'.json',{'request':args,'record':rec,'result':res})
     audits=res['selection_audit']
     check('G5 independent CAT signatures '+name+str(seed),all(tuple(c['arithmetic_signature'])==signature(c['matrix'],t['witness']) for t in res['trace'] for c in t['selection_audit']['candidates']))
     if name=='known-quadratic':check('G5 independent dynamic trajectory '+str(seed),[t['view'] for t in res['trace']]==run_policy(seed,8,'pair_after_novelty')['trajectory'])
     check('G5 primary max every step '+name+str(seed),all(t['novelty_primary']==max(c['novelty_primary'] for c in t['candidates']) for t in audits))
     check('G5 candidate hashes and source binding '+name+str(seed),all(hashlib.sha256(json.dumps(t['candidates'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==t['candidate_list_sha'] and all(c['source_sha256']==q['encoding']['source']['sha256'] for c in t['candidates']) for t in audits))
     seen=set()
     for t in audits:
      selected=t['candidates'][t['selected_index']];pair=selected['distinction_key']
      if selected['alias_resolution']=='DISTINCTION_AMBIGUOUS':check('G5 ambiguous not marked '+name+str(seed)+':'+str(t['step']),pair is None and selected['new_pair'] is None)
      elif pair is not None:
       check('dynamic seen memory '+name+str(seed)+':'+str(t['step']),selected['seen_before']==(tuple(pair) in seen));seen.add(tuple(pair))
     check('G5 aliases counters '+name+str(seed),len(seen)==res['summary']['selected_unambiguous_pairs'])
     replay=await call('udav_replay',{'project':a.project,'run_id':rec['run_id']});check('replay '+name+str(seed),replay['status']=='REPLAY_MATCH')
     check('G6 resources '+name+str(seed),rec['metrics']['job_cpu_s']<=5 and rec['metrics']['worker_wall_s']<=6 and rec['metrics']['max_rss_kib']*1024<=512*1024*1024)
     entry={'geometry':name,'seed':seed,'pairs':len(seen),'v2_run_id':rec['run_id'],'metrics':rec['metrics']}
     legacy=await call('white_star_explore',{'project':a.project,'request_key':a.tag+':native:'+name+':'+str(seed),'request':q})
     if name not in atlas_cache:atlas_cache[name]=await legacy_read(legacy['run_id'],'atlas')
     atlas=atlas_cache[name];native=await legacy_read(legacy['run_id'],'trace');pairs=set()
     for t in native:
      alternatives={tuple(sorted(x['concepts'])) for x in atlas[t['view']]['aliases']}
      if len(alternatives)==1:pairs.add(next(iter(alternatives)))
     entry.update(legacy_pairs=len(pairs),legacy_run_id=legacy['run_id'],legacy_metrics=legacy['metrics'])
     if all(len({tuple(sorted(x['concepts'])) for x in c['aliases']})>1 for c in atlas):
      check('G5 ambiguous atlas falls back to unchanged legacy '+str(seed),[t['view'] for t in res['trace']]==[t['view'] for t in native])
     rows.append(entry);runs.append({'engine':'v2','run_id':rec['run_id'],'geometry':name,'seed':seed});save('RESULTS_TABLE.json',rows);print(name,seed,'PAIRS',len(seen),flush=True)
    known=[r for r in rows if r['geometry']=='known-quadratic'];mean=sum(r['pairs'] for r in known)/len(known);native_mean=sum(r['legacy_pairs'] for r in known)/len(known);check('G5 mean >=21 of28',mean>=21,mean=mean,native_mean=native_mean)
    save('LIVE_RUNS.json',runs);save('result.json',{'status':'PASS','checks':len(checks),'runs':len(runs),'known_seeds':30,'new_geometry_cases':15,'mean_pairs':mean,'legacy_mean_pairs':native_mean,'execution_permission':False});print('NUMERIC_MCP_G5_PASS',mean,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--loopback',action='store_true');p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',required=True);p.add_argument('--tag',required=True);asyncio.run(main(p.parse_args()))
