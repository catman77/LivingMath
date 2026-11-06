"""FIX-A actual assumptions and FIX-B genuinely used, independently checked observer."""

import copy, hashlib
from itertools import product
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic_complex.model import analyze
from lm_suti_assurance.observer_synthesis.features import encode, verify_feature
from lm_suti_assurance.observer_synthesis.learner import fit, predict


def record(tokens, train=False):
    text = " ".join(tokens)
    value = {
        "id": digest({"text": text}),
        "tokens": list(tokens),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "generated finite equality experiment",
            "edition": "fixed-binary-words/1",
        },
    }
    if train:
        value["accepted"] = tokens[1] == tokens[-2]
    return value


def request(derive=True):
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": "0" * 64,
            "predict_ref": "1" * 64,
            "holdout_labels_visible": False,
            "structure_levels": ["word"],
            "candidate_transformations": ["REVERSE"],
        },
        "feature_policy": {
            "enabled_builtins": ["alpha_pattern", "composition"],
            "feature_allowlist": ["derived:*"],
            "feature_denylist": ["pair_0_max", "pair_0_min", "pair_0_final"],
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
            "representation": "literal",
            "derive_relations": derive,
        },
        "search": {
            "seed": 137,
            "max_composition_depth": 4,
            "max_proposals": 128,
            "max_contexts": 64,
            "max_witnesses": 128,
            "max_cpu_ms": 4000,
        },
    }


@pytest.mark.parametrize(
    "n,policy,missing",
    [(6, "bigons_only", 32), (6, "diamonds_only", 48), (10, "none", 3360)],
)
def test_partial_complex_assumptions_are_checked(n, policy, missing):
    q = {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "sp_balanced_fixture",
            "max_length": n,
            "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
            "edge_identity": "source_position_rule",
        },
        "cells": {"policy": policy, "join_depth_limit": 1},
        "analysis": ["path_coherence", "homology_F2"],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }
    result = analyze(q)
    summary = result["summary"]
    assert "all_local_peaks_filled" not in summary["assumptions"]
    assert summary["selected_cells_policy"] == policy and summary["partial_attachment"]
    assert (
        summary["unresolved_peaks"] == missing and summary["pi1_status"] == "NOT_PROVED"
    )


def test_positive_frozen_operator_feature_beats_disabled_ablation(monkeypatch):
    train = [record(w, True) for w in product("AB", repeat=6)]
    queries = [record(w) for w in product("AB", repeat=8)]
    model = fit(train, request())
    ablation = fit(train, request(False))
    seal = model["hypothesis_digest"]
    assert set(r["id"] for r in train).isdisjoint(r["id"] for r in queries)
    assert all("accepted" not in r for r in queries)
    used = [
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    ]
    assert len(used) == 1 and used[0]["origin"] == "DERIVED_FROM_OPERATORS"
    feature = used[0]
    assert feature["operator_ast"]["offset"] == 1 and feature["execution_verified"]
    assert feature["semantic_alias_of"] is None
    assert all(f["origin"] != "BUILTIN" for f in used)
    assert not any(x.startswith("pair_") for x in model["enabled_feature_ids"])
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    assert verify_feature(feature, samples)["verified_witnesses"] == 64
    assert all(
        w["states"] and w["input_state_ref"] in w["states"]
        for w in feature["construction_trace"]
    )
    from lm_suti_assurance.symbolic import grammar

    def forbidden(*args, **kwargs):
        raise AssertionError("builtin shortcut must not evaluate a derived observer")

    monkeypatch.setattr(grammar, "features", forbidden)
    monkeypatch.setattr(grammar, "relation_value", forbidden)
    predicted = predict(model, queries)["predictions"]
    disabled = predict(ablation, queries)["predictions"]
    true = [r["tokens"][1] == r["tokens"][-2] for r in queries]
    assert sum((r["score"] >= 0.5) == y for r, y in zip(predicted, true)) == 256
    assert sum((r["score"] >= 0.5) == y for r, y in zip(disabled, true)) == 128
    assert model["hypothesis_digest"] == seal


@pytest.mark.parametrize(
    "mutation", ["AST", "output_hash", "operator", "span", "missing_state"]
)
def test_independent_observer_checker_rejects_tampering(mutation, monkeypatch):
    train = [record(w, True) for w in product("AB", repeat=6)]
    model = fit(train, request())
    feature = next(
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    )
    feature = copy.deepcopy(feature)
    w = feature["construction_trace"][0]
    if mutation == "AST":
        feature["operator_ast"]["offset"] = 2
    elif mutation == "output_hash":
        w["operator_trace"][0]["output_word_hashes"][0] = "0" * 64
    elif mutation == "operator":
        w["operator_trace"][0]["operator"] = "EVAL"
    elif mutation == "span":
        next(v for v in w["states"].values() if v["source_spans"])["source_spans"][0][
            0
        ][1] += 1
    else:
        w["states"].pop(w["input_state_ref"])
    from lm_suti_assurance.observer_synthesis import operator_execution

    def forbidden(*args, **kwargs):
        raise AssertionError("checker cannot call producer")

    monkeypatch.setattr(operator_execution, "evaluate", forbidden)
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    assert verify_feature(feature, samples)["status"] == "REJECTED"


