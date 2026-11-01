"""Offline recovery of successfully captured metadata after a stopped HTTP batch."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from roblox_pred.config import load_config, registry
from roblox_pred.evaluation.runner import freeze
from roblox_pred.sources import normalize


def recover(base: Path) -> dict:
    root=Path(__file__).resolve().parents[1];original=json.loads((base/'collection.json').read_text())
    plan=json.loads((base/'genre-search/search-plan.json').read_text())
    origins={int(k):set(v) for k,v in original['origins'].items()}
    search_captures=[]
    for file in sorted((base/'genre-search').glob('*.json')):
        data=json.loads(file.read_text())
        if 'searchResults' not in data:continue
        search_captures.append({'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
            'capture_persisted_at':datetime.fromtimestamp(file.stat().st_mtime,UTC).isoformat()})
        for group in data['searchResults']:
            if group.get('contentGroupType')!='Game':continue
            for item in group.get('contents',[]):
                if type(item.get('universeId')) is int and item['universeId']>0:
                    origins.setdefault(item['universeId'],set()).add('genre_search_background')
    config,_=load_config(root/'configs/public-observation.yaml')
    policy=registry(root,config)['roblox_public_games']
    start=datetime.fromisoformat(original['receipts'][0]['observed_at']).timestamp()
    rows={r['universe_id']:r for r in original['rows']};recovered=0;captures=[]
    for file in sorted((root/'data/raw/captures').glob('*.json'),key=lambda p:p.stat().st_mtime):
        if file.stat().st_mtime<start:continue
        raw=file.read_bytes();data=json.loads(raw);records=data.get('data',[])
        if not records or not all('playing' in r and 'creator' in r for r in records):continue
        ids=[r['id'] for r in records]
        # Only accept source IDs selected in the chart/portfolio/search frame, never unrelated captures.
        if any(uid not in origins for uid in ids) or len(ids)!=len(set(ids)):continue
        sha=hashlib.sha256(raw).hexdigest()
        if file.stem!=sha:raise ValueError('CAPTURE_FILE_HASH_DRIFT')
        timestamp=datetime.fromtimestamp(file.stat().st_mtime,UTC)
        receipt={'response_sha256':sha,'source_id':policy.source_id,
            'timestamp_basis':'RAW_FILE_PERSISTENCE_MTIME_NOT_ORIGINAL_HTTP_RECEIPT',
            'capture_persisted_at':timestamp.isoformat(),'recovery_scope':'OFFLINE_NO_NEW_REQUESTS'}
        games,snapshots=normalize(data,ids,timestamp,receipt,policy.source_id,policy.authorization_sha256)
        metadata={g.universe_id:g for g in games};captures.append(receipt)
        for s in snapshots:
            if s.universe_id in rows:continue
            g=metadata[s.universe_id]
            rows[s.universe_id]={'universe_id':s.universe_id,'title':s.title,'description':s.description,
                'genre':g.genre,'creator_key':f'{g.creator_type}:{g.creator_id}' if g.creator_id else None,
                'launch_date_proxy':g.creation_date.isoformat() if g.creation_date else None,
                'launch_date_proxy_kind':'UNIVERSE_CREATION_DATE','current_players':s.current_players,
                'visits_total':s.visits_total,'favorites':s.favorites,'observed_at':timestamp.isoformat(),
                'source_sha256':sha,'timestamp_basis':'RAW_FILE_PERSISTENCE_MTIME'}
            recovered+=1
    output=base/'combined';output.mkdir(exist_ok=True)
    protocol=json.loads((base/'protocol.json').read_text());protocol['background_enrichment']=plan
    freeze(output/'protocol.json',protocol)
    result={**original,'rows':list(rows.values()),'origins':{str(k):sorted(v) for k,v in origins.items()},
        'search_source_captures':search_captures,'recovered_game_captures':captures,
        'recovered_games':recovered,'unresolved_universe_ids':sorted(set(origins)-set(rows)),
        'errors':original['errors']+[{'phase':'genre_metadata','stop_reason':'HTTP_429; no further network; recovered successful raw captures offline'}],
        'requests':None,'portfolio_requests':original['requests'],'search_requests_captured':len(search_captures),
        'total_requests_note':'Exact interrupted genre-request count unavailable; raw successful captures and 429 log retained'}
    (output/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'directory':str(output),'games':len(rows),'recovered':recovered,'unresolved':len(result['unresolved_universe_ids'])}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('collection',type=Path)
    recover(parser.parse_args().collection)
