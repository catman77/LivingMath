import argparse
import hashlib
import json
from pathlib import Path

from roblox_pred.classifier_benchmark import score_rows

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Score blind SUTI-LivingMath or control classifier predictions on the same frozen test')
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--model-name',required=True)
    args=parser.parse_args()
    raw=args.predictions.read_bytes();predictions=[json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    # Inputs are frozen before labels are loaded/scored; every test ID exactly once.
    rows=[r for r in json.loads((args.dataset/'classifier_dataset.json').read_text()) if r['split']=='test']
    report={'model_name':args.model_name,'prediction_sha256':hashlib.sha256(raw).hexdigest(),
        'metrics':score_rows(rows,predictions),'scope':'WEAK_ACTIVITY_PROXY_LABELS','verified':False}
    print(json.dumps(report,ensure_ascii=False,indent=2))
