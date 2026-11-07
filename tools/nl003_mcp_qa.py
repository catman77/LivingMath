"""Actual SDK/OAuth causal acceptance. Source-only receipts are never regenerated."""
import argparse, asyncio, base64, copy, hashlib, json, os, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'live_math_mcp_prod'))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from lm_suti_assurance.core import digest
from lm_suti_assurance.nl_proposal.causal import ARMS
from nl002_mcp_qa import symbolic

POLICY={'max_candidates_per_source':8,'max_ast_nodes':32,'max_cpu_ms':4000,'sham_seed':2211,'max_primitive_depth':2}

async def main(a):
 out=a.output;out.mkdir(mode=0o700,parents=True,exist_ok=False)
 save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 auth=authenticate(a.origin,Path.home()/'.config/livingmath/login-password',out/'oauth.private.json',a.loopback_port)
 headers={'Authorization':'Bearer '+auth['token']['access_token']}
 if a.loopback_port:headers['Host']='livingmath.example'
 checks=[];manifest=[]
 def check(name,yes,**details):
  checks.append({'name':name,'status':'PASS' if yes else 'FAIL','evidence':'REAL_SERVER_EXECUTED',**details});save('checks.json',checks)
  assert yes,(name,details)
 async with httpx.AsyncClient(headers=headers,timeout=180) as http:
  from mcp_retry_transport import install
  install(http,out/'HTTP_RETRIES.jsonl')
  async with streamable_http_client(a.endpoint,http_client=http) as (rd,wr,_):
   async with ClientSession(TappedStream(rd,out/'wire.jsonl','server_to_client'),TappedStream(wr,out/'wire.jsonl','client_to_server')) as c:
    init=await c.initialize();listing=(await c.list_tools()).model_dump(mode='json');save('initialize.json',init.model_dump(mode='json'));save('tools.json',listing)
    old={t['name']:t for t in json.loads(a.baseline.read_text())['tools']};now={t['name']:t for t in listing['tools']}
    check('93 historical published tools byte-identical',len(old)==93 and all(now.get(n)==v for n,v in old.items()))
    check('only formal_nl_redecode additive',set(now)-set(old)=={'formal_nl_redecode'} and len(now)==94)
    async def call(name,args,error=False):
     r=await c.call_tool(name,args);v=r.structuredContent or json.loads(r.content[0].text)
     with (out/'transcript.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'arguments':args,'response':r.model_dump(mode='json')},ensure_ascii=False)+'\n')
     assert bool(r.isError)==error,(name,v)
     assert v.get('execution_permission') is not True
     return v.get('data',v)
    async def read(project,ref,view='result',tool='formal_nl_inspect'):
     parts=[];offset=0
     while True:
      v=await call(tool,{'project':project,'run_ref':ref,'view':view,'offset':offset,'limit':48})
      if v.get('encoding')!='base64':return v
      parts.append(base64.b64decode(v['data']))
      if v['next_offset'] is None:
       raw=b''.join(parts);assert hashlib.sha256(raw).hexdigest()==v['sha256'];return json.loads(raw)
      offset=v['next_offset']
    project='nl_independent_eval_20261107'
    A='8f0c58adc0dc4c3a7279203cce6be439d75de6c47ca5a690c468cf47eb9f793c'
    B='b09e3b06b9251b1ac3297023fa098fc3305fe3c02e34839402d4bee3d13118f2'
    C='076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46'
    old_c=await read(project,C);save('C_RECOVERED.json',old_c)
    check('old C completed actual receipt retained',old_c['receipt']['status']=='OK')
    rep=await read(project,C,'replay');save('C_REPLAY.json',rep);check('old C replay with zero model/network',rep['status']=='REPLAY_MATCH' and rep['LLM_calls']==rep['network_calls']==0)
    base=await read(project,A);traced=await read(project,B)
    refs=[{'engine':i['traces'][0]['engine'],'run_id':i['traces'][0]['run_id']} for i in traced['bundle']['items'][:5]]
    args={'project':project,'request_key':a.tag+':open','source_nl_run_ref':A,'source_item_indices':list(range(5)),'structural_run_refs':refs,'arms':list(ARMS),'policy':{**POLICY,'model_class':{'domain_sizes':[1,2,3],'max_models':530,'max_relation_cells':9}}}
    opened=await call('formal_nl_redecode',args);result=await read(project,opened['run_ref']);save('OPEN_RESULT.json',result);save('OPEN_BUNDLE.json',await read(project,opened['run_ref'],'bundle'))
    check('open hard frozen invariants',all(result['invariants'][k] is True for k in ['provider_request_equal','raw_output_equal','base_ast_equal']) and result['invariants']['model_calls_delta']==result['invariants']['network_calls']==0)
    scores=json.loads((ROOT/'docs/LM_NL_CAUSAL_DIAGNOSTIC_20261107/fixtures/AMBIGUITY_SCORES_PARTIAL.json').read_text())
    rows=[]
    for index,item in enumerate(result['items']):
     real=item['arms']['REAL_TRACE'];target=next(q for q in scores['source_rows'] if q['id']=='U'+str(21+index))
     # The archived score uses full AST SHA; evaluate only after generation.
     new=[x for x in real['candidates'] if x['structural_move'] and x['finite_relation']['different_models']==176 and x['finite_relation']['models_checked']==530]
     check('U'+str(21+index)+' actual frozen one-swap 176/530',bool(new) and all(x['primitive_reproduction']['cost']==1 for x in new))
     check('U'+str(21+index)+' exact published B wide SHA',any(x['candidate_ast_sha256']==target['wide_ast_sha256_B'] for x in new))
     check('U'+str(21+index)+' no incremental expressivity',item['incremental_status']=='NO_INCREMENTAL_STRUCTURAL_EXPRESSIVITY_ON_BOUND')
     check('U'+str(21+index)+' equal attempt ceilings',all(x['attempt_slots']==8 and len(x['attempts'])==8 for x in item['arms'].values()))
     rows.append({'id':'U'+str(21+index),'candidates':[{'sha256':x['candidate_ast_sha256'],'relation':x['finite_relation']['status'],'differences':176,'models':530,'primitive_cost':x['primitive_reproduction']['cost']} for x in new],'verdict':item['incremental_status']})
    save('OPEN_TABLE.json',rows);save('U26.json',{'id':'U26','status':'EXCLUDED_INVALID_ORACLE','reason':'Original oracle rejects a textually required shared journalist reading; retained unchanged in original archive. Not a new positive or hidden score.'})
    repeat=await call('formal_nl_redecode',args);check('idempotent exact record',repeat==opened)
    conflict=await call('formal_nl_redecode',{**args,'policy':{**args['policy'],'sham_seed':2212}},True);check('request key conflict',conflict['error']['code']=='REQUEST_KEY_CONFLICT')
    foreign='qa-nl003-foreign-'+a.tag
    await call('assurance_project_new',{'project':foreign,'request_key':'init'})
    attacks=[('foreign source',{'project':foreign}),('missing traces',{'structural_run_refs':[]}),('fake node',{'structural_run_refs':[{**refs[0],'node_refs':['0'*64]}],'source_item_indices':[0]}),('stale snapshot',{'structural_run_refs':[{**refs[0],'snapshot_sha256':'0'*64}],'source_item_indices':[0]}),('wrong source',{'structural_run_refs':[refs[1]],'source_item_indices':[0]}),('raw output injection',{'raw_output':'{"items":[]}'}),('duplicate index',{'source_item_indices':[0,0]})]
    for name,change in attacks:
     v=await call('formal_nl_redecode',{**args,'request_key':a.tag+':attack:'+name,**change},True)
     check(name+' fail closed',bool(v.get('error')),error=v['error']['code'])
    v=await call('formal_nl_inspect',{'project':project,'run_ref':opened['run_ref'],'view':'replay','expected_ast_sha256':'0'*64},True)
    check('forged expected AST fail closed',v['error']['code']=='REJECTED_PROVENANCE')
    replay=await read(project,opened['run_ref'],'replay');save('OPEN_REPLAY.json',replay);check('new frozen offline replay',replay['status']=='REPLAY_MATCH' and replay['LLM_calls']==0)
    check('old A immutable',await read(project,A)==base)
    manifest.append({'kind':'open','project':project,'run_ref':opened['run_ref'],'source_nl_run_ref':A})
    if a.holdout:
     corpus=json.loads((ROOT/'docs/nl-causal003/fixtures/PUBLIC_SOURCES.json').read_text())['sources'];protocol=json.loads((ROOT/'docs/nl-causal003/fixtures/PRECOMMIT.json').read_text())
     check('new holdout precommit preserved',all(hashlib.sha256((ROOT/'docs/nl-causal003/fixtures'/n).read_bytes()).hexdigest()==h for n,h in protocol['files'].items()))
     fresh=json.loads(a.holdout.read_text())
     for batch,entry in enumerate(fresh):
      qp=entry['request']['project'];receipt=entry['result']['receipt'];save('HIDDEN_PROVIDER_'+str(batch)+'.json',receipt)
      check('fresh source-only provider '+str(batch),receipt['status']=='OK' and receipt['tools_used']==0 and not any(i['structural_frames'] for i in receipt['request']['items']))
      hold_refs=[]
      for i,s in enumerate(corpus[batch*6:batch*6+6]):
       sy=await call('white_star_symbolic_explore',{'project':qp,'request_key':a.tag+':structural:'+s['id'],'request':symbolic(s,2211)})
       check('real structural source '+s['id'],sy['status']=='COMPLETED')
       hold_refs.append({'engine':'symbolic_v1','run_id':sy['run_id']})
      payload={'project':qp,'request_key':a.tag+':hidden:'+str(batch),'source_nl_run_ref':entry['run_ref'],'source_item_indices':list(range(len(receipt['request']['items']))),'structural_run_refs':hold_refs,'arms':list(ARMS),'policy':POLICY}
      rec=await call('formal_nl_redecode',payload);res=await read(qp,rec['run_ref']);save('HIDDEN_RESULT_'+str(batch)+'.json',res);save('HIDDEN_BUNDLE_'+str(batch)+'.json',await read(qp,rec['run_ref'],'bundle'))
      check('hidden zero provider calls '+str(batch),res['invariants']['model_calls_delta']==res['invariants']['network_calls']==0)
      check('hidden same frozen inputs '+str(batch),all(res['invariants'][k] for k in ['provider_request_equal','raw_output_equal','base_ast_equal']))
      rep=await read(qp,rec['run_ref'],'replay');save('HIDDEN_REPLAY_'+str(batch)+'.json',rep);check('hidden exact replay '+str(batch),rep['status']=='REPLAY_MATCH')
      check('hidden request repeat '+str(batch),(await call('formal_nl_redecode',payload))==rec)
      manifest.append({'kind':'hidden','project':qp,'run_ref':rec['run_ref'],'source_nl_run_ref':entry['run_ref']})
    save('MCP_RUN_MANIFEST.json',manifest)
    save('service_health.json',await call('service_health',{}));save('bridge_system_status.json',await call('bridge_system_status',{}))
    save('result.json',{'status':'PASS','checks':len(checks),'tools':94,'external_human_licensing':'HUMAN_NOT_EVALUATED','execution_permission':False})
    print('CAUSAL_MCP_PASS',len(checks),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--endpoint',required=True);p.add_argument('--loopback-port',type=int);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--tag',required=True);p.add_argument('--holdout',type=Path);asyncio.run(main(p.parse_args()))
