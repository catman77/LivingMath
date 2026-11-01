"""Quick weak-label corpus: inactive is not automatically a failed launch."""
from collections import Counter
from datetime import datetime
import csv
import json
from pathlib import Path
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedGroupKFold

from roblox_pred.config import digest
from roblox_pred.evaluation.runner import freeze


def clean_description(text: str | None) -> str:
    lines=[]
    for line in (text or '').splitlines():
        line=re.sub(r'https?://\S+',' ',line)
        if (re.search(r'\b(visits|likes|favorites|favourites|followers)\b',line,re.I)
                and re.search(r'\d|million|billion',line,re.I)):
            continue
        lines.append(line)
    return re.sub(r'\s+',' ',' '.join(lines)).strip()


def classify(row: dict, settings: dict) -> dict:
    result=dict(row);text=clean_description(row.get('description'))
    result.update(model_description=text,label=None,activity_class='INSUFFICIENT_DATA',label_basis='')
    if not row.get('launch_date_proxy') or row.get('current_players') is None or row.get('visits_total') is None:
        return result
    age=(datetime.fromisoformat(row['observed_at'])-datetime.fromisoformat(row['launch_date_proxy'])).total_seconds()/86400
    result['age_days']=max(age,0);result['visits_per_day_since_creation_proxy']=row['visits_total']/max(age,1)
    result['launch_date_proxy']=row['launch_date_proxy'][:10]
    if age<settings['min_age_days']:
        result.update(activity_class='YOUNG_OR_UNKNOWN_RELEASE',label_basis='Creation-date age below registered cutoff')
    elif 'very first roblox creation' in text.lower() or text.lower().startswith('this is your very first roblox'):
        result.update(activity_class='DEFAULT_TEMPLATE',label_basis='Default Roblox template description')
    elif row['current_players']>=settings['high_activity_min_ccu']:
        result.update(activity_class='HIGH_ACTIVITY',label=1,label_basis='Mature universe; current CCU >= registered threshold')
    elif settings.get('target_mode')=='CURRENT_AUDIENCE' and row['current_players']<=settings['low_activity_max_ccu']:
        result.update(activity_class='LOW_ACTIVITY_PAST_REACH' if row['visits_total']>=settings['dormant_min_visits'] else 'LOW_ACTIVITY_LOW_REACH',
            label=0,label_basis='Mature universe; current audience <= registered cutoff; historical-reach subtype retained')
    elif (row['current_players']<=settings['low_traction_max_ccu'] and row['visits_total']<=settings['low_traction_max_visits']
          and result['visits_per_day_since_creation_proxy']<=settings['low_traction_max_visits_per_day_proxy']):
        result.update(activity_class='LOW_TRACTION_MATURE',label=0,
            label_basis='Mature universe; low current CCU AND low lifetime reach AND low age-normalized visits')
    elif row['current_players']<=settings['low_traction_max_ccu'] and row['visits_total']>=settings['dormant_min_visits']:
        result.update(activity_class='DORMANT_HIGH_REACH',label_basis='Low current CCU but substantial historical reach; not a failed launch label')
    else:
        result.update(activity_class='INTERMEDIATE',label_basis='Between registered extremes')
    result['eligible_for_classifier']=(result['label'] is not None and len(text)>=settings['min_description_chars']
        and bool(row.get('creator_key')))
    if not result['eligible_for_classifier']:result['label']=None
    return result


def assign_components(rows: list[dict], threshold: float) -> None:
    """Union creator + exact/near-duplicate description, then hold components apart."""
    parents=list(range(len(rows)))
    def find(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parents[max(a,b)]=min(a,b)
    creators={};texts={}
    normalized=[]
    for i,row in enumerate(rows):
        text=re.sub(r'\W+',' ',row['model_description'].lower()).strip();normalized.append(text)
        creator=row['creator_key']
        if creator in creators:union(i,creators[creator])
        creators[creator]=i
        if text in texts:union(i,texts[text])
        texts[text]=i
    if len(rows)>1 and any(len(s)>20 for s in normalized):
        x=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),max_features=30000).fit_transform(normalized)
        similarity=(x@x.T).tocoo()
        for a,b,value in zip(similarity.row,similarity.col,similarity.data):
            if a<b and value>=threshold:union(int(a),int(b))
    for i,row in enumerate(rows):row['split_group']='component-'+str(find(i))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:return
    keys=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def model_input(row: dict, *, training=False) -> dict:
    result={key:row.get(key) for key in ['case_id','title','model_description','genre','launch_date_proxy','launch_date_proxy_kind']}
    if training:result['label']=row['label']
    return result


