"""Actual no-auth MCP/worker acceptance; oracles are harness-only."""
import argparse,asyncio,base64,copy,hashlib,json,sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'live_math_mcp_prod'))
from dav_acceptance import TappedStream


def symbolic(seed=119):
    q=json.loads((ROOT/'docs/udav-core001/fixtures/split-request.json').read_text());q['search'].update(seed=seed,strategy='frontier_argument_coverage_v1');return q

async def main(a):
 out=a.output;out.mkdir(mode=0o700,parents=True,exist_ok=False);save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');checks=[];runs=[]
 def check(name,yes,**details):
  checks.append({'name':name,'status':'PASS' if yes else 'FAIL','evidence':'REAL_MCP_EXECUTED',**details});save('checks.json',checks);assert yes,(name,details)
 headers={'Host':'livingmath.example'} if a.loopback else {}
 async with httpx.AsyncClient(headers=headers,timeout=180) as h:
  async with streamable_http_client(a.endpoint,http_client=h) as (rd,wr,_):
   async with ClientSession(TappedStream(rd,out/'wire.jsonl','server_to_client'),TappedStream(wr,out/'wire.jsonl','client_to_server')) as c:
    init=await c.initialize();tools=(await c.list_tools()).model_dump(mode='json');save('tools.json',tools);save('initialize.json',init.model_dump(mode='json'))
    before={t['name']:t for t in json.loads(a.baseline.read_text())['tools']};now={t['name']:t for t in tools['tools']};check('all94 old tool records exact',len(before)==94 and all(now.get(n)==v for n,v in before.items()))
    async def call(name,args,error=False):
     r=await c.call_tool(name,args);v=r.structuredContent or json.loads(r.content[0].text)
     with (out/'transcript.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'arguments':args,'response':r.model_dump(mode='json')},ensure_ascii=False)+'\n')
     assert bool(r.isError)==error,(name,v);return v.get('data',v)
    async def inspect(ref,view='result',project=None):
     parts=[];offset=0
     while True:
      r=await call('udav_inspect',{'project':project or a.project,'run_id':ref,'view':view,'offset':offset,'limit':48})
      if r.get('encoding')!='base64':return r
      parts.append(base64.b64decode(r['data']))
      if r['next_offset'] is None:
       raw=b''.join(parts);assert hashlib.sha256(raw).hexdigest()==r['sha256'];return json.loads(raw)
      offset=r['next_offset']
    async def explore(key,q,tool='udav_symbolic_explore',extra=None):
     args={'project':a.project,'request_key':a.tag+':'+key,'request':q,**(extra or {})};rec=await call(tool,args)
     assert rec['status']=='COMPLETED',rec
     result=await inspect(rec['run_id']);save(key+'.json',{'request':args,'record':rec,'result':result});runs.append({'key':key,'run_id':rec['run_id'],'record':rec})
     return args,rec,result
    await call('assurance_project_new',{'project':a.project,'request_key':'init'})
    for seed in range(119,125):
     args,rec,r=await explore('split-'+str(seed),symbolic(seed))
     if seed==119:first_args=copy.deepcopy(args)
     states={s['node_id']:s for s in r['states']};words={tuple(s['tokens']) for s in states.values()};root=next(iter(states.values()))['tokens'];target={tuple(root[i:j]) for i in range(len(root)+1) for j in range(i,len(root)+1)}
     check('G1 source'+str(seed),len(target)==22 and len(words&target)>=21 and r['summary']['applied']==72,coverage=len(words&target),applies=r['summary']['applied'])
     attempted=set();epsilon_run=0;max_empty=0;inputs=[]
     for step in r['ops_trace']:
      for cand in step['candidates']:
       ident=(cand['input_node'],cand['operator'],cand['parameter_key']);check('unique work '+str(seed)+':'+str(len(attempted)),ident not in attempted);attempted.add(ident);inputs.append(cand['input_node'])
       epsilon_run=epsilon_run+1 if not states[cand['input_node']]['tokens'] else 0;max_empty=max(max_empty,epsilon_run)
     check('G2 no epsilon starvation '+str(seed),max_empty<=1,consecutive_empty=max_empty)
     check('G3 both split branches expanded '+str(seed),any(len(x['outputs'])==2 and all(i in inputs for i in x['outputs']) and all(len(states[i]['tokens'])>=2 for i in x['outputs']) for t in r['ops_trace'] for x in t['candidates']))
     check('G6 unchanged request ceilings '+str(seed),r['summary']['nodes']<=args['request']['search']['max_nodes'] and r['summary']['total_stored_tokens']<=args['request']['search']['max_total_tokens'])
     check('G8 no global exhaustion '+str(seed),not r['summary']['global_exhaustion_proved'] and r['checks']['LLM_calls']==0 and r['checks']['execution_permission'] is False)
     replay=await call('udav_replay',{'project':a.project,'run_id':rec['run_id']});check('replay '+str(seed),replay['status']=='REPLAY_MATCH')
     check('same request key '+str(seed),(await call('udav_symbolic_explore',args))['run_id']==rec['run_id'])
    q=symbolic();q['operators']=['REVERSE','SPLIT'];_,_,left=await explore('operator-order-A',q);q=copy.deepcopy(q);q['operators'].reverse();_,_,right=await explore('operator-order-B',q);check('G3 operator-order independent',left['ops_trace']==right['ops_trace'] and left['history']==right['history'])
    q=symbolic();q['search']['history_identity']='provenance';_,_,r=await explore('provenance-identity',q);check('G3 provenance identity and DAG',r['checks']['DAG_acyclic_and_hashed'] and len(r['history'])>r['summary']['unique_literal_words'])
    for label,changes in [('tiny-budget',{'max_nodes':3}),('tiny-tokens',{'max_total_tokens':16})]:
     q=symbolic();q['search'].update(changes);_,_,r=await explore(label,q);check('G6 '+label,r['summary']['halt_reason'].startswith('MAX_') and not r['summary']['global_exhaustion_proved'])
    q=symbolic();q['observers']=['literal','composition'];_,_,r=await explore('raw-only',q);check('G4 undefined structural quotient',r['summary']['structural_novelty_status']=='STRUCTURAL_NOVELTY_UNDEFINED' and r['summary']['new_structural_class'] is None)
    foreign=a.project+'-foreign';await call('assurance_project_new',{'project':foreign,'request_key':'init'})
    v=await call('udav_inspect',{'project':foreign,'run_id':runs[0]['run_id']},True);check('G7 foreign run',v['error']['code']=='NOT_FOUND')
    v=await call('udav_replay',{'project':a.project,'run_id':runs[0]['run_id'],'expected_result_sha256':'0'*64},True);check('G7 altered replay digest',v['error']['code']=='REJECTED_PROVENANCE')
    v=await call('udav_inspect',{'project':a.project,'run_id':runs[0]['run_id'],'view':'summary','expected_result_sha256':'0'*64},True);check('G7 altered summary digest',v['error']['code']=='REJECTED_PROVENANCE')
    q=symbolic();q['source']['sha256']='0'*64
    v=await call('udav_symbolic_explore',{'project':a.project,'request_key':a.tag+':bad-sha','request':q},True);check('G7 changed source SHA rejected',v['error']['code'] in ('SOURCE_MISMATCH','SOURCE_BINDING_MISMATCH'))
    changed=copy.deepcopy(first_args);changed['request']['search']['seed']+=1
    v=await call('udav_symbolic_explore',changed,True);check('G7 request key substitution rejected',v['error']['code']=='REQUEST_KEY_CONFLICT')
    v=await call('udav_inspect',{'project':a.project,'run_id':'0'*64},True);check('G7 fake run rejected',v['error']['code']=='NOT_FOUND')
    q=symbolic();q['operators']=['RENAME'];q['observers']=['literal','composition','alpha_pattern'];_,_,r=await explore('sampled-mapping',q)
    check('G3 partial mapping family declared',r['summary']['parameter_coverage']['RENAME']['status']=='ARGUMENT_FAMILY_PARTIAL')
    check('G4 defined quotient raw-only growth',r['summary']['new_raw_observation']>0 and r['summary']['new_structural_class']==0)
    q=symbolic();q['search']['cpu_budget_ms']=1;_,_,r=await explore('cooperative-cpu-bound',q);check('G6 CPU bound retains source DAG',r['summary']['halt_reason']=='CPU_BOUND' and r['checks']['DAG_acyclic_and_hashed'])
    q=symbolic();q['source'].update(text='S P',sha256=hashlib.sha256(b'S P').hexdigest());q['source'].pop('alphabet',None);q['algebra']['kind']='SP';q['operators']=['INSERT_CANCEL_PAIR'];_,_,r=await explore('both-insert-kinds',q)
    check('G3 both real INSERT kinds',{c['args']['kind'] for t in r['ops_trace'] for c in t['candidates']}=={'SP','PS'})
    save('LIVE_RUNS.json',runs);save('service_health.json',await call('service_health',{}));save('result.json',{'status':'PASS','checks':len(checks),'runs':len(runs),'tools':len(tools['tools']),'phase':'SYMBOLIC_G1_G2_GATE','execution_permission':False});print('SYMBOLIC_G1_G2_MCP_PASS',len(checks),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--loopback',action='store_true');p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',required=True);p.add_argument('--tag',required=True);asyncio.run(main(p.parse_args()))
