"""Frozen012 source experiment and honest ceiling gate; never writes production."""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical,digest
from native_preview008_qa import readonly_state
from normalization_regression import Tap,run_regression
from qa_positive_acceptance import write_json,snapshot
from research_store import ResearchStore
from concept_genesis012_native import definition_sha256
from concept_genesis012_source import Request,Frame,bind
from concept_genesis012 import evaluate,field_value
from concept_genesis012_oracle import run as oracle_run,attention as oracle_attention
from live_transfer006 import attend

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def append(path,data):
    with path.open('a') as f:f.write(json.dumps(data,ensure_ascii=False)+'\n')


def seed(database: Path, world: dict, label: str = '') -> dict:
    store=ResearchStore(database);project=world['project']
    def record(name,data,kind='hypothesis',parent=None):
        result=store.record(project,kind,label+name,canonical(data),'experiment' if kind=='counterexample' else 'hypothesis',
            parent_id=parent,request_key=project+':'+label+name)
        with store._connect() as c:return dict(c.execute('SELECT * FROM events WHERE id=?',(result['id'],)).fetchone())
    if 'fixture' not in world:
        fixture=record('fixture',{'claim_type':'SOURCE_CLAIM','statement':'Native finite source, no supplied interpretation or optimal test.',
            'scope':world['scope'],'version':1,'native_definition_sha256':definition_sha256(),'parameters':world['parameters']},kind='qa_source')
    else:fixture=world['fixture']
    refs={}
    for name,word in world['histories'].items():
        row=record(name,{'claim_type':'SOURCE_CLAIM','statement':'Unlabelled source history, not a theory.',
            'scope':world['scope'],'version':world['version'],'representation':'source012-native/v1','word':word},parent=fixture['id'])
        refs[name]=row['id']
    ind=record('independent',{'claim_type':'HYPOTHESIS','statement':'Independent research branch, no dependence on the failed coarse model.',
        'scope':'independent','version':world['version'],'representation':'source012-native/v1','word':[]},parent=fixture['id'])
    root=record('root',{'claim_type':'SOURCE_CLAIM','statement':'Equality of current observation is an unproven local predictive description.',
        'scope':world['scope'],'version':world['version'],'source_spec':{'parameters':world['parameters'],
            'histories':['event:'+str(i) for i in refs.values()],'independent_ref':'event:'+str(ind['id']),
            'tests':world['tests'],'observer':world['observer'],'scope':world['scope'],'version':world['version'],
            'primitive_sha256':definition_sha256(),'representation':'source012-native/v1',
            'instance_ref':'event:'+str(fixture['id'])+'@'+digest(fixture)}},parent=fixture['id'])
    if 'obligation_id' not in world:
        ob=store.frontier.create(project,'Bounded source interpretation only; no experiment permission.',world['scope'],[fixture['id'],root['id']])
        oid=ob['id']
    else:oid=world['obligation_id']
    return {'fixture':fixture,'root_id':root['id'],'refs':refs,'independent_id':ind['id'],'obligation_id':oid}


def request(database: Path, world: dict, binding: dict, negative=None) -> dict:
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row;events=[dict(r) for r in c.execute('SELECT * FROM events WHERE project=? ORDER BY id',(world['project'],))]
    return {'project':world['project'],'obligation_id':binding['obligation_id'],'version':world['version'],
        'root_event_id':binding['root_id'],'source_bindings':[{'event_id':e['id'],'sha256':digest(e)} for e in events],
        'observer':world['observer'],'negative_event_id':negative}


