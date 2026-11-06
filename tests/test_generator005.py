"""Mixed-length candidate completeness; independent finite labels are external to fit."""

import copy
from collections import Counter
from itertools import product
import pytest
from test_compositional_promotion import record, rows, request
from lm_suti_assurance.core import digest
from lm_suti_assurance.observer_synthesis.learner import fit, predict


def selected(model):
    return next(
        f
        for f in model["feature_registry"]
        if f["feature_id"] in model["used_feature_ids"]
    )


@pytest.mark.parametrize("extra", [None, "SS", "PP", "SP", "PS"])
def test_short_positive_never_removes_valid_recursive_skeleton(extra):
    train = rows("mirror", [4])
    if extra:
        train.append(record(list(extra), extra[0] == extra[1]))
    m = fit(train, request())
    f = selected(m)
    assert f["operator_ast"]["composition"] == "iterate_on_inner_fragment"
    assert f["verifier_result"]["verified_witnesses"] == len(train)
    assert f["verifier_result"]["status"] == "CHECKED_INSTANCE"
    d = m["composition_diagnostics"]["candidate_generation"]
    assert d["grammar_version"] == "mixed_length_typed_composition/1"
    assert d["train_length_histogram"] == dict(
        Counter(str(len(r["tokens"])) for r in train)
    )
    assert any(
        x["kind"] == "iterate_on_inner_fragment"
        and x["promotion_status"] == "PROMOTED_VERIFIED"
        for x in d["candidate_records"]
    )


@pytest.mark.parametrize(
    "lengths,n",
    [([2, 4], 6), ([2, 4], 8), ([1, 2, 3, 4], 7), ([1, 3, 5], 7), ([2, 4, 6], 8)],
)
def test_mixed_length_complete_train_transfer(lengths, n):
    train = rows("mirror", lengths)
    m = fit(train, request())
    f = selected(m)
    assert f["operator_ast"]["composition"] == "iterate_on_inner_fragment"
    gold = rows("mirror", [n])
    q = [{k: v for k, v in r.items() if k != "accepted"} for r in gold]
    before = digest(m)
    p = predict(m, q)["predictions"]
    assert all(
        x["score"] is not None and (x["score"] >= 0.5) == y["accepted"]
        for x, y in zip(p, gold)
    )
    assert digest(m) == before and m["identifiability_status"] == "UNDERDETERMINED"


def test_generation_counterexamples_are_exact_and_budget_is_not_impossibility():
    train = rows("mirror", [2, 4])
    q = request()
    q["search"]["max_proposals"] = 1
    m = fit(train, q)
    d = m["composition_diagnostics"]["candidate_generation"]
    assert d["candidate_budget_exhausted"] and not d["bounded_search_complete"]
    assert d["search_status"] == "BOUNDED_SEARCH_INCOMPLETE"
    assert not any(
        x.get("failed_obligation") == "NO_TRAIN_COMPATIBLE_TYPED_COMPOSITION"
        for x in m["derivation_trace"]
    )
    considered = [
        x for x in d["candidate_records"] if x["generation_status"] == "GENERATED"
    ]
    assert len(considered) == 1
    ce = considered[0]["counterexamples"][0]
    r = next(r for r in train if r["id"] == ce["sample_id"])
    assert (
        ce["expected"] == r["accepted"]
        and ce["observed"] != ce["expected"]
        and ce["record_ref"] == digest(r)
    )
    assert any(
        x["generation_status"] == "NOT_GENERATED"
        and x["pruning_reason"] == "max_proposals"
        for x in d["candidate_records"]
    )


@pytest.mark.parametrize("n", [0, 1, 2])
def test_native_epsilon_and_singleton_base_cases_without_contract_expansion(n):
    from lm_suti_assurance.observer_synthesis.compositional import typed_skeletons
    from lm_suti_assurance.observer_synthesis.composition_ast import (
        execute,
        declared_domain,
    )
    from lm_suti_assurance.observer_synthesis.composition_checker import execute_checked
    from lm_suti_assurance.observer_synthesis.contexts import record_state

    r = record(["кот"] * n, True)
    ast = next(
        a
        for a in typed_skeletons([r])
        if a["composition"] == "iterate_on_inner_fragment"
    )
    domain = declared_domain(request()["promotion_policy"])
    state = record_state(r)
    value, trace, states = execute(ast, state, domain, certify=True)
    w = {
        "record_ref": digest(r),
        "source_sha256": r["source"]["sha256"],
        "input_state_ref": digest(state.data()),
        "decision": value,
        "operator_trace": trace,
        "states": states,
    }
    assert value is True and execute_checked(ast, r, w, domain) is True


