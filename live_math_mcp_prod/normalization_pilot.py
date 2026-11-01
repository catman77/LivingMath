"""A small hidden-state measurement pilot, never a table of ready oracle choices."""
import asyncio
from collections import defaultdict
from fractions import Fraction
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import time

import jsonschema
import tiktoken

from causal_model import stop_process_group
from normalizer import canonical, digest, normalize_context, read_history
from research_store import ResearchStore

MODEL = 'gpt-6-luna'
PILOT_PROTOCOL = '004.P1.2'
TOKENS = 6000
TIMEOUT = 120
SEED = 104004
ENCODING = tiktoken.get_encoding('o200k_base')
TARGETS = ['The last two indicators are both1.', 'Exactly one of indicators0 and2 is1.',
           'At least two of the four indicators are1.', 'Indicator0 equals the parity of indicators1,2,3.']
TESTS = ['Read indicator0.', 'Read indicator2.', 'Read the parity of indicators0 and2.',
         'Read the number of ones among all four indicators.', 'Read the target Boolean itself, using a costly full assessment.']


def outcome(task: int, state: tuple) -> int:
    a,b,c,d = state
    return [int(c and d), a ^ c, int(sum(state) >= 2), int(a == ((b+c+d) % 2))][task]


def readout(task: int, test: int, state: tuple) -> int:
    return [state[0], state[2], state[0] ^ state[2], sum(state), outcome(task, state)][test]


def support(task: int) -> list:
    result = []
    for state in itertools.product((0,1), repeat=4):
        if (state[0] ^ state[1]) == task % 2:
            weight = 1 + (task+1)*state[0] + 2*state[2] + state[1]*state[3]
            result.append((state, weight))
    return result


def costs(task: int) -> list:
    return [[2,1,2,3,4], [1,2,3,2,5], [1,2,2,3,4], [2,1,2,3,4]][task]


def oracle(task: int) -> dict:
    states = support(task);total = sum(w for _,w in states);losses=[];reductions=[]
    for test in range(5):
        groups = defaultdict(lambda: [0,0])
        for state, weight in states:
            groups[readout(task,test,state)][outcome(task,state)] += weight
        residual = Fraction(sum(min(pair) for pair in groups.values()), total)
        loss = Fraction(costs(task)[test]) + 12*residual
        # Independent reference: enumerate every deterministic readout->continuation decision rule.
        values = sorted(groups)
        brute = min(sum(weight for state,weight in states if dict(zip(values, assignment))[readout(task,test,state)] != outcome(task,state))
                    for assignment in itertools.product((0,1),repeat=len(values)))
        assert residual == Fraction(brute,total)
        losses.append(float(loss));reductions.append(float(residual))
    initial=[sum(w for s,w in states if outcome(task,s)==label) for label in (0,1)]
    prior_error=Fraction(min(initial),total)
    useful=[i for i,r in enumerate(reductions) if r<float(prior_error)]
    assert len(useful)>=2 and len({costs(task)[i] for i in useful})>=2
    return {'task':task,'support':states,'losses':losses,'residual_error':reductions,
            'best_loss':min(losses),'worst_loss':max(losses),'best_tests':[i for i,x in enumerate(losses) if x==min(losses)],
            'prior_error':float(prior_error),'useful_test_indices':useful,
            'implementations_agree':True,'two_usable_tests_with_different_cost_or_reduction':True}


def schema() -> dict:
    props={'decision':{'enum':['measure','review']},'test_id':{'type':'string'},'source_version':{'type':['integer','null']},
        'evidence_refs':{'type':'array','items':{'type':'string'}},'retained_independent_ids':{'type':'array','items':{'type':'string'}},
        'reason':{'type':'string'},'proof_status':{'const':'unverified'}}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def retained_branch(values: list[str], task: dict) -> bool:
    """Match explicit output labels for this task's registered independent source.

    This grades a branch marker, not mathematical equality or an alias witness.
    Protocol 004.P1.1 scores are historical and must never be rewritten with it.
    """
    reference = task['refs']['independent']
    aliases = {'I', 'Branch I', reference, reference.split(':', 1)[1]}
    return any(value in aliases for value in values)


