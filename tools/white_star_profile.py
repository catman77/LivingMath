"""Six bounded timing runs (3 raw+3 wrapped), no optimization or seed selection."""

import argparse, asyncio, json, statistics, time
from pathlib import Path
from lm_suti_assurance.core import canonical, digest
from lm_suti_assurance.white_star.pool import Pool
from lm_suti_assurance.white_star.service import WhiteStar
from lm_suti_assurance.white_star.runtime import load
from lm_suti_assurance.white_star.contracts import VENDOR
import lm_suti_assurance.workspace as workspace


def main(args):
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    req = json.loads((VENDOR / "fixtures/blok_request.json").read_text())
    started = time.perf_counter()
    adapter, _, identity = load()
    cold = time.perf_counter() - started
    raw = []
    expected = None
    for i in range(3):
        before = time.perf_counter()
        result = adapter.explore(req)
        elapsed = time.perf_counter() - before
        if expected is None:
            expected = digest(result)
        assert digest(result) == expected
        raw.append(
            {
                "index": i + 1,
                "standalone_adapter_s": elapsed,
                "logical_result_digest": expected,
            }
        )
    pool = Pool()
    readiness = pool.status()["workers"]
    service = WhiteStar(args.out / "state", pool)
    service.base.new("qa", "new")
    writes = []
    original = workspace.atomic_write

    def measured(path, data):
        before = time.perf_counter()
        value = original(path, data)
        writes.append(
            {
                "kind": (
                    "journal_commit"
                    if path.name == "journal.jsonl"
                    else "immutable_object"
                ),
                "s": time.perf_counter() - before,
                "bytes": len(data),
            }
        )
        return value

    workspace.atomic_write = measured
    wrapped = []
    try:
        for i in range(3):
            start = len(writes)
            before = time.perf_counter()
            result = asyncio.run(service.explore("qa", "run-" + str(i), req))
            elapsed = time.perf_counter() - before
            assert result["result_digest"] == expected
            sample = writes[start:]
            wrapped.append(
                {
                    "index": i + 1,
                    "facade_total_s": elapsed,
                    "worker_metrics": result["metrics"],
                    "journal_commit_s": sum(
                        r["s"] for r in sample if r["kind"] == "journal_commit"
                    ),
                    "immutable_object_write_s": sum(
                        r["s"] for r in sample if r["kind"] == "immutable_object"
                    ),
                    "write_count": len(sample),
                    "logical_result_digest": result["result_digest"],
                }
            )
    finally:
        workspace.atomic_write = original
        pool.close()
    value = {
        "schema": "levinmas-white-star-profile/1",
        "status": "PASS",
        "repetitions": {"raw": 3, "wrapped": 3, "total": 6},
        "cold_raw_import_native_s": cold,
        "worker_cold_readiness": readiness,
        "raw": raw,
        "wrapped": wrapped,
        "source_identity": identity,
        "standalone_median_s": statistics.median(
            r["standalone_adapter_s"] for r in raw
        ),
        "wrapped_median_s": statistics.median(r["facade_total_s"] for r in wrapped),
        "scope": "Same frozen Blok input, same machine, full timing samples kept; not literature quality and not transport/LLM time",
    }
    (args.out / "TIMING.json").write_text(json.dumps(value, indent=2) + "\n")
    print(
        canonical(
            {
                k: value[k]
                for k in (
                    "status",
                    "repetitions",
                    "standalone_median_s",
                    "wrapped_median_s",
                )
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    main(p.parse_args())
