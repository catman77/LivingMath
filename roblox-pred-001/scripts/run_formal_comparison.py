"""Durable owner-side batch using the actual installed LivingMath source/formal code."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from roblox_pred.config import digest
from roblox_pred.evaluation.runner import freeze
from roblox_pred.formal_basis import DIMENSIONS,VERSION
from formal_worker import render,save


def notify(run: Path, title: str, body: str) -> None:
    if not shutil.which('notify-send'):return
    env=dict(os.environ);env.setdefault('DBUS_SESSION_BUS_ADDRESS',f'unix:path=/run/user/{os.getuid()}/bus')
    p=subprocess.run(['notify-send','--app-name=LivingMath',title,body],env=env,capture_output=True,text=True,timeout=10)
    save(run/'notification.json',{'exit_code':p.returncode,'title':title,'stderr':p.stderr,'scope':'DESKTOP_DBUS_NOT_CHAT'})


def main(args) -> int:
    os.umask(0o077);root=Path(__file__).resolve().parents[1];run=args.run_dir.absolute()
    run.mkdir(parents=True,exist_ok=True,mode=0o700)
    final=run/'status.json'
    if final.exists() and json.loads(final.read_text()).get('status','').startswith('COMPLETED'):return 0
    if not 1<=args.workers<=4:raise ValueError('WORKER_BOUND_1_TO_4')
    dataset=args.dataset.resolve(strict=True);inputs=[]
    for split in ['train','validation','test']:
        for line in (dataset/f'{split}_input.jsonl').read_text().splitlines():
            row=json.loads(line);row={k:v for k,v in row.items() if k!='label'}
            text=render(row)
            if len(text.encode())>48000:raise ValueError('SOURCE_UTF8_BOUND')
            row['split']=split;row['input_sha256']=digest(row);inputs.append(row)
    inputs.sort(key=lambda r:r['case_id'])
    layer=args.product_layer.resolve(strict=True)
    worker_python=args.worker_python.expanduser().absolute() # Preserve venv pyvenv.cfg discovery.
    declaration={'dataset_manifest_sha256':hashlib.sha256((dataset/'dataset-frozen.json').read_bytes()).hexdigest(),
        'source_inputs_sha256':digest(inputs),'rows':len(inputs),'feature_basis':VERSION,'dimensions':DIMENSIONS,
        'product_layer':str(layer),'product_manifest_sha256':hashlib.sha256((layer/'manifest.json').read_bytes()).hexdigest(),
        'classifier_dataset_sha256':hashlib.sha256((dataset/'classifier_dataset.json').read_bytes()).hexdigest(),
        'baseline_models_sha256':hashlib.sha256((dataset/'baseline-models.joblib').read_bytes()).hexdigest(),
        'worker_python':str(worker_python),'workers':args.workers,'model':'gpt-6.1-sol',
        'source_budget':{'workers':16,'models':4,'source_views':1,'retries':1},'screenshots_used':False,
        'feature_code_sha256':hashlib.sha256((root/'src/roblox_pred/formal_basis.py').read_bytes()).hexdigest(),
        'study_code_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ['src/roblox_pred/formal_basis.py','src/roblox_pred/formal_comparison.py',
             'scripts/formal_worker.py','scripts/run_formal_comparison.py']}}
    freeze(run/'run-frozen.json',declaration);save(run/'source-inputs.json',inputs)
    if args.prepare_only:
        print(json.dumps({'status':'FROZEN_READY','directory':str(run),'cases':len(inputs)}));return 0
    processes=[];logs=[]
    try:
        for worker in range(args.workers):
            folder=run/f'worker-{worker}';folder.mkdir(exist_ok=True,mode=0o700)
            log=(folder/'worker.log').open('a');logs.append(log)
            command=[str(worker_python),'-B',str(root/'scripts/formal_worker.py'),'--product-layer',str(layer),
                '--run-dir',str(run),'--worker',str(worker),'--workers',str(args.workers)]
            processes.append(subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUNBUFFERED':'1'}))
        while True:
            cases=list((run/'cases').glob('*/result.json'));states=[]
            for worker in range(args.workers):
                path=run/f'worker-{worker}'/'status.json'
                if path.exists():states.append(json.loads(path.read_text()))
            save(final,{'status':'RUNNING','completed':len(cases),'total':len(inputs),'updated_at':datetime.now(UTC).isoformat(),
                'worker_statuses':states,'run_directory':str(run),'source_only':True,'feature_basis':VERSION})
            if any(p.poll() is not None and p.returncode!=0 for p in processes):
                for p in processes:
                    if p.poll() is None:p.terminate()
                for p in processes:
                    try:p.wait(timeout=15)
                    except subprocess.TimeoutExpired:p.kill();p.wait()
                reason={'status':'BLOCKED_OR_FAILED','completed':len(cases),'total':len(inputs),'worker_statuses':states,
                    'exit_codes':[p.returncode for p in processes],'updated_at':datetime.now(UTC).isoformat()}
                save(final,reason);(run/'report.md').write_text('# Прогон остановлен\n\n'+json.dumps(reason,ensure_ascii=False,indent=2)+'\n')
                notify(run,'LivingMath: прогон остановлен','Причина и сохранённый прогресс: '+str(run/'report.md'))
                return 78
            if all(p.poll() is not None for p in processes):break
            time.sleep(5)
        from roblox_pred.formal_comparison import evaluate
        comparison=evaluate(dataset,run)
        save(final,{'status':comparison['status'],'completed':len(inputs),'total':len(inputs),
            'updated_at':datetime.now(UTC).isoformat(),'report':str(run/'report.md'),'comparison':str(run/'comparison.json')})
        notify(run,'LivingMath: сравнение завершено','Результат: '+str(run/'report.md'))
        return 0
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for log in logs:log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--product-layer',type=Path,required=True)
    p.add_argument('--worker-python',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args()
    try:raise SystemExit(main(args))
    except Exception as error:
        args.run_dir.mkdir(parents=True,exist_ok=True)
        save(args.run_dir/'status.json',{'status':'FAILED','error':type(error).__name__+':'+str(error)})
        raise
