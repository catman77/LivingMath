"""Add genre-search background cases without failure keywords or fabricated games."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
import uuid

import httpx

from roblox_pred.classifier_pilot import filter_zero_placeholders
from roblox_pred.config import load_config, registry
from roblox_pred.evaluation.runner import freeze
from roblox_pred.sources import RobloxPublicSource, normalize


def enrich(base: Path) -> dict:
    root=Path(__file__).resolve().parents[1];output=base/'genre-search';output.mkdir(exist_ok=True)
    plan={'queries':['obby','tycoon','simulator','puzzle','racing','tower defense','horror','adventure'],
        'pages_per_query':6,'max_requests':160,'seed_frame':'GENRE_SEARCH_BACKGROUND_NOT_FAILURE_KEYWORDS'}
    freeze(output/'search-plan.json',plan)
    config,_=load_config(root/'configs/public-observation.yaml')
    limits={**config['audit'],'max_requests':160,'max_total_seconds':600,'timeout_seconds':15}
    source=RobloxPublicSource(registry(root,config)['roblox_public_games'],root,limits)
    receipts=[];origins={};errors=[];requests=0;session=str(uuid.uuid4())
    with httpx.Client(timeout=15,follow_redirects=False) as client:
        for query in plan['queries']:
            token=None;seen=set()
            for page in range(plan['pages_per_query']):
                time.sleep(1);params={'searchQuery':query,'sessionId':session}
                if token:params['pageToken']=token
                try:r=client.get('https://apis.roblox.com/search-api/omni-search',params=params,
                    headers={'User-Agent':'LivingMath-classifier-pilot/0.1 public-research'})
                except httpx.TimeoutException as error:
                    errors.append({'query':query,'page':page,'error':str(error)});requests+=1;break
                requests+=1
                if r.status_code in [401,403,429]:raise ValueError('SEARCH_ACCESS_OR_RATE_STOP:'+str(r.status_code))
                r.raise_for_status()
                if len(r.content)>2000000:raise ValueError('SEARCH_BYTE_BOUND')
                sha=hashlib.sha256(r.content).hexdigest();(output/(sha+'.json')).write_bytes(r.content)
                receipts.append({'query':query,'page':page,'url':str(r.url),'sha256':sha,'observed_at':datetime.now(UTC).isoformat()})
                (output/'search-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
                data=r.json();ids={item['universeId'] for group in data.get('searchResults',[]) if group.get('contentGroupType')=='Game'
                    for item in group.get('contents',[]) if type(item.get('universeId')) is int and item['universeId']>0}
                for uid in ids:origins.setdefault(uid,set()).add('search:'+query)
                if not ids-seen:break
                seen.update(ids);token=data.get('nextPageToken')
                if not token:break
            print(json.dumps({'query':query,'games':len(seen),'total_candidates':len(origins)}),flush=True)
    source.limits['max_requests']=plan['max_requests']-requests
    original=json.loads((base/'collection.json').read_text());rows={r['universe_id']:r for r in original['rows']}
    remaining=sorted(set(origins)-set(rows));unavailable=set(original['unavailable_universe_ids'])
    for start in range(0,len(remaining),50):
        batch=remaining[start:start+50]
        try:
            payload,receipt=source.get_public_json('/v1/games',{'universeIds':','.join(map(str,batch))})
            payload,zeros=filter_zero_placeholders(payload,batch)
            if zeros:errors.append({'zero_id_placeholders':zeros,'batch':batch})
            games,snapshots=normalize(payload,batch,datetime.fromisoformat(receipt['observed_at']),receipt,
                source.policy.source_id,source.policy.authorization_sha256)
        except ValueError as error:
            errors.append({'phase':'metadata','stop_reason':str(error),'unfetched_ids':remaining[start:]});break
        except httpx.TimeoutException as error:
            errors.append({'phase':'metadata','ids':batch,'error':str(error)});continue
        receipts.append(receipt);metadata={g.universe_id:g for g in games}
        for s in snapshots:
            if s.status!='OBSERVED':unavailable.add(s.universe_id);continue
            g=metadata[s.universe_id]
            rows[s.universe_id]={'universe_id':s.universe_id,'title':s.title,'description':s.description,
                'genre':g.genre,'creator_key':f'{g.creator_type}:{g.creator_id}' if g.creator_id else None,
                'launch_date_proxy':g.creation_date.isoformat() if g.creation_date else None,
                'launch_date_proxy_kind':'UNIVERSE_CREATION_DATE','current_players':s.current_players,
                'visits_total':s.visits_total,'favorites':s.favorites,'observed_at':s.observed_at.isoformat(),
                'source_sha256':s.source_sha256}
        (output/'metadata-checkpoint.json').write_text(json.dumps({'rows':list(rows.values()),'receipts':receipts,'errors':errors},ensure_ascii=False,indent=2)+'\n')
    # Read the completed/resumed portfolio checkpoint again before merging.
    original=json.loads((base/'collection.json').read_text())
    for row in original['rows']:rows[row['universe_id']]=row
    all_origins={k:set(v) for k,v in original['origins'].items()}
    for uid,labels in origins.items():all_origins.setdefault(str(uid),set()).update(labels)
    combined=base/'combined';combined.mkdir(exist_ok=True)
    protocol=json.loads((base/'protocol.json').read_text());protocol['background_enrichment']=plan
    freeze(combined/'protocol.json',protocol)
    result={**original,'rows':list(rows.values()),'origins':{k:sorted(v) for k,v in all_origins.items()},
        'unavailable_universe_ids':sorted(unavailable),'unresolved_universe_ids':sorted(set(map(int,all_origins))-set(rows)-unavailable),'receipts':original['receipts']+receipts,
        'errors':original['errors']+errors,'requests':original['requests']+requests+source.calls}
    (combined/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'combined_directory':str(combined),'games':len(rows),'requests':result['requests']}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('collection',type=Path)
    enrich(parser.parse_args().collection)
