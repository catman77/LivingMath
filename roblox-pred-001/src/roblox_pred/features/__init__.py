"""As-of validation and source-addressed feature construction."""
from datetime import timedelta
from roblox_pred.schemas import FeatureValue, Game, Sample, Snapshot, target_window

ALLOWED = {'visits_total', 'current_players', 'favorites', 'likes', 'dislikes',
           'age_days', 'genre', 'creator_prior_games', 'title', 'description', 'thumbnail_ref'}


def validate_as_of(sample: Sample) -> None:
    if sample.creator_known_at > sample.as_of:
        raise ValueError('CREATOR_FUTURE')
    if sample.clone_group_id is not None and (sample.clone_known_at is None or sample.clone_known_at > sample.as_of):
        raise ValueError('CLONE_FUTURE_OR_UNDATED')
    for name, value in sample.features.items():
        if name not in ALLOWED:
            raise ValueError('UNREGISTERED_OR_LEAKED_FEATURE_NAME:' + name)
        if value.known_at > sample.as_of or value.source_observed_at > sample.as_of:
            raise ValueError('FUTURE_FEATURE:' + name)
        if value.known_at < value.source_observed_at:
            raise ValueError('BACKDATED_FEATURE_VERSION:' + name)
        if value.capture_kind == 'HISTORICAL_CAPTURE' and not value.capture_evidence:
            raise ValueError('HISTORICAL_CAPTURE_EVIDENCE_REQUIRED')
    if sample.scenario in {'P7', 'P30'}:
        if sample.release_date is None or sample.release_precision != 'EXACT' or not sample.release_evidence:
            raise ValueError('EXACT_RELEASE_EVIDENCE_REQUIRED')
        day = 7 if sample.scenario == 'P7' else 30
        cutoff = sample.release_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day+1)
        if sample.as_of != cutoff - timedelta(microseconds=1):
            raise ValueError('SCENARIO_RELEASE_CUTOFF_MISMATCH')
    if sample.scenario == 'P0' and (sample.release_date is None or sample.as_of >= sample.release_date
            or sample.release_precision != 'EXACT' or not sample.release_evidence):
        raise ValueError('P0_PRE_RELEASE_EVIDENCE_REQUIRED')
    if (sample.outcome_window_start, sample.horizon_end) != target_window(sample.as_of):
        raise ValueError('OUTCOME_WINDOW_MISMATCH')


def from_snapshot(game: Game, snapshot: Snapshot, as_of) -> dict[str, FeatureValue]:
    if game.universe_id != snapshot.universe_id:
        raise ValueError('SOURCE_UNIVERSE_BINDING_MISMATCH')
    if game.known_at > as_of or snapshot.observed_at > as_of or snapshot.ingested_at > as_of:
        raise ValueError('FUTURE_FEATURE_SNAPSHOT')
    if game.creation_date is not None and game.creation_date > as_of:
        raise ValueError('FUTURE_CREATION_DATE')
    result = {}
    for name in ['visits_total', 'current_players', 'favorites', 'likes', 'dislikes', 'title', 'description', 'thumbnail_ref']:
        result[name] = FeatureValue(value=getattr(snapshot, name), known_at=snapshot.ingested_at,
            source_observed_at=snapshot.observed_at, source_id=snapshot.source_id,
            source_version_sha256=snapshot.source_sha256)
    for name, value in [('genre', game.genre), ('age_days',
            max(0, (as_of-game.creation_date).total_seconds()/86400) if game.creation_date else None)]:
        result[name] = FeatureValue(value=value, known_at=game.known_at, source_observed_at=game.known_at,
            source_id=game.source_id, source_version_sha256=game.source_provenance['response_sha256'])
    return result
