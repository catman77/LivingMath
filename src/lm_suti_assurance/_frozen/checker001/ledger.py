"""Append-only source/claim/decision history with explicit generation provenance."""
from datetime import datetime,timezone
from pathlib import Path
import fcntl
from contracts import *


def append(path, payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX);handle.seek(0);rows=[strict_json(s) for s in handle.read().splitlines()]
        row={'sequence':len(rows)+1,'previous_hash':rows[-1]['row_digest'] if rows else None,'payload':payload}
        row['row_digest']=digest(row);handle.write(canonical(row)+'\n');handle.flush();fcntl.flock(handle,fcntl.LOCK_UN)
    return row


def read_chain(path):
    path=Path(path);rows=[strict_json(s) for s in path.read_text().splitlines()] if path.exists() else [];previous=None
    for no,row in enumerate(rows,1):
        if row['sequence']!=no or row['previous_hash']!=previous or row['row_digest']!=digest({k:v for k,v in row.items() if k!='row_digest'}):raise ValueError('APPEND_CHAIN_INVALID')
        previous=row['row_digest']
    return rows


def record(root,candidate,decision,witnesses,*,request_key,lineage=None,actual_generator=None):
    root=Path(root);row={'schema':'symseq.assurance.artifact.v1','task_id':(actual_generator or {}).get('task_id',candidate.get('task_id')),'candidate':candidate,'candidate_full_digest':digest(candidate),
        'claim_digest':claim_digest(candidate),'source_digest':decision['source_digest'],'scope_digest':decision['scope_digest'],
        'witnesses':witnesses,'decision':decision,'lineage':lineage or [],'request_key':request_key,
        'source_status':'BYTE_BOUND' if decision['check_kind']!='NONE' else 'NOT_ATTESTED',
        'evidence_status':'CHECKED_FOR_DECLARED_PROPERTY' if decision['check_kind']!='NONE' else 'NOT_CHECKED',
        'check_status':decision['decision'],'assurance_status':decision['assurance_status'],
        'execution_permission':False,'actual_generator':actual_generator or {'kind':'symbolic','self_report_trusted':False}}
    row['artifact_digest']=digest(row)
    with (root/'artifact_transaction.lock').open('a+') as transaction:
        fcntl.flock(transaction,fcntl.LOCK_EX)
        existing=[x['payload'] for x in read_chain(root/'ARTIFACT_LEDGER.jsonl') if x['payload']['request_key']==request_key]
        if existing:
            if existing[0]['artifact_digest']!=row['artifact_digest']:raise ValueError('REQUEST_KEY_CONFLICT')
            return existing[0]
        append(root/'ARTIFACT_LEDGER.jsonl',row);append(root/'DECISION_LEDGER.jsonl',{'artifact_digest':row['artifact_digest'],'decision':decision,'witnesses':witnesses})
        append(root/'STATUS_TRANSITIONS.jsonl',{'artifact_digest':row['artifact_digest'],'from':'PROPOSED','to':decision['assurance_status'],'decision_digest':decision['decision_digest'],'execution_permission':False})
        return row
