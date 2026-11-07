"""P0 attacks through a real authenticated MCP client; no provider calls for attacks."""
import argparse,asyncio,base64,copy,json,sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'live_math_mcp_prod'))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream

async def main(a):
 out=a.output;out.mkdir(mode=0o700,parents=True,exist_ok=True);checks=[];save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 data=json.loads(a.candidates.read_text());first=data['B'][0];payload=copy.deepcopy(first['request']);project=payload['project'];one=payload['items'][0];run=first['run_ref'];numeric_ref=one['structural_run_refs'][0]
 auth=authenticate(a.origin,Path.home()/'.config/livingmath/login-password',out/'oauth.private.json',a.loopback_port);headers={'Authorization':'Bearer '+auth['token']['access_token']}
 if a.loopback_port:headers['Host']='livingmath.example'
 async with httpx.AsyncClient(headers=headers,timeout=120) as http:
  from mcp_retry_transport import install
  install(http,out/'HTTP_RETRIES.jsonl')
  async with streamable_http_client(a.endpoint,http_client=http) as (rd,wr,_):
   async with ClientSession(TappedStream(rd,out/'wire.jsonl','server_to_client'),TappedStream(wr,out/'wire.jsonl','client_to_server')) as c:
    await c.initialize();tools=await c.list_tools();save('tools.json',tools.model_dump(mode='json'))
    async def call(name,args,error=False):
     r=await c.call_tool(name,args);v=r.structuredContent or json.loads(r.content[0].text)
     with (out/'transcript.jsonl').open('a') as f:f.write(json.dumps({'tool':name,'arguments':args,'response':r.model_dump(mode='json')},ensure_ascii=False)+'\n')
     if bool(r.isError)!=error:raise AssertionError((name,v))
     return v
    attacks=[]
    for name,changes in [('unknown_run',{'run_id':'0'*64}),('unknown_frame',{'frame_ids':['F99']}),('changed_coordinates_input',{'input_sha256':'0'*64}),('stale_snapshot',{'snapshot_sha256':'0'*64})]:
     item={**one,'structural_run_refs':[{**numeric_ref,**changes}]};attacks.append((name,item))
    attacks.append(('source_sha',{**one,'expected_source_sha256':'0'*64}))
    wrongsource=payload['items'][1];attacks.append(('different_real_source',{**one,'source_ref':wrongsource['source_ref'],'expected_source_sha256':wrongsource['expected_source_sha256']}))
    for name,item in attacks:
     args={**payload,'request_key':'attack:'+name,'items':[item]};v=await call('formal_nl_propose',args,True);code=v['error']['code'];checks.append({'name':name,'status':'PASS' if code in ['UNBACKED_ORIGIN','SOURCE_BINDING_MISMATCH','REJECTED_PROVENANCE'] else 'FAIL','error':code,'provider_calls':0})
    foreign='qa-nl002-foreign-'+a.tag
    await call('assurance_project_new',{'project':foreign,'request_key':'init'})
    v=await call('formal_nl_propose',{**payload,'project':foreign,'request_key':'foreign','items':[one]},True);checks.append({'name':'foreign_project_source_ref','status':'PASS' if v['error']['code']=='NOT_FOUND' else 'FAIL','error':v['error']['code']})
    v=await call('formal_nl_inspect',{'project':project,'run_ref':run,'view':'result','expected_ast_sha256':'0'*64},True);checks.append({'name':'forged_ast_sha','status':'PASS' if v['error']['code']=='REJECTED_PROVENANCE' else 'FAIL'})
    v=await call('formal_nl_propose',{**payload,'policy':{**payload['policy'],'seed':payload['policy']['seed']+1}},True);checks.append({'name':'request_key_payload_substitution','status':'PASS' if v['error']['code']=='REQUEST_KEY_CONFLICT' else 'FAIL'})
    # Explicit import remains a declaration; this is not the verified trace path.
    oldc=first['result']['items'][0]['candidates'][0]
    f=(await call('formal_interpret',{'project':project,'request_key':'legacy-fake:'+a.tag,'source_ref':one['source_ref'],'target_signature':one['target_signature'],'candidate_provider':{'kind':'white_star','provenance':{'run_id':'0'*64,'frame_id':'F99'}},'proposals':[{'formula_ast':oldc['formula_ast'],'assumptions':[],'token_role_links':oldc['token_role_links'],'construction_trace':[{'declaration_only':True}]}]}))['data']
    v=(await call('formal_inspect',{'project':project,'run_ref':f['run_ref'],'view':'candidates'}))['data'];checks.append({'name':'legacy_import_declaration_only','status':'PASS' if v['items'][0]['semantic_alignment_status']=='PROPOSED' and v['items'][0]['proof_status']=='PROPOSED' else 'FAIL','run_ref':f['run_ref']})
    health=await call('service_health',{});save('service_health.json',health)
    save('PROVENANCE_ATTACK_MATRIX.json',checks);save('result.json',{'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','checks':len(checks),'execution_permission':False})
    assert all(x['status']=='PASS' for x in checks),checks

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--endpoint',required=True);p.add_argument('--loopback-port',type=int);p.add_argument('--candidates',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--tag',required=True);asyncio.run(main(p.parse_args()))
