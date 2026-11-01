"""Versioned SQLite research ledger. No model-produced assertion verifies itself."""
from __future__ import annotations
import hashlib, json, re, sqlite3, time
from contextlib import contextmanager, closing
from pathlib import Path

DEFAULT_PRINCIPLES = [
 ('NO_SUBSTITUTION','Не подменять обнаруженный механизм готовым DSL или аппаратом без сравнения преемственности.'),
 ('TWO_OPERATIONS','Интерпретация и перенос внимания; новые фундаментальные операции требуют доказательств.'),
 ('PROOF_STATUS','Аналогии, тексты модели и численные тесты не являются математическими доказательствами.'),
 ('FAILURE_FIRST','После провала — RCA и проверяемый контрпример прежде новой эвристики.'),
 ('SOURCE_VS_READER','Разделять изменение источника, интерпретации и способа проверки.'),
 ('FTL_CONTROL','Совпадение смыслов через известный канал не доказывает независимую передачу новой информации.'),
]
FAILURE_KINDS={'failure','failed_check','counterexample','rca'}
FAILURE_STATUSES={'refuted','counterexample'}
STATUSES={'observation','hypothesis','interpretation','counterexample','experiment','proof_candidate','verified','refuted','open'}
PROJECT_RE=re.compile(r'^[A-Za-zА-Яа-яЁё0-9][\w.-]{0,79}$',re.U)

