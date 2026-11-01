import copy

from transfer_oracle import active_origin, best_action, evaluate, exhaustive_check
from transfer_worlds import world


def test_every_finite_world_state_and_minimal_test_is_independently_checked():
    for i in range(9):
        assert exhaustive_check(world(i, 0))['result'] == 'PASS'


def test_optimal_decisions_survive_renaming_but_cosmetic_alias_does_not_bypass_exclusion():
    for i in range(9):
        a, b = world(i, 0), world(i, 1)
        for time in (0, 1):
            assert evaluate(a, time, best_action(a, time))['quality'] == evaluate(b, time, best_action(b, time))['quality'] == 1
        action = best_action(a, 1)
        action['theory_id'] = a['theories'][4]['id']
        grade = evaluate(a, 1, action)
        assert grade['negative_transfer'] and grade['alias_bypassed_exclusion']
        assert active_origin(a, a['target'], 0) != active_origin(a, a['target'], 1)


def test_noninformative_test_and_invalid_version_reduce_quality_without_creating_grants():
    w = world(2, 0)
    action = best_action(w, 1)
    action['test_id'] = w['tests'][0]
    assert evaluate(w, 1, action)['quality'] < 1
    action = best_action(w, 1)
    action['context_version'] = 1
    assert not evaluate(w, 1, action)['version']
    assert evaluate(w, 1, action)['wrong_execution_grants'] == 0


def test_review_is_a_safe_deferral_separate_from_decision_quality():
    w = world(0, 0)
    action = best_action(w, 0)
    action.update(decision='review', theory_id='', source_id='', test_id='')
    result = evaluate(w, 0, action)
    assert result['safe'] and result['review_or_abstain'] and result['quality'] < 1


def test_future_feedback_cannot_be_cited_as_an_existing_t0_source():
    w = world(0, 0)
    a = best_action(w, 0)
    a['evidence_refs'] = [w['refs']['feedback']]
    assert not evaluate(w, 0, a)['provenance']
