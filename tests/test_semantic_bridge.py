import copy
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import zipfile
import pytest
from lm_suti_assurance import core
from lm_suti_assurance.core import canonical,digest,byte_digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.service import Service
from lm_suti_assurance.bundle import export_bundle,replay
from lm_suti_assurance.semantic_bridge.service import SemanticService
from lm_suti_assurance.semantic_bridge.anchors import make_anchor,check_anchor,line_index
from lm_suti_assurance.semantic_bridge.records import validate,schema
from lm_suti_assurance.semantic_bridge.bundle import export
from lm_suti_assurance.semantic_bridge.report import dossier
from lm_suti_assurance.semantic_bridge.replay import verify_graph

RAW=json.loads((Path(__file__).parent/'fixtures/semantic_manual_fixture.json').read_text())
POLICY={'schema':'lm-suti.assurance.publication-policy/0.1','audiences':['private'],'allow_source_bytes':True,'reason':'Private generated unit QA only'}
TEXT='Ночь, улица.\nЁж — не ель.\nФонарь.'
META={'author':'QA','title':'Generated unit text','edition':'v1','editorial_source_url':'','edition_status':'DECLARED_EDITION'}


@pytest.fixture
def setup(tmp_path):
    base=Service(tmp_path/'state');p='semantic-qa';base.new(p,'new')
    source=core.contracts.SourceSnapshot.create('poem',TEXT,'Owner-provided private QA').record
    sr=base.source(p,source,POLICY,'source');s=SemanticService(base.root)
    e=s.edition(p,sr['source_ref'],META,'OWNER_QA','Pinned exact bytes and interpretation-only scope','edition')
    return s,p,e['edition_ref'],source


def add(s,p,e,key='first',raw=None,parents=()):
    return s.import_proposal(p,e,canonical(raw if raw is not None else RAW),key,parents=parents,mode='FIXTURE')


def test_S01_S02_fixture_sources_exact():
    path=Path(__file__).parents[1]/'docs/LM_SUTI_SEMANTIC_BRIDGE_001/POETRY_QA_FIXTURES.json'
    if not path.exists():pytest.skip('Original attached fixture archive not included in this source-only test checkout')
    sources=json.loads(path.read_text())['source_records'];assert len(sources)==3
    for s in sources:
        assert byte_digest(s['raw_text_utf8'].encode())==s['raw_text_sha256'] and len(s['raw_text_utf8'].encode())==s['byte_length']


def test_S03_unicode_exact_and_navigation(setup):
    s,p,e,source=setup;ed=s.workspace(p).get(e);a=make_anchor(p,e,ed,source,'Ёж — не ель.')
    assert TEXT.encode()[a['byte_start']:a['byte_end']]=='Ёж — не ель.'.encode()
    assert check_anchor(a,source,e) and a['line_number']==2
    assert line_index('ё\r\nе—')[0]['quote_utf8']=='ё\r'


def test_S04_offset_mismatch_even_with_resealed_digest(setup):
    s,p,e,source=setup;a=make_anchor(p,e,s.workspace(p).get(e),source,'Ёж — не ель.')
    a['byte_start']+=1;a['content_digest']=digest({k:v for k,v in a.items() if k!='content_digest'})
    with pytest.raises(AssuranceError,match='SOURCE_ANCHOR_MISMATCH'):check_anchor(a,source,e)


def test_S05_other_edition_does_not_silently_replace(setup):
    s,p,e,_=setup;first=add(s,p,e);changed=copy.deepcopy(META);changed['edition']='v2'
    ed=s.workspace(p).get(e);new=s.edition(p,ed['source_ref'],changed,'OWNER_QA','Review a distinct edition declaration','new-edition')
    second=add(s,p,new['edition_ref'],'second',parents=[first['frame_ref']])
    assert second['reason_code']=='SOURCE_VERSION_CHANGED_REQUIRES_NEW_TASK'


