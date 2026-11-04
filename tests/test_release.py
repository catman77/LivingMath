import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
import pytest

from lm_suti_assurance import core
from lm_suti_assurance.core import canonical, digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.service import Service
from lm_suti_assurance.smoke import POLICY, TAG, populate
from lm_suti_assurance.bundle import export_bundle, replay
from lm_suti_assurance.validation import parse, validate
from lm_suti_assurance.workspace import validate_history, atomic_write

FIX = Path(__file__).parent/'fixtures'
SOURCES=json.loads((core.ROOT/'examples/SOURCE_SNAPSHOTS.json').read_text())
TASKS=json.loads((core.ROOT/'examples/FROZEN_CORPUS.json').read_text())


def load(name): return json.loads((FIX/name).read_text())


@pytest.fixture
def setup(tmp_path):
    s=Service(tmp_path/'state');p='qa';s.new(p,'new')
    s.source(p,copy.deepcopy(SOURCES['program:C1']),POLICY,'source')
    t=s.task(p,{'schema':'lm-suti.assurance.task/0.1','project':p,'task':TASKS['C1']},'task')
    s.review(p,t['task_ref'],'QA_OPERATOR','Confirm exact finite scope','review')
    a={'schema':'lm-suti.assurance.candidate/0.1','project':p,'task_ref':t['task_ref'],'format':'delta',
       'raw':canonical({'schema':TAG,'intent':'PROPOSE','kind':'BOUNDED_PROPERTY','property':'PRESERVES_POPCOUNT'})}
    return s,p,a


@pytest.mark.parametrize('f,old',list(zip(load('baseline001-fixtures.json'),load('baseline001-results.json'))),ids=lambda f:f.get('fixture_id','old'))
def test_baseline001(f,old):
    for engine in ('direct','compiled'):
        d,w=core.module('checks').check(f['candidate'],f['task'],f['sources'],engine=engine,expected_verifier_digest=f.get('expected_verifier_digest',core.LOCK['verifier_digest']))
        assert d==old['decision'] and w==old['witnesses']


@pytest.mark.parametrize('f,old',list(zip(load('baseline002-fixtures.json'),load('baseline002-results.json'))),ids=lambda f:f.get('fixture_id','old'))
def test_baseline002(f,old):
    expected=old['evaluation']
    for engine in ('direct','compiled'):
        try:
            b=core.compile_delta(f['raw'],f['task'],f['sources'],expected['runtime'])
        except core.module('proposal_schema').ProposalError as e:
            assert e.reason==expected['reason_code'] and expected['decision'] is None
            continue
        assert b==expected['binding']
        if b['candidate'] is not None:
            d,w=core.module('checks').check(b['candidate'],f['task'],f['sources'],engine=engine,expected_verifier_digest=f['expected_checker'])
            assert d==expected['decision'] and w==expected['witnesses']


@pytest.mark.parametrize('f,old',list(zip(load('baseline003-fixtures.json'),load('baseline003-results.json')['results'])),ids=lambda f:f.get('test_id','old'))
def test_baseline003(f,old):
    expected=old['evaluation']; err=None
    try:wire=core.strict_json(f['raw'])
    except (ValueError,TypeError) as e:
        err='DUPLICATE_JSON_KEY' if 'DUPLICATE_JSON_KEY' in str(e) else 'NONFINITE_JSON' if 'NONFINITE_JSON' in str(e) else 'INVALID_JSON'
    if err:
        assert err==expected['reason_code'];return
    assert set(wire)=={'payload'}
    from jsonschema import Draft202012Validator
    schema=core.module('proposal_schema').SCHEMA if f['interface']=='DELTA' else json.loads((core.FROZEN/'checker001/ASSURANCE_CLAIM_V1.schema.json').read_text())
    if not Draft202012Validator(schema).is_valid(wire['payload']):
        assert expected['reason_code']==('MODEL_DELTA_INVALID' if f['interface']=='DELTA' else 'CANDIDATE_SCHEMA_INVALID');return
    for engine in ('direct','compiled'):
        try:
            b=core.compile_delta(canonical(wire['payload']),f['task'],f['sources'],expected['runtime']) if f['interface']=='DELTA' else None
        except core.module('proposal_schema').ProposalError as e:
            assert e.reason==expected['reason_code'];continue
        c=b['candidate'] if b else wire['payload']
        if c is None:
            assert expected['decision'] is None;continue
        d,w=core.check(c,f['task'],f['sources'],engine)
        assert d==expected['decision'] and w==expected['witnesses']