def prepare(collection_dir: Path) -> dict:
    collection=json.loads((collection_dir/'collection.json').read_text())
    protocol=json.loads((collection_dir/'protocol.json').read_text())
    rows=[classify(r,protocol['labels']) for r in collection['rows']]
    # Opaque IDs/order avoid chart-position and universe-ID leakage into model input.
    rows.sort(key=lambda r:digest([protocol['seed'],r['universe_id']]))
    for i,row in enumerate(rows):row['case_id']=f'case-{i+1:05d}'
    eligible=[r for r in rows if r.get('eligible_for_classifier')]
    if len(set(r['label'] for r in eligible))<2:raise ValueError('Both proxy classes are required; collection retained')
    assign_components(eligible,protocol['split']['near_duplicate_cosine'])
    y=np.array([r['label'] for r in eligible]);groups=np.array([r['split_group'] for r in eligible])
    splitter=StratifiedGroupKFold(n_splits=protocol['split']['folds'],shuffle=True,random_state=protocol['seed'])
    for fold,(_,indices) in enumerate(splitter.split(np.zeros(len(y)),y,groups)):
        split='test' if fold==protocol['split']['test_fold'] else 'validation' if fold==protocol['split']['validation_fold'] else 'train'
        for i in indices:eligible[int(i)]['split']=split
    for a,b in [('train','test'),('train','validation'),('validation','test')]:
        left={r['split_group'] for r in eligible if r['split']==a};right={r['split_group'] for r in eligible if r['split']==b}
        if left & right:raise ValueError('SPLIT_COMPONENT_LEAKAGE')
    for name in ['train','validation','test']:
        if len({r['label'] for r in eligible if r['split']==name})!=2:
            raise ValueError('FROZEN_SPLIT_HAS_SINGLE_CLASS:'+name)
    output=collection_dir/'prepared'
    declaration={'protocol':protocol,'rows_sha256':digest(rows),'split_sha256':digest([(r['case_id'],r['split']) for r in eligible])}
    freeze(output/'dataset-frozen.json',declaration)
    write_csv(output/'all_games.csv',rows);write_csv(output/'classifier_dataset.csv',eligible)
    (output/'classifier_dataset.json').write_text(json.dumps(eligible,ensure_ascii=False,indent=2)+'\n')
    for split in ['train','validation','test']:
        members=[r for r in eligible if r['split']==split]
        (output/f'{split}_input.jsonl').write_text(''.join(json.dumps(model_input(r,training=split=='train'),ensure_ascii=False)+'\n' for r in members))
        write_csv(output/f'{split}_labels.csv',[{k:r[k] for k in ['case_id','label','activity_class','current_players',
            'visits_total','split_group','creator_key']} for r in members])
    write_csv(output/'dormant_examples.csv',[r for r in rows if r['activity_class'] in {'DORMANT_HIGH_REACH','LOW_ACTIVITY_PAST_REACH'}])
    write_csv(output/'low_reach_examples.csv',[r for r in eligible if r['label']==0 and r['visits_total']<protocol['labels']['dormant_min_visits']])
    write_csv(output/'strict_low_traction_examples.csv',[r for r in eligible if r['label']==0
        and r['current_players']<=protocol['labels']['low_traction_max_ccu']
        and r['visits_total']<=protocol['labels']['low_traction_max_visits']
        and r['visits_per_day_since_creation_proxy']<=protocol['labels']['low_traction_max_visits_per_day_proxy']])
    summary={'status':'CLASSIFIER_DATASET_PREPARED','all_games':len(rows),'classifier_games':len(eligible),
        'activity_classes':dict(Counter(r['activity_class'] for r in rows)),
        'labels':dict(Counter(str(r['label']) for r in eligible)),
        'splits':{s:dict(Counter(str(r['label']) for r in eligible if r['split']==s)) for s in ['train','validation','test']},
        'creators':len({r['creator_key'] for r in eligible}),'split_components':len(set(groups)),
        'missing_or_short_description':sum(len(r['model_description'])<protocol['labels']['min_description_chars'] for r in rows),
        'unavailable_games':len(collection['unavailable_universe_ids']),
        'requests':collection['requests'],'source_errors':collection['errors'],
        'truncated_portfolios':sum(c['truncated'] for c in collection['catalogs']),
        'directory':str(output),'model_inputs_exclude_targets':True,
        'target':('HIGH_ACTIVITY vs LOW_CURRENT_AUDIENCE; historical-reach subtypes retained'
            if protocol['labels'].get('target_mode')=='CURRENT_AUDIENCE' else 'HIGH_ACTIVITY vs LOW_TRACTION_MATURE; weak activity proxies'),
        'generalization_scope':'Charts, public creator portfolios and genre-search background; cross-sectional, not marketwide launch prediction',
        'suti_livingmath_comparison':'READY_FOR_BLIND_PREDICTIONS_NOT_EXECUTED'}
    (output/'dataset-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def filter_zero_placeholders(payload: dict, requested: list[int]) -> tuple[dict,int]:
    """Observed API id=0 sentinel is unavailable, never a zero-audience example."""
    rows=payload['data'];valid=[r for r in rows if r.get('id')!=0]
    if any(r.get('id') not in requested for r in valid) or len({r['id'] for r in valid})!=len(valid):
        raise ValueError('SOURCE_UNIVERSE_RESPONSE_BINDING')
    return {**payload,'data':valid},len(rows)-len(valid)
