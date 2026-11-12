"""Reuse bounded transport and the existing numeric shared job budget."""
from pathlib import Path
from ..symbolic.executor import Executor as BaseExecutor


class Executor(BaseExecutor):
    def __init__(self, shared_budget=None):
        super().__init__(Path(__file__).with_name('worker.py'), shared_budget=shared_budget)