def test_utf8_source_spans_checked_independently():
    train = [record(w, True) for w in product("αβ", repeat=6)]
    model = fit(train, request())
    f = next(
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    )
    rows = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    assert verify_feature(f, rows)["status"] == "CHECKED_FINITE_INSTANCE"
    for witness in f["construction_trace"]:
        for state in witness["states"].values():
            for spans in state["source_spans"]:
                assert all(end - start == 2 for _, start, end in spans)


def test_checker_accepts_valid_witness_without_producer(monkeypatch):
    from lm_suti_assurance.observer_synthesis import operator_execution

    train = [record(w, True) for w in product("AB", repeat=6)]
    model = fit(train, request())
    feature = next(
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("independent verification cannot call trace producer")

    monkeypatch.setattr(operator_execution, "evaluate", forbidden)
    rows = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    assert verify_feature(feature, rows)["status"] == "CHECKED_FINITE_INSTANCE"


def test_observer_verify_through_real_registered_fastmcp_tool(tmp_path):
    import asyncio
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.symbolic_complex.mcp import register_tools
    from lm_suti_assurance.symbolic.executor import Executor
    from lm_suti_assurance.core import canonical

    pool = Executor()
    try:
        server = FastMCP("observer-verify-test")
        service = register_tools(server, tmp_path, pool)
        service.base.new("qa", "new")
        service.base.new("other", "new")
        train = [record(w, True) for w in product("AB", repeat=6)]
        queries = [record(w) for w in product("AB", repeat=8)]

        def store(kind, rows):
            ds = {
                "schema": "livingmath-observer-dataset/1",
                "kind": kind,
                "records": rows,
            }
            ds["sha256"] = digest(ds)
            return service.dataset_store("qa", kind, ds)["dataset_ref"]

        q = request()
        q["task"].update(
            train_ref=store("train", train), predict_ref=store("queries", queries)
        )

        async def go():
            run = await service.run("qa", "positive", "observer_synthesis_v1", q)
            from lm_suti_assurance.white_star import blobs

            w, _ = service.load("qa", run["run_id"])
            model = blobs.get(w, run["section_refs"]["model"])
            feature = next(
                f
                for f in model["feature_registry"]
                if f["feature_id"] in model["used_feature_ids"]
            )
            args = {
                "project": "qa",
                "run_id": run["run_id"],
                "feature_id": feature["feature_id"],
            }
            result = await server._tool_manager.call_tool(
                "white_star_symbolic_observer_verify", args, convert_result=False
            )
            assert (
                result.structuredContent["data"]["status"] == "CHECKED_FINITE_INSTANCE"
            )
            bad = copy.deepcopy(feature)
            bad["construction_trace"] = bad["construction_trace"][:1]
            bad["construction_trace"][0]["operator_trace"][0]["output_word_hashes"][
                0
            ] = "0" * 64
            assert len(canonical(bad).encode()) < 262144
            result = await server._tool_manager.call_tool(
                "white_star_symbolic_observer_verify",
                args | {"certificate": bad},
                convert_result=False,
            )
            assert result.structuredContent["data"]["status"] == "REJECTED"
            result = await server._tool_manager.call_tool(
                "white_star_symbolic_observer_verify",
                args | {"project": "other"},
                convert_result=False,
            )
            assert (
                result.isError
                and result.structuredContent["error"]["code"] == "NOT_FOUND"
            )

        asyncio.run(go())
    finally:
        pool.close()


def test_no_builtin_calculation_during_operator_only_fit_or_prediction(monkeypatch):
    from lm_suti_assurance.symbolic import grammar

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled builtin calculator must never run")

    monkeypatch.setattr(grammar, "features", forbidden)
    train = [record(w, True) for w in product("AB", repeat=6)]
    model = fit(train, request())
    disabled = fit(train, request(False))
    queries = [record(w) for w in product("AB", repeat=8)]
    assert len(predict(model, queries)["predictions"]) == 256
    assert len(predict(disabled, queries)["predictions"]) == 256
    assert model["used_feature_ids"] and not disabled["used_feature_ids"]


@pytest.mark.parametrize(
    "groups",
    [
        [],
        ["literal"],
        ["alpha_pattern"],
        ["composition"],
        ["alpha_pattern", "adjacency", "composition"],
    ],
)
def test_declarative_registry_matches_unchanged_builtin_names(groups):
    from lm_suti_assurance.observer_synthesis.features import builtin_registry
    from lm_suti_assurance.symbolic.grammar import features

    sample = {"tokens": list("ABCDAC"), "lines": [list("ABCDAC")]}
    registry = builtin_registry([sample], {"enabled_builtins": groups}, list("ABCD"))
    assert {r["feature_id"] for r in registry} == set(
        features(sample["tokens"], list("ABCD"), groups or ["_no_builtin_observer_"])
    )
