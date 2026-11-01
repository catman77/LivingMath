"""Replay frozen013 scientific inputs on a fresh QA database, with OS cost receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import time
from native_preview008_server import MeasuredProcess
from qa_positive_acceptance import write_json
from research_store import ResearchStore

SOURCE=Path(__file__).resolve().parent


def measured(command,log,timeout):
    start=time.perf_counter_ns()
    with log.open('w') as stream:
        process=MeasuredProcess(command,stdout=stream,stderr=stream)
        try:process.wait(timeout=timeout)
        except __import__('subprocess').TimeoutExpired:
            process.kill();process.wait();raise ValueError('QA_WALL_BUDGET_EXCEEDED')
    usage=process.child_usage
    return {'exit_code':process.returncode,'wall_ns':time.perf_counter_ns()-start,
            'CPU_ns_including_reaped_descendants':round((usage.ru_utime+usage.ru_stime)*1e9),
            'peak_RSS_KiB':usage.ru_maxrss,'method':'OS wait4 through process exit; subsets must not be summed again'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);base=out/'private';base.mkdir(mode=0o700)
    origin=base/'source-origin.sqlite3';ResearchStore(origin);origin.chmod(0o600)
    shutil.copy2(origin,base/'canonical.sqlite3')
    for name in ('freeze.json','source-audit.md'):shutil.copy2(args.package/name,base/name)
    shutil.copytree(args.package/'frozen-inputs',base/'frozen-inputs')
    freeze=json.loads((base/'freeze.json').read_text())
    actual={name:hashlib.sha256((base/'frozen-inputs'/name).read_bytes()).hexdigest() for name in freeze['frozen_files']}
    if actual!=freeze['frozen_files']:raise ValueError('FROZEN_INPUT_DRIFT')
    for name in ('operational013_native.py','operational013_oracle.py','operational013_worlds.py'):
        if hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=actual[name]:raise ValueError('FROZEN_NATIVE_OR_ORACLE_CODE_DRIFT')
    write_json(base/'metadata.json',{'canonical':str(origin),'reproduction':'Fresh synthetic QA only; original data preservation is a separate original-run check.'})
    costs={}
    costs['P0']=measured([sys.executable,str(SOURCE/'operational013_qa.py'),'--baseline',str(base),'--output',str(out/'P0')],out/'P0-process.log',120)
    policy=freeze['policy']['budgets'];r=costs['P0']
    r['resource_gate']=r['wall_ns']<=policy['P0_wall_seconds']*1e9 and r['CPU_ns_including_reaped_descendants']<=policy['P0_CPU_seconds']*1e9 and r['peak_RSS_KiB']<=policy['RSS_KiB']
    p0=json.loads((out/'P0/result.json').read_text())
    if p0['status']!='P0_PASS_TYPED_PENDING' or not r['resource_gate']:raise ValueError('P0_OR_RESOURCE_GATE_FAILED')
    costs['typed']=measured([sys.executable,str(SOURCE/'operational013_cycle_qa.py'),'--baseline',str(base)],out/'typed-process.log',45)
    typed=json.loads((base/'typed-current.json').read_text());attempt=Path(typed['attempt'])
    failure=json.loads((attempt/'first-failure.json').read_text())
    expected_stop=failure['invariant']=='A2:source_forecast' and failure['evidence']['status']=='NO_INFORMATIVE_TEST'
    if not expected_stop:raise ValueError('UNEXPECTED_TYPED_RESULT; original failure must be retained')
    costs['post_stop_controls']=measured([sys.executable,str(SOURCE/'operational013_controls.py'),'--baseline',str(base)],out/'controls-process.log',45)
    control=json.loads((base/'controls-current.json').read_text())
    write_json(out/'measured-costs.json',costs)
    write_json(out/'result.json',{'status':'REPRODUCED_P0_PASS_AND_TYPED_NO_GO','independent_new_data':False,
        'frozen_input_hashes_match':True,'P0_qualified':p0['qualified'],'expected_typed_stop':expected_stop,
        'controls':control,'costs':costs,'proof_status':'unverified','production_touched':False})
    print(json.dumps({'output':str(out),'status':'REPRODUCED_P0_PASS_AND_TYPED_NO_GO','costs':costs}))


if __name__=='__main__':main()
