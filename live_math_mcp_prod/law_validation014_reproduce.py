"""Replay014 frozen scientific inputs on a fresh private synthetic database."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from native_preview008_server import MeasuredProcess
from qa_positive_acceptance import write_json
from research_store import ResearchStore


def main():
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False);base=output/'private';base.mkdir(mode=0o700)
    original=base/'source-origin.sqlite3';ResearchStore(original);original.chmod(0o600)
    with __import__('sqlite3').connect(original) as src,__import__('sqlite3').connect(base/'canonical.sqlite3') as dst:src.backup(dst)
    shutil.copy2(args.package/'source-freeze.json',base/'source-freeze.json');shutil.copytree(args.package/'frozen-inputs',base/'frozen-inputs')
    freeze=json.loads((base/'source-freeze.json').read_text())
    for name,expected in freeze['hashes'].items():
        if hashlib.sha256((base/'frozen-inputs'/name).read_bytes()).hexdigest()!=expected:raise ValueError('FROZEN_INPUT_DRIFT:'+name)
    source=Path(__file__).resolve().parent
    for name in ('law_validation014_native.py','law_validation014_oracle.py','law_validation014_worlds.py'):
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=freeze['hashes'][name]:raise ValueError('SOURCE_CODE_DRIFT:'+name)
    write_json(base/'metadata.json',{'canonical':str(original),'reproduction':'same frozen inputs, not independent new scientific evidence'})
    started=time.perf_counter_ns()
    with (output/'process.log').open('w') as log:
        process=MeasuredProcess([sys.executable,str(source/'law_validation014_qa.py'),'--baseline',str(base),'--output',str(output/'P0')],stdout=log,stderr=log)
        try:process.wait(timeout=freeze['policy']['budgets']['P0_wall_s'])
        except __import__('subprocess').TimeoutExpired:process.kill();process.wait();raise ValueError('P0_WALL_LIMIT')
    usage=process.child_usage
    costs={'wall_ns':time.perf_counter_ns()-started,'CPU_ns_including_reaped_descendants':round((usage.ru_utime+usage.ru_stime)*1e9),
           'peak_RSS_KiB':usage.ru_maxrss,'method':'OS wait4 through full process exit'}
    result=json.loads((output/'P0/result.json').read_text())
    passed=process.returncode==0 and result['status']=='P0_PASS_REGRESSIONS_PENDING' and result['receipts']==5
    limits=freeze['policy']['budgets'];passed &= costs['CPU_ns_including_reaped_descendants']<=limits['P0_CPU_s']*1e9 and costs['peak_RSS_KiB']<=limits['RSS_KiB']
    write_json(output/'result.json',{'status':'REPRODUCED_P0_PASS' if passed else 'FAIL','receipts':result['receipts'],'costs':costs,
        'same_frozen_inputs_not_independent_new_data':True,'historical86':'NOT_RERUN: original private historical snapshot is not distributed',
        'production_touched':False,'proof_status':'unverified'})
    print(json.dumps({'output':str(output),'PASS':passed,'receipts':result['receipts'],'costs':costs}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
