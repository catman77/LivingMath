"""Replay data only through the installed bounded extension worker, without network."""

import argparse, base64, json
from pathlib import Path
from lm_suti_assurance.symbolic.executor import Executor

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.bundle.stat().st_size > 64 * 1024 * 1024:
        raise SystemExit("BUNDLE_SIZE_LIMIT")
    pool = Executor()
    try:
        result = pool.run(
            {
                "action": "extension_replay",
                "bundle_base64": base64.b64encode(args.bundle.read_bytes()).decode(),
            }
        )["data"]
        print(json.dumps(result, ensure_ascii=False))
    finally:
        pool.close()
