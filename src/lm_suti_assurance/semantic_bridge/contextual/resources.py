"""Per-pair fuel and CPU shares charged into the unchanged global research budget."""
from contextlib import contextmanager
import time
from ...formal_bridge import fol
from ...formal_bridge.ir import Bound


class PairBound(Bound):
    pass


class PairWork:
    def __init__(self, parent, steps, cpu_ms):
        self.parent = parent
        self.max_steps = steps
        self.max_cpu_ms = cpu_ms
        self.steps = 0
        self.cpu_used = 0.0
        self.started = None
        self.before_evaluate = None

    def elapsed_ms(self):
        return self.cpu_used + (0 if self.started is None else (time.process_time() - self.started) * 1000)

    @contextmanager
    def active(self):
        self.started = time.process_time()
        try:
            yield self
        finally:
            self.cpu_used += (time.process_time() - self.started) * 1000
            self.started = None

    def charge(self, n):
        self.steps += n
        self.parent.counter.steps += n
        self.parent.tick(0)
        if self.steps > self.max_steps or self.elapsed_ms() > self.max_cpu_ms:
            raise PairBound('PAIR_STEP_OR_CPU_BOUND')

    def tick(self, n=1):
        if self.steps + n > self.max_steps:
            raise PairBound('PAIR_STEP_BOUND')
        self.charge(n)

    def evaluate(self, formula, signature, model):
        self.tick()
        steps = min(self.max_steps - self.steps, self.parent.bounds['max_steps'] - self.parent.counter.steps)
        cpu = min(self.max_cpu_ms - self.elapsed_ms(), self.parent.bounds['max_cpu_ms'] - (time.process_time() - self.parent.counter.started) * 1000)
        if steps <= 0 or cpu <= 0:
            raise PairBound('PAIR_EVALUATION_BOUND')
        bounds = {**self.parent.bounds, 'max_steps': steps, 'max_cpu_ms': max(1, int(cpu))}
        if self.before_evaluate:
            self.before_evaluate()
        value = fol.evaluate(formula, signature, model, bounds)
        if value['status'] == 'UNKNOWN_BOUND':
            # FOL returns no visited-node count on a cutoff; charge the actual granted
            # allocation conservatively, never the other pairs' reserved allocations.
            self.charge(steps)
            raise PairBound('PAIR_FORMULA_EVALUATION_BOUND')
        self.charge(value.get('evaluated_nodes', 1))
        return value
