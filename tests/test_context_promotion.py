"""FIX-B2: labelled operator witness -> registered predicate -> independent checking."""

import copy, hashlib
from itertools import product
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.observer_synthesis.learner import fit, predict
from lm_suti_assurance.observer_synthesis.features import encode, verify_feature


def record(word, train=False):
    text = " ".join(word)
    result = {
        "id": digest(text),
        "tokens": list(word),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "generated finite test",
            "edition": "FIX-B2/1",
        },
    }
    if train:
        result["accepted"] = any(
            word[i : i + 2] == tuple("SP") for i in range(len(word) - 1)
        )
    return result


def fixture():
    return [record(w, True) for n in [1, 2, 3] for w in product("SP", repeat=n)]


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
            "derive_relations": True,
            "feature_denylist": ["pair_0_max", "pair_0_min", "pair_0_final"],
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
        },
        "search": {
            "seed": 137,
            "max_composition_depth": 4,
            "max_contexts": 128,
            "max_cpu_ms": 4000,
            "max_proposals": 128,
            "max_witnesses": 512,
        },
    }


def trained():
    rows = fixture()
    model = fit(rows, request())
    child = next(f for f in model["feature_registry"] if f.get("role") == "PREDICTIVE")
    return rows, model, child


def test_actual_promotion_no_builtins_frozen_holdout_and_baselines(monkeypatch):
    from lm_suti_assurance.symbolic import grammar

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled builtin feature calculator used")

    monkeypatch.setattr(grammar, "features", forbidden)
    rows, model, child = trained()
    assert model["used_feature_ids"] == [child["feature_id"]]
    assert child["origin"] == "DERIVED_FROM_OPERATORS" and child["execution_verified"]
    assert child["verifier_result"]["status"] == "CHECKED_INSTANCE"
    assert model["identifiability_status"] == "UNDERDETERMINED"
    assert model["promotion_statistics"]["executed_promotion_rules"] == 1
    assert model["promotion_statistics"]["registered_promoted_features"] == 2
    q = request()
    q["feature_policy"]["derive_relations"] = False
    baseline = fit(rows, q)
    seal = model["hypothesis_digest"]
    for length, correct_baseline in [(4, 5), (5, 6)]:
        queries = [record(w) for w in product("SP", repeat=length)]
        labels = [
            any(w[i : i + 2] == tuple("SP") for i in range(len(w) - 1))
            for w in product("SP", repeat=length)
        ]
        predicted = predict(model, queries)["predictions"]
        ablated = predict(baseline, queries)["predictions"]
        assert all((r["score"] >= 0.5) == y for r, y in zip(predicted, labels))
        assert (
            sum((r["score"] >= 0.5) == y for r, y in zip(ablated, labels))
            == correct_baseline
        )
        assert model["hypothesis_digest"] == seal and all(
            "accepted" not in r for r in queries
        )
        assert {r["id"] for r in rows}.isdisjoint(r["id"] for r in queries)


