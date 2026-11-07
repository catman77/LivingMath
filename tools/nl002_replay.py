"""Offline frozen proposal replay; optional exact original White Star recomputation."""
import argparse,json,socket
from pathlib import Path
from unittest.mock import patch
from lm_suti_assurance.core import digest
from lm_suti_assurance.nl_proposal.decoder import replay_bundle

def main(a):
 data=json.loads(a.candidates.read_text());receipts=[]
 with patch.object(socket,'socket',side_effect=AssertionError('OFFLINE_NETWORK_FORBIDDEN')):
  for arm,jobs in data.items():
   for job in jobs:receipts.append({'arm':arm,'run_ref':job['run_ref'],**replay_bundle(job['result']['bundle'])})
 numeric=[]
 if a.snapshots:
  from lm_suti_assurance.white_star.pool import Pool
  from lm_suti_assurance.symbolic.executor import Executor
  pools={'white_star':Pool(),'symbolic_v1':Executor()}
  try:
   for frozen in json.loads(a.snapshots.read_text())['runs']:
    answer=pools[frozen['engine']].run({'action':'explore','request':frozen['input']})['data']
    assert digest(answer)==frozen['result_sha256']==digest(frozen['result']),frozen['run_id']
    numeric.append({'engine':frozen['engine'],'run_id':frozen['run_id'],'status':'EXACT_RESULT_SHA256_MATCH','sha256':digest(answer),'model_calls':0})
  finally:
   for pool in pools.values():pool.close()
 output={'status':'PASS','proposal_receipts':receipts,'structural_receipts':numeric,'LLM_calls':0,'network_calls':0,'scientific_semantics':'NOT_EVALUATED'}
 a.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n');print('OFFLINE_REPLAY_PASS',len(receipts),len(numeric))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--snapshots',type=Path);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