def create_task(directory: Path, task: int) -> dict:
    store=ResearchStore(directory/('p1-'+str(task)+'.sqlite3'));project='LOCAL_N004_PILOT_'+str(task)
    rng=random.Random(SEED+task);ids=['t'+str(n) for n in rng.sample(range(1000,9999),5)]
    refs={};facts=[]
    declarations=[('source',f'Four binary indicators are unobserved. Exactly parity(indicator0,indicator1)={task%2}. '
        f'Prior integer weight for an allowed assignment is 1+{task+1}*indicator0+2*indicator2+indicator1*indicator3. No actual assignment is supplied.'),
        ('goal','The next measurement helps distinguish two continuations. Target: '+TARGETS[task]),
        ('criterion','Minimize measurement cost +12 times expected error probability of the optimal continuation decision AFTER observing that test. Choose exactly one current measurement.'),
        ('independent','Branch I remains independently available; its separate sensor is not evidence about these four indicators.')]
    declarations += [(tid,desc+' Cost='+str(costs(task)[i])+'. Current version2, scope Q.') for i,(tid,desc) in enumerate(zip(ids,TESTS))]
    declarations += [('obsolete','Old version1 proposed a zero-cost answer without reading the current indicators. It is closed after a failed check; do not treat it as a current measurement.')]
    for key,statement in declarations:
        payload={'claim_type':'SOURCE_CLAIM','statement':statement,'scope':'Q' if key!='independent' else 'I',
            'representation':'finite hidden binary state; no realized values supplied','version':1 if key=='obsolete' else 2,
            'method_model':{'input':'unknown indicators','operation':key,'output':'unobserved'},
            'unknowns':['Actual indicators and future readout are unknown'],'claim_map':{'source_claim':statement},'counter_reading':None}
        record=store.record(project,'failed_check' if key=='obsolete' else 'hypothesis',key,json.dumps(payload),
                            'refuted' if key=='obsolete' else 'hypothesis')
        refs[key]='event:'+str(record['id']);facts.append({'ref':refs[key],**payload})
    for i in range(2):
        store.record(project,'hypothesis','Separate context '+str(i),json.dumps({'claim_type':'SOURCE_CLAIM','statement':'Unrelated archived scope. '+('Historical detail retained. '*35),'scope':'elsewhere','version':0,'representation':'notes'}))
    history=read_history(store.path,project)
    dq=[{'id':tid,'project':project,'proposal':'One finite measurement','move':{'parent_event_ids':[int(refs[k].split(':')[1]) for k in refs],
         'proposed_operation':{'test':tid}}} for tid in ids]
    view=normalize_context(history,'measurement',dq,'C2')
    assert view['status']=='COMPLETE'
    projection={'concepts':[{key:c[key] for key in ('statement','source_refs','scope','representation','version','method_model','unknowns','epistemic_status')}
                            for c in view['concepts']], 'loss_ledger':view['loss_ledger'],'status':view['status']}
    byref={c['source_refs'][0]['ref']:c for c in view['concepts']}
    for fact in facts:
        node=byref[fact['ref']]
        for key in ('statement','scope','representation','version','method_model'):
            assert node[key]==fact[key]
        assert [u['reason'] for u in node['unknowns'] if u['field']=='source.unknowns']==fact['unknowns']
    full={'events':history['tables']['events']}
    flat='\n'.join(canonical(f) for f in facts)
    # Ordinary summary is explicitly a lossy baseline, not a source-equivalent treatment.
    summary='\n'.join(f['method_model']['operation']+': '+f['statement'] for f in facts)
    return {'task':task,'project':project,'test_ids':ids,'refs':refs,'facts':facts,'history':history,'view':view,
            'inputs':{'A':canonical(full),'B':summary,'C':canonical(projection),'D':flat},'oracle':oracle(task),
            'decision_facts_equivalent_A_C_D':True,'B_is_lossy':True}


def make_prompt(task: dict, mode: str) -> str:
    common=('Finite QA. No tools, files, commands, network, skills or agents. Source claims are unverified. '
        'Choose ONE current measurement minimizing the stated expected decision loss under the stated prior. '
        'There is no realized hidden state in this input. A test ID is one of the tNNNN measurement records. '
        'Keep branch I available, do not revive the closed old rule. Use I or its source event reference in retained_independent_ids. '
        'Copy version2 and event references when available; '
        'if source references are unavailable state that in reason. No grant or proof is created. Reason<=120 words. Return the JSON schema.\n')
    text=common+'DATA\n'+task['inputs'][mode]+'\nEND DATA\nIGNORABLE PADDING:'
    n=len(ENCODING.encode(text))
    if n>TOKENS:raise ValueError('P1 matched token budget exceeded')
    text+=' x'*(TOKENS-n)
    assert len(ENCODING.encode(text))==TOKENS
    return text


