"""Fresh frozen011 acceptance. Production is read-only; all experiments use a private clone."""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical, digest, read_history
from native_preview008_qa import readonly_state
from native_preview008_server import MeasuredProcess
from normalization_regression import Tap, run_regression
from qa_positive_acceptance import write_json, snapshot
from research_store import ResearchStore
from research_cycle009_runtime import Cycle, append
from research_cycle009 import requests, event_rows, survivors, selected_claim, material, validate_witness, qa_closure_changes
from research_cycle009_worlds import declarations, environments, checksum
from research_cycle009_oracle import sequence, rank
from live_constructive007_native import native_fingerprint
from typed_cycle011 import TypedCycle, ordinal_parameters
from typed_cycle011_store import install, register_scope, connect

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Acceptance(Cycle):
    def __init__(self,base,db,canonical_db):
        super().__init__(base,db,canonical_db);self.gates={'G0':'PASS'};self.negatives=[]

    async def call(self,name,arguments,allow_error=False):
        readonly=name in {'research_cycle_validate','research_novelty_snapshot'}
        before=readonly_state(self.db) if readonly else None
        value=await super().call(name,arguments,allow_error)
        append(self.base/'database-routing.jsonl',{'call':len(self.calls),'database':self.db.name})
        if readonly:self.check('call:'+str(len(self.calls))+':SELECT_only',before==readonly_state(self.db))
        return value

    async def session(self,label,work,script=None):
        folder=self.base/'sessions'/label;folder.mkdir(parents=True,exist_ok=False)
        params=StdioServerParameters(command=sys.executable,args=[str(script or SOURCE/'typed_cycle011_server.py'),'--db',str(self.db)],env={**os.environ,'LIVE_MATH_NATIVE_PREVIEW':'1','PYTHONPATH':str(SOURCE)})
        with (folder/'stderr.txt').open('w') as error:
            async with stdio_client(params,errlog=error) as (read,write):
                async with ClientSession(Tap(read,folder/'wire.jsonl','response'),Tap(write,folder/'wire.jsonl','request')) as client:
                    self.client=client;initialized=await client.initialize();tools=(await client.list_tools()).model_dump(mode='json')
                    write_json(folder/'tools-list.json',{'initialize':initialized.model_dump(mode='json'),**tools})
                    names={t['name'] for t in tools['tools']}
                    self.check(label+':operator_tools_absent',not names&{'activate','commit','transition_research_move','audit_research_move','record_research_move'})
                    await work()

    def local(self,action,data,allow_error=False):
        script='typed_cycle011_executor.py' if action=='execute' else 'typed_cycle011_operator.py'
        args=[sys.executable,str(SOURCE/script),'--db',str(self.db)]+([] if action=='execute' else [action])
        before=readonly_state(self.db);start=time.perf_counter_ns()
        process=MeasuredProcess(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:out,err=process.communicate(canonical(data).encode(),timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.communicate();raise
        value=json.loads(out) if out else {'ok':False,'error':err.decode()}
        usage=process.child_usage
        row={'action':action,'request':data,'response':value,'returncode':process.returncode,
            'wall_ns':time.perf_counter_ns()-start,'CPU_ns':round((usage.ru_utime+usage.ru_stime)*1e9),'peak_RSS_KiB':usage.ru_maxrss,
            'before':before,'after':readonly_state(self.db)}
        append(self.base/'operator-ledger.jsonl',row)
        if not value['ok']:
            self.check('operator denial:'+action+':no_DB_delta',row['before']==row['after'])
            if not allow_error:raise RuntimeError(value['error'])
            return None
        return value['result']

    async def seed(self,world,environment_hash):
        binding=await super().seed(world,environment_hash)
        fixture=event_rows(self.db,world['project'])[binding['fixture_id']]
        directory=self.base/'measurement-artifacts'/world['id'];directory.mkdir(parents=True,exist_ok=True)
        register_scope(self.db,world['project'],{'scope':world['scope'],'fixture_id':fixture['id'],
            'fixture_sha256':digest(fixture),'fixture_content_sha256':world['fixture_sha256'],
            'source_family_id':digest({'fixture_id':fixture['id'],'sha256':digest(fixture)}),
            'operation_definition_sha256':digest(ordinal_parameters(world['parameters'])),
            'native_definition_sha256':native_fingerprint(),'executor_code_sha256':sha(SOURCE/'typed_cycle011_executor.py'),
            'environment_sha256':environment_hash,'artifact_directory':str(directory)})
        return binding

    async def seed_projection(self,world,*args,**kwargs):
        declared=copy.deepcopy(world);declared['id']=world['parameters']['family']
        return await super().seed_projection(declared,*args,**kwargs)

    async def preview(self,world,binding,label,feedback_id=None,expected=None):
        _,native=requests(self.db,world,binding,feedback_id)
        out=await self.call('research_cycle_preview',{'request':native})
        self.check(label+':bounded_source_preview',out['status'] in {'NEW_DISTINCTION','NO_NEW_DISTINCTION_BOUNDED','UNKNOWN_BOUNDED'},out.get('reason'))
        from live_constructive007_oracle import run
        validate_witness(world,binding,out,run)
        oracle=rank(world,binding['active']) if expected is None else expected
        self.check(label+':independent_T',out['attention']['status']==oracle['status'] and out['attention'].get('test_id')==oracle['test_id'])
        if oracle['ranking']:
            keys=list(oracle['ranking'][0]);self.check(label+':exact_fraction_ranking',[{k:r[k] for k in keys} for r in out['attention']['ranking']]==oracle['ranking'])
        self.costs.append({'label':label,**{k:out[k] for k in ('cold_wall_ns','child_cpu_ns','child_peak_rss_KiB','cost_ledger','primitive_calls','source_serialization','source_snapshot_wall_ns','source_lookup_wall_ns') if k in out},
            'normalization':{k:out['normalization'][k] for k in ('cold_wall_ns','child_cpu_ns','child_peak_rss_KiB','source_serialization') if k in out['normalization']}})
        append(self.base/'costs.jsonl',self.costs[-1])
        write_json(self.base/(label+'-preview.json'),out)
        offline=TypedCycle(self.db).preview(native)
        # Timings and OS process accounting differ; all witnesses, guards, source and T remain comparable.
        for key in ('status','witness','attention','claim_fingerprint','raw_distinction_sha256','authoritative_novelty'):
            self.check(label+':offline_MCP:'+key,material(out[key])==material(offline[key]))
        return native,out

    async def precommit(self,world,binding,label,feedback=None,mode=None):
        _,native=requests(self.db,world,binding,feedback)
        if mode:native['question']['mode']=mode
        args={'request':native,'request_key':label}
        record=await self.call('research_cycle_precommit',args)
        self.check(label+':no_autogrant',record['execution_permission']=={'allowed':False})
        before=readonly_state(self.db);repeat=await self.call('research_cycle_precommit',args)
        self.check(label+':precommit_idempotent',record==repeat and before==readonly_state(self.db))
        self.moves.append((world['project'],record['move_id']))
        return record

    def activate(self,world,record,label):
        return self.local('activate',{'project':world['project'],'move_id':record['move_id'],'request_key':label})

    def measure(self,world,record,force=None):
        data={'project':world['project'],'move_id':record['move_id'],'world_file':str(self.base/'world-inputs'/(world['id']+'.json')),
            'environment_file':str(self.base/'sealed-environments'/(world['id']+'.json'))}
        if force:data['instrument_outcome']=force
        return self.local('execute',data)

    async def negative_binding(self,world,record,measured,binding):
        env=measured['envelope'];base=event_rows(self.db,world['project'])[measured['event_id']]
        for field in ('move_id','audit_id','activation_operation_id','obligation_version','scope','test_id','observer','suffix','source_bindings','native_definition_sha256','executor_id','artifact_sha256','outcome'):
            content=json.loads(base['content']);b=content['measurement_binding']
            if field in {'move_id','audit_id','activation_operation_id','obligation_version'}:b[field]+=1
            elif field=='observer':b[field]['mod']=2
            elif field=='suffix':b[field]=['invalid_ordinal_a','invalid_ordinal_b']
            elif field=='source_bindings':b[field][0]['sha256']='0'*64
            elif field in {'native_definition_sha256','artifact_sha256'}:b[field]='0'*64
            elif field=='outcome':b[field]='SUCCESS' if b[field]=='FAILURE' else 'FAILURE'
            else:b[field]='forged-'+str(b[field])
            event=await self.event(world,'negative:'+str(record['move_id'])+':'+field,content,kind='experiment',status='experiment',parent=binding['root_id'])
            out=await self.call('research_cycle_validate',{'project':world['project'],'move_id':record['move_id'],'event_id':event['id']})
            self.check('binding:'+field,out['status'] in {'REJECTED','INSUFFICIENT_MEASUREMENT_BINDING'} and not out['execution_permission']['allowed'],out['reason'])
            self.negatives.append({'case':field,'event_id':event['id'],'response':out})
        for label,project,event_id in [('premise',world['project'],binding['fixture_id']),('foreign','LM_QA_TYPED011_FOREIGN',measured['event_id'])]:
            out=await self.call('research_cycle_validate',{'project':project,'move_id':record['move_id'],'event_id':event_id})
            self.check(label+':fail_closed',out['status'] in {'REJECTED','INSUFFICIENT_MEASUREMENT_BINDING'})
            self.negatives.append({'case':label,'response':out})
        artifact=Path(measured['artifact_path']);held=artifact.with_suffix('.held');artifact.rename(held)
        try:
            response=await self.call('research_cycle_validate',{'project':world['project'],'move_id':record['move_id'],'event_id':measured['event_id']},allow_error=True)
            self.check('missing_artifact:fail_closed',response is None or response['status']=='REJECTED')
        finally:held.rename(artifact)

    async def finish(self,world,record,measured,label):
        validation=await self.call('research_cycle_validate',{'project':world['project'],'move_id':record['move_id'],'event_id':measured['event_id']})
        self.check(label+':fresh_binding',validation['status']=='VALID_BOUND_MEASUREMENT',validation.get('reason'))
        self.gates['G1']='PASS';self.gates['G2']='PASS'
        if not self.ledger:
            original_db,original_client=self.db,self.client;negative_db=self.base/'binding-negative-controls.sqlite3'
            with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(negative_db) as dst:src.backup(dst)
            async def negative_work():await self.negative_binding(world,record,measured,self.current_binding)
            try:
                self.db=negative_db;await self.session('binding-negative-controls',negative_work)
                store=ResearchStore(negative_db)
                with connect(negative_db) as c:
                    active=[(r['project'],r['id']) for r in c.execute("SELECT m.* FROM research_moves m JOIN research_move_status_history h ON h.move_id=m.id WHERE m.project LIKE 'LM_QA_TYPED011_%' AND h.status='EXPERIMENT_ALLOWED' AND h.sequence=(SELECT max(sequence) FROM research_move_status_history s WHERE s.move_id=m.id)")]
                for project,move_id in active:store.moves.transition(project,move_id,'abandon','negative-fixture-cleanup:'+str(move_id),reason='Isolated fault-injection fixture ended; no execution.')
            finally:self.db,self.client=original_db,original_client
        e=measured['envelope'];request={'project':world['project'],'move_id':record['move_id'],'event_id':measured['event_id'],
            'request_key':label,'outcome':e['outcome'],'observed':e['observed'],'summary':e['summary'],'reason':e['reason']}
        wrong={**request,'observed':{**e['observed'],'observation':'forged'}}
        self.check(label+':result_conflict_rejected',self.local('commit',wrong,True) is None)
        receipt=self.local('commit',request)
        self.check(label+':terminal_no_grant',receipt['status']=='COMPLETED' and receipt['proof_status']=='unverified' and receipt['execution_permission']=={'allowed':False})
        before=readonly_state(self.db)
        self.check(label+':receipt_repeat',self.local('commit',request)['idempotent'] and readonly_state(self.db)==before)
        self.check(label+':receipt_newkey_no_second_result',self.local('commit',{**request,'request_key':label+':alias'})['receipt_id']==receipt['receipt_id'] and readonly_state(self.db)==before)
        self.check(label+':key_tamper_denied',self.local('commit',wrong,True) is None)
        self.check(label+':terminal_reactivation_denied',self.local('activate',{'project':world['project'],'move_id':record['move_id'],'request_key':label+':terminal'},True) is None)
        row={'world':world['id'],'move_id':record['move_id'],'precommit_id':record['precommit_id'],
            'audit_id':receipt['audit_id'],'activation_operation_id':receipt['activation_operation_id'],'event_id':measured['event_id'],
            'receipt_id':receipt['receipt_id'],'outcome':receipt['outcome'],'version':e['obligation_version'],
            'precommit_sha256':record['precommit_sha256'],'event_sha256':receipt['event_sha256'],'scope':e['scope']}
        self.ledger.append(row);append(self.base/'lifecycle-ledger.jsonl',row)
        self.gates['G3']='PASS'
        return receipt

    async def run_world(self,world,oracle,control=None):
        async def work():
            env=self.base/'sealed-environments'/(world['id']+'.json');binding=await self.seed(world,sha(env));original=event_rows(self.db,world['project'])
            native,first=await self.preview(world,binding,world['id']+'-step1')
            record=await self.precommit(world,binding,world['id']+':step1')
            self.current_binding=binding
            # No audit/activation permission is conveyed by source precommit.
            denied=self.local('execute',{'project':world['project'],'move_id':record['move_id'],
                'world_file':'/not-opened','environment_file':'/not-opened'},True)
            self.check(world['id']+':sealed_not_opened_before_activation',denied is None)
            canary=None
            if not control:
                canary=await self.precommit(world,binding,world['id']+':canary',mode='bounded')
                self.activate(world,canary,world['id']+':canary')
            self.activate(world,record,world['id']+':step1')
            measured=self.measure(world,record,control)
            receipt=await self.finish(world,record,measured,world['id']+':step1')
            if control:
                self.check(control+':preserved',receipt['outcome']==control)
                await self.call('research_obligation_update',{'project':world['project'],'obligation_id':binding['obligation_id'],
                    'expected_version':1,'changes':qa_closure_changes(measured['event_id'])})
                return
            self.check(world['id']+':first_FAILURE',measured['envelope']['outcome']=='FAILURE')
            if world['id']=='affine':
                old_source=Path(json.loads((self.base/'metadata.json').read_text())['baseline'])/'cohorts/20261027T080448862969Z/frozen-sources'
                if old_source.exists():
                    original_client=self.client;_,repro_req=requests(self.db,world,binding);captured={}
                    async def old_work():
                        captured['old_response']=await self.call('research_cycle_preview',{'request':repro_req})
                    try:await self.session('old-feedback-reproducer',old_work,old_source/'typed_cycle011_server.py')
                    finally:self.client=original_client
                    captured['new_response']=await self.call('research_cycle_preview',{'request':repro_req})
                    captured.update(classification='SOURCE_CONTRACT_BUG',old_result='FAIL',new_result='PASS',request=repro_req,
                        old_source_sha256=sha(old_source/'typed_cycle011.py'),old_cohort='20261027T080448862969Z',
                        cause='Old server used caller-selected feedback; omitted latest committed negative observation left stale T. New server resolves current journal feedback itself.')
                    write_json(self.base/'feedback-RCA-reproducer.json',captured)
                    self.check('server-owned feedback fixes reproduced old stale_T',captured['old_response']['attention']['test_id']!=captured['new_response']['attention']['test_id'])
            # Refresh immutable source refs; an omitted/empty caller registry is never authoritative.
            for known in (None,[]):
                _,again=requests(self.db,world,binding)
                if known is not None:again['question']['known_fingerprints']=known
                replay=await self.call('research_cycle_preview',{'request':again})
                self.check(world['id']+':authoritative_repeat',replay['status']=='NO_NEW_DISTINCTION_BOUNDED')
            active=survivors(first['attention'],measured['envelope']['observed'])
            test1=first['attention']['test_id']
            # An unexecuted, separately bound old-version action must lose permission on advance.
            previous=binding
            binding=await self.seed_projection(world,binding,active,2,previous,
                [{'event_ref':'event:'+str(measured['event_id']),'excluded_guard_ids':sorted(set(binding['active'])-set(active)),
                  'scope':world['scope'],'not_universal_refutation':True}])
            obsv={k:measured['envelope'][k] for k in ('test_id','scope','observer')};obsv.update(readout=measured['envelope']['observed'],version=2)
            feedback=await self.event(world,'v2-negative-projection',{'claim_type':'COUNTEREXAMPLE','statement':'Derived version projection, not a new measurement.',
                'observation':obsv,'scope':world['scope'],'version':2,'relations':[{'type':'derived_from','target_ref':'event:'+str(measured['event_id'])}]},
                kind='counterexample',status='experiment',parent=measured['event_id'])
            await self.call('research_obligation_update',{'project':world['project'],'obligation_id':binding['obligation_id'],'expected_version':1,
                'changes':{'status':'TESTING','source_event_ids':[binding['fixture_id'],binding['root_id'],measured['event_id']],
                    'evidence_refs':['event:'+str(measured['event_id'])]}})
            stale=await self.call('research_move_history',{'project':world['project'],'move_id':canary['move_id']})
            self.check(world['id']+':version_revokes',stale['status']=='REQUIRES_REVIEW' and not stale['execution_permission']['allowed'])
            self.check(world['id']+':stale_activation_denied',self.local('activate',{'project':world['project'],'move_id':canary['move_id'],'request_key':'stale'},True) is None)
            self.check(world['id']+':stale_executor_denied',self.local('execute',{'project':world['project'],'move_id':canary['move_id'],'world_file':'/not-opened','environment_file':'/not-opened'},True) is None)
            ResearchStore(self.db).moves.transition(world['project'],canary['move_id'],'abandon','typed011:cleanup:'+world['id'],reason='Unexecuted grant revoked by version advance.')
            _,second=await self.preview(world,binding,world['id']+'-step2',feedback['id'])
            self.check(world['id']+':T_changed',second['attention']['test_id']!=test1)
            record2=await self.precommit(world,binding,world['id']+':step2',feedback['id']);self.current_binding=binding
            view=await self.call('research_move_history',{'project':world['project'],'move_id':record2['move_id']})
            self.check(world['id']+':adverse_requires_operator_review',view['status']=='REQUIRES_REVIEW')
            self.activate(world,record2,world['id']+':step2')
            measured2=self.measure(world,record2);await self.finish(world,record2,measured2,world['id']+':step2')
            remaining=survivors(second['attention'],measured2['envelope']['observed'])
            self.check(world['id']+':oracle_two_steps',test1==oracle['steps'][0]['attention']['test_id'] and
                second['attention']['test_id']==oracle['steps'][1]['attention']['test_id'] and
                measured['envelope']['observed']==oracle['steps'][0]['measurement'] and measured2['envelope']['observed']==oracle['steps'][1]['measurement'])
            self.check(world['id']+':second_SUCCESS_one_candidate',measured2['envelope']['outcome']=='SUCCESS' and len(remaining)==1)
            hyp=second['attention']['hypotheses'];self.check(world['id']+':independent_survives',next(h for h in hyp if h['id']=='IND')['status']=='ACTIVE')
            self.check(world['id']+':original_sources_retained',all(event_rows(self.db,world['project'])[i]==e for i,e in original.items()))
            #006 consumes counterexample sources: this is a scoped exclusion of the other guard,
            # derived from SUCCESS measurement, explicitly not another external observation.
            observed2={'test_id':measured2['envelope']['test_id'],'readout':measured2['envelope']['observed'],
                'scope':world['scope'],'version':2,'observer':world['observer']}
            final_feedback=await self.event(world,'v2-final-guard-exclusion',{'claim_type':'COUNTEREXAMPLE',
                'statement':'Scoped counterexample to the other finite guard, derived from committed SUCCESS; not a new measurement.',
                'scope':world['scope'],'version':2,'observation':observed2,
                'relations':[{'type':'derived_from','target_ref':'event:'+str(measured2['event_id'])}]},kind='counterexample',status='experiment',parent=measured2['event_id'])
            final_version=await self.extra_controls(world,binding,second,final_feedback['id'])
            await self.call('research_obligation_update',{'project':world['project'],'obligation_id':binding['obligation_id'],'expected_version':final_version,'changes':qa_closure_changes(measured2['event_id'])})
        await self.session(world['id'],work)

    async def extra_controls(self,world,binding,second,feedback):
        _,native=requests(self.db,world,binding,feedback)
        for case in ('foreign','hash','version','observer','C4','quota','missing_source','unsupported','C3_incomplete','wrong_question'):
            req=copy.deepcopy(native)
            if case=='foreign':req['project']='LM_QA_TYPED011_FOREIGN'
            elif case=='hash':req['source_bindings'][0]['sha256']='0'*64
            elif case=='version':req['active_frontier_version']=1
            elif case=='observer':req['observer']['mod']=2
            elif case=='C4':req['question']['context_level']='C4'
            elif case=='quota':req['budget']={'native_calls':1}
            elif case=='missing_source':req['question']['root_event_id']=999999
            elif case=='unsupported':req['source_adapter_id']='unsupported'
            elif case=='C3_incomplete':req['question']['context_level']='C3';req['budget']={'max_events':1}
            else:req['question']['left_history_id']=req['question']['root_event_id']
            out=await self.call('research_cycle_preview',{'request':req})
            self.check(world['id']+':negative_preview:'+case,out['status'] in {'INSUFFICIENT_CONTEXT','NOVELTY_CONTEXT_INCOMPLETE','UNKNOWN_BOUNDED','RESOURCE_LIMIT'})
            self.negatives.append({'case':world['id']+':'+case,'response_status':out['status']})
        denied=await self.call('record_result',{'project':'RH','kind':'experiment','focus':'unauthorized QA control','result':'Must not write'},True)
        self.check(world['id']+':nonQA_write_denied',denied is None)
        renamed=copy.deepcopy(world);names={a:'alias_'+str(i) for i,a in enumerate(world['parameters']['actions'])}
        renamed['parameters']['actions']=[names[a] for a in world['parameters']['actions']]
        renamed['histories']={n:[names[a] for a in word] for n,word in world['histories'].items()}
        for t in renamed['tests']:t['suffix']=[names[a] for a in t['suffix']]
        alias=await self.seed_projection(renamed,binding,binding['active'],binding['version'],binding,label_prefix='alias-')
        _,req=requests(self.db,renamed,alias,feedback);out=await self.call('research_cycle_preview',{'request':req})
        self.check(world['id']+':rename_not_new',out['claim_fingerprint']==second['claim_fingerprint'] and out['status']=='NO_NEW_DISTINCTION_BOUNDED')
        swapped=copy.deepcopy(req)
        swapped['question']['left_history_id'],swapped['question']['right_history_id']=swapped['question']['right_history_id'],swapped['question']['left_history_id']
        swap_out=await self.call('research_cycle_preview',{'request':swapped})
        self.check(world['id']+':history_orientation_not_new',swap_out['status']=='NO_NEW_DISTINCTION_BOUNDED' and swap_out['claim_fingerprint']==second['claim_fingerprint'])
        # A separate corrupted-journal fixture forces a raw identity collision. Main history is untouched.
        original_db,original_client=self.db,self.client;collision=self.base/(world['id']+'-journal-collision.sqlite3')
        with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(collision) as dst:src.backup(dst)
        with connect(collision,True) as c:
            r=c.execute('SELECT * FROM typed011_journal WHERE project=? AND claim_fingerprint=? LIMIT 1',(world['project'],second['claim_fingerprint'])).fetchone()
            c.execute('INSERT INTO typed011_journal(project,scope,source_family_id,claim_fingerprint,raw_sha256,receipt_id,payload_json) VALUES (?,?,?,?,?,?,?)',
                (r['project'],r['scope'],r['source_family_id'],r['claim_fingerprint'],'0'*64,r['receipt_id'],canonical({'fixture':'intentional conflicting raw identity; not a valid new measurement'})))
        async def collision_work():
            result=await self.call('research_cycle_preview',{'request':req})
            self.check(world['id']+':raw_identity_conflict_REVIEW',result['status']=='REQUIRES_REVIEW' and not result['execution_permission']['allowed'])
            self.negatives.append({'case':world['id']+':injected_journal_collision','status':result['status'],'separate_database':True})
        try:
            self.db=collision;await self.session(world['id']+'-journal-collision',collision_work)
        finally:self.db,self.client=original_db,original_client
        # Rebind the same ordinal source/claim to a new frontier version, without new mathematics.
        rebound=await self.seed_projection(world,binding,binding['active'],3,binding,label_prefix='rebound-')
        data=json.loads(event_rows(self.db,world['project'])[feedback]['content']);data['version']=3;data['observation']['version']=3
        data['relations']=[{'type':'derived_from','target_ref':'event:'+str(feedback)}]
        projected=await self.event(world,'v3-negative-projection',data,kind='counterexample',status='experiment',parent=feedback)
        await self.call('research_obligation_update',{'project':world['project'],'obligation_id':binding['obligation_id'],'expected_version':2,
            'changes':{'status':'TESTING','source_event_ids':[binding['fixture_id'],rebound['root_id']],'evidence_refs':['event:'+str(projected['id'])]}})
        _,rebound_req=requests(self.db,world,rebound,projected['id']);rebound_out=await self.call('research_cycle_preview',{'request':rebound_req})
        self.check(world['id']+':version_rebind_not_new',rebound_out['status']=='NO_NEW_DISTINCTION_BOUNDED' and rebound_out['claim_fingerprint']==second['claim_fingerprint'])
        self.check(world['id']+':server_final_partition',rebound_out['attention']['status']=='NO_INFORMATIVE_TEST' and
            len([h for h in rebound_out['attention']['hypotheses'] if h['predictive'] and h['status']=='ACTIVE'])<=1 and
            next(h for h in rebound_out['attention']['hypotheses'] if h['id']=='IND')['status']=='ACTIVE')
        return 3


def freeze(baseline,base):
    registered=baseline/'frozen-inputs'
    if not registered.exists():
        registered.mkdir();(registered/'world-inputs').mkdir();(registered/'sealed-environments').mkdir()
        worlds=declarations(baseline.name)
        controls=[copy.deepcopy(worlds[0]),copy.deepcopy(worlds[0])]
        for w,label in zip(controls,('inconclusive','error')):w['id']=label
        for w in worlds+controls:
            w['project']='LM_QA_TYPED011_'+baseline.name+'_'+w['id']
            w.pop('scope',None);w.pop('fixture_sha256',None);w['fixture_sha256']=checksum(w);w['scope']='QA011/'+w['id']+'/'+w['fixture_sha256']
        envs=environments(worlds+controls,[secrets.token_hex(32) for _ in range(5)])
        for w,e in zip(worlds+controls,envs):
            write_json(registered/'world-inputs'/(w['id']+'.json'),w);write_json(registered/'sealed-environments'/(w['id']+'.json'),e)
        write_json(registered/'worlds.json',worlds+controls);write_json(registered/'oracle.json',[sequence(w,e) for w,e in zip(worlds,envs)])
        write_json(registered/'manifest.json',{str(p.relative_to(registered)):sha(p) for p in registered.rglob('*') if p.is_file()})
    frozen=json.loads((registered/'manifest.json').read_text());assert all(sha(registered/n)==h for n,h in frozen.items())
    for folder in ('world-inputs','sealed-environments'):shutil.copytree(registered/folder,base/folder)
    for name in ('oracle.json','worlds.json','manifest.json'):shutil.copyfile(registered/name,base/name)
    (base/'frozen-sources').mkdir()
    sources=[*SOURCE.glob('typed_cycle011*.py'),SOURCE/'test_typed_cycle011.py']
    for p in sources:
        if p.exists():shutil.copyfile(p,base/'frozen-sources'/p.name)
    write_json(base/'frozen-source-manifest.json',{str(p):sha(p) for p in sources if p.exists()})
    return json.loads((registered/'worlds.json').read_text()),json.loads((registered/'oracle.json').read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline-dir',type=Path,required=True);p.add_argument('--skip-regressions',action='store_true',help='Development only; cannot yield G5/PASS')
    a=p.parse_args();baseline=a.baseline_dir.resolve(strict=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base=baseline/'cohorts'/stamp;base.mkdir(parents=True,mode=0o700);Path('/tmp/lm011_cohort').write_text(str(base))
    write_json(base/'metadata.json',{'baseline':str(baseline),'report':str(ROOT/'docs/qa/LM-TYPED-SOURCE-CYCLE-011'/stamp)})
    worlds,oracle=freeze(baseline,base);db=base/'isolated.sqlite3'
    with sqlite3.connect((baseline/'research-before.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(db) as dest:src.backup(dest)
    canonical_db=Path(json.loads((baseline/'metadata.json').read_text())['db']);install(db,canonical_db)
    # Reserve a disjoint numeric event range as well as a fresh project namespace.
    # Old009 identifiers cannot be mistaken for this cohort's newly created events.
    with connect(db,True) as c:
        floor=int(datetime.now(timezone.utc).timestamp()*10000)
        c.execute("UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='events'",(floor,))
        ResearchStore(db)._audit(c,'typed011_QA_event_range_reserved',{'minimum_new_event_id':floor+1})
    runner=Acceptance(base,db,canonical_db);failure=None
    try:
        if not a.skip_regressions:
            with (base/'pytest.txt').open('w') as out:
                subprocess.run([sys.executable,'-m','pytest','-q',str(SOURCE)],stdout=out,stderr=subprocess.STDOUT,
                    env={k:v for k,v in os.environ.items() if k!='LIVE_MATH_NATIVE_PREVIEW'},check=True)
            print('Full pytest PASS',flush=True)
            previous=os.environ.pop('LIVE_MATH_NATIVE_PREVIEW',None)
            try:old=run_regression(base/'historical86',baseline/'research-before.sqlite3')
            finally:
                if previous is not None:os.environ['LIVE_MATH_NATIVE_PREVIEW']=previous
            runner.check('historical86',old['result']=='PASS')
        async def run():
            for w,o in zip(worlds[:3],oracle):await runner.run_world(w,o)
            runner.gates['G4']='PASS'
            for w,control in zip(worlds[3:],('INCONCLUSIVE','ERROR')):await runner.run_world(w,None,control)
        asyncio.run(run())
        if not a.skip_regressions:runner.gates['G5']='PASS'
    except BaseException as error:
        failure={'classification':'MCP_LIFECYCLE_BUG','error':str(error),'traceback':traceback.format_exc()}
        if not (base/'first-failure.json').exists():write_json(base/'first-failure.json',failure)
        else:write_json(base/'run-failure.json',failure)
        print(json.dumps(failure),flush=True)
    finally:
        write_json(base/'gates.json',runner.gates);write_json(base/'negative-controls.json',runner.negatives)
        from typed_cycle011_report import export
        print(json.dumps(export(base,failure)),flush=True)


if __name__=='__main__':main()
