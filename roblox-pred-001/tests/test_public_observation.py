import csv
from pathlib import Path

import httpx
import pytest

from roblox_pred.config import authorize, load_config, registry
from roblox_pred.sources import RobloxPublicSource
from roblox_pred.observation import observe_market

ROOT = Path(__file__).resolve().parents[1]


def policy_config():
    config,root=load_config(ROOT/'configs/public-observation.yaml')
    return registry(root,config)['roblox_public_games'],config


def test_public_observation_does_not_require_claimed_training_license():
    policy,_=policy_config()
    assert policy.rights_status == 'PUBLIC_API_OBSERVATION'
    authorize(policy,ROOT,collect=True)
    authorize(policy,ROOT)
    collection_only=policy.model_copy(update={'ml_allowed':False})
    authorize(collection_only,ROOT,collect=True)
    with pytest.raises(ValueError,match='SOURCE_RIGHTS_BLOCKED'):authorize(collection_only,ROOT)


def test_public_documentation_cannot_whitelist_arbitrary_source():
    policy,_=policy_config()
    with pytest.raises(ValueError,match='SOURCE_RIGHTS_BLOCKED'):
        authorize(policy.model_copy(update={'family':'THIRD_PARTY'}),ROOT,collect=True)


@pytest.mark.parametrize('path,params,error',[
    ('/v1/private-revenue',{},'UNDOCUMENTED_OR_PRIVATE_ENDPOINT'),
    ('https://example.com',{},'UNDOCUMENTED_OR_PRIVATE_ENDPOINT'),
    ('/v2/users/1/games',{'accessFilter':'All'},'PUBLIC_CATALOG_FILTER_REQUIRED')])
def test_public_transport_is_bounded_to_documented_public_methods(path,params,error):
    policy,config=policy_config()
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('unexpected network'))) as client:
        with pytest.raises(ValueError,match=error):
            RobloxPublicSource(policy,ROOT,config['audit'],client).get_public_json(path,params)


def test_public_market_end_to_end_in_isolated_storage(tmp_path,monkeypatch):
    import roblox_pred.observation as module
    policy,config=policy_config();config['audit']['interval_seconds']=0
    config['storage']={'directory':str(tmp_path/'store'),'database':str(tmp_path/'store/db.duckdb')}
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        if request.url.path=='/v1/games':
            ids=[int(i) for i in request.url.params['universeIds'].split(',')]
            return httpx.Response(200,json={'data':[{'id':i,'name':'Unit project '+str(i),'description':'Fixture',
                'created':'2020-01-01T00:00:00Z','playing':0,'visits':100,'genre':'Adventure',
                'creator':{'id':1,'type':'User'}} for i in ids]},request=request)
        assert request.url.params['accessFilter']=='Public'
        return httpx.Response(200,json={'data':[{'id':10,'isPlayable':True},{'id':11,'isPlayable':False}]},request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(module,'RobloxPublicSource',lambda *_:RobloxPublicSource(policy,ROOT,config['audit'],client))
        summary=observe_market(ROOT,config,tmp_path/'observation')
    assert len(calls)==5 and summary['games_observed']==7
    assert 11 not in summary['universe_ids'] and summary['zero_current_players']==7
    assert summary['revenue_robux'] is None and not summary['ml_training_performed']
    rows=list(csv.DictReader((tmp_path/'observation/projects.csv').open()))
    assert len(rows)==7 and all(r['revenue_robux']=='' for r in rows)
    assert all(r['revenue_status']=='OWNER_ANALYTICS_REQUIRED_NOT_PUBLIC' for r in rows)
    assert all(r['release_date']=='' for r in rows)


def test_installer_keeps_venv_interpreter_and_dry_run_does_not_write(tmp_path):
    import os
    import shlex
    import subprocess
    import sys
    result=subprocess.run([sys.executable,str(ROOT/'scripts/install_daily_timer.py'),'--dry-run'],
        env={**os.environ,'XDG_CONFIG_HOME':str(tmp_path/'config')},capture_output=True,text=True,check=True)
    command=next(line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('ExecStart='))
    executable=shlex.split(command)[0]
    probe=subprocess.run([executable,'-c','import sys; print(sys.prefix); import roblox_pred'],
        capture_output=True,text=True,check=True)
    assert probe.stdout.strip()==sys.prefix
    assert not (tmp_path/'config').exists()
