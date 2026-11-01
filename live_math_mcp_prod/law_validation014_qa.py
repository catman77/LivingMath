"""Bounded014 acceptance through real confined MCP and explicit local authority."""
import argparse
import asyncio
from collections import Counter
import copy
from datetime import datetime,timezone
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical,digest
from native_preview008_qa import readonly_state
from normalization_regression import Tap
from qa_positive_acceptance import write_json,snapshot
from research_store import ResearchStore
from research_cycle009 import MECHANISM
from typed_cycle011 import ordinal_parameters
from typed_cycle011_store import install as install011,register_scope,connect
from typed_cycle011_operator import activate
from law_validation014_operator import commit
from law_validation014_store import install as install_guards
from law_validation014_native import Port,Ledger,native_sha
from law_validation014_contract import ADAPTER
from live_transfer006 import endpoint

SOURCE=Path(__file__).resolve().parent
OBSERVER={'projection':'primary','mod':None}


def append(path,row):
    with path.open('a') as stream:stream.write(canonical(row)+'\n');stream.flush();os.fsync(stream.fileno())


def acquisition(declaration):
    ledger=Ledger(20000);port=Port(declaration,ledger);ledger.stage='discovery'
    origin=port.load([]);origin_image=port.inspect(origin);cache={():{'state':origin,'admissibility':[]}};transitions=[]
    for n in range(3):
        for w in product(range(declaration['arity']),repeat=n):
            word=list(w);readout=endpoint(port,cache,word,OBSERVER)
            if not readout['defined']:continue
            before=port.inspect(cache[tuple(word)]['state'])
            for a in range(declaration['arity']):
                response=endpoint(port,cache,word+[a],OBSERVER)
                if response['defined']:
                    transitions.append({'before':before,'after':port.inspect(cache[tuple(word+[a])]['state']),'action':a,'history':word})
    ledger.stage='separate_validation';validation=endpoint(port,cache,[0,1,0,0],OBSERVER)
    return {'origin':origin_image,'transitions':transitions,'executed_words':[list(w) for w in cache],
            'validation':validation,'costs':ledger.summary(),'native_trace':ledger.rows,
            'opaque_image':port.inspect(origin,opaque=True) if declaration['algebra']=='latch' else 'NOT_REQUESTED'}


def record(store,project,name,data,parent=None):
    out=store.record(project,'qa_source',name,canonical(data),'hypothesis',parent_id=parent,request_key=project+':'+name)
    with store._connect() as c:return dict(c.execute('SELECT * FROM events WHERE id=?',(out['id'],)).fetchone())


