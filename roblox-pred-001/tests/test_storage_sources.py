from datetime import UTC, datetime

import httpx
import pyarrow.parquet as pq
import pytest

from roblox_pred.config import load_config, registry
from roblox_pred.sources import RobloxPublicSource, normalize
from roblox_pred.storage import Store


def fixture():
    return {'data':[{'id':1,'creator':{'id':2,'type':'Group'},'name':'Original example',
        'description':'Original synthetic description','created':'2013-01-01T00:00:00Z',
        'visits':0,'playing':0}]}


def records():
    return normalize(fixture(),[1,2],datetime(2026,11,1,tzinfo=UTC),{'response_sha256':'1'*64},'unit','UNIT_ONLY')


def test_missing_game_is_censored_not_zero_or_deleted():
    games,snapshots=records()
    assert len(games)==1 and games[0].release_date is None
    assert snapshots[0].current_players==0 and snapshots[0].favorites is None
    assert snapshots[1].current_players is None and snapshots[1].status=='UNAVAILABLE_UNKNOWN'


def test_parquet_duckdb_roundtrip_and_append_only(tmp_path):
    games,ss=records();store=Store(tmp_path/'store')
    assert store.append('games',games)['inserted']==1
    first=store.append('snapshots',ss);assert first['inserted']==2
    assert store.append('snapshots',ss)['inserted']==0
    restored=store.rows('snapshots');assert [r.current_players for r in restored]==[0,None]
    p=pq.read_table(first['part']);assert p.schema.field('current_players').type.bit_width==64
    assert p.column('current_players').to_pylist()==[0,None]
    changed=ss[0].model_copy(update={'current_players':100})
    with pytest.raises(ValueError,match='APPEND_ONLY'):store.append('snapshots',[changed])
    assert store.rows('snapshots')[0].current_players==0


def test_denied_policy_blocks_before_network():
    from pathlib import Path
    cfg,root=load_config(Path(__file__).parents[1]/'configs/protocol.yaml')
    policies=registry(root,cfg)
    def fail(request): raise AssertionError('Network must not be called')
    client=httpx.Client(transport=httpx.MockTransport(fail))
    policy=policies['roblox_public_games'].model_copy(update={'rights_status':'DENIED','collection_allowed':False})
    source=RobloxPublicSource(policy,root,cfg['audit'],client)
    with pytest.raises(ValueError,match='SOURCE_RIGHTS_BLOCKED'):source.fetch([1])
    assert source.calls==0


def test_foreign_or_duplicate_source_ids_rejected():
    raw=fixture();raw['data'].append(raw['data'][0])
    with pytest.raises(ValueError,match='BINDING'):normalize(raw,[1],datetime.now(UTC),{},'s','x')
