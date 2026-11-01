"""Six-call held-out005 difficulty pilot with no current oracle/ranking in inputs."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

import jsonschema
from causal_model import stop_process_group
from live_core005 import interpret_distinction,transfer_attention
from live_core005_worlds import create_world,build_view
from live_core005_oracle import all_pairs,attention,source_spec
from normalizer import canonical,digest,ENCODING
from normalization_pilot import retained_branch
from qa_positive_acceptance import write_json

MODEL='gpt-6-luna'
TOKENS=7000
TIMEOUT=120


def schema() -> dict:
    p={'test_id':{'type':'string'},'novelty':{'enum':['new_distinction','no_new_distinction','insufficient_context']},
       'left_ref':{'type':'string'},'right_ref':{'type':'string'},'witness_suffix':{'type':'array','items':{'type':'integer'},'maxItems':2},
       'source_version':{'type':'integer'},'evidence_refs':{'type':'array','items':{'type':'string'}},
       'retained_independent_ids':{'type':'array','items':{'type':'string'}},'reason':{'type':'string'},'proof_status':{'const':'unverified'}}
    return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}


def prepare(base: Path) -> list:
    directory=base/'pilot';directory.mkdir();tasks=[]
    configs=[([2,3,5,7,11],[0,5,1,3,6,2,2,4]),([7,2,11,3,5],[0,4,2,1,5,3,2,4])]
    for index,(weights,costs) in enumerate(configs):
        world=create_world(directory/f'fixture{index}.sqlite3',1+4*index,weights=weights,costs=costs)
        view=build_view(world);spec=source_spec(world['history'],world['query'])
        oracle=attention(world['history'],world['query']);pairs=all_pairs(world['history'],world['query'])
        assert len({r['loss'] for r in oracle['ranks']})>1
        normalized=[{'source_fields':json.loads(c['source_record']['content']),'source_refs':c['source_refs'],
                     'scope':c['scope'],'representation':c['representation'],'unknowns':c['unknowns']} for c in view['concepts']]
        original={'event:'+str(r['id']):json.loads(r['content']) for r in world['history']['tables']['events']}
        assert {n['source_refs'][0]['ref']:n['source_fields'] for n in normalized}==original
        interpretation=interpret_distinction(view,world['history'],world['query'],world['refs']['h3'],world['refs']['h0'])
        proposed=transfer_attention(view,world['history'],world['query'])
        # Deliberately withhold current T selection/ranking and all complete predictions.
        t_preview={'remaining_alternative_ids':[h['id'] for h in proposed['hypotheses'] if h['question']=='current' and h['predictive']],
                   'unknowns':proposed['unknowns'],'execution_allowed':False,'proof_status':'unverified'}
        inputs={'A':{'source_records':[dict(r,sha256=digest(r)) for r in world['history']['tables']['events']]},
                'B':{'normalized_source_map':normalized},
                'C':{'normalized_source_map':normalized,'I_constructed_witness':interpretation,'T_uncertainty_preview':t_preview}}
        task={'index':index,'world':world,'oracle':oracle,'pair_oracle':pairs,'source_atoms_equal':True,
              'I_origin':'experimental native arithmetic algorithm','T_current_selection_withheld':True,'prompts':{}}
        common=('Finite QA005, no tools/files/commands/network/skills/agents. Claims unverified. No actual hidden history supplied. '
          'Choose ONE informative registered current test minimizing cost +7/3 times expected remaining alternative COUNT. '
          'Prior draw probability is each current predictive hypothesis weight / total weight. '
          'An outcome is the pair (declared observer after suffix, admissibility); remaining count is the number of current '
          'predictive hypotheses with that same pair. Ignore independent-question hypotheses in that loss, retain their branch. '
          'Compute from the native source rules, NOT display names. Also propose a finite hidden-distinction witness pair '
          'with equal current observation and unequal future observation/admissibility, or state no distinction/context. '
          'Use event:N references, source version1 and unverified. Keep independent I or its event reference. '
          'No grant/completion/proof is created. Reason<=120 words. Return only schema JSON.\nDATA\n')
        for mode in 'ABC':
            text=common+canonical(inputs[mode])+'\nEND DATA\nIGNORABLE PADDING:'
            count=len(ENCODING.encode(text))
            if count>TOKENS:raise ValueError('QA_WORLD_BUG matched token budget exceeded')
            text+=' x'*(TOKENS-count);assert len(ENCODING.encode(text))==TOKENS
            assert 'optimal_test_ids' not in text and 'expected_remaining' not in text and '"ranking"' not in text
            label='p'+digest([index,mode])[:16]
            path=directory/'frozen-prompts'/f'{label}.txt';path.parent.mkdir(exist_ok=True);path.write_text(text)
            task['prompts'][mode]=str(path.relative_to(directory))
        tasks.append(task)
    write_json(directory/'tasks.json',tasks);write_json(directory/'schema.json',schema())
    write_json(directory/'preregistration.json',{'protocol':'005.P1.1','max_calls':6,'model':MODEL,'reasoning':'low',
        'concurrency':1,'timeout':TIMEOUT,'matched_user_tokens_estimated':TOKENS,'provider_seed':None,'immutable_build':None,'output_cap':None,
        'codex_version':subprocess.check_output(['codex','--version'],text=True).strip(),
        'order':[[0,'A'],[1,'A'],[0,'B'],[0,'C'],[1,'B'],[1,'C']],
        'gate':'P0 PASS; baseline mean quality in[.25,.95); any transport/schema/tool failure stops. No retries.',
        'metric':'Frozen oracle loss regret; noninformative/unregistered tests receive worst informative-test loss.',
        'coverage':'Paired complete cases; no imputation; causal claims require>=90% and remain exploratory with2 tasks.',
        'C_ablation':'I witness and T uncertainty preview only; current selected test/ranking withheld to prevent ready-answer leakage.',
        'main':'Separate decision only,0/24 automatic','build_seed_output_cap_known':False})
    files=[directory/'tasks.json',directory/'schema.json',directory/'preregistration.json',*(directory/'frozen-prompts').glob('*.txt')]
    files += list(Path(__file__).parent.glob('live_core005*.py'))
    write_json(directory/'immutable-manifest.json',{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    return tasks


async def infer(directory: Path, prompt: str) -> dict:
    directory.mkdir(parents=True);(directory/'empty').mkdir()
    (directory/'prompt.txt').write_text(prompt);write_json(directory/'schema.json',schema())
    cmd=['bwrap','--bind','/','/','--ro-bind','/dev/null',str(Path.home()/'.codex/AGENTS.md'),'--chdir',str(directory/'empty'),
         'codex','--no-daemon','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check','--sandbox','read-only',
         '-m',MODEL,'-c','project_doc_max_bytes=0','-c','features.apps=false','-c','features.plugins=false','-c','features.multi_agent=false',
         '-c','features.skill_search=false','-c','model_reasoning_effort="low"','--json','--output-schema',str(directory/'schema.json'),'-o',str(directory/'output.json'),'-']
    env={k:v for k,v in os.environ.items() if k not in {'OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL','ANTHROPIC_API_KEY','AZURE_OPENAI_API_KEY'}}
    row={'outcome':'TRANSPORT_FAILURE','model_requested':MODEL,'reasoning':'low','provider_seed':None,'immutable_build':None,
         'output_cap':None,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'user_tokens_estimated':TOKENS,'retries':0}
    start=time.monotonic()
    with (directory/'events.jsonl').open('w') as out,(directory/'stderr.txt').open('w') as err:
        proc=await asyncio.create_subprocess_exec(*cmd,stdin=asyncio.subprocess.PIPE,stdout=out,stderr=err,env=env,start_new_session=True)
        try:await asyncio.wait_for(proc.communicate(prompt.encode()),TIMEOUT)
        except asyncio.TimeoutError:
            await stop_process_group(proc);row['timeout']=True
        except asyncio.CancelledError:
            await stop_process_group(proc);raise
    events=[]
    for line in (directory/'events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:row['invalid_event_json']=True
    tools=[e for e in events if (e.get('item') or {}).get('type') not in {None,'reasoning','agent_message'}]
    row.update(wall_seconds=time.monotonic()-start,exit_code=proc.returncode,tool_events=len(tools),
               usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None))
    if proc.returncode==0 and not row.get('timeout'):
        row['outcome']='MODEL_FAILURE'
        try:
            answer=json.loads((directory/'output.json').read_text());jsonschema.validate(answer,schema())
            if tools or row.get('invalid_event_json') or len(answer['reason'].split())>120:raise ValueError('Tool/format/word gate')
            row.update(outcome='OK',output=answer)
        except (ValueError,OSError,jsonschema.ValidationError) as error:row['error']=str(error)
    write_json(directory/'receipt.json',row);return row


def evaluate(task: dict, output: dict) -> dict:
    ranks=task['oracle']['ranks'];byid={r['test_id']:r for r in ranks}
    from fractions import Fraction
    low=min(Fraction(r['loss']) for r in ranks);high=max(Fraction(r['loss']) for r in ranks)
    loss=Fraction(byid[output['test_id']]['loss']) if output['test_id'] in byid else high
    pair=next((p for p in task['pair_oracle'] if {p['left_ref'],p['right_ref']}=={output['left_ref'],output['right_ref']}),None)
    valid=False
    if pair:
        a=next((s for s in pair['Sig_left'] if s['suffix']==output['witness_suffix']),None)
        b=next((s for s in pair['Sig_right'] if s['suffix']==output['witness_suffix']),None)
        valid=bool(pair['hidden_distinction'] and a and b and a['readout']!=b['readout'])
    refs=set(task['world']['refs'].values())
    return {'quality':float(1-(loss-low)/(high-low)),'loss':str(loss),'informative_test':output['test_id'] in byid,
        'false_novelty':output['novelty']=='new_distinction' and not (pair and pair['hidden_distinction']),
        'witness_valid':valid,'source_error':not set(output['evidence_refs'])<=refs or not output['evidence_refs'] or output['source_version']!=1,
        'independent_retained':retained_branch(output['retained_independent_ids'],task['world']),
        'mathematically_verified':False}


def run(base: Path, tasks: list) -> dict:
    directory=base/'pilot';rows=[];stop=None
    for index,mode in [(0,'A'),(1,'A'),(0,'B'),(0,'C'),(1,'B'),(1,'C')]:
        task=tasks[index];path=directory/task['prompts'][mode];label=path.stem
        row={'id':label,'task':index,'condition':mode,**asyncio.run(infer(directory/'models'/label,path.read_text()))}
        if row['outcome']=='OK':row['metrics']=evaluate(task,row['output'])
        rows.append(row)
        with (directory/'outputs.jsonl').open('a') as out:out.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({'P1':len(rows),'condition':mode,'outcome':row['outcome']}),flush=True)
        if row['outcome']!='OK':stop={'classification':row['outcome'],'reason':'Registered immediate stop; no retry'};break
        if len(rows)==2:
            mean=statistics.mean(r['metrics']['quality'] for r in rows)
            if not .25<=mean<.95:
                stop={'classification':'QA_WORLD_BUG','reason':'Baseline ceiling/floor gate','baseline_mean':mean};break
    result={'result':'STOP_WITH_RCA' if stop else 'DIFFICULTY_PASS_UTILITY_INCONCLUSIVE','calls':len(rows),
        'complete':sum(r['outcome']=='OK' for r in rows),'stop':stop,'main_calls':0,'utility':'INCONCLUSIVE',
        'baseline_A_mean':statistics.mean(r['metrics']['quality'] for r in rows if r['condition']=='A' and r['outcome']=='OK')
            if any(r['condition']=='A' and r['outcome']=='OK' for r in rows) else None}
    write_json(directory/'result.json',result);return result
