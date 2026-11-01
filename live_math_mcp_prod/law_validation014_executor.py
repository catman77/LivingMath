"""Operator-local014 native instrument implementing the existing011 receipt wire format.

Protocol executor_id remains011/v1; this implementation has a different,
per-scope pinned code digest and an explicit source014 adapter identity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from normalizer import canonical,digest
from research_store import ResearchStore
from typed_cycle011 import TypedCycle,ordinal_parameters
from typed_cycle011_store import connect,scope,assert_isolated
from typed_cycle011_contract import MeasurementEnvelope,EXECUTOR
from law_validation014_native import Port,native_sha
from operational013_native import Ledger
from law_validation014_contract import ADAPTER,Envelope014


def execute(database,project,move_id,environment_file):
    assert_isolated(database)
    with connect(database) as c:
        registered=scope(c,project)
        row=c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON p.id=m.precommit_id WHERE m.move_id=? AND p.project=?',(move_id,project)).fetchone()
        activation=c.execute('SELECT * FROM typed011_activations WHERE move_id=?',(move_id,)).fetchone()
        if not row or not activation:raise ValueError('NO_TYPED_ACTIVATION')
        if c.execute('SELECT 1 FROM typed011_executions WHERE move_id=?',(move_id,)).fetchone():raise ValueError('EXECUTION_ALREADY_CONSUMED')
        pc=json.loads(row['payload_json']);TypedCycle._sources_current(c,pc)
        if pc['native_request']['source_adapter_id']!=ADAPTER:raise ValueError('WRONG_SOURCE_ADAPTER')
        reader=ResearchStore.__new__(ResearchStore);reader.path=Path(database)
        view=reader.moves._view(c,reader.moves._row(c,project,move_id))
        if not view['execution_permission']['allowed'] or view['audits'][-1]['id']!=activation['audit_id']:raise ValueError('STALE_OR_WRONG_TYPED_GRANT')
        code_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if code_sha!=registered['executor_code_sha256'] or native_sha()!=pc['native_definition_sha256']:raise ValueError('EXECUTOR_OR_NATIVE_CODE_DRIFT')
    # Actual hidden source history is opened only after scoped permission and code checks.
    raw_environment=Path(environment_file).read_bytes()
    if hashlib.sha256(raw_environment).hexdigest()!=registered['environment_sha256']:raise ValueError('ENVIRONMENT_COMMITMENT_DRIFT')
    environment=json.loads(raw_environment);declaration=environment['declaration']
    parameters={**declaration,'actions':['a'+str(i) for i in range(declaration['arity'])]}
    if digest(ordinal_parameters(parameters))!=pc['operation_definition_sha256'] or environment['project']!=project:
        raise ValueError('WRONG_NATIVE_SOURCE')
    if pc['suffix']!=[parameters['actions'][i] for i in pc['suffix_ordinals']]:raise ValueError('GRANTED_SUFFIX_MISMATCH')
    ledger=Ledger(pc['native_request']['budget']['native_calls']);ledger.stage='external_measurement'
    port=Port(declaration,ledger);state=port.load(environment['target_word']);flags=[]
    if pc['purpose']=='VALIDATE_TRANSFER' and environment['target_word']!=pc['context_word']:raise ValueError('ENVIRONMENT_OUTSIDE_DECLARED_CONTEXT')
    for a in pc['suffix_ordinals']:
        allowed=port.guard_image(port.inspect(state),a);flags.append(allowed)
        if not allowed:raise ValueError('NATIVE_GUARD_DENIED')
        state=port.extend(state,a)
        if not port.within_guard(port.inspect(state)):raise ValueError('ACTUAL_STATE_OUTSIDE_G')
    observed={'defined':True,'observation':port.observe(state,pc['observer']),'admissibility':flags}
    coordinate=port.inspect(state)
    matches=observed==pc['expected_readout']
    if pc['purpose']=='VALIDATE_TRANSFER':matches=matches and coordinate==pc['expected_coordinate']
    outcome='SUCCESS' if matches else 'FAILURE'
    artifact={'schema':'local-native014-executor/v1','precommit_sha256':row['digest'],'move_id':move_id,
              'observed':observed,'observed_coordinate':coordinate,'outcome':outcome,'costs':ledger.summary(),'raw_source_trace':ledger.rows,
              'source_adapter_id':ADAPTER,'proof_status':'unverified'}
    artifact_path=Path(registered['artifact_directory'])/('move-'+str(move_id)+'.json')
    artifact_raw=canonical(artifact).encode()
    with artifact_path.open('xb') as f:f.write(artifact_raw)
    env={k:pc[k] for k in ('project','proposal_fingerprint','obligation_id','obligation_version','scope','source_family_id',
         'source_bindings','native_definition_sha256','operation_definition_sha256','observer','test_id','suffix','suffix_ordinals','purpose','law_fingerprint','context_word')}
    env.update(precommit_id=row['id'],precommit_sha256=row['digest'],move_id=move_id,audit_id=activation['audit_id'],
        activation_operation_id=activation['operation_id'],predictions=pc['alternatives'],observed=observed,observed_coordinate=coordinate,outcome=outcome,
        executor_id=EXECUTOR,executor_code_sha256=code_sha,artifact_sha256=hashlib.sha256(artifact_raw).hexdigest(),
        summary='Source014 scoped native experiment '+outcome+'; not mathematical verification.',
        reason='Fresh post-activation source014 instrument replay of the fixed QA environment.')
    envelope=Envelope014.model_validate(env).model_dump()
    content={'claim_type':'EXPERIMENT_RESULT','statement':'Fresh independently executed synthetic source014 readout.',
        'scope':pc['scope'],'version':pc['obligation_version'],'outcome':outcome,'proof_status':'unverified',
        'measurement_binding':envelope,'observation':{'test_id':pc['test_id'],'readout':observed,'scope':pc['scope'],
            'version':pc['obligation_version'],'observer':pc['observer']}}
    store=ResearchStore(database)
    with connect(database) as c:TypedCycle._sources_current(c,pc)
    event=store.record(project,'counterexample' if outcome=='FAILURE' else 'experiment','Source014 post-activation measurement',
        canonical(content),'experiment',parent_id=pc['native_request']['question']['root_event_id'],request_key='014:measurement:'+str(move_id))
    local={'artifact_path':str(artifact_path),'artifact_sha256':envelope['artifact_sha256'],'envelope_sha256':digest(envelope)}
    with connect(database,True) as c:
        c.execute('INSERT INTO typed011_executions VALUES (?,?,?)',(move_id,event['id'],canonical(local)))
        store._audit(c,'typed011_executor_receipt',{'move_id':move_id,'event_id':event['id'],'digest':digest(local)})
    return {'event_id':event['id'],'envelope':envelope,'artifact_path':str(artifact_path),'costs':ledger.summary()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);args=p.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU,(5,6));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    try:print(canonical({'ok':True,'result':execute(args.db,**json.loads(sys.stdin.buffer.read(65537)))}))
    except (ValueError,KeyError,OSError) as error:print(canonical({'ok':False,'error':str(error)}));raise SystemExit(2)
