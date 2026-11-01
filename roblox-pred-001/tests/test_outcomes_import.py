from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest

from roblox_pred.features.dataset import aggregate_outcome, build_dataset
from roblox_pred.schemas import Snapshot, Game

T = datetime(2020, 1, 1, 18, tzinfo=UTC)


def snap(i, **change):
    stamp = T+timedelta(days=61+i)
    return Snapshot(record_id=str(i), universe_id=1, observed_at=stamp, ingested_at=stamp,
        source_id='test', source_license='test', source_sha256='a'*64, status='OBSERVED',
        current_players=change.pop('current_players', i), source_provenance={}, **change)


def test_thirty_distinct_days_and_genuine_zero():
    result = aggregate_outcome(1, T, [snap(i, current_players=0) for i in range(30)])
    assert result.raw_measure == 0 and result.source_provenance['daily_sample_count'] == 30
    assert not result.source_provenance['is_daily_mean_ccu']


def test_duplicate_day_cannot_replace_missing_day():
    result = aggregate_outcome(1, T, [snap(i) for i in range(29)] + [snap(0)])
    assert result.raw_measure is None and result.censoring_flags


def test_unavailable_cannot_be_zero_or_replaced_by_later_success():
    rows = [snap(i) for i in range(30)]
    bad = rows[0].model_copy(update={'status': 'UNAVAILABLE_UNKNOWN', 'current_players': None})
    good = rows[0].model_copy(update={'record_id': 'later', 'observed_at': rows[0].observed_at+timedelta(minutes=1)})
    result = aggregate_outcome(1, T, [bad, good, *rows[1:]])
    assert result.raw_measure is None


def test_sampling_slot_and_foreign_universe_are_not_outcomes():
    rows = [snap(i) for i in range(30)]
    rows[0] = rows[0].model_copy(update={'universe_id': 99})
    rows[1] = rows[1].model_copy(update={'observed_at': rows[1].observed_at+timedelta(hours=2)})
    result = aggregate_outcome(1, T, rows)
    assert result.raw_measure is None and result.source_provenance['daily_sample_count'] == 28


def test_import_manifest_missing_is_explicit_gate(tmp_path):
    with pytest.raises(ValueError, match='NO_LICENSED_MANIFEST'):
        build_dataset(tmp_path, {'input_manifest': 'missing.json'})


def imported(tmp_path):
    import yaml
    evidence = tmp_path/'license.txt'; evidence.write_text('UNIT FIXTURE ONLY: permitted for this test')
    sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    policy = dict(source_id='test', family='OPERATOR_IMPORT', documentation_url=None, terms_url=None,
        rights_status='EXPLICIT_EXCEPTION_OR_LICENSE', rights_reason='UNIT FIXTURE NOT ACTUAL RIGHTS',
        commercial_allowed=True, ml_allowed=True, collection_allowed=False, historical_snapshots=True,
        sampling_frame_confirmed=True, authorization_evidence='license.txt', authorization_sha256=sha)
    (tmp_path/'sources.yaml').write_text(yaml.safe_dump({'sources': [policy]}))
    body = tmp_path/'capture.json'; body.write_text(json.dumps({'fixture': True, 'values': list(range(30))}))
    bsha = hashlib.sha256(body.read_bytes()).hexdigest()
    rows = [snap(-61, current_players=0), *[snap(i) for i in range(30)]]
    rows = [r.model_copy(update={'source_license': sha, 'source_sha256': bsha}) for r in rows]
    game = Game(record_id='game', universe_id=1, creator_id=7, creator_type='User', creation_date=T-timedelta(days=1),
        known_at=T, source_id='test', source_license=sha, source_provenance={'response_sha256': bsha})
    (tmp_path/'games.jsonl').write_text(game.model_dump_json()+'\n')
    (tmp_path/'snapshots.jsonl').write_text('\n'.join(r.model_dump_json() for r in rows)+'\n')
    (tmp_path/'cohort.json').write_text(json.dumps([{'sample_id':'unit-1','universe_id':1,
        'as_of':T.isoformat(),'enrolled_at':T.isoformat()}]))
    ref = lambda name: {'path': name, 'sha256': hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()}
    manifest = dict(format='roblox-pred-import/1', frame_id='unit-frame', source_id='test', origin=T.isoformat(),
        files={k:ref(v) for k,v in [('games','games.jsonl'),('snapshots','snapshots.jsonl'),('cohort','cohort.json')]},
        captures={bsha:ref('capture.json')})
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    config = dict(input_manifest='manifest.json',scenario='Pfirst',sources_registry='sources.yaml',
        cohort={'frame_id':'unit-frame'},utc_daily_sampling_hour=18,sampling_tolerance_minutes=30)
    return config


def test_licensed_fixture_import_calculates_outcome_and_retains_asof(tmp_path):
    config = imported(tmp_path)
    rows, manifest, tables = build_dataset(tmp_path, config)
    assert len(rows) == 1 and rows[0].outcome == pytest.approx(14.5)
    assert rows[0].features['current_players'].known_at == T
    assert rows[0].release_date is None and manifest['frame_size'] == 1
    assert len(tables['outcomes']) == 1


def test_import_hash_drift_rejected(tmp_path):
    config = imported(tmp_path)
    (tmp_path/'capture.json').write_text('changed')
    with pytest.raises(ValueError, match='HASH_DRIFT'):
        build_dataset(tmp_path, config)