class P0:
    def __init__(self,base:Path,database:Path):
        self.base,self.db=base,database;self.checks=[];self.calls=[];self.results=[];self.metrics=[]

    def check(self,name,ok,evidence=None):
        row={'invariant':name,'result':'PASS' if ok else 'FAIL','evidence':evidence};self.checks.append(row)
        write_json(self.base/'checks.json',self.checks)
        if not ok:
            write_json(self.base/'first-failure.json',{'classification':'SOURCE_CONTRACT_BUG',**row})
            raise AssertionError(name)

    async def call(self,client,name,args,label):
        before=readonly_state(self.db);start=time.perf_counter_ns()
        response=await client.call_tool(name,{'request':args});elapsed=time.perf_counter_ns()-start
        after=readonly_state(self.db);raw=response.model_dump(mode='json')
        value=None if response.isError else (response.structuredContent or json.loads(response.content[0].text))
        index=len(self.calls)+1
        self.calls.append({'index':index,'label':label,'tool':name,'arguments':{'request':args},'response':raw,'MCP_wall_ns':elapsed})
        append(self.base/'calls.jsonl',self.calls[-1]);append(self.base/'readonly.jsonl',{'call':index,'before':before,'after':after,'exact':before==after})
        self.check(label+':read_only_all_rows_schema_sequence_inode_bytes_chain',before==after)
        if value is not None:
            self.check(label+':no_grant_no_verified',value['execution_permission']=={'allowed':False} and value['proof_status']=='unverified' and not value['measurement_executed'])
        return value

    def record_negative(self,world,data,label):
        value=ResearchStore(self.db).record(world['project'],'counterexample',label,canonical(data),'experiment',
            parent_id=data.get('histories') and int(data['histories'][0].split(':')[1]),request_key=world['project']+':'+label)
        return value['id']

    async def case(self,client,world,oracle,control=False):
        label=world['name']+(':NO_GENESIS' if control else '')
        binding=seed(self.db,world);args=request(self.db,world,binding)
        negative=await self.call(client,'source_counterexample_preview',args,label+':006_discovery')
        self.check(label+':source_discovery_not_external_measurement',negative is not None)
        if control:
            self.check(label+':no_false_genesis',negative['status']=='NO_DISTINCTION_BOUNDED',negative['status'])
            out=await self.call(client,'concept_genesis_preview',args,label+':no_negative')
            self.check(label+':unwarranted_concept_refused',out['status']=='NO_NEGATIVE_FEEDBACK')
            self.results.append({'world':world['name'],'control':True,'status':'NO_DISTINCTION_BOUNDED'})
            return
        self.check(label+':genuine_source_counterexample',negative['status']=='SOURCE_COUNTEREXAMPLE',negative['status'])
        event_id=self.record_negative(world,negative['counterexample'],'computed-native-counterexample')
        args=request(self.db,world,binding,event_id)
        candidate=await self.call(client,'concept_genesis_preview',args,label+':I_star')
        baseline=await self.call(client,'source_probing_baseline',args,label+':B1')
        self.check(label+':B1_full_finite_census',baseline['status']=='BASELINE_FINITE_CENSUS',baseline.get('reason'))
        expected={str('event:'+str(binding['refs'][name])):value for name,value in oracle['signatures'].items()}
        self.check(label+':independent_native_table',baseline['table']==expected)
        expected_T=oracle['T']
        self.check(label+':unchanged_T_independent_oracle',baseline['attention']['status']==expected_T['status'] and baseline['attention'].get('test_id')==expected_T['test_id'])
        if expected_T['ranking']:
            keys=list(expected_T['ranking'][0]);self.check(label+':exact_fraction_T',[{k:r[k] for k in keys} for r in baseline['attention']['ranking']]==expected_T['ranking'])
        self.check(label+':B1_independent_branch',next(h for h in baseline['attention']['hypotheses'] if h['id']=='IND')['status']=='ACTIVE')
        self.check(label+':C_valid_status',candidate['status'] in {'CANDIDATE_REFINEMENT','NO_VALID_INTERPRETATION'},candidate.get('reason'))
        recovered=True;semantic_valid=False
        if candidate['status']=='CANDIDATE_REFINEMENT':
            concept=candidate['concept'];actions=world['parameters']['actions'];suffix=[actions[i] for i in concept['suffix_ordinals']]
            test=next(t for t in world['tests'] if t['suffix']==suffix)
            for cell in concept['interpretations']:
                for ref in cell['source_members']:
                    self.check(label+':source_guard_native_prediction:'+ref,baseline['table'][ref][test['id']]==cell['prediction'])
            left,right=candidate['witness']['histories'];values=candidate['witness']['readouts']
            semantic_valid=baseline['table'][left][test['id']]==values[0] and baseline['table'][right][test['id']]==values[1] and values[0]!=values[1]
            self.check(label+':independent_witness',semantic_valid)
            self.check(label+':multiple_operational_interpretations',len(concept['interpretations'])>=2 and len({canonical(c['prediction']) for c in concept['interpretations']})>=2)
            self.check(label+':source_authored_dependencies',candidate['dependency_log']['oracle_access'] is False and candidate['dependency_log']['actual_hidden_environment_access'] is False)
            # Is this a new mathematical distinction beyond the fair probing baseline?
            recovered=all(all(baseline['table'][ref][test['id']]==cell['prediction'] for ref in cell['source_members']) for cell in concept['interpretations'])
            self.check(label+':independent_branch_C',next(h for h in candidate['attention']['hypotheses'] if h['id']=='IND')['status']=='ACTIVE')
            self.check(label+':C_T_is_unchanged006',candidate['attention']['test_id']==baseline['attention']['test_id'])
            if candidate.get('falsifier'):
                f=candidate['falsifier'];word=[actions[i] for i in f['suffix_ordinals']];t=next(t for t in world['tests'] if t['suffix']==word)
                self.check(label+':independent_falsifier',all(baseline['table'][ref][t['id']]==r for ref,r in zip(f['histories'],f['readouts'])) and f['readouts'][0]!=f['readouts'][1])
        else:
            # Correctly refuse an address basis that cannot explain the full presented class.
            self.check(label+':no_unjustified_candidate',candidate['reason']=='NO_TRACE_ADDRESS_EXPLAINS_THE_NEGATIVE_CLASS')
        frame,_=bind(self.db,Request.model_validate(args));table=baseline['table'];cells={}
        for ref,rows in table.items():cells.setdefault(canonical(rows),[]).append(ref)
        b0spec=copy.deepcopy(frame.spec)
        b0spec['hypotheses']=([{'id':'operator-cell:'+str(i),'ref':members[0],'weight':len(members),'predictive':True,'question':'current','depends_on':[]} for i,members in enumerate(cells.values())]+
            [{'id':'IND','ref':frame.spec['independent_ref'],'weight':1,'predictive':False,'question':'independent','depends_on':[]}])
        b0=Frame(b0spec,frame.query,frame.events,frame.words);b0.ledger.stage='B0_operator_cells';upper=attend(b0,max_calls=4096)
        # B2 has exactly its declared ability: retain the failure and reject the old coarse prediction.
        b2={'status':'OLD_COARSE_PREDICTION_REJECTED','new_feature':None,'counterexample_ref':'event:'+str(event_id),
            'source_histories_retained':len(world['histories']),'independent_branch_retained':True,'interpretation_owner':'no new interpretation generated'}
        record={'world':world['name'],'control':False,'negative_event_id':event_id,'source_binding':binding,
            'I_star_status':candidate['status'],'valid_bounded_refinement':semantic_valid,'B1_recovers_every_C_partition':recovered,
            'C_only_observable_distinctions':0 if recovered else 1,'productive_next_test':candidate.get('attention',{}).get('test_id'),
            'B0':{'operator_supplied':True,'T':upper,'costs':b0.ledger.summary()},'B2':b2,
            'C':candidate,'B1':baseline}
        self.results.append(record);write_json(self.base/(world['name']+'-results.json'),record)
        self.metrics.append({'world':world['name'],'source_refinement':semantic_valid,'new_beyond_B1':not recovered,
            'B1_calls':baseline['costs']['total_native_calls'],'C_calls':candidate['costs']['total_native_calls'],
            'B1_CPU_ns':baseline['CPU_ns'],'C_CPU_ns':candidate['CPU_ns'],
            'predictive_gain_after_external_feedback':None,'reason':'No external experiment was substituted with QA oracle/source computations.'})
        if candidate['status']=='CANDIDATE_REFINEMENT':await self.controls(client,world,binding,event_id,args,candidate)

    async def controls(self,client,world,binding,event_id,args,candidate):
        label=world['name'];no_trace={**args,'trace_access':False};no_feedback={**args,'negative_event_id':None}
        out=await self.call(client,'concept_genesis_preview',no_trace,label+':C_no_trace');self.check(label+':trace_required',out['status']=='INSUFFICIENT_CONTEXT')
        out=await self.call(client,'concept_genesis_preview',no_feedback,label+':C_no_negative');self.check(label+':negative_required',out['status']=='NO_NEGATIVE_FEEDBACK')
        for case in ('hash','observer','version','project','C4','quota','extra_authority'):
            bad=copy.deepcopy(args)
            if case=='hash':bad['source_bindings'][0]['sha256']='0'*64
            elif case=='observer':bad['observer']['mod']=1
            elif case=='version':bad['version']+=1
            elif case=='project':bad['project']='LM_QA_CONCEPT012_FOREIGN'
            elif case=='C4':bad['context_level']='C4'
            elif case=='quota':bad['max_calls']=1
            else:bad['verified']=True
            out=await self.call(client,'concept_genesis_preview',bad,label+':negative_'+case)
            self.check(label+':fail_closed_'+case,out is None if case=='extra_authority' else out['status'] in {'INSUFFICIENT_CONTEXT','BUDGET_EXHAUSTED'})
        negative=next(json.loads(e['content']) for e in snapshot(self.db)['tables']['events'] if e['id']==event_id)
        negative['readouts'][0]['observation']='intentional false witness'
        wrong=self.record_negative(world,negative,'intentional-false-native-witness')
        out=await self.call(client,'concept_genesis_preview',request(self.db,world,binding,wrong),label+':false_witness')
        self.check(label+':false_witness_rejected',out['status']=='NO_VALID_INTERPRETATION' and out['reason']=='NEGATIVE_SOURCE_REPLAY_MISMATCH')
        # Display labels, source order and version are changed by new immutable projections.
        alias=copy.deepcopy(world);mapping={a:'alias_'+str(i) for i,a in enumerate(world['parameters']['actions'])}
        alias['parameters']['actions']=[mapping[a] for a in world['parameters']['actions']]
        alias['histories']={n:[mapping[a] for a in w] for n,w in reversed(list(world['histories'].items()))}
        for t in alias['tests']:t['suffix']=[mapping[a] for a in t['suffix']]
        alias.update(fixture=binding['fixture'],obligation_id=binding['obligation_id'])
        aliased=seed(self.db,alias,'alias:')
        discovered=await self.call(client,'source_counterexample_preview',request(self.db,alias,aliased),label+':alias_discover')
        neg=self.record_negative(alias,discovered['counterexample'],'alias-counterexample')
        repeated=await self.call(client,'concept_genesis_preview',request(self.db,alias,aliased,neg),label+':alias_genesis')
        self.check(label+':rename_and_reordering_no_false_novelty',repeated['fingerprint']==candidate['fingerprint'])
        alias['version']=2;rebound=seed(self.db,alias,'v2:')
        ResearchStore(self.db).frontier.update(binding['obligation_id'],1,{'status':'TESTING','source_event_ids':[binding['fixture']['id'],rebound['root_id']]})
        discovered=await self.call(client,'source_counterexample_preview',request(self.db,alias,rebound),label+':version_discover')
        neg=self.record_negative(alias,discovered['counterexample'],'v2-counterexample')
        repeated=await self.call(client,'concept_genesis_preview',request(self.db,alias,rebound,neg),label+':version_genesis')
        self.check(label+':version_no_false_novelty',repeated['fingerprint']==candidate['fingerprint'])


