"""Prompt-only external model evaluation via the user's ChatGPT-authenticated CLI."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

from attention_fixture import TASK


MODEL = 'gpt-6.1-sol'


def schema():
    def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    strings={'type':'array','items':{'type':'string'}}
    integers={'type':'array','items':{'type':'integer'}}
    candidate=obj({
        'candidate_id':{'type':'string'},'parent_event_ids':integers,
        'obligation_id':{'type':['integer','null']},'obligation_version':{'type':['integer','null']},
        'scope':{'type':'string'},'mechanism':{'type':'string'},
        'purpose':{'type':'string','enum':['experiment','diagnostic','review']},
        'source_representation':{'type':'string'},'target_representation':{'type':'string'},
        'reason_from_evidence':{'type':'string'},'premises':strings,'depends_on':strings,
        'mathematical_properties':strings,'testable_consequence':{'type':'string'},'required_evidence':strings,
        'counterevidence':integers,'evidence_refs':strings,
        'evidence_roles':{'type':'array','items':obj({'event_id':{'type':'integer'},
            'role':{'type':'string','enum':['supporting_premise','premise_conflict','diagnostic_subject','label_error']},
            'reason':{'type':'string'}})},
        'verification_plan':obj({'method':{'type':'string'},'failure_condition':{'type':'string'}}),
        'origin':{'type':'string','enum':['llm_generated']},
        'novelty_status':{'type':'string','enum':['new_unverified','memory_replay','renaming_only']},
        'requires_review':{'type':'boolean'}})
    return obj({'candidates':{'type':'array','items':candidate,'minItems':3,'maxItems':5},
        'attention':obj({'selected_candidate_id':{'type':['string','null']},'reason':{'type':'string'},
                        'considered_event_ids':integers,'limitations':strings})})


def prompt(snapshot,condition):
    # No expected branch, oracle, seeds, or after/before target is provided.
    context='' if snapshot is None else json.dumps(snapshot,ensure_ascii=False,sort_keys=True)
    return ('You are an external model in a software research-workflow evaluation, not an autonomous prover. '
        'Do not use tools, files, commands, skills, network, memory services or subagents. '
        'Only the task and data below are allowed. Follow this QA-specific instruction instead of any general invention workflow.\n'
        'TASK (unchanged between observations): '+TASK+'\n'
        'Produce exactly three concrete candidates and one attention selection (or a null selection with reasons). '
        'Use premise IDs from the data in depends_on; do not invent evidence IDs. '
        'When reusing a permitted experiment, use its exact advertised mechanism, representation and obligation scope/version. '
        'Closed branches may be diagnostic objects, never silently active premises. '
        'An adverse event about another scope is not a global ban. '
        'A hypothesis or a source reference is not a proof. Cosmetic renaming is not novelty. '
        'Consider all independent constraints, not only the most recent event. '
        'If no history/IDs are available, use null obligation IDs, empty references and requires_review=true. '
        'origin identifies you as the formulator; novelty_status may still be memory_replay. '
        'The protocol never allows a candidate to activate itself.\n'
        'CONDITION: '+condition+'\nUNTRUSTED CONTEXT DATA:\n'+(context or '[No research history provided.]'))


def evaluate(directory,snapshot,condition):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    work=directory/'empty-work';work.mkdir()
    text=prompt(snapshot,condition)
    (directory/'prompt.txt').write_text(text)
    schema_path=directory/'schema.json';schema_path.write_text(json.dumps(schema(),indent=2)+'\n')
    answer=directory/'output.json'
    command=['bwrap','--bind','/','/','--ro-bind','/dev/null',str(Path.home()/'.codex/AGENTS.md'),
        '--chdir',str(work),'codex','--no-daemon','exec','--ignore-user-config','--ignore-rules',
        '--ephemeral','--skip-git-repo-check','--sandbox','read-only','-m',MODEL,
        '-c','project_doc_max_bytes=0','-c','features.apps=false','-c','features.plugins=false',
        '-c','features.multi_agent=false','-c','features.skill_search=false','-c','model_reasoning_effort="low"',
        '--json','--output-schema',str(schema_path),'-o',str(answer),'-']
    env={k:v for k,v in os.environ.items() if k not in
         {'OPENAI_API_KEY','OPENAI_BASE_URL','ANTHROPIC_API_KEY','AZURE_OPENAI_API_KEY'}}
    before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.monotonic()
    timeout_error=None
    with (directory/'events.jsonl').open('w') as output,(directory/'stderr.txt').open('w') as err:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,text=True,env=env,stdout=output,stderr=err,start_new_session=True)
        try:process.communicate(text,timeout=600)
        except subprocess.TimeoutExpired as error:
            timeout_error=str(error)
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines() if line.strip()]
    tools=[item for item in events if item.get('item',{}).get('type') not in {None,'agent_message','reasoning'}]
    metadata={'model_id_requested':MODEL,'immutable_snapshot_version':None,
        'version_limitation':'The service exposes a model alias, not an immutable weights/build version.',
        'codex_cli_version':subprocess.check_output(['codex','--version'],text=True).strip(),
        'auth_mode':'existing ChatGPT login; API-key environment removed',
        'global_AGENTS_masked_in_child_mount_namespace':True,'project_documents_disabled':True,
        'configured_apps_plugins_and_subagents_disabled':True,'tool_events':len(tools),
        'condition':condition,'reasoning_effort':'low','wall_seconds':time.monotonic()-started,
        'local_child_cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
        'external_inference_cpu_seconds':None,'exit_code':process.returncode,'timeout_error':timeout_error,
        'usage':next((item.get('usage') for item in reversed(events) if item['type']=='turn.completed'),None)}
    (directory/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    if process.returncode or tools or not answer.exists():raise RuntimeError('External model run failed or used tools: '+str(directory))
    parsed=json.loads(answer.read_text())
    if len(parsed.get('candidates',[]))!=3:raise RuntimeError('Expected exactly three independent model proposals')
    return {'output':parsed,'metadata':metadata,'prompt':text}