def test_S06_literal_bytes_only_and_interpretations_unknown(setup):
    s,p,e,_=setup;result=add(s,p,e);a=s.workspace(p).get(result['assurance_ref'])
    assert a['source_prose_truth_verified'] is False
    assert [c['status'] for c in a['claims']]==['SOURCE_ATTESTED','SOURCE_ATTESTED','UNKNOWN','UNKNOWN']
    assert all(c['target']=='SOURCE_QUOTE_BYTES_ONLY' for c in a['claims'][:2])


@pytest.mark.parametrize('quote',['Светлый лес вместо ночи.','Еж — не ель.','Ёж - не ель.'])
def test_S07_false_quotes_preserved_rejected(setup,quote):
    s,p,e,_=setup;raw=copy.deepcopy(RAW);raw['literal_observations'][1]['quote']=quote
    result=add(s,p,e,raw=raw);assert result['status']=='FRAME_UNTRUSTED' and result['reason_code']=='SOURCE_ANCHOR_MISMATCH'
    assert s.workspace(p).get(result['proposal_ref'])['raw_proposal']==canonical(raw)


@pytest.mark.parametrize('field,value',[('source_ref','a'*64),('source_sha256','0'*64),('source_anchor_refs',['missing']),('execution_permission',True),('epistemic_status','PROVED_FORMAL')])
def test_S08_S09_R07_generator_cannot_set_trusted_fields(setup,field,value):
    s,p,e,_=setup;result=add(s,p,e,raw={**RAW,field:value})
    assert result['status']=='FRAME_UNTRUSTED' and result['reason_code']=='SEMANTIC_SCHEMA_INVALID'


def test_S10_S11_rights_safe_dependency_export(setup):
    s,p,e,_=setup;add(s,p,e);w=s.workspace(p)
    for include,audience in [(False,'private'),(True,'public')]:
        raw,m=export(w,audience,include);assert m['source_dependencies']
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert not any(n.startswith('objects/') for n in z.namelist())
            assert not any(TEXT.encode() in z.read(n) for n in z.namelist())
        with pytest.raises(AssuranceError,match='MISSING_SOURCE_DEPENDENCY'):replay(raw)


def test_I06_I07_physical_and_world_readings_not_promoted(setup):
    s,p,e,_=setup;raw=copy.deepcopy(RAW);raw['interpretations'][0]['text']='Абсолютно тот же физический мир; реальная токсикология доказана.'
    r=add(s,p,e,raw=raw);a=s.workspace(p).get(r['assurance_ref']);assert a['claims'][2]['status']=='UNKNOWN'
    frame=s.workspace(p).get(r['frame_ref']);assert frame['claim_atoms'][2]['text']==raw['interpretations'][0]['text']


def test_I08_history_and_version_immutable(setup):
    s,p,e,_=setup;a=add(s,p,e);w=s.workspace(p);prefix=(w.path/'journal.jsonl').read_bytes();before=w.get(a['frame_ref'])
    raw=copy.deepcopy(RAW);raw['interpretations'][0]['text']='A changed alternative';b=add(s,p,e,'revise',raw,[a['frame_ref']])
    assert w.get(a['frame_ref'])==before and (w.path/'journal.jsonl').read_bytes().startswith(prefix)
    edge=w.get(b['edge_ref']);assert edge['parent_frames']==[a['frame_ref']] and edge['child_frame']==b['frame_ref']
    assert 'i1' in edge['changed_claims']