def test_endpoint_only_is_a_real_48_fp_counterexample_not_our_selected_rule():
    from lm_suti_assurance.observer_synthesis.compositional import typed_skeletons
    from lm_suti_assurance.observer_synthesis.composition_ast import (
        value,
        declared_domain,
    )

    gold = rows("mirror", [7])
    guard = next(typed_skeletons(rows("mirror", [1, 3])))
    domain = declared_domain(request()["promotion_policy"])
    assert (
        sum(value(guard, r["tokens"], domain) and not r["accepted"] for r in gold) == 48
    )
    m = fit(rows("mirror", [1, 3]), request())
    candidates = m["composition_diagnostics"]["candidate_generation"][
        "candidate_records"
    ]
    assert any(
        c["kind"] == "iterate_on_inner_fragment"
        and c["train_status"] == "TRAIN_COMPATIBLE"
        for c in candidates
    )
    assert len(m["competing_train_compatible_models"]) >= 2


def test_both_seeds_preserve_feature_identity_and_queries_cannot_change_fit():
    models = []
    for seed in [137, 42]:
        q = request()
        q["search"]["seed"] = seed
        q["task"]["predict_ref"] = str(seed % 10) * 64
        m = fit(rows("mirror", [1, 2, 3, 4]), q)
        models.append(selected(m)["feature_id"])
        assert selected(m)["operator_ast"]["composition"] == "iterate_on_inner_fragment"
    assert len(set(models)) == 1


def test_type_and_termination_failures_have_separate_stages(monkeypatch):
    from lm_suti_assurance.observer_synthesis import compositional

    valid = list(compositional.typed_skeletons(rows("mirror", [4])))
    illegal = {"composition": "RUN_SCRIPT"}
    loop = copy.deepcopy(valid[1])
    loop["trim_left"] = loop["trim_right"] = 0
    monkeypatch.setattr(
        compositional, "typed_skeletons", lambda records: iter([illegal, loop, *valid])
    )
    m = fit(rows("mirror", [4]), request())
    d = m["composition_diagnostics"]["candidate_generation"]
    assert {r["status"] for r in d["candidate_records"]} >= {
        "GENERATED_REJECTED_BY_TYPE",
        "GENERATED_REJECTED_BY_TERMINATION",
    }
    assert all(r.get("pruning_reason") for r in d["candidate_records"][:2])


def test_copy_mixed_lengths_and_unicode_never_depend_on_atom_names():
    for train in [
        rows("duplicate", [2, 4]),
        rows("duplicate", [2, 4]) + rows("duplicate", [6])[:32],
    ]:
        m = fit(train, request())
        assert selected(m)["operator_ast"]["composition"] == "compare_fragments"
        for n in [6, 8]:
            gold = rows("duplicate", [n])
            p = predict(
                m, [{k: v for k, v in r.items() if k != "accepted"} for r in gold]
            )["predictions"]
            assert all((x["score"] >= 0.5) == r["accepted"] for x, r in zip(p, gold))
    tr = rows("mirror", [1, 2, 3, 4])
    tr = [
        record(["кот" if t == "S" else "лес" for t in r["tokens"]], r["accepted"])
        for r in tr
    ]
    m = fit(tr, request())
    assert selected(m)["verifier_result"]["status"] == "CHECKED_INSTANCE"


def test_compositional126_is_bounded_without_relaxing_literal64():
    m = fit(rows("mirror", [1, 2, 3, 4, 5, 6]), request())
    assert selected(m)["verifier_result"]["verified_witnesses"] == 126
    q = request()
    q.pop("promotion_policy")
    m = fit(rows("mirror", [1, 2, 3, 4, 5, 6]), q)
    assert any(
        r.get("failed_obligation") == "FINITE_SHORT_WORD_SCOPE_REQUIRED"
        for r in m["derivation_trace"]
    )
