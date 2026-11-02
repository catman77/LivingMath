"""Unknown formal representations must not create a fictitious comparative win."""
import hashlib
import json

import joblib
from roblox_pred.classifier_benchmark import pipeline,features
from roblox_pred.formal_comparison import evaluate


def test_missing_formal_sources_fall_back_to_same_baseline(tmp_path):
    dataset=tmp_path/'dataset';dataset.mkdir();run=tmp_path/'unit-run';run.mkdir()
    protocol={'seed':1,'model':{'tfidf_max_features':100,'logistic_C':1}}
    rows=[]
    for i in range(6):
        rows.append({'case_id':str(i),'title':'Original unit fixture','model_description':'collect resources and build a home together',
            'age_days':100+i,'genre':'UNIT','label':i%2,'split':['train','train','validation','validation','test','test'][i],
            'split_group':'unit-'+str(i)})
    (dataset/'classifier_dataset.json').write_text(json.dumps(rows))
    (dataset/'dataset-frozen.json').write_text(json.dumps({'protocol':protocol}))
    base=pipeline(protocol,True).fit(features(rows[:2]),[0,1])
    joblib.dump({'M2_text_metadata':base},dataset/'baseline-models.joblib')
    frozen={'study_code_sha256':{},'classifier_dataset_sha256':hashlib.sha256((dataset/'classifier_dataset.json').read_bytes()).hexdigest(),
        'baseline_models_sha256':hashlib.sha256((dataset/'baseline-models.joblib').read_bytes()).hexdigest()}
    (run/'run-frozen.json').write_text(json.dumps(frozen))
    for row in rows:
        folder=run/'cases'/row['case_id'];folder.mkdir(parents=True)
        (folder/'result.json').write_text(json.dumps({'semantic_features':{'MISSING_SEMANTIC_GRAPH':1},
            'formal_features':{'MISSING_FORMAL_MODEL':1},'semantic_available':False,'formal_available':False,
            'engine_status':'UNIT_FIXTURE_UNAVAILABLE','model_calls':0,'usage':{}}))
    result=evaluate(dataset,run)
    assert result['status']=='COMPLETED_INCONCLUSIVE_LOW_FORMAL_COVERAGE'
    assert result['metrics']['test']['C_formal']==result['metrics']['test']['A_text']
    assert result['metrics']['test']['B_semantic']==result['metrics']['test']['A_text']
    assert result['model_calls']==0 and result['source_claim_verified'] is False
