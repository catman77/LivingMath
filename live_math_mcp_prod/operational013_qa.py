"""Frozen deterministic P0, prereveal prediction receipts and strong baselines."""
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
import resource
import shutil
import sqlite3
import sys
import time

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from normalizer import canonical,digest
from normalization_regression import Tap
from native_preview008_qa import readonly_state
from qa_positive_acceptance import write_json
from research_store import ResearchStore
from operational013 import LinearTransport,Predictor,TransportRefusal
from operational013_native import Port,Ledger,definition_sha256
from operational013_oracle import replay
from operational013_worlds import prefixes
from operational013_source import Frame,VisiblePort
from live_transfer006 import endpoint,initial_cache,attend
from concept_genesis012 import discover,construct

OBSERVER={'projection':'primary','mod':None}
SOURCE=Path(__file__).resolve().parent


def append(path,data):
    with path.open('a') as f:
        f.write(canonical(data)+'\n');f.flush();os.fsync(f.fileno())


def acquisition(declaration):
    ledger=Ledger();port=Port(declaration,ledger)
    initial=port.load([]);origin=port.inspect(initial)
    cache={():{'state':initial,'admissibility':[]}}
    transitions=[];validation=[];images={():origin};observations={};timings={}
    for stage,words,destination in [('discovery',prefixes(declaration['arity'],2),transitions),
                                    ('validation',prefixes(declaration['arity'],3,exact=True),validation)]:
        ledger.stage=stage
        stage_wall,stage_cpu=time.perf_counter_ns(),time.process_time_ns()
        for word in words:
            key=tuple(word)
            # Populate from the root with the unchanged006 prefix-caching primitive.
            readout=endpoint(port,cache,word,OBSERVER)
            if not readout['defined']:continue
            state=cache[key]['state'];before=images.setdefault(key,port.inspect(state))
            observations[key]=readout
            for a in range(declaration['arity']):
                after_word=word+[a];out=endpoint(port,cache,after_word,OBSERVER)
                if not out['defined']:continue
                after_state=cache[tuple(after_word)]['state'];after=port.inspect(after_state)
                images[tuple(after_word)]=after;observations[tuple(after_word)]=out
                if before is not None and after is not None:
                    destination.append({'before':before,'after':after,'action':a,'history':word})
        timings[stage]={'wall_ns':time.perf_counter_ns()-stage_wall,'CPU_ns':time.process_time_ns()-stage_cpu}
    return {'port':port,'ledger':ledger,'cache':cache,'origin':origin,'transitions':transitions,
            'validation':validation,'images':images,'observations':observations,'timings':timings}


def record(store,project,focus,content,parent=None,kind='qa_source'):
    response=store.record(project,kind,focus,canonical(content),'experiment' if kind=='counterexample' else 'hypothesis',
                          parent_id=parent,request_key=project+':'+focus)
    with store._connect() as c:return dict(c.execute('SELECT * FROM events WHERE id=?',(response['id'],)).fetchone())


def seed(db,declaration,acquired,stamp):
    project='LM_QA_OPERATIONAL013_'+stamp[-12:]+'_'+declaration['id'];scope='QA013/'+project
    store=ResearchStore(db)
    fixture=record(store,project,'source',{'claim_type':'SOURCE_CLAIM','scope':scope,'version':1,'declaration':declaration,
                  'native_definition_sha256':definition_sha256(),'statement':'Native source, no supplied rule or heldout information.'})
    bundle=record(store,project,'observations',{'claim_type':'SOURCE_CLAIM','scope':scope,'version':1,
                  'origin':acquired['origin'],'transitions':acquired['transitions'],
                  'provenance':'Counted native discovery replay; not external measurement.'},fixture['id'])
    root=record(store,project,'root',{'claim_type':'HYPOTHESIS','scope':scope,'version':1,'observer':OBSERVER,
                'native_definition_sha256':definition_sha256(),'fixture_event_id':fixture['id'],
                'observations_event_id':bundle['id'],'statement':'Guarded law is an empirical hypothesis, not source equality.'},fixture['id'])
    words={};rows=[fixture,bundle,root]
    for index,word in enumerate(prefixes(declaration['arity'],2)):
        if tuple(word) not in acquired['observations'] or acquired['observations'][tuple(word)]['observation']!=0:continue
        row=record(store,project,'h'+str(index),{'claim_type':'SOURCE_CLAIM','scope':scope,'version':1,'word':word},fixture['id'])
        words['event:'+str(row['id'])]=word;rows.append(row)
    ind=record(store,project,'independent',{'claim_type':'HYPOTHESIS','scope':'independent','version':1,'word':[]},fixture['id'])
    rows.append(ind);words['event:'+str(ind['id'])]=[]
    obligation=store.frontier.create(project,'Bounded law test, no autonomous grants.',scope,[fixture['id'],root['id']])
    return {'project':project,'scope':scope,'fixture':fixture,'root':root,'obligation_id':obligation['id'],'words':words,'events':{r['id']:r for r in rows}}


