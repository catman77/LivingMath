"""Auditable, deliberately narrow Pfirst import; no retrospective text reconstruction."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from statistics import mean

from roblox_pred.config import authorize, digest, registry
from roblox_pred.features import from_snapshot, validate_as_of
from roblox_pred.schemas import Game, Outcome, Sample, Snapshot, target_window, utc

METRIC = 'mean_daily_sampled_current_players_d61_90'


def aggregate_outcome(universe_id: int, as_of: datetime, snapshots: list[Snapshot],
                      *, hour: int = 18, tolerance_minutes: int = 30) -> Outcome:
    start, end = target_window(as_of)
    days = {}
    for row in snapshots:
        if row.universe_id != universe_id or not start <= row.observed_at < end:
            continue
        scheduled = row.observed_at.replace(hour=hour, minute=0, second=0, microsecond=0)
        distance = abs((row.observed_at-scheduled).total_seconds())
        if distance > tolerance_minutes*60:
            continue
        # Earliest capture per scheduled day is fixed before inspecting its value/status.
        key = row.observed_at.date()
        if key not in days or (row.observed_at, row.record_id) < (days[key].observed_at, days[key].record_id):
            days[key] = row
    valid = [r for r in days.values() if r.status == 'OBSERVED' and r.current_players is not None]
    complete = len(valid) == 30
    flags = [] if complete else ['MISSING_OR_CENSORED_DAILY_OBSERVATION']
    return Outcome(record_id=digest([universe_id, as_of, METRIC, sorted(r.record_id for r in days.values())]),
        universe_id=universe_id, as_of=as_of, window_start=start, window_end=end, metric=METRIC,
        raw_measure=mean(r.current_players for r in valid) if complete else None,
        eligibility_flags=[] if complete else ['INCOMPLETE_HORIZON'], censoring_flags=flags,
        source_provenance={'rule': 'EARLIEST_CAPTURE_PER_UTC_DAY_WITHIN_REGISTERED_SLOT',
            'daily_sample_count': len(valid), 'selected_snapshot_ids': sorted(r.record_id for r in days.values()),
            'available_at': max([end, *(r.ingested_at for r in days.values())]).isoformat(),
            'sampling_hour_utc': hour, 'tolerance_minutes': tolerance_minutes,
            'is_daily_mean_ccu': False})


def checked_file(root: Path, ref: dict) -> Path:
    path = (root / ref['path']).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise ValueError('IMPORT_PATH_OUTSIDE_PROJECT')
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
        raise ValueError('IMPORT_FILE_HASH_DRIFT:' + ref['path'])
    return path


def read_records(path: Path, model) -> list:
    if path.suffix == '.parquet':
        import pyarrow.parquet as pq
        return [model.model_validate(r) for r in pq.read_table(path).to_pylist()]
    return [model.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def build_dataset(root: Path, config: dict) -> tuple[list[Sample], dict, dict]:
    manifest_path = root / config['input_manifest']
    if not manifest_path.exists():
        raise ValueError('DATA_GATE_PENDING:NO_OBSERVED_DATASET_MANIFEST; нет зарегистрированной истории и завершённых исходов')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 'roblox-pred-import/1' or config['scenario'] != 'Pfirst':
        raise ValueError('SUPPORTED_IMPORT_IS_PFIRST_ONLY')
    if manifest['frame_id'] != config['cohort']['frame_id']:
        raise ValueError('COHORT_FRAME_PROTOCOL_MISMATCH')
    policies = registry(root, config)
    policy = policies[manifest['source_id']]
    authorize(policy, root)
    if not policy.sampling_frame_confirmed:
        raise ValueError('FIXED_SAMPLING_FRAME_REQUIRED')
    games = read_records(checked_file(root, manifest['files']['games']), Game)
    snapshots = read_records(checked_file(root, manifest['files']['snapshots']), Snapshot)
    for records in [games, snapshots]:
        if len({r.record_id for r in records}) != len(records):
            raise ValueError('DUPLICATE_IMPORT_RECORD_ID')
    cohort = json.loads(checked_file(root, manifest['files']['cohort']).read_text())
    captures = manifest['captures']
    for sha, ref in captures.items():
        if ref['sha256'] != sha:
            raise ValueError('CAPTURE_HASH_KEY_MISMATCH')
        checked_file(root, ref)
    if (not cohort or len({r['universe_id'] for r in cohort}) != len(cohort)
            or len({r['sample_id'] for r in cohort}) != len(cohort)):
        raise ValueError('EMPTY_OR_DUPLICATE_COHORT')
    enrolled = {r['universe_id'] for r in cohort}
    if any(r.universe_id not in enrolled for r in games + snapshots):
        raise ValueError('UNENROLLED_DATA_CANNOT_CHANGE_COHORT')
    for row in games + snapshots:
        if row.source_id != policy.source_id or row.source_license != policy.authorization_sha256:
            raise ValueError('SOURCE_LICENSE_BINDING_REQUIRED')
        sha = row.source_sha256 if isinstance(row, Snapshot) else row.source_provenance.get('response_sha256')
        if sha not in captures:
            raise ValueError('EXACT_SOURCE_VERSION_CAPTURE_REQUIRED')
        if isinstance(row, Snapshot) and row.ingested_at < row.observed_at:
            raise ValueError('BACKDATED_CAPTURE_KNOWLEDGE')
        stamp = row.ingested_at if isinstance(row, Snapshot) else row.known_at
        if stamp > datetime.now(UTC):
            raise ValueError('FUTURE_IMPORT_NOT_OBSERVED')
    result = []; outcomes = []
    origin = utc(datetime.fromisoformat(manifest['origin']))
    for item in cohort:
        uid = item['universe_id']; as_of = utc(datetime.fromisoformat(item['as_of']))
        if utc(datetime.fromisoformat(item['enrolled_at'])) > as_of:
            raise ValueError('COHORT_SELECTED_AFTER_AS_OF')
        observed = sorted([r for r in snapshots if r.universe_id == uid], key=lambda r: r.observed_at)
        available = [r for r in observed if r.observed_at <= as_of and r.ingested_at <= as_of]
        metadata = [g for g in games if g.universe_id == uid and g.known_at <= as_of]
        # Pfirst is the first retained capture, never an invented release date.
        if observed and (not available or observed[0].record_id != available[0].record_id):
            raise ValueError('PFIRST_FIRST_CAPTURE_NOT_AVAILABLE')
        if available and as_of != available[0].ingested_at:
            raise ValueError('PFIRST_CUTOFF_NOT_FIRST_CAPTURE')
        game = max(metadata, key=lambda r: r.known_at) if metadata else None
        snapshot = available[0] if available else None
        features = from_snapshot(game, snapshot, as_of) if game and snapshot else {}
        target = aggregate_outcome(uid, as_of, observed, hour=config['utc_daily_sampling_hour'],
                                   tolerance_minutes=config['sampling_tolerance_minutes'])
        outcomes.append(target)
        creator = f'{game.creator_type}:{game.creator_id}' if game and game.creator_id else None
        sample = Sample(sample_id=item['sample_id'], universe_id=uid, creator_key=creator,
            creator_known_at=game.known_at if game else as_of, as_of=as_of, scenario='Pfirst',
            release_date=None, release_precision='UNKNOWN', cohort_frame=manifest['frame_id'],
            source_id=policy.source_id, source_license=policy.authorization_sha256, features=features,
            clone_group_id=item.get('clone_group_id'), clone_known_at=item.get('clone_known_at'),
            outcome_metric=METRIC, outcome_window_start=target.window_start, horizon_end=target.window_end,
            outcome=target.raw_measure, outcome_days=target.source_provenance['daily_sample_count'],
            outcome_available_at=target.source_provenance['available_at'],
            eligibility_flags=target.eligibility_flags + ([] if game and snapshot else ['NO_AS_OF_CAPTURE']),
            censoring_flags=target.censoring_flags)
        validate_as_of(sample); result.append(sample)
    if min(s.as_of for s in result) != origin:
        raise ValueError('ORIGIN_NOT_FIRST_ENROLLED_CAPTURE')
    return result, {'manifest_sha256': digest(manifest), 'origin': origin.isoformat(),
        'frame_size': len(cohort), 'complete_outcomes': sum(s.outcome is not None for s in result),
        'censored_or_pending': sum(s.outcome is None for s in result), 'synthetic': False}, {
            'games': games, 'snapshots': snapshots, 'outcomes': outcomes}
