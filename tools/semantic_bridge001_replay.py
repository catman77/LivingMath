"""Trusted-installed-code replay of a data-only contextual bundle, without network."""
import argparse,json,hashlib
from pathlib import Path
from lm_suti_assurance.core import digest
from lm_suti_assurance.semantic_bridge.contextual.engine import binding
from lm_suti_assurance.semantic_bridge.contextual.executor import Executor


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--expected-sha256',required=True);a=p.parse_args();raw=a.bundle.read_bytes()
    if len(raw)>33554432 or hashlib.sha256(raw).hexdigest()!=a.expected_sha256:raise SystemExit('REJECTED_PROVENANCE')
    b=json.loads(raw)
    if b.get('schema')!='semantic-bridge-replay-bundle/1' or b['kernel_binding']!=binding() or digest(b['packet'])!=b['packet_sha256'] or digest(b['result'])!=b['result_sha256']:raise SystemExit('REJECTED_PROVENANCE')
    if b.get('operation') not in ('register','analyze') or b['packet']['operation']!=b['operation']:raise SystemExit('INVALID_REPLAY_OPERATION')
    e=Executor()
    try:v=e.run({'action':'explore','request':b['packet']})['data']
    finally:e.close()
    if digest(v)!=b['result_sha256']:raise SystemExit('REPLAY_MISMATCH')
    print(json.dumps({'status':'REPLAY_MATCH','result_sha256':digest(v),'LLM_calls':0,'network_calls':0,'execution_permission':False}))

if __name__=='__main__':main()