@pytest.mark.parametrize("parent_index", [0, 1, 2])
def test_disabling_each_real_parent_blocks_promoted_predicate(parent_index):
    rows, model, child = trained()
    q = request()
    q["feature_policy"]["feature_denylist"].append(
        child["parent_feature_refs"][parent_index]
    )
    ablated = fit(rows, q)
    assert child["feature_id"] not in ablated["enabled_feature_ids"]
    assert any(
        r.get("failed_obligation") == "PARENT_OR_FEATURE_DISABLED"
        for r in ablated["derivation_trace"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "output_hash",
        "source_span",
        "operator",
        "origin",
        "hidden_labels",
        "parent",
        "scope",
        "missing_train",
    ],
)
def test_hostile_full_certificates_are_rejected_independently(mutation, monkeypatch):
    rows, model, feature = trained()
    samples = [{"record": r, "encoded": encode(r, "literal")} for r in rows]
    from lm_suti_assurance.observer_synthesis import promotion

    def forbidden(*a, **k):
        raise AssertionError("verifier invoked producer")

    monkeypatch.setattr(promotion, "execute", forbidden)
    assert verify_feature(feature, samples)["status"] == "CHECKED_INSTANCE"
    bad = copy.deepcopy(feature)
    if mutation == "output_hash":
        bad["construction_trace"][0]["operator_trace"][0]["output_word_hashes"][0] = (
            "0" * 64
        )
    elif mutation == "source_span":
        next(
            s
            for w in bad["construction_trace"]
            for s in w["states"].values()
            if s["source_spans"]
        )["source_spans"][0][0][1] += 1
    elif mutation == "operator":
        bad["construction_trace"][0]["operator_trace"][0]["operator"] = "EVAL"
    elif mutation == "origin":
        bad["origin"] = "BUILTIN"
    elif mutation == "hidden_labels":
        bad["promotion_proof"]["heldout_labels"] = {"fake": True}
    elif mutation == "parent":
        bad["dependency_features"][0]["origin"] = "BUILTIN"
    elif mutation == "scope":
        bad["known_invariance_scope"]["universal_invariant"] = True
    else:
        bad["construction_trace"].pop()
    assert verify_feature(bad, samples)["status"] == "REJECTED"


def test_missing_label_obligation_unknown_scope_and_no_fake_success():
    rows, model, child = trained()
    incomplete = [r for r in rows if r["tokens"] != ["S"]]
    failed = fit(incomplete, request())
    assert failed["synthesis_status"] == "NO_VERIFIABLE_NEW_OBSERVER"
    assert failed["promotion_statistics"]["failed_obligations"]
    assert all(f.get("role") != "PREDICTIVE" for f in failed["feature_registry"])
    unknown = predict(model, [record(tuple("S" * 9))])["predictions"][0]
    assert unknown["status"] == "UNKNOWN" and unknown["score"] is None


def test_no_language_flag_pattern_comes_from_utf8_train():
    rows = fixture()
    for r in rows:
        r["tokens"] = [{"S": "α", "P": "β"}[t] for t in r["tokens"]]
        text = " ".join(r["tokens"])
        r["id"] = digest(text)
        r["source"].update(text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    model = fit(rows, request())
    f = next(f for f in model["feature_registry"] if f.get("role") == "PREDICTIVE")
    assert f["operator_ast"]["predicate_ast"]["prototype_tokens"] == ["α", "β"]
    assert (
        verify_feature(
            f, [{"record": r, "encoded": encode(r, "literal")} for r in rows]
        )["status"]
        == "CHECKED_INSTANCE"
    )


def test_dyck_restricted_does_not_become_a_false_context_law():
    rows = []
    for n in [2, 4, 6]:
        for word in product("SP", repeat=n):
            if word.count("S") != word.count("P"):
                continue
            r = record(word)
            s = 0
            ok = True
            for t in word:
                s += 1 if t == "S" else -1
                ok &= s >= 0
            r["accepted"] = bool(ok and s == 0)
            rows.append(r)
    model = fit(rows, request())
    assert model["synthesis_status"] == "NO_VERIFIABLE_NEW_OBSERVER"
    assert model["promotion_statistics"]["failed_obligations"]


@pytest.mark.parametrize(
    "limit,value,obligation",
    [
        ("max_composition_depth", 1, "MAX_COMPOSITION_DEPTH"),
        ("max_witnesses", 27, "INSUFFICIENT_COMPLETE_TRAIN_WITNESS_BUDGET"),
    ],
)
def test_promotion_respects_declared_budgets(limit, value, obligation):
    q = request()
    q["search"][limit] = value
    model = fit(fixture(), q)
    assert model["synthesis_status"] == "NO_VERIFIABLE_NEW_OBSERVER"
    assert any(
        r.get("failed_obligation") == obligation for r in model["derivation_trace"]
    )
