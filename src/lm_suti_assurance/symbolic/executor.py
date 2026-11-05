"""Reuse the existing bounded worker transport/pool without changing historical code."""

import json, queue, select, subprocess, sys, threading
from pathlib import Path
from ..errors import AssuranceError
from ..white_star.pool import Pool as NumericalPool, Worker as Transport, environment
from .contracts import LIMITS


class Worker(Transport):
    def __init__(self):
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).with_name("worker.py"))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment(),
        )
        try:
            if not select.select([self.process.stdout], [], [], 20)[0]:
                raise AssuranceError("ENGINE_UNAVAILABLE")
            self.ready = json.loads(self.process.stdout.readline())
            if not self.ready.get("ready"):
                raise AssuranceError("ENGINE_UNAVAILABLE", details=self.ready)
        except Exception:
            self.close()
            raise


class Executor(NumericalPool):
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
        except (AssuranceError, ValueError, OSError) as exc:
            self.error = {"code": "ENGINE_UNAVAILABLE", "message": str(exc)}
            self.close()
