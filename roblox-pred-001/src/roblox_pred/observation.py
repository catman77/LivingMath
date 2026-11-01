"""Small public market snapshot. Public popularity never becomes invented revenue."""
import csv
from datetime import UTC, datetime
import json
from pathlib import Path

from roblox_pred.config import registry
from roblox_pred.evaluation.runner import freeze
from roblox_pred.sources import RobloxPublicSource
from roblox_pred.storage import Store


def observe_market(root: Path, config: dict, output: Path) -> dict:
    if output.exists():
        raise ValueError('OBSERVATION_OUTPUT_ALREADY_EXISTS')
    policies = registry(root, config)
    source = RobloxPublicSource(policies['roblox_public_games'], root, config['audit'])
    discovery = []; receipts = []; ids = set(config['audit']['requested_universe_ids'])
    # Known creator portfolios, not a claim to enumerate the entire Roblox market.
    for kind, uid in [('Group', 4372130), ('Group', 295182), ('Group', 2613928), ('User', 1)]:
        path = f'/v2/groups/{uid}/gamesV2' if kind == 'Group' else f'/v2/users/{uid}/games'
        payload, receipt = source.get_public_json(path, {'accessFilter':'Public', 'sortOrder':'Asc', 'limit':50})
        receipts.append(receipt)
        rows = payload['data']
        accepted = [r['id'] for r in rows if type(r.get('id')) is int and r['id'] > 0
                    and r.get('isPlayable') is not False]
        ids.update(accepted)
        discovery.append({'creator_type':kind, 'creator_id':uid, 'returned':len(rows),
            'accepted_universe_ids':accepted, 'unplayable_not_followed':sum(r.get('isPlayable') is False for r in rows),
            'pagination_truncated':bool(payload.get('nextPageCursor')), 'receipt':receipt})
    selected = sorted(ids)[:50]
    frame = {'frame_id':'ROBLOX-PUBLIC-PORTFOLIOS-001', 'frozen_at':datetime.now(UTC).isoformat(),
        'universe_ids':selected, 'selection':'FOUR_CREATOR_PUBLIC_PORTFOLIOS_PLUS_TRANSPORT_SEEDS_SORTED_ID_LIMIT50',
        'scope':'DESCRIPTIVE_PUBLIC_OBSERVATION_NOT_MARKETWIDE_PREDICTION',
        'discovery_request_sha256':[r['response_sha256'] for r in receipts]}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    freeze(output/'frame-before-observation.json', frame)
    games, snapshots, receipt = source.fetch(selected); receipts.append(receipt)
    store = Store(root/config['storage']['directory'], root/config['storage']['database'])
    stored = {'games':store.append('games', games), 'snapshots':store.append('snapshots', snapshots)}
    by_id = {g.universe_id:g for g in games}
    fields = ['universe_id','title','description','genre','creator','created_at','first_seen_at',
        'release_date','current_players','visits_total','favorites','revenue_robux','revenue_status','source_url']
    with (output/'projects.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in snapshots:
            g = by_id.get(row.universe_id)
            writer.writerow({'universe_id':row.universe_id,'title':row.title,'description':row.description,
                'genre':g.genre if g else None,'creator':f'{g.creator_type}:{g.creator_id}' if g else None,
                'created_at':g.creation_date.isoformat() if g and g.creation_date else None,
                'first_seen_at':row.observed_at.isoformat(),'release_date':None,
                'current_players':row.current_players,'visits_total':row.visits_total,'favorites':row.favorites,
                'revenue_robux':None,'revenue_status':'OWNER_ANALYTICS_REQUIRED_NOT_PUBLIC',
                'source_url':receipt['url']})
    summary = {'status':'PUBLIC_OBSERVATION_COLLECTED','observed_at':receipt['observed_at'],
        'frame_id':frame['frame_id'],'universe_ids':selected,'catalogs':discovery,'request_count':len(receipts),
        'games_observed':len(games),'unavailable':sum(s.status != 'OBSERVED' for s in snapshots),
        'zero_current_players':sum(s.current_players == 0 for s in snapshots),
        'descriptions_present':sum(bool(s.description) for s in snapshots),
        'revenue_robux':None,'revenue_status':'OWNER_ANALYTICS_REQUIRED_NOT_PUBLIC',
        'historical_revenue_or_launch_date_invented':False,'scope':frame['scope'],
        'first_snapshot_not_prediction_validation':True,'ml_training_performed':False,
        'storage':stored,'database':str(store.database),'csv':str(output/'projects.csv'),
        'receipts':receipts,'daily_scheduler_installed':False}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (output/'catalogs.json').write_text(json.dumps(discovery,ensure_ascii=False,indent=2)+'\n')
    return summary
