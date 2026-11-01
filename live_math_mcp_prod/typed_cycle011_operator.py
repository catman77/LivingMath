"""Local operator authority; never registered as MCP tools. Linux DB/file access is trusted."""
import argparse
import json
import sys

from normalizer import canonical, digest
from research_store import ResearchStore
from typed_cycle011 import TypedCycle
from typed_cycle011_contract import ReceiptRequest, EXECUTOR
from typed_cycle011_store import connect, scope, assert_isolated


def activate(database, project, move_id, request_key):
    assert_isolated(database)
    store = ResearchStore(database); engine = TypedCycle(database)
    with connect(database) as c:
        row = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?', (move_id,project)).fetchone()
        if row is None: raise ValueError('NO_TYPED_PRECOMMIT')
        pc = json.loads(row['payload_json']); registered = scope(c, project)
        engine._sources_current(c, pc)
        view = store.moves._view(c, store.moves._row(c, project, move_id))
        existing = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
        if existing:
            if not view['execution_permission']['allowed']: raise ValueError('TERMINAL_OR_REVOKED_ACTIVATION')
            return dict(existing)
    # Only the local operator may create a narrowly scoped diagnostic disposition.
    for event_id, role in view.get('evidence_roles', {}).items():
        store.evidence_reviews.record(project, int(event_id), pc['obligation_id'], pc['obligation_version'],
            view['proposed_operation'], 'diagnostic_subject',
            'Isolated011 operator: failed guard is the diagnostic subject; surviving candidates only, not support for the failed premise.',
            ['event:' + str(event_id), 'event:' + str(registered['fixture_id'])],
            'typed011:review:' + str(move_id) + ':' + event_id, 'Explicit isolated QA operator')
    store.moves.audit(project, move_id, 'typed011:audit:' + request_key)
    with connect(database, True) as c:
        engine._sources_current(c, pc)
        row_move = store.moves._row(c, project, move_id); view = store.moves._view(c, row_move)
        if view['status'] != 'AUDITED' or view['audit']['verdict'] != 'EXPERIMENT_ALLOWED' or view['execution_permission']['needs_reaudit']:
            raise ValueError('ACTIVATION_REQUIRES_CURRENT_SUCCESSFUL_AUDIT')
        if c.execute('SELECT 1 FROM typed011_activations WHERE move_id=?',(move_id,)).fetchone(): raise ValueError('ACTIVATION_ALREADY_BOUND')
        audit_id = view['audits'][-1]['id']
        decision = {'allowed': True, 'operation':'bounded_experiment', 'scope':pc['scope'],
            'frontier_versions': {str(pc['obligation_id']):pc['obligation_version']},
            'transformation_allowed':False, 'proof_allowed':False}
        store.moves._append(c, move_id, 'EXPERIMENT_ALLOWED', 'Local operator activated exact typed011 precommit.', audit_id, decision, 'typed011:activate:' + request_key)
        op_id = c.execute('SELECT max(id) FROM operations').fetchone()[0]
        binding = {'precommit_id':row['id'], 'precommit_sha256':row['digest'], 'executor_id':EXECUTOR,
            'executor_code_sha256':registered['executor_code_sha256']}
        c.execute('INSERT INTO typed011_activations VALUES (?,?,?,?)',(move_id,audit_id,op_id,canonical(binding)))
        store._audit(c,'typed011_activation_bound',{'move_id':move_id,'activation_operation_id':op_id,'digest':digest(binding)})
        return {'move_id':move_id,'audit_id':audit_id,'activation_operation_id':op_id,**binding}


def commit(database, request):
    assert_isolated(database)
    req = ReceiptRequest.model_validate(request); payload = req.model_dump(); request_digest = digest({k:v for k,v in payload.items() if k!='request_key'})
    store = ResearchStore(database); engine = TypedCycle(database)
    with connect(database, True) as c:
        scope(c,req.project)
        prior_key = c.execute('SELECT * FROM typed011_receipts WHERE project=? AND request_key=?',(req.project,req.request_key)).fetchone()
        if prior_key and prior_key['request_digest'] != request_digest: raise ValueError('RECEIPT_REQUEST_KEY_CONFLICT')
        prior = c.execute('SELECT * FROM typed011_receipts WHERE project=? AND move_id=?',(req.project,req.move_id)).fetchone()
        if prior:
            if prior['request_digest'] != request_digest: raise ValueError('TERMINAL_RECEIPT_CONFLICT')
            return {**json.loads(prior['payload_json']), 'receipt_id':prior['id'],'idempotent':True}
        validated = engine.validate_in(c,req.project,req.move_id,req.event_id)
        if validated['status']!='VALID_BOUND_MEASUREMENT': raise ValueError(validated['status']+':'+validated['reason'])
        env = validated['envelope']
        if any(payload[k]!=env[k] for k in ('outcome','observed','summary','reason','proof_status')): raise ValueError('RECEIPT_RESULT_EVENT_CONFLICT')
        p = c.execute('SELECT * FROM typed011_precommits WHERE id=?',(validated['precommit_id'],)).fetchone()
        pc = json.loads(p['payload_json'])
        result = {'outcome':req.outcome,'summary':req.summary,'data':{'observed':payload['observed'],'measurement_event_id':req.event_id,
            'measurement_sha256':validated['event_sha256'],'precommit_sha256':p['digest']}}
        store.moves._append(c,req.move_id,'COMPLETED',req.reason,validated['audit_id'],
            {'allowed':False,'result':result,'evidence_refs':['event:'+str(req.event_id)],'completion_contract':'typed011/v1','proof_status':'unverified'},
            'typed011:commit:'+req.request_key)
        receipt = {**payload, **{k:validated[k] for k in ('precommit_id','precommit_sha256','audit_id','activation_operation_id','event_sha256')},
            'status':'COMPLETED','execution_permission':{'allowed':False},'artifact_inspection':validated['artifact_inspection'],
            'measurement_authenticity':validated['measurement_authenticity']}
        cursor = c.execute('INSERT INTO typed011_receipts(project,move_id,event_id,request_key,request_digest,payload_json) VALUES (?,?,?,?,?,?)',
            (req.project,req.move_id,req.event_id,req.request_key,request_digest,canonical(receipt)))
        receipt_id = cursor.lastrowid
        journal = {'receipt_id':receipt_id,'event_id':req.event_id,'event_sha256':validated['event_sha256'],
            'outcome':req.outcome,'obligation_version':pc['obligation_version'],'source_bindings':pc['source_bindings'],
            'raw_distinction':json.loads(p['preview_json'])['raw_distinction'], 'proof_status':'unverified'}
        c.execute('INSERT INTO typed011_journal(project,scope,source_family_id,claim_fingerprint,raw_sha256,receipt_id,payload_json) VALUES (?,?,?,?,?,?,?)',
            (req.project,pc['scope'],pc['source_family_id'],pc['claim_fingerprint'],pc['raw_distinction_sha256'],receipt_id,canonical(journal)))
        store._audit(c,'typed011_receipt_committed',{'receipt_id':receipt_id,'request_digest':request_digest,'receipt_sha256':digest(receipt),'journal_sha256':digest(journal)})
        return {**receipt,'receipt_id':receipt_id,'idempotent':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('action',choices=['activate','commit'])
    args=p.parse_args();data=json.loads(sys.stdin.buffer.read(65537))
    try:
        result=activate(args.db,**data) if args.action=='activate' else commit(args.db,data)
        print(json.dumps({'ok':True,'result':result}))
    except (ValueError,KeyError) as error:
        print(json.dumps({'ok':False,'error':str(error)}));raise SystemExit(2)


if __name__=='__main__':main()