def sha(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_text(value, field, maxlen=20000):
    if not isinstance(value,str) or not value.strip() or len(value)>maxlen: raise ValueError(f'{field}: expected 1..{maxlen} non-empty characters')
    return value.strip()

class ResearchStore:
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.migrate()
    @contextmanager
    def _connect(self):
        c=sqlite3.connect(str(self.path),timeout=15)
        try:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=15000')
            with c:
                yield c
        finally:
            c.close()
    def migrate(self):
        from frontier import SCHEMA_SQL
        from move_lifecycle import SCHEMA_SQL as MOVE_SCHEMA_SQL
        from evidence_review import SCHEMA_SQL as EVIDENCE_SCHEMA_SQL
        with self._connect() as c:
            current=c.execute('PRAGMA user_version').fetchone()[0]
            if current > 5: raise ValueError('database schema is newer than this server')
            if current == 5: return
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
              BEGIN IMMEDIATE;
              CREATE TABLE IF NOT EXISTS policies(code TEXT PRIMARY KEY,content TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
              CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp INTEGER NOT NULL,project TEXT NOT NULL,kind TEXT NOT NULL,focus TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,parent_id INTEGER REFERENCES events(id));
              CREATE INDEX IF NOT EXISTS events_project ON events(project,id);
              CREATE TABLE IF NOT EXISTS policy_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL,content TEXT NOT NULL,enabled INTEGER NOT NULL,created_at INTEGER NOT NULL,approved_at INTEGER,approver TEXT);
              CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL REFERENCES events(id),verdict TEXT NOT NULL,reviewer TEXT NOT NULL,artifact_sha256 TEXT NOT NULL,notes TEXT NOT NULL,created_at INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS operations(id INTEGER PRIMARY KEY AUTOINCREMENT,occurred_at INTEGER NOT NULL,action TEXT NOT NULL,details_json TEXT NOT NULL,previous_hash TEXT NOT NULL,entry_hash TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS request_keys(key TEXT PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES events(id),request_hash TEXT NOT NULL);
            ''' + SCHEMA_SQL + MOVE_SCHEMA_SQL + EVIDENCE_SCHEMA_SQL)
            if current < 3:
                for k,v in DEFAULT_PRINCIPLES: c.execute('INSERT OR IGNORE INTO policies(code,content) VALUES (?,?)',(k,v))
                for event in c.execute('SELECT * FROM events ORDER BY id').fetchall():
                    args={key:event[key] for key in ('project','kind','focus','content','status','evidence','parent_id')}
                    c.execute('INSERT OR IGNORE INTO event_fingerprints(digest,event_id) VALUES (?,?)',(sha(args),event['id']))
            for row in c.execute('SELECT * FROM research_moves ORDER BY id').fetchall():
                self.moves.import_legacy(c,row)
            c.execute('PRAGMA user_version=5')
    def _audit(self,c,action,details):
        prev=c.execute('SELECT entry_hash FROM operations ORDER BY id DESC LIMIT 1').fetchone()
        prev_hash=prev[0] if prev else 'GENESIS'
        now=int(time.time())
        entry={'time':now,'action':action,'details':details,'previous':prev_hash}
        h=sha(entry)
        c.execute('INSERT INTO operations(occurred_at,action,details_json,previous_hash,entry_hash) VALUES (?,?,?,?,?)',(now,action,json.dumps(details,ensure_ascii=False,sort_keys=True),prev_hash,h))
    def verify_audit(self):
        with self._connect() as c:
            prev='GENESIS'; count=0
            for a in c.execute('SELECT * FROM operations ORDER BY id'):
                obj={'time':a['occurred_at'],'action':a['action'],'details':json.loads(a['details_json']),'previous':prev}
                if a['previous_hash']!=prev or sha(obj)!=a['entry_hash']: return {'ok':False,'failed_at':a['id']}
                prev=a['entry_hash']; count+=1
            return {'ok':True,'entries':count,'last_hash':prev}
    def policies(self):
        with self._connect() as c: return [dict(row) for row in c.execute('SELECT code,content FROM policies WHERE enabled=1 ORDER BY code')]
    def propose_policy(self,code,content,enabled=True):
        code=validate_text(code,'code',80); content=validate_text(content,'content',4000)
        if not re.fullmatch('[A-Z][A-Z0-9_]{1,79}',code): raise ValueError('policy code must be uppercase identifier')
        with self._connect() as c:
            cur=c.execute('INSERT INTO policy_requests(code,content,enabled,created_at) VALUES (?,?,?,?)',(code,content,int(enabled),int(time.time())))
            self._audit(c,'policy_proposed',{'id':cur.lastrowid,'code':code})
            return {'request_id':cur.lastrowid,'status':'pending_approval'}
    def approve_policy(self,request_id,approver):
        approver=validate_text(approver,'approver',120)
        with self._connect() as c:
            req=c.execute('SELECT * FROM policy_requests WHERE id=?',(request_id,)).fetchone()
            if not req: raise ValueError('unknown policy request')
            if req['approved_at']: raise ValueError('already approved')
            c.execute('INSERT INTO policies(code,content,enabled) VALUES (?,?,?) ON CONFLICT(code) DO UPDATE SET content=excluded.content,enabled=excluded.enabled',(req['code'],req['content'],req['enabled']))
            c.execute('UPDATE policy_requests SET approved_at=?,approver=? WHERE id=?',(int(time.time()),approver,request_id))
            self._audit(c,'policy_approved',{'id':request_id,'approver':approver})
            return {'status':'approved','code':req['code']}
    def record(self,project,kind,focus,content,status='hypothesis',evidence='',parent_id=None,request_key=None):
        project=validate_text(project,'project',80)
        if not PROJECT_RE.fullmatch(project): raise ValueError('project: invalid identifier')
        kind=validate_text(kind,'kind',80);focus=validate_text(focus,'focus',2000)
        content=validate_text(content,'content',20000)
        if status not in STATUSES: raise ValueError('invalid status')
        if status=='verified': raise ValueError('verified status is only available through independent review, never record()')
        if not isinstance(evidence,str) or len(evidence)>20000: raise ValueError('invalid evidence')
        if request_key is not None: validate_text(request_key,'request_key',128)
        args={'project':project,'kind':kind,'focus':focus,'content':content,'status':status,'evidence':evidence,'parent_id':parent_id}
        digest=sha(args)
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if request_key:
                old=c.execute('SELECT event_id,request_hash FROM request_keys WHERE key=?',(request_key,)).fetchone()
                if old:
                    if old['request_hash']!=digest: raise ValueError('idempotency key reused with different request')
                    return {'id':old['event_id'],'project':project,'status':status,'idempotent':True}
            existing=c.execute('SELECT event_id FROM event_fingerprints WHERE digest=?',(digest,)).fetchone()
            if existing:
                if request_key:
                    c.execute('INSERT INTO request_keys(key,event_id,request_hash) VALUES (?,?,?)',(request_key,existing['event_id'],digest))
                    self._audit(c,'request_key_bound',{'event_id':existing['event_id'],'request_hash':digest})
                return {'id':existing['event_id'],'project':project,'status':status,'idempotent':True}
            if parent_id is not None:
                parent=c.execute('SELECT project FROM events WHERE id=?',(parent_id,)).fetchone()
                if not parent or parent['project']!=project: raise ValueError('parent event missing or belongs to other project')
            cur=c.execute('INSERT INTO events(timestamp,project,kind,focus,content,status,evidence,parent_id) VALUES (?,?,?,?,?,?,?,?)',(int(time.time()),project,kind,focus,content,status,evidence,parent_id))
            eid=cur.lastrowid
            c.execute('INSERT INTO event_fingerprints(digest,event_id) VALUES (?,?)',(digest,eid))
            if request_key: c.execute('INSERT INTO request_keys(key,event_id,request_hash) VALUES (?,?,?)',(request_key,eid,digest))
            self._audit(c,'event_created',{'id':eid,'project':project,'status':status,'digest':digest})
            return {'id':eid,'project':project,'status':status,'parent_id':parent_id}
    def add_review(self,event_id,verdict,reviewer,artifact_sha256,notes):
        if verdict not in ('verified','refuted'): raise ValueError('review verdict must be verified or refuted')
        reviewer=validate_text(reviewer,'reviewer',120)
        notes=validate_text(notes,'notes',4000)
        if not re.fullmatch(r'[0-9a-f]{64}',artifact_sha256): raise ValueError('artifact_sha256 must be SHA-256 hex of externally validated witness')
        with self._connect() as c:
            event=c.execute('SELECT id,status FROM events WHERE id=?',(event_id,)).fetchone()
            if not event: raise ValueError('unknown event')
            cur=c.execute('INSERT INTO reviews(event_id,verdict,reviewer,artifact_sha256,notes,created_at) VALUES (?,?,?,?,?,?)',(event_id,verdict,reviewer,artifact_sha256,notes,int(time.time())))
            self._audit(c,'independent_review',{'event_id':event_id,'review_id':cur.lastrowid,'verdict':verdict,'reviewer':reviewer})
            return {'review_id':cur.lastrowid,'event_id':event_id,'review_claim':verdict,'caution':'Witness hash and reviewer declaration are recorded, not mathematically verified by this service.'}
    def events(self,project='',limit=50):
        limit=max(1,min(200,int(limit)))
        with self._connect() as c:
            query='SELECT * FROM events '+('WHERE project=? ' if project else '')+'ORDER BY id DESC LIMIT ?'
            return [dict(r) for r in c.execute(query,(project,limit) if project else (limit,))]
    def inspect(self,project,limit=25):
        rows=list(reversed(self.events(project,limit)))
        return {'project':project,'policies':self.policies(),'events':rows,'open_or_unverified':[x for x in rows if x['status']!='refuted'],
                'frontier':self.frontier.inspect(project,include_closed=True),
                'note':'verified claims require external independent review records; raw event statuses are untrusted'}
    def focus_candidates(self,project,limit=30):
        rows=self.events(project,limit); out=[]
        for e in rows:
            out.append({'event_id':e['id'],'target':'claim','focus':e['content'][:300]})
            if e['status'] in FAILURE_STATUSES or e['kind'] in FAILURE_KINDS: out.append({'event_id':e['id'],'target':'failure','focus':e['content'][:300]})
        return out[:100]
    @property
    def frontier(self):
        from frontier import ResearchFrontier
        return ResearchFrontier(self)
    @property
    def moves(self):
        from move_lifecycle import ResearchMoveLifecycle
        return ResearchMoveLifecycle(self)
    @property
    def evidence_reviews(self):
        from evidence_review import EvidenceReviews
        return EvidenceReviews(self)
    def audit(self,project,candidate='',evidence='',**move):
        if move:
            return self.frontier.audit(project,candidate,evidence,**move)
        rows=self.events(project,100); flags=[]
        if not evidence.strip(): flags.append('No independently inspectable witness declared')
        if rows and not any(x['parent_id'] is not None for x in rows): flags.append('Missing event lineage')
        if not any(x['status'] in FAILURE_STATUSES or x['kind'] in FAILURE_KINDS for x in rows): flags.append('No RCA/counterexample in recorded history')
        return {'candidate':candidate,'warnings':flags,'verdict':'needs_independent_check','policy_codes':[p['code'] for p in self.policies()],
                'decision':'REQUIRES_SEMANTIC_REVIEW','semantic_review_required':True,
                'missing_data':['structured research move and active_frontier_id'],'proof_status':'unverified'}
    def backup(self,destination):
        dest=Path(destination).expanduser().resolve()
        if dest==self.path: raise ValueError('backup must differ from source')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as src, closing(sqlite3.connect(str(dest))) as dst: src.backup(dst)
        return {'destination':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
    def health(self):
        with self._connect() as c:
            chk=c.execute('PRAGMA integrity_check').fetchone()[0]
            return {'sqlite_integrity':chk,'event_count':c.execute('SELECT count(*) FROM events').fetchone()[0],
                    'schema_version':c.execute('PRAGMA user_version').fetchone()[0], 'audit':self.verify_audit()}
