"""Public HTTPS/OAuth SDK QA. Requires a preloaded, scoped real six-reading QA project."""
import argparse,asyncio,base64,json,sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def save(path,value):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


async def run(a):
    from lm_suti_assurance.core import canonical
    sys.path.insert(0,str(a.legacy_client));sys.path.insert(0,str(Path(__file__).parent))
    from unified_client_qa import authenticate
    from dav_acceptance import TappedStream
    from semantic_bridge_pilot import CHALLENGES
    a.private.mkdir(mode=0o700,parents=True,exist_ok=True);a.out.mkdir(mode=0o700,parents=True,exist_ok=False)
    tokenfile=a.private/'oauth.private.json';auth=json.loads(tokenfile.read_text()) if tokenfile.exists() else authenticate(a.origin,a.password_file,tokenfile)
    checks=[];calls=[]
    def check(name,ok):
        checks.append({'id':name,'status':'PASS' if ok else 'FAIL'});save(a.out/'checks.json',checks)
        if not ok:raise AssertionError(name)
    async with httpx.AsyncClient(timeout=60) as http:
        r=await http.post(a.origin+'/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'},headers={'Accept':'application/json,text/event-stream'})
        check('HTTPS_WITHOUT_OAUTH_DENIED',r.status_code==401)
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+auth['token']['access_token']},timeout=180) as http:
        async with streamable_http_client(a.origin+'/mcp',http_client=http) as (read,write,_):
            async with ClientSession(TappedStream(read,a.out/'wire.jsonl','server_to_client'),TappedStream(write,a.out/'wire.jsonl','client_to_server')) as client:
                init=await client.initialize();listing=await client.list_tools();save(a.out/'initialize.json',init.model_dump(mode='json'));save(a.out/'tools-list.json',listing.model_dump(mode='json'))
                before=json.loads(a.baseline.read_text())['tools'];after={t.name:t.model_dump(mode='json') for t in listing.tools}
                check('OLD_55_INPUT_SCHEMAS_PRESERVED',len(before)==55 and all(t['name'] in after and after[t['name']]['inputSchema']==t['inputSchema'] for t in before))
                check('64_REAL_TOOLS_AND_V02',len(after)==64 and init.serverInfo.version=='v0.2.0-developer-preview')
                async def call(name,params):
                    if 'request_key' in params:params={**params,'request_key':a.run_key+':'+params['request_key']}
                    r=await client.call_tool(name,params);calls.append({'tool':name,'request':params,'response':r.model_dump(mode='json')});save(a.out/'mcp-transcript.json',calls)
                    if r.isError:raise AssertionError('TOOL_ERROR:'+name+':'+str(r.content))
                    return r.structuredContent if r.structuredContent is not None else json.loads(r.content[0].text)
                doctor=await call('assurance_doctor',{});check('FROZEN_VERIFIER_UNCHANGED',doctor['verifier_digest']=='a035303149c1307126ff26e4bf60725daf3b104598be8a04a958e14388a61f08')
                health=await call('service_health',{});save(a.out/'health.json',health)
                check('LEGACY_INTEGRITY_AND_CHAIN',health['sqlite_integrity']=='ok' and health['audit']['ok'] and health['event_count']==2058)
                contract=await call('semantic_contract',{});check('STRICT_SCHEMAS_AND_HUMAN_GATE',len(contract['schemas'])>=6 and contract['R3']=='PENDING' and contract['execution_permission'] is False)
                check('OWNER_PIPE_CONFIGURED',contract['hosted_backend']=='OWNER_PIPE_CODEX_CHATGPT')
                report=await call('semantic_report',{'project':a.project});save(a.out/'dossier-before.json',report)
                models=[r for r in report['frames'] if r['value']['generation_mode']=='HOSTED_MODEL'];check('SIX_GENUINE_PRELOADED_MODEL_FRAMES',len(models)==6)
                check('SOURCE_ANCHORS_AND_ALTERNATIVES',all(len(r['value']['counterreadings'])>=1 for r in models) and len(report['anchors'])>=6)
                editions={r['ref']:r['value'] for r in report['editions']};first=next(r for r in models if r['value']['revision_index']==1 and editions[r['value']['poem_ref']]['source_id']=='blok_night_1960')
                fresh=await call('semantic_draft',{'project':a.project,'edition_ref':first['value']['poem_ref'],'request_key':'mcp-real-cache-initial'})
                check('REAL_OWNER_PIPE_SOURCE_CONTEXT_CACHE',fresh.get('frame_ref')==first['ref'] and fresh.get('model_status')=='OK' and fresh.get('model_attempt_created') is False)
                revised=await call('semantic_revise',{'project':a.project,'frame_ref':first['ref'],'challenge':CHALLENGES['blok_night_1960'],'request_key':'mcp-real-cache-revise'})
                child=next(r for r in models if r['value']['poem_ref']==first['value']['poem_ref'] and r['value']['revision_index']==2)
                check('REAL_REVISION_LINEAGE_AND_CACHE_NO_NEW_MODEL_ATTEMPT',revised.get('frame_ref')==child['ref'] and revised.get('model_attempt_created') is False)
                again=await call('semantic_revise',{'project':a.project,'frame_ref':first['ref'],'challenge':CHALLENGES['blok_night_1960'],'request_key':'mcp-real-cache-revise'})
                check('RETRY_REUSES_SAME_FRAME',again.get('frame_ref')==revised.get('frame_ref'))
                conflict=await call('semantic_revise',{'project':a.project,'frame_ref':first['ref'],'challenge':'A changed diagnostic request','request_key':'mcp-real-cache-revise'})
                check('CHANGED_REQUEST_KEY_CONFLICT',conflict.get('reason_code')=='REQUEST_KEY_CONFLICT')
                fixtures=[r for r in report['frames'] if r['value']['generation_mode']=='FIXTURE'];check('MANUAL_CONTROLS_SEPARATE_FROM_MODELS',len(fixtures)==2)
                q=[{'id':'order','kind':'STRUCTURAL_FIELD','field':'/image_order','question':'Declared image order'}, {'id':'canal','kind':'STRUCTURAL_FIELD','field':'/canal_details','question':'Declared canal details'}]
                spec={'fields':['/image_set'],'declared_Q':q,'complete':True,'expectation':'REPORT'}
                args={'project':a.project,'left_ref':fixtures[0]['ref'],'right_ref':fixtures[1]['ref'],'projection_json':canonical(spec),'request_key':'mcp-loss'}
                loss=await call('semantic_compare',args);check('ACTUAL_STRUCTURAL_LOSS',loss['status']=='LOSS_DETECTED')
                rejected=await call('semantic_compare',{**args,'projection_json':canonical({**spec,'expectation':'PRESERVED_FOR_DECLARED_Q'}),'request_key':'mcp-false-preservation'})
                check('FALSE_PRESERVATION_REJECTED',rejected['status']=='REJECTED')
                no_loss=await call('semantic_compare',{**args,'projection_json':canonical({**spec,'fields':['/image_set','/image_order','/canal_details']}),'request_key':'mcp-full-Q'})
                check('FULL_Q_NO_FALSE_LOSS',no_loss['status']=='PRESERVED_FOR_DECLARED_Q')
                bad=await call('semantic_draft',{'project':a.project,'edition_ref':first['value']['poem_ref'],'request_key':'mcp-false-quote','proposal_json':canonical({'source_sha256':'0'*64,'execution_permission':True})})
                check('MODEL_CANNOT_FORGE_SOURCE_HASH_OR_EXECUTION',bad['status']=='FRAME_UNTRUSTED')
                private=await call('semantic_export',{'project':a.project,'audience':'private','include_source_bytes':True})
                check('AUTHORIZED_EXPORT',private['status']=='EXPORTED');(a.out/'demo_poetry_private.zip').write_bytes(base64.b64decode(private['bundle_base64']))
                direct=await call('semantic_replay',{'project':a.project,'bundle_ref':private['bundle_ref'],'engine':'direct'});compiled=await call('semantic_replay',{'project':a.project,'bundle_ref':private['bundle_ref'],'engine':'compiled'})
                check('REAL_MCP_OFFLINE_BOTH_ENGINES',direct['status']==compiled['status']=='PASS' and direct['logical_digest']==compiled['logical_digest'])
                missing=await call('semantic_export',{'project':a.project,'audience':'private','include_source_bytes':False})
                denied=await call('semantic_replay',{'project':a.project,'bundle_ref':missing['bundle_ref']})
                check('EXCLUDED_BYTES_MISSING_DEPENDENCY',denied.get('reason_code')=='MISSING_SOURCE_DEPENDENCY')
                public=await call('semantic_export',{'project':a.project,'audience':'public'})
                check('PUBLIC_CORPUS_NOT_SILENTLY_PUBLISHED',bool(public.get('manifest',{}).get('source_dependencies')))
                newreport=await call('semantic_report',{'project':a.project});save(a.out/'dossier-after.json',newreport)
                check('NO_DUPLICATE_MODEL_READING_OR_FALSE_VERIFICATION',len([r for r in newreport['frames'] if r['value']['generation_mode']=='HOSTED_MODEL'])==6 and all(c['value']['epistemic_status']=='UNKNOWN' for c in newreport['assurances']))
                check('R3_REMAINS_PENDING',newreport['dossier']['R3']=='PENDING')
                withdrawn=await call('semantic_withdraw',{'project':a.project,'frame_ref':fixtures[0]['ref'],'reason':'Dedicated QA withdrawal; retain original annotation and all witnesses.','request_key':'mcp-withdraw'})
                check('APPEND_ONLY_WITHDRAWAL',withdrawn['status']=='FRAME_WITHDRAWN')
                result={'status':'PASS','origin':a.origin,'public_HTTPS_verified':True,'OAuth':'REAL_OWNER_PKCE','tools':len(after),'checks':checks,'new_model_attempts':0,'cached_real_model_outputs_reused':True,'project':a.project,'logical_digest':direct['logical_digest'],'deployment_id':health['deployment_id']}
                save(a.out/'result.json',result);print(json.dumps({k:result[k] for k in ('status','origin','tools','new_model_attempts')}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('private','out','password-file','legacy-client','baseline'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--origin',required=True);p.add_argument('--project',default='semantic-poetry-001');p.add_argument('--run-key',default='qa1');a=p.parse_args();asyncio.run(run(a))
