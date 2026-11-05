"""Fixed isolated symbolic supervisor; fresh fork per job, actual supplied UDAV clock."""

import os, sys, resource, select, signal, time
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lm_suti_assurance.core import canonical, strict_json
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.symbolic.contracts import LIMITS
from lm_suti_assurance.symbolic.kernel import run
from lm_suti_assurance.offline import isolated


def bounded(packet, clock):
    read, write = os.pipe()
    started = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        os.close(read)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (LIMITS["worker_memory_bytes"],) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["worker_cpu_s"],) * 2)
            before = time.process_time()
            with isolated():
                if packet["action"] == "explore":
                    data = run(packet["request"], clock)
                elif packet["action"] == "replay":
                    from lm_suti_assurance.symbolic.bundle import replay

                    data = replay(packet["bundle_base64"], clock)
                elif packet["action"] in (
                    "extension_run",
                    "complex_verify",
                    "extension_replay",
                ):
                    from lm_suti_assurance.symbolic_complex.app import dispatch

                    data = dispatch(packet)
                else:
                    raise AssuranceError("INVALID_INPUT")
            value = {
                "ok": True,
                "data": data,
                "metrics": {
                    "job_cpu_s": time.process_time() - before,
                    "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "LLM_calls": 0,
                },
            }
            raw = canonical(value).encode()
            if len(raw) > LIMITS["result_bytes"]:
                raise AssuranceError("RESULT_TOO_LARGE")
        except AssuranceError as exc:
            raw = canonical(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": (exc.details or {}).get("message", exc.code),
                        "field_path": exc.field or "",
                    },
                }
            ).encode()
        except Exception as exc:
            raw = canonical(
                {
                    "ok": False,
                    "error": {
                        "code": (
                            "WORKER_LIMIT"
                            if isinstance(exc, MemoryError)
                            else "INTERNAL_SYMBOLIC_ERROR"
                        ),
                        "message": str(exc)[:512],
                        "field_path": "",
                    },
                }
            ).encode()
        try:
            with os.fdopen(write, "wb", buffering=0) as out:
                view = memoryview(raw)
                while view:
                    view = view[out.write(view) :]
        finally:
            os._exit(0)
    os.close(write)
    parts = []
    size = 0
    deadline = started + LIMITS["worker_wall_s"]
    timed = False
    try:
        while True:
            left = deadline - time.perf_counter()
            if left <= 0 or not select.select([read], [], [], max(0, left))[0]:
                timed = True
                break
            chunk = os.read(read, 65536)
            if not chunk:
                break
            size += len(chunk)
            if size > LIMITS["result_bytes"] + 65536:
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
                "message": "Symbolic CPU/wall/memory or result quota exceeded",
                "field_path": "",
            },
        }
    try:
        value = strict_json(b"".join(parts).decode())
        value["worker_wall_s"] = time.perf_counter() - started
        return value
    except ValueError:
        return {
            "ok": False,
            "error": {
                "code": "ENGINE_UNAVAILABLE",
                "message": "No valid symbolic worker response",
                "field_path": "",
            },
        }


def main():
    try:
        # Import only installed, hash-checked original code before the audit boundary.
        from lm_suti_assurance.white_star.runtime import load

        _, _, identity = load()
        from udav import ReversibleUDAV
        from lm_suti_assurance.symbolic import (
            bundle,
        )  # preload ZIP dependencies before isolation

        # Preload the additive engines before the same existing audit boundary.
        from lm_suti_assurance.symbolic_complex import (
            app as extension_app,
            bundle as extension_bundle,
        )
        from lm_suti_assurance.symbolic_complex import saved as saved_complex
        from lm_suti_assurance.white_star.isolation import restrict

        isolation = restrict()
        print(
            canonical(
                {
                    "ready": True,
                    "engine": "symbolic_v1",
                    "clock": "supplied ReversibleUDAV",
                    "numeric": identity,
                    "isolation": isolation,
                }
            ),
            flush=True,
        )
    except Exception as exc:
        print(
            canonical(
                {
                    "ready": False,
                    "code": "ENGINE_UNAVAILABLE",
                    "message": str(exc)[:512],
                }
            ),
            flush=True,
        )
        return 2
    while True:
        raw = sys.stdin.buffer.readline(64 * 1024 * 1024 + 1)
        if not raw:
            return 0
        try:
            if len(raw) > 64 * 1024 * 1024:
                raise AssuranceError("INPUT_TOO_LARGE")
            value = bounded(strict_json(raw.decode()), ReversibleUDAV)
        except AssuranceError as exc:
            value = {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": exc.code,
                    "field_path": exc.field or "",
                },
            }
        print(canonical(value), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
