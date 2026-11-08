"""Bounded data-only UDAV replay; code comes only from installed modules."""
import argparse,hashlib,json
from pathlib import Path
from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import SharedBudget
from lm_suti_assurance.udav_core.executor import Executor
from lm_suti_assurance.udav_core.symbolic import binding


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--expected-sha256',required=True);a=p.parse_args();raw=a.bundle.read_bytes()
    if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=a.expected_sha256:raise SystemExit('REJECTED_PROVENANCE')
    b=json.loads(raw)
    if b.get('schema')!='udav-data-only-bundle/1' or b.get('engine') not in ('symbolic','numeric'):raise SystemExit('INVALID_BUNDLE')
    if b['request_sha256']!=digest(b['request']) or b['result_sha256']!=digest(b['result']) or b['kernel_binding']!=binding(b['engine']):raise SystemExit('REJECTED_PROVENANCE')
    pool=Executor(SharedBudget(),SharedBudget())
    try:actual=pool.run({'action':'explore','engine':b['engine'],'request':b['request']})['data']
    finally:pool.close()
    if digest(actual)!=b['result_sha256']:raise SystemExit('REPLAY_MISMATCH')
    print(json.dumps({'status':'REPLAY_MATCH','result_sha256':digest(actual),'engine':b['engine'],'model_calls':0,'network_calls':0,'execution_permission':False}))

if __name__=='__main__':main()