class Acceptance:
    def __init__(self,baseline,output):
        self.base,self.out=baseline,output;output.mkdir(parents=True,exist_ok=False)
        self.private=baseline/output.name;self.workspace=self.private/'workspace';self.workspace.mkdir(parents=True,mode=0o700)
        self.seals=self.private/'seals';self.seals.mkdir(mode=0o700)
        self.db=self.workspace/'research.sqlite3';self.checks=[];self.trace=[];self.receipts=[];self.sources={};self.gates={};self.predictions=[]
        self.policy=json.loads((baseline/'source-freeze.json').read_text())['policy']
        self.declarations=json.loads((baseline/'frozen-inputs/sources.json').read_text())
        self.start=time.perf_counter_ns();self.cpu=time.process_time_ns()
        self.before_original=snapshot(baseline/'canonical.sqlite3')
        with sqlite3.connect((baseline/'canonical.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(self.db) as dst:src.backup(dst)
        self.db.chmod(0o600)
        install011(self.db,json.loads((baseline/'metadata.json').read_text())['canonical']);install_guards(self.db)
        shutil.copy2(baseline/'source-freeze.json',output/'source-freeze.json')
        shutil.copytree(baseline/'frozen-inputs',output/'frozen-inputs')
        frozen=output/'sources';frozen.mkdir()
        for path in SOURCE.glob('law_validation014*.py'):shutil.copy2(path,frozen/path.name)
        shutil.copy2(SOURCE/'test_law_validation014.py',frozen/'test_law_validation014.py')
        write_json(output/'source-hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen.iterdir()})

    def check(self,name,ok,evidence=None):
        row={'invariant':name,'result':'PASS' if ok else 'FAIL','evidence':evidence};self.checks.append(row)
        write_json(self.out/'checks.json',self.checks)
        if not ok:
            write_json(self.out/'first-failure.json',row);raise ValueError(name)

    def seed(self,declaration):
        key=declaration['id'];project='LM_QA_TYPED011_LV014_'+self.out.name[-12:]+'_'+key;scoped='QA014/'+project
        store=ResearchStore(self.db);observed=acquisition(declaration)
        write_json(self.out/('discovery-'+key+'.json'),observed)
        environment={'project':project,'declaration':declaration,'target_word':self.policy['hidden_targets'].get(key,[]),
                     'salt':os.urandom(24).hex()}
        seal=self.seals/(key+'.json');seal.write_text(canonical(environment));seal.chmod(0o600)
        identity=digest({'source':declaration,'scope':scoped})
        operator_fixture=record(store,project,'operator-fixture',{'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,
            'fixture_sha256':identity,'environment_commitment':hashlib.sha256(seal.read_bytes()).hexdigest()})
        source=record(store,project,'native-source',{'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,'declaration':declaration,'native_sha':native_sha()})
        observations=record(store,project,'observations',{'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,
            **{k:observed[k] for k in ('origin','transitions','executed_words')}},source['id'])
        actions=['a'+str(i) for i in range(declaration['arity'])];words={};hypotheses=[]
        for index,w in enumerate(declaration['discrimination_histories']):
            word=[actions[a] for a in w];row=record(store,project,'h'+str(index),{'claim_type':'HYPOTHESIS','scope':scoped,'version':1,'word':word},source['id'])
            ref='event:'+str(row['id']);words[ref]=word
            hypotheses.append({'id':ref,'ref':ref,'weight':1,'predictive':True,'question':'current','depends_on':[]})
        ind=record(store,project,'independent',{'claim_type':'HYPOTHESIS','scope':'independent','version':1,'word':[]},source['id'])
        iref='event:'+str(ind['id']);words[iref]=[];hypotheses.append({'id':'IND','ref':iref,'weight':1,'predictive':False,'question':'independent','depends_on':[]})
        tests=[{'id':'t'+str(i),'ordinal':i,'suffix':list(w),'cost':len(w)-1} for i,w in enumerate([w for n in (1,2) for w in product(actions,repeat=n)])]
        domain=[{'id':'v'+str(i),'ordinal':i,'word':word,'cost':len(word)} for i,word in enumerate(self.policy['validation_domain'])]
        spec={'parameters':{**declaration,'actions':actions},'histories':list(words)[:-1],'independent_ref':iref,'tests':tests,
            'validation_domain':domain,'hypotheses':hypotheses,'current_observation':0,'known_failures':[],
            'unknowns':['Finite empirical transfer, not universal truth.'],'observer':OBSERVER,'scope':scoped,'version':1,'primitive_sha256':native_sha()}
        root=record(store,project,'root',{'claim_type':'HYPOTHESIS','scope':scoped,'version':1,'source_event_id':source['id'],
            'observations_event_id':observations['id'],'source_spec':spec},source['id'])
        blueprint={'import_key':project+':allow','project':project,'sources':[{'id':operator_fixture['id'],'sha256':digest(operator_fixture)}],
            'obligations':[{'key':'law','statement':'Bounded source014 experiment only; separate discrimination and transfer validation.',
                'scope':scoped,'source_event_ids':[operator_fixture['id'],root['id']],'evidence_refs':['event:'+str(source['id'])]}],
            'constraints':[{'kind':'allowed_experiment','obligation_key':'law','mechanisms':[MECHANISM],'scope':scoped,
                'source_event_ids':[operator_fixture['id']],'source_representations':['fixture009:'+identity],
                'reason':'Only exact014 source, declared suffix, observer, guard and current operator-activated precommit.',
                'reopen_conditions':['Changed source/scope requires a new explicit operator review.']}]}
        imported=store.frontier.import_history(blueprint,'User-authorized isolated014 operator')
        artifact=self.workspace/'artifacts'/key;artifact.mkdir(parents=True)
        register_scope(self.db,project,{'scope':scoped,'fixture_id':operator_fixture['id'],'fixture_sha256':digest(operator_fixture),
            'fixture_content_sha256':identity,'source_family_id':digest({'native':native_sha(),'source_id':source['id']}),
            'operation_definition_sha256':digest(ordinal_parameters(spec['parameters'])),'native_definition_sha256':native_sha(),
            'executor_code_sha256':hashlib.sha256((SOURCE/'law_validation014_executor.py').read_bytes()).hexdigest(),
            'environment_sha256':hashlib.sha256(seal.read_bytes()).hexdigest(),'artifact_directory':str(artifact)})
        binding={'key':key,'project':project,'scope':scoped,'obligation_id':imported['obligation_ids']['law'],'version':1,
            'root_id':root['id'],'histories':[int(r.split(':')[1]) for r in spec['histories']],'environment':str(seal),'declaration':declaration,'domain':domain,'observed':observed}
        self.sources[key]=binding;return binding

    def request(self,b):
        with connect(self.db) as c:rows=[dict(r) for r in c.execute('SELECT * FROM events WHERE project=? ORDER BY id',(b['project'],))]
        return {'project':b['project'],'active_frontier_id':b['obligation_id'],'active_frontier_version':b['version'],
            'source_event_ids':[r['id'] for r in rows],'source_bindings':[{'event_id':r['id'],'sha256':digest(r)} for r in rows],
            'source_adapter_id':ADAPTER,'observer':OBSERVER,'question':{'root_event_id':b['root_id'],
                'left_history_id':b['histories'][0],'right_history_id':b['histories'][1],'mode':'constructive'}}

    async def call(self,client,name,args,readonly=False,allow_error=False):
        before=readonly_state(self.db);wall=time.perf_counter_ns();cpu=time.process_time_ns()
        reply=await client.call_tool(name,args);raw=reply.model_dump(mode='json')
        text=''.join(c.text for c in reply.content if c.type=='text')
        try:out=json.loads(text)
        except ValueError:out={'error':text}
        self.trace.append({'tool':name,'request':args,'response':raw,'driver_wall_ns':time.perf_counter_ns()-wall,'driver_CPU_ns':time.process_time_ns()-cpu})
        write_json(self.out/'mcp-transcript.json',self.trace)
        if readonly:self.check(name+':readonly:'+str(len(self.trace)),readonly_state(self.db)==before)
        if reply.isError and not allow_error:raise ValueError('MCP_ERROR:'+text)
        return out

    async def step(self,client,b,index,expected_purpose):
        req=self.request(b);preview=await self.call(client,'law_research_preview',{'request':req},True)
        self.check(b['key']+str(index)+':ready',preview['status']=='PROPOSAL_READY',preview)
        self.check(b['key']+str(index)+':purpose',preview['purpose']==expected_purpose)
        if expected_purpose=='VALIDATE_TRANSFER':
            self.check(b['key']+str(index)+':real_singleton',len(preview['alternatives'])==1 and preview['discrimination']['status']=='NO_INFORMATIVE_TEST')
            # Frozen scoring oracle evaluates only after the actual measurement below.
        self.check(b['key']+str(index)+':independent',all(h['status']=='ACTIVE' for h in preview['independent_branch']))
        self.check(b['key']+str(index)+':no_predictive_native_E',all(r['operation']!='E' for r in preview['native_trace']))
        pc=await self.call(client,'law_research_precommit',{'request':req,'request_key':'step'+str(index)})
        repeat_before=readonly_state(self.db);repeat=await self.call(client,'law_research_precommit',{'request':req,'request_key':'step'+str(index)})
        self.check(b['key']+str(index)+':precommit_idempotent',repeat==pc and readonly_state(self.db)==repeat_before)
        view=ResearchStore(self.db).moves.inspect(b['project'],pc['move_id'])
        self.check(b['key']+str(index)+':no_implicit_grant',not view['execution_permission']['allowed'])
        prediction={'source':b['key'],'step':index,'purpose':preview['purpose'],'proposal':pc,'prediction':preview,
                    'time':datetime.now(timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns()}
        append(self.out/'predictions-before-execution.jsonl',prediction);self.predictions.append(prediction)
        denied=subprocess.run([sys.executable,str(SOURCE/'law_validation014_executor.py'),'--db',str(self.db)],input=canonical(
            {'project':b['project'],'move_id':pc['move_id'],'environment_file':'/nonexistent/denied-before-open'}),text=True,capture_output=True,timeout=10)
        self.check(b['key']+str(index)+':executor_requires_activation',denied.returncode!=0 and 'NO_TYPED_ACTIVATION' in denied.stdout,denied.stdout)
        activation=activate(self.db,b['project'],pc['move_id'],b['key']+str(index))
        self.trace.append({'authority':'operator-local','action':'activate','response':activation})
        if b['key']=='A' and index==2:
            with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as original,sqlite3.connect(self.private/'unexecuted-control.sqlite3') as target:original.backup(target)
        measured=subprocess.run([sys.executable,str(SOURCE/'law_validation014_executor.py'),'--db',str(self.db)],input=canonical(
            {'project':b['project'],'move_id':pc['move_id'],'environment_file':b['environment']}),text=True,capture_output=True,timeout=10)
        try:value=json.loads(measured.stdout)
        except ValueError:raise ValueError('EXECUTOR_OUTPUT:'+measured.stdout+measured.stderr)
        self.check(b['key']+str(index)+':external_native',measured.returncode==0 and value.get('ok'),value)
        value=value['result'];env=value['envelope'];self.trace.append({'authority':'external-native014-process','response':value})
        shutil.copy2(value['artifact_path'],self.out/('instrument-'+b['key']+str(index)+'.json'))
        validated=await self.call(client,'law_research_validate',{'project':b['project'],'move_id':pc['move_id'],'event_id':value['event_id']},True)
        self.check(b['key']+str(index)+':strict_binding',validated['status']=='VALID_BOUND_MEASUREMENT',validated)
        if b['key']=='A' and index==2:
            from law_validation014_controls import active_controls
            controls=active_controls(self.db,b['project'],pc['move_id'],value['event_id'],self.private/'fault-controls',self.private/'unexecuted-control.sqlite3')
            write_json(self.out/'binding-controls.json',controls)
            self.check('active_binding_and_stale_controls',all(c['PASS'] for c in controls),controls)
        if self.receipts:
            wrong=await self.call(client,'law_research_validate',{'project':b['project'],'move_id':pc['move_id'],'event_id':self.receipts[0]['event_id']},True)
            self.check(b['key']+str(index)+':old_or_foreign_evidence_denied',wrong['status']!='VALID_BOUND_MEASUREMENT')
        receipt_req={'project':b['project'],'move_id':pc['move_id'],'event_id':value['event_id'],'request_key':'receipt'+str(index),
                     **{k:env[k] for k in ('outcome','observed','summary','reason','proof_status')}}
        receipt=commit(self.db,receipt_req);before=readonly_state(self.db);repeat=commit(self.db,receipt_req)
        self.check(b['key']+str(index)+':receipt_idempotent',repeat['idempotent'] and readonly_state(self.db)==before)
        self.check(b['key']+str(index)+':unverified_terminal',receipt['status']=='COMPLETED' and receipt['proof_status']=='unverified' and not receipt['execution_permission']['allowed'])
        self.trace.append({'authority':'operator-local','action':'commit','request':receipt_req,'response':receipt})
        row={'source':b['key'],'step':index,'purpose':env['purpose'],'event_id':value['event_id'],'receipt':receipt,
             'context_word':env['context_word'],'suffix_ordinals':env['suffix_ordinals'],'observed_coordinate':env['observed_coordinate']}
        self.receipts.append(row);append(self.out/'typed-receipts.jsonl',row)
        # Only now is the independent oracle opened/invoked by the evaluator process.
        from law_validation014_oracle import replay,rank_probes
        target=json.loads(Path(b['environment']).read_text())['target_word']
        raw,coordinate,steps=replay(b['declaration'],target+env['suffix_ordinals'])
        raw['admissibility']=raw['admissibility'][-len(env['suffix_ordinals']):]
        oracle={'source':b['key'],'step':index,'readout':raw,'coordinate':coordinate,'steps':steps,'origin':'post-measurement independent synthetic evaluator'}
        append(self.out/'oracle.jsonl',oracle)
        self.check(b['key']+str(index)+':independent_replay',env['observed']==raw and env['observed_coordinate']==coordinate,oracle)
        if expected_purpose=='VALIDATE_TRANSFER':
            previous=[r for r in self.receipts[:-1] if r['source']==b['key'] and r['purpose']=='VALIDATE_TRANSFER']
            seen={tuple(r['suffix_ordinals']) for r in previous};covered=[pair for r in previous for pair in zip(r['suffix_ordinals'],r['suffix_ordinals'][1:])]
            ranked=rank_probes(b['domain'],seen,covered)
            self.check(b['key']+str(index)+':independent_score',preview['selected_test']['test_id']==ranked[0],ranked)
            rng=random.Random(self.policy['random_seed']+index);random_choice=rng.choice([p for p in b['domain'] if tuple(p['word']) not in seen])
            append(self.out/'random-control.jsonl',{'source':b['key'],'step':index,'selected':random_choice,
                'same_domain_eligibility_budget':True,'readout':replay(b['declaration'],target+random_choice['word'])[0],
                'origin':'post-execution counterfactual control, not a committed external measurement'})
        write_json(self.out/'mcp-transcript.json',self.trace)
        return env,preview

    async def run(self):
        for declaration in self.declarations:self.seed(declaration)
        oracle_path=SOURCE/'law_validation014_oracle.py';seal=self.sources['A']['environment']
        params=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'law_validation014_server.py'),'--db',str(self.db),
            '--forbidden',str(oracle_path),'--forbidden',seal],env={**os.environ,'LM014_NATIVE_LEDGER':str(self.workspace/'native-meter.jsonl')})
        with (self.out/'server-stderr.txt').open('w') as errors:
            async with stdio_client(params,errlog=errors) as (read,write):
                async with ClientSession(Tap(read,self.out/'mcp-wire.jsonl','response'),Tap(write,self.out/'mcp-wire.jsonl','request')) as client:
                    init=(await client.initialize()).model_dump(mode='json');tools=(await client.list_tools()).model_dump(mode='json')
                    self.trace.append({'initialize':init,'tools':tools})
                    self.check('no_model_grant_commit_executor',{t['name'] for t in tools['tools']}=={'source_law_preview','law_research_preview','law_research_precommit','law_research_validate'})
                    law_previews={}
                    for key,b in self.sources.items():
                        out=await self.call(client,'source_law_preview',{'request':self.request(b)},True);law_previews[key]=out
                        self.check(key+':source_law_status',out['status']==('INSUFFICIENT_STATE' if key=='D' else 'CANDIDATE_TRANSPORT'),out)
                    self.check('C_partial_guard',all(p['prediction']['status']=='GUARD_INSUFFICIENT' for p in law_previews['C']['probes']))
                    self.check('D_no_opaque_data',self.sources['D']['observed']['opaque_image'] is None)
                    write_json(self.out/'law-candidates.json',law_previews)
                    for step,purpose in ((1,'DISCRIMINATE'),(2,'VALIDATE_TRANSFER'),(3,'VALIDATE_TRANSFER')):
                        env,_=await self.step(client,self.sources['A'],step,purpose)
                        if step>1:self.check('A'+str(step)+':stable_law',env['outcome']=='SUCCESS')
                    no_next=await self.call(client,'law_research_preview',{'request':self.request(self.sources['A'])},True)
                    self.check('A_honest_NO_NEXT_ACTION',no_next['status']=='NO_UNTESTED_GUARDED_PROBE',no_next)
                    bfirst,_=await self.step(client,self.sources['B'],1,'DISCRIMINATE');self.check('B_first_pass',bfirst['outcome']=='SUCCESS')
                    bsecond,_=await self.step(client,self.sources['B'],2,'VALIDATE_TRANSFER');self.check('B_falsified',bsecond['outcome']=='FAILURE')
                    review=await self.call(client,'law_research_preview',{'request':self.request(self.sources['B'])},True)
                    self.check('B_REQUIRES_REVIEW_no_guard_fabrication',review['status']=='REQUIRES_REVIEW' and not review['execution_permission']['allowed'],review)
                    before=readonly_state(self.db)
                    await self.call(client,'law_research_precommit',{'request':self.request(self.sources['B']),'request_key':'forbidden-after-failure'},allow_error=True)
                    self.check('B_no_new_move_after_refutation',readonly_state(self.db)==before)
                    for label,change in (
                        ('observer',lambda q:q.update(observer={'projection':'primary','mod':2})),
                        ('version',lambda q:q.update(active_frontier_version=2)),
                        ('foreign_history',lambda q:q['question'].update(left_history_id=self.sources['B']['histories'][0])),
                        ('C4',lambda q:q['question'].update(context_level='C4'))):
                        bad=self.request(self.sources['A']);change(bad)
                        denied=await self.call(client,'law_research_preview',{'request':bad},True)
                        self.check('MCP_'+label+'_denied',denied['status']=='INSUFFICIENT_CONTEXT',denied)
                    before=readonly_state(self.db)
                    await self.call(client,'law_research_preview',{'request':self.request(self.sources['A']),'grant':True},allow_error=True)
                    self.check('caller_grant_argument_denied',readonly_state(self.db)==before)
        shutil.copy2(self.workspace/'isolation.json',self.out/'isolation.json')
        shutil.copy2(self.workspace/'native-meter.jsonl',self.out/'native-meter.jsonl')
        self.check('five_actual_receipts',len(self.receipts)==5)
        self.gates={name:'PASS' for name in ('G0 SOURCE_FREEZE','G1 LAW_TRANSFER','G2 SINGLETON','G3 VALIDATION_ATTENTION','G4 TYPED','G5 FEEDBACK')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    base=args.baseline or Path(Path('/tmp/lm014_path').read_text().strip());stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=args.output or SOURCE.parent/'docs/qa/LM-LAW-VALIDATION-014'/stamp;runner=Acceptance(base,out)
    write_json(base/'current.json',{'output':str(out),'private':str(runner.private),'database':str(runner.db)})
    try:asyncio.run(runner.run());status='P0_PASS_REGRESSIONS_PENDING'
    except Exception as error:
        status='STOP_WITH_RCA';write_json(out/'exception.json',{'error':str(error),'traceback':traceback.format_exc()})
    write_json(out/'gates.json',runner.gates)
    write_json(out/'result.json',{'status':status,'checks':runner.checks,'receipts':len(runner.receipts),'proof_status':'unverified','production_deploy':False})
    write_json(out/'driver-costs.json',{'wall_ns':time.perf_counter_ns()-runner.start,'self_CPU_ns':time.process_time_ns()-runner.cpu})
    print(canonical({'status':status,'output':str(out),'receipts':len(runner.receipts)}))


if __name__=='__main__':main()
