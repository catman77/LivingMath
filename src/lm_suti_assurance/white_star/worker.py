"""Warm fixed-code supervisor; each bounded job forks a fresh native state."""

import argparse
import json
import math
import os
from pathlib import Path
import resource
import select
import signal
import sys
import time

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lm_suti_assurance.core import canonical, strict_json, digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.white_star.contracts import LIMITS, preflight
from lm_suti_assurance.offline import isolated


def execute(packet, adapter, ops, metrics=None):
    from lm_suti_assurance.white_star.formal import evaluate

    if packet["action"] == "explore":
        timer = time.perf_counter()
        preflight(packet["request"])
        if metrics is not None:
            metrics["source_preflight_s"] = time.perf_counter() - timer
        original = adapter.search

        def timed_search(*args, **kwargs):
            timer = time.perf_counter()
            value = original(*args, **kwargs)
            if metrics is not None:
                metrics["numeric_kernel_search_s"] = time.perf_counter() - timer
            return value

        adapter.search = timed_search
        with isolated():
            result = adapter.explore(packet["request"])
        return result
    if packet["action"] == "model":
        with isolated():
            return evaluate(packet["proposal"], ops)
    if packet["action"] == "replay":
        from lm_suti_assurance.white_star.bundle import replay_inside_worker

        return replay_inside_worker(packet["bundle_base64"], adapter, ops)
    raise AssuranceError("INVALID_INPUT")


def bounded(packet, adapter, ops):
    read, write = os.pipe()
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        os.close(read)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (LIMITS["worker_memory_bytes"],) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["worker_cpu_s"],) * 2)
            before = time.process_time()
            timer = time.perf_counter()
            metrics = {}
            result = execute(packet, adapter, ops, metrics)
            metrics["warm_adapter_or_check_s"] = time.perf_counter() - timer
            timer = time.perf_counter()
            canonical(result)
            metrics["result_serialization_s"] = time.perf_counter() - timer
            response = {
                "ok": True,
                "data": result,
                "metrics": {
                    **metrics,
                    "job_cpu_s": time.process_time() - before,
                    "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                },
            }
        except AssuranceError as exc:
            response = {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": (exc.details or {}).get("message", exc.code),
                    "field_path": exc.field or "",
                },
            }
        except (ValueError, KeyError, TypeError, OverflowError, MemoryError) as exc:
            response = {
                "ok": False,
                "error": {
                    "code": (
                        "WORKER_LIMIT"
                        if isinstance(exc, MemoryError)
                        else getattr(exc, "code", "INVALID_INPUT")
                    ),
                    "message": str(exc)[:1000],
                    "field_path": "",
                },
            }
        try:
            raw = canonical(response).encode()
            if len(raw) > LIMITS["result_bytes"] + 65536:
                raw = b'{"ok":false,"error":{"code":"RESULT_TOO_LARGE","message":"32MiB result limit","field_path":""}}'
            with os.fdopen(write, "wb", buffering=0) as out:
                view = memoryview(raw)
                while view:
                    view = view[out.write(view) :]
        finally:
            os._exit(0)
    os.close(write)
    parts = []
    count = 0
    deadline = started + LIMITS["worker_wall_s"]
    timed = False
    try:
        while True:
            remaining = deadline - time.perf_counter()
            if (
                remaining <= 0
                or not select.select([read], [], [], max(0, remaining))[0]
            ):
                timed = True
                break
            chunk = os.read(read, 65536)
            if not chunk:
                break
            count += len(chunk)
            if count > LIMITS["result_bytes"] + 65536:
                timed = True
                break
            parts.append(chunk)
        if timed:
            os.kill(pid, signal.SIGKILL)
    finally:
        os.close(read)
        _, status = os.waitpid(pid, 0)
    if timed or status:
        return {
            "ok": False,
            "error": {
                "code": "WORKER_LIMIT",
                "message": "Bounded numerical job interrupted or exceeded CPU/wall/memory profile",
                "field_path": "",
            },
        }
    try:
        result = strict_json(b"".join(parts).decode())
        result["worker_wall_s"] = time.perf_counter() - started
        return result
    except (ValueError, UnicodeError):
        return {
            "ok": False,
            "error": {
                "code": "ENGINE_UNAVAILABLE",
                "message": "Worker exited without a valid result",
                "field_path": "",
            },
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true")
    a = p.parse_args()
    start = time.perf_counter()
    from lm_suti_assurance.white_star.runtime import load

    try:
        adapter, ops, identity = load(a.prepare)
    except Exception as exc:
        print(
            canonical(
                {
                    "ready": False,
                    "code": "ENGINE_UNAVAILABLE",
                    "message": str(exc)[:1000],
                }
            ),
            flush=True,
        )
        return 2
    ready = {
        "ready": True,
        **identity,
        "cold_import_native_s": time.perf_counter() - start,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    if not a.prepare:
        from lm_suti_assurance.white_star.isolation import restrict

        ready["isolation"] = restrict()
    print(canonical(ready), flush=True)
    if a.prepare:
        return 0
    # Imports and native loading precede this audit boundary. The job cannot
    # open sockets, invoke models/compilers/subprocesses or load new libraries.
    for line in sys.stdin.buffer:
        try:
            if len(line) > 48 * 1024 * 1024:
                raise AssuranceError("INPUT_TOO_LARGE")
            packet = strict_json(line.decode())
            result = bounded(packet, adapter, ops)
        except AssuranceError as e:
            result = {
                "ok": False,
                "error": {
                    "code": e.code,
                    "message": e.code,
                    "field_path": e.field or "",
                },
            }
        print(canonical(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
