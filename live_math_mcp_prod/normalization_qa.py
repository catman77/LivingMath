"""P0 acceptance and optional small P1; production research SQLite is SELECT-only."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from attention_qa import configure
from normalizer import Budget, canonical, digest, normalize_context, reconstruct_context, read_history, ENCODING
from normalization_worlds import create_world, SEED
from normalization_oracle import expected, materialize, run_audit, audit_projection
from normalization_regression import run_regression, run_demonstration
from qa_positive_acceptance import snapshot, write_json


def initialize() -> Path:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base=Path.home()/'.local/state/livingmath/normalization004'/stamp;base.mkdir(parents=True,mode=0o700)
    cfg=configure();db=(Path(cfg['LIVE_MATH_DATA_DIR'])/'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(base/'research-before.sqlite3') as dst:src.backup(dst)
    (base/'research-before.sqlite3').chmod(0o600);write_json(base/'before.json',snapshot(db))
    root=Path(__file__).resolve().parents[1]
    write_json(base/'metadata.json',{'private':str(base),'report':str(root/'docs/qa/LM-SUTI-NORMALIZATION-004'/stamp),'db':str(db),
        'endpoint':cfg['LIVE_MATH_PUBLIC_URL']+'/mcp','backup_sha256':hashlib.sha256((base/'research-before.sqlite3').read_bytes()).hexdigest(),
        'source_before':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        'AGENTS_sha256':hashlib.sha256((root/'AGENTS.md').read_bytes()).hexdigest()})
    # Real MCP reads; temporary owner OAuth registration is separate from the canonical research DB.
    from transfer_qa import Session
    from qa_positive_acceptance import oauth
    folder=base/'live-readonly';folder.mkdir();client=Session(folder,db,cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):
        write_json(base/'live-preflight.json',{'initialize':c.initialized,'tools':(await c.session.list_tools()).model_dump(mode='json'),
            'contract_RH':await c.call('research_contract',{'project':'RH'}),'health':await c.call('service_health',{})})
    client.work=read;oauth(cfg,client)
    return base


def prepare_p0(base: Path) -> list:
    directory=base/'world-databases';directory.mkdir(exist_ok=False)
    worlds=[]
    for i in range(16):
        w=create_world(directory/('world-'+str(i)+'.sqlite3'),i)
        start=time.perf_counter();again=read_history(Path(w['database']),w['project']);w['source_lookup_seconds']=time.perf_counter()-start
        assert digest(again)==digest(w['history'])
        worlds.append(w)
    write_json(base/'worlds.json',worlds)
    write_json(base/'cases.json',[{'world':w['index'],'candidate':a} for w in worlds for a in w['candidates']])
    write_json(base/'oracle.json',{'seed':SEED,'independent_rules':'normalization_oracle.expected',
        'expected':[{'id':a['id'],**expected(a)} for w in worlds for a in w['candidates']],
        'finite_math_control':{'polynomial_coefficients':[0,1],'point_at_zero':0,'zero_analytic_germ':False,
                               'scope':'Finite polynomial example only; no SRT completeness claim'},
        'hidden_guard_control':{'h_values':[0,1],'separating_readout':[0,1],'constant_readout':[0,0],
                                'unique_distinguishing_test':'read h once; this oracle is not in normalization output'}})
    write_json(base/'preregistration.json',{'protocol':'004.P0.1','seed':SEED,'worlds':16,'Dq_per_world':36,
        'levels':['C0','C1','C2','C3','C4'],'complete_levels':['C0','C1','C2','C3'],
        'material_comparison':'Exact report including verdict/findings/scope/event hashes/versions/proof status/reopen conditions.',
        'P0_gate':'100% exact audits on complete views, independent oracle match, roundtrip, unknown/adverse retention, no false-grant.',
        'incomplete_gate':'Budget/missing/foreign/tampered/out-of-Dq/C4 must not grant; INSUFFICIENT_CONTEXT is explicit.',
        'P1_gate':'No remote inference before P0 PASS; at most16 calls, main32 requires separate after-pilot decision.'})
    paths=[base/name for name in ('worlds.json','cases.json','oracle.json','preregistration.json')]
    paths+=list(Path(__file__).parent.glob('normaliz*.py'))+[Path(__file__).with_name('normalization-schema.json')]
    manifest={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write_json(base/'P0-manifest.json',manifest)
    for p in paths[:4]:p.chmod(0o444)
    return worlds


def run_p0(base: Path, worlds: list) -> dict:
    root=base/'materialized';root.mkdir()
    comparisons=[];metrics=[];failures=[];ledgers=[];negative=[]
    def fail(kind,case,expected_value,actual):
        failures.append({'classification':kind,'case':case,'expected':expected_value,'actual':actual})
    for w in worlds:
        history=w['history'];dq=w['candidates'];full=materialize(history,root/(f'full-{w["index"]}.sqlite3'))
        baseline={}
        for a in dq:
            result=run_audit(full,a);baseline[a['id']]=result;prediction=expected(a)
            if result['status']!='AUDITED' or result['report']['verdict']!=prediction['verdict'] or sorted(result['report']['warnings'])!=prediction['codes']:
                fail('TEST_ORACLE_BUG',a['id'],prediction,result)
        for level in ('C0','C1','C2','C3','C4'):
            start=time.perf_counter();view=normalize_context(history,'zero microtheory audit',dq,level);elapsed=time.perf_counter()-start
            auditable=level!='C4';store=materialize(view['audit_context'],root/(f'{level}-{w["index"]}.sqlite3')) if view['status']=='COMPLETE' else None
            success=True if auditable else None
            if auditable:
                if view['status']!='COMPLETE':
                    fail('PROJECTION_LOSS_BUG',str(w['index'])+level,'COMPLETE',view['unresolved']);success=False
                else:
                    recovered=reconstruct_context(view,history)
                    success=digest(recovered)==view['input_digest']
                    if not success:fail('SOURCE_BINDING_BUG',str(w['index'])+level,'exact source roundtrip',False)
            for a in dq:
                projected=audit_projection(store,view,a,history);same=projected==baseline[a['id']]
                full_allowed=baseline[a['id']].get('report',{}).get('verdict')=='EXPERIMENT_ALLOWED'
                projected_allowed=projected.get('report',{}).get('verdict')=='EXPERIMENT_ALLOWED'
                safe_refusal=projected['status']=='INSUFFICIENT_CONTEXT' and not projected.get('execution_allowed')
                if auditable and not same:fail('NORMALIZER_BUG',a['id']+level,baseline[a['id']],projected)
                if not auditable and not safe_refusal:fail('PROJECTION_LOSS_BUG',a['id']+level,'INSUFFICIENT_CONTEXT',projected)
                comparisons.append({'world':w['index'],'level':level,'candidate_id':a['id'],'exact_equal':same,
                    'expected_safe_refusal':not auditable,'false_grant':not full_allowed and projected_allowed,
                    'full':baseline[a['id']],'projected':projected})
            selected={e['id'] for e in view['audit_context']['tables']['events']} if view['audit_context'] else set()
            adverse={e['id'] for e in history['tables']['events'] if e['kind']=='counterexample' or e['status']=='refuted'}
            lost=adverse-selected if auditable else set()
            if lost:fail('PROJECTION_LOSS_BUG',str(w['index'])+level,'No lost adverse evidence',sorted(lost))
            raw=canonical(history).encode();output=canonical(view).encode()
            metrics.append({'world':w['index'],'level':level,'status':view['status'],'input_bytes':len(raw),'output_bytes':len(output),
                'input_tokens':len(ENCODING.encode(raw.decode(),disallowed_special=())),'output_tokens':len(ENCODING.encode(output.decode(),disallowed_special=())),
                'normalization_seconds':elapsed,'source_roundtrip':success,'lost_adverse':sorted(lost),'concepts':len(view['concepts'])})
            ledgers.append({'world':w['index'],'level':level,'ledger':view['loss_ledger']})
            if w['index']==0:write_json(base/('example-'+level+'.json'),view)
        small=normalize_context(history,'zero',dq,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
        missing=copy.deepcopy(history);missing['tables']['events']=[e for e in missing['tables']['events'] if e['id']!=w['events']['adverse']]
        missing_view=normalize_context(missing,'zero',dq,'C2')
        for name,view in [('budget',small),('missing_source',missing_view)]:
            denied=audit_projection(None,view,dq[0],history)
            ok=denied['status']=='INSUFFICIENT_CONTEXT' and not denied['execution_allowed']
            negative.append({'world':w['index'],'case':name,'result':'PASS' if ok else 'FAIL','response':denied})
            if not ok:fail('PROJECTION_LOSS_BUG',str(w['index'])+name,'Fail closed',denied)
        print(json.dumps({'P0_world':w['index'],'candidates':len(dq),'failures':len(failures)}),flush=True)
    write_json(base/'audit-equivalence.json',{'comparisons':comparisons,'negative_controls':negative})
    write_json(base/'loss-ledger.json',ledgers);write_json(base/'P0-metrics.json',metrics);write_json(base/'P0-failures.json',failures)
    result={'result':'PASS' if not failures else 'FAIL','worlds':len(worlds),'candidate_family_size':sum(len(w['candidates']) for w in worlds),
        'complete_audit_comparisons':sum(not r['expected_safe_refusal'] for r in comparisons),
        'exact_complete_matches':sum(r['exact_equal'] and not r['expected_safe_refusal'] for r in comparisons),
        'false_grants':sum(r['false_grant'] for r in comparisons),'failures':len(failures),'negative_controls':len(negative)}
    write_json(base/'P0-result.json',result);return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir',type=Path,help='Existing prepared read-only baseline, never a previously sampled run')
    parser.add_argument('--p0-only',action='store_true',help='Reproduce deterministic acceptance without remote model calls')
    args=parser.parse_args();base=args.private_dir.resolve(strict=True) if args.private_dir else initialize()
    if (base/'P0-result.json').exists() or (base/'pilot').exists():raise SystemExit('Existing results are retained; use a fresh run directory')
    print(json.dumps({'private':str(base)}),flush=True)
    failures=[]
    try:
        with (base/'pytest.txt').open('w') as output:
            subprocess.run([sys.executable,'-m','pytest',str(Path(__file__).parent),'-q'],stdout=output,stderr=subprocess.STDOUT,check=True)
        regression=base/'local86/result.json'
        if not regression.exists():run_regression(base/'local86',base/'research-before.sqlite3')
        saved=json.loads(regression.read_text())
        if saved['result']!='PASS':raise RuntimeError('86 isolated MCP invariants failed')
        worlds=prepare_p0(base);p0=run_p0(base,worlds)
        if p0['result']=='PASS':run_demonstration(base/'demonstration')
        if p0['result']=='PASS' and not args.p0_only:
            from normalization_pilot import prepare,run
            tasks=prepare(base);run(base,tasks)
    except BaseException as error:
        import traceback
        (base/'exception.txt').write_text(traceback.format_exc())
        failures.append({'classification':'NORMALIZER_BUG','stage':'orchestration','reason':type(error).__name__+': '+str(error)})
    finally:
        write_json(base/'run-failures.json',failures)
        from normalization_report import export
        result=export(base)
        print(json.dumps({'report':result['report'],'P0':result['P0'],'GO':result['read_only_MCP_tool']}),flush=True)


if __name__=='__main__':main()
