from datetime import UTC, datetime, timedelta

import pytest

from roblox_pred.schemas import FeatureValue, Sample, target_window
from roblox_pred.features import validate_as_of


def sample():
    t = datetime(2020, 1, 1, tzinfo=UTC)
    start, end = target_window(t)
    return Sample(sample_id='s1', universe_id=1, creator_key='User:1', creator_known_at=t,
        as_of=t, scenario='Pfirst', release_date=None, release_precision='UNKNOWN',
        cohort_frame='fixed', source_id='licensed', source_license='explicit-ML-permission',
        features={'current_players': FeatureValue(value=0, known_at=t, source_observed_at=t,
            source_id='licensed', source_version_sha256='1' * 64)},
        outcome_metric='mean_daily_sampled_current_players_d61_90',
        outcome_window_start=start, horizon_end=end, outcome=5.0, outcome_days=30,
        outcome_available_at=end, synthetic=False)


def test_unknown_is_not_zero():
    s = sample(); s.features['favorites'] = s.features['current_players'].model_copy(update={'value': None})
    validate_as_of(s)
    assert s.features['current_players'].value == 0 and s.features['favorites'].value is None


def test_future_version_even_when_creation_date_is_old():
    s = sample(); f = s.features['current_players']
    s.features['title'] = f.model_copy(update={'value': 'current edited text',
        'known_at': s.as_of + timedelta(days=1), 'source_observed_at': s.as_of + timedelta(days=1)})
    with pytest.raises(ValueError, match='FUTURE_FEATURE'): validate_as_of(s)


def test_backdating_known_at_does_not_hide_future_capture():
    s = sample(); f = s.features['current_players']
    s.features['current_players'] = f.model_copy(update={'source_observed_at': s.as_of + timedelta(days=30)})
    with pytest.raises(ValueError, match='FUTURE_FEATURE|BACKDATED'): validate_as_of(s)


def test_future_creator_identity_rejected():
    s = sample().model_copy(update={'creator_known_at': datetime(2021, 1, 1, tzinfo=UTC)})
    with pytest.raises(ValueError, match='CREATOR_FUTURE'): validate_as_of(s)


def test_p7_needs_actual_release_evidence():
    s = sample().model_copy(update={'scenario': 'P7'})
    with pytest.raises(ValueError, match='RELEASE'): validate_as_of(s)


def test_outcome_window_must_match_registered_metric():
    s = sample().model_copy(update={'horizon_end': sample().as_of + timedelta(days=5)})
    with pytest.raises(ValueError, match='OUTCOME_WINDOW'): validate_as_of(s)


def test_naive_timestamps_rejected():
    with pytest.raises(ValueError, match='TIMEZONE'):
        FeatureValue(value=1, known_at=datetime(2020, 1, 1), source_observed_at=datetime(2020, 1, 1),
            source_id='x', source_version_sha256='1' * 64)