def test_I09_missing_parent_cycle_cross_project_merge(setup):
    s,p,e,_=setup
    with pytest.raises(AssuranceError,match='REFERENCE_NOT_IN_PROJECT'):add(s,p,e,parents=['0'*64])
    a=add(s,p,e);raw=copy.deepcopy(RAW);raw['revision_rationale']='Second branch';b=add(s,p,e,'branch',raw,[a['frame_ref']])
    c=add(s,p,e,'bad-merge',parents=[a['frame_ref'],b['frame_ref']]);assert c['reason_code']=='MERGE_RESOLUTION_REQUIRED'
    good=s.import_proposal(p,e,canonical(RAW),'merge',parents=[a['frame_ref'],b['frame_ref']],mode='FIXTURE',operation='MERGE',merge_resolution='Both are retained as alternatives; no truth promotion.')
    assert good['status']=='FRAME_REVISED'
    f=copy.deepcopy(s.workspace(p).get(a['frame_ref']));f['parent_refs']=['a'*64]
    with pytest.raises(AssuranceError,match='LINEAGE_CYCLE'):verify_graph({'a'*64:f})
    s.base.new('foreign','new')
    with pytest.raises(AssuranceError,match='REFERENCE_NOT_IN_PROJECT'):add(s,'foreign',e)


def test_I10_model_unavailable_no_manual_success(setup,tmp_path,monkeypatch):
    from lm_suti_assurance.semantic_bridge.proposer import generate
    import lm_suti_assurance.semantic_bridge.proposer as proposer
    s,p,e,source=setup;monkeypatch.setattr(proposer.shutil,'which',lambda _:None)
    receipt=generate(source,s.workspace(p).get(e),'initial',None,None,tmp_path/'spool','unavailable')
    assert receipt['status']=='MODEL_UNAVAILABLE' and receipt['model_invoked'] is False and receipt['usage'] is None
    r=s._register(p,e,receipt['raw_output'],'unavailable',mode='HOSTED_MODEL',receipt=receipt)
    assert 'frame_ref' not in r
    with pytest.raises(AssuranceError,match='HOSTED_PROVENANCE_NOT_CLIENT_ASSIGNABLE'):s.import_proposal(p,e,canonical(RAW),'fake',mode='HOSTED_MODEL')


def query(field):return {'id':field,'kind':'STRUCTURAL_FIELD','field':field,'question':'Declared annotation field '+field}


def test_L01_L02_loss_and_false_preservation(setup):
    s,p,e,_=setup;a=add(s,p,e);raw=copy.deepcopy(RAW);raw['observables']['image_order'].reverse();raw['observables']['canal_details']=['Changed declared detail']
    b=add(s,p,e,'revision',raw,[a['frame_ref']]);q=[query('/image_order'),query('/canal_details')]
    r=s.compare(p,a['frame_ref'],b['frame_ref'],['/image_set'],q,'loss');w=s.workspace(p).get(r['witness_ref'])
    assert w['status']=='LOSS_DETECTED' and len(w['lost_queries'])==2 and w['checked_pair_count']==4
    assert w['lost_queries'][0]['P_u']==w['lost_queries'][0]['P_v'] and w['lost_queries'][0]['q_u']!=w['lost_queries'][0]['q_v']
    r=s.compare(p,a['frame_ref'],b['frame_ref'],['/image_set'],q,'false-preservation',expectation='PRESERVED_FOR_DECLARED_Q')
    assert r['status']=='REJECTED' and r['reason_code']=='FALSE_STRUCTURAL_PRESERVATION'


def test_L03_complete_projection_no_loss_and_key_order(setup):
    s,p,e,_=setup;a=add(s,p,e);raw=copy.deepcopy(RAW);raw['observables']['image_order'].reverse();b=add(s,p,e,'r',raw,[a['frame_ref']])
    fields=['/image_set','/image_order','/canal_details','/speaker_roles'];r=s.compare(p,a['frame_ref'],b['frame_ref'],fields,[query(f) for f in fields],'full')
    assert r['status']=='PRESERVED_FOR_DECLARED_Q'
    r=s.compare(p,a['frame_ref'],a['frame_ref'],list(reversed(fields)),[query(f) for f in fields],'identical')
    assert r['status']=='PRESERVED_FOR_DECLARED_Q'


