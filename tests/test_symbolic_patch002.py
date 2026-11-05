"""Bounded escape from the actual PATCH002 text fixture; no model of the worker."""

import hashlib
import json
from pathlib import Path

import pytest

from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.white_star.pool import prepare

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "docs/LIVINGMATH_SYMBOLIC_PATCH002/reproduction"
)


def request():
    return json.loads(
        (FIXTURES / "nostradamus_original_local_word.request.json").read_text()
    )


@pytest.fixture(scope="module")
def executor():
    assert prepare()["ready"]
    pool = Executor()
    assert pool.status()["ready"]
    yield pool
    pool.close()


def explore(executor, value):
    return executor.run({"action": "explore", "request": value})["data"]


def check_bounds(value, result):
    budget = value["search"]
    summary = result["summary"]
    assert summary["steps"] <= budget["max_steps"]
    assert summary["nodes"] <= budget["max_nodes"]
    assert summary["observations"] <= budget.get("max_observations", 8192)
    assert summary["total_stored_tokens"] <= budget.get("max_total_tokens", 131072)
    assert all(len(s["tokens"]) <= budget["max_word_tokens"] for s in result["states"])
    assert all(
        len(t["candidates"]) <= budget["max_candidates_per_step"]
        for t in result["ops_trace"]
    )
    assert summary["attempted_candidates"] == sum(
        len(t["candidates"]) for t in result["ops_trace"]
    )
    assert not summary["global_exhaustion_proved"]
    assert result["checks"]["DAG_acyclic_and_hashed"]


def test_exact_historical_fixture_escapes_empty_word_without_larger_budget(executor):
    value = request()
    result = explore(executor, value)
    check_bounds(value, result)
    assert result["summary"]["steps"] > 5
    assert result["summary"]["nodes"] > 18
    assert result["summary"]["fallback_count"] > 0
    assert result["summary"]["halt_reason"] in {
        "MAX_STEPS",
        "MAX_NODES",
        "MAX_TOTAL_TOKENS",
        "MAX_OBSERVATIONS",
    }
    assert result["search_diagnostics"][0]["status"] == "LOCAL_STAGNATION"
    assert "RENAME" in result["search_diagnostics"][0]["unproposed_operators"]
    old = json.loads((FIXTURES / "controller_golden.json").read_text())
    assert digest(result["ops_trace"][:5]) == old["nostradamus_first_5_trace_digest"]
    assert digest(result["source_map"]) == old["nostradamus_source_map_digest"]
    events = [
        d for d in result["search_diagnostics"] if d["status"] == "FRONTIER_FALLBACK"
    ]
    assert len(events) == result["summary"]["fallback_count"]
    forced = [(e["selected_node_id"], e["selected_operator"]) for e in events]
    assert len(forced) == len(set(forced))
    for event in events:
        step = result["ops_trace"][event["step"]]
        candidate = step["candidates"][0]
        assert step["input_node"] == event["selected_node_id"]
        assert candidate["parents"][0] == event["selected_node_id"]
        assert candidate["operator"] == event["selected_operator"]
        assert candidate["proposal"] == "frontier_fallback"
        assert event["selected_node_id"] in {n["node_id"] for n in result["history"]}
        assert event["frontier_size"] > 0


def test_seeded_repeat_and_golden_grammar_are_unchanged(executor):
    value = request()
    a, b = explore(executor, value), explore(executor, value)
    assert digest(a) == digest(b)
    value = json.loads(
        (FIXTURES / "patch001_palindrome_regression.request.json").read_text()
    )
    result = explore(executor, value)
    golden = json.loads((FIXTURES / "grammar_golden.json").read_text())
    assert result["grammar_hypotheses"] == golden["grammar_hypotheses"]
    predictions = result["heldout_eval"]["predictions"]
    assert all(
        (p["membership_probability"] >= 0.5) == (p["tokens"] == p["tokens"][::-1])
        for p in predictions
    )
    assert (
        result["grammar_hypotheses"][0]["identifiability_status"] == "UNDERDETERMINED"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"max_steps": 0},
        {"max_nodes": 16},
        {"max_total_tokens": 120},
        {"max_observations": 16},
        {"max_steps": 7},
        {"max_candidates_per_step": 1, "max_steps": 24},
    ],
)
def test_all_existing_resource_limits_include_fallback(executor, changes):
    value = request()
    value["search"].update(changes)
    result = explore(executor, value)
    check_bounds(value, result)
    terminal = result["search_diagnostics"][-1]
    assert terminal["status"] == result["summary"]["halt_reason"]
    assert terminal["candidate_attempts"] == result["summary"]["attempted_candidates"]
    assert terminal["fallback_count"] == result["summary"]["fallback_count"]
    if changes == {"max_steps": 0}:
        assert not result["ops_trace"] and not terminal["fallback_count"]
        assert result["summary"]["saturation_certificate_digest"] is None
        assert not terminal["sampled_operators"]


def test_exhaustion_is_explicitly_of_sampled_node_operator_frontier_only(executor):
    value = request()
    value["source"].update(text="", sha256=hashlib.sha256(b"").hexdigest())
    value["operators"] = ["REVERSE"]
    result = explore(executor, value)
    check_bounds(value, result)
    summary = result["summary"]
    assert summary["halt_reason"] == "ACTUAL_LOCAL_EXHAUSTION"
    assert summary["frontier_size"] == 0
    assert summary["untried_allowed_operators"] == []
    assert not summary["global_exhaustion_proved"]
    assert result["search_diagnostics"][-1]["unseen_variants_may_exist"]


def test_coverage_matches_real_trace_in_both_identity_modes(executor):
    for identity in ("word", "provenance"):
        value = request()
        value["search"].update(history_identity=identity, max_steps=24)
        result = explore(executor, value)
        check_bounds(value, result)
        assert result["summary"]["history_identity"] == identity
        coverage = result["summary"]["operation_coverage"]
        for op in value["operators"]:
            candidates = [
                c
                for t in result["ops_trace"]
                for c in t["candidates"]
                if c["operator"] == op
            ]
            assert coverage[op]["proposed"] == len(candidates)
            assert coverage[op]["accepted"] == sum(
                bool(c.get("new_outputs")) for c in candidates
            )
            assert coverage[op]["duplicate"] == sum(
                c["status"] == "DUPLICATE_WORD" for c in candidates
            )
            assert coverage[op]["proposed"] == sum(
                coverage[op][k]
                for k in ("accepted", "duplicate", "forbidden", "resource_limited")
            )
        if identity == "provenance":
            assert len(result["states"]) > len(
                {s["word_hash"] for s in result["states"]}
            )


def test_max_nodes_keeps_earlier_stagnation_and_fallback_evidence(executor):
    value = request()
    value["search"].update(max_nodes=64)
    result = explore(executor, value)
    assert result["summary"]["halt_reason"] == "MAX_NODES"
    assert result["summary"]["fallback_count"] > 0
    statuses = [d["status"] for d in result["search_diagnostics"]]
    assert "LOCAL_STAGNATION" in statuses and "FRONTIER_FALLBACK" in statuses
    assert statuses[-1] == "MAX_NODES"
    check_bounds(value, result)
