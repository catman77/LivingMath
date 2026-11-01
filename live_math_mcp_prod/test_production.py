import json, sqlite3, tempfile, threading, unittest
from pathlib import Path
from research_store import ResearchStore
class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'data.db';self.s=ResearchStore(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_persistence_audit_backup(self):
        e=self.s.record('RH','attention','lemma','focus',status='observation',request_key='req1')
        assert self.s.record('RH','attention','lemma','focus',status='observation',request_key='req1')['id']==e['id']
        with self.assertRaises(ValueError):self.s.record('RH','attention','lemma','different',status='observation',request_key='req1')
        assert ResearchStore(self.path).events('RH')[0]['content']=='focus'
        assert self.s.health()['audit']['ok']
        dest=Path(self.tmp.name)/'backup.db'; self.s.backup(dest)
        assert ResearchStore(dest).events('RH')[0]['content']=='focus'
    def test_no_model_verification(self):
        with self.assertRaises(ValueError):self.s.record('RH','proof','A','B','verified','http://fake')
        e=self.s.record('RH','proof_candidate','A','B',evidence='artifact pointer')
        with self.assertRaises(ValueError):self.s.add_review(e['id'],'verified','user','fake','validated')
        rec=self.s.add_review(e['id'],'verified','independent reviewer','a'*64,'External verification claim')
        assert rec['review_claim']=='verified'
        assert self.s.events('RH')[0]['status']=='hypothesis'
    def test_cross_project_parent_denied(self):
        a=self.s.record('RH','attention','x','y')
        with self.assertRaises(ValueError): self.s.record('SoftFTL','interpretation','x','y',parent_id=a['id'])
    def test_policy_approval(self):
        with self.assertRaises(ValueError): self.s.propose_policy('bad code','content')
        prop=self.s.propose_policy('TEST_RULE','Never assert unverifiable claims.')
        assert 'TEST_RULE' not in [x['code'] for x in self.s.policies()]
        self.s.approve_policy(prop['request_id'],'human operator')
        assert 'TEST_RULE' in [x['code'] for x in self.s.policies()]
    def test_legacy_migration(self):
        legacy=Path(self.tmp.name)/'legacy.db'
        with sqlite3.connect(legacy) as c:
            c.executescript('CREATE TABLE events(id INTEGER PRIMARY KEY,timestamp INTEGER NOT NULL,project TEXT NOT NULL,kind TEXT NOT NULL,focus TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,parent_id INTEGER);CREATE TABLE policies(code TEXT PRIMARY KEY,content TEXT NOT NULL,enabled INTEGER DEFAULT 1);')
            c.execute("INSERT INTO events VALUES(1,1,'RH','attention','f','legacy','observation','',NULL)")
        upgraded=ResearchStore(legacy)
        assert upgraded.events('RH')[0]['content']=='legacy'
        assert upgraded.health()['sqlite_integrity']=='ok'
    def test_concurrent_writes_and_repeated_requests(self):
        err=[]
        def worker(i):
            try:self.s.record('ARC','experiment',f'f{i}',f'content{i}',request_key=f'key{i}')
            except Exception as e:err.append(str(e))
        ts=[threading.Thread(target=worker,args=(i,)) for i in range(20)]
        for t in ts:t.start()
        for t in ts:t.join()
        assert not err,err
        assert len(self.s.events('ARC'))==20
        assert self.s.verify_audit()['ok']
    def test_audit_detects_tampering(self):
        self.s.record('RH','attention','foo','bar')
        with sqlite3.connect(self.path) as c:c.execute("UPDATE operations SET details_json='{}' WHERE id=1")
        assert not self.s.verify_audit()['ok']
    def test_failure_kinds_count_for_audit(self):
        for project, kind in [('RH','counterexample'), ('soft-ftl','failed_check')]:
            source=self.s.record(project,kind,'negative result','reproducible failed claim',status='experiment',evidence='source: test file')
            self.s.record(project,'attention','new focus','reason',status='observation',parent_id=source['id'])
            audit=self.s.audit(project,'new research direction','source: test file')
            self.assertNotIn('No RCA/counterexample in recorded history', audit['warnings'])
            candidates=self.s.focus_candidates(project)
            self.assertTrue(any(e['target']=='failure' and e['event_id']==source['id'] for e in candidates))
    def test_audit_does_not_promote_unverified_claim(self):
        self.s.record('RH','interpretation','claim','novel hypothesis',status='hypothesis')
        audit=self.s.audit('RH','proposed shift','evidence description')
        self.assertIn('No RCA/counterexample in recorded history',audit['warnings'])
        self.assertEqual(audit['verdict'],'needs_independent_check')
    def test_input_limits(self):
        with self.assertRaises(ValueError):self.s.record('../../etc','a','b','c')
        with self.assertRaises(ValueError):self.s.record('RH','a','b','c'*20001)
        with self.assertRaises(ValueError):self.s.record('RH','a','b','c',status='made_up')
if __name__=='__main__':unittest.main()
