"""Real private MCP013 typed acceptance with local011 operator authority."""
import argparse
import asyncio
import copy
from datetime import datetime,timezone
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical,digest
from normalization_regression import Tap
from native_preview008_qa import readonly_state
from qa_positive_acceptance import write_json,snapshot
from research_store import ResearchStore
from research_cycle009 import MECHANISM
from typed_cycle011 import TypedCycle,ordinal_parameters
from typed_cycle011_store import install,register_scope,connect
from typed_cycle011_operator import activate,commit
from operational013_native import definition_sha256
from operational013_cycle import ADAPTER
from operational013_qa import record,OBSERVER
from operational013_store import install_append_only

SOURCE=Path(__file__).resolve().parent


class Acceptance:
    def __init__(self,baseline,p0,attempt):
        self.base,self.p0,self.out=baseline,p0,attempt;attempt.mkdir(parents=True,exist_ok=False)
        self.checks=[];self.trace=[];self.cycles=[];self.scopes=[]
        config=json.loads((baseline/'current.json').read_text());self.db=baseline/('typed-'+attempt.name+'.sqlite3')
        with sqlite3.connect(Path(config['database']).as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(self.db) as dst:src.backup(dst)
        self.db.chmod(0o600);self.before=snapshot(self.db)
        self.metadata=json.loads((baseline/'metadata.json').read_text())
        install(self.db,self.metadata['canonical'])
        install_append_only(self.db)
        for filename in ('operational013_cycle.py','operational013_executor.py','operational013_cycle_server.py','operational013_cycle_qa.py'):
            shutil.copy2(SOURCE/filename,attempt/filename)

    def check(self,name,ok,data=None):
        row={'invariant':name,'result':'PASS' if ok else 'FAIL','evidence':data};self.checks.append(row)
        write_json(self.out/'checks.json',self.checks)
        if not ok:
            if not (self.out/'first-failure.json').exists():write_json(self.out/'first-failure.json',row)
            raise ValueError(name)

    def seed(self,key,tag='main'):
        acq=json.loads((self.p0/('acquisition-'+key+'.json')).read_text())
        declaration=next(d for d in json.loads((self.base/'frozen-inputs/discovery.json').read_text()) if d['id']==key)
        project='LM_QA_TYPED011_OP013_'+self.out.name[-12:]+'_'+key+'_'+tag;scoped='QA013/'+project
        store=ResearchStore(self.db)
        identity=digest({'declaration':declaration,'project':project,'scope':scoped})
        environment={'declaration':declaration,'project':project,'target_word':json.loads((self.base/'freeze.json').read_text())['policy']['typed_hidden_histories'][key],
                     'salt':hashlib.sha256((self.out.name+tag+key).encode()).hexdigest()}
        environment_file=self.base/(project+'-environment.json');environment_file.write_text(canonical(environment));environment_file.chmod(0o600)
        env_sha=hashlib.sha256(environment_file.read_bytes()).hexdigest()
        operator_fixture=record(store,project,'operator-fixture',{'claim_type':'SOURCE_CLAIM','statement':'Local operator environment commitment, never passed into law induction.',
             'scope':scoped,'version':1,'fixture_sha256':identity,'environment_commitment':env_sha})
        source=record(store,project,'source',{'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,'declaration':declaration,
             'native_definition_sha256':definition_sha256(),'statement':'Unsealed operational source; no hidden target or heldout fields.'})
        origin=next(t['before'] for t in acq['discovery'] if t['history']==[])
        observations=record(store,project,'observations',{'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,
             'origin':origin,'transitions':acq['discovery'],'provenance':'Frozen native discovery; source013 P0 verified, not external measurement.'},source['id'])
        words={};hypotheses=[]
        old=acq['source']
        for index,(ref,word) in enumerate(old['words'].items()):
            independent=index==len(old['words'])-1
            labels=['a'+str(a) for a in word]
            row=record(store,project,'independent' if independent else 'h'+str(index),{'claim_type':'HYPOTHESIS' if independent else 'SOURCE_CLAIM',
                'scope':'independent' if independent else scoped,'version':1,'word':labels},source['id'])
            newref='event:'+str(row['id']);words[newref]=labels
            hypotheses.append({'id':'IND' if independent else newref,'ref':newref,'weight':1,
                'predictive':not independent,'question':'independent' if independent else 'current','depends_on':[]})
        actions=['a'+str(i) for i in range(declaration['arity'])]
        tests=[{'id':'t'+str(i),'ordinal':i,'suffix':list(w),'cost':len(w)-1}
               for i,w in enumerate([w for n in (1,2) for w in product(actions,repeat=n)])]
        spec={'parameters':{**declaration,'actions':actions},'histories':list(words)[:-1],'independent_ref':list(words)[-1],
              'tests':tests,'observer':OBSERVER,'scope':scoped,'version':1,'primitive_sha256':definition_sha256(),
              'current_observation':0,'known_failures':[],'unknowns':['Transport is an empirical bounded law.'],
              'hypotheses':hypotheses}
        root=record(store,project,'root',{'claim_type':'HYPOTHESIS','scope':scoped,'version':1,'observer':OBSERVER,
              'native_definition_sha256':definition_sha256(),'fixture_event_id':source['id'],
              'observations_event_id':observations['id'],'source_spec':spec},source['id'])
        blueprint={'import_key':project+':constraint','project':project,'sources':[{'id':operator_fixture['id'],'sha256':digest(operator_fixture)}],
            'obligations':[{'key':'cycle','statement':'User-authorized bounded013 native measurement only.','scope':scoped,
                'source_event_ids':[operator_fixture['id'],root['id']],'evidence_refs':['event:'+str(operator_fixture['id'])]}],
            'constraints':[{'kind':'allowed_experiment','obligation_key':'cycle','mechanisms':[MECHANISM],
                'source_event_ids':[operator_fixture['id']],'source_representations':['fixture009:'+identity],'scope':scoped,
                'reason':'Only this exact013 QA fixture, source adapter, precommit and bounded suffix; no global experiment authority.',
                'reopen_conditions':['Changed native source or scope requires explicit new operator review.']}]}
        imported=store.frontier.import_history(blueprint,'User-authorized isolated013 QA operator')
        directory=self.base/(project+'-artifacts');directory.mkdir(mode=0o700)
        register_scope(self.db,project,{'scope':scoped,'fixture_id':operator_fixture['id'],'fixture_sha256':digest(operator_fixture),
            'fixture_content_sha256':identity,'source_family_id':digest({'native':definition_sha256(),'source':source['id'],'declaration':declaration}),
            'operation_definition_sha256':digest(ordinal_parameters(spec['parameters'])),'native_definition_sha256':definition_sha256(),
            'executor_code_sha256':hashlib.sha256((SOURCE/'operational013_executor.py').read_bytes()).hexdigest(),
            'environment_sha256':env_sha,'artifact_directory':str(directory)})
        result={'project':project,'scope':scoped,'obligation_id':imported['obligation_ids']['cycle'],'version':1,'root_id':root['id'],
                'left':int(spec['histories'][0].split(':')[1]),'right':int(spec['histories'][1].split(':')[1]),
                'environment_file':str(environment_file),'key':key}
        self.scopes.append(result);return result

    def request(self,b):
        with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as c:
            c.row_factory=sqlite3.Row;rows=[dict(r) for r in c.execute('SELECT * FROM events WHERE project=? ORDER BY id',(b['project'],))]
        return {'project':b['project'],'active_frontier_id':b['obligation_id'],'active_frontier_version':b['version'],
                'source_event_ids':[r['id'] for r in rows],'source_bindings':[{'event_id':r['id'],'sha256':digest(r)} for r in rows],
                'source_adapter_id':ADAPTER,'observer':OBSERVER,'question':{'root_event_id':b['root_id'],
                    'left_history_id':b['left'],'right_history_id':b['right'],'mode':'constructive'}}

    async def call(self,client,name,args,readonly=False):
        before=readonly_state(self.db)
        response=await client.call_tool(name,args)
        value=json.loads(''.join(c.text for c in response.content if c.type=='text'))
        self.trace.append({'tool':name,'request':args,'response':response.model_dump(mode='json')})
        write_json(self.out/'mcp-transcript.json',self.trace)
        if readonly:self.check(name+':readonly:'+str(len(self.trace)),readonly_state(self.db)==before)
        if response.isError:raise ValueError('MCP_ERROR:'+canonical(value))
        return value

    def local(self,action,request):
        before=readonly_state(self.db)
        if action=='activate':value=activate(self.db,**request)
        else:value=commit(self.db,request)
        self.trace.append({'authority':'operator-local-only','action':action,'request':request,'response':value,
                           'before':before,'after':readonly_state(self.db)})
        write_json(self.out/'mcp-transcript.json',self.trace);return value

    async def run(self):
        a,b,stale=[self.seed(k,tag) for k,tag in [('A','main'),('B','main'),('A','stale')]]
        parameters=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'operational013_cycle_server.py'),'--db',str(self.db)],
            env={**os.environ,'LM013_COST_LEDGER':str(self.out/'native-costs.jsonl')})
        with (self.out/'server-stderr.txt').open('w') as errors:
            async with stdio_client(parameters,errlog=errors) as (read,write):
                async with ClientSession(Tap(read,self.out/'mcp-wire.jsonl','response'),Tap(write,self.out/'mcp-wire.jsonl','request')) as client:
                    init=(await client.initialize()).model_dump(mode='json');tools=(await client.list_tools()).model_dump(mode='json')
                    self.trace.append({'initialize':init,'tools':tools})
                    self.check('private_tools_no_activation_commit_executor',{t['name'] for t in tools['tools']}==
                               {'operational_cycle_preview','operational_cycle_precommit','operational_cycle_validate'})
                    for binding in (a,b):
                        for iteration in (1,2):
                            req=self.request(binding);preview=await self.call(client,'operational_cycle_preview',{'request':req},True)
                            self.check(binding['key']+str(iteration)+':source_forecast',preview['status']=='NEW_DISTINCTION',preview)
                            self.check(binding['key']+str(iteration)+':independent_branch',any(h['status']=='ACTIVE' for h in preview['independent_branch']))
                            self.check(binding['key']+str(iteration)+':no_I_optimal_test',preview['I_supplies_optimal_test_id'] is False)
                            self.check(binding['key']+str(iteration)+':no_native_E_in_I_T',not any(r['operation']=='E' for r in preview['native_trace']))
                            pc=await self.call(client,'operational_cycle_precommit',{'request':req,'request_key':'main-'+str(iteration)})
                            before=readonly_state(self.db)
                            repeat=await self.call(client,'operational_cycle_precommit',{'request':req,'request_key':'main-'+str(iteration)})
                            self.check(binding['key']+str(iteration)+':precommit_idempotent',pc==repeat and readonly_state(self.db)==before)
                            move=ResearchStore(self.db).moves.inspect(binding['project'],pc['move_id'])
                            self.check(binding['key']+str(iteration)+':precommit_no_grant',not move['execution_permission']['allowed'])
                            activation=self.local('activate',{'project':binding['project'],'move_id':pc['move_id'],'request_key':binding['key']+str(iteration)})
                            execution=subprocess.run([sys.executable,str(SOURCE/'operational013_executor.py'),'--db',str(self.db)],
                                input=canonical({'project':binding['project'],'move_id':pc['move_id'],'environment_file':binding['environment_file']}),
                                text=True,capture_output=True,timeout=12)
                            result=json.loads(execution.stdout);self.trace.append({'authority':'external-native013-process','request':{'move_id':pc['move_id']},'response':result})
                            self.check(binding['key']+str(iteration)+':external_execution',execution.returncode==0 and result['ok'],result)
                            measured=result['result'];env=measured['envelope']
                            shutil.copy2(measured['artifact_path'],self.out/('measurement-'+binding['key']+str(iteration)+'.json'))
                            validated=await self.call(client,'operational_cycle_validate',{'project':binding['project'],'move_id':pc['move_id'],'event_id':measured['event_id']},True)
                            self.check(binding['key']+str(iteration)+':exact_bound_measurement',validated['status']=='VALID_BOUND_MEASUREMENT',validated)
                            if iteration==2:
                                wrong=await self.call(client,'operational_cycle_validate',{'project':binding['project'],'move_id':pc['move_id'],
                                    'event_id':self.cycles[-1]['event_id']},True)
                                self.check(binding['key']+':old_event_refused',wrong['status']!='VALID_BOUND_MEASUREMENT')
                            receipt_req={'project':binding['project'],'move_id':pc['move_id'],'event_id':measured['event_id'],
                                'request_key':'commit-'+str(iteration),**{k:env[k] for k in ('outcome','observed','summary','reason','proof_status')}}
                            receipt=self.local('commit',receipt_req)
                            self.check(binding['key']+str(iteration)+':terminal_unverified',receipt['status']=='COMPLETED' and receipt['proof_status']=='unverified' and not receipt['execution_permission']['allowed'])
                            before=readonly_state(self.db);repeat_receipt=self.local('commit',receipt_req)
                            self.check(binding['key']+str(iteration)+':receipt_idempotent',repeat_receipt['idempotent'] and readonly_state(self.db)==before)
                            try:activate(self.db,binding['project'],pc['move_id'],'reactivate');denied=False
                            except ValueError:denied=True
                            self.check(binding['key']+str(iteration)+':reactivation_denied',denied)
                            self.cycles.append({'source':binding['key'],'iteration':iteration,'precommit':pc,'activation':activation,
                                               'event_id':measured['event_id'],'receipt':receipt,'preview':preview})
                    # Independent stale-version canary; it never executes or fabricates a result.
                    req=self.request(stale);pc=await self.call(client,'operational_cycle_precommit',{'request':req,'request_key':'stale'})
                    self.local('activate',{'project':stale['project'],'move_id':pc['move_id'],'request_key':'stale'})
                    store=ResearchStore(self.db)
                    store.frontier.update(stale['obligation_id'],1,{'statement':'Version2 requires fresh source applicability and audit.'})
                    view=store.moves.inspect(stale['project'],pc['move_id'])
                    self.check('stale_version_revokes_grant',not view['execution_permission']['allowed'] and view['status']=='REQUIRES_REVIEW',view['status'])
                    execution=subprocess.run([sys.executable,str(SOURCE/'operational013_executor.py'),'--db',str(self.db)],
                        input=canonical({'project':stale['project'],'move_id':pc['move_id'],'environment_file':'/nonexistent/must-not-be-opened'}),text=True,capture_output=True,timeout=12)
                    self.check('stale_executor_checks_before_environment',execution.returncode!=0 and 'STALE_OBLIGATION_VERSION' in execution.stdout,execution.stdout)
                    store.moves.transition(stale['project'],pc['move_id'],'abandon','abandon-stale',reason='Stale canary intentionally abandoned.')
        self.check('two_source_linked_iterations_per_family',CounterLike(self.cycles)=={'A':2,'B':2})
        self.check('fresh_negative_then_positive',all([c['receipt']['outcome'] for c in self.cycles if c['source']==k]==['FAILURE','SUCCESS'] for k in ('A','B')),
                   [{'source':c['source'],'iteration':c['iteration'],'outcome':c['receipt']['outcome']} for c in self.cycles])
        for binding in self.scopes:
            store=ResearchStore(self.db)
            version=2 if binding is stale else 1
            store.frontier.update(binding['obligation_id'],version,{'status':'RESOLVED','closure_reason':'Synthetic013 acceptance complete; not mathematical verification.',
                'reopen_conditions':['New source evidence and explicit operator review are required.']})
        with connect(self.db) as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project LIKE ?',('LM_QA_TYPED011_OP013_%',))]
            reader=ResearchStore.__new__(ResearchStore);reader.path=self.db
            self.check('no_active_QA_grants',not any(reader.moves._view(c,r)['execution_permission']['allowed'] for r in rows))
            journals=[dict(r) for r in c.execute('SELECT * FROM typed011_journal')]
        write_json(self.out/'novelty-journal.json',journals)
        write_json(self.out/'cycles.json',self.cycles)
        after=snapshot(self.db)
        preserved={name:after['tables'][name][:len(rows)]==rows for name,rows in self.before['tables'].items()}
        self.check('all_original_rows_preserved',all(preserved.values()),preserved)
        write_json(self.out/'metadata.json',{'database':str(self.db),'scopes':self.scopes,'original_prefix_rows':{k:len(v) for k,v in self.before['tables'].items()}})


