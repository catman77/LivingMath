import copy
import pytest
from lm_suti_assurance.symbolic.grammar import (
    fit,
    probability,
    baseline_fit,
    baseline_probability,
)
from lm_suti_assurance.core import digest
from lm_suti_assurance.errors import AssuranceError


def test_small_corpus_has_two_real_competing_grammars():
    train = [{"tokens": list(w), "accepted": True} for w in ("AB", "AABB")]
    g = fit(train)
    assert g["status"] == "UNDERDETERMINED"
    a, b = g["competing_train_compatible_models"]
    witness = g["distinguishing_word"]
    for s in train:
        assert (
            (s["tokens"] in a["accepted_words"])
            == (s["tokens"] in b["accepted_words"])
            == s["accepted"]
        )
    assert witness not in a["accepted_words"] and witness in b["accepted_words"]


def test_train_only_freeze_order_and_generic_distant_relation():
    train = [
        {"tokens": list(a + middle + b), "accepted": a == b}
        for a in "AB"
        for b in "AB"
        for middle in ("ABAB", "BABA", "AABB", "BBAA")
    ]
    g = fit(train)
    assert g["candidate_status"] == "EMPIRICAL"
    assert g["identifiability_status"] == g["status"] == "UNDERDETERMINED"
    frozen = copy.deepcopy(g)
    for a in "AB":
        for b in "AB":
            assert (probability(g, list(a + "ABBABAAB" * 4 + b)) >= 0.5) == (a == b)
    assert g == frozen and fit(list(reversed(train))) == g
    assert "endpoint_equal" in str(g["tree"])
    for kind in ("unigram", "bigram", "simple_context"):
        m = baseline_fit(train, kind)
        assert 0 < baseline_probability(m, list("ABBA")) < 1


def test_training_contradiction_is_not_an_invented_grammar():
    with pytest.raises(AssuranceError, match="CONTRADICTORY_TRAINING"):
        fit([{"tokens": ["x"], "accepted": True}, {"tokens": ["x"], "accepted": False}])