def test_manual_cleanroom(tmp_path):
    result=populate(Service(tmp_path/'state'),output=tmp_path/'out')
    assert result['status']=='PASS'
    assert result['direct']['logical_digest']==result['compiled']['logical_digest']
    cp=subprocess.run([sys.executable,'-m','lm_suti_assurance','replay',str(tmp_path/'out/pilot.zip'),'--offline'],capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(core.ROOT.parent)})
    assert cp.returncode==0,cp.stdout+cp.stderr
    assert json.loads(cp.stdout)['logical_digest']==result['direct']['logical_digest']


def test_idempotency_conflict_and_concurrency(setup):
    s,p,a=setup
    with ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(lambda _:s.candidate(p,a,'candidate'),range(4)))
    assert len({v['candidate_ref'] for v in values})==1
    assert len([r for r in s.workspace(p).history() if r['action']=='candidate.import'])==1
    b={**a,'raw':a['raw']+' '}
    with pytest.raises(AssuranceError,match='REQUEST_KEY_CONFLICT'):s.candidate(p,b,'candidate')
    c=values[0]['candidate_ref']
    x=s.check(p,c,'direct','check'); prefix=(s.workspace(p).path/'journal.jsonl').read_bytes()
    assert s.check(p,c,'direct','check')==x
    assert (s.workspace(p).path/'journal.jsonl').read_bytes()==prefix
    s.check(p,c,'compiled','check2')
    assert (s.workspace(p).path/'journal.jsonl').read_bytes().startswith(prefix)


def test_cross_project_and_review(setup):
    s,p,a=setup;s.new('other','new')
    with pytest.raises(AssuranceError,match='CROSS_PROJECT_REFERENCE'):s.candidate('other',a,'candidate')
    with pytest.raises(AssuranceError,match='REFERENCE_NOT_IN_PROJECT'):s.candidate('other',{**a,'project':'other'},'candidate')
    t=s.task(p,{'schema':'lm-suti.assurance.task/0.1','project':p,'task':{**TASKS['C1'],'question':'New exact question'}},'new-task')
    c=s.candidate(p,{**a,'task_ref':t['task_ref']},'new-candidate')
    with pytest.raises(AssuranceError,match='TASK_REVIEW_REQUIRED'):s.check(p,c['candidate_ref'],'direct','check')


@pytest.mark.parametrize('raw,code',[('{"a":1,"a":2}','DUPLICATE_JSON_KEY'),('{','INVALID_JSON'),('[NaN]','NONFINITE_JSON'),('['*55+'0'+']'*55,'JSON_DEPTH_EXCEEDED'),('"'+'x'*2100000+'"','INPUT_TOO_LARGE')])
def test_strict_input(raw,code):
    with pytest.raises(AssuranceError,match=code):parse(raw)


@pytest.mark.parametrize('raw',['null','[]','1','"text"','{}','{"schema":"future"}','{"a":true,"a":false}'])
def test_bad_candidate_retained(setup,raw):
    s,p,a=setup;c=s.candidate(p,{**a,'format':'candidate','raw':raw},'candidate')
    d=s.check(p,c['candidate_ref'],'direct','check')
    assert d['status'] in ('HOLD','REJECTED') and not d['execution_permission']
    assert s.workspace(p).get(c['candidate_ref'])['raw']==raw


def test_versions_and_paths(setup):
    s,p,a=setup
    with pytest.raises(AssuranceError,match='MIGRATION_REQUIRED'):s.candidate(p,{**a,'schema':'lm-suti.assurance.candidate/0.2'},'c')
    for project in ('../outside','/tmp/abs','qa/child','q\\a','..'):
        with pytest.raises(AssuranceError,match='INVALID_PROJECT_ID'):s.new(project,'new')
    path=s.workspace(p).path/'objects'/'a.json';path.symlink_to('/etc/passwd')
    assert not path.readlink().is_relative_to(s.workspace(p).path)
    dest=s.workspace(p).path/'symlink';dest.symlink_to('/tmp')
    with pytest.raises(AssuranceError,match='SYMLINK_FORBIDDEN'):atomic_write(dest,b'bad')


