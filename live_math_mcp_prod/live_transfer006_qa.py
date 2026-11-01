"""Registered006 acceptance, isolated source DBs and unchanged historical regression."""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
import tracemalloc

from normalizer import Budget,digest,normalize_context,read_history
from qa_positive_acceptance import snapshot,write_json
from live_transfer006 import interpret,attend
from live_transfer006_source import load_frame,BindingError
from live_transfer006_worlds import create_world,frame,view
from live_transfer006_baselines import flat_pair,flat_attention,old_pair,old_attention,raw_endpoint
from live_transfer006_oracle import attention
from research_store import ResearchStore

SOURCE=Path(__file__).parent


def measured(function, allocations=True):
    start=time.perf_counter();rss_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if allocations:tracemalloc.start()
    try:
        out=function();peak=tracemalloc.get_traced_memory()[1] if allocations else None
    finally:
        if allocations:tracemalloc.stop()
    return out,{'wall_seconds':time.perf_counter()-start,'python_peak_bytes':peak,
                'process_max_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'rss_before_KiB':rss_before,'memory_scope':'per-case Python allocations' if allocations else 'process high-water RSS; no per-case peak attribution'}


def emit(base,name,row):
    with (base/(name+'.jsonl')).open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def require(base,condition,kind,case,expected,actual):
    if condition:return
    record={'classification':kind,'case':case,'expected':expected,'actual':actual}
    write_json(base/'first-failure.json',record)
    raise RuntimeError(kind+': '+case)


def reframe(w,h=None,q=None):
    h=h if h is not None else w['history'];q=q if q is not None else w['query']
    return load_frame(normalize_context(h,'finite primary',[q],'C2'),h,q)


def controls(base,w,f,expected_pairs):
    out=[]
    for case in ('C4','budget','missing','hash','project','scope','version','oracle_answer','omitted_guard'):
        h=copy.deepcopy(w['history']);q=copy.deepcopy(w['query']);v=view(w)
        if case=='C4':v=view(w,'C4')
        if case=='budget':v=view(w,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
        if case=='missing':
            v['audit_context']['tables']['events']=v['audit_context']['tables']['events'][1:];v['certificate']['context_digest']=digest(v['audit_context'])
        if case=='hash':v['source_catalog'][w['refs']['h0']]='0'*64
        if case in {'project','scope','version'}:
            if case=='project':q['project']='FOREIGN'
            elif case=='scope':q['scope']='FOREIGN_SCOPE'
            else:q['version']=999
            v=normalize_context(h,'finite primary',[q],'C2')
        if case in {'oracle_answer','omitted_guard'}:
            for e in h['tables']['events']:
                if 'event:'+str(e['id'])==q['root_ref']:
                    p=json.loads(e['content']);p['source_spec'][case]='seeded forbidden answer';e['content']=json.dumps(p)
            v=normalize_context(h,'finite primary',[q],'C2')
        try:load_frame(v,h,q);ok=False;actual='ACCEPTED_INVALID_SOURCE'
        except BindingError as error:ok=True;actual=str(error)
        row={'world':w['id'],'case':case,'result':'PASS' if ok else 'FAIL','response':actual,'input_digest':digest(h),'view_digest':digest(v),'query':q}
        emit(base,'adversarial-controls',row);out.append(row)
        require(base,ok,'SOURCE_BINDING_BUG',w['id']+case,'FAIL_CLOSED',row)
    positive=next((p for p in expected_pairs if p['hidden']),None)
    if positive:
        l,r=positive['left'],positive['right'];a=interpret(f,l,r)
        cases={'rename':interpret(f,r,l,known=(a['fingerprint'],),title='Impressive new name'),
               'short_bound':interpret(f,l,r,max_length=0),'primitive_quota':interpret(f,l,r,max_calls=1),
               'observer':interpret(f,l,r,observer={'projection':'primary','mod':29}),
               'false_alias':interpret(f,f.spec['independent_ref'],r)}
        for case,value in cases.items():
            wanted='NO_NEW_DISTINCTION' if case=='rename' else 'UNKNOWN_BOUNDED' if case in {'short_bound','primitive_quota'} else 'FAIL_CLOSED'
            ok=value['status']==wanted and not value['execution_allowed']
            row={'world':w['id'],'case':case,'result':'PASS' if ok else 'FAIL','response':value}
            emit(base,'adversarial-controls',row);out.append(row);require(base,ok,'INTERPRETATION_BUG',w['id']+case,wanted,value)
    # IDs are display/provenance labels, not operation meaning or tie breakers.
    h=copy.deepcopy(w['history'])
    for e in h['tables']['events']:
        if 'event:'+str(e['id'])==w['query']['root_ref']:
            p=json.loads(e['content']);spec=p['source_spec'];mapping={x['id']:'renamed_'+x['id'] for x in spec['hypotheses']}
            for x in spec['hypotheses']:x['id']=mapping[x['id']];x['depends_on']=[mapping[i] for i in x['depends_on']]
            for t in spec['tests']:t['id']='display_'+t['id']
            e['content']=json.dumps(p)
    before=attend(f);after=attend(reframe(w,h));ok=before['status']==after['status'] and before.get('suffix')==after.get('suffix')
    row={'world':w['id'],'case':'irrelevant_ID_permutation','result':'PASS' if ok else 'FAIL','before':before,'after':after}
    emit(base,'adversarial-controls',row);out.append(row);require(base,ok,'ATTENTION_BUG',w['id']+'IDs','Same actual suffix',row)
    if positive:
        h=copy.deepcopy(w['history']);rename={a:'display_'+a for a in f.spec['parameters']['actions']}
        for e in h['tables']['events']:
            p=json.loads(e['content'])
            if 'word' in p:p['word']=[rename[a] for a in p['word']]
            if 'source_spec' in p:
                spec=p['source_spec'];spec['parameters']['actions']=[rename[a] for a in spec['parameters']['actions']]
                for t in spec['tests']:t['suffix']=[rename[a] for a in t['suffix']]
            e['content']=json.dumps(p)
        original=interpret(f,positive['left'],positive['right'])
        renamed=interpret(reframe(w,h),positive['left'],positive['right'],known=(original['fingerprint'],))
        ok=renamed['status']=='NO_NEW_DISTINCTION'
        row={'world':w['id'],'case':'bijective_primitive_label_rename','result':'PASS' if ok else 'FAIL','before':original,'after':renamed}
        emit(base,'adversarial-controls',row);require(base,ok,'INTERPRETATION_BUG',w['id']+'primitive labels','NO_NEW_DISTINCTION',row)
    # Real closed-version setup on a separate private fixture copy.
    path=base/'closed-controls'/f'{w["id"]}.sqlite3';path.parent.mkdir(exist_ok=True)
    with sqlite3.connect(Path(w['database']).as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(path) as dst:src.backup(dst)
    q=copy.deepcopy(w['query']);store=ResearchStore(path)
    store.frontier.update(q['move']['active_frontier_id'],1,{'status':'REFUTED','closure_reason':'Finite QA closure',
        'evidence_refs':[w['refs']['root']],'reopen_conditions':['New version and source evidence.']})
    q['version']=2;h=read_history(path,q['project'])
    try:reframe(w,h,q);ok=False;answer='ACCEPTED_CLOSED'
    except BindingError as e:ok=True;answer=str(e)
    row={'world':w['id'],'case':'closed_obligation','result':'PASS' if ok else 'FAIL','response':answer}
    emit(base,'adversarial-controls',row);require(base,ok,'SOURCE_BINDING_BUG',w['id']+'closed','FAIL_CLOSED',row)


def feedback_cycle(base,w,f,chosen):
    if chosen['status']!='ATTENTION_PROPOSED':
        emit(base,'feedback',{'world':w['id'],'status':'PAUSED_NO_SAFE_INFORMATIVE_TEST','independent_retained':True});return
    # Registered environment policy: last consistent current history, chosen before its readout.
    candidates=[h for h in chosen['hypotheses'] if h['predictive'] and h['question']=='current' and h['status']=='ACTIVE']
    environment_ref=candidates[-1]['ref'];port=f.port()
    measured_readout=raw_endpoint(port,f,environment_ref,chosen['suffix'])
    receipt={'scope':w['query']['scope'],'version':1,'observer':f.spec['observer'],'test_id':chosen['test_id'],
             'readout':measured_readout,'origin':'precommitted last-consistent source environment; not LLM/oracle-selected'}
    event=ResearchStore(Path(w['database'])).record(w['query']['project'],'counterexample','Finite environmental feedback',json.dumps({'observation':receipt}),'experiment')
    q=copy.deepcopy(w['query']);q['move']['parent_event_ids'].append(event['id']);h=read_history(Path(w['database']),q['project'])
    out=attend(reframe(w,h,q),'event:'+str(event['id']));expected=attention(w['history'],w['query'],receipt)
    statuses={x['id']:x['status'] for x in out.get('hypotheses',[])}
    preserved=all(next(e for e in h['tables']['events'] if e['id']==old['id'])==old for old in w['history']['tables']['events'])
    ok=(out['status']==expected['status'] and out.get('test_id')==expected['selected_test_id']
        and statuses==expected['statuses'] and statuses.get('I')=='ACTIVE' and preserved
        and event['id'] in out['source_event_ids'])
    emit(base,'feedback',{'world':w['id'],'environment_ref':environment_ref,'receipt':receipt,'event_id':event['id'],
        'T_after':out,'oracle':expected,'source_preserved':preserved,'independent_retained':statuses.get('I')=='ACTIVE','result':'PASS' if ok else 'FAIL'})
    require(base,ok,'INTERPRETATION_BUG',w['id']+'feedback',expected,out)


def run_p0(base: Path):
    worlds=json.loads((base/'worlds.json').read_text());expected=json.loads((base/'oracle.json').read_text())['worlds']
    start=time.perf_counter();rows=[];attentions=[]
    for w,oracle in zip(worlds,expected):
        f=frame(w)
        for pair in oracle['pairs']:
            a,am=measured(lambda:interpret(f,pair['left'],pair['right']))
            baseline,bm=measured(lambda:flat_pair(f,pair['left'],pair['right']))
            legacy,lm=measured(lambda:old_pair(w,f,pair['left'],pair['right']),allocations=False)
            valid=(a['status']=='NEW_DISTINCTION')==pair['hidden']
            if a['status']=='NEW_DISTINCTION':
                tid=a['witness']['test_id'];valid=valid and a['predictions']==[pair['Sig_left'][tid],pair['Sig_right'][tid]]
            valid=valid and not a['execution_allowed'] and a['proof_status']=='unverified' and bool(a['source_hashes'])
            valid=valid and all(ref['sha256']==digest(f.events[int(ref['ref'].split(':')[1])]) for ref in a['source_hashes'])
            valid=valid and baseline['hidden']==pair['hidden'] and baseline['signatures']==[pair['Sig_left'],pair['Sig_right']]
            if legacy['output']['status']=='NEW_DISTINCTION':
                old_w=legacy['output']['witness'];tid=old_w['test_id']
                valid=valid and old_w['left']==[pair['Sig_left'][tid]['observation'],True] and old_w['right']==[pair['Sig_right'][tid]['observation'],True]
            if legacy['input_reencoded_mod5_only']:
                valid=valid and (legacy['output']['status']=='NEW_DISTINCTION')==pair['hidden']
            row={'world':w['id'],'family':w['family'],'held_out':w['held_out'],'pair':pair,'I':a,'flat':baseline,'baseline005':legacy,
                 'measurements':{'portable':am,'flat':bm,'baseline005':lm},'independent_verification':'PASS' if valid else 'FAIL'}
            emit(base,'witnesses',row);rows.append(row)
            require(base,valid,'INTERPRETATION_BUG',w['id']+pair['left']+pair['right'],pair,row)
        t,tm=measured(lambda:attend(f));flat=flat_attention(f);old=old_attention(w,f);reference=oracle['attention']
        equal=t['status']==reference['status'] and t.get('test_id')==reference['selected_test_id'] and flat['test_id']==reference['selected_test_id']
        table={}
        for p in oracle['pairs']:table[p['left']]=p['Sig_left'];table[p['right']]=p['Sig_right']
        equal=equal and {h['id']:h['status'] for h in t.get('hypotheses',[])}==reference['statuses']
        equal=equal and all(c['readout']==table[c['source_ref']][r['test_id']] for r in t.get('ranking',[]) for c in r['counterfactuals'])
        if reference['ranking']:equal=equal and [{k:r[k] for k in reference['ranking'][0]} for r in t['ranking']]==reference['ranking']
        if old['input_reencoded_mod5_only']:equal=equal and old['output'].get('test_id')==reference['selected_test_id']
        record={'world':w['id'],'T':t,'oracle':reference,'flat':flat,'baseline005':old,'measurements':tm,'result':'PASS' if equal else 'FAIL'}
        emit(base,'attention-decisions',record);attentions.append(record)
        require(base,equal,'ATTENTION_BUG',w['id'],reference,record)
        controls(base,w,f,oracle['pairs']);feedback_cycle(base,w,f,t)
        print(json.dumps({'P0_world':w['id'],'pairs_done':len(rows),'status':'PASS'}),flush=True)
    for name in ('witnesses','attention-decisions','adversarial-controls','feedback'):
        write_json(base/(name+'.json'),[json.loads(s) for s in (base/(name+'.jsonl')).read_text().splitlines()])
    result={'result':'PASS','pairs':len(rows),'new_distinctions':sum(r['I']['status']=='NEW_DISTINCTION' for r in rows),
        'false_witnesses':0,'false_novelty':0,'missed_within_registered_bound':0,'incorrect_admissibility':0,'false_grants':0,
        'missing_source_provenance':0,'negative_controls':len(json.loads((base/'adversarial-controls.json').read_text())),
        'attention_cases':len(attentions),'seconds':time.perf_counter()-start,'worker_max_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'mathematical_mechanism':'PASS_BOUNDED_OPERATIONAL_TRANSFER','algebraic_shortcut_transfer':'MISSING_CAPABILITY',
        'P1_calls':0,'P1_decision':'SKIP_OPTIONAL: native transfer question is deterministic; no LLM re-ranking or repeat005 witness-preview pilot.'}
    write_json(base/'P0-result.json',result)
    return result


def initialize():
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    cfg=configure();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');root=SOURCE.parent
    b=Path.home()/'.local/state/livingmath/transfer006'/stamp;b.mkdir(parents=True,mode=0o700)
    db=(Path(cfg['LIVE_MATH_DATA_DIR'])/'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(b/'research-before.sqlite3') as dest:src.backup(dest)
    (b/'research-before.sqlite3').chmod(0o600);write_json(b/'before.json',snapshot(db))
    paths=[root/'AGENTS.md',*SOURCE.glob('*.py'),*SOURCE.glob('*.json'),*[p for p in (root/'docs/qa').rglob('*') if p.is_file()]]
    write_json(b/'metadata.json',{'private':str(b),'report':str(root/'docs/qa/LM-LIVE-MATH-TRANSFER-006'/stamp),'db':str(db),
        'backup_sha256':hashlib.sha256((b/'research-before.sqlite3').read_bytes()).hexdigest(),
        'protected_files':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
    folder=b/'live-readonly';folder.mkdir();client=Session(folder,db,cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):write_json(b/'preflight.json',{'health':await c.call('service_health',{}),'tools':(await c.session.list_tools()).model_dump(mode='json'),'contract':await c.call('research_contract',{'project':'RH'})})
    client.work=read;oauth(cfg,client)
    return b


def freeze(b):
    if (b/'worlds.json').exists():return
    from live_transfer006_oracle import pairs
    (b/'databases').mkdir();worlds=[create_world(b/'databases'/f'world{i}.sqlite3',i) for i in range(8)]
    write_json(b/'worlds.json',worlds);shutil.copyfile(SOURCE/'live_transfer006-contract.json',b/'frozen-contract.json')
    files=[*SOURCE.glob('live_transfer006*.py'),*SOURCE.glob('test_live_transfer006*.py'),SOURCE/'live_transfer006-contract.json']
    (b/'frozen-sources').mkdir()
    for p in files:shutil.copyfile(p,b/'frozen-sources'/p.name)
    manifest={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    write_json(b/'pre-oracle-source-manifest.json',manifest)
    write_json(b/'oracle.json',{'worlds':[{'world':w['id'],'pairs':pairs(w['history'],w['query']),'attention':attention(w['history'],w['query'])} for w in worlds]})
    manifest.update({str(b/n):hashlib.sha256((b/n).read_bytes()).hexdigest() for n in ('worlds.json','oracle.json','frozen-contract.json')})
    write_json(b/'source-manifest.json',manifest)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--private-dir',type=Path);parser.add_argument('--p0-worker',type=Path)
    args=parser.parse_args()
    if args.p0_worker:
        resource.setrlimit(resource.RLIMIT_CPU,(90,95));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
        run_p0(args.p0_worker);return
    b=args.private_dir.resolve(strict=True) if args.private_dir else initialize()
    if (b/'P0-result.json').exists() or (b/'witnesses.jsonl').exists():raise SystemExit('Existing results preserved; fresh run required')
    freeze(b);failures=[]
    try:
        with (b/'pytest.txt').open('w') as out:subprocess.run([sys.executable,'-m','pytest','-q',str(SOURCE)],stdout=out,stderr=subprocess.STDOUT,check=True)
        from normalization_regression import run_regression
        reg=run_regression(b/'local86',b/'research-before.sqlite3')
        if reg['result']!='PASS':raise RuntimeError('86 MCP invariants failed')
        with (b/'p0-worker.txt').open('w') as out:subprocess.run([sys.executable,__file__,'--p0-worker',str(b)],stdout=out,stderr=subprocess.STDOUT,timeout=120,check=True)
    except BaseException as e:
        import traceback
        (b/'exception.txt').write_text(traceback.format_exc());failures.append({'classification':'MISSING_CAPABILITY_OR_PIPELINE_FAILURE','reason':str(e)})
    finally:
        write_json(b/'run-failures.json',failures)
        from live_transfer006_report import export
        print(json.dumps(export(b)),flush=True)


if __name__=='__main__':main()
