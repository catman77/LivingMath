import pytest

from normalization_pilot import retained_branch


@pytest.mark.parametrize('values',[['I'],['Branch I'],['event:4'],['4']])
def test_explicit_aliases_of_the_registered_source_branch(values):
    assert retained_branch(values,{'refs':{'independent':'event:4'}})


@pytest.mark.parametrize('values',[[],['event:5'],['Other I'],['event:4suffix']])
def test_unknown_or_foreign_source_is_not_a_branch_alias(values):
    assert not retained_branch(values,{'refs':{'independent':'event:4'}})