def memory_prediction(acquired,word):
    table={}
    for t in acquired['transitions']:
        key=(tuple(t['before']),t['action'])
        if key in table and table[key]!=t['after']:return {'status':'INSUFFICIENT_STATE'}
        table[key]=t['after']
    image=acquired['origin']
    if image is None:return {'status':'NO_TRANSFER_LAW'}
    for a in word:
        if (tuple(image),a) not in table:return {'status':'UNKNOWN_UNOBSERVED_TRANSITION'}
        image=table[(tuple(image),a)]
    known=[v['observation'] for k,v in acquired['observations'].items() if acquired['images'].get(k)==image]
    if not known:return {'status':'UNKNOWN_OBSERVER'}
    return {'status':'MEMORIZED','observation':known[0]}


def b2_baseline(db,declaration,binding):
    ledger=Ledger();frame=Frame(declaration,dict(binding['events']),binding['words'],binding['root']['id'],binding['scope'],binding['project'],ledger)
    negative=discover(frame)
    if negative['status']!='SOURCE_COUNTEREXAMPLE':return {'discovery':negative,'costs':ledger.summary(),'native_trace':ledger.rows}
    store=ResearchStore(db)
    row=record(store,binding['project'],'B2-negative',negative['counterexample'],binding['root']['id'],'counterexample')
    frame.events[row['id']]=row
    out=construct(frame,row['id'])
    return {'discovery':negative,'construction':out,'costs':ledger.summary(),'native_trace':ledger.rows,
            'heldout_policy':'Original012 applicability names only source histories and one registered suffix, not arbitrary composition. UNKNOWN outside it.'}


