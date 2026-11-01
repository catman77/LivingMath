"""Fetch a single Top Playing Now dataset for a quick model check."""
import argparse
import csv
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import uuid

import httpx

from roblox_pred.config import load_config, registry
from roblox_pred.sources import RobloxPublicSource


def collect(root: Path, config: dict, output: Path, limit: int = 50) -> dict:
    if not 1 <= limit <= 50: raise ValueError('Limit must be 1..50')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    url='https://apis.roblox.com/explore-api/v1/get-sorts'
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        with client.stream('GET',url,params={'sessionId':str(uuid.uuid4())},
                headers={'User-Agent':'LivingMath-quick-top/0.1 public-research'}) as response:
            response.raise_for_status();raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>2000000:raise ValueError('Chart response too large')
            chart_receipt={'url':str(response.url),'observed_at':datetime.now(UTC).isoformat(),
                'sha256':hashlib.sha256(raw).hexdigest()}
    (output/'chart-source.json').write_bytes(raw)
    charts=[s for s in json.loads(raw)['sorts'] if s.get('sortId')=='top-playing-now']
    if len(charts)!=1:raise ValueError('Top Playing Now chart not found')
    selected=[];seen=set()
    for item in charts[0]['games']:
        if item['universeId'] not in seen:
            selected.append(item);seen.add(item['universeId'])
        if len(selected)==limit:break
    if not selected:raise ValueError('Empty chart')
    source=RobloxPublicSource(registry(root,config)['roblox_public_games'],root,config['audit'])
    games,snapshots,receipt=source.fetch([r['universeId'] for r in selected])
    metadata={g.universe_id:g for g in games};observations={s.universe_id:s for s in snapshots}
    observed=datetime.fromisoformat(receipt['observed_at']);rows=[]
    for rank,item in enumerate(selected,1):
        uid=item['universeId'];g=metadata.get(uid);s=observations.get(uid)
        created=g.creation_date if g else None;age=(observed-created).total_seconds()/86400 if created else None
        visits=s.visits_total if s else None
        rows.append({'case_id':'roblox-'+str(uid),'chart_rank':rank,'universe_id':uid,
            'title':s.title if s else item.get('name'),'description':s.description if s else None,
            'genre':g.genre if g else item.get('genreL1'),
            'launch_date_proxy':created.date().isoformat() if created else None,
            'launch_date_proxy_kind':'UNIVERSE_CREATION_DATE' if created else 'UNKNOWN',
            'current_players':s.current_players if s else None,'visits_total':visits,
            'favorites':s.favorites if s else None,
            'visits_per_day_since_creation_proxy':round(visits/max(age,1),2)
                if visits is not None and age is not None and age>=0 else None,
            'observed_at':observed.isoformat()})
    with (output/'top_games.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'top_games.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    inputs=['case_id','title','description','genre','launch_date_proxy','launch_date_proxy_kind']
    (output/'model_input.jsonl').write_text(''.join(json.dumps({k:r[k] for k in inputs},ensure_ascii=False)+'\n' for r in rows))
    targets=['case_id','chart_rank','current_players','visits_total','favorites','visits_per_day_since_creation_proxy']
    with (output/'audience_labels.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=targets);writer.writeheader()
        writer.writerows({k:r[k] for k in targets} for r in rows)
    (output/'MODEL_PROMPT_RU.md').write_text('''# Быстрая проверка на топ-играх Roblox

В model_input.jsonl даны описание, жанр и приближённая дата запуска каждой игры.
Дата — creation date universe. Извлеки основной игровой цикл, награду, социальный
механизм, причины возвращаться и отличительную идею. Кратко обоснуй из описания;
неизвестное обозначай unknown. Дай относительный прогноз аудитории.
После фиксации ответов сравни их с audience_labels.csv: current_players —
текущий онлайн, visits_total — накопленные посещения. Visits/day proxy — visits,
делённые на возраст universe; это грубый масштаб интереса, не измеренный рост или DAU.
Это быстрая поперечная проверка среди популярных игр, не прогноз будущего релиза.
''')
    summary={'status':'READY_FOR_QUICK_MODEL_CHECK','rows':len(rows),'chart':'Top Playing Now',
        'chart_applied_filters':charts[0].get('appliedFilters'),'http_requests':2,
        'descriptions_present':sum(bool(r['description']) for r in rows),
        'launch_date_proxies_present':sum(r['launch_date_proxy'] is not None for r in rows),
        'audience_present':sum(r['current_players'] is not None for r in rows),
        'audience_min':min(r['current_players'] for r in rows if r['current_players'] is not None),
        'audience_max':max(r['current_players'] for r in rows if r['current_players'] is not None),
        'chart_receipt':chart_receipt,'games_receipt':receipt,'directory':str(output),'model_executed':False,
        'proxy_definitions':{'launch_date':'universe creation date','audience':'current concurrent players',
            'missing_dynamics':'lifetime visits / max(age_days,1); not measured growth or DAU'}}
    (output/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=50)
    parser.add_argument('--config',type=Path,default=Path('configs/public-observation.yaml'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();config,root=load_config(args.config)
    output=args.output or root/'data/quick-top'/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    print(json.dumps(collect(root,config,output,args.limit),ensure_ascii=False,indent=2))
