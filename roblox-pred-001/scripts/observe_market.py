"""Collect documented public portfolios and game details without login."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import httpx

from roblox_pred.config import load_config
from roblox_pred.observation import observe_market

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/public-observation.yaml'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        config,root=load_config(args.config)
        output=args.output or root/'data'/'observations'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
        print(json.dumps(observe_market(root,config,output),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError,httpx.HTTPError) as error:
        print(json.dumps({'status':'COLLECTION_ERROR','error':str(error)},ensure_ascii=False))
        raise SystemExit(3)