async def mathematical_p0(base: Path, database: Path, worlds: list, oracle: list) -> dict:
    experiment=P0(base,database);folder=base/'mcp';folder.mkdir()
    params=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'concept_genesis012_server.py'),'--db',str(database)])
    with (folder/'stderr.txt').open('w') as error:
        async with stdio_client(params,errlog=error) as (read,write):
            async with ClientSession(Tap(read,folder/'wire.jsonl','response'),Tap(write,folder/'wire.jsonl','request')) as client:
                init=await client.initialize();tools=(await client.list_tools()).model_dump(mode='json');write_json(folder/'schemas.json',{'initialize':init.model_dump(mode='json'),**tools})
                experiment.check('MCP_only_three_readonly_tools',len(tools['tools'])==3 and all(t['annotations']['readOnlyHint'] for t in tools['tools']))
                for w,o in zip(worlds,oracle):await experiment.case(client,w,o)
                for world in worlds:
                    control=copy.deepcopy(world);control['project']+='_N';control['scope']+='/NO_GENESIS'
                    control['histories']={name:[] for name in control['histories']}
                    await experiment.case(client,control,None,True)
    positives=[r for r in experiment.results if not r.get('control')]
    ceiling=all(r['B1_recovers_every_C_partition'] for r in positives)
    result={'scientific_decision':'FAIL_CEILING' if ceiling else 'REQUIRES_TYPED_GATE',
        'bounded_refinement_candidates':sum(r['valid_bounded_refinement'] for r in positives),'worlds':4,
        'valid_genesis_rate':0 if ceiling else None,'source_refinement_rate':sum(r['valid_bounded_refinement'] for r in positives)/4,
        'C_only_observable_distinctions':sum(r['C_only_observable_distinctions'] for r in positives),
        'predictive_gain_after_feedback':None,'false_genesis':0,'false_grant':0,'LLM_calls':0,
        'typed_cycles_completed':0,'typed_receipts_created':0,'independent_branch_retention':1.0,
        'next_gate':'STOP before expensive typed cycles / hidden world' if ceiling else 'Stage needs source-adapter review; no inherited authority.',
        'metrics':experiment.metrics,'checks_PASS':sum(c['result']=='PASS' for c in experiment.checks),'checks_FAIL':sum(c['result']=='FAIL' for c in experiment.checks),
        'epistemic_note':'Source-native computed counterexamples and oracle checks are not independent external measurements.'}
    write_json(base/'P0-result.json',result)
    write_json(base/'typed-cycle-stage.json',{'status':'NOT_RUN_FAIL_CEILING' if ceiling else 'NOT_RUN_ADAPTER_REVIEW_REQUIRED',
        'receipts':[],'execution_grants':0,'journal_writes':0,'reason':result['next_gate']})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline-dir',type=Path)
    parser.add_argument('--replay-frozen',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.replay_frozen:
        if not args.output:parser.error('--replay-frozen requires a fresh --output')
        base=args.output.resolve();base.mkdir(parents=True,exist_ok=False);frozen=args.replay_frozen.resolve(strict=True)
        db=base/'isolated.sqlite3';ResearchStore(db)
        worlds=json.loads((frozen/'worlds.json').read_text());oracle=json.loads((frozen/'oracle.json').read_text())
        print(json.dumps(asyncio.run(mathematical_p0(base,db,worlds,oracle))),flush=True);return
    if args.baseline_dir is None:parser.error('--baseline-dir required; use source replay without private data via --replay-frozen/--output')
    baseline=args.baseline_dir.resolve(strict=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');base=baseline/'cohorts'/stamp
    base.mkdir(parents=True,mode=0o700);Path('/tmp/lm012_cohort').write_text(str(base))
    write_json(base/'metadata.json',{'baseline':str(baseline),'report':str(ROOT/'docs/qa/LM-CONCEPT-GENESIS-012'/stamp)})
    frozen=baseline/'frozen-inputs';manifest=json.loads((frozen/'manifest.json').read_text());assert all(sha(frozen/n)==h for n,h in manifest.items())
    shutil.copytree(frozen,base/'frozen-inputs');(base/'frozen-sources').mkdir()
    paths=[*SOURCE.glob('concept_genesis012*.py'),SOURCE/'test_concept_genesis012.py']
    for p in paths:
        if p.exists():shutil.copyfile(p,base/'frozen-sources'/p.name)
    write_json(base/'source-manifest.json',{str(p):sha(p) for p in paths if p.exists()})
    db=base/'isolated.sqlite3'
    with sqlite3.connect((baseline/'research-before.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(db) as dest:src.backup(dest)
    p0_start=time.perf_counter_ns();cpu=time.process_time_ns();child0=resource.getrusage(resource.RUSAGE_CHILDREN);failure=None
    try:
        worlds=json.loads((frozen/'worlds.json').read_text());oracle=json.loads((frozen/'oracle.json').read_text())
        result=asyncio.run(mathematical_p0(base,db,worlds,oracle))
        children=resource.getrusage(resource.RUSAGE_CHILDREN)
        measured={'wall_ns':time.perf_counter_ns()-p0_start,'CPU_ns':time.process_time_ns()-cpu+round((children.ru_utime+children.ru_stime-child0.ru_utime-child0.ru_stime)*1e9),
            'peak_RSS_KiB':max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children.ru_maxrss),'scope':'Complete mathematical P0 including normalization, MCP source calls, baseline/evaluation and source recording; before regressions.'}
        measured['resource_PASS']=measured['wall_ns']<=120e9 and measured['CPU_ns']<=90e9;write_json(base/'P0-costs.json',measured)
        if not measured['resource_PASS']:raise RuntimeError('P0_RESOURCE_FAIL')
        print(json.dumps({'mathematical_P0':result['scientific_decision'],'candidates':result['bounded_refinement_candidates'],'P0_costs':measured}),flush=True)
        # G6 is code preservation verification after scientific evaluation, not a continuation of blocked research.
        env={k:v for k,v in os.environ.items() if k not in {'LIVE_MATH_NATIVE_PREVIEW','LIVE_MATH_TYPED_CYCLE_DB'}}
        with (base/'pytest.txt').open('w') as out:subprocess.run([sys.executable,'-m','pytest','-q',str(SOURCE)],stdout=out,stderr=subprocess.STDOUT,env=env,check=True)
        saved={k:os.environ.pop(k,None) for k in ('LIVE_MATH_NATIVE_PREVIEW','LIVE_MATH_TYPED_CYCLE_DB')}
        try:legacy=run_regression(base/'historical86',baseline/'research-before.sqlite3')
        finally:
            for k,v in saved.items():
                if v is not None:os.environ[k]=v
        if legacy['result']!='PASS':raise AssertionError('HISTORICAL86_FAILED')
    except BaseException as error:
        failure={'classification':'SOURCE_CONTRACT_BUG','error':str(error),'traceback':traceback.format_exc()}
        if (base/'first-failure.json').exists():write_json(base/'run-failure.json',failure)
        else:write_json(base/'first-failure.json',failure)
        print(json.dumps(failure),flush=True)
    finally:
        from concept_genesis012_report import export
        print(json.dumps(export(base,failure)),flush=True)


if __name__=='__main__':main()
