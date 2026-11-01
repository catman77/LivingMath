"""Bounded public charts + creator portfolios, retaining weak/unknown examples."""
import argparse
from datetime import UTC, datetime
import json
import hashlib
from pathlib import Path
import random
import time
import uuid

import httpx
import yaml

from roblox_pred.config import load_config, registry
from roblox_pred.evaluation.runner import freeze
from roblox_pred.sources import RobloxPublicSource, normalize
from roblox_pred.classifier_pilot import filter_zero_placeholders


def collect(root: Path, protocol: dict, output: Path) -> dict:
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    freeze(output/'protocol.json',protocol)
    config,_=load_config(root/'configs/public-observation.yaml')
    settings=protocol['collection'];limits={**config['audit'],**{k:settings[k] for k in
        ['max_requests','max_seconds','interval_seconds']}}
    limits['max_total_seconds']=limits.pop('max_seconds')
    source=RobloxPublicSource(registry(root,config)['roblox_public_games'],root,limits)
    checkpoint=output/'collection.json'
    old=json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    receipts=old['receipts'] if old else [];errors=old['errors'] if old else []
    catalogs=old['catalogs'] if old else [];origins={int(k):set(v) for k,v in old['origins'].items()} if old else {}
    captured={r['universe_id']:r for r in old['rows']} if old else {}
    unavailable=set(old['unavailable_universe_ids']) if old else set()
    prior_requests=old['requests'] if old else 1;prior_seconds=old['seconds'] if old else 0
    source.limits['max_requests']=max(0,settings['max_requests']-prior_requests)
    source.limits['timeout_seconds']=15
    source.started-=prior_seconds
    started=time.monotonic()
    def save_checkpoint():
        result={'rows':list(captured.values()),'unavailable_universe_ids':sorted(unavailable),
            'origins':{str(k):sorted(v) for k,v in origins.items()},'receipts':receipts,
            'catalogs':catalogs,'errors':errors,'requests':source.calls+prior_requests,'seconds':prior_seconds+time.monotonic()-started}
        temporary=output/'collection.tmp'
        temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        temporary.replace(output/'collection.json')
        return result
    try:
        if not old:
            with httpx.Client(timeout=15,follow_redirects=False) as client:
                response=client.get('https://apis.roblox.com/explore-api/v1/get-sorts',
                    params={'sessionId':str(uuid.uuid4())},headers={'User-Agent':'LivingMath-classifier-pilot/0.1 public-research'})
                response.raise_for_status()
                if len(response.content)>2000000:raise ValueError('CHART_BYTE_BOUND')
                (output/'chart-source.json').write_bytes(response.content)
                receipts.append({'url':str(response.url),'sha256':hashlib.sha256(response.content).hexdigest(),
                    'observed_at':datetime.now(UTC).isoformat(),'http_status':response.status_code})
                for chart in response.json()['sorts']:
                    if chart.get('contentType')!='Games':continue
                    for item in chart.get('games',[]):origins.setdefault(item['universeId'],set()).add('chart:'+chart['sortId'])
        def details(ids):
            ids=sorted(set(ids)-set(captured)-unavailable)
            for start in range(0,len(ids),50):
                batch=ids[start:start+50]
                try:
                    payload,receipt=source.get_public_json('/v1/games',{'universeIds':','.join(map(str,batch))})
                    payload,zero_count=filter_zero_placeholders(payload,batch)
                    if zero_count:errors.append({'phase':'metadata','zero_id_placeholders':zero_count,'requested_ids':batch})
                    games,snapshots=normalize(payload,batch,datetime.fromisoformat(receipt['observed_at']),receipt,
                        source.policy.source_id,source.policy.authorization_sha256)
                except httpx.TimeoutException as error:
                    errors.append({'phase':'metadata','universe_ids':ids[start:start+50],'error':str(error)})
                    continue
                receipts.append(receipt)
                metadata={g.universe_id:g for g in games}
                for s in snapshots:
                    if s.status!='OBSERVED':unavailable.add(s.universe_id);continue
                    g=metadata[s.universe_id]
                    captured[s.universe_id]={'universe_id':s.universe_id,'title':s.title,'description':s.description,
                        'genre':g.genre,'creator_key':f'{g.creator_type}:{g.creator_id}' if g.creator_id else None,
                        'launch_date_proxy':g.creation_date.isoformat() if g.creation_date else None,
                        'launch_date_proxy_kind':'UNIVERSE_CREATION_DATE','current_players':s.current_players,
                        'visits_total':s.visits_total,'favorites':s.favorites,'observed_at':s.observed_at.isoformat(),
                        'source_sha256':s.source_sha256}
                save_checkpoint()
        details(origins)
        # Fixed seed order, not post-outcome selection of creators with weak games.
        creators=sorted({r['creator_key'] for uid,r in captured.items() if r['creator_key'] and any(o.startswith('chart:') for o in origins[uid])})
        random.Random(protocol['seed']).shuffle(creators)
        print(json.dumps({'stage':'charts','games':len(captured),'creators':len(creators)}),flush=True)
        completed={c['creator_key'] for c in catalogs}
        for index,creator in enumerate(creators[:settings['max_creators']]):
            if creator in completed:continue
            kind,uid=creator.split(':');cursor=None;ids=set();pages=0;truncated=False
            for page in range(settings['max_pages_per_creator']):
                path=f'/v2/groups/{uid}/gamesV2' if kind=='Group' else f'/v2/users/{uid}/games'
                params={'accessFilter':'Public','sortOrder':'Asc','limit':settings['page_size']}
                if cursor:params['cursor']=cursor
                try:payload,receipt=source.get_public_json(path,params)
                except httpx.TimeoutException as error:
                    errors.append({'phase':'catalog','creator':creator,'error':str(error)})
                    break
                except httpx.HTTPStatusError as error:
                    errors.append({'creator':creator,'http_status':error.response.status_code,'url':str(error.request.url)})
                    if error.response.status_code in [401,403,429]:raise
                    break
                receipts.append(receipt);pages+=1
                for item in payload.get('data',[]):
                    if item.get('isPlayable') is False:continue
                    candidate=item['id'];ids.add(candidate);origins.setdefault(candidate,set()).add('portfolio:'+creator)
                cursor=payload.get('nextPageCursor')
                if not cursor:break
                truncated=page+1==settings['max_pages_per_creator']
            catalogs.append({'creator_key':creator,'pages':pages,'ids':sorted(ids),'truncated':truncated})
            details(ids)
            save_checkpoint()
            if index%10==0:print(json.dumps({'stage':'portfolios','creators':index+1,'games':len(captured),'requests':source.calls+prior_requests}),flush=True)
            if len(captured)>=settings['target_games']:break
    except (ValueError,httpx.HTTPError) as error:
        errors.append({'stop_reason':str(error)})
    result=save_checkpoint()
    print(json.dumps({'directory':str(output),'games':len(captured),'requests':result['requests'],
        'seconds':result['seconds'],'stop':errors[-1] if errors else 'TARGET_OR_CREATOR_LIMIT'},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/classifier-pilot.yaml'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    protocol=yaml.safe_load(args.config.read_text())
    output=args.output or root/'data/classifier'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    collect(root,protocol,output)
