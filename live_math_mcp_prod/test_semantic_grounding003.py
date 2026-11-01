"""Source-grounding contracts; synthetic controls are never historical evidence."""
from copy import deepcopy
import pytest

from artifact_genesis.source import packet_from_text
from semantic_grounding.critic import critique
from semantic_grounding.proposer import propose
from semantic_grounding.contract import validate_pair, independent_spans


def fixture(context, *, negative=False, inverted=False):
    first = 'The engineer met the pilot.' if inverted else 'The pilot met the engineer.'
    second = 'He did not return at dawn.' if negative else 'He returned at dawn.'
    combined = packet_from_text('test-roles', first + '\n' + second + '\n' + context + '\n')
    train = combined.model_copy(update={'spans': combined.spans[:2]})
    challenge = combined.model_copy(update={'spans': combined.spans[2:]})
    return train, challenge


def test_same_grammar_different_independent_referents():
    train, actor = fixture('In this account, "he" refers to the pilot.')
    other_train, patient = fixture('In this account, "he" refers to the engineer.')
    assert [s.text for s in train.spans] == [s.text for s in other_train.spans]
    assert critique(train, actor, 'anaphora')['label'] == 'SAME_ROLE'
    assert critique(other_train, patient, 'anaphora')['label'] == 'DIFFERENT_ROLE'


def test_conflicting_definitions_remain_unresolved():
    train, context = fixture('In this account, "he" refers to the pilot.\nIn this account, "he" refers to the engineer.')
    assert critique(train, context, 'anaphora')['label'] == 'UNRESOLVED'


def test_missing_independent_evidence_cannot_choose_reading():
    train, _ = fixture('This is another chapter.')
    assert critique(train, None, 'anaphora')['label'] == 'UNRESOLVED'
    with pytest.raises(ValueError, match='OVERLAP'):
        independent_spans(train, train)


def test_two_raw_competing_hypotheses_with_opposite_predictions():
    train, _ = fixture('In this account, "he" refers to the pilot.')
    proposals = propose(train, 'anaphora')
    validate_pair(proposals, train)
    assert len(proposals) == 2
    assert proposals[0]['prediction']['label'] != proposals[1]['prediction']['label']
    assert all(h['target_binding'] is None for h in proposals)


def test_false_quote_and_role_offset_rejected():
    train, _ = fixture('In this account, "he" refers to the pilot.')
    hs = propose(train, 'anaphora')
    wrong = deepcopy(hs)
    wrong[0]['quoted_evidence'][0]['quote'] += ' forged'
    with pytest.raises(ValueError):
        validate_pair(wrong, train)
    wrong = deepcopy(hs)
    wrong[0]['roles'][0]['start'] += 1
    with pytest.raises(ValueError):
        validate_pair(wrong, train)


def test_negation_preserved_without_changing_explicit_reference():
    train, context = fixture('In this account, "he" refers to the pilot.', negative=True)
    r = critique(train, context, 'anaphora')
    assert r['label'] == 'SAME_ROLE'
    assert r['distinctions']['negation']
    assert r['event_occurrence_established'] is False


def test_subject_inversion_uses_definition_not_nearest_word():
    train, context = fixture('In this account, "he" refers to the pilot.', inverted=True)
    assert critique(train, context, 'anaphora')['label'] == 'DIFFERENT_ROLE'


def test_source_critic_does_not_accept_target_truth_or_proposal_rationale():
    train, context = fixture('In this account, "he" refers to the pilot.')
    with pytest.raises(TypeError):
        critique(train, context, 'anaphora', target_result={'status': 'proved'})
    with pytest.raises(TypeError):
        critique(train, context, 'anaphora', proposal_rationale='Choose the first hypothesis.')


def test_pronoun_reference_does_not_assert_actor_object_identity():
    train, _ = fixture('In this account, "he" refers to the pilot.')
    for h in propose(train, 'anaphora'):
        assert len(h['roles']) == 3
        query = h['proposed_relation']['reference_query']
        assert query['actor_and_object_identity_asserted'] is False
        assert h['proposed_relation']['src'] == h['roles'][2]['id']
        assert h['proposed_relation']['dst'] == query['candidate_referent']
