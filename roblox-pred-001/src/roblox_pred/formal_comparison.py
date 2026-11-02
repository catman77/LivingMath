"""Shared-encoder paired comparison; no test-dependent feature or parameter search."""
from collections import Counter
import json
from pathlib import Path

import joblib
import numpy as np
from scipy import sparse
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score

from roblox_pred.classifier_benchmark import features, score_rows
from roblox_pred.classifier_pilot import write_csv
from roblox_pred.formal_basis import fixed_projection


def evaluate(dataset: Path, run: Path) -> dict:
    import hashlib
    run_frozen=json.loads((run/'run-frozen.json').read_text())
    root=Path(__file__).resolve().parents[2]
    for name,sha in run_frozen['study_code_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('STUDY_CODE_DRIFT:'+name)
    for name,key in [('classifier_dataset.json','classifier_dataset_sha256'),('baseline-models.joblib','baseline_models_sha256')]:
        if hashlib.sha256((dataset/name).read_bytes()).hexdigest()!=run_frozen[key]:raise ValueError('FROZEN_DATA_OR_BASELINE_DRIFT')
    rows=json.loads((dataset/'classifier_dataset.json').read_text())
    frozen=json.loads((dataset/'dataset-frozen.json').read_text());protocol=frozen['protocol']
    source={r['case_id']:json.loads((run/'cases'/r['case_id']/'result.json').read_text()) for r in rows}
    base=joblib.load(dataset/'baseline-models.joblib')['M2_text_metadata']
    x=sparse.csr_matrix(base.named_steps['features'].transform(features(rows)))
    y=np.asarray([r['label'] for r in rows]);split=np.asarray([r['split'] for r in rows])
    train=np.flatnonzero(split=='train');test=np.flatnonzero(split=='test')
    semantic=sparse.csr_matrix(np.array([fixed_projection(source[r['case_id']]['semantic_features']) for r in rows]))
    formal=sparse.csr_matrix(np.array([fixed_projection(source[r['case_id']]['formal_features']) for r in rows]))
    availability={key:np.array([source[r['case_id']][key] for r in rows]) for key in ['semantic_available','formal_available']}
    shuffled_available=availability['formal_available'].copy()
    shuffled=formal.copy().tolil();rng=np.random.default_rng(protocol['seed'])
    for part in ['train','validation','test']:
        ids=np.flatnonzero(split==part);permutation=rng.permutation(ids)
        shuffled[ids]=formal[permutation];shuffled_available[ids]=availability['formal_available'][permutation]
    shuffled=shuffled.tocsr()
    matrices={'B_semantic':sparse.hstack([x,semantic],format='csr'),
        'C_formal':sparse.hstack([x,formal],format='csr'),
        'C_shuffled':sparse.hstack([x,shuffled],format='csr'),'formal_only':formal}
    models={name:LogisticRegression(C=1.,class_weight='balanced',max_iter=1000,random_state=protocol['seed']).fit(matrix[train],y[train])
        for name,matrix in matrices.items()}
    metrics={};predictions=[];test_scores={}
    for part in ['validation','test']:
        ids=np.flatnonzero(split==part);members=[rows[i] for i in ids]
        baseline=base.predict_proba(features(members))[:,1]
        scores={'A_text':baseline}
        for name,model in models.items():
            values=model.predict_proba(matrices[name][ids])[:,1]
            if name in ['B_semantic','C_formal','formal_only']:
                mask=availability['semantic_available' if name=='B_semantic' else 'formal_available'][ids]
                values=np.where(mask,values,baseline)
            if name=='C_shuffled':values=np.where(shuffled_available[ids],values,baseline)
            scores[name]=values
        metrics[part]={}
        for name,values in scores.items():
            records=[{'case_id':r['case_id'],'score':float(p)} for r,p in zip(members,values)]
            metrics[part][name]=score_rows(members,records)
            predictions.extend({**r,'model':name,'split':part} for r in records)
            if part=='test':test_scores[name]=values
    # Paired component bootstrap, never a second train/test split or model refit.
    groups=np.array([rows[i]['split_group'] for i in test]);unique=np.unique(groups);deltas=[]
    for _ in range(2000):
        sampled=rng.choice(unique,size=len(unique),replace=True)
        ids=np.concatenate([np.flatnonzero(groups==g) for g in sampled])
        truth=y[test][ids]
        if len(set(truth))<2:continue
        deltas.append(balanced_accuracy_score(truth,test_scores['C_formal'][ids]>=.5)-
            balanced_accuracy_score(truth,test_scores['A_text'][ids]>=.5))
    differences={name:metrics['test'][name]['balanced_accuracy']-metrics['test']['A_text']['balanced_accuracy'] for name in matrices}
    coverage={part:{kind:int(availability[kind][split==part].sum()) for kind in availability}
        for part in ['train','validation','test']}
    nformal=coverage['test']['formal_available'];ntest=len(test)
    report={'status':'COMPLETED_MEASURED_COMPARISON' if nformal>=.8*ntest else 'COMPLETED_INCONCLUSIVE_LOW_FORMAL_COVERAGE',
        'metrics':metrics,'test_balanced_accuracy_delta_vs_A':differences,
        'C_vs_A_paired_group_bootstrap_CI95':np.quantile(deltas,[.025,.975]).tolist() if deltas else None,
        'coverage':coverage,'case_count':len(rows),'model_calls':sum(r['model_calls'] for r in source.values()),
        'model_usage':{key:sum(r.get('usage',{}).get(key,0) for r in source.values()) for key in ['input_tokens','output_tokens','reasoning_output_tokens']},
        'source_status_counts':dict(Counter(r['engine_status'] for r in source.values())),
        'scope':'EXPLORATORY_CURRENT_AUDIENCE_PROXY; TEXT_ONLY; NOT FUTURE/FINANCIAL SUCCESS',
        'feature_encoder':'livingmath-source-graph-basis/1','unknown_policy':'A_TEXT_FALLBACK_NOT_ZERO_SEMANTICS',
        'native_SUTI_runtime_executed':False,'formal_LivingMath_pipeline_executed':True,
        'source_claim_verified':False,'model_parameters_tuned_on_test':False}
    write_csv(run/'predictions.csv',predictions);joblib.dump(models,run/'readout-models.joblib')
    (run/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    text='# Сравнение текстового и формального классификаторов\n\n'
    text+='Это реальное исполнение установленного source/formal pipeline LivingMath. Native SUTI runtime отдельно не заявлен.\n\n'
    text+='| Модель | Balanced accuracy test | ROC-AUC |\n|---|---:|---:|\n'
    for name,value in metrics['test'].items():text+=f"| {name} | {value['balanced_accuracy']:.4f} | {value['roc_auc']:.4f} |\n"
    text+=f"\nПолнота формальных признаков test: {nformal}/{ntest}.\n"
    text+=f"Разница C−A: {differences['C_formal']:.4f}; paired group bootstrap CI95: {report['C_vs_A_paired_group_bootstrap_CI95']}.\n"
    text+='\nМетки отражают текущую аудиторию; скриншоты, будущий успех и выручка не проверялись. '
    text+='B_semantic использует те же source proposer/critic; C_formal добавляет фактическую формальную компиляцию/проверку. '
    text+='META_ONLY не означает динамическое исполнение игры или доказательство смысла. '
    text+='Ни один результат не присваивает verified или execution grant.\n'
    (run/'report.md').write_text(text)
    return report