def test_L04_incomplete_or_missing_Q_and_unregistered_fields(setup):
    s,p,e,_=setup;a=add(s,p,e)
    assert s.compare(p,a['frame_ref'],a['frame_ref'],['/image_set'],[],'empty')['status']=='UNDETERMINED'
    assert s.compare(p,a['frame_ref'],a['frame_ref'],['/image_set'],[query('/image_order')],'incomplete',complete=False)['status']=='NOT_CHECKED'
    assert s.compare(p,a['frame_ref'],a['frame_ref'],['/missing'],[query('/image_order')],'missing')['status']=='NOT_CHECKED'


def test_L05_semantic_question_not_certified(setup):
    s,p,e,_=setup;a=add(s,p,e);q={'id':'world','kind':'SEMANTIC_QUESTION','field':'','question':'Is the physical world numerically identical?'}
    r=s.compare(p,a['frame_ref'],a['frame_ref'],['/image_set'],[q],'world');assert r['status']=='HYPOTHESIZED_SEMANTIC_LOSS'


def test_R01_R02_existing_export_dispatch_and_replay(setup):
    s,p,e,_=setup;a=add(s,p,e);add(s,p,e,'revision',parents=[a['frame_ref']]);raw,m=export_bundle(s.workspace(p),'private')
    assert m['schema']=='lm-suti.semantic.package/1'
    a=replay(raw);b=replay(raw,'compiled');assert a['status']==b['status']=='PASS' and a['frames']==2 and a['logical_digest']==b['logical_digest']


@pytest.mark.parametrize('prefix',['objects/','core/','application/'])
def test_R03_any_payload_tamper_is_detected(setup,prefix):
    s,p,e,_=setup;add(s,p,e);raw,_=export(s.workspace(p))
    with zipfile.ZipFile(io.BytesIO(raw)) as z:files={n:z.read(n) for n in z.namelist()}
    name=next(n for n in files if n.startswith(prefix));files[name]+=b' '
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    with pytest.raises(AssuranceError,match='MANIFEST_SHA_MISMATCH'):replay(out.getvalue())


def test_R04_metadata_invariance_of_original_assurance(setup):
    s,p,e,_=setup;refs=[]
    for version in ('fixture-a','fixture-b'):
        r=s._register(p,e,canonical(RAW),version,mode='FIXTURE',receipt={'model_version':version,'model_invoked':False})
        refs.append(r)
    w=s.workspace(p);assert refs[0]['frame_ref']!=refs[1]['frame_ref']
    left=w.get(refs[0]['assurance_ref']);right=w.get(refs[1]['assurance_ref'])
    for a,b in zip(left['claims'],right['claims']):
        aa=w.get(a['check_ref']);bb=w.get(b['check_ref']);assert aa['decision']==bb['decision'] and aa['witnesses']==bb['witnesses']


def test_R05_historical_23_of_24_countermodels():
    items=json.loads((Path(__file__).parent/'fixtures/baseline003-fixtures.json').read_text());f=next(x for x in items if x['test_id']=='T17')
    expected=json.loads((Path(__file__).parent/'fixtures/baseline003-results.json').read_text())['results'];runtime=next(x for x in expected if x['test_id']=='T17')['evaluation']['runtime']
    c=core.compile_delta(canonical(json.loads(f['raw'])['payload']),f['task'],f['sources'],runtime)['candidate'];d,w=core.check(c,f['task'],f['sources'])
    payload=next(iter(w.values()))['payload'];assert d['assurance_status']=='REJECTED' and len(payload['countermodels'])==2
    assert [x['count'] for x in payload['distribution']]==[23,1]


