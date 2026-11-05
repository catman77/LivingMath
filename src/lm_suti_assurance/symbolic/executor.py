"""Reuse the existing bounded worker transport/pool without changing historical code."""

import json, queue, select, subprocess, sys, threading
from pathlib import Path
from ..errors import AssuranceError
from ..white_star.pool import Pool as NumericalPool, Worker as Transport, environment
from .contracts import LIMITS


class Worker(Transport):
    def __init__(self, worker_path: Path | None = None):
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                str(worker_path or Path(__file__).with_name("worker.py")),
            ],
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
    def __init__(self, worker_path: Path | None = None, shared_budget=None):
        self.shared_budget = shared_budget
        self.slots = threading.BoundedSemaphore(
            LIMITS["concurrent_jobs"] + LIMITS["queue"]
        )
        self.queue = queue.Queue()
        self.workers = []
        self.error = None
        try:
            for _ in range(LIMITS["concurrent_jobs"]):
                w = Worker(worker_path)
                self.workers.append(w)
                self.queue.put(w)
        except (AssuranceError, ValueError, OSError) as exc:
            self.error = {"code": "ENGINE_UNAVAILABLE", "message": str(exc)}
            self.close()

    def run(self, packet: dict) -> dict:
        if self.shared_budget is None:
            return super().run(packet)
        return self.shared_budget.call(lambda: super(Executor, self).run(packet))


class SharedBudget:
    """The original2 active/16 queued quota covers current and historical profiles."""

    def __init__(self):
        self.slots = threading.BoundedSemaphore(
            LIMITS["concurrent_jobs"] + LIMITS["queue"]
        )
        self.active = threading.BoundedSemaphore(LIMITS["concurrent_jobs"])

    def call(self, operation):
        if not self.slots.acquire(blocking=False):
            raise AssuranceError(
                "WORKER_LIMIT",
                details={"message": "Shared symbolic profile quota:2 active,16 queued"},
            )
        try:
            with self.active:
                return operation()
        finally:
            self.slots.release()
