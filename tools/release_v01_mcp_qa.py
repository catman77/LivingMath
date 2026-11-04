"""Real SDK HTTPS/OAuth acceptance, dedicated file-based QA projects only.

OAuth tokens stay in --private; the transcript contains only MCP messages.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
import time
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


async def run(args):
    from lm_suti_assurance import core
    from lm_suti_assurance.core import canonical
    from lm_suti_assurance.smoke import CASES, TAG, POLICY
    sys.path.insert(0, str(args.legacy_client))
    from unified_client_qa import authenticate
    from dav_acceptance import TappedStream
    token_file=args.private/'oauth.private.json'
    args.private.mkdir(mode=0o700,parents=True,exist_ok=True)
    auth=json.loads(token_file.read_text()) if token_file.exists() else authenticate(args.origin,args.password_file,token_file)
    assert auth['origin']==args.origin
    headers={'Authorization':'Bearer '+auth['token']['access_token']}
    transcript=[];checks=[]
    def check(name, condition):
        checks.append({'invariant':name,'result':'PASS' if condition else 'FAIL'})
        save(args.out/'checks.json',checks)
        if not condition:raise AssertionError(name)
    async with httpx.AsyncClient(timeout=90) as unauth:
        r=await unauth.post(args.origin+'/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'},headers={'Accept':'application/json, text/event-stream'})
        check('PUBLIC_HTTPS_NO_TOKEN_DENIED',r.status_code==401)
        metadata=(await unauth.get(args.origin+'/.well-known/oauth-authorization-server')).json()
        check('PUBLIC_OAUTH_ISSUER_EXACT',metadata['issuer']==args.origin+'/' and metadata['token_endpoint']==args.origin+'/token' and metadata['authorization_endpoint']==args.origin+'/authorize')
    async with httpx.AsyncClient(headers=headers,timeout=120) as http:
        async with streamable_http_client(args.origin+'/mcp',http_client=http) as (read,write,_):
            async with ClientSession(TappedStream(read,args.out/'mcp-wire.jsonl','server_to_client'),
                                     TappedStream(write,args.out/'mcp-wire.jsonl','client_to_server')) as session:
                init=await session.initialize();listing=await session.list_tools()
                save(args.out/'initialize.json',init.model_dump(mode='json'));save(args.out/'tools-list.json',listing.model_dump(mode='json'))
                async def call(name,params):
                    response=await session.call_tool(name,params)
                    transcript.append({'tool':name,'request':params,'response':response.model_dump(mode='json')})
                    save(args.out/'mcp-transcript.json',transcript)
                    if response.isError:raise AssertionError('MCP_ERROR:'+name+':'+str(response.content))
                    return response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
                check('INITIALIZE_RELEASE_VERSION',init.serverInfo.version=='v0.1.0-developer-preview')
                names={t.name for t in listing.tools}
                expected={'assurance_contract','assurance_project_new','assurance_source_add','assurance_task_import','assurance_task_review','assurance_candidate_import','assurance_check','assurance_report','assurance_export','assurance_replay','assurance_doctor'}
                check('ALL_11_NEW_TOOLS_REGISTERED',expected<=names)
                if args.baseline:
                    old=json.loads(args.baseline.read_text())['tools'];new={t.name:t.model_dump(mode='json') for t in listing.tools}
                    check('ALL_LEGACY_INPUT_SCHEMAS_PRESERVED',all(t['name'] in new and t['inputSchema']==new[t['name']]['inputSchema'] for t in old))
                health=await call('service_health',{});save(args.out/'health.json',health)
                check('SQLITE_AND_AUDIT_HEALTH',health['sqlite_integrity']=='ok' and health['audit']['ok'])
                status=await call('bridge_system_status',{});save(args.out/'status.json',status)
                check('REPORTED_RELEASE_VERSION',status['version']=='v0.1.0-developer-preview')
                contract=await call('assurance_contract',{});check('SCHEMAS_PUBLISHED',set(contract['schemas'])=={'task','candidate','decision','witness','publication-policy','package-manifest'})
                tasks=json.loads((core.ROOT/'examples/FROZEN_CORPUS.json').read_text());sources=json.loads((core.ROOT/'examples/SOURCE_SNAPSHOTS.json').read_text())
                p=args.project
                await call('assurance_project_new',{'project':p,'request_key':'new'})
                refs=[]
                for tid,delta,expected_status in CASES:
                    for sid in tasks[tid]['source_ids']:
                        await call('assurance_source_add',{'project':p,'snapshot_json':canonical(sources[sid]),'publication_policy_json':canonical(POLICY),'request_key':'source.'+sid})
                    task=await call('assurance_task_import',{'project':p,'artifact_json':canonical({'schema':'lm-suti.assurance.task/0.1','project':p,'task':tasks[tid]}),'request_key':'task.'+tid})
                    envelope={'schema':'lm-suti.assurance.candidate/0.1','project':p,'task_ref':task['task_ref'],'format':'delta','raw':canonical({'schema':TAG,**delta})}
                    params={'project':p,'artifact_json':canonical(envelope),'request_key':'candidate.'+tid}
                    c=await call('assurance_candidate_import',params)
                    check(tid+'_PROPOSAL_HAS_NO_GRANT',c['status']=='PROPOSED' and c['execution_permission'] is False)
                    denied=await call('assurance_check',{'project':p,'candidate_ref':c['candidate_ref'],'request_key':'pre-review.'+tid})
                    check(tid+'_REVIEW_REQUIRED',denied['reason_code']=='TASK_REVIEW_REQUIRED')
                    await call('assurance_task_review',{'project':p,'task_ref':task['task_ref'],'actor':'QA_OPERATOR','reason':'Real MCP automated QA, exact source/scope confirmed; not an external human pilot.','request_key':'review.'+tid})
                    d=await call('assurance_check',{'project':p,'candidate_ref':c['candidate_ref'],'request_key':'check.'+tid})
                    check(tid+'_EXPECTED_STATUS',d['status']==expected_status and d['execution_permission'] is False)
                    again=await call('assurance_candidate_import',params);check(tid+'_RETRY_IDEMPOTENT',again==c)
                    altered=await call('assurance_candidate_import',{**params,'artifact_json':canonical({**envelope,'raw':envelope['raw']+' '})})
                    check(tid+'_RETRY_CONFLICT',altered.get('reason_code')=='REQUEST_KEY_CONFLICT')
                    refs.append(d)
                report=await call('assurance_report',{'project':p});check('ALL_FOUR_RESULTS_RETAINED',len(report['records'])==4)
                from lm_suti_assurance.validation import validate
                for record in report['records']:
                    validate('decision',record['decision_artifact'])
                    for witness_artifact in record['witness_artifacts']:validate('witness',witness_artifact)
                check('PUBLISHED_TYPED_ARTIFACTS_VALIDATE_ACTUAL_REPORT',True)
                finite=next(r for r in report['records'] if r['claim_kind']=='FINITE_PROPOSITION')
                witness=next(iter(finite['witnesses_and_countermodels'].values()))['payload']
                check('ACTUAL_23_1_TWO_COUNTERMODELS',len(witness['countermodels'])==2 and [d['count'] for d in witness['distribution']]==[23,1])
                check('NO_FORMAL_OR_VERIFIED_PROMOTION',all(r['status'] not in ('verified','PROVED_FORMAL') for r in report['records']))
                exported=await call('assurance_export',{'project':p,'audience':'reviewers'})
                raw=base64.b64decode(exported['bundle_base64']);args.out.mkdir(mode=0o700,exist_ok=True,parents=True);(args.out/'pilot.zip').write_bytes(raw)
                a=await call('assurance_replay',{'bundle_base64':exported['bundle_base64'],'engine':'direct'})
                b=await call('assurance_replay',{'bundle_base64':exported['bundle_base64'],'engine':'compiled'})
                check('REAL_MCP_OFFLINE_REPLAY_BOTH_ENGINES',a['status']==b['status']=='PASS' and a['logical_digest']==b['logical_digest'])
                await call('assurance_project_new',{'project':p+'-other','request_key':'new'})
                cross=await call('assurance_check',{'project':p+'-other','candidate_ref':refs[0]['candidate_ref'],'request_key':'cross'})
                check('CROSS_PROJECT_DENIED',cross.get('reason_code')=='REFERENCE_NOT_IN_PROJECT')
                original=report['records'][0]['original_submission']
                for fmt,version in [('candidate','symseq.assurance.candidate.v2'),('delta','symseq.assurance.proposal-delta.v2')]:
                    future={**original,'format':fmt,'raw':canonical({'schema':version})}
                    c=await call('assurance_candidate_import',{'project':p,'artifact_json':canonical(future),'request_key':'future.'+fmt})
                    d=await call('assurance_check',{'project':p,'candidate_ref':c['candidate_ref'],'request_key':'future.check.'+fmt})
                    check(fmt+'_UNKNOWN_VERSION_REQUIRES_MIGRATION',d.get('status')=='HOLD' and d.get('reason_code')=='MIGRATION_REQUIRED')
                invalid64=await call('assurance_replay',{'bundle_base64':'!invalid-base64'})
                check('BAD_BASE64_PRECISE_ERROR',invalid64.get('reason_code')=='INVALID_BASE64')
                badzip=await call('assurance_replay',{'bundle_base64':base64.b64encode(b'not-a-zip').decode()})
                check('BAD_BUNDLE_PRECISE_ERROR',badzip.get('reason_code')=='INVALID_BUNDLE')
                doctor=await call('assurance_doctor',{});check('ACTUAL_CORE_PIN',doctor['verifier_digest']==core.LOCK['verifier_digest'])
                result={'status':'PASS','checks':checks,'project':p,'created_check_refs':refs,'tool_count':len(names),'origin':args.origin,
                        'transport':'REAL_EXTERNAL_HTTPS_OAUTH_SDK','public_TLS_certificate_verified':True,
                        'external_human_pilot':False,'logical_digest':a['logical_digest']}
                save(args.out/'result.json',result)
                print(json.dumps({k:result[k] for k in ('status','project','tool_count','origin')}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ('private','out','password-file','legacy-client'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--origin',required=True);p.add_argument('--project',required=True);p.add_argument('--baseline',type=Path)
    a=p.parse_args();asyncio.run(run(a))