def test_R06_no_secret_exfiltration_and_exact_prompt_projection(setup):
    from lm_suti_assurance.semantic_bridge.proposer import public_receipt
    s,p,e,_=setup;raw={**RAW,'counterreadings':['sk-abcdefghijklmnopqrstuvwxyz012345']};add(s,p,e,raw=raw)
    with pytest.raises(AssuranceError,match='EXPORT_SENSITIVE_CONTENT'):export(s.workspace(p))
    receipt={'request':{'source_text':TEXT},'raw_output':canonical(RAW),'events':[{'type':'item.completed','item':{'type':'error','message':'Under-development features enabled: x; /home/private/config.toml'}},{'type':'error','message':'Provider schema error remains visible'}]}
    projected=public_receipt(receipt)
    assert projected['raw_output']==receipt['raw_output'] and projected['request']==receipt['request']
    assert len(projected['events'])==1 and projected['events'][0]['message']=='Provider schema error remains visible'
    assert projected['original_operator_receipt_sha256']==digest(receipt)


def test_R08_idempotence_concurrent_revision_and_conflict(setup):
    s,p,e,_=setup
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:add(s,p,e),range(3)))
    assert len({r['frame_ref'] for r in results})==1
    count=len(s.workspace(p).history());assert add(s,p,e)==results[0] and len(s.workspace(p).history())==count
    raw=copy.deepcopy(RAW);raw['revision_rationale']='Changed input'
    with pytest.raises(AssuranceError,match='REQUEST_KEY_CONFLICT'):add(s,p,e,raw=raw)
    def branch(index):
        raw=copy.deepcopy(RAW);raw['revision_rationale']='Branch '+str(index)
        return add(s,p,e,'branch'+str(index),raw,[results[0]['frame_ref']])
    with ThreadPoolExecutor(max_workers=2) as pool:branches=list(pool.map(branch,[1,2]))
    assert branches[0]['frame_ref']!=branches[1]['frame_ref']
    assert all(s.workspace(p).get(r['frame_ref'])['parent_refs']==[results[0]['frame_ref']] for r in branches)


def test_R09_core_unchanged_and_R10_never_human_pass(setup):
    s,p,e,_=setup;add(s,p,e);value=dossier(s.workspace(p))
    assert value['dossier']['R3']=='PENDING' and core.identity()['verifier_digest']==core.LOCK['verifier_digest']
    assert value['dossier']['execution_permission'] is False


def test_withdrawal_is_append_only_and_blocks_parent(setup):
    s,p,e,_=setup;a=add(s,p,e);w=s.workspace(p);old=w.get(a['frame_ref'])
    s.withdraw(p,a['frame_ref'],'Retain but no longer pursue this reading','withdraw')
    assert w.get(a['frame_ref'])==old and dossier(w)['current_registration_states'][a['frame_ref']]=='FRAME_WITHDRAWN'
    with pytest.raises(AssuranceError,match='WITHDRAWN_PARENT_REQUIRES_NEW_BRANCH_REVIEW'):add(s,p,e,'revive',parents=[a['frame_ref']])


def test_transport_only_profile_keeps_local_uniqueness(setup):
    from lm_suti_assurance.semantic_bridge.proposer import output_schema
    s,p,e,source=setup
    assert schema('proposal')['properties']['observables']['properties']['image_set']['uniqueItems'] is True
    assert 'uniqueItems' not in output_schema(source)['properties']['observables']['properties']['image_set']
    raw=copy.deepcopy(RAW);raw['observables']['image_set']=['duplicate','duplicate']
    assert add(s,p,e,raw=raw)['status']=='FRAME_UNTRUSTED'


def test_all_old_assurance_input_schemas_preserved_and_semantic_additive(tmp_path):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.mcp import register_tools
    from lm_suti_assurance.semantic_bridge.mcp import register_tools as register_semantic
    server=FastMCP('qa');register_tools(server,tmp_path/'root')
    before={t.name:copy.deepcopy(t.parameters) for t in server._tool_manager.list_tools()}
    register_semantic(server,tmp_path/'root')
    after={t.name:t.parameters for t in server._tool_manager.list_tools()}
    assert all(after[n]==v for n,v in before.items()) and len(after)==len(before)+9


