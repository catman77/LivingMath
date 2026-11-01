"""Real MCP/OAuth acceptance on private BackupAPI clones, with no production writes."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any, cast

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dav_acceptance import TappedStream
from dav_http_acceptance import LoopbackTransport
from unified_client_qa import authenticate
from .experiment import save


def backup(source: Path, destination: Path) -> None:
    with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as old,sqlite3.connect(destination) as new:old.backup(new)
    destination.chmod(0o600)


async def checks(url: str, token: str, out: Path, entries: list[dict]) -> dict:
    calls=[];invariants=[];ids=[]
    def require(name,ok):
        invariants.append({'invariant':name,'result':'PASS' if ok else 'FAIL'})
        save(out/'checks.json',invariants)
        if not ok:raise AssertionError(name)
    async with httpx.AsyncClient(headers={'Host':'livingmath.example','Authorization':'Bearer '+token},timeout=45) as client:
        async with streamable_http_client(url+'/mcp',http_client=client) as (read,send,_):
            async with ClientSession(cast(Any,TappedStream(read,out/'mcp-wire.jsonl','server_to_client')),
                cast(Any,TappedStream(send,out/'mcp-wire.jsonl','client_to_server'))) as session:
                init=await session.initialize();listing=await session.list_tools()
                save(out/'initialize.json',init.model_dump(mode='json'));save(out/'tools-list.json',listing.model_dump(mode='json'))
                names={t.name for t in listing.tools}
                require('REAL_REGISTERED_EXTENSION_AND_EXISTING_DAV',{'artifact_translation_propose','artifact_translation_check',
                    'artifact_translation_history','dav_register_adapter','dav_check_law'}<=names)
                require('PRIVATE_PROFILE_DOES_NOT_CLAIM_PRODUCTION_AUTOMATION',
                    init.serverInfo.name=='LivingMath Artifact Translation Private QA' and 'research_autonomy_status' not in names)
                async def call(name,arguments,error=False):
                    response=await session.call_tool(name,arguments)
                    calls.append({'tool':name,'arguments':arguments,'response':response.model_dump(mode='json')})
                    save(out/'mcp-transcript.json',calls)
                    require('RESPONSE_'+str(len(calls))+'_EXPECTED_ERROR' if error else 'RESPONSE_'+str(len(calls)),bool(response.isError)==error)
                    if error:return response
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
                project='LM_QA_ARTIFACT_T001'
                event=await call('record_result',{'project':project,'kind':'observation','focus':'Private translation acceptance',
                    'result':'Source-bound symbolic network QA only; no physical realization asserted.','status':'observation','request_key':'qa-source'})
                ids.append({'object':'canonical_QA_event','response':event})
                selected=[next(e for e in entries if e.get('gate')==1),next(e for e in entries if e.get('gate')==6),
                          next(e for e in entries if e['split']=='literary_train')]
                for index,entry in enumerate(selected):
                    args: dict[str,Any]={'project':project,'request':{'graph':entry['graph'],'max_candidates':12},'request_key':'propose-'+str(index)}
                    proposal=await call('artifact_translation_propose',args)
                    duplicate=await call('artifact_translation_propose',args)
                    require('PROPOSAL_IDEMPOTENCY_'+str(index),proposal==duplicate)
                    require('PROPOSE_DOES_NOT_VERIFY_OR_GRANT_'+str(index),proposal['payload']['status']=='PROPOSED' and
                        proposal['payload']['execution_permission']=={'allowed':False})
                    candidate=next(c for c in proposal['payload']['proposals']['candidates'] if c['edit']=='transition')
                    ca: dict[str,Any]={'project':project,'proposal_id':proposal['id'],'candidate_id':candidate['candidate_id'],
                        'request_key':'check-'+str(index),'max_laws':24}
                    checked=await call('artifact_translation_check',ca);payload=checked['payload']
                    require('SOURCE_REVERSE_AND_DAV_REGISTRATION_'+str(index),payload['status']=='FORMAL_TRANSLATION_VALID' and
                        payload['registration']['payload']['metadata']['spec']['kind']=='reaction_network')
                    registration=payload['registration'];positive=next(l for l in payload['laws'] if l['nontrivial'])
                    law_args={'project':project,'registration_id':registration['id'],'adapter_binding':registration['payload']['binding'],
                        'formula':positive['formula'],'persist':True,'request_key':'law-'+str(index)}
                    law=await call('dav_check_law',law_args)
                    require('EXISTING_DAV_EXACT_SCOPED_EVIDENCE_'+str(index),law['payload']['status']=='proved' and
                        law['payload']['proof_status']=='unverified' and law['payload']['execution_permission']=={'allowed':False})
                    export=await call('dav_export_evidence',{'project':project,'evidence_id':law['id']})
                    require('CURRENT_PINNED_EVIDENCE_'+str(index),export['certificate_current'])
                    require('RESULT_REPEAT_NO_DUPLICATE_'+str(index),law==await call('dav_check_law',law_args))
                    ids.append({'source':entry['name'],'proposal_id':proposal['id'],'check_id':checked['id'],
                                'registration_id':registration['id'],'law_evidence_id':law['id'],'candidate_id':candidate['candidate_id']})
                    if index==0:
                        bad=next(c for c in proposal['payload']['proposals']['candidates'] if c['edit']=='merge_roles')
                        ba={**ca,'candidate_id':bad['candidate_id'],'request_key':'reject-merged'}
                        rejected=await call('artifact_translation_check',ba)
                        require('REJECTED_FIDELITY_NEVER_REGISTERS',rejected['payload']['status']=='FAIL_FIDELITY' and
                            rejected['payload']['registration'] is None)
                        fixed=await call('artifact_translation_check',{**ba,'request_key':'repair-merged','repair_on_conflict':True})
                        require('REPAIR_RETAINS_ORIGINAL_CONFLICT',fixed['payload']['original_check']['status']=='FAIL_FIDELITY' and
                            fixed['payload']['effective_check']['status']=='FORMAL_TRANSLATION_VALID' and fixed['payload']['repair']['original_result_retained'])
                        await call('artifact_translation_check',{**ca,'project':'LM_QA_OTHER','request_key':'foreign-proposal'},error=True)
                        await call('artifact_translation_propose',{**args,'request':{**args['request'],'expected_answer':True}},error=True)
                        forged_graph=json.loads(json.dumps(entry['graph']))
                        forged_graph['nodes'][0]['source_refs']=['nonexistent-source-span']
                        await call('artifact_translation_propose',{**args,'request_key':'forged-source',
                            'request':{**args['request'],'graph':forged_graph}},error=True)
                        await call('artifact_translation_propose',{**args,'request_key':'propose-'+str(index),
                            'request':{**args['request'],'max_candidates':1}},error=True)
                        await call('artifact_translation_propose',{**args,'project':'RH','request_key':'forbidden-RH'},error=True)
                        changed={**law_args,'formula':{'body':{'tag':'eq','left':{'tag':'apply','operation':'One','argument':{'tag':'var'}},
                            'right':{'tag':'apply','operation':'Zero','argument':{'tag':'var'}}}}}
                        await call('dav_check_law',changed,error=True)
                history=await call('artifact_translation_history',{'project':project,'limit':20})
                require('APPEND_ONLY_HASH_CHAIN_OK',history['integrity']['ok'])
                foreign=await call('artifact_translation_history',{'project':'LM_QA_OTHER'})
                require('OTHER_PROJECT_HISTORY_EMPTY',foreign['total']==0)
                health=await call('service_health',{});save(out/'health.json',health)
                require('CANONICAL_SQLITE_AUDIT_OK',health['sqlite_integrity']=='ok' and health['audit']['ok'])
                save(out/'object-ids.json',ids)
                return {'status':'PASS_REAL_PRIVATE_OAUTH_MCP','tool_count':len(listing.tools),'calls':len(calls),
                    'checks':invariants,'objects':ids,'production_writes':0,'scope':'PRIVATE_BACKUP_CLONES_STAGING_ONLY',
                    'proof_status':'unverified','execution_permission':{'allowed':False}}


def run(root: Path, private: Path, out: Path, snapshots: Path | None = None) -> dict:
    private.mkdir(parents=True,exist_ok=False,mode=0o700);out.mkdir(parents=True,exist_ok=True)
    if snapshots is None:
        seed=private/'seed';seed.mkdir(mode=0o700)
        from research_store import ResearchStore
        from davcore.storage import Store
        ResearchStore(seed/'canonical-before.sqlite3');Store(seed/'dav-before.sqlite3')
        snapshots=seed
    receipt: dict[str,Any]={'purpose':'ARTIFACT_TRANSLATION001_PRIVATE_BACKUP_CLONES'}
    for role,name in [('canonical','research.sqlite3'),('dav','dav.sqlite3')]:
        src=snapshots/(role+'-before.sqlite3');dest=private/name;backup(src,dest)
        receipt[role]={'source':str(src.resolve()),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
                       'inode':dest.stat().st_ino}
    if (snapshots/'oauth-before.sqlite3').exists():backup(snapshots/'oauth-before.sqlite3',private/'oauth.sqlite3')
    save(private/'clone-receipt.json',receipt);(private/'clone-receipt.json').chmod(0o600)
    (private/'qa-password').write_text(secrets.token_urlsafe(30));(private/'qa-password').chmod(0o600)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.startswith('LIVE_MATH_')};env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-B','-m','artifact_translation.staging','--root',str(private),
             '--source-root',str(root),
             '--port',str(port)]
    code=Path(__file__).resolve().parent.parent
    with (out/'server.log').open('w') as log:
        server=subprocess.Popen(command,cwd=code,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url='https://livingmath.example',transport=LoopbackTransport(port)) as client:
                for _ in range(100):
                    try:
                        if client.get('/healthz').status_code==200:break
                    except httpx.ConnectError:pass
                    if server.poll() is not None:raise RuntimeError('PRIVATE_QA_SERVER_STARTUP_FAILED')
                    time.sleep(.05)
                else:raise RuntimeError('PRIVATE_QA_SERVER_STARTUP_TIMEOUT')
                if client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code!=401:
                    raise AssertionError('ANONYMOUS_MCP_NOT_DENIED')
            oauth=authenticate('https://livingmath.example',private/'qa-password',private/'private-oauth.json',port)
            result=asyncio.run(checks('http://127.0.0.1:'+str(port),oauth['token']['access_token'],out,
                json.loads((root/'frozen/graphs.json').read_text())))
            result['anonymous_denied']=True;result['source_mode']='PRODUCTION_BACKUP_API_CLONES' if snapshots.name!='seed' else 'CLEAN_FIXTURE_BACKUP_API_CLONES'
            save(out/'result.json',result);return result
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--private-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--snapshots',type=Path)
    a=p.parse_args();result=run(a.root.resolve(),a.private_root.resolve(),a.out.resolve(),a.snapshots.resolve() if a.snapshots else None)
    print(json.dumps({'status':result['status'],'calls':result['calls'],'checks':len(result['checks'])}))
