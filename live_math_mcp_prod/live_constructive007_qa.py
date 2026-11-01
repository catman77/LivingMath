"""007 cold paired acceptance; no model calls or production research writes."""
import argparse,copy,json,resource,subprocess,sys,time,tracemalloc,hashlib,shutil,sqlite3
from pathlib import Path

from normalizer import digest,normalize_context,read_history,Budget
from qa_positive_acceptance import write_json,snapshot
from live_transfer006 import interpret as B1,attend
from live_transfer006_baselines import flat_pair,raw_endpoint
from live_constructive007 import interpret_constructive
from live_constructive007_source import load_frame,BindingError
from live_constructive007_native import Ledger,Port
from live_constructive007_worlds import create_world,frame,view
from live_constructive007_oracle import attention
from research_store import ResearchStore

SOURCE=Path(__file__).parent


def append(base,name,row):
    with (base/(name+'.jsonl')).open('a') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')


def require(base,ok,case,expected,actual):
    if ok:return
    write_json(base/'first-failure.json',{'case':case,'expected':expected,'actual':actual})
    raise RuntimeError('007 acceptance failure: '+case)


def measure(f,method,l,r,cert=None,known=()):
    ledger=Ledger();ledger.stage=method;bound=f.fork(ledger)
    tracemalloc.start();start=time.perf_counter()
    try:
        if method=='B0':out=flat_pair(bound,l,r)
        elif method=='B1':out=B1(bound,l,r,known=known)
        else:out=interpret_constructive(bound,l,r,cert,known=known)
        memory=tracemalloc.get_traced_memory()[1]
    finally:tracemalloc.stop()
    elapsed=time.perf_counter()-start
    return {'output':out,'ledger':ledger.summary(),'wall_seconds':elapsed,'python_peak_bytes':memory,
            'native_trace':ledger.trace,'cold_law_preparation':method=='C'}


def validate_output(out,pair):
    if out['proof_status']!='unverified' or out['execution_allowed'] or out['completion_allowed']:return False
    if (out['status']=='NEW_DISTINCTION')!=pair['hidden']:return False
    if pair['hidden']:
        tid=out['witness']['test_id']
        return out['predictions']==[pair['Sig_left'][tid],pair['Sig_right'][tid]] and out['predictions'][0]!=out['predictions'][1]
    return True


def primitive_trace_valid(trace):
    allowed={}
    for row in trace:
        key=digest([row['source'],row['argument']])
        if row['operation']=='admissible':allowed[key]=row['result']
        if row['operation']=='extend' and allowed.get(key) is not True:return False
    return True


def reframe(w,h,q=None):
    q=q or w['query'];return load_frame(normalize_context(h,'007',[q],'C2'),h,q)