def test_owner_pipe_cache_reuse_real_input_contract(setup,tmp_path):
    import subprocess,sys
    from lm_suti_assurance.semantic_bridge.proposer import output_schema,normalized_request,SYSTEM
    s,p,e,source=setup;ed=s.workspace(p).get(e)
    request={'phase':'initial','author':ed['author'],'title':ed['title'],'edition':ed['edition'],'source_text':source['content_utf8'],
             'exact_quote_choices':[r['quote_utf8'] for r in line_index(source['content_utf8']) if r['quote_utf8']],
             'initial_frozen_frame':None,'diagnostic_question':None}
    # Explicit FIXTURE receipt; tests pipe mechanics without claiming model success.
    receipt={'status':'OK','model_requested':'gpt-6.1-sol','request':request,'response_schema':output_schema(source),
             'instructions':SYSTEM,'events':[],'raw_output':canonical(RAW),'model_invoked':False,'test_fixture_only':True}
    spool=tmp_path/'pipe';spool.mkdir(mode=0o700);(spool/digest(p)).mkdir(mode=0o700)
    folder=spool/digest(p)/'fixture';folder.mkdir(mode=0o700)
    (folder/'receipt.json').write_text(canonical(receipt))
    from lm_suti_assurance.semantic_bridge import owner_pipe
    command=[sys.executable,'-I','-B',owner_pipe.__file__,'--spool',str(spool)]
    v={'project':p,'source':source,'edition':ed,'phase':'initial','parent':None,'challenge':None,'request_key':'cache'}
    response=subprocess.run(command,input=canonical(v)+'\n',capture_output=True,text=True,check=True)
    result=json.loads(response.stdout)
    assert result['model_attempt_created'] is False and result['receipt']['raw_output']==canonical(RAW)
    assert not (spool/digest(p)/'MODEL_ATTEMPTS.jsonl').exists()


def test_revision_receipt_cannot_swap_source_or_frozen_parent(setup):
    s,p,e,_=setup;first=add(s,p,e);w=s.workspace(p)
    receipt={'status':'OK','model_version':'fixture-only','request':{'source_text':'Different bytes','phase':'revise','initial_frozen_frame':w.get(first['frame_ref'])},'model_invoked':False}
    r=s._register(p,e,canonical(RAW),'wrong-context',parents=[first['frame_ref']],mode='HOSTED_MODEL',receipt=receipt)
    assert r['status']=='FRAME_UNTRUSTED' and r['reason_code']=='MODEL_SOURCE_CONTEXT_MISMATCH'


def test_mcp_json_string_is_not_preparsed_as_optional_union(setup):
    import asyncio
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.semantic_bridge.mcp import register_tools
    s,p,e,_=setup;server=FastMCP('semantic-json-contract');register_tools(server,s.base.root)
    async def invoke():
        return await server._tool_manager.call_tool('semantic_draft',{'project':p,'edition_ref':e,'request_key':'json-string-regression',
                                      'proposal_json':canonical({'source_sha256':'0'*64,'execution_permission':True})})
    result=asyncio.run(invoke());assert result['status']=='FRAME_UNTRUSTED'


def test_mcp_large_export_replay_uses_project_bound_sha(setup):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.semantic_bridge.mcp import register_tools
    s,p,e,_=setup;add(s,p,e);server=FastMCP('bounded-replay');register_tools(server,s.base.root)
    export_fn=server._tool_manager.get_tool('semantic_export').fn
    replay_fn=server._tool_manager.get_tool('semantic_replay').fn
    result=export_fn(p,'private',True)
    assert result['status']=='EXPORTED' and replay_fn(p,result['bundle_ref'])['status']=='PASS'
    assert replay_fn('other',result['bundle_ref'])['reason_code']=='EXPORT_NOT_IN_PROJECT'
    missing=export_fn(p,'private',False)
    assert replay_fn(p,missing['bundle_ref'])['reason_code']=='MISSING_SOURCE_DEPENDENCY'
