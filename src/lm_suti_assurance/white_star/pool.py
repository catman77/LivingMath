"""Two fixed warm workers, bounded queue, no server module-name collisions."""

import json
import os
from pathlib import Path
import queue
import select
import subprocess
import sys
import threading
import time
from ..core import canonical
from ..errors import AssuranceError
from .contracts import LIMITS

WORKER = Path(__file__).with_name("worker.py")


def environment():
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": "/nonexistent",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def prepare() -> dict:
    cp = subprocess.run(
        [sys.executable, "-I", "-B", str(WORKER), "--prepare"],
        capture_output=True,
        text=True,
        env=environment(),
        timeout=90,
    )
    try:
        result = json.loads(cp.stdout)
    except ValueError:
        raise AssuranceError(
            "ENGINE_UNAVAILABLE", details={"message": cp.stderr[-1000:]}
        )
    if cp.returncode or not result.get("ready"):
        raise AssuranceError("ENGINE_UNAVAILABLE", details=result)
    return result


class Worker:
    def __init__(self):
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment(),
        )
        if not select.select([self.process.stdout], [], [], 20)[0]:
            self.close()
            raise AssuranceError("ENGINE_UNAVAILABLE")
        try:
            self.ready = json.loads(self.process.stdout.readline())
        except (ValueError, OSError):
            self.close()
            raise AssuranceError("ENGINE_UNAVAILABLE") from None
        if not self.ready.get("ready"):
            self.close()
            raise AssuranceError("ENGINE_UNAVAILABLE", details=self.ready)

    def run(self, packet: dict) -> dict:
        if self.process.poll() is not None:
            raise AssuranceError("ENGINE_UNAVAILABLE")
        self.process.stdin.write(canonical(packet).encode() + b"\n")
        self.process.stdin.flush()
        if not select.select(
            [self.process.stdout], [], [], LIMITS["worker_wall_s"] + 3
        )[0]:
            self.close()
            raise AssuranceError("WORKER_LIMIT")
        raw = self.process.stdout.readline(LIMITS["result_bytes"] + 128 * 1024)
        if not raw or not raw.endswith(b"\n"):
            raise AssuranceError("ENGINE_UNAVAILABLE")
        return json.loads(raw)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()


class Pool:
    def __init__(self):
        self.slots = threading.BoundedSemaphore(
            LIMITS["concurrent_jobs"] + LIMITS["queue"]
        )
        self.queue = queue.Queue()
        self.workers = []
        self.error = None
        try:
            for _ in range(LIMITS["concurrent_jobs"]):
                w = Worker()
                self.workers.append(w)
                self.queue.put(w)
        except AssuranceError as e:
            self.error = e.as_dict()
            self.close()

    def status(self) -> dict:
        return {
            "ready": bool(self.workers) and self.error is None,
            "workers": [w.ready for w in self.workers],
            "error": self.error,
        }

    def run(self, packet: dict) -> dict:
        if self.error is not None or not self.workers:
            raise AssuranceError("ENGINE_UNAVAILABLE")
        if not self.slots.acquire(blocking=False):
            raise AssuranceError(
                "WORKER_LIMIT",
                details={"message": "Two active jobs and16 queued requests maximum"},
            )
        w = None
        try:
            w = self.queue.get()
            value = w.run(packet)
            if not value["ok"]:
                e = value["error"]
                raise AssuranceError(
                    e["code"],
                    e.get("field_path"),
                    {"message": e.get("message", e["code"])},
                )
            return value
        finally:
            if w is not None:
                self.queue.put(w)
            self.slots.release()

    def close(self):
        for w in self.workers:
            w.close()
        self.workers = []
