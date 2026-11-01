"""Frozen finite005 acceptance; canonical research data is never written."""
import argparse
import asyncio
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from normalizer import Budget,canonical,digest,normalize_context,read_history
from live_core005 import interpret_distinction,transfer_attention,apply_feedback
from live_core005_worlds import create_world,build_view,append_observation
from live_core005_oracle import all_pairs,attention,feedback
from normalization_regression import run_regression,Tap
from qa_positive_acceptance import snapshot,write_json

SOURCE=Path(__file__).parent


def initialize() -> Path:
    from attention_qa import configure
    from qa_positive_acceptance import oauth
    from transfer_qa import Session
    cfg=configure();root=SOURCE.parent;stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base=Path.home()/'.local/state/livingmath/core005'/stamp;base.mkdir(parents=True,mode=0o700)
    db=(Path(cfg['LIVE_MATH_DATA_DIR'])/'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(base/'research-before.sqlite3') as dest:src.backup(dest)
    (base/'research-before.sqlite3').chmod(0o600);write_json(base/'before.json',snapshot(db))
    paths=[root/'AGENTS.md',*SOURCE.glob('*.py'),*SOURCE.glob('*.json'),*[p for p in (root/'docs/qa').rglob('*') if p.is_file()]]
    write_json(base/'metadata.json',{'private':str(base),'report':str(root/'docs/qa/LM-LIVE-MATH-CORE-005'/stamp),'db':str(db),
        'backup_sha256':hashlib.sha256((base/'research-before.sqlite3').read_bytes()).hexdigest(),
        'protected_files':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'endpoint':cfg['LIVE_MATH_PUBLIC_URL']+'/mcp'})
    folder=base/'live-readonly';folder.mkdir();client=Session(folder,db,cfg['LIVE_MATH_PUBLIC_URL'])
    async def read(c):
        write_json(base/'live-preflight.json',{'initialize':c.initialized,'tools':(await c.session.list_tools()).model_dump(mode='json'),
            'health':await c.call('service_health',{}),'contract_RH':await c.call('research_contract',{'project':'RH'})})
    client.work=read;oauth(cfg,client)
    return base


def freeze(base: Path) -> None:
    if (base/'worlds.json').exists():return
    folder=base/'world-databases';folder.mkdir()
    worlds=[create_world(folder/f'world{i}.sqlite3',i) for i in range(4)]
    write_json(base/'worlds.json',worlds)
    write_json(base/'oracle.json',{'implementation':'live_core005_oracle.py; independent sequential full enumeration',
        'worlds':[{'world':w['id'],'pairs':all_pairs(w['history'],w['query']),'attention':attention(w['history'],w['query'])} for w in worlds]})
    contract=json.loads((SOURCE/'live_core005-contract.json').read_text())
    write_json(base/'frozen-contract.json',contract)
    paths=[*SOURCE.glob('live_core005*.py'),SOURCE/'test_live_core005.py',SOURCE/'live_core005-contract.json']
    archive=base/'frozen-sources';archive.mkdir()
    for p in paths:shutil.copyfile(p,archive/p.name)
    paths += [base/name for name in ('worlds.json','oracle.json','frozen-contract.json')]
    write_json(base/'frozen-manifest.json',{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    for name in ('worlds.json','oracle.json','frozen-contract.json','frozen-manifest.json'):(base/name).chmod(0o444)


def negative_controls(base: Path, world: dict) -> list:
    outcomes=[];directory=base/'negative-inputs';directory.mkdir(exist_ok=True)
    for case in ('C4','budget_C3','missing_C2','missing_C3','hash','catalog','foreign','stale','closed','point_germ','observer','alias'):
        h=copy.deepcopy(world['history']);q=copy.deepcopy(world['query']);view=build_view(world)
        left,right=world['refs']['h3'],world['refs']['h0'];other=None
        if case=='C4':view=build_view(world,'C4')
        if case=='budget_C3':view=build_view(world,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
        if case.startswith('missing_'):
            view=build_view(world,case.split('_')[1]);view['audit_context']['tables']['events']=[r for r in view['audit_context']['tables']['events'] if r['id']!=int(left.split(':')[1])]
            view['certificate']['context_digest']=digest(view['audit_context'])
        if case=='hash':view['audit_context']['tables']['events'][0]['content']+='tamper'
        if case=='catalog':view['source_catalog'][left]='0'*64
        if case=='foreign':q['project']='FOREIGN'
        if case in {'stale','closed'}:
            from research_store import ResearchStore
            path=directory/(world['id']+'-'+case+'.sqlite3')
            with sqlite3.connect(Path(world['database']).resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(path) as dst:src.backup(dst)
            store=ResearchStore(path)
            changes={'status':'TESTING'} if case=='stale' else {'status':'REFUTED','closure_reason':'Synthetic closure control',
                'evidence_refs':[world['refs']['root']],'reopen_conditions':['New version and scoped evidence.']}
            store.frontier.update(q['move']['active_frontier_id'],1,changes)
            if case=='closed':q['version']=2
            h=read_history(path,world['project']);view=normalize_context(h,'finite',[q],'C2')
        if case=='point_germ':left,right=world['refs']['point'],world['refs']['germ']
        if case=='observer':other='parity' if world['index']!=1 else 'x'
        if case=='alias':left=world['refs']['alias']
        result=interpret_distinction(view,h,q,left,right,other_observer=other)
        t=None if case in {'point_germ','observer','alias'} else transfer_attention(view,h,q)
        ok=result['status']=='INSUFFICIENT_CONTEXT' and not result['execution_allowed']
        if t:ok=ok and t['status']=='INSUFFICIENT_CONTEXT' and not t['execution_allowed']
        record={'world':world['id'],'case':case,'I':result,'T':t,'result':'PASS' if ok else 'FAIL',
            'I_arguments':{'query':q,'left_ref':left,'right_ref':right,'other_observer':other},'view_digest':digest(view),'source_digest':digest(h)}
        write_json(directory/(world['id']+'-'+case+'.json'),{'record':record,'view':view,'source':h})
        outcomes.append(record)
    return outcomes


def run_p0(base: Path) -> dict:
    worlds=json.loads((base/'worlds.json').read_text());oracle=json.loads((base/'oracle.json').read_text())['worlds']
    witnesses=[];decisions=[];controls=[];cycles=[];errors=[];timings=[]
    def check(condition,kind,case,expected,actual):
        if not condition:errors.append({'classification':kind,'case':case,'expected':expected,'actual':actual})
    for w,expected in zip(worlds,oracle):
        view=build_view(w);start=time.perf_counter()
        for pair in expected['pairs']:
            out=interpret_distinction(view,w['history'],w['query'],pair['left_ref'],pair['right_ref'])
            positive=out['status']=='NEW_DISTINCTION';valid=positive==pair['hidden_distinction']
            if positive:
                witness=out['witness'];a=next((r for r in pair['Sig_left'] if r['test_id']==witness['test_id']),None)
                b=next((r for r in pair['Sig_right'] if r['test_id']==witness['test_id']),None)
                valid=valid and bool(a and b and a['suffix']==b['suffix']==witness['suffix']
                    and a['readout']==witness['left'] and b['readout']==witness['right'] and a['readout']!=b['readout'])
            check(valid,'I_WITNESS_BUG',w['id']+pair['left_ref']+pair['right_ref'],pair,out)
            witnesses.append({'world':w['id'],'pair':pair,'I':out,'result':'PASS' if valid else 'FAIL'})
        chosen=transfer_attention(view,w['history'],w['query']);reference=expected['attention']
        exact=(chosen.get('test_id')==reference['selected_test_id'] and chosen.get('ties')==reference['optimal_test_ids']
            and [{k:r[k] for k in ('test_id','cost','loss','expected_remaining')} for r in chosen.get('ranking',[])]==reference['ranks'])
        check(exact,'T_RANKING_BUG',w['id'],reference,chosen)
        decisions.append({'world':w['id'],'phase':'before','T':chosen,'oracle':reference,'result':'PASS' if exact else 'FAIL'})
        controls.extend(negative_controls(base,w))
        known=interpret_distinction(view,w['history'],w['query'],w['refs']['h3'],w['refs']['h0'])
        repeat=interpret_distinction(view,w['history'],w['query'],w['refs']['h3'],w['refs']['h0'],
            known=(known.get('fingerprint'),),title='Renamed proposition')
        check(repeat['status']=='NO_NEW_DISTINCTION','FALSE_NOVELTY',w['id'],'NO_NEW_DISTINCTION',repeat)
        after,ref=append_observation(w,chosen);after_view=build_view(after)
        updated=apply_feedback(after_view,after['history'],after['query'],ref)
        receipt=json.loads(next(r for r in after['history']['tables']['events'] if 'event:'+str(r['id'])==ref)['content'])['observation']
        expected_status=feedback(w['history'],w['query'],receipt)
        actual={h['id']:h['status'] for h in updated.get('hypotheses',[])}
        preserved=all(next(r for r in after['history']['tables']['events'] if r['id']==old['id'])==old for old in w['history']['tables']['events'])
        valid=actual==expected_status and actual.get('I')=='ACTIVE' and any(v=='EXCLUDED_DEPENDENCY' for v in actual.values()) and preserved
        check(valid,'FEEDBACK_OR_SOURCE_BUG',w['id'],expected_status,updated)
        next_t=transfer_attention(after_view,after['history'],after['query'],ref)
        next_oracle=attention(after['history'],after['query'],[i for i,s in expected_status.items() if s!='ACTIVE'])
        match=next_t['status']==next_oracle['status'] and (not next_oracle['optimal_test_ids'] or next_t.get('test_id')==next_oracle['selected_test_id'])
        check(match,'T_AFTER_FEEDBACK_BUG',w['id'],next_oracle,next_t)
        decisions.append({'world':w['id'],'phase':'after','T':next_t,'oracle':next_oracle,'result':'PASS' if match else 'FAIL'})
        narrowed=interpret_distinction(after_view,after['history'],after['query'],w['refs']['h3'],w['refs']['h0'])
        cycles.append({'world':w['id'],'I_before':known,'renamed':repeat,'attention':chosen,'observation_event':ref,
            'observation':receipt,'feedback':updated,'I_after':narrowed,'next_attention':next_t,'source_preserved':preserved,
            'narrowed_guard_excludes_counterexample':narrowed.get('guard',{}).get('left_state')!=narrowed.get('guard',{}).get('right_state'),
            'after_history':after['history'],'after_query':after['query']})
        timings.append(time.perf_counter()-start)
        print(json.dumps({'P0_world':w['id'],'witness_cases':len(expected['pairs']),'errors':len(errors)}),flush=True)
    for row in controls:
        check(row['result']=='PASS','FAIL_CLOSED_BUG',row['world']+row['case'],'INSUFFICIENT_CONTEXT',row)
    all_outputs=[r['I'] for r in witnesses]+[r['T'] for r in decisions]
    false_grants=sum(bool(r.get('execution_allowed')) or r.get('proof_status')!='unverified' for r in all_outputs)
    result={'result':'PASS' if not errors and not false_grants else 'FAIL','worlds':4,'pair_cases':len(witnesses),
        'valid_witness_cases':sum(r['result']=='PASS' for r in witnesses),
        'new_distinctions':sum(r['I']['status']=='NEW_DISTINCTION' for r in witnesses),
        'false_novelty':sum(r['I']['status']=='NEW_DISTINCTION' and not r['pair']['hidden_distinction'] for r in witnesses),
        'missed_distinctions':sum(r['I']['status']!='NEW_DISTINCTION' and r['pair']['hidden_distinction'] for r in witnesses),
        'false_grants':false_grants,'attention_checks':len(decisions),'negative_controls':len(controls),
        'independent_branches_preserved':sum(c['feedback'].get('hypotheses',[])[-1]['status']=='ACTIVE' for c in cycles),
        'errors':len(errors),'world_cycle_seconds':timings}
    for name,data in [('witnesses.json',witnesses),('attention-decisions.json',decisions),('controls.json',controls),
                      ('cycles.json',cycles),('P0-failures.json',errors),('P0-result.json',result)]:write_json(base/name,data)
    return result


def log_algorithms(base: Path) -> dict:
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    world=json.loads((base/'worlds.json').read_text())[0];cycle=json.loads((base/'cycles.json').read_text())[0]
    folder=base/'local-logging';folder.mkdir();calls=[]
    params=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'mcp_server.py'),'stdio'],
                                env={**os.environ,'LIVE_MATH_DB':world['database']})
    async def run():
        with (folder/'stderr.txt').open('w') as err:
            async with stdio_client(params,errlog=err) as (read,write):
                async with ClientSession(Tap(read,folder/'wire.jsonl','response'),Tap(write,folder/'wire.jsonl','request')) as session:
                    init=await session.initialize();tools=await session.list_tools()
                    write_json(folder/'tools.json',tools.model_dump(mode='json'))
                    for tool,args in [('interpret',{'project':world['project'],'focus':'Algorithm-constructed finite distinction',
                        'claim':json.dumps(cycle['I_before'],sort_keys=True),'evidence':world['refs']['root'],
                        'parent_id':int(world['refs']['root'].split(':')[1]),'request_key':'core005:local:I'}),
                        ('attend',{'project':world['project'],'focus':cycle['attention']['test_id'],
                        'reason':json.dumps(cycle['attention'],sort_keys=True),'parent_id':int(world['refs']['root'].split(':')[1]),
                        'request_key':'core005:local:T'})]:
                        response=await session.call_tool(tool,args)
                        calls.append({'tool':tool,'request':args,'response':response.model_dump(mode='json')})
                        if response.isError:raise RuntimeError('Local logging MCP failure')
    asyncio.run(run());write_json(folder/'calls.json',calls)
    result={'result':'PASS','calls':2,'transport':'real isolated MCP stdio',
        'content_origin':'experimental algorithm I/T','MCP_role':'persist supplied content only',
        'production_research_writes':0,'core_tools_installed':False}
    write_json(folder/'result.json',result);return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir',type=Path)
    parser.add_argument('--pilot',action='store_true',help='After P0 PASS, at most6 new model calls; never main24')
    args=parser.parse_args();base=args.private_dir.resolve(strict=True) if args.private_dir else initialize()
    if (base/'P0-result.json').exists() or (base/'pilot').exists():raise SystemExit('Existing results retained; use a fresh directory')
    freeze(base);write_json(base/'run-state.json',{'stage':'P0','pilot_requested':args.pilot})
    failures=[]
    try:
        with (base/'pytest.txt').open('w') as output:
            subprocess.run([sys.executable,'-m','pytest','-q',str(SOURCE)],stdout=output,stderr=subprocess.STDOUT,check=True)
        reg=run_regression(base/'local86',base/'research-before.sqlite3')
        if reg['result']!='PASS':raise RuntimeError('Historical86 regression failure')
        result=run_p0(base)
        if result['result']=='PASS':
            log_algorithms(base)
            if args.pilot:
                from live_core005_pilot import prepare,run
                run(base,prepare(base))
    except BaseException as error:
        import traceback
        (base/'exception.txt').write_text(traceback.format_exc())
        failures.append({'classification':'EXPERIMENT_PIPELINE_FAILURE','reason':type(error).__name__+': '+str(error)})
    finally:
        write_json(base/'run-failures.json',failures)
        from live_core005_report import export
        print(json.dumps(export(base)),flush=True)


if __name__=='__main__':main()
