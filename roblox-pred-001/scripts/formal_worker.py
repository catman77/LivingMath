"""Execute the installed LivingMath Controller on isolated source-only cases."""
import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def save(path: Path, value: object) -> None:
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def render(row: dict) -> str:
    text='Game title: '+row['title']+'\nGame description:\n'+row['model_description']
    # Keep full bytes; short consecutive lines fit the unchanged 8-span/4K contract.
    lines=[]
    for line in text.splitlines():
        lines.extend(line[i:i+4000] for i in range(0,len(line),4000))
    if len(lines)>8:raise ValueError('SOURCE_EXCEEDS_ONE_VIEW_NO_SILENT_TRUNCATION')
    return '\n'.join(lines)


async def run(args) -> int:
    layer=args.product_layer.resolve(strict=True);root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(layer));sys.path.insert(0,str(root/'src'))
    from davcore.service import Service
    from research_automation.controller import Controller
    from research_automation.artifact_contract import ArtifactInput
    from semantic_repair.inference011 import SubscriptionInference
    from roblox_pred.formal_basis import semantic_features,formal_features,raw_semantic_views
    manifest=json.loads((layer/'manifest.json').read_text())
    for name,sha in manifest.items():
        file=(layer/name).resolve(strict=True)
        if not file.is_relative_to(layer) or hashlib.sha256(file.read_bytes()).hexdigest()!=sha:
            raise ValueError('INSTALLED_PRODUCT_SOURCE_DRIFT:'+name)
    if args.preflight:return 0
    run_dir=args.run_dir.resolve();work=run_dir/f'worker-{args.worker}';work.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.environ['TIKTOKEN_CACHE_DIR']=str(layer/'dependency_cache')
    frozen=json.loads((run_dir/'run-frozen.json').read_text())
    for name,sha in frozen['study_code_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('STUDY_CODE_DRIFT:'+name)
    inputs=json.loads((run_dir/'source-inputs.json').read_text())
    encoded=json.dumps(inputs,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest()!=frozen['source_inputs_sha256']:raise ValueError('SOURCE_INPUT_MANIFEST_DRIFT')
    assigned=[row for i,row in enumerate(inputs) if i%args.workers==args.worker]
    if args.max_cases is not None:assigned=assigned[:args.max_cases]
    provider=SubscriptionInference(work/'inference-spool',model='gpt-6.1-sol')
    service=Service(work/'dav.sqlite3');controller=Controller(service,semantic_provider=provider)
    project='BRIDGE_QA_ROBLOX_FORMAL_W'+str(args.worker)
    completed=0;consecutive_failure=0
    try:
        for row in assigned:
            case_dir=run_dir/'cases'/row['case_id'];case_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
            target=case_dir/'result.json'
            if target.exists():
                old=json.loads(target.read_text())
                if old['input_sha256']!=row['input_sha256']:raise ValueError('CASE_SOURCE_SUBSTITUTION')
                completed+=1;continue
            save(work/'status.json',{'status':'RUNNING','case_id':row['case_id'],'completed':completed,'assigned':len(assigned),'updated_at':datetime.now(UTC).isoformat()})
            packet=ArtifactInput.model_validate({'format':'livingmath-artifact/1','profile':'typed008/1','interpretation':'observer012',
                'scope':'roblox/formal-v1/'+row['case_id'],'source_name':'Roblox '+row['case_id'],
                'edition':'Frozen public API description; classification targets excluded','language':'en',
                'rights':{'basis':'USER_SESSION','origin':'Public descriptions collected at the explicit operator request; source provenance retained outside the model pipe.'},
                'raw_text':render(row),'budget':{'workers':16,'models':4,'source_views':1,'retries':1}})
            start=time.monotonic();ingest=controller.ingest(project,packet,'formal-case-'+row['case_id'])
            ident=ingest['case_ids'][0]
            for iteration in range(128):
                await controller.tick()
                current=next(c for c in controller.status(project)['cases'] if c['case_id']==ident)
                if current['status'] not in {'QUEUED','DIAGNOSING','PROPOSING','AUDITING','EXPERIMENTING','CHECKING','RETRY_WAIT'}:break
                if time.monotonic()-start>360:raise TimeoutError('CASE_WALL_LIMIT_360')
                await asyncio.sleep(.02)
            else:raise ValueError('CASE_STEP_LIMIT')
            records=controller.journal.rows(('artifact_semantic_call','artifact_checkpoint','artifact_result'),project,case_id=ident)
            results=[r['payload'] for r in records if r['kind']=='artifact_result']
            calls=[r['payload']['result'] for r in records if r['kind']=='artifact_semantic_call']
            sem,sem_ok=semantic_features(raw_semantic_views(records));formal,formal_ok=formal_features(results)
            result={'case_id':row['case_id'],'input_sha256':row['input_sha256'],'engine_case_id':ident,'engine_project':project,
                'engine_status':current['status'],'engine_result':current['result'],'seconds':time.monotonic()-start,
                'semantic_features':sem,'semantic_available':sem_ok,'formal_features':formal,'formal_available':formal_ok,
                'model_calls':len(calls),'model_statuses':[c.get('status') for c in calls],
                'usage':{key:sum((c.get('usage') or {}).get(key,0) or 0 for c in calls) for key in ['input_tokens','output_tokens','reasoning_output_tokens']},
                'formal_result_count':len(results),'journal':str(service.store.path),'source_only':True,
                'proof_status':'unverified','native_SUTI_runtime_executed':False,'external_execution_grant':False}
            save(case_dir/'engine-records.json',{'records':records})
            save(target,result);completed+=1
            backend_failed=not calls or any(c.get('status')!='OK' for c in calls)
            consecutive_failure=consecutive_failure+1 if backend_failed else 0
            if consecutive_failure>=3:
                save(work/'status.json',{'status':'BLOCKED_MODEL_UNAVAILABLE_OR_EMPTY','completed':completed,'assigned':len(assigned),'last_case':row['case_id']})
                return 78
        save(work/'status.json',{'status':'COMPLETED','completed':completed,'assigned':len(assigned),'updated_at':datetime.now(UTC).isoformat()})
        return 0
    finally:provider.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--product-layer',type=Path,required=True);p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--worker',type=int,required=True);p.add_argument('--workers',type=int,required=True)
    p.add_argument('--preflight',action='store_true');p.add_argument('--max-cases',type=int)
    args=p.parse_args()
    try:raise SystemExit(asyncio.run(run(args)))
    except Exception as error:
        work=args.run_dir/f'worker-{args.worker}';work.mkdir(parents=True,exist_ok=True)
        save(work/'status.json',{'status':'FAILED','error':type(error).__name__+':'+str(error)})
        raise
