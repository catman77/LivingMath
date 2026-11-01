"""Explicit local synthetic instrument; never imported by the controller/I/T."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

from normalizer import canonical, digest
from live_constructive007_native import Port, Ledger, native_fingerprint
from research_store import ResearchStore
from typed_cycle011 import TypedCycle, ordinal_parameters
from typed_cycle011_contract import MeasurementEnvelope, EXECUTOR
from typed_cycle011_store import connect, scope, assert_isolated


def execute(database, move_id, project, world_file, environment_file, instrument_outcome=None):
    assert_isolated(database)
    started=time.perf_counter_ns()
    if instrument_outcome not in {None,'INCONCLUSIVE','ERROR'}: raise ValueError('INVALID_INSTRUMENT_CONTROL')
    with connect(database) as c:
        registered=scope(c,project)
        row=c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON p.id=m.precommit_id WHERE m.move_id=? AND p.project=?',(move_id,project)).fetchone()
        activation=c.execute('SELECT * FROM typed011_activations WHERE move_id=?',(move_id,)).fetchone()
        if not row or not activation: raise ValueError('NO_TYPED_ACTIVATION')
        if c.execute('SELECT 1 FROM typed011_executions WHERE move_id=?',(move_id,)).fetchone(): raise ValueError('EXECUTION_ALREADY_CONSUMED')
        pc=json.loads(row['payload_json']);TypedCycle._sources_current(c,pc)
        reader=ResearchStore.__new__(ResearchStore);reader.path=Path(database)
        move=reader.moves._row(c,project,move_id);view=reader.moves._view(c,move)
        if not view['execution_permission']['allowed'] or view['audits'][-1]['id']!=activation['audit_id']:raise ValueError('STALE_OR_WRONG_TYPED_GRANT')
        executor_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if executor_sha!=registered['executor_code_sha256'] or native_fingerprint()!=pc['native_definition_sha256']:raise ValueError('EXECUTOR_OR_NATIVE_CODE_DRIFT')
    # No hidden environment is opened before the exact scoped grant checks above.
    world=json.loads(Path(world_file).read_text())
    if world['project']!=project or digest(ordinal_parameters(world['parameters']))!=pc['operation_definition_sha256']:raise ValueError('WRONG_EXECUTED_SOURCE')
    env_bytes=Path(environment_file).read_bytes()
    if hashlib.sha256(env_bytes).hexdigest()!=registered['environment_sha256']:raise ValueError('SEALED_ENVIRONMENT_COMMITMENT_DRIFT')
    environment=json.loads(env_bytes)
    if environment['parameters']!=world['parameters'] or environment['fixture_sha256']!=world['fixture_sha256']:raise ValueError('SEALED_SOURCE_IDENTITY_DRIFT')
    test=next(t for t in world['tests'] if t['id']==pc['test_id'])
    if test['suffix']!=pc['suffix']:raise ValueError('GRANTED_SUFFIX_MISMATCH')
    ledger=Ledger(pc['native_request']['budget']['native_calls'],5);ledger.stage='external_measurement'
    port=Port(world['parameters'],ledger);state=port.load(environment['target_word']);flags=[]
    for action in pc['suffix']:
        allowed=port.admissible(state,action);flags.append(allowed)
        if not allowed:raise ValueError('MEASUREMENT_ADMISSIBILITY_DENIED')
        state=port.extend(state,action)
    observed={'defined':True,'observation':port.observe(state,pc['observer']),'admissibility':flags}
    outcome=instrument_outcome or ('SUCCESS' if observed==pc['expected_readout'] else 'FAILURE')
    artifact={'schema':'local-native-executor/v1','precommit_sha256':row['digest'],'move_id':move_id,
        'observed':observed,'outcome':outcome,'cost_ledger':ledger.summary(),'private_native_trace':ledger.trace,
        'instrument_wall_ns':time.perf_counter_ns()-started}
    directory=Path(registered['artifact_directory']);directory.mkdir(exist_ok=True)
    artifact_path=directory/('move-'+str(move_id)+'.json')
    raw=canonical(artifact).encode()
    with artifact_path.open('xb') as out:out.write(raw)
    env={k:pc[k] for k in ('project','proposal_fingerprint','obligation_id','obligation_version','scope','source_family_id',
        'source_bindings','native_definition_sha256','operation_definition_sha256','observer','test_id','suffix','suffix_ordinals')}
    env.update(precommit_id=row['id'],precommit_sha256=row['digest'],move_id=move_id,audit_id=activation['audit_id'],
        activation_operation_id=activation['operation_id'],predictions=pc['alternatives'],observed=observed,outcome=outcome,
        executor_id=EXECUTOR,executor_code_sha256=executor_sha,artifact_sha256=hashlib.sha256(raw).hexdigest(),
        summary='External bounded native readout of '+pc['test_id']+'; '+outcome+' is not mathematical verification.',
        reason='Explicit scoped local synthetic instrument'+(' control '+instrument_outcome if instrument_outcome else '')+'.')
    envelope=MeasurementEnvelope.model_validate(env).model_dump()
    content={'claim_type':'EXPERIMENT_RESULT','statement':'Fresh independently executed finite readout; unverified.',
        'scope':pc['scope'],'version':pc['obligation_version'],'test_id':pc['test_id'],'outcome':outcome,'proof_status':'unverified',
        'measurement_binding':envelope,'observation':{'test_id':pc['test_id'],'readout':observed,'scope':pc['scope'],
            'version':pc['obligation_version'],'observer':pc['observer']}}
    store=ResearchStore(database)
    # Source hashes/version are checked again immediately before append; commit rechecks transactionally.
    with connect(database) as c:TypedCycle._sources_current(c,pc)
    event=store.record(project,'counterexample' if outcome=='FAILURE' else 'experiment','Fresh typed011 external measurement',
        canonical(content),'experiment',parent_id=pc['native_request']['question']['root_event_id'],request_key='typed011:measurement:'+str(move_id))
    local={'artifact_path':str(artifact_path),'artifact_sha256':envelope['artifact_sha256'],'envelope_sha256':digest(envelope)}
    with connect(database,True) as c:
        c.execute('INSERT INTO typed011_executions VALUES (?,?,?)',(move_id,event['id'],canonical(local)))
        store._audit(c,'typed011_executor_receipt',{'move_id':move_id,'event_id':event['id'],'digest':digest(local)})
    return {'event_id':event['id'],'envelope':envelope,'artifact_path':str(artifact_path),'costs':artifact['cost_ledger']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);args=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CPU,(5,6));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    try: print(json.dumps({'ok':True,'result':execute(args.db,**json.loads(sys.stdin.buffer.read(65537)))}))
    except (ValueError,KeyError,OSError) as error:
        print(json.dumps({'ok':False,'error':str(error)}));raise SystemExit(2)


if __name__=='__main__':main()
