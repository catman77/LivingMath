"""Observation source only. No TSP matrix, objective or solver is accepted.

The pair algebra, WhiteStarOrbit and CAD maps are the prior executable
primitives. The bounded novelty rule is from V2 BudgetedUDAV, purpose=novelty.
This adapter exposes their symbolic observations at NOBS's encoder boundary.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import pandas as pd

PRIMITIVES = Path(__file__).resolve().parent / "source_primitives"
if str(PRIMITIVES) not in sys.path:
    sys.path.insert(0, str(PRIMITIVES))

from cad import CHARTS, project
from udav import GraphTopology, ReversibleUDAV, WhiteStarOrbit


@dataclass(frozen=True)
class Observation:
    step: int
    numerator: tuple[int, int]
    denominator: tuple[int, int]
    witness: tuple[int, int]
    finite_fibre_layer: int
    candidate_views: tuple[int, ...]
    candidate_scores: tuple[tuple[float, ...], ...]
    view: int
    matrix: tuple[int, int, int, int]
    coordinates: tuple[int, int]
    direction_defined: bool
    euclid_quotients: tuple[int, ...]
    gcd: int
    signature: tuple[int, ...]
    state: str

    def to_dict(self):
        return asdict(self)


class WhiteStarSource:
    """One division witness and at most k CAD observations per step.

    'active' uses the existing V2 novelty rule, without its TSP context bridge.
    'fixed' is a diagnostic control with the identity chart.
    Only the selected observation updates the observation graph, as in V2.
    The witness stream itself is the old lazy triangular-layer traversal.
    """

    def __init__(self, seed: int = 42, k: int = 3, mode: str = "active"):
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= len(CHARTS):
            raise ValueError(f"k must be an integer in 1..{len(CHARTS)}")
        if mode not in ("active", "fixed"):
            raise ValueError("mode must be active or fixed")
        self.seed, self.k, self.mode = seed, k, mode
        self.orbit = WhiteStarOrbit(seed)
        self.reversible = ReversibleUDAV(seed)
        self.graph = GraphTopology()
        self.prev = None
        self.seen, self.used, self.phase = Counter(), Counter(), Counter()
        self.steps, self.projections = 0, 0

    @staticmethod
    def state_of(witness, projection) -> str:
        # Same coarse observation map as the prior source_to_tsp.py:
        # capped Euclid depth (0..4) and within-quadrant phase bin (0..7).
        # The complete witness and signed coordinates stay in Observation.
        if witness.direction == (0, 0):
            return "WS:unresolved"
        return f"WS:E{min(projection.signature[0], 4)}:A{projection.signature[-1]}"

    def next(self) -> Observation:
        self.steps += 1
        witness = self.orbit.next()
        if not witness.verify():
            raise ValueError("invalid division witness")
        schedule_state = self.reversible.step()
        first = (schedule_state + self.steps * 7 + self.seed) % len(CHARTS)
        views = ((0,) if self.mode == "fixed" else
                 tuple((first + i * 11) % len(CHARTS) for i in range(self.k)))
        candidates, scores = [], []
        for view in views:
            projection = project(witness, view)
            self.projections += 1
            nv, ne, nc = self.graph.novelty(self.prev, projection.signature)
            novelty = min(1.0, (3 * nv + 1.5 * ne + 2 * nc) / 6.5)
            score = (novelty, 1 / (1 + self.seen[projection.signature]),
                     1 / (1 + self.phase[projection.signature[-1]]),
                     1 / (1 + self.used[view]))
            candidates.append(projection)
            scores.append(score)
        # Stable first-candidate tie break matches BudgetedUDAV.random().
        selected = max(range(len(views)), key=lambda i: scores[i])
        projection = candidates[selected]
        self.graph.add(self.prev, projection.signature)
        self.prev = projection.signature
        self.seen[projection.signature] += 1
        self.used[projection.view] += 1
        self.phase[projection.signature[-1]] += 1
        a, b = witness.direction
        return Observation(
            step=self.steps - 1,
            numerator=(witness.numerator.s, witness.numerator.p),
            denominator=(witness.denominator.s, witness.denominator.p),
            witness=(a, b), finite_fibre_layer=a + b,
            candidate_views=views, candidate_scores=tuple(scores),
            view=projection.view, matrix=projection.matrix,
            coordinates=(projection.a, projection.b),
            direction_defined=bool(a or b),
            euclid_quotients=projection.quotients, gcd=projection.gcd,
            signature=projection.signature,
            state=self.state_of(witness, projection),
        )

    def snapshot(self) -> dict:
        return dict(steps=self.steps, projections=self.projections,
                    charts_used=len(self.used), available_charts=len(CHARTS),
                    full_signatures=len(self.seen),
                    observation_vertices=len(self.graph.parent),
                    observation_edges=len(self.graph.edges),
                    beta0=self.graph.beta0, beta1=self.graph.beta1)


class WhiteStarEncoder:
    """Drop-in encode(frame) -> Series; frame supplies only length and index.

    Every call starts the same source afresh, like an archive encoder. For
    incremental observation use WhiteStarSource.next() directly.
    """

    def __init__(self, seed: int = 42, k: int = 3, mode: str = "active"):
        WhiteStarSource(seed, k, mode)  # Validate before any experiment starts.
        self.seed, self.k, self.mode = seed, k, mode
        self.trace: list[Observation] = []
        self.diagnostics: dict = {}

    def encode(self, frame: pd.DataFrame) -> pd.Series:
        source = WhiteStarSource(self.seed, self.k, self.mode)
        self.trace = [source.next() for _ in range(len(frame))]
        self.diagnostics = source.snapshot()
        return pd.Series([record.state for record in self.trace],
                         index=frame.index, dtype=object)
