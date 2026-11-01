"""One genuine Xi source experiment. No native test-h values exist before sealing."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
from normalizer import canonical,digest,read_history,normalize_context,reconstruct_context
from qa_positive_acceptance import write_json
from research_store import ResearchStore
from native_preview008_server import MeasuredProcess
from real_xi015_math import assess,binding_fingerprint,require_binding

SOURCE=Path(__file__).resolve().parent


def append(path,value):
    with path.open('a') as stream:stream.write(canonical(value)+'\n');stream.flush();os.fsync(stream.fileno())


def measured(command,log,timeout=90):
    start=time.perf_counter_ns()
    with log.open('w') as stream:
        process=MeasuredProcess(command,stdout=stream,stderr=stream,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        try:process.wait(timeout=timeout)
        except __import__('subprocess').TimeoutExpired:process.kill();process.wait();raise ValueError('PROCESS_WALL_BUDGET')
    usage=process.child_usage
    result={'wall_ns':time.perf_counter_ns()-start,'CPU_ns':round((usage.ru_utime+usage.ru_stime)*1e9),'peak_RSS_KiB':usage.ru_maxrss,'exit_code':process.returncode}
    if process.returncode:raise ValueError('WORKER_FAILED:'+str(log)+':'+log.read_text()[-1800:])
    return result


def legacy_source(db,source_sha,A,B):
    project='LM_QA_XI015_TRAIN';scope='XI015/source-training';store=ResearchStore(db)
    def event(name,content):
        e=store.record(project,'qa_source',name,canonical(content),'hypothesis',request_key='015:'+name)
        with store._connect() as c:return dict(c.execute('SELECT * FROM events WHERE id=?',(e['id'],)).fetchone())
    source=event('source',{'claim_type':'SOURCE_CLAIM','archive_sha256':source_sha,'scope':scope,'version':1})
    a=event('CASE-A-anchor',{'claim_type':'SOURCE_CLAIM','h':'0','edge':A[0]});b=event('CASE-B-anchor',{'claim_type':'SOURCE_CLAIM','h':'0.001','edge':B[0]})
    ind=event('independent',{'claim_type':'HYPOTHESIS','scope':'independent','statement':'Address/provenance investigation, independent of a parameter-transfer hypothesis.'})
    refs=['event:'+str(a['id']),'event:'+str(b['id'])];iref='event:'+str(ind['id']);root='event:'+str(source['id'])
    obligation=store.frontier.create(project,'Read actual source values without generating unsealed h.',scope,[source['id'],a['id'],b['id']])
    spec={'parameters':{'actions':['heldout-h-forbidden']},'histories':refs,'independent_ref':iref,
        'hypotheses':[{'id':r,'ref':r,'weight':1,'predictive':True,'question':'current','depends_on':[]} for r in refs]+
            [{'id':'IND','ref':iref,'weight':1,'predictive':False,'question':'independent','depends_on':[]}],
        'tests':[],'observer':{'projection':'primary','mod':None},'current_observation':json.dumps(A[0]['value'],sort_keys=True,separators=(',',':')),
        'known_failures':[],'unknowns':['No existing Xi proof-schema is registered in007.'],'primitive_sha256':source_sha}
    query={'id':'xi015-actual-training','project':project,'scope':scope,'version':1,'root_ref':root,
           'move':{'active_frontier_id':obligation['id'],'parent_event_ids':[source['id'],a['id'],b['id']]}}
    history=read_history(db,project);view=normalize_context(history,'actual theta source anchors',[query],'C2')
    recovered=reconstruct_context(view,history)
    if view['status']!='COMPLETE' or {r['id']:r for r in recovered['tables']['events']}!={r['id']:r for r in history['tables']['events']}:raise ValueError('NORMALIZATION_SOURCE_RECOVERY')
    return {'spec':spec,'query':query,'events':{r['id']:r for r in (source,a,b,ind)},
            'words':{refs[0]:['A'],refs[1]:['B'],iref:['A']},'data':{'A':A[0],'B':B[0]}}, {'normalizer':'004.1','status':view['status'],'exact_source_recovery':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    base=args.baseline or Path(Path('/tmp/lm015_path').read_text().strip());meta=json.loads((base/'metadata.json').read_text());raw=Path(meta['raw'])
    cohort=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out=args.output or SOURCE.parent/'docs/qa/LM-REAL-XI-015'/cohort;out.mkdir(parents=True,exist_ok=False)
    public=base/cohort/'public';public.mkdir(parents=True,mode=0o700);evaluation=base/cohort/'evaluation';evaluation.mkdir(mode=0o700)
    policy=json.loads((base/'frozen-split.json').read_text());audit=json.loads((base/'audited-input.json').read_text());costs={};checks=[]
    def check(name,ok,evidence=None):
        checks.append({'invariant':name,'result':'PASS' if ok else 'FAIL','evidence':evidence});write_json(out/'checks.json',checks)
        if not ok:
            write_json(out/'first-failure.json',checks[-1]);raise ValueError(name)
    source=out/'sources';source.mkdir()
    for p in SOURCE.glob('real_xi015*.py'):shutil.copy2(p,source/p.name)
    for name in ('source-manifest.json','frozen-split.json','source-validation.json','native-reproduction-costs.json'):shutil.copy2(base/name,out/name)
    write_json(out/'source-address-join.json',audit['join'])
    db=base/cohort/'private-source.sqlite3'
    import sqlite3
    with sqlite3.connect((base/'canonical.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(db) as dst:src.backup(dst)
    write_json(base/'current.json',{'output':str(out),'public':str(public),'evaluation':str(evaluation),'database':str(db)})
    try:
        A=[audit['selected']['0'][str(i)] for i in range(32)];B=[audit['selected']['1'][str(i)] for i in range(32)]
        frame,normalization=legacy_source(db,policy['archive_sha256'],A[:16],B[:16]);write_json(out/'normalization.json',normalization)
        train={'A':A[:16],'B':B[:16],'nodes':{k:v for k,v in audit['nodes'].items() if int(k)<2},'legacy_frame':frame}
        train['sha256']=digest(train);write_json(public/'train.json',train)
        costs['learn']=measured([sys.executable,str(SOURCE/'real_xi015_worker.py'),'learn','--native',str(raw),'--input',str(public/'train.json'),
            '--output',str(public/'model.json'),'--forbidden',str(raw/'cases.json')],evaluation/'learn.log')
        model=json.loads((public/'model.json').read_text());write_json(out/'law-candidate.json',model)
        check('old013_declines_complex_intervals',model['unchanged013_value_attempt']['status']=='NO_GO_INTEGER_REPRESENTATION')
        query={'model':model['model'],'A':A,'B':B,'nodes':audit['nodes'],'test_h':policy['test_h'],'t':policy['t'],'definition_sha256':policy['archive_sha256']}
        write_json(public/'query.json',query)
        costs['predict']=measured([sys.executable,str(SOURCE/'real_xi015_worker.py'),'predict','--native',str(raw),'--input',str(public/'query.json'),
            '--output',str(public/'predictions.json'),'--forbidden',str(raw/'cases.json')],evaluation/'predict.log')
        predicted=json.loads((public/'predictions.json').read_text());predicted_hash=digest(predicted)
        for row in predicted['predictions']:append(out/'sealed-predictions.jsonl',{**row,'sealed_at':datetime.now(timezone.utc).isoformat(),'prediction_artifact_sha256':predicted_hash})
        write_json(out/'prediction-seal.json',{'sha256':hashlib.sha256((out/'sealed-predictions.jsonl').read_bytes()).hexdigest(),'model_sha256':digest(model),
            'prediction_process':predicted['costs'],'native_theta_evaluate_calls':predicted['native_theta_evaluate_calls']})
        comparisons=[];measurements=[]
        for h in policy['test_h']:
            # First actual new-h call occurs only after every prediction has been sealed.
            inp=evaluation/('request-'+h+'.json');answer=evaluation/('answer-'+h+'.json')
            write_json(inp,{'nodes':audit['nodes'],'origins':audit['origins'],'h':h,'t':policy['t']})
            costs['B1-native-'+h]=measured([sys.executable,str(SOURCE/'real_xi015_worker.py'),'measure','--native',str(raw),'--input',str(inp),'--output',str(answer)],evaluation/('oracle-'+h+'.log'))
            actual=json.loads(answer.read_text());measurements.append(actual)
            for row in actual['rows']:
                append(out/'heldout-measurements.jsonl',{'h':h,'t':policy['t'],'native':row,'after_prediction_seal':True})
                prediction=next(p for p in predicted['predictions'] if p['index']==row['index'] and p['binding']['h']==h)
                check('address_origin_match:'+h+':'+str(row['index']),prediction['binding']['source_address']==row['source_address'] and prediction['binding']['origin_id']==row['origin_id'])
                scores={method:assess(prediction[method],row,(A[row['index']],B[row['index']])) for method in ('C_source_candidate','B2_linear','B2_Hermite')}
                comparisons.append({'h':h,'index':row['index'],'source_address':row['source_address'],'origin_id':row['origin_id'],'scores':scores})
                check('C_blind:'+h+':'+str(row['index']),scores['C_source_candidate']['PASS'],comparisons[-1])
        check('two_new_h_only',len(measurements)==2 and all(len(m['rows'])==32 for m in measurements))
        identity=predicted['predictions'][0]['binding'];renamed={**identity,'display_label':'renamed'}
        check('source_neutral_rename',binding_fingerprint(identity)==binding_fingerprint(renamed))
        for field,value in [('origin_id',99),('h','0.0006'),('t','14'),('observer','different'),('version',2),('definition_sha256','0'*64),('source_address',{**identity['source_address'],'n':99})]:
            try:require_binding({**identity,field:value},identity);refused=False
            except ValueError:refused=True
            check('rebind:'+field,refused)
        controls=json.loads((base/'reproduced/loops.json').read_text())['cases'][2]['loops']
        check('CASE_C_point_not_germ',len(controls)==4 and all(r['zero_statuses']['C']['status']=='REFUTED' and not r['native_erase_allowed'] and Decimal(r['strict_derivative_change_lower_bound'])>0 for r in controls))
        write_json(out/'CASE-C-control.json',controls)
        summary={method:{'PASS':sum(c['scores'][method]['PASS'] for c in comparisons),'FAIL':sum(not c['scores'][method]['PASS'] for c in comparisons)} for method in ('C_source_candidate','B2_linear','B2_Hermite')}
        write_json(out/'comparison.json',{'summary':summary,'per_address':comparisons,'public_anchor_policy':policy['public_anchor_policy'],
            'structural_advantage':'Explicit source-schema prediction versus interpolation only; no autonomous discovery or total source-cost superiority established.'})
        status='BLIND_PREDICTION_PASS_TYPED_PENDING'
    except Exception as error:
        status='STOP_WITH_RCA';write_json(out/'exception.json',{'error':str(error),'traceback':__import__('traceback').format_exc()})
    write_json(out/'costs.json',costs);write_json(out/'result.json',{'status':status,'checks':checks,'proof_status':'unverified','production_writes':False})
    print(canonical({'status':status,'output':str(out)}))


if __name__=='__main__':main()