async def infer(directory: Path, text: str) -> dict:
    directory.mkdir(parents=True,exist_ok=False);(directory/'empty').mkdir()
    (directory/'prompt.txt').write_text(text);(directory/'schema.json').write_text(json.dumps(schema()))
    command=['bwrap','--bind','/','/','--ro-bind','/dev/null',str(Path.home()/'.codex/AGENTS.md'),'--chdir',str(directory/'empty'),
        'codex','--no-daemon','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check','--sandbox','read-only',
        '-m',MODEL,'-c','project_doc_max_bytes=0','-c','features.apps=false','-c','features.plugins=false','-c','features.multi_agent=false',
        '-c','features.skill_search=false','-c','model_reasoning_effort="low"','--json','--output-schema',str(directory/'schema.json'),'-o',str(directory/'output.json'),'-']
    env={k:v for k,v in os.environ.items() if k not in {'OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL','ANTHROPIC_API_KEY','AZURE_OPENAI_API_KEY'}}
    start=time.monotonic();receipt={'outcome':'TRANSPORT_FAILURE','metadata':{'model_requested':MODEL,'reasoning':'low',
        'timeout':TIMEOUT,'estimated_input_tokens':TOKENS,'actual_usage':None,'immutable_build':None,'sampling_seed':None,
        'provider_output_cap':None,'prompt_sha256':hashlib.sha256(text.encode()).hexdigest(),'controller_retries':0}}
    (directory/'attempt-start.json').write_text(json.dumps({'monotonic':start,'model_requested':MODEL}))
    with (directory/'events.jsonl').open('w') as out,(directory/'stderr.txt').open('w') as err:
        process=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=out,stderr=err,env=env,start_new_session=True)
        timed_out=False
        try:await asyncio.wait_for(process.communicate(text.encode()),TIMEOUT)
        except asyncio.TimeoutError:
            timed_out=True;await stop_process_group(process)
        except asyncio.CancelledError:
            await stop_process_group(process);receipt['metadata']['cancelled']=True
            receipt['metadata']['wall_seconds']=time.monotonic()-start
            (directory/'receipt.json').write_text(json.dumps(receipt));raise
    events=[];invalid=False
    for line in (directory/'events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:invalid=True
    tools=[e for e in events if (e.get('item') or {}).get('type') not in {None,'reasoning','agent_message'}]
    receipt['metadata'].update(wall_seconds=time.monotonic()-start,timed_out=timed_out,exit_code=process.returncode,tool_events=len(tools),
        actual_usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None))
    if not timed_out and process.returncode==0:
        receipt['outcome']='MODEL_FAILURE'
        try:
            answer=json.loads((directory/'output.json').read_text());jsonschema.validate(answer,schema())
            if invalid or tools or len(answer['reason'].split())>120:raise ValueError('Tool/format/word-budget violation')
            receipt.update(outcome='OK',output=answer)
        except (ValueError,OSError,jsonschema.ValidationError) as error:receipt['error']=str(error)
    (directory/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


def prepare(base: Path) -> list:
    directory=base/'pilot';directory.mkdir();tasks=[create_task(directory,i) for i in range(4)]
    prompts=directory/'frozen-prompts';prompts.mkdir()
    for task in tasks:
        for mode in 'ABCD':
            (prompts/('c'+digest([task['task'],mode])[:16]+'.txt')).write_text(make_prompt(task,mode))
    (directory/'tasks.json').write_text(json.dumps([{k:v for k,v in t.items() if k!='inputs'} for t in tasks],ensure_ascii=False,indent=2)+'\n')
    (directory/'oracle.json').write_text(json.dumps([t['oracle'] for t in tasks],indent=2)+'\n')
    (directory/'schema.json').write_text(json.dumps(schema(),indent=2)+'\n')
    (directory/'treatment-equivalence.json').write_text(json.dumps({'decision_facts_equivalent_A_C_D':True,'B_is_lossy_descriptive_control':True},indent=2)+'\n')
    prereg={'version':PILOT_PROTOCOL,'model_requested':MODEL,'reasoning':'low','calls_max':16,'concurrency':1,'timeout':TIMEOUT,
        'codex_version':subprocess.check_output(['codex','--version'],text=True).strip(),
        'auth_status':subprocess.check_output(['codex','login','status'],text=True,stderr=subprocess.STDOUT).strip(),
        'input_tokens_estimated':TOKENS,'provider_seed':None,'immutable_build':None,'output_token_cap':None,
        'primary_loss':'measurement cost +12*Bayes error after readout, exact finite prior enumeration',
        'comparison':'Matched A-C and D-C complete task pairs only; B is explicitly lossy and descriptive.',
        'statistics':'10000 bootstrap resamples by task; seed104004; coverage>=90%; pilot exploratory, no population claim.',
        'gate':'At least2 genuinely usable tests per task; baseline A mean quality in[.30,.95), else QA_WORLD_BUG. No automatic expansion.',
        'stop':'At transport failures/started>=.10 or any schema/model failure; otherwise16 calls.',
        'main32':'Requires separate after-pilot decision; never automatically started here.',
        'hidden_state':'No realized guard or full test-prediction table in any model input.'}
    (directory/'preregistration.json').write_text(json.dumps(prereg,indent=2)+'\n')
    frozen={str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in prompts.iterdir()}
    for name in ('tasks.json','oracle.json','preregistration.json','schema.json','treatment-equivalence.json'):frozen[name]=hashlib.sha256((directory/name).read_bytes()).hexdigest()
    (directory/'immutable-manifest.json').write_text(json.dumps(frozen,indent=2)+'\n')
    return tasks


def run(base: Path, tasks: list) -> dict:
    directory=base/'pilot';rows=[];failures=[]
    for task in tasks:
        modes=list('ABCD');random.Random(SEED+task['task']).shuffle(modes)
        for mode in modes:
            label='c'+digest([task['task'],mode])[:16];text=(directory/'frozen-prompts'/(label+'.txt')).read_text()
            row={'id':label,'task':task['task'],'mode':mode,**asyncio.run(infer(directory/'models'/label,text))}
            if row['outcome']=='OK':
                action=row['output'];o=task['oracle'];test=task['test_ids'].index(action['test_id']) if action['test_id'] in task['test_ids'] else None
                loss=o['losses'][test] if action['decision']=='measure' and test is not None else o['worst_loss']
                row['metrics']={'regret_quality':1-(loss-o['best_loss'])/(o['worst_loss']-o['best_loss']),
                    'loss':loss,'optimal':loss==o['best_loss'],'provenance':bool(action['evidence_refs']) and set(action['evidence_refs'])<=set(task['refs'].values()),
                    'version':action['source_version']==2,'independent_retained':retained_branch(action['retained_independent_ids'],task),'proof_status':'unverified'}
            rows.append(row)
            with (directory/'outputs.jsonl').open('a') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')
            print(json.dumps({'P1':len(rows),'id':label,'outcome':row['outcome']}),flush=True)
            if sum(r['outcome']=='TRANSPORT_FAILURE' for r in rows)/len(rows)>=.1:
                failures.append({'classification':'TRANSPORT_FAILURE','reason':'Registered>=10% transport threshold'});break
            if row['outcome']=='MODEL_FAILURE':
                failures.append({'classification':'MODEL_DECISION_FAILURE','reason':'Schema/format gate failed; no rescoring'});break
        if failures:break
    baseline=[r['metrics']['regret_quality'] for r in rows if r['mode']=='A' and r['outcome']=='OK']
    passed=len(rows)==16 and all(r['outcome']=='OK' for r in rows) and .3<=statistics.mean(baseline)<.95
    if len(baseline)==4 and not passed and not failures:
        failures.append({'classification':'QA_WORLD_BUG','reason':'P1 baseline ceiling or unsuitable difficulty; no expansion'})
    result={'difficulty_gate':'PASS' if passed else 'FAIL_OR_INCOMPLETE','calls':len(rows),'complete':sum(r['outcome']=='OK' for r in rows),
        'baseline_A_mean':statistics.mean(baseline) if baseline else None,'failures':failures,'main_calls':0,
        'main_decision':'Separate after-pilot decision required; not started','causal_utility':'INCONCLUSIVE'}
    (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result
