"""Construct only the explicitly finite SP fixture; checker is a separate module."""

from itertools import combinations
import hashlib
from ..core import digest
from .contracts import validate, Budget


def rank_columns(columns):
    pivots = {}
    basis = []
    for index, column in enumerate(columns):
        value = column
        for _ in range(column.bit_length() + 1):
            if not value:
                break
            pivot = value.bit_length() - 1
            if pivot in pivots:
                value ^= pivots[pivot]
            else:
                pivots[pivot] = value
                basis.append(index)
                break
    return len(pivots), basis


def _identified(kind, **fields):
    return {"id": digest({"kind": kind, **fields}), **fields}


def _step(edge):
    return {"edge_id": edge, "sign": 1}


def analyze(request, source_artifact=None):
    validate(request)
    budget = Budget(request["budgets"])
    if request["complex_source"]["kind"] == "saved_symbolic_history":
        from .saved import build_saved

        return build_saved(request, source_artifact, budget)
    n = request["complex_source"]["max_length"]
    scope = digest(request["complex_source"])
    words = [""]
    for length in range(2, n + 1, 2):
        for positions in combinations(range(length), length // 2):
            selected = set(positions)
            words.append("".join("S" if i in selected else "P" for i in range(length)))
    words = sorted(words, key=lambda w: (len(w), w))
    budget.count("max_vertices", len(words))
    vertices = []
    by_word = {}
    for word in words:
        vertex = _identified(
            "sp_vertex/1",
            tokens=list(word),
            source_spans=[
                {
                    "source_sha256": hashlib.sha256(word.encode()).hexdigest(),
                    "byte_start": 0,
                    "byte_end": len(word),
                }
            ],
            object_scope=scope,
        )
        vertices.append(vertex)
        by_word[word] = vertex["id"]
    edges = []
    out = {w: [] for w in words}
    edge_map = {}
    for word in words:
        for i in range(len(word) - 1):
            pair = word[i : i + 2]
            if pair not in ("SP", "PS"):
                continue
            target = word[:i] + word[i + 2 :]
            edge = _identified(
                "rewrite_edge/1",
                src_id=by_word[word],
                dst_id=by_word[target],
                rule_id=pair + "_TO_EMPTY",
                match_span={"token_start": i, "token_end": i + 2},
                orientation="forward",
                provenance={
                    "generator_ref": scope,
                    "source_word_sha256": hashlib.sha256(word.encode()).hexdigest(),
                    "rule_version": "SP-cancel/1",
                },
                verified=True,
            )
            edges.append(edge)
            out[word].append(edge["id"])
            edge_map[edge["id"]] = edge
            budget.count("max_edges", len(edges))
    inverse = {i: w for w, i in by_word.items()}
    peaks = []
    cells = []
    peak_cells = {}
    for word in words:
        for left, right in combinations(out[word], 2):
            budget.check()
            a, b = edge_map[left]["dst_id"], edge_map[right]["dst_id"]
            join = None
            if a == b:
                kind = "bigon"
                lp = [left]
                rp = [right]
                join = a
            else:
                matches = [
                    (inverse[edge_map[g]["dst_id"]], g, h)
                    for g in out[inverse[a]]
                    for h in out[inverse[b]]
                    if edge_map[g]["dst_id"] == edge_map[h]["dst_id"]
                ]
                if matches:
                    _, g, h = min(matches)
                    kind = "diamond"
                    lp = [left, g]
                    rp = [right, h]
                    join = edge_map[g]["dst_id"]
                else:
                    kind = "unresolved"
                    lp = [left]
                    rp = [right]
            peak = _identified(
                "local_peak/1",
                src_id=by_word[word],
                edge_ids=sorted([left, right]),
                branch_kind=kind,
                join_state=join,
            )
            peaks.append(peak)
            policy = request["cells"]["policy"]
            if (
                join is None
                or policy == "none"
                or (policy == "bigons_only" and kind != "bigon")
                or (policy == "diamonds_only" and kind != "diamond")
            ):
                continue
            cell = _identified(
                "coherence_cell/1",
                left_path=[_step(i) for i in lp],
                right_path=[_step(i) for i in rp],
                src_id=by_word[word],
                dst_id=join,
                source_peak_id=peak["id"],
                role=kind,
                source_spans=next(
                    v["source_spans"] for v in vertices if v["id"] == by_word[word]
                ),
                rule_version="SP-cancel/1",
                verified=True,
                assumption_tags=["all_local_peaks_filled"],
                completion_search_budget=1,
            )
            cells.append(cell)
            peak_cells[frozenset([left, right])] = cell
            budget.count("max_cells", len(cells))
    edge_index = {e["id"]: i for i, e in enumerate(edges)}
    vertex_index = {v["id"]: i for i, v in enumerate(vertices)}
    d1 = [[vertex_index[e["src_id"]], vertex_index[e["dst_id"]]] for e in edges]
    d2 = []
    columns = []
    for cell in cells:
        value = 0
        for s in cell["left_path"] + cell["right_path"]:
            value ^= 1 << edge_index[s["edge_id"]]
        columns.append(value)
        d2.append(
            sorted(
                {
                    edge_index[s["edge_id"]]
                    for s in cell["left_path"] + cell["right_path"]
                    if (value >> edge_index[s["edge_id"]]) & 1
                }
            )
        )
    rank, basis = rank_columns(columns)
    lemmas = []
    canonical_paths = {}
    for word in words:
        if not word:
            canonical_paths[by_word[word]] = []
            continue
        canonical = out[word][0]
        tail = edge_map[canonical]["dst_id"]
        canonical_paths[by_word[word]] = [canonical] + canonical_paths[tail]
        for eid in out[word]:
            if eid == canonical:
                lemma = {
                    "edge_id": eid,
                    "case": "canonical",
                    "canonical_edge_id": canonical,
                    "cell_id": None,
                    "dependencies": [],
                }
            else:
                cell = peak_cells.get(frozenset([eid, canonical]))
                deps = []
                if cell:
                    deps = [
                        s["edge_id"]
                        for branch in (cell["left_path"], cell["right_path"])
                        for s in branch[1:]
                    ]
                lemma = {
                    "edge_id": eid,
                    "case": "local_peak",
                    "canonical_edge_id": canonical,
                    "cell_id": cell["id"] if cell else None,
                    "dependencies": deps,
                }
            lemmas.append(lemma)
    paths = {
        "schema": "livingmath-path-coherence/1",
        "algorithm": "strict-length-induction-on-canonical-SP-paths/1",
        "assumptions": ["all_local_peaks_filled", "terminating_SP_rewriting"],
        "base_vertex": by_word[""],
        "canonical_paths": canonical_paths,
        "lemmas": lemmas,
    }
    result = {
        "schema": "livingmath-symbolic-complex-artifacts/1",
        "engine": "symbolic_complex_v1",
        "input": request,
        "vertices": vertices,
        "edges": edges,
        "peaks": peaks,
        "cells": cells,
        "homology": {
            "field": "F2",
            "boundary_d1": d1,
            "boundary_d2": d2,
            "rank_d1": len(vertices) - 1,
            "rank_d2_F2": rank,
            "H1_dim": len(edges) - len(vertices) + 1 - rank,
            "basis_cell_ids": [cells[i]["id"] for i in basis],
        },
        "paths": paths if request["cells"]["policy"] == "all_local_peaks" else None,
        "diagnostics": [],
    }
    from .checker import verify

    checked = verify(result)
    budget.check()
    if checked["status"] == "REJECTED":
        from ..errors import AssuranceError

        raise AssuranceError(
            "INTERNAL_COMPLEX_ERROR",
            details={"message": str(checked["failed_obligations"])},
        )
    result["checks"] = checked
    result["summary"] = {
        "vertices": len(vertices),
        "edges": len(edges),
        "components": checked["components"],
        "graph_beta1": checked["graph_beta1"],
        "local_peaks": len(peaks),
        "verified_cells": len(cells),
        "rank_d2_F2": rank,
        "dim_H1_F2": checked["H1_dim"],
        "pi1_status": checked["pi1_status"],
        "pi1_basis": "based_at_empty_word",
        "assumptions": (
            ["terminating_SP_rewriting"]
            + (["all_local_peaks_filled"] if checked["missing_peaks"] == 0 else [])
        ),
        "selected_cells_policy": request["cells"]["policy"],
        "partial_attachment": checked["missing_peaks"] > 0,
        "graph_pi1_free_rank": checked["graph_beta1"],
        "unresolved_peaks": checked["missing_peaks"],
        "claim_status": "CHECKED_FINITE_INSTANCE",
        "execution_permission": False,
    }
    return result
