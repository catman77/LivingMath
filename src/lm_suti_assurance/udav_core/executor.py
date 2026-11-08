"""New isolated policies share the existing2-active/16-queued engine quotas."""
from pathlib import Path
from ..symbolic.executor import Executor as BaseExecutor


class BudgetedPool:
    def __init__(self,pool,budget):self.pool=pool;self.budget=budget
    def run(self,packet):return self.budget.call(lambda:self.pool.run(packet))
    def status(self):return self.pool.status()
    def close(self):self.pool.close()


class Executor(BaseExecutor):
    def __init__(self,symbolic_budget,numeric_budget):
        self.policy_budgets={'symbolic':symbolic_budget,'numeric':numeric_budget}
        super().__init__(Path(__file__).with_name('worker.py'))
    def run(self,packet):
        budget=self.policy_budgets[packet['engine']]
        return budget.call(lambda:super(Executor,self).run(packet))