def metamorphic(base,w,f,pairs):
    l,r=w['refs']['h0'],w['refs']['h1'];positive=next(p for p in pairs if p['left']==l and p['right']==r)
    c=measure(f,'C',l,r,w['certificate_ref'])['output']
    repeated=measure(f,'C',r,l,w['certificate_ref'],known=(c['fingerprint'],))['output']
    checks=[('prior-distinction-rename',repeated['status']=='NO_NEW_DISTINCTION',repeated)]
    h=copy.deepcopy(w['history']);rename={a:'display_'+a for a in f.spec['parameters']['actions']}
    for e in h['tables']['events']:
        p=json.loads(e['content'])
        if 'word' in p:p['word']=[rename[a] for a in p['word']]
        if 'source_spec' in p:
            spec=p['source_spec'];spec['parameters']['actions']=[rename[a] for a in spec['parameters']['actions']]
            for t in spec['tests']:t['suffix']=[rename[a] for a in t['suffix']]
        e['content']=json.dumps(p)
    out=measure(reframe(w,h),'C',l,r,w['certificate_ref'],known=(c['fingerprint'],))['output']
    checks.append(('primitive-label-rename',out['status']=='NO_NEW_DISTINCTION',out))
    if w['certificate_ref']:
        for fault in ('hash','scope','version','observer','noncommutative-kind','partial'):
            h=copy.deepcopy(w['history'])
            for e in h['tables']['events']:
                if 'event:'+str(e['id'])==w['certificate_ref']:
                    p=json.loads(e['content']);cert=p['source_certificate']
                    if fault=='hash':cert['source_hash']='0'*64
                    elif fault=='scope':cert['scope']='other'
                    elif fault=='version':cert['version']=999
                    elif fault=='observer':cert['observer_hash']='f'*64
                    elif fault=='noncommutative-kind':cert['kind']='left-commuting-projection'
                    else:cert['coverage']=[]
                    e['content']=json.dumps(p)
            out=measure(reframe(w,h),'C',l,r,w['certificate_ref'])['output']
            checks.append((fault,out['strategy']=='FALLBACK_BOUNDED' and validate_output(out,positive),out))
    for case in ('C4','budget','foreign','missing','stale','germ'):
        h=copy.deepcopy(w['history']);q=copy.deepcopy(w['query']);v=view(w)
        if case=='C4':v=view(w,'C4')
        if case=='budget':v=view(w,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
        if case=='foreign':q['project']='FOREIGN'
        if case=='missing':
            v['audit_context']['tables']['events']=v['audit_context']['tables']['events'][1:];v['certificate']['context_digest']=digest(v['audit_context'])
        if case=='stale':q['version']=99;v=normalize_context(h,'007',[q],'C2')
        if case=='germ':h['tables']['events'][0]['content']=json.dumps({'word':[],'scope':q['scope'],'version':1,'representation':'analytic_germ'});v=normalize_context(h,'007',[q],'C2')
        try:load_frame(v,h,q);ok=False;answer='UNSAFE_ACCEPT'
        except BindingError as error:ok=True;answer=str(error)
        checks.append((case,ok,answer))
    small=interpret_constructive(f.fork(Ledger(1)),l,r,w['certificate_ref'],max_calls=1)
    checks.append(('global-native-budget',small['status']=='UNKNOWN_BOUNDED',small))
    for case,ok,response in checks:
        row={'world':w['id'],'case':case,'result':'PASS' if ok else 'FAIL','response':response};append(base,'metamorphic',row)
        require(base,ok,w['id']+case,'safe correct handling',row)


def mutants(base,worlds):
    """Real guard/detector inputs with deliberately unsafe mutant assertions."""
    f=frame(worlds[1]);w=worlds[1];l,r=w['refs']['h0'],w['refs']['h1']
    clean=measure(f,'C',l,r,w['certificate_ref'])['output'];records=[]
    for label in ('provenance','alias-rename','noncommutativity','stale-version','boundary-permission'):
        evidence={}
        try:
            if label=='provenance':
                mutant=copy.deepcopy(clean['source_hashes']);mutant[0]['sha256']='0'*64
                evidence={'mutant_sources':mutant,'actual_source':f.events[int(mutant[0]['ref'].split(':')[1])]}
                assert all(x['sha256']==digest(f.events[int(x['ref'].split(':')[1])]) for x in mutant)
            elif label=='alias-rename':
                actual=measure(f,'C',r,l,w['certificate_ref'],known=(clean['fingerprint'],))['output']
                mutant=copy.deepcopy(actual);mutant['status']='NEW_DISTINCTION';evidence={'safe':actual,'mutant':mutant}
                assert mutant['status']=='NO_NEW_DISTINCTION'
            elif label=='noncommutativity':
                p=f.fork(Ledger()).port();a,b=f.spec['parameters']['actions'][1],f.spec['parameters']['actions'][5]
                ab=p.load([a,b]);ba=p.load([b,a]);evidence={'ab':list(ab.value),'ba':list(ba.value),'source':f.sources([w['query']['root_ref']])}
                assert ab.value==ba.value
            elif label=='stale-version':
                h=copy.deepcopy(w['history'])
                for e in h['tables']['events']:
                    if 'event:'+str(e['id'])==w['certificate_ref']:
                        d=json.loads(e['content']);d['source_certificate']['version']=999;e['content']=json.dumps(d)
                actual=measure(reframe(w,h),'C',l,r,w['certificate_ref'])['output'];evidence={'actual':actual,'mutant_claim':'stale law accepted'}
                assert actual['law']['status']=='SOURCE_SCHEMA_CERTIFIED'
            else:
                fw=frame(worlds[7]).fork(Ledger());p=fw.port();state=p.load(fw.words[worlds[7]['refs']['h1']]);action=fw.spec['parameters']['actions'][-1]
                allowed=p.admissible(state,action);evidence={'actual_allowed':allowed,'trace':p.trace,'mutant_claim':'permission granted'}
                assert allowed is True
        except AssertionError:
            import traceback
            records.append({'fault':label,'outcome':'EXPECTED_MUTANT_ASSERTION_FAILURE','trace':traceback.format_exc(),
                            'evidence':evidence,'implementation_failure':False,'original_worlds_changed':False})
    write_json(base/'expected-fault-regressions.json',records)
    require(base,len(records)==5,'fault regressions','5 observed mutant assertion failures',records)


def feedback(base,w,f,t):
    if t['status']!='ATTENTION_PROPOSED':
        append(base,'feedback',{'world':w['id'],'result':'PASS','status':'PAUSED_NO_SAFE_TEST','independent_retained':True});return
    hs=[h for h in t['hypotheses'] if h['predictive'] and h['question']=='current' and h['status']=='ACTIVE'];env=hs[-1]['ref']
    port=f.fork(Ledger()).port();observation=raw_endpoint(port,f,env,t['suffix'])
    receipt={'scope':w['query']['scope'],'version':1,'observer':f.spec['observer'],'test_id':t['test_id'],'readout':observation}
    event=ResearchStore(Path(w['database'])).record(w['query']['project'],'counterexample','Precommitted finite environment',json.dumps({'observation':receipt}),'experiment')
    q=copy.deepcopy(w['query']);q['move']['parent_event_ids'].append(event['id']);h=read_history(Path(w['database']),q['project'])
    after=attend(reframe(w,h,q).fork(Ledger()),'event:'+str(event['id']));reference=attention(w['history'],w['query'],receipt)
    statuses={x['id']:x['status'] for x in after['hypotheses']}
    preserved=all(next(e for e in h['tables']['events'] if e['id']==old['id'])==old for old in w['history']['tables']['events'])
    ok=after['status']==reference['status'] and after.get('test_id')==reference['selected_test_id'] and statuses==reference['statuses'] and statuses['I']=='ACTIVE' and preserved
    row={'world':w['id'],'receipt':receipt,'event_id':event['id'],'T_after':after,'oracle':reference,'source_preserved':preserved,
         'independent_retained':statuses['I']=='ACTIVE','result':'PASS' if ok else 'FAIL'}
    append(base,'feedback',row);require(base,ok,w['id']+'feedback',reference,row)


def run_p0(base):
    worlds=json.loads((base/'worlds.json').read_text());oracle=json.loads((base/'oracle.json').read_text())['worlds'];paired=[];start=time.perf_counter()
    for w,reference in zip(worlds,oracle):
        setup=time.perf_counter();f=frame(w);setup=time.perf_counter()-setup
        for pair in reference['pairs']:
            l,r=pair['left'],pair['right'];b0=measure(f,'B0',l,r);b1=measure(f,'B1',l,r);c=measure(f,'C',l,r,w['certificate_ref'])
            ok=validate_output(b1['output'],pair) and validate_output(c['output'],pair)
            ok=ok and b0['output']['signatures']==[pair['Sig_left'],pair['Sig_right']]
            for x in (b0,b1,c):
                ok=ok and x['ledger']['total_native_calls']==len(x['native_trace']) and primitive_trace_valid(x['native_trace'])
            for output in (b1['output'],c['output']):
                ok=ok and bool(output['source_hashes']) and all(x['project']==w['query']['project'] and x['sha256']==digest(f.events[int(x['ref'].split(':')[1])]) for x in output['source_hashes'])
            if c['output']['status']=='NEW_DISTINCTION':ok=ok and c['output']['fingerprint']==b1['output']['fingerprint']
            row={'world':w['id'],'family':w['family'],'held_out':w['held_out'],'pair':pair,'B0':b0,'B1':b1,'C':c,
                 'input_preparation_seconds_shared':setup,'independent_verification':'PASS' if ok else 'FAIL'}
            append(base,'paired-costs',row);paired.append(row);require(base,ok,w['id']+l+r,pair,row)
        before=attend(f.fork(Ledger()));interpret_constructive(f.fork(Ledger()),w['refs']['h0'],w['refs']['h1'],w['certificate_ref']);after=attend(f.fork(Ledger()))
        expected=reference['attention'];ok=before.get('ranking')==after.get('ranking') and before.get('test_id')==after.get('test_id')==expected['selected_test_id'] and before['status']==expected['status']
        if expected['ranking']:ok=ok and [{k:r[k] for k in expected['ranking'][0]} for r in before['ranking']]==expected['ranking']
        append(base,'attention',{'world':w['id'],'T_before':before,'T_after':after,'oracle':expected,'result':'PASS' if ok else 'FAIL'})
        require(base,ok,w['id']+'H3',expected,before);metamorphic(base,w,f,reference['pairs']);feedback(base,w,f,before)
        print(json.dumps({'P0_world':w['id'],'pairs':len(paired),'status':'PASS'}),flush=True)
    mutants(base,worlds)
    for name in ('paired-costs','metamorphic','attention','feedback'):
        write_json(base/(name+'.json'),[json.loads(s) for s in (base/(name+'.jsonl')).read_text().splitlines()])
    wins={x['family'] for x in paired if x['pair']['hidden'] and x['C']['output']['strategy']=='CONSTRUCTIVE_VALIDATED' and x['C']['ledger']['total_native_calls']<x['B1']['ledger']['total_native_calls']}
    result={'result':'PASS_CONSTRUCTIVE_TRANSFER_BOUNDED' if len(wins)>=2 else 'PASS_OPERATIONAL_ONLY',
        'correctness':'PASS','pairs':len(paired),'new_distinctions':sum(x['pair']['hidden'] for x in paired),
        'winning_algebras':sorted(wins),'false_witnesses':0,'false_novelty':0,'permission_errors':0,'missed_bounded_distinctions':0,
        'seconds':time.perf_counter()-start,'max_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'P1_calls':0,
        'P1':'SKIP; no registered proposer test adds information to the deterministic mechanism question; T not re-ranked by LLM.'}
    write_json(base/'P0-result.json',result)


def initialize():
    from datetime import datetime,timezone
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    cfg=configure();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');root=SOURCE.parent
    b=Path.home()/'.local/state/livingmath/constructive007'/stamp;b.mkdir(parents=True,mode=0o700);db=(Path(cfg['LIVE_MATH_DATA_DIR'])/'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(b/'research-before.sqlite3') as dst:src.backup(dst)
    (b/'research-before.sqlite3').chmod(0o600);write_json(b/'before.json',snapshot(db))
    paths=[root/'AGENTS.md',*SOURCE.glob('*.py'),*SOURCE.glob('*.json'),*[p for p in (root/'docs/qa').rglob('*') if p.is_file()]]
    write_json(b/'metadata.json',{'private':str(b),'report':str(root/'docs/qa/LM-LIVE-MATH-CONSTRUCTIVE-007'/stamp),'db':str(db),
      'backup_sha256':hashlib.sha256((b/'research-before.sqlite3').read_bytes()).hexdigest(),'protected_files':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})
    folder=b/'live-readonly';folder.mkdir();client=Session(folder,db,cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):write_json(b/'preflight.json',{'health':await c.call('service_health',{}),'tools':(await c.session.list_tools()).model_dump(mode='json'),'contract':await c.call('research_contract',{'project':'RH'})})
    client.work=read;oauth(cfg,client);return b


def freeze(b):
    if (b/'worlds.json').exists():return
    from live_constructive007_oracle import pairs
    (b/'databases').mkdir();worlds=[create_world(b/'databases'/f'world{i}.sqlite3',i) for i in range(8)]
    write_json(b/'worlds.json',worlds);shutil.copyfile(SOURCE/'live_constructive007-contract.json',b/'frozen-contract.json')
    (b/'frozen-sources').mkdir();files=[*SOURCE.glob('live_constructive007*.py'),*SOURCE.glob('test_live_constructive007*.py'),SOURCE/'live_constructive007-contract.json']
    hashes={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for p in files:shutil.copyfile(p,b/'frozen-sources'/p.name)
    write_json(b/'pre-oracle-hashes.json',hashes)
    write_json(b/'oracle.json',{'implementation':'independent raw replay','worlds':[{'world':w['id'],'pairs':pairs(w['history'],w['query']),'attention':attention(w['history'],w['query'])} for w in worlds]})
    hashes.update({str(b/n):hashlib.sha256((b/n).read_bytes()).hexdigest() for n in ('worlds.json','oracle.json','frozen-contract.json')});write_json(b/'source-hashes.json',hashes)


def ensure_fresh(base):
    markers=('paired-costs.jsonl','P0-result.json','run-failures.json','pytest.txt','worker.txt','local86','run-state.json')
    if any((base/name).exists() for name in markers):raise SystemExit('Existing attempt retained; new cohort required')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private-dir',type=Path);p.add_argument('--worker',type=Path);args=p.parse_args()
    if args.worker:
        resource.setrlimit(resource.RLIMIT_CPU,(90,95));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));run_p0(args.worker);return
    b=args.private_dir.resolve(strict=True) if args.private_dir else initialize()
    ensure_fresh(b)
    write_json(b/'run-state.json',{'stage':'RUNNING'})
    freeze(b);failures=[]
    try:
        with (b/'pytest.txt').open('w') as out:subprocess.run([sys.executable,'-m','pytest','-q',str(SOURCE)],stdout=out,stderr=subprocess.STDOUT,check=True)
        from normalization_regression import run_regression
        reg=run_regression(b/'local86',b/'research-before.sqlite3')
        if reg['result']!='PASS':raise RuntimeError('86 MCP regression failed')
        with (b/'worker.txt').open('w') as out:subprocess.run([sys.executable,__file__,'--worker',str(b)],stdout=out,stderr=subprocess.STDOUT,timeout=120,check=True)
    except BaseException as e:
        import traceback
        (b/'exception.txt').write_text(traceback.format_exc());failures.append({'reason':str(e),'classification':'FAIL_RCA'})
    finally:
        write_json(b/'run-failures.json',failures)
        from live_constructive007_report import export
        print(json.dumps(export(b)),flush=True)


if __name__=='__main__':main()
