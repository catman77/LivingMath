"""Production implementation/checker differential and adversarial finite SP gates."""

import copy
import json
from pathlib import Path
import pytest
from lm_suti_assurance.symbolic_complex.model import analyze
from lm_suti_assurance.symbolic_complex.checker import verify


def request(n=6, policy="all_local_peaks"):
    return {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "sp_balanced_fixture",
            "max_length": n,
            "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
            "edge_identity": "source_position_rule",
        },
        "cells": {"policy": policy, "join_depth_limit": 1},
        "analysis": [
            "graph_cycles",
            "homology_F2",
            "path_coherence",
            "pi1_certificate",
        ],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }


@pytest.mark.parametrize(
    "n,expected",
    [
        (2, (3, 2, 0, 0, 0)),
        (4, (9, 14, 6, 8, 6)),
        (6, (29, 74, 46, 80, 46)),
        (8, (99, 354, 256, 560, 256)),
        (10, (351, 1614, 1264, 3360, 1264)),
    ],
)
def test_exact_counts_and_independent_path_checker(n, expected):
    result = analyze(request(n))
    s = result["summary"]
    assert (
        tuple(
            s[k]
            for k in (
                "vertices",
                "edges",
                "graph_beta1",
                "verified_cells",
                "rank_d2_F2",
            )
        )
        == expected
    )
    assert s["dim_H1_F2"] == 0 and s["pi1_status"] == "PROVED_TRIVIAL_WITH_CERTIFICATE"
    check = verify(result)
    assert (
        check["status"] == "CHECKED_INSTANCE" and check["pi1_status"] == s["pi1_status"]
    )
    assert (
        result["paths"]["lemmas"] and result["homology"]["basis_cell_ids"] is not None
    )


@pytest.mark.parametrize("policy", ["none", "bigons_only", "diamonds_only"])
def test_partial_faces_are_not_a_pi1_proof(policy):
    result = analyze(request(8, policy))
    assert result["summary"]["pi1_status"] == "NOT_PROVED"
    assert verify(result)["status"] == "NOT_PROVED"
    if policy == "none":
        assert result["summary"]["dim_H1_F2"] == 256
        assert result["summary"]["graph_pi1_free_rank"] == 256


@pytest.mark.parametrize(
    "mutation",
    [
        "edge_position",
        "cell_endpoint",
        "missing_face",
        "cyclic_proof",
        "wrong_child",
        "fake_homology",
        "fake_flag",
    ],
)
def test_corrupt_certificate_is_rejected_or_not_proved(mutation):
    result = copy.deepcopy(analyze(request()))
    if mutation == "edge_position":
        result["edges"][0]["match_span"]["token_start"] = 99
    if mutation == "cell_endpoint":
        result["cells"][0]["dst_id"] = "f" * 64
    if mutation == "missing_face":
        result["cells"].pop()
    if mutation == "cyclic_proof":
        result["paths"]["lemmas"][0]["dependencies"] = [
            result["paths"]["lemmas"][0]["edge_id"]
        ]
    if mutation == "wrong_child":
        result["paths"]["lemmas"][-1]["dependencies"] = ["f" * 64]
    if mutation == "fake_homology":
        result["homology"]["rank_d2_F2"] += 1
    if mutation == "fake_flag":
        result["input"]["complex_source"]["kind"] = "untrusted_graph"
        result["summary"]["pi1_status"] = "PROVED_TRIVIAL_WITH_CERTIFICATE"
    verdict = verify(result)
    assert verdict["status"] in ("REJECTED", "NOT_PROVED")
    assert verdict["failed_obligations"]


def test_positions_parallel_edges_and_sp_involution_incidence():
    result = analyze(request(6))
    vertices = {v["id"]: "".join(v["tokens"]) for v in result["vertices"]}
    duplicates = {}
    for e in result["edges"]:
        duplicates.setdefault((e["src_id"], e["dst_id"]), []).append(e)
    assert any(len(es) > 1 for es in duplicates.values())
    assert (
        len(
            {
                v["id"]
                for v in result["vertices"]
                if "".join(v["tokens"]) in ("SSPP", "SPSP")
            }
        )
        == 2
    )
    mapping = {
        v: next(
            k
            for k, w in vertices.items()
            if w == vertices[v].translate(str.maketrans("SP", "PS"))
        )
        for v in vertices
    }
    signatures = {
        (e["src_id"], e["dst_id"], e["match_span"]["token_start"])
        for e in result["edges"]
    }
    assert all((mapping[a], mapping[b], p) in signatures for a, b, p in signatures)
    assert len({c["id"] for c in result["cells"]}) == len(result["cells"])


def test_determinism_invalid_n_and_budget():
    from lm_suti_assurance.core import digest
    from lm_suti_assurance.errors import AssuranceError

    assert digest(analyze(request(4))) == digest(analyze(request(4)))
    with pytest.raises(AssuranceError):
        analyze(request(11))
    q = request()
    q["budgets"]["max_vertices"] = 10
    with pytest.raises(AssuranceError) as error:
        analyze(q)
    assert error.value.code == "BUDGET_EXCEEDED"


def test_zero_homology_without_complete_path_coherence_is_not_pi1_proof():
    from lm_suti_assurance.symbolic_complex.model import rank_columns

    result = analyze(request(4))
    homology = result["homology"]
    rows = homology["boundary_d2"]
    for remove in range(len(rows)):
        columns = [
            sum(1 << i for i in col) for j, col in enumerate(rows) if j != remove
        ]
        rank, basis = rank_columns(columns)
        if rank == homology["rank_d2_F2"]:
            break
    else:
        raise AssertionError("expected a redundant local cell")
    result["cells"].pop(remove)
    homology.update(
        boundary_d2=[col for j, col in enumerate(rows) if j != remove],
        basis_cell_ids=[result["cells"][i]["id"] for i in basis],
    )
    verdict = verify(result)
    assert (
        verdict["H1_dim"] == 0
        and verdict["status"] == "NOT_PROVED"
        and verdict["missing_peaks"] == 1
    )
