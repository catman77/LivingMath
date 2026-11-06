"""Actual authenticated MCP acceptance for rehearsal or the existing public endpoint."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import stat
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs, urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from dav_acceptance import TappedStream
from dav_http_acceptance import LoopbackTransport
from davcore.ast import implication


def authenticate(origin: str, password_file: Path, token_path: Path, loopback_port=None):
    transport=LoopbackTransport(loopback_port) if loopback_port else None
    with httpx.Client(base_url=origin,transport=transport,timeout=30,follow_redirects=False) as client:
        callback='https://chatgpt.com/connector/oauth/livingmath-unified-qa'
        existing=os.environ.get('LIVINGMATH_QA_CLIENT_FILE')
        if existing:
            credential=Path(existing);info=credential.stat()
            if credential.is_symlink() or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
                raise ValueError('OWNER_ONLY_QA_CLIENT_REQUIRED')
            registration=json.loads(credential.read_text())['client']
            if callback not in registration['redirect_uris']:
                raise ValueError('QA_CLIENT_CALLBACK_MISMATCH')
        else:
            r=client.post('/register',json={'client_name':'Owner unified MCP QA','redirect_uris':[callback],
                'grant_types':['authorization_code','refresh_token'],'response_types':['code'],
                'token_endpoint_auth_method':'client_secret_post','scope':'research'})
            if r.status_code!=201:raise RuntimeError('QA_OAUTH_REGISTRATION_FAILED:'+str(r.status_code))
            registration=r.json()
        verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        r=client.get('/authorize',params={'client_id':registration['client_id'],'redirect_uri':callback,
            'response_type':'code','code_challenge':challenge,'code_challenge_method':'S256','scope':'research',
            'resource':origin+'/mcp','state':'owner-qa'})
        if r.status_code not in (302,303,307):raise RuntimeError('QA_OAUTH_AUTHORIZE_FAILED')
        login=r.headers['location'];page=client.get(login)
        if page.status_code!=200:raise RuntimeError('QA_LOGIN_PAGE_FAILED')
        request_id=parse_qs(urlparse(login).query)['request'][0]
        r=client.post('/login',data={'request':request_id,'password':password_file.read_text().strip()},headers={'Origin':origin})
        if r.status_code!=303:raise RuntimeError('QA_OWNER_LOGIN_FAILED:'+str(r.status_code))
        code=parse_qs(urlparse(r.headers['location']).query)['code'][0]
        r=client.post('/token',data={'grant_type':'authorization_code','client_id':registration['client_id'],
            'client_secret':registration['client_secret'],'code':code,'code_verifier':verifier,'redirect_uri':callback,'resource':origin+'/mcp'})
        if r.status_code!=200:raise RuntimeError('QA_TOKEN_EXCHANGE_FAILED')
        data={'token':r.json(),'client':registration,'origin':origin}
        token_path.write_text(json.dumps(data));token_path.chmod(0o600)
        return data


async def run(args):
    args.out.mkdir(parents=True,exist_ok=False)
    token_file=args.token_file or args.out/'private-oauth.json'
    data=json.loads(token_file.read_text()) if token_file.exists() else authenticate(args.origin,args.password_file,token_file,args.loopback_port)
    if data['origin']!=args.origin:raise ValueError('OAUTH_TOKEN_ORIGIN_MISMATCH')
    headers={'Authorization':'Bearer '+data['token']['access_token']}
    if args.loopback_port:headers['Host']='livingmath.example'
    calls=[];checks=[]
    def save(name,value):(args.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    def check(name,ok):
        checks.append({'invariant':name,'result':'PASS' if ok else 'FAIL'});save('checks.json',checks)
        if not ok:raise AssertionError(name)
    async with httpx.AsyncClient(headers=headers,timeout=45) as http:
        async with streamable_http_client(args.endpoint,http_client=http) as (read,send,_):
            async with ClientSession(TappedStream(read,args.out/'mcp-wire.jsonl','server_to_client'),
                                     TappedStream(send,args.out/'mcp-wire.jsonl','client_to_server')) as session:
                init=await session.initialize();listing=await session.list_tools()
                save('initialize.json',init.model_dump(mode='json'));save('tools-list.json',listing.model_dump(mode='json'))
                async def call(name,params,error=False,denied=False):
                    response=await session.call_tool(name,params)
                    calls.append({'tool':name,'arguments':params,'response':response.model_dump(mode='json')});save('mcp-transcript.json',calls)
                    if error:
                        check('REJECTION_'+name+'_'+str(len(calls)),response.isError);return None
                    if denied:
                        check('EXPECTED_OPERATOR_DENIAL',response.isError)
                    elif response.isError:raise AssertionError((name,response))
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
                health=await call('service_health',{});contract=await call('research_contract',{})
                save('health.json',health);save('contract.json',contract)
                if args.catalog_only:
                    result={'status':'BASELINE_CATALOG_CAPTURED','tool_count':len(listing.tools),'health':health}
                    save('result.json',result);return result
                check('UNIFIED_SERVER_INFO',init.serverInfo.version=='1.1.0-unified.1')
                check('REAL_TOOLS_LIST_44',len(listing.tools)==44)
                check('HEALTH_VERSION_AND_DATA',health['version']=='1.1.0-unified.1' and health['audit']['ok'] and health['sqlite_integrity']=='ok')
                if args.baseline:
                    original=json.loads(args.baseline.read_text())['tools'];now={x.name:x.model_dump(mode='json') for x in listing.tools}
                    check('ALL_27_PREVIOUS_INPUT_SCHEMAS_PRESERVED',all(old['name'] in now and now[old['name']]['inputSchema']==old['inputSchema'] for old in original))
                # Exercise the preserved source-normalization path on one isolated ledger QA event.
                event=await call('record_result',{'project':args.project,'kind':'source','focus':'Unified API normalization check',
                    'result':json.dumps({'claim_type':'SOURCE_CLAIM','statement':'Dedicated QA input; not a mathematical proof.'}),
                    'status':'observation','request_key':args.project+':unified-normalizer-source'})
                frontier=await call('research_frontier',{'project':args.project})
                obligation=next((x for x in frontier['obligations'] if x['scope']=='unified-qa-normalization'),None)
                if obligation is None:
                    obligation=await call('research_obligation_create',{'project':args.project,'statement':'Read-only QA source normalization',
                        'scope':'unified-qa-normalization','source_event_ids':[event['id']]})
                normalized=await call('research_normalize_preview',{'project':args.project,'focus':'Read the exact QA source with existing normalizer',
                    'source_event_ids':[event['id']],'query_scope':{'level':'C2','obligation_id':obligation['id'],'version':obligation['version'],
                        'scope':obligation['scope'],'candidates':[{'id':'unified-source','root_ref':'event:'+str(event['id']),
                            'project':args.project,'scope':obligation['scope'],'version':obligation['version']}]}})
                check('EXISTING_NORMALIZER_REMAINS_OPERATIONAL',normalized['status']=='COMPLETE')
                status=await call('bridge_system_status',{})
                check('BRANDED_COMBINED_SYSTEM',status['name']=='SUTI-Bridge-LivingMath' and status['tool_count']==44)
                catalog=await call('bridge_catalog',{})
                check('REAL_SUTI_AND_ALCH006_SOURCES',set(r['source_id'] for r in catalog['sources'])=={'P1-001','P1-002','ALCH006'})
                for source in ['P1-001','P1-002']:
                    pair=await call('bridge_inspect',{'source_id':source,'view':'pair'})
                    result=await call('bridge_validate_records',{'source_id':source})
                    check('ORIGINAL_SOURCE_SCHEMA_PAIR_'+source,all(r['valid'] for r in result['record_checks']) and bool(result['projection_collisions']))
                    fields=pair['data']['observer']['fields']+[pair['data']['distinguished_field']]
                    result=await call('bridge_validate_records',{'source_id':source,'projection_fields':fields})
                    check('SOURCE_DISTINCTION_RESTORED_'+source,not result['projection_collisions'])
                model=await call('bridge_inspect',{'source_id':'ALCH006','view':'uncertainty','limit':2})
                check('ALCHEMY_UNKNOWNS_PRESERVED',model['total']==60)
                r=await call('dav_register_adapter',{'project':args.project,'spec':{'kind':'graph'},'request_key':'graph-qa'})
                result=await call('dav_check_law',{'project':args.project,'registration_id':r['id'],'adapter_binding':r['payload']['binding'],
                    'formula':implication('S0','S2','P','Q').model_dump(),'backend':'smt'})
                check('DAV_DIRECT_SMT_REAL_ENDPOINT',result['status']=='proved' and result['proof_status']=='unverified')
                request={'project':args.project,'request_key':'first-public-alchemy'}
                started=await call('bridge_run_alchemy',request);duplicate=await call('bridge_run_alchemy',request)
                check('ONE_CALL_ALCHEMY_AND_IDEMPOTENCY',started==duplicate and started['original_law_status']=='refuted')
                start=time.monotonic();cases=[]
                while time.monotonic()-start<90:
                    cases=[];offset=0
                    while True:
                        view=await call('research_autonomy_status',{'project':args.project,'offset':offset,'limit':20})
                        cases.extend(view['cases'])
                        if view['next_offset'] is None:break
                        offset=view['next_offset']
                    if len(cases)==45 and all(c['status'] in {'COMPLETED','WAITING_FOR_INPUT'} for c in cases):break
                    await asyncio.sleep(0.5)
                save('automatic-cases.json',cases)
                check('ALCHEMY_AUTOMATIC_45_CASES',len(cases)==45 and all(c['status'] in {'COMPLETED','WAITING_FOR_INPUT'} for c in cases))
                check('P_TO_PQ_AUTOMATIC',any(c['result'].get('observer_mask')==3 and c['status']=='COMPLETED' for c in cases))
                check('ORIGINAL_P1_Q0_RETAINED',any(c['result'].get('outcome')=='LAW_REFUTED' and c['result']['counterexample']['state']==1 for c in cases))
                check('43_SOURCE_REQUIREMENTS_EXPLICIT',sum(c['status']=='WAITING_FOR_INPUT' for c in cases)==43)
                check('NO_VERIFIED_OR_EXTERNAL_GRANTS',all(c['proof_status']=='unverified' and c['execution_permission']=={'allowed':False} for c in cases))
                denied=await call('transition_research_move',{'project':args.project,'move_id':1,'action':'activate_experiment','request_key':'forbidden-activation'},denied=True)
                # Accepted RC020 returns an explicit DENIED envelope inside a protocol response.
                check('LEGACY_OPERATOR_BOUNDARY_RETAINED',denied.get('status')=='DENIED' and denied['execution_permission']=={'allowed':False})
                await call('bridge_run_alchemy',{'project':'RH','request_key':'refuse-existing-project'},error=True)
                final=await call('service_health',{});save('health-final.json',final)
                result={'status':'PASS_REAL_UNIFIED_MCP','endpoint':args.endpoint,'project':args.project,'tool_count':44,
                    'checks':checks,'tool_calls':len(calls),'scientific_proof_status':'unverified','execution_permission':{'allowed':False}}
                save('result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--origin',required=True)
    p.add_argument('--password-file',type=Path,default=Path.home()/'.config/livingmath/login-password')
    p.add_argument('--token-file',type=Path);p.add_argument('--loopback-port',type=int);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--project',default='BRIDGE_QA_UNIFIED_CHATGPT');p.add_argument('--catalog-only',action='store_true');p.add_argument('--baseline',type=Path)
    args=p.parse_args();r=asyncio.run(run(args));print(json.dumps({'status':r['status'],'tools':r.get('tool_count')}))
