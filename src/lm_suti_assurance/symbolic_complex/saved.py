"""Import only actual stored operations; never complete missing histories by words/q."""

from itertools import combinations
from ..core import digest
from ..symbolic.state import require
from .model import _identified, rank_columns


def build_saved(request, artifact, budget):
    require(isinstance(artifact, dict), "SOURCE_REQUIRED", "/complex_source")
    states = {s["node_id"]: s for s in artifact["states"]}
    vertices = []
    mapping = {}
    scope = digest(request["complex_source"])
    for ident, state in states.items():
        vertex = _identified(
            "saved_vertex/1",
            tokens=state["tokens"],
            source_spans=state["source_spans"],
            object_scope=scope,
            lineage_ref=ident,
        )
        mapping[ident] = vertex["id"]
        vertices.append(vertex)
        budget.count("max_vertices", len(vertices))
    edges = []
    allowed = {
        "CONCAT",
        "SPLIT",
        "RENAME",
        "SUBSTITUTE",
        "REVERSE",
        "SP_INV",
        "REDUCE_SP",
        "INSERT_CANCEL_PAIR",
    }
    for node in artifact["history"]:
        if node["op"] not in allowed:
            continue
        edge = _identified(
            "rewrite_edge/1",
            src_id=mapping[node["parent_ids"][0]],
            dst_id=mapping[node["node_id"]],
            rule_id=node["op"],
            match_span={"source_event_ranges": node["events"]},
            orientation="forward",
            provenance={
                "history_node_id": node["node_id"],
                "parent_ids": node["parent_ids"],
                "op_args": node["op_args"],
                "source_artifact_digest": digest(artifact),
            },
            verified=True,
        )
        edges.append(edge)
        budget.count("max_edges", len(edges))
    out = {v["id"]: [] for v in vertices}
    em = {e["id"]: e for e in edges}
    for e in edges:
        out[e["src_id"]].append(e["id"])
    peaks = []
    cells = []
    for src, ids in out.items():
        for a, b in combinations(ids, 2):
            budget.check()
            peaks.append(
                _identified(
                    "local_peak/1",
                    src_id=src,
                    edge_ids=sorted([a, b]),
                    branch_kind="unresolved",
                    join_state=None,
                )
            )
    # A provenance DAG's distinct child nodes do not become a common endpoint
    # merely because their token words agree. No synthetic joins are inserted.
    vi = {v["id"]: i for i, v in enumerate(vertices)}
    d1 = [[vi[e["src_id"]], vi[e["dst_id"]]] for e in edges]
    r1, _ = rank_columns([sum(1 << i for i in column) for column in d1])
    beta = len(edges) - r1
    result = {
        "schema": "livingmath-symbolic-complex-artifacts/1",
        "engine": "symbolic_complex_v1",
        "input": request,
        "source_artifact": artifact,
        "vertices": vertices,
        "edges": edges,
        "peaks": peaks,
        "cells": cells,
        "homology": {
            "field": "F2",
            "boundary_d1": d1,
            "boundary_d2": [],
            "rank_d1": r1,
            "rank_d2_F2": 0,
            "H1_dim": beta,
            "basis_cell_ids": [],
        },
        "paths": None,
        "source_check": {"status": "CHECKED_INSTANCE"},
        "diagnostics": [
            {
                "status": "UNRESOLVED_PEAK",
                "scope": "stored provenance-node incidences only; equal words never manufacture a shared endpoint",
                "count": len(peaks),
            }
        ],
    }
    from .checker import verify

    check = verify(result)
    require(check["status"] != "REJECTED", "UNVERIFIED_EDGE")
    result["checks"] = check
    result["summary"] = {
        "vertices": len(vertices),
        "edges": len(edges),
        "components": check["components"],
        "graph_beta1": check["graph_beta1"],
        "local_peaks": len(peaks),
        "verified_cells": 0,
        "rank_d2_F2": 0,
        "dim_H1_F2": beta,
        "pi1_status": "NOT_PROVED",
        "assumptions": ["only_actual_saved_operations"],
        "unresolved_peaks": len(peaks),
        "execution_permission": False,
    }
    return result