class Experiment:
    def __init__(self,baseline,output):
        self.base,self.out=baseline,output;output.mkdir(parents=True,exist_ok=False)
        self.freeze=json.loads((baseline/'freeze.json').read_text());self.checks=[];self.calls=[]
        self.start=time.perf_counter_ns();self.cpu=time.process_time_ns()
        self.children_before=resource.getrusage(resource.RUSAGE_CHILDREN)
        self.db=baseline/('experiment-'+output.name+'.sqlite3')
        with sqlite3.connect((baseline/'canonical.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(self.db) as dst:src.backup(dst)
        self.db.chmod(0o600);self.before=readonly_state(self.db)
        self.policy=self.freeze['policy'];self.worlds=json.loads((baseline/'frozen-inputs/discovery.json').read_text())
        self.data={};self.laws={};self.predictions=[];self.receipts=[];self.baselines={};self.metrics={};self.counterexamples=[]
        write_json(output/'freeze.json',self.freeze)
        shutil.copy2(baseline/'source-audit.md',output/'source-audit.md')
        shutil.copytree(baseline/'frozen-inputs',output/'frozen-inputs')
        sources=output/'sources';sources.mkdir()
        for p in sorted(SOURCE.glob('operational013*.py')):shutil.copy2(p,sources/p.name)
        shutil.copy2(SOURCE/'test_operational013.py',sources/'test_operational013.py')
        write_json(output/'source-hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.iterdir()})

    def check(self,name,ok,evidence=None):
        row={'invariant':name,'result':'PASS' if ok else 'FAIL','evidence':evidence};self.checks.append(row)
        write_json(self.out/'checks.json',self.checks)
        if not ok:
            if not (self.out/'first-failure.json').exists():write_json(self.out/'first-failure.json',row)
            raise ValueError(name)

    async def p0(self):
        for d in self.worlds:
            acquired=acquisition(d);binding=seed(self.db,d,acquired,self.base.name)
            self.data[d['id']]={'acquired':acquired,'binding':binding,'declaration':d}
            write_json(self.out/('acquisition-'+d['id']+'.json'),{'discovery':acquired['transitions'],'validation':acquired['validation'],
                       'costs':acquired['ledger'].summary(),'trace':acquired['ledger'].rows,'source':binding,'timings':acquired['timings']})
        parameters=StdioServerParameters(command=sys.executable,args=[str(SOURCE/'operational013_server.py'),'--db',str(self.db)])
        wire=self.out/'mcp-wire.jsonl'
        with (self.out/'server-stderr.txt').open('w') as errors:
            async with stdio_client(parameters,errlog=errors) as (read,write):
                async with ClientSession(Tap(read,wire,'response'),Tap(write,wire,'request')) as client:
                    initialized=(await client.initialize()).model_dump(mode='json')
                    tools=(await client.list_tools()).model_dump(mode='json')
                    self.check('private_MCP_no_operator_authority',{t['name'] for t in tools['tools']}=={'operational_law_preview'})
                    self.calls.append({'initialize':initialized,'tools':tools})
                    for key,item in self.data.items():
                        b=item['binding'];args={'project':b['project'],'obligation_id':b['obligation_id'],'version':1,
                              'root_event_id':b['root']['id'],'observer':OBSERVER,
                              'source_bindings':[{'event_id':i,'sha256':digest(r)} for i,r in b['events'].items()]}
                        before=readonly_state(self.db)
                        reply=await client.call_tool('operational_law_preview',{'request':args})
                        raw=reply.model_dump(mode='json');out=json.loads(''.join(c.text for c in reply.content if c.type=='text'))
                        self.calls.append({'source':key,'request':args,'response':raw})
                        self.check(key+':MCP_readonly',readonly_state(self.db)==before)
                        self.check(key+':source_bound_law','law' in out,out)
                        law=LinearTransport.restore(out['law']);self.laws[key]=law
                        item['law_response_timings']=out.get('timings',{})
                        write_json(self.out/('law-'+key+'.json'),out)
                        a=item['acquired'];covered=0;refusals=Counter()
                        for t in a['validation']:
                            try:
                                predicted=law.step(t['before'],t['action'])
                            except TransportRefusal as error:
                                refusals[str(error)]+=1;continue
                            self.check(key+':validation:'+str(covered),predicted==t['after'],t);covered+=1
                        item['validation_summary']={'covered':covered,'refusals':dict(refusals)}
        write_json(self.out/'mcp-transcript.json',self.calls)
        # Freeze all fitted laws BEFORE opening the sealed query words. The constructor process exited.
        fitted={key:law.artifact() for key,law in self.laws.items()}
        write_json(self.out/'law-candidates.json',fitted)
        law_digest=digest(fitted);frozen_at=datetime.now(timezone.utc).isoformat()
        sealed=json.loads((self.base/'frozen-inputs/sealed-evaluation.json').read_text())
        for key,item in self.data.items():
            a=item['acquired'];law=self.laws[key];ledger=Ledger();ledger.stage='prediction'
            prediction_wall,prediction_cpu=time.perf_counter_ns(),time.process_time_ns()
            predictor=Predictor(law,Port(item['declaration'],ledger),OBSERVER,law.binding)
            item['prediction_ledger']=ledger
            for index,word in enumerate(sealed[key]):
                pred=predictor.predict(a['origin'] or [],word) if law.status=='CANDIDATE_TRANSPORT' else {'status':law.status,'reason':law.counterexample}
                row={'order':len(self.predictions),'source':key,'index':index,'word':word,'prediction':pred,
                     'law_sha256':law_digest,'law_frozen_at':frozen_at,'prediction_time':datetime.now(timezone.utc).isoformat(),
                     'monotonic_ns':time.monotonic_ns(),'previous':digest(self.predictions[-1]) if self.predictions else 'GENESIS',
                     'B3':memory_prediction(a,word),'proof_status':'unverified'}
                self.predictions.append(row);append(self.out/'predictions-before-heldout.jsonl',row)
            item['prediction_timings']={'wall_ns_including_receipt_IO':time.perf_counter_ns()-prediction_wall,'CPU_ns':time.process_time_ns()-prediction_cpu}
        prediction_seal=hashlib.sha256((self.out/'predictions-before-heldout.jsonl').read_bytes()).hexdigest()
        write_json(self.out/'prediction-seal.json',{'sha256':prediction_seal,'count':len(self.predictions),'time':datetime.now(timezone.utc).isoformat()})
        # Independent replay starts only AFTER all predictions were durably sealed.
        replay_started=time.monotonic_ns();qualified=[]
        for key,item in self.data.items():
            a=item['acquired'];law=self.laws[key];d=item['declaration'];good=0;unknown=0;b3missing=0;oracle_calls=0
            replay_wall,replay_cpu=time.perf_counter_ns(),time.process_time_ns()
            for row in [p for p in self.predictions if p['source']==key]:
                readout,steps=replay(d,row['word']);oracle_calls+=1+len(steps)*2
                receipt={'source':key,'index':row['index'],'word':row['word'],'prediction_order':row['order'],'prediction_seal':prediction_seal,
                         'prediction_sha256':digest(row),'replay_time':datetime.now(timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns(),
                         'readout':readout,'raw_native_steps':steps,'oracle_sha256':hashlib.sha256((SOURCE/'operational013_oracle.py').read_bytes()).hexdigest(),
                         'origin':'independent synthetic QA source replay, not a production observation','proof_status':'unverified'}
                self.receipts.append(receipt);append(self.out/'heldout-receipts.jsonl',receipt)
                if row['prediction']['status']=='PREDICTED':
                    self.check(key+':heldout:'+str(row['index']),row['prediction']['readout']==readout,{'prediction':row,'receipt':receipt});good+=1
                    if row['B3']['status']!='MEMORIZED':b3missing+=1
                else:unknown+=1
            oracle_timings={'wall_ns_including_receipt_IO':time.perf_counter_ns()-replay_wall,'CPU_ns':time.process_time_ns()-replay_cpu}
            # B1 receives all the same acquired native states/readouts, without extra hidden data.
            b1ledger=Ledger();b1ledger.stage='heldout_B1';b1=Port(d,b1ledger)
            cache=copy.deepcopy(a['cache']);b1outputs=[endpoint(b1,cache,word,OBSERVER) for word in sealed[key]]
            expected=[r['readout'] for r in self.receipts if r['source']==key]
            self.check(key+':B1_independent_replay',b1outputs==expected)
            common=sum(a['ledger'].counts.values());c_calls=common+sum(item['prediction_ledger'].counts.values())
            b1_calls=common+sum(b1ledger.counts.values())
            metrics={'law_status':law.status,'correct_predictions':good,'refusals':unknown,'B3_missing_correct':b3missing,
                'discovery_validation_queries':common,'C_total_native_queries':c_calls,'B1_total_native_queries':b1_calls,
                'savings':b1_calls-c_calls,'oracle_verification_queries':oracle_calls,'validation':item['validation_summary']}
            metrics['timings']={'acquisition':a['timings'],'constructor':item['law_response_timings'],
                               'prediction':item['prediction_timings'],'oracle':oracle_timings}
            self.metrics[key]=metrics
            if good==len(sealed[key]) and b3missing>0 and c_calls<b1_calls:qualified.append(key)
            b2=b2_baseline(self.db,d,item['binding']) if key not in {'D','E'} else {'status':'SOURCE_IMAGE_UNAVAILABLE_OR_INSUFFICIENT','out_of_domain':'No transport law asserted.'}
            self.baselines[key]={'shared_acquisition':a['ledger'].summary(),'C_prediction':item['prediction_ledger'].summary(),
                'C_trace':item['prediction_ledger'].rows,'B1':{'costs':b1ledger.summary(),'trace':b1ledger.rows,'outputs':b1outputs},
                'B2_actual012':b2,'B3':{'table_rows':len(a['transitions']),'out_of_domain':'UNKNOWN','additional_native_queries':0}}
        self.check('predictions_immutable_before_replay',all(r['monotonic_ns']<replay_started for r in self.predictions) and
                   hashlib.sha256((self.out/'predictions-before-heldout.jsonl').read_bytes()).hexdigest()==prediction_seal)
        self.check('two_distinct_positive_sources',len(qualified)>=2,qualified)
        self.check('opaque_refusal',self.laws['D'].status=='NO_TRANSFER_LAW')
        self.check('insufficient_state_counterexample',self.laws['E'].status=='INSUFFICIENT_STATE',self.laws['E'].counterexample)
        self.counterexamples.append(self.laws['E'].counterexample)
        # Minimal absolute-address012 falsifier: bottom remains0, relative top changes0->1.
        old,new=[0],[0,1]
        counter={'classification':'THEORETICAL_LAW_FAILURE','claim':'absolute source index0 transports stack top',
                 'before':old,'after':new,'action':1,'absolute_index0':[old[0],new[0]],'native_top':[old[-1],new[-1]],
                 'effect':'Reject stronger absolute-address claim; keep original012 failure.'}
        self.counterexamples.append(counter);self.check('absolute_address012_falsifier',old[0]==new[0] and old[-1]!=new[-1])
        # Literal order and relative-origin/presentation controls have no family branch in the learner.
        for key in ('A','B'):
            law=self.laws[key];image=self.data[key]['acquired']['origin']
            ab=law.step(law.step(image,0),1);ba=law.step(law.step(image,1),0)
            self.check(key+':noncommuting_composition',ab!=ba,{'T1_T0':ab,'T0_T1':ba})
            artifact=law.artifact();clone=copy.deepcopy(artifact);clone['binding']={**clone['binding'],'title':'renamed'}
            self.check(key+':rename_not_new_law',artifact['actions']==clone['actions'])
            for changed in ({**law.binding,'version':2},{**law.binding,'observer':{'projection':'constant','mod':None}}):
                try:law.assert_binding(changed);refused=False
                except TransportRefusal:refused=True
                self.check(key+':binding_refusal:'+digest(changed)[:8],refused)
        self.check('point_zero_not_germ_zero',0==0 and [0,1]!=[0,0],{'point_values':[0,0],'germs':[[0,1],[0,0]],'source_equality_asserted':False})
        self.check('no_generator_native_E_on_predictions',not any(r['operation']=='E' for item in self.data.values() for r in item['prediction_ledger'].rows))
        write_json(self.out/'baseline-ledgers.json',self.baselines);write_json(self.out/'counterexamples.json',self.counterexamples)
        write_json(self.out/'P0-metrics.json',self.metrics)
        return qualified

    def resource_costs(self):
        children=resource.getrusage(resource.RUSAGE_CHILDREN)
        return {'P0_wall_ns':time.perf_counter_ns()-self.start,'P0_CPU_ns':time.process_time_ns()-self.cpu,
                'reaped_child_CPU_ns':round(((children.ru_utime+children.ru_stime)-(self.children_before.ru_utime+self.children_before.ru_stime))*1e9),
                'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'serialization_bytes':sum(p.stat().st_size for p in self.out.rglob('*') if p.is_file()),
                'source_calls':self.metrics,'LLM_calls':0,'oracle_cost_is_not_native_constructor_cost':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    baseline=args.baseline or Path(Path('/tmp/lm013_path').read_text().strip())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=args.output or SOURCE.parent/'docs/qa/LM-OPERATIONAL-INVARIANT-013'/stamp
    experiment=Experiment(baseline,output)
    write_json(baseline/'current.json',{'output':str(output),'database':str(experiment.db)})
    try:
        qualified=asyncio.run(experiment.p0());status='P0_PASS_TYPED_PENDING'
    except Exception as error:
        qualified=[];status='STOP_WITH_RCA'
        write_json(output/'exception.json',{'error':str(error),'traceback':__import__('traceback').format_exc()})
    costs=experiment.resource_costs();write_json(output/'costs.json',costs)
    write_json(output/'result.json',{'status':status,'qualified':qualified,'metrics':experiment.metrics,'checks':experiment.checks,
                                  'proof_status':'unverified','production_changed':False})
    print(canonical({'status':status,'output':str(output),'qualified':qualified,'metrics':experiment.metrics,'costs':costs}))


if __name__=='__main__':main()
