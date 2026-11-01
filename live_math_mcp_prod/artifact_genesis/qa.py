"""Existing MCP methods only, with real IDs and the accepted private clone launcher."""
import argparse
import json
from pathlib import Path
from typing import Any,cast

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dav_acceptance import TappedStream
from artifact_translation import qa as existing_qa
from davcore.ast import implication
from .source import save,SourceVault
from .audit import source_audit
from .binding import synthetic_control


async def exercise(url,token,out,root,experiment):
    checks=[];calls=[];ids=[];vault=SourceVault(root)
    raw_h=[json.loads(line) for line in (experiment/'candidate-source-relations.jsonl').read_text().splitlines()]
    targets=[json.loads(line) for line in (experiment/'target-bindings.jsonl').read_text().splitlines()]
    selected=[b for b in targets if b['revision']['kind']=='BINDING_REPAIR'][:2]
    def require(name,ok):
        checks.append({'invariant':name,'result':'PASS' if ok else 'FAIL'});save(out/'checks.json',checks)
        if not ok:raise AssertionError(name)
    project='LM_QA_GENESIS_002'
    async with httpx.AsyncClient(headers={'Host':'livingmath.example','Authorization':'Bearer '+token},timeout=30) as http:
        async with streamable_http_client(url+'/mcp',http_client=http) as (read,send,_):
            async with ClientSession(cast(Any,TappedStream(read,out/'mcp-wire.jsonl','server_to_client')),
                cast(Any,TappedStream(send,out/'mcp-wire.jsonl','client_to_server'))) as session:
                init=await session.initialize();listing=await session.list_tools();save(out/'initialize.json',init.model_dump(mode='json'))
                save(out/'tools-list.json',listing.model_dump(mode='json'));names={t.name for t in listing.tools}
                require('REAL_EXISTING_SCHEMA',{'record_result','dav_register_adapter','dav_check_law','dav_export_evidence','service_health'}<=names)
                require('NO_NEW_GENESIS_METHOD_INSTALLED',not any(n.startswith('genesis_') for n in names))
                async def call(name,args,error=False):
                    response=await session.call_tool(name,args);calls.append({'tool':name,'arguments':args,'response':response.model_dump(mode='json')})
                    save(out/'mcp-transcript.json',calls);require('CALL_'+str(len(calls)),bool(response.isError)==error)
                    if error:return response
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
                for i,b in enumerate(selected):
                    h=next(h for h in raw_h if h['hypothesis_id']==b['hypothesis_id']);packet=vault.packet(h['packet_id']);audit=source_audit(h,packet)
                    require('SOURCE_AUDIT_BEFORE_TARGET_'+str(i),audit['status']=='PROXY_SUPPORTED')
                    source={'project':project,'kind':'hypothesis','focus':'Raw source H '+str(i),'result':json.dumps({'H':h,'source_audit':audit},ensure_ascii=False),
                            'status':'hypothesis','request_key':'raw-H-'+str(i)}
                    event=await call('record_result',source);again=await call('record_result',source)
                    require('CANONICAL_SOURCE_IDEMPOTENCY_'+str(i),
                        all(again.get(k)==event.get(k) for k in ['id','project','status']) and again.get('idempotent') is True)
                    old=await call('dav_register_adapter',{'project':project,'spec':{'kind':'reaction_network','reaction_network':b['old_binding']},'request_key':'old-binding-'+str(i)})
                    require('REAL_REGISTRATION_'+str(i),'id' in old and old['payload']['metadata']['spec']['kind']=='reaction_network')
                    old_law={'project':project,'registration_id':old['id'],'adapter_binding':old['payload']['binding'],
                             'formula':implication('S0','One','S1','One').model_dump(),'persist':True,'request_key':'counter-'+str(i)}
                    bad=await call('dav_check_law',old_law)
                    require('ACTUAL_DAV_BINDING_COUNTEREXAMPLE_'+str(i),bad['payload']['status']=='refuted' and bad['payload']['counterexample']['state']==1)
                    revised=await call('dav_register_adapter',{'project':project,'spec':{'kind':'reaction_network','reaction_network':b['effective_network']},'request_key':'revised-binding-'+str(i)})
                    rr=await call('record_result',{'project':project,'kind':'counterexample','focus':'Binding revision '+str(i),
                        'result':json.dumps({'revision':b['revision'],'actual_DAV_counterexample_id':bad['id'],'revised_registration_id':revised['id']},ensure_ascii=False),
                        'status':'experiment','parent_id':event['id'],'evidence':'dav:'+str(bad['id']),'request_key':'revision-'+str(i)})
                    exported=await call('dav_export_evidence',{'project':project,'evidence_id':bad['id']})
                    require('NO_TRUTH_OR_EXECUTION_UPGRADE_'+str(i),exported['record']['payload']['proof_status']=='unverified' and
                        exported['record']['payload']['execution_permission']=={'allowed':False})
                    require('DAV_RESULT_REPEAT_'+str(i),bad==await call('dav_check_law',old_law))
                    await call('dav_export_evidence',{'project':'LM_QA_GENESIS_OTHER','evidence_id':bad['id']},error=True)
                    if i==0:
                        await call('record_result',{**source,'result':'changed source under the same key'},error=True)
                        await call('record_result',{**source,'status':'verified','request_key':'forbidden-verified'},error=True)
                        await call('record_result',{**source,'project':'LM_QA_GENESIS_OTHER','parent_id':event['id'],'request_key':'foreign-parent'},error=True)
                    ids.append({'hypothesis_id':h['hypothesis_id'],'source_event_id':event['id'],'old_registration_id':old['id'],
                                'counterexample_id':bad['id'],'revised_registration_id':revised['id'],'revision_event_id':rr['id']})
                # Positive finite control is genuinely synthetic, with an essential premise.
                positive=synthetic_control();reg=await call('dav_register_adapter',{'project':project,'spec':{'kind':'reaction_network','reaction_network':positive['network']},'request_key':'synthetic-register'})
                evidence=await call('dav_check_law',{'project':project,'registration_id':reg['id'],'adapter_binding':reg['payload']['binding'],
                    'formula':positive['formula'],'persist':True,'request_key':'synthetic-law'})
                require('SYNTHETIC_CONTROL_ONLY',evidence['payload']['status']=='proved' and evidence['payload']['proof_status']=='unverified')
                health=await call('service_health',{});save(out/'health.json',health)
                require('CANONICAL_INTEGRITY_AND_AUDIT',health['sqlite_integrity']=='ok' and health['audit']['ok'])
                history=await call('artifact_translation_history',{'project':project,'limit':20})
                require('DAV_FULL_HASH_CHAIN',history['integrity']['ok'])
                save(out/'object-ids.json',ids)
                return {'status':'PASS_EXISTING_PRIVATE_OAUTH_MCP','calls':len(calls),'checks':checks,'objects':ids,
                    'tool_count':len(names),'source_audit_location':'LOCAL_INDEPENDENT_PROXY_BEFORE_MCP; server stores hypotheses as unverified claims',
                    'new_production_tools':0,'external_execution_grants':0,'proof_status':'unverified'}


def run(root: Path,experiment: Path,source001: Path,private: Path,out: Path,snapshots: Path|None=None):
    previous=existing_qa.checks
    async def callback(url,token,dest,entries):return await exercise(url,token,dest,root,experiment)
    existing_qa.checks=callback
    try:return existing_qa.run(source001,private,out,snapshots)
    finally:existing_qa.checks=previous


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--experiment',type=Path,required=True)
    p.add_argument('--source001',type=Path,required=True);p.add_argument('--private-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--snapshots',type=Path)
    a=p.parse_args();res=run(a.root.resolve(),a.experiment.resolve(),a.source001.resolve(),a.private_root.resolve(),a.out.resolve(),a.snapshots.resolve() if a.snapshots else None)
    print(json.dumps({'status':res['status'],'calls':res['calls'],'checks':len(res['checks'])}))