def test_rights_and_offline_missing_dependency(setup):
    s,p,a=setup
    source=copy.deepcopy(SOURCES['program:C1']);source['rights']['can_embed']=False
    s.source(p,source,{**POLICY,'allow_source_bytes':False},'private-source')
    t={**TASKS['C1'],'scope':{**TASKS['C1']['scope'],'source_snapshots':{'program:C1':digest(source)}}}
    tr=s.task(p,{'schema':'lm-suti.assurance.task/0.1','project':p,'task':t},'private-task')
    s.review(p,tr['task_ref'],'QA_OPERATOR','private source','r2')
    c=s.candidate(p,{**a,'task_ref':tr['task_ref']},'private-c')
    assert s.check(p,c['candidate_ref'],'direct','c2')['status']=='HOLD'
    raw,m=export_bundle(s.workspace(p),'reviewers');assert m['source_dependencies']
    with pytest.raises(AssuranceError,match='MISSING_SOURCE_DEPENDENCY'):replay(raw)


def test_policy_restricts_public(setup):
    s,p,a=setup
    source=copy.deepcopy(SOURCES['program:C1']);source['version']='2'
    r=s.source(p,source,{**POLICY,'audiences':['private']},'private')
    raw,m=export_bundle(s.workspace(p),'public')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert 'objects/'+r['source_ref']+'.json' not in z.namelist()


def test_failed_candidate_supersession(setup):
    s,p,a=setup
    bad={**a,'raw':a['raw'].replace('PRESERVES_POPCOUNT','PRESERVES_VALUE')}
    b=s.candidate(p,bad,'bad');assert s.check(p,b['candidate_ref'],'direct','bc')['status']=='REJECTED'
    good=s.candidate(p,{**a,'supersedes':b['candidate_ref']},'good')
    assert s.check(p,good['candidate_ref'],'direct','gc')['status']=='CHECKED_FINITE'
    raw,m=export_bundle(s.workspace(p),'reviewers')
    r=replay(raw);assert [c['status'] for c in r['checks']]==['REJECTED','CHECKED_FINITE']


def test_external_schema_blocked(setup):
    s,p,a=setup
    source=core.contracts.SourceSnapshot.create('remote',canonical({'$ref':'https://example.com/no-network'}),'user',kind='schema').record
    with pytest.raises(AssuranceError,match='SCHEMA_REFERENCE_NOT_SUPPORTED'):s.source(p,source,POLICY,'remote')


def test_secret_and_local_paths_not_exported(setup):
    s,p,a=setup
    c=s.candidate(p,{**a,'raw':'{"password":"not-for-publication"}'},'secret')
    with pytest.raises(AssuranceError,match='EXPORT_SENSITIVE_CONTENT'):export_bundle(s.workspace(p),'reviewers')


def test_journal_and_object_tamper(setup):
    s,p,a=setup;w=s.workspace(p);path=w.path/'journal.jsonl';rows=w.history();rows[0]['result']['status']='HACK'
    path.write_text('\n'.join(canonical(r) for r in rows)+'\n')
    with pytest.raises(AssuranceError,match='JOURNAL_INTEGRITY_FAILURE'):w.history()


def test_crash_commit_visibility(setup,monkeypatch):
    s,p,a=setup;w=s.workspace(p);old=(w.path/'journal.jsonl').read_bytes()
    import lm_suti_assurance.workspace as ws
    original=ws.atomic_write
    def crash(path,raw):
        if path.name=='journal.jsonl':raise OSError('injected pre-commit crash')
        original(path,raw)
    with monkeypatch.context() as m:
        m.setattr(ws,'atomic_write',crash)
        with pytest.raises(OSError):s.candidate(p,a,'c')
    assert (w.path/'journal.jsonl').read_bytes()==old
    s.candidate(p,a,'c');assert len([r for r in w.history() if r['action']=='candidate.import'])==1


