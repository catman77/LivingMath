import pytest

from roblox_pred.evaluation import metrics


def test_top_fraction_and_lift_use_test_prevalence():
    r=metrics([0,0,0,1],[.1,.2,.3,.9],['a','b','c','d'],.25)
    assert r['precision_at_fraction']==1 and r['lift_at_fraction']==4
    assert r['brier']==pytest.approx(.0375)


def test_ties_are_deterministic_and_bad_probabilities_rejected():
    a=metrics([1,0],[.5,.5],['b','a'],.5)
    assert a['selected_sample_ids']==['a']
    with pytest.raises(ValueError,match='PROBABILITY'):metrics([1,0],[2,.5],['b','a'],.5)


def test_undefined_auc_is_null_not_fake_perfect():
    r=metrics([0,0],[.1,.2],['a','b'],.5)
    assert r['roc_auc'] is None and r['lift_at_fraction'] is None