def CounterLike(cycles):
    from collections import Counter
    return dict(Counter(c['source'] for c in cycles))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path);args=parser.parse_args()
    base=args.baseline or Path(Path('/tmp/lm013_path').read_text().strip());config=json.loads((base/'current.json').read_text());p0=Path(config['output'])
    p0_receipt=p0/'P0-result.json' if (p0/'P0-result.json').exists() else p0/'result.json'
    if json.loads(p0_receipt.read_text())['status']!='P0_PASS_TYPED_PENDING':raise SystemExit('P0_GATE_NOT_PASSED')
    attempt=p0/('typed-'+datetime.now(timezone.utc).strftime('%H%M%S%f'))
    runner=Acceptance(base,p0,attempt)
    try:asyncio.run(runner.run());status='PASS_TYPED013_BOUNDED'
    except Exception as error:
        status='STOP_WITH_RCA';write_json(attempt/'exception.json',{'error':str(error),'traceback':__import__('traceback').format_exc()})
    write_json(attempt/'result.json',{'status':status,'checks':runner.checks,'proof_status':'unverified'})
    write_json(base/'typed-current.json',{'attempt':str(attempt),'database':str(runner.db),'status':status})
    print(canonical({'status':status,'attempt':str(attempt)}))


if __name__=='__main__':main()
