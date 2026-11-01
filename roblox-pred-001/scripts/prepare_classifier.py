import argparse
from pathlib import Path
import json

from roblox_pred.classifier_pilot import prepare
from roblox_pred.classifier_benchmark import benchmark

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Prepare weak-label train/validation/test and run quick classifier baselines')
    parser.add_argument('collection',type=Path)
    args=parser.parse_args();summary=prepare(args.collection)
    result=benchmark(Path(summary['directory']))
    print(json.dumps({'dataset':summary,'baseline':result},ensure_ascii=False,indent=2))
