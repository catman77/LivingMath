"""PATCH004 acceptance against real package code, never the supplied reference AST."""

import copy, hashlib
from itertools import product
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.observer_synthesis.learner import fit, predict
from lm_suti_assurance.observer_synthesis.features import encode, verify_feature


def record(word, label=None, ident=None):
    text = " ".join(word)
    r = {
        "id": ident or digest(text),
        "tokens": list(word),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "ORIGINAL_TEST_FIXTURE",
            "edition": "PATCH004/1",
        },
    }
    if label is not None:
        r["accepted"] = label
    return r


def rows(kind, lengths):
    result = []
    for n in lengths:
        for w in product("SP", repeat=n):
            label = (
                w == w[::-1]
                if kind == "mirror"
                else n % 2 == 0 and w[: n // 2] == w[n // 2 :]
            )
            result.append(record(w, label))
    return result


def request():
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": "0" * 64,
            "predict_ref": "1" * 64,
            "holdout_labels_visible": False,
            "structure_levels": ["word"],
            "candidate_transformations": ["REVERSE", "RENAME"],
        },
        "feature_policy": {
            "enabled_builtins": [],
            "feature_denylist": ["pair_0_max", "pair_0_min", "pair_0_final"],
            "derive_relations": True,
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
        },
        "search": {
            "seed": 137,
            "max_composition_depth": 4,
            "max_proposals": 128,
            "max_contexts": 128,
            "max_witnesses": 512,
            "max_cpu_ms": 4000,
        },
        "promotion_policy": {
            "mode": "compositional_ast",
            "candidate_sources": ["derivation_trace", "source_run_id"],
            "max_ast_nodes": 32,
            "max_ast_depth": 8,
            "max_recursion_steps": 8,
            "max_tokens": 8,
            "max_train_witnesses": 256,
            "require_independent_checker": True,
        },
    }


def trained(kind="mirror"):
    train = rows(kind, [4] if kind == "mirror" else [2, 4])
    model = fit(train, request())
    feature = next(
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    )
    return train, model, feature


@pytest.mark.parametrize(
    "kind,composition",
    [("mirror", "iterate_on_inner_fragment"), ("duplicate", "compare_fragments")],
)
def test_discovered_compositions_builtins_disabled_frozen_lengths(
    kind, composition, monkeypatch
):
    from lm_suti_assurance.symbolic import grammar

    def forbidden(*a, **k):
        raise AssertionError("Disabled builtin calculator called")

    monkeypatch.setattr(grammar, "features", forbidden)
    train, model, feature = trained(kind)
    assert feature["operator_ast"]["composition"] == composition
    assert (
        feature["origin"] == "DERIVED_FROM_OPERATORS" and feature["execution_verified"]
    )
    assert feature["verifier_result"]["status"] == "CHECKED_INSTANCE"
    assert model["identifiability_status"] == "UNDERDETERMINED"
    seal = model["hypothesis_digest"]
    for n in [6, 8]:
        gold = rows(kind, [n])
        q = [{k: v for k, v in r.items() if k != "accepted"} for r in gold]
        predicted = predict(model, q)["predictions"]
        assert all(
            (p["score"] >= 0.5) == r["accepted"] for p, r in zip(predicted, gold)
        )
        assert all(
            p["hypothesis_digest"] == seal and p["operator_evidence"] for p in predicted
        )
        assert seal == model["hypothesis_digest"]
    other = request()
    other["task"]["predict_ref"] = "2" * 64
    assert fit(train, other)["hypothesis_digest"] == seal
    for denied in [feature["feature_id"], *feature["parent_feature_refs"]]:
        q = request()
        q["feature_policy"]["feature_denylist"].append(denied)
        ablated = fit(train, q)
        assert feature["feature_id"] not in ablated["enabled_feature_ids"]
    q = request()
    q["feature_policy"]["derive_relations"] = False
    assert not fit(train, q)["used_feature_ids"]


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "position",
        "span",
        "missing",
        "malformed",
        "illegal",
        "hidden",
        "origin",
        "universal",
        "binding",
    ],
)
def test_independent_composite_verifier_rejects_rehashed_corruption(
    mutation, monkeypatch
):
    train, model, feature = trained()
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    from lm_suti_assurance.observer_synthesis import composition_ast

    monkeypatch.setattr(
        composition_ast,
        "execute",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Producer used by checker")
        ),
    )
    assert verify_feature(feature, samples)["status"] == "CHECKED_INSTANCE"
    bad = copy.deepcopy(feature)
    if mutation == "hash":
        bad["construction_trace"][0]["operator_trace"][0]["output_word_hashes"][0] = (
            "0" * 64
        )
    elif mutation == "position":
        next(
            x
            for x in bad["construction_trace"][0]["operator_trace"]
            if x.get("operator") == "SPLIT"
        )["args"]["position"] += 1
    elif mutation == "span":
        next(
            s
            for s in bad["construction_trace"][0]["states"].values()
            if s["source_spans"]
        )["source_spans"][0][0][1] += 1
    elif mutation == "missing":
        bad["construction_trace"].pop()
    elif mutation == "malformed":
        bad["operator_ast"]["trim_left"] = 0
        bad["operator_ast"]["trim_right"] = 0
    elif mutation == "illegal":
        bad["construction_trace"][0]["operator_trace"][0]["operator"] = "RUN_SCRIPT"
    elif mutation == "hidden":
        bad["hidden_labels"] = {"query": True}
    elif mutation == "origin":
        bad["origin"] = "BUILTIN"
    elif mutation == "universal":
        bad["known_invariance_scope"]["universal_invariant"] = True
    else:
        bad["operator_bindings"]["state_sha256"] = "0" * 64
    bad["witness_set_digest"] = digest(bad["construction_trace"])
    bad["digest"] = digest({k: v for k, v in bad.items() if k != "digest"})
    result = verify_feature(bad, samples)
    assert (
        result["status"] == "REJECTED"
        and result["field_path"]
        and not result["execution_permission"]
    )


