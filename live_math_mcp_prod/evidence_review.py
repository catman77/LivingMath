"""Scoped operator dispositions of cited adverse data, never truth judgments."""
import json
import re
import time

from frontier import ResearchMoveFingerprint, canonical, fingerprint_hash, text


SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS adverse_evidence_reviews(
 id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
 event_id INTEGER NOT NULL REFERENCES events(id),
 obligation_id INTEGER NOT NULL REFERENCES research_obligations(id),
 frontier_version INTEGER NOT NULL, scope TEXT NOT NULL, fingerprint TEXT NOT NULL,
 payload_json TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 created_at INTEGER NOT NULL, UNIQUE(project,request_key));
CREATE TRIGGER IF NOT EXISTS evidence_reviews_no_update BEFORE UPDATE ON adverse_evidence_reviews
 BEGIN SELECT RAISE(ABORT,'evidence reviews are append-only'); END;
CREATE TRIGGER IF NOT EXISTS evidence_reviews_no_delete BEFORE DELETE ON adverse_evidence_reviews
 BEGIN SELECT RAISE(ABORT,'evidence reviews are append-only'); END;
'''
ROLES = {'supporting_premise', 'premise_conflict', 'diagnostic_subject', 'label_error'}
DISPOSITIONS = {'diagnostic_subject', 'label_error'}


def cited_event_ids(move):
    ids = set(move.get('parent_event_ids') or [])
    def walk(value):
        if isinstance(value, dict):
            for key, entry in value.items():
                if key in {'evidence_refs', 'required_evidence'} and isinstance(entry, list):
                    for ref in entry:
                        if isinstance(ref, str):
                            ids.update(int(i) for i in re.findall(r'(?<!\w)event:(\d+)(?=\D|$)', ref))
                else:
                    walk(entry)
        elif isinstance(value, list):
            for entry in value: walk(entry)
    walk(move)
    return ids


class EvidenceReviews:
    def __init__(self, store):
        self.store = store

    def inspect(self, project):
        with self.store._connect() as connection:
            return [{'id': row['id'], **json.loads(row['payload_json'])} for row in connection.execute(
                'SELECT * FROM adverse_evidence_reviews WHERE project=? ORDER BY id', (project,))]

    def assess(self, connection, project, move):
        from research_store import FAILURE_KINDS, FAILURE_STATUSES
        ids = cited_event_ids(move)
        roles = move.get('evidence_roles') or {}
        if not isinstance(roles, dict): raise ValueError('evidence_roles must be an object keyed by cited event ID')
        for key, value in roles.items():
            if not isinstance(key, str) or not key.isdecimal() or int(key) not in ids:
                raise ValueError('evidence role must reference a cited project event')
            if not isinstance(value, dict) or value.get('role') not in ROLES:
                raise ValueError('invalid evidence role')
            text(value.get('reason'), 'evidence role reason')
        active = self.store.frontier._obligation(connection, move['active_frontier_id']) if move.get('active_frontier_id') else None
        if active and active['project'] != project: raise ValueError('active frontier belongs to another project')
        fingerprint = ResearchMoveFingerprint.build(move.get('proposed_operation', {})).digest
        findings = []
        for event_id in sorted(ids):
            event = connection.execute('SELECT * FROM events WHERE id=? AND project=?', (event_id, project)).fetchone()
            if event is None: raise ValueError('cited event missing or belongs to another project')
            if event['kind'] not in FAILURE_KINDS and event['status'] not in FAILURE_STATUSES:
                continue
            role = roles.get(str(event_id), {}).get('role', 'supporting_premise')
            review = None
            if active:
                review = connection.execute('''SELECT * FROM adverse_evidence_reviews WHERE project=?
                    AND event_id=? AND obligation_id=? AND frontier_version=? AND scope=? AND fingerprint=?
                    ORDER BY id DESC LIMIT 1''', (project, event_id, active['id'], active['version'],
                                                 active['scope'], fingerprint)).fetchone()
            payload = json.loads(review['payload_json']) if review else {}
            event_hash = fingerprint_hash(dict(event))
            accepted = (review is not None and role in DISPOSITIONS and payload['disposition'] == role
                        and payload['event_sha256'] == event_hash)
            findings.append({'event_id': event_id, 'event_sha256': event_hash, 'role': role,
                'status': 'SCOPED_DISPOSITION' if accepted else 'REVIEW_REQUIRED',
                'review_id': review['id'] if accepted else None,
                'reason': payload['reason'] if accepted else
                    'Cited adverse evidence has not been adjudicated for this claim, scope and frontier version.',
                'reopen_conditions': ['Record a scoped operator disposition for diagnostic use or label correction; '
                                      'otherwise resolve the conflict affecting the premises.'],
                'proof_status': 'unverified'})
        return findings

    def matches_report(self, connection, project, move, report):
        current = self.assess(connection, project, move)
        if any(item['status'] == 'REVIEW_REQUIRED' for item in current): return False
        keys = ('event_id', 'event_sha256', 'role', 'status', 'review_id')
        compact = lambda rows: [{key: row.get(key) for key in keys} for row in rows]
        return compact(current) == compact((report or {}).get('adverse_evidence', []))

    def record(self, project, event_id, obligation_id, expected_version, proposed_operation,
               disposition, reason, evidence_refs, request_key, operator):
        if disposition not in DISPOSITIONS: raise ValueError('unsupported adverse-evidence disposition')
        reason = text(reason, 'reason')
        operator = text(operator, 'operator')
        key = text(request_key, 'request_key')
        if len(key)>128: raise ValueError('request_key must have at most 128 characters')
        fp = ResearchMoveFingerprint.build(proposed_operation)
        if not fp.complete: raise ValueError('a scoped evidence review requires complete structured claims')
        with self.store._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self.store.frontier._events(connection, project, [event_id])
            active = self.store.frontier._obligation(connection, obligation_id)
            if active['project'] != project: raise ValueError('obligation belongs to another project')
            refs = self.store.frontier._evidence_refs(connection, project, evidence_refs)
            if not refs: raise ValueError('a disposition requires inspectable supporting references')
            supporting = [int(m[1]) for ref in refs if (m := re.fullmatch(r'event:([1-9]\d*)', ref))]
            if not supporting or (disposition=='label_error' and not set(supporting)-{event_id}):
                raise ValueError('disposition needs an existing project event; a label correction needs another event')
            event = connection.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            payload = {'project':project, 'event_id':event_id, 'event_sha256':fingerprint_hash(dict(event)),
                       'obligation_id':obligation_id, 'frontier_version':expected_version, 'scope':active['scope'],
                       'fingerprint':fp.digest, 'disposition':disposition, 'reason':reason,
                       'evidence_refs':refs, 'operator':operator, 'proof_status':'unverified'}
            digest = fingerprint_hash(payload)
            prior = connection.execute('SELECT * FROM adverse_evidence_reviews WHERE project=? AND request_key=?',
                                       (project,key)).fetchone()
            if prior:
                if prior['request_hash']!=digest: raise ValueError('evidence review key reused with different content')
                return {'id':prior['id'],**json.loads(prior['payload_json']),'idempotent':True}
            if active['version']!=expected_version or active['status'] not in {'OPEN','TESTING'}:
                raise ValueError('evidence review needs the current open frontier version')
            cursor = connection.execute('''INSERT INTO adverse_evidence_reviews(project,event_id,obligation_id,
                frontier_version,scope,fingerprint,payload_json,request_key,request_hash,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (project,event_id,obligation_id,expected_version,active['scope'],
                    fp.digest,canonical(payload),key,digest,int(time.time())))
            self.store._audit(connection,'adverse_evidence_review_recorded',
                              {'id':cursor.lastrowid,'project':project,'payload_sha256':digest})
            # A superseding disposition cannot reuse an earlier execution grant.
            for row in connection.execute('SELECT * FROM research_moves WHERE project=? AND fingerprint=?',
                                          (project,fp.digest)).fetchall():
                latest = self.store.moves._latest(connection,row['id'])
                move = json.loads(row['payload_json'])
                if (latest['status'] in {'AUDITED','EXPERIMENT_ALLOWED'}
                        and move.get('active_frontier_id')==obligation_id and event_id in cited_event_ids(move)):
                    self.store.moves._append(connection,row['id'],'REQUIRES_REVIEW',
                        'EVIDENCE_REVIEW_CHANGED: persist a new audit before activation.',latest['audit_id'])
            return {'id':cursor.lastrowid,**payload,'idempotent':False}