def test_offline_denies_network_model_subprocess():
    from lm_suti_assurance.offline import isolated
    with isolated():
        with pytest.raises(AssuranceError,match='OFFLINE_EXTERNAL_OPERATION_FORBIDDEN'):socket.socket()
        with pytest.raises(AssuranceError,match='OFFLINE_EXTERNAL_OPERATION_FORBIDDEN'):subprocess.run([sys.executable,'-V'])
    with socket.socket():pass  # The host server outside replay keeps its transport.


def test_unsafe_zip(setup):
    s,p,a=setup
    for name in ('../evil','/absolute','a\\b','x/../evil'):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr(name,'{}')
        with pytest.raises(AssuranceError,match='UNSAFE_ZIP_MEMBER'):replay(out.getvalue())


def test_no_global_module_pollution():
    assert core.identity()['verifier_digest']==core.LOCK['verifier_digest']
    assert not any(name in sys.modules for name in ('contracts','checks','proposal_binder','common002'))

@pytest.mark.parametrize('raw',['contact person@example.org','phone +7 999 123 45 67','/home/operator/private-file','sk-abcdefghijklmnopqrstuvwx'])
def test_common_pii_and_secrets_guarded(setup,raw):
    s,p,a=setup;s.candidate(p,{**a,'raw':raw},'sensitive')
    with pytest.raises(AssuranceError,match='EXPORT_SENSITIVE_CONTENT'):export_bundle(s.workspace(p),'reviewers')


def test_schema_kind_cannot_bypass_boundary(setup):
    s,p,a=setup
    source=core.contracts.SourceSnapshot.create('malicious-schema',canonical({'type':'string','pattern':'(a+)+$'}),'QA',kind='qa').record
    sr=s.source(p,source,POLICY,'s')
    value=core.contracts.SourceSnapshot.create('value','"test"','QA',schema_id='malicious-schema').record
    s.source(p,value,POLICY,'v')
    task={'task_id':'typed','claim_kind':'SOURCE_CLAIM','source_ids':['malicious-schema','value'],
          'question':'Check source only','assumptions':[], 'allowed_predicates':['field_equals'],
          'scope':{'task_id':'typed','scope_version':1,'execution_permission':False,'source_snapshots':{'malicious-schema':digest(source),'value':digest(value)}}}
    with pytest.raises(AssuranceError,match='SCHEMA_SOURCE_KIND_REQUIRED'):s.task(p,{'schema':'lm-suti.assurance.task/0.1','project':p,'task':task},'t')


def test_mcp_replay_preserves_specific_domain_errors(tmp_path):
    import base64
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.mcp import register_tools
    server=FastMCP('qa');register_tools(server,tmp_path/'state')
    fn=server._tool_manager.get_tool('assurance_replay').fn
    assert fn('!invalid-base64')['reason_code']=='INVALID_BASE64'
    assert fn(base64.b64encode(b'invalid ZIP').decode())['reason_code']=='INVALID_BUNDLE'

@pytest.mark.parametrize('fmt,schema',[('candidate','symseq.assurance.candidate.v2'),('delta','symseq.assurance.proposal-delta.v2')])
def test_inner_version_requires_explicit_migration(setup,fmt,schema):
    s,p,a=setup;c=s.candidate(p,{**a,'format':fmt,'raw':canonical({'schema':schema})},'future')
    d=s.check(p,c['candidate_ref'],'direct','check-future')
    assert d['status']=='HOLD' and d['reason_code']=='MIGRATION_REQUIRED'

@pytest.mark.parametrize('recompute_manifest',[False,True])
def test_bundle_core_tamper_cannot_redefine_checker(setup,recompute_manifest):
    s,p,a=setup;c=s.candidate(p,a,'c');s.check(p,c['candidate_ref'],'direct','check')
    raw,_=export_bundle(s.workspace(p),'reviewers')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:files={n:z.read(n) for n in z.namelist()}
    name='core/_frozen/checker001/checks.py';files[name]+=b'\n# tamper\n'
    if recompute_manifest:
        m=json.loads(files['package_manifest.json']);m['files'][name]=core.byte_digest(files[name]);files['package_manifest.json']=canonical(m).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    with pytest.raises(AssuranceError,match='FROZEN_CORE_INTEGRITY_FAILURE' if recompute_manifest else 'MANIFEST_SHA_MISMATCH'):replay(out.getvalue())