def test_scope_utf8_bijection_and_copy_weak_hypothesis_counterexamples():
    for kind in ["mirror", "duplicate"]:
        train, model, feature = trained(kind)
        q = record(tuple("S" * 9))
        p = predict(model, [q])["predictions"][0]
        assert p["score"] is None and p["status"] == "UNKNOWN"
        renamed = []
        for r in train:
            names = {"S": "кот", "P": "лес"}
            renamed.append(record([names[t] for t in r["tokens"]], r["accepted"]))
        m = fit(renamed, request())
        f = next(
            f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
        )
        assert (
            verify_feature(
                f, [{"record": r, "encoded": encode(r, "literal")} for r in renamed]
            )["status"]
            == "CHECKED_INSTANCE"
        )
    _, model, _ = trained("duplicate")
    cases = [tuple("SSPSSP"), tuple("SSPPSS"), tuple("SPSPPS")]
    got = predict(model, [record(w) for w in cases])["predictions"]
    assert [(p["score"] >= 0.5) for p in got] == [w[:3] == w[3:] for w in cases]


def test_source_bridge_real_symbolic_run_binding_and_project_isolation(tmp_path):
    import asyncio, json
    from pathlib import Path
    from lm_suti_assurance.service import Service
    from lm_suti_assurance.symbolic.service import SymbolicService
    from lm_suti_assurance.symbolic.executor import Executor
    from lm_suti_assurance.symbolic_complex.service import ExtensionService
    from lm_suti_assurance.observer_synthesis.source_bridge import resolve
    from lm_suti_assurance.errors import AssuranceError

    root = tmp_path / "state"
    Service(root).new("source-project", "new")
    Service(root).new("other-project", "new")
    from lm_suti_assurance.white_star.pool import prepare

    assert prepare()["ready"]
    pool = Executor()
    try:
        q = json.loads(
            (
                Path(__file__).parent / "fixtures/composition_source_request.json"
            ).read_text()
        )
        source = asyncio.run(
            SymbolicService(root, pool).explore("source-project", "original", q)
        )
        assert source["status"] == "COMPLETED"
        train = rows("mirror", [4])
        resolved = resolve(root, "source-project", source["run_id"], train)
        req = request()
        req["promotion_policy"]["candidate_sources"] = ["source_run_id"]
        m = fit(train, req, resolved)
        f = next(
            f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
        )
        assert f["candidate_provenance"]["origin"] == "SOURCE_SUPPLIED"
        assert f["candidate_provenance"]["source_run_id"] == source["run_id"]
        with pytest.raises(AssuranceError, match="NOT_FOUND"):
            resolve(root, "other-project", source["run_id"], train)
        wrong = copy.deepcopy(train)
        wrong[0]["accepted"] = not wrong[0]["accepted"]
        with pytest.raises(AssuranceError, match="SOURCE_TRAIN_MISMATCH"):
            resolve(root, "source-project", source["run_id"], wrong)
        service = ExtensionService(root, pool)

        def store(kind, rs):
            ds = {
                "schema": "livingmath-observer-dataset/1",
                "kind": kind,
                "records": rs,
            }
            ds["sha256"] = digest(ds)
            return service.dataset_store("source-project", kind, ds)["dataset_ref"]

        req = request()
        req["task"]["train_ref"] = store("train", train)
        req["task"]["predict_ref"] = store("queries", [record(tuple("SSSSSS"))])
        req["source_run_id"] = source["run_id"]
        first = asyncio.run(
            service.run("source-project", "first", "observer_synthesis_v1", req)
        )
        assert first["status"] == "COMPLETED"
        repeat = asyncio.run(
            service.run("source-project", "first", "observer_synthesis_v1", req)
        )
        assert repeat["run_id"] == first["run_id"]
        # Historical key resolves before any newly strengthened source check.
        service.resolve = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Archived key was resolved again")
        )
        assert (
            asyncio.run(
                service.run("source-project", "first", "observer_synthesis_v1", req)
            )["run_id"]
            == first["run_id"]
        )
        changed = copy.deepcopy(req)
        changed["promotion_policy"]["max_tokens"] = 6
        with pytest.raises(AssuranceError, match="REQUEST_KEY_CONFLICT"):
            asyncio.run(
                service.run("source-project", "first", "observer_synthesis_v1", changed)
            )
    finally:
        pool.close()


