"""Deterministic unique closed worlds compatible with unchanged FOL semantics."""
from itertools import product
from ...formal_bridge import fol
from ...formal_bridge.ir import Bound


class FiniteModelCursor:
    """One model stream shared across all pairs; no direction restarts."""
    def __init__(self, signature):
        fol.signature(signature)
        self.signature = signature
        self.iterator = self._models()

    def _models(self):
        for size in (1, 2):
            domains = {s: [s + ':' + str(i) for i in range(size)] for s in sorted(self.signature['sorts'])}
            cells = [(name, list(row)) for name, sorts in sorted(self.signature['predicates'].items())
                     for row in product(*(domains[s] for s in sorts))]
            if len(cells) > 16:
                raise Bound('RELATION_CELL_BOUND')
            for bits in product((False, True), repeat=len(cells)):
                relations = {name: [] for name in sorted(self.signature['predicates'])}
                for (name, row), bit in zip(cells, bits):
                    if bit:
                        relations[name].append(row)
                yield {'domains': domains, 'relations': relations, 'world': 'closed'}

    def __next__(self):
        return next(self.iterator)
