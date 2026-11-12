"""Real HTTP/MCP acceptance, resume, and independent export audit.

All output is private. External endpoints receive only isolated QA projects.
"""
import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(1, str(ROOT/'live_math_mcp_prod'))
from dav_acceptance import TappedStream
from lm_suti_assurance.core import digest
from lm_suti_assurance.completeness.contracts import SCOPE
from completeness001_verify import verify_export


async def main(a):
    out = a.output.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    def save(name, value):
        path = out/name
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        path.chmod(0o600)
    checks=[]
    def check(name, condition, **detail):
        checks.append({'invariant':name,'status':'PASS' if condition else 'FAIL',**detail})
        save('checks.json',checks)
        assert condition,(name,detail)
    request=json.loads(a.input.read_text())
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    endpoint=a.endpoint or f'http://127.0.0.1:{port}/mcp'
    child=None
    log=(out/'server.log').open('a')
    def stop():
        nonlocal child
        if child is not None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
            child=None
    async def start(baseline=False):
        nonlocal child
        if a.endpoint:
            return
        args=[sys.executable,str(ROOT/'tools/completeness001_server.py'),'--state',str(out/'workspaces'),'--port',str(port)]
        if baseline: args.append('--without-coverage')
        child=subprocess.Popen(args,stdout=log,stderr=log,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        async with httpx.AsyncClient() as http:
            for _ in range(200):
                if child.poll() is not None: raise RuntimeError('QA server startup failed; see server.log')
                try:
                    await http.get(endpoint); return
                except httpx.ConnectError: await asyncio.sleep(.05)
        raise RuntimeError('QA startup did not complete')
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def connect():
        headers={'Host':a.host_header} if a.host_header else {}
        async with httpx.AsyncClient(timeout=120,headers=headers) as http:
            async with streamable_http_client(endpoint,http_client=http) as (rd,wr,_):
                async with ClientSession(TappedStream(rd,out/'wire.jsonl','server_to_client'),TappedStream(wr,out/'wire.jsonl','client_to_server')) as c:
                    info=await c.initialize(); save('initialize.json',info.model_dump(mode='json'))
                    if a.expected_version:
                        check('actual initialized server version',info.serverInfo.version==a.expected_version)
                    yield c
    async def call(c,tool,args,error=None):
        args=dict(args)
        if args.get('project')=='coverage-qa':args['project']=a.project
        elif args.get('project')=='other-qa':args['project']=a.project+'-other'
        response=await c.call_tool(tool,args)
        with (out/'transcript.jsonl').open('a') as f:
            f.write(json.dumps({'tool':tool,'arguments':args,'response':response.model_dump(mode='json')},ensure_ascii=False)+'\n')
        payload=response.structuredContent or json.loads(response.content[0].text)
        if error:
            check('reject '+error,bool(response.isError) and payload['error']['code']==error)
            return payload
        check('call '+tool+' succeeds',not response.isError and payload.get('ok',True))
        return payload.get('data',payload)
    try:
        if a.endpoint:
            assert a.baseline_tools is not None,'--baseline-tools required for external endpoint'
            baseline=json.loads(a.baseline_tools.read_text());save('tools-before.json',baseline)
        else:
            await start(True)
            async with connect() as c:
                baseline=(await c.list_tools()).model_dump(mode='json'); save('tools-before.json',baseline)
        stop()
        await start()
        async with connect() as c:
            listing=(await c.list_tools()).model_dump(mode='json');save('tools-after.json',listing)
            old={t['name']:t for t in baseline['tools']}; new={t['name']:t for t in listing['tools']}
            check('all existing complete tool contracts unchanged',len(new)==len(old)+4 and all(new[k]==v for k,v in old.items()),old_count=len(old),new_count=len(new))
            check('four new tools visible through real MCP tools/list',set(new)-set(old)=={'coverage_plan','coverage_advance','coverage_inspect','coverage_replay'})
            await call(c,'assurance_project_new',{'project':'coverage-qa','request_key':'project'})
            await call(c,'assurance_project_new',{'project':'other-qa','request_key':'project'})
            args={'project':'coverage-qa','request_key':'plan','source_request':request,'scope':SCOPE}
            initial=await call(c,'coverage_plan',args); save('plan-created.json',initial)
            check('fixture224 targets700 exact cells112 charts',initial['total_count']==224 and initial['independent_check']['exact_partition_cells']==700 and initial['independent_check']['numeric_charts']==112)
            check('planning is not computation/export/delivery',not initial['compute_complete'] and not initial['export_available'] and not initial['delivery_acked'])
            ref=initial['plan_ref']
            for audience in ['public','reviewers','private']:
                denied=await call(c,'assurance_export',{'project':'coverage-qa','audience':audience})
                check('generic '+audience+' bundle cannot publish private coverage source',denied.get('reason_code')=='COVERAGE_EXPORT_REQUIRES_PLAN_REF' and 'bundle_base64' not in denied)
            check('identical plan request idempotent',await call(c,'coverage_plan',args)==initial)
            await call(c,'coverage_inspect',{'project':'other-qa','plan_ref':ref},'PLAN_NOT_FOUND')
            forged=copy.deepcopy(args);forged['request_key']='source-forgery';forged['source_request']['encoding']['source']['text']+='x'
            await call(c,'coverage_plan',forged,'SOURCE_MISMATCH')
            base=copy.deepcopy(args);base['request_key']='base';base['source_request']['atlas_profile']='base_v1'
            await call(c,'coverage_plan',base,'COVERAGE_REQUIRES_CJ_V1')
            bad={**initial['cursor'],'index':1}
            await call(c,'coverage_advance',{'project':'coverage-qa','plan_ref':ref,'request_key':'forged-cursor','cursor':bad,'work_budget':1},'CURSOR_PREFIX_MISMATCH')
            current=await call(c,'coverage_advance',{'project':'coverage-qa','plan_ref':ref,'request_key':'zero','cursor':initial['cursor'],'work_budget':0})
            check('zero budget remains PARTIAL',current['status']=='PARTIAL' and current['computed_count']==0)
            first_args={'project':'coverage-qa','plan_ref':ref,'request_key':'work1','cursor':current['cursor'],'work_budget':17}
            current=await call(c,'coverage_advance',first_args)
            check('bounded prefix PARTIAL17',current['status']=='PARTIAL' and current['computed_count']==17)
            check('advance idempotent',await call(c,'coverage_advance',first_args)==current)
            changed={**first_args,'work_budget':18}
            await call(c,'coverage_advance',changed,'REQUEST_KEY_CONFLICT')
            save('before-restart.json',current)
        stop();await start()
        async with connect() as c:
            restored=await call(c,'coverage_inspect',{'project':'coverage-qa','plan_ref':ref})
            check('client reconnect restores committed prefix' if a.endpoint else 'actual process restart restores exact committed prefix',restored['cursor']==current['cursor'] and restored['computed_count']==17)
            for n,budget in enumerate([47,64,96],2):
                current=await call(c,'coverage_advance',{'project':'coverage-qa','plan_ref':ref,'request_key':f'work{n}','cursor':current['cursor'],'work_budget':budget})
                check('no hidden CAT veto or lost work',current['advanced_count']==budget)
            check('computed and available does not imply acknowledged',current['compute_complete'] and current['export_available'] and not current['delivery_acked'])
            all_views={}
            for view in ['plan','atlas','omissions','records']:
                items=[];sizes=[];index=0
                while True:
                    page=await call(c,'coverage_inspect',{'project':'coverage-qa','plan_ref':ref,'view':view,'cursor':index,'page_size':64})
                    check('page hash '+view,digest(page['records'])==page['page_sha256'])
                    items+=page['records'];sizes.append(len(page['records']))
                    if page['next_cursor'] is None:break
                    index=page['next_cursor']
                all_views[view]=items;save(view+'.json',items)
                if view=='records':check('64+64+64+32 complete untruncated delivery',sizes==[64,64,64,32])
            records=all_views['records']
            check('unique work units and fixed denominator',len(records)==len({r['work_unit_key'] for r in records})==current['total_count']==224)
            check('zero and balance boundaries retained',sum(r['target']['relation']=='UNRESOLVED' for r in records)==56 and sum(r['target']['dominance']=='EQUAL' for r in records)==56)
            check('witness18 bounded24',max(sum(r['witness']) for r in records)==18 and current['witness_l1_bound']==24)
            check('export digest equals client reconstructed bytes',digest(records)==current['export_sha256'])
            independent=verify_export(request,records,all_views['atlas'],a.input.parent/'independent_verify.py')
            save('independent-verification.json',independent);check('supplied independent checker700 cells',independent['status']=='PASS' and independent['exact_partition_cells']==700)
            offset=0;replays=[]
            while True:
                replay=await call(c,'coverage_replay',{'project':'coverage-qa','plan_ref':ref,'cursor':offset,'work_budget':64})
                replays.append(replay)
                if replay['next_cursor'] is None:break
                offset=replay['next_cursor']
            check('all224 projections really replay through pinned worker',sum(r['checked_count'] for r in replays)==224 and all(r['status']=='REPLAY_MATCH' for r in replays))
            ack={'export_sha256':digest(records),'record_count':len(records),'client_id':'actual-python-mcp-qa'}
            wrong={**ack,'export_sha256':'0'*64}
            await call(c,'coverage_inspect',{'project':'coverage-qa','plan_ref':ref,'view':'delivery','acknowledgement':wrong,'request_key':'bad-ack'},'DELIVERY_ACK_MISMATCH')
            final=await call(c,'coverage_inspect',{'project':'coverage-qa','plan_ref':ref,'view':'delivery','acknowledgement':ack,'request_key':'ack'})
            check('explicit named client acknowledgement persisted',final['delivery_acked'])
            save('final-summary.json',final)
        from lm_suti_assurance.workspace import Workspace,validate_history
        rows=[];head=None
        if not a.endpoint:
            w=Workspace(out/'workspaces',a.project);rows=w.history()
            head=validate_history(rows)
            check('append-only journal and all content-addressed objects intact',all(w.get(r) is not None for row in rows for r in row['object_refs']))
        save('result.json',{'status':'PASS','checks':len(checks),'failures':0,'endpoint_scope':a.endpoint_scope if a.endpoint else 'LOCAL_LOOPBACK_REAL_MCP_NOT_PRODUCTION','plan_ref':ref,'project':a.project,'source_sha256':request['encoding']['source']['sha256'],'computed':224,'delivery_acked':True,'journal_entries':len(rows) if rows else None,'journal_head':head,'independent':independent,'production_deployed':bool(a.endpoint and a.endpoint_scope=='PRODUCTION_HTTPS')})
        print(json.dumps({'status':'PASS','checks':len(checks),'output':str(out)}))
    except BaseException as e:
        save('result.json',{'status':'FAIL','error':str(e),'checks':len(checks),'production_deployed':False})
        raise
    finally:
        stop();log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--endpoint')
    p.add_argument('--baseline-tools',type=Path)
    p.add_argument('--project',default='coverage-qa')
    p.add_argument('--expected-version')
    p.add_argument('--host-header')
    p.add_argument('--endpoint-scope',choices=['STAGING_FULL_COMPOSITION','PRODUCTION_HTTPS'],default='STAGING_FULL_COMPOSITION')
    asyncio.run(main(p.parse_args()))