@pytest.mark.parametrize(
    "bound,limit",
    [
        ("max_tokens", 3),
        ("max_ast_nodes", 2),
        ("max_ast_depth", 1),
        ("max_recursion_steps", 1),
        ("max_train_witnesses", 15),
    ],
)
def test_explicit_scope_bounds_never_turn_resource_failures_into_false(bound, limit):
    q = request()
    q["promotion_policy"][bound] = limit
    m = fit(rows("mirror", [6] if bound == "max_recursion_steps" else [4]), q)
    assert (
        not m["used_feature_ids"]
        and m["synthesis_status"] == "NO_VERIFIABLE_NEW_OBSERVER"
    )
    assert any(r.get("failed_obligation") for r in m["derivation_trace"])


def test_new_branch_supports_bounded_128_records_without_relaxing_legacy64():
    original = rows("mirror", [4])
    repeated = [
        record(r["tokens"], r["accepted"], ident=str(i) + "-" + r["id"])
        for i in range(8)
        for r in original
    ]
    m = fit(repeated, request())
    f = next(
        f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
    )
    assert f["verifier_result"]["verified_witnesses"] == 128
    q = request()
    q.pop("promotion_policy")
    old = fit(repeated, q)
    assert not old["used_feature_ids"]
    assert any(
        r.get("failed_obligation") == "FINITE_SHORT_WORD_SCOPE_REQUIRED"
        for r in old["derivation_trace"]
    )


def test_no_renamed_builtin_or_forged_verifier_claim():
    train, _, feature = trained()
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    bad = copy.deepcopy(feature)
    bad["verifier_result"]["status"] = "PROVED_EXACT"
    assert verify_feature(bad, samples)["status"] == "REJECTED"
    q = request()
    q["feature_policy"]["representation"] = "global_alpha"
    assert not fit(train, q)["used_feature_ids"]


