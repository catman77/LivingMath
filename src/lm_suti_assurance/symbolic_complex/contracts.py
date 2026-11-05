"""Closed finite extension contracts; old symbolic schemas and ceilings unchanged."""

import time
from ..symbolic.contracts import (
    obj,
    arr,
    integer,
    REF,
    PROJECT,
    KEY,
    LIMITS as WORKER_LIMITS,
)
from ..white_star.contracts import check_schema
from ..core import canonical
from ..errors import AssuranceError

VERSION = "symbolic_complex_v1/1-patch003"
STRING = {"type": "string", "maxLength": 1024}
SOURCE = obj(
    {
        "kind": {"const": "sp_balanced_fixture"},
        "max_length": {"enum": [2, 4, 6, 8, 10]},
        "rewrite_rules": {"const": ["SP_TO_EMPTY", "PS_TO_EMPTY"]},
        "edge_identity": {"const": "source_position_rule"},
    },
    ["kind", "max_length", "rewrite_rules", "edge_identity"],
)
SAVED = obj(
    {
        "kind": {"const": "saved_symbolic_history"},
        "project": PROJECT,
        "run_id": REF,
        "only_verified_edges": {"const": True},
    },
    ["kind", "project", "run_id", "only_verified_edges"],
)
BUDGET = obj(
    {
        "max_vertices": integer(1, 8192),
        "max_edges": integer(1, 16384),
        "max_cells": integer(0, 5000),
        "max_cpu_ms": integer(1, 4000),
    },
    ["max_vertices", "max_edges", "max_cells", "max_cpu_ms"],
)
REQUEST = obj(
    {
        "schema": {"const": "livingmath-symbolic-complex-request/1"},
        "complex_source": {"oneOf": [SOURCE, SAVED]},
        "cells": obj(
            {
                "policy": {
                    "enum": ["all_local_peaks", "none", "bigons_only", "diamonds_only"]
                },
                "join_depth_limit": {"const": 1},
            },
            ["policy", "join_depth_limit"],
        ),
        "analysis": arr(
            {
                "enum": [
                    "graph_cycles",
                    "homology_F2",
                    "path_coherence",
                    "pi1_certificate",
                ]
            },
            4,
            1,
        ),
        "budgets": BUDGET,
    },
    ["schema", "complex_source", "cells", "analysis", "budgets"],
)


def validate(value, schema=REQUEST):
    try:
        check_schema(value, schema)
        raw = canonical(value).encode()
    except UnicodeError:
        raise AssuranceError("INVALID_UTF8", "/request")
    if len(raw) > WORKER_LIMITS["request_bytes"]:
        raise AssuranceError("INPUT_TOO_LARGE", "/request")
    return value


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.started = time.process_time()

    def check(self):
        if (time.process_time() - self.started) * 1000 > self.limits.get(
            "max_cpu_ms", 4000
        ):
            raise AssuranceError("BUDGET_EXCEEDED", "/budgets/max_cpu_ms")

    def count(self, name, n):
        if n > self.limits[name]:
            raise AssuranceError("BUDGET_EXCEEDED", "/budgets/" + name)
        self.check()
