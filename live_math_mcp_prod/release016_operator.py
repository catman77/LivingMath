"""Operator-only016 atomic commit: unchanged014 transaction with native016 validator."""
import json
from normalizer import canonical,digest
from research_store import ResearchStore
from law_validation014_contract import ReceiptRequest014 as ReceiptRequest
from typed_cycle011_store import assert_isolated,connect,scope
from release016_typed import Validator016 as ReceiptValidator014


def commit(database, request):
    assert_isolated(database)
    req = ReceiptRequest.model_validate(request); payload = req.model_dump(); request_digest = digest({k:v for k,v in payload.items() if k!='request_key'})
    store = ResearchStore(database); engine = ReceiptValidator014(database)
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
            {'allowed':False,'result':result,'evidence_refs':['event:'+str(req.event_id)],'completion_contract':'typed014/v1','proof_status':'unverified'},
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

