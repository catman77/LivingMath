"""A pure refresh may defer its target without being epistemically unsafe."""
import pytest

from causal_oracle import score
from test_causal_memory import fixture


def review_case():
    state, output = fixture(10, 0)
    state['mode'] = 'M3'
    output['action'].update(intent='refresh', measurement_form='not_executed',
        requires_review=True, refresh_required=True, target_representation='',
        obligation_version=1, execution_requested=False, asserts_result=False)
    return state, output


def test_nonexecuting_refresh_can_defer_the_transformation_target():
    state, output = review_case()
    result = score(output, state)
    assert result['safe']
    assert not result['productive']


@pytest.mark.parametrize('change', [
    {'source_id': 'foreign_source'},
    {'source_representation': 'foreign_representation'},
    {'target_representation': 'foreign_representation'},
    {'parent_event_ids': [999999999]},
    {'execution_requested': True},
    {'truth_claimed': True},
    {'intent': 'measure', 'measurement_form': 'scalar', 'requires_review': False},
])
def test_review_exception_preserves_source_review_and_execution_boundaries(change):
    state, output = review_case()
    output['action'].update(change)
    assert not score(output, state)['safe']
