"""Data-only exact-binding offline replay; no archive/source code loading."""

import argparse, json
from pathlib import Path
from lm_suti_assurance.core import digest, strict_json
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.symbolic_complex.app import binding


def replay(path):
    raw = path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("BUNDLE_BOUND")
    bundle = strict_json(raw.decode())
    if (
        set(bundle) != {"schema", "kernel_binding", "packet", "result", "result_sha256"}
        or bundle["schema"] != "formal-replay-bundle/1"
    ):
        raise ValueError("INVALID_BUNDLE")
    if bundle["kernel_binding"] != binding():
        raise ValueError("KERNEL_BINDING_UNAVAILABLE")
    if digest(bundle["result"]) != bundle["result_sha256"]:
        raise ValueError("RESULT_SHA_MISMATCH")
    if bundle["packet"].get("action") != "observer_verify" or set(bundle["packet"]) != {
        "action",
        "formal_packet",
    }:
        raise ValueError("INVALID_PACKET")
    pool = Executor()
    try:
        r = pool.run(bundle["packet"])
    finally:
        pool.close()
    h = digest(r["data"])
    return {
        "status": "REPLAY_MATCH" if h == bundle["result_sha256"] else "REPLAY_MISMATCH",
        "kernel_binding": binding(),
        "result_sha256": h,
        "metrics": r["metrics"],
        "execution_permission": False,
        "UNIVERSAL_INVARIANT": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    a = p.parse_args()
    print(json.dumps(replay(a.bundle)))