def test_midpoint_source_supplied_evaluator_control_is_not_discovery():
    from lm_suti_assurance.observer_synthesis.composition_ast import (
        execute,
        declared_domain,
    )
    from lm_suti_assurance.observer_synthesis.composition_checker import execute_checked
    from lm_suti_assurance.observer_synthesis.contexts import record_state

    # A manually supplied allowed shape only tests execution, never a model found
    # by the producer. Actual discovery is tested above with no AST argument.
    supplied = {
        "composition": "compare_fragments",
        "cut": {"operator": "SPLIT", "position": "MIDPOINT_EXACT_EVEN"},
        "comparison": "literal_word_equality",
        "expected_equal": True,
    }
    scope = declared_domain(request()["promotion_policy"])
    for r in rows("duplicate", [6, 8]):
        state = record_state(r)
        v, tr, table = execute(supplied, state, scope, certify=True)
        w = {
            "record_ref": digest(r),
            "source_sha256": r["source"]["sha256"],
            "input_state_ref": digest(state.data()),
            "operator_trace": tr,
            "states": table,
            "decision": v,
        }
        assert execute_checked(supplied, r, w, scope) == r["accepted"]


def test_resource_failure_is_never_converted_to_a_semantic_negative(monkeypatch):
    from lm_suti_assurance.observer_synthesis import compositional
    from lm_suti_assurance.errors import AssuranceError

    def exhausted(*a, **k):
        raise AssuranceError("BUDGET_EXCEEDED", "/search")

    monkeypatch.setattr(compositional, "execute", exhausted)
    with pytest.raises(AssuranceError, match="BUDGET_EXCEEDED"):
        fit(rows("mirror", [4]), request())


@pytest.mark.parametrize(
    "mutation", ["position_bool", "span_bool", "readout_integer", "verifier_numeric"]
)
def test_certificate_JSON_types_are_exact_even_when_python_equality_matches(mutation):
    train, _, feature = trained()
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    bad = copy.deepcopy(feature)
    if mutation == "position_bool":
        next(
            s
            for w in bad["construction_trace"]
            for s in w["operator_trace"]
            if s.get("operator") == "SPLIT" and s["args"]["position"] == 1
        )["args"]["position"] = True
    elif mutation == "span_bool":
        next(
            s
            for w in bad["construction_trace"]
            for s in w["states"].values()
            if s["source_spans"] and s["source_spans"][0][0][2] == 1
        )["source_spans"][0][0][2] = True
    elif mutation == "readout_integer":
        step = next(
            s
            for w in bad["construction_trace"]
            for s in w["operator_trace"]
            if s.get("operation") == "literal_word_equality"
        )
        step["value"] = int(step["value"])
    else:
        bad["verifier_result"]["verified_witnesses"] = float(len(train))
    bad["witness_set_digest"] = digest(bad["construction_trace"])
    bad["digest"] = digest({k: v for k, v in bad.items() if k != "digest"})
    assert verify_feature(bad, samples)["status"] == "REJECTED"


def test_no_nested_false_proof_claims_or_unknown_witness_fields():
    train, _, feature = trained()
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    for mutation in ["witness", "provenance"]:
        bad = copy.deepcopy(feature)
        target = (
            bad["construction_trace"][0]
            if mutation == "witness"
            else bad["candidate_provenance"]
        )
        target["universal_invariant"] = True
        target["claim_status"] = "PROVED_EXACT"
        bad["witness_set_digest"] = digest(bad["construction_trace"])
        bad["digest"] = digest({k: v for k, v in bad.items() if k != "digest"})
        assert verify_feature(bad, samples)["status"] == "REJECTED"


def test_corrupted_outer_certificate_digest_is_rejected():
    train, _, feature = trained()
    feature["digest"] = "0" * 64
    assert (
        verify_feature(
            feature, [{"record": r, "encoded": encode(r, "literal")} for r in train]
        )["status"]
        == "REJECTED"
    )
