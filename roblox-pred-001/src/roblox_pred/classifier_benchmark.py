"""A quick cross-sectional baseline plus a shared blind-prediction scorer."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer

from roblox_pred.classifier_pilot import write_csv
from roblox_pred.config import digest
from roblox_pred.evaluation import metrics
from roblox_pred.evaluation.runner import freeze


def features(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{'age_log':np.log1p(r['age_days']),
        'length_log':np.log1p(len(r['model_description'])),'genre':r.get('genre') or 'UNKNOWN',
        'text':(r.get('title') or '')+'\n'+r['model_description']} for r in rows])


def pipeline(protocol: dict, text: bool) -> Pipeline:
    transformers=[('numeric',Pipeline([('imputer',SimpleImputer()),('scale',StandardScaler())]),['age_log','length_log']),
        ('genre',OneHotEncoder(handle_unknown='ignore'),['genre'])]
    if text:transformers.append(('text',TfidfVectorizer(ngram_range=(1,2),min_df=2,
        max_features=protocol['model']['tfidf_max_features'],sublinear_tf=True),'text'))
    return Pipeline([('features',ColumnTransformer(transformers)),('classifier',LogisticRegression(
        C=protocol['model']['logistic_C'],class_weight='balanced',max_iter=1000,random_state=protocol['seed']))])


def score_rows(rows: list[dict], predictions: list[dict]) -> dict:
    expected={r['case_id']:r['label'] for r in rows}
    actual={r['case_id']:float(r['score']) for r in predictions}
    if len(actual)!=len(predictions) or set(actual)!=set(expected):
        raise ValueError('PREDICTION_COVERAGE_OR_DUPLICATE_ID')
    ids=sorted(expected);y=[expected[i] for i in ids];p=[actual[i] for i in ids]
    result=metrics(y,p,ids)
    from sklearn.metrics import balanced_accuracy_score, f1_score, confusion_matrix
    labels=np.array(p)>=.5
    result.update(balanced_accuracy=float(balanced_accuracy_score(y,labels)),
        f1=float(f1_score(y,labels,zero_division=0)),confusion_matrix=confusion_matrix(y,labels,labels=[0,1]).tolist())
    return result


def benchmark(prepared: Path) -> dict:
    rows=json.loads((prepared/'classifier_dataset.json').read_text())
    declaration=json.loads((prepared/'dataset-frozen.json').read_text());protocol=declaration['protocol']
    freeze(prepared/'baseline-frozen.json',{'dataset':declaration,'models':['M0_base_rate','M0_metadata','M2_text_metadata'],
        'policy':'FIT_TRAIN_ONLY_FIXED_PARAMETERS_NO_TEST_TUNING','code_sha256':digest(Path(__file__).read_text())})
    output=prepared/'baseline-result.json'
    if output.exists():return json.loads(output.read_text())
    train=[r for r in rows if r['split']=='train'];y=[r['label'] for r in train]
    trained={name:pipeline(protocol,text).fit(features(train),y) for name,text in [('M0_metadata',False),('M2_text_metadata',True)]}
    results={};predictions=[]
    for split in ['validation','test']:
        group=[r for r in rows if r['split']==split];x=features(group)
        scores={'M0_base_rate':np.full(len(group),np.mean(y)),
            **{name:model.predict_proba(x)[:,1] for name,model in trained.items()}}
        results[split]={}
        for model,values in scores.items():
            records=[{'case_id':r['case_id'],'score':float(p)} for r,p in zip(group,values)]
            results[split][model]=score_rows(group,records)
            predictions.extend({**p,'model':model,'split':split} for p in records)
    write_csv(prepared/'baseline-predictions.csv',predictions)
    import joblib
    joblib.dump(trained,prepared/'baseline-models.joblib')
    report={'status':'BASELINE_MEASURED_ON_ACTIVITY_PROXY_LABELS','metrics':results,
        'scope':'CREATOR_AND_NEAR_DUPLICATE_GROUP_DISJOINT_CROSS_SECTIONAL_WEAK_LABEL_TEST',
        'suti_livingmath_result':None,'suti_livingmath_status':'BLIND_EVALUATION_PACK_PREPARED_NOT_RUN',
        'not_a_future_or_financial_success_claim':True}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return report
