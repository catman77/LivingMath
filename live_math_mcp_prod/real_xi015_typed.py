"""One genuine Xi measurement through011/014, with an explicit diagnostic observer.

The observer counts violated complex-interval predictions. It is not Xi's
value or a zero label. All raw native complex edges remain in the artifact;
the validator independently recomputes this count before atomic commit.
No new model tool or operator authority is registered.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime,timezone
from normalizer import canonical,digest
from frontier import ResearchMoveFingerprint
from research_store import ResearchStore
from research_cycle009 import operation,MECHANISM
from typed_cycle011 import TypedCycle
from typed_cycle011_store import install,register_scope,connect,scope,assert_isolated
from typed_cycle011_operator import activate
from law_validation014_contract import Precommit014,Envelope014,ReceiptRequest014
from law_validation014_receipt import ReceiptValidator014
from law_validation014_store import install as guard_install
from real_xi015_math import assess
from real_xi015_source import load_native,native_block
from law_validation014 import select_validation

ADAPTER='actual-theta-xi015/v1'
OBSERVER={'projection':'primary','mod':None}
SOURCE=Path(__file__).resolve().parent


def choose_replay(policy,predictions,rename=False):
    """014 selects a fresh protocol replay; this is not an additional blind prediction."""
    class QueryLaw:
        status='CANDIDATE_TRANSPORT'
        binding={'observer':OBSERVER}
        def step(self,image,action):return [action+1]
    class ForecastQuestions:
        def guard_image(self,image,action):return action in range(len(policy['test_h']))
        def within_guard(self,image):return image[0] in range(1,len(policy['test_h'])+1)
        def observe_image(self,image,observer):
            h=policy['test_h'][image[0]-1]
            return digest([p['C_source_candidate'] for p in predictions if p['binding']['h']==h])
    domain=[{'id':('renamed-' if rename else 'theta-h-')+str(i),'ordinal':i,'word':[i],'cost':1} for i in range(len(policy['test_h']))]
    return select_validation(QueryLaw(),ForecastQuestions(),[0],[],domain,[])


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate_observer(question,rows):
    if question.get('observer_code_sha256')!=sha(SOURCE/'real_xi015_math.py'):raise ValueError('XI_OBSERVER_DEFINITION_DRIFT')
    expected=[p for p in question['predictions'] if p['binding']['h']==question['h']]
    if [r['index'] for r in rows]!=[p['index'] for p in expected]:raise ValueError('XI_SOURCE_ORDER_MISMATCH')
    failures=[]
    for p,row in zip(expected,rows):
        if (row['source_address'],row['origin_id'])!=(p['binding']['source_address'],p['binding']['origin_id']):raise ValueError('XI_ADDRESS_ORIGIN_MISMATCH')
        anchors=question['anchors'][str(row['index'])]
        score=assess(p['C_source_candidate'],row,anchors)
        if not score['PASS']:failures.append({'index':row['index'],'score':score})
    return len(failures),failures


class XiValidator(ReceiptValidator014):
    def validate_in(self,c,project,move_id,event_id):
        result=super().validate_in(c,project,move_id,event_id)
        if result['status']!='VALID_BOUND_MEASUREMENT':return result
        row=c.execute('SELECT p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?',(move_id,)).fetchone()
        pc=json.loads(row[0])
        root=c.execute('SELECT content FROM events WHERE id=? AND project=?',(pc['native_request']['question']['root_event_id'],project)).fetchone()
        question=read_question(json.loads(root[0]));local=c.execute('SELECT payload_json FROM typed011_executions WHERE move_id=?',(move_id,)).fetchone()
        artifact=json.loads(Path(json.loads(local[0])['artifact_path']).read_text())
        if pc['native_request']['source_adapter_id']!=ADAPTER or pc['native_definition_sha256']!=question['archive_sha256']:raise ValueError('XI_NATIVE_BINDING')
        if artifact['h']!=question['h'] or artifact['t']!=question['t'] or artifact['archive_sha256']!=question['archive_sha256']:raise ValueError('XI_PARAMETER_BINDING')
        if artifact['question_sha256']!=digest(question):raise ValueError('XI_QUESTION_BINDING')
        count,_=evaluate_observer(question,artifact['raw_theta_edges'])
        if result['envelope']['observed']['observation']!=count or result['envelope']['observed_coordinate']!=[count]:raise ValueError('XI_OBSERVER_RESULT_MISMATCH')
        result['measurement_authenticity']='UNCHANGED_ARCHIVAL_THETA_EVALUATOR_REPLAY; local trusted operator/executor boundary'
        result['observer_definition']='count of violated source-addressed complex-interval forecasts; not Xi-zero observation'
        return result


def execute(database,project,move_id,native_directory):
    assert_isolated(database)
    with connect(database) as c:
        registered=scope(c,project)
        row=c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?',(move_id,project)).fetchone()
        activation=c.execute('SELECT * FROM typed011_activations WHERE move_id=?',(move_id,)).fetchone()
        if not row or not activation:raise ValueError('NO_TYPED_ACTIVATION')
        if c.execute('SELECT 1 FROM typed011_executions WHERE move_id=?',(move_id,)).fetchone():raise ValueError('EXECUTION_ALREADY_CONSUMED')
        pc=json.loads(row['payload_json']);TypedCycle._sources_current(c,pc)
        reader=ResearchStore.__new__(ResearchStore);reader.path=Path(database)
        view=reader.moves._view(c,reader.moves._row(c,project,move_id))
        if not view['execution_permission']['allowed'] or view['audits'][-1]['id']!=activation['audit_id']:raise ValueError('STALE_TYPED_GRANT')
        if sha(__file__)!=registered['executor_code_sha256']:raise ValueError('XI_EXECUTOR_CODE_DRIFT')
        question=read_question(json.loads(c.execute('SELECT content FROM events WHERE id=?',(pc['native_request']['question']['root_event_id'],)).fetchone()[0]))
    # No source evaluation or future-value file is opened before the grant checks.
    if sha(question['archive_path'])!=question['archive_sha256']:raise ValueError('XI_ARCHIVE_DRIFT')
    import zipfile
    with zipfile.ZipFile(question['archive_path']) as z:
        manifest=json.loads(z.read('RH_XI_ROUTES_EXPORT_001/MANIFEST_SHA256.json'))
        for name in ('reproduce.py','vendor/intervals.py','vendor/source.py','vendor/ALGEBRAIC_NODES.json'):
            if sha(Path(native_directory)/name)!=manifest[name]:raise ValueError('XI_SOURCE_CODE_DRIFT:'+name)
    native=load_native(native_directory)
    rows=native_block(native,question['nodes'],question['origins'],question['h'],question['t'])
    count,failures=evaluate_observer(question,rows)
    observed={'defined':True,'observation':count,'admissibility':[True]};outcome='SUCCESS' if count==0 else 'FAILURE'
    artifact={'schema':'native-theta-xi015/v1','precommit_sha256':row['digest'],'move_id':move_id,'observed':observed,
        'observed_coordinate':[count],'outcome':outcome,'h':question['h'],'t':question['t'],'archive_sha256':question['archive_sha256'],
        'question_sha256':digest(question),'raw_theta_edges':rows,'failed_forecasts':failures,'native_theta_evaluate_calls':1}
    path=Path(registered['artifact_directory'])/('move-'+str(move_id)+'.json');raw=canonical(artifact).encode()
    with path.open('xb') as stream:stream.write(raw)
    env={k:pc[k] for k in ('project','proposal_fingerprint','obligation_id','obligation_version','scope','source_family_id','source_bindings',
        'native_definition_sha256','operation_definition_sha256','observer','test_id','suffix','suffix_ordinals','purpose','law_fingerprint','context_word')}
    env.update(precommit_id=row['id'],precommit_sha256=row['digest'],move_id=move_id,audit_id=activation['audit_id'],activation_operation_id=activation['operation_id'],
        predictions=pc['alternatives'],observed=observed,observed_coordinate=[count],outcome=outcome,
        executor_id='qa.external.native011/v1',executor_code_sha256=sha(__file__),artifact_sha256=hashlib.sha256(raw).hexdigest(),
        summary='Fresh actual theta-source interval-comparison measurement; '+outcome+' is not a proof.',
        reason='Original source recomputed after activation; no reuse of the P0 measurement artifact.')
    envelope=Envelope014.model_validate(env).model_dump()
    content={'claim_type':'EXPERIMENT_RESULT','statement':'Fresh native Xi theta block replay.','scope':pc['scope'],'version':pc['obligation_version'],
        'outcome':outcome,'proof_status':'unverified','measurement_binding':envelope,
        'observation':{'test_id':pc['test_id'],'readout':observed,'scope':pc['scope'],'version':pc['obligation_version'],'observer':pc['observer']}}
    store=ResearchStore(database)
    event=store.record(project,'experiment' if outcome=='SUCCESS' else 'counterexample','Fresh native theta Xi measurement',canonical(content),'experiment',
        parent_id=pc['native_request']['question']['root_event_id'],request_key='xi015:measure:'+str(move_id))
    local={'artifact_path':str(path),'artifact_sha256':envelope['artifact_sha256'],'envelope_sha256':digest(envelope)}
    with connect(database,True) as c:
        c.execute('INSERT INTO typed011_executions VALUES (?,?,?)',(move_id,event['id'],canonical(local)))
        store._audit(c,'typed011_executor_receipt',{'move_id':move_id,'event_id':event['id'],'digest':digest(local)})
    return {'event_id':event['id'],'envelope':envelope,'artifact_path':str(path)}


def prepare(base):
    meta=json.loads((base/'metadata.json').read_text());current=json.loads((base/'current.json').read_text());out=Path(current['output']);db=Path(current['database'])
    if json.loads((out/'result.json').read_text())['status']!='BLIND_PREDICTION_PASS_TYPED_PENDING':raise ValueError('P0_GATE_NOT_PASSED')
    install(db,meta['canonical']);guard_install(db)
    audit=json.loads((base/'audited-input.json').read_text());policy=json.loads((base/'frozen-split.json').read_text());manifest=json.loads((base/'source-manifest.json').read_text())
    predictions=[json.loads(s) for s in (out/'sealed-predictions.jsonl').read_text().splitlines()]
    selected=choose_replay(policy,predictions);renamed=choose_replay(policy,predictions,True)
    if selected['selected']['word']!=renamed['selected']['word']:raise ValueError('SOURCE_NEUTRAL_ATTENTION_RENAME')
    (out/'T014-protocol-replay-selection.json').write_text(canonical({'selected':selected,'renamed':renamed,
        'scope':'Post-P0 selection for fresh typed measurement; does not retroactively claim to have driven the original blind evaluations.'})+'\n')
    chosen_h=policy['test_h'][selected['selected']['word'][0]]
    suffix=datetime.now(timezone.utc).strftime('%H%M%S%f')
    project='LM_QA_TYPED011_XI015_'+out.name[-12:]+'_'+suffix;scoped='XI015/'+project;store=ResearchStore(db)
    question={'h':chosen_h,'t':policy['t'],'archive_path':manifest['archive'],'archive_sha256':manifest['archive_sha256'],
        'observer_code_sha256':sha(SOURCE/'real_xi015_math.py'),
        'nodes':audit['nodes'],'origins':audit['origins'],
        'predictions':[p for p in predictions if p['binding']['h']==chosen_h],
        'anchors':{str(i):[audit['selected']['0'][str(i)],audit['selected']['1'][str(i)]] for i in range(32)},
        'observer':'interval-agreement-count/v1; zero means no failed forecasts, not a Xi zero'}
    # Store the strict question in an inspectable immutable artifact, keeping event content bounded.
    question_file=Path(current['public'])/('typed-question-'+suffix+'.json');question_file.write_text(canonical(question))
    q_sha=digest(question);small={k:v for k,v in question.items() if k not in {'nodes','origins','predictions','anchors'}}
    fixture_data={'claim_type':'SOURCE_CLAIM','scope':scoped,'version':1,'fixture_sha256':q_sha,'environment_commitment':q_sha}
    def record(name,data):
        value=store.record(project,'qa_source',name,canonical(data),'hypothesis',request_key=project+':'+name)
        with store._connect() as c:return dict(c.execute('SELECT * FROM events WHERE id=?',(value['id'],)).fetchone())
    fixture=record('archive-and-observer',fixture_data)
    root=record('exact Xi question',{'claim_type':'HYPOTHESIS','theta_question_file':str(question_file),'theta_question_sha256':q_sha,'scope':scoped,'version':1})
    imported=store.frontier.import_history({'import_key':project+':allow','project':project,'sources':[{'id':fixture['id'],'sha256':digest(fixture)}],
        'obligations':[{'key':'xi','statement':'Fresh bounded native theta replay, never a proof of RH.','scope':scoped,'source_event_ids':[fixture['id'],root['id']],'evidence_refs':[]}],
        'constraints':[{'kind':'allowed_experiment','obligation_key':'xi','mechanisms':[MECHANISM],'scope':scoped,'source_event_ids':[fixture['id']],
            'source_representations':['fixture009:'+q_sha],'reason':'Only this archive, ordered block, h/t, observer and typed precommit.',
            'reopen_conditions':['New source binding and explicit review required.']}]},'User-authorized actual Xi015 private operator')
    directory=Path(current['public'])/('typed-artifacts-'+suffix);directory.mkdir()
    op_sha=digest({'question':q_sha,'observer':'interval-agreement-count/v1','native':manifest['archive_sha256']})
    register_scope(db,project,{'scope':scoped,'fixture_id':fixture['id'],'fixture_sha256':digest(fixture),'fixture_content_sha256':q_sha,
        'source_family_id':digest({'archive':manifest['archive_sha256'],'block':list(range(32))}),'operation_definition_sha256':op_sha,
        'native_definition_sha256':manifest['archive_sha256'],'executor_code_sha256':sha(__file__),'environment_sha256':q_sha,'artifact_directory':str(directory)})
    with connect(db) as c:events=[dict(r) for r in c.execute('SELECT * FROM events WHERE project=?',(project,))];registered=scope(c,project)
    bindings=[{'event_id':e['id'],'sha256':digest(e)} for e in events]
    native_req={'project':project,'active_frontier_id':imported['obligation_ids']['xi'],'active_frontier_version':1,
        'source_event_ids':[e['id'] for e in events],'source_adapter_id':ADAPTER,'source_bindings':bindings,'observer':OBSERVER,
        'question':{'root_event_id':root['id'],'left_history_id':fixture['id'],'right_history_id':root['id']}}
    expected={'defined':True,'observation':0,'admissibility':[True]};test='native-theta-h'+question['h']
    op=operation({'fixture_sha256':q_sha},test,expected,'actual Xi source validation');op['premises']+=['Exact source question '+q_sha]
    pc=Precommit014(project=project,obligation_id=imported['obligation_ids']['xi'],obligation_version=1,scope=scoped,native_request=native_req,
        source_bindings=bindings,source_family_id=registered['source_family_id'],native_definition_sha256=manifest['archive_sha256'],operation_definition_sha256=op_sha,
        observer=OBSERVER,test_id=test,suffix=['set-h:'+question['h']],suffix_ordinals=[0],admissibility_guard=[True],
        alternatives=[{'kind':'ACTUAL_XI_SOURCE_FORECAST_TEST','question_sha256':q_sha,'readout':expected}],tested_hypothesis='source-supplied exponential transport',
        expected_readout=expected,expected_coordinate=[0],proposal_fingerprint=ResearchMoveFingerprint.build(op).digest,
        claim_fingerprint=digest({'archive':manifest['archive_sha256'],'h':question['h'],'block':list(range(32))}),raw_distinction_sha256=q_sha,
        preview_digest=q_sha,purpose='VALIDATE_TRANSFER',law_fingerprint=digest({'source_expression':'A*exp(epsilon*u*(h+i*t))','archive':manifest['archive_sha256']}),context_word=[0,31,32]).model_dump()
    preview={'preview_digest':q_sha,'raw_distinction':{'question':small,'source_question_sha256':q_sha}}
    with connect(db,True) as c:
        TypedCycle._sources_current(c,pc)
        cur=c.execute('INSERT INTO typed011_precommits(project,request_key,request_sha,digest,payload_json,operation_json,preview_json) VALUES (?,?,?,?,?,?,?)',
            (project,'xi015',digest(native_req),digest(pc),canonical(pc),canonical(op),canonical(preview)))
        row=dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?',(cur.lastrowid,)).fetchone())
        store._audit(c,'typed011_precommitted',{'precommit_id':row['id'],'digest':row['digest']})
    linked=TypedCycle(db)._link(row)
    return {'database':str(db),'project':project,'move_id':linked['move_id'],'precommit':linked,'question_sha256':q_sha,'native_directory':meta['raw'],'out':str(out)}


def read_question(data):
    path=Path(data['theta_question_file']);question=json.loads(path.read_text())
    if digest(question)!=data['theta_question_sha256']:raise ValueError('XI_QUESTION_ARTIFACT_DRIFT')
    return question


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--db',type=Path);args=p.parse_args()
    if args.execute:
        try:print(canonical({'ok':True,'result':execute(args.db,**json.loads(sys.stdin.read()))}))
        except (ValueError,KeyError,OSError) as error:print(canonical({'ok':False,'error':str(error)}));raise SystemExit(2)
    else:
        result=prepare(Path(Path('/tmp/lm015_path').read_text().strip()));print(canonical(result))
