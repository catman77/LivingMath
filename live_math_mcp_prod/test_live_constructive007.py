from live_constructive007 import interpret_constructive


def test_constructor_exists():
    assert callable(interpret_constructive)

import copy,json
from pathlib import Path
import pytest
from live_constructive007_worlds import create_world,frame,view
from live_constructive007_native import Ledger,Port
from live_constructive007_source import load_frame,BindingError
from live_constructive007_oracle import pairs,attention
from live_transfer006 import interpret as B1,attend
from normalizer import normalize_context,Budget,digest


@pytest.fixture(params=range(8))
def world(request,tmp_path):return create_world(tmp_path/'source.sqlite3',request.param)


def test_all_witnesses_against_independent_native_replay(world):
    f=frame(world)
    for pair in pairs(world['history'],world['query']):
        a=interpret_constructive(f.fork(Ledger()),pair['left'],pair['right'],world['certificate_ref'])
        b=B1(f.fork(Ledger()),pair['left'],pair['right'])
        assert (a['status']=='NEW_DISTINCTION')==pair['hidden'],(world['id'],pair,a)
        assert (b['status']=='NEW_DISTINCTION')==pair['hidden']
        assert not a['execution_allowed'] and a['proof_status']=='unverified'
        if pair['hidden']:
            tid=a['witness']['test_id'];assert a['predictions']==[pair['Sig_left'][tid],pair['Sig_right'][tid]]
            assert a['predictions'][0]!=a['predictions'][1]
            assert a['fingerprint']==b['fingerprint']
        assert a['cost_ledger']['total_native_calls']==len(a['operations_trace'])


def test_cold_native_savings_or_exact_blackbox_fallback(world):
    f=frame(world);l,r=world['refs']['h0'],world['refs']['h1']
    c=interpret_constructive(f.fork(Ledger()),l,r,world['certificate_ref']);b=f.fork(Ledger());out=B1(b,l,r)
    assert c['status']==out['status']=='NEW_DISTINCTION'
    if world['certificate_ref']:
        assert c['strategy']=='CONSTRUCTIVE_VALIDATED'
        assert c['cost_ledger']['total_native_calls']<sum(out['primitive_calls'].values())
        assert c['law']['status']=='SOURCE_SCHEMA_CERTIFIED'
        assert 'law_validation' not in c['cost_ledger']['native_by_stage']
    else:
        assert c['strategy']=='FALLBACK_BOUNDED'
        assert c['cost_ledger']['native']==out['primitive_calls']


def test_T_is_independent_of_constructor_witness(world):
    f=frame(world);before=attend(f.fork(Ledger()));interpret_constructive(f.fork(Ledger()),world['refs']['h0'],world['refs']['h1'],world['certificate_ref'])
    after=attend(f.fork(Ledger()));reference=attention(world['history'],world['query'])
    assert before['status']==after['status']==reference['status']
    assert before.get('test_id')==after.get('test_id')==reference['selected_test_id']
    assert before.get('ranking')==after.get('ranking')
    if reference['ranking']:
        assert [{k:r[k] for k in reference['ranking'][0]} for r in before['ranking']]==reference['ranking']


@pytest.mark.parametrize('fault',['hash','scope','version','observer','kind','partial'])
def test_false_or_partial_law_falls_back_without_false_claim(world,fault):
    if not world['certificate_ref']:return
    h=copy.deepcopy(world['history']);q=world['query']
    for e in h['tables']['events']:
        if 'event:'+str(e['id'])==world['certificate_ref']:
            p=json.loads(e['content']);cert=p['source_certificate']
            if fault=='hash':cert['source_hash']='0'*64
            elif fault=='scope':cert['scope']='other'
            elif fault=='version':cert['version']=999
            elif fault=='observer':cert['observer_hash']='f'*64
            elif fault=='kind':cert['kind']='commuting-left-projection'
            else:cert['coverage']=[]
            e['content']=json.dumps(p)
    f=load_frame(normalize_context(h,'007',[q],'C2'),h,q)
    c=interpret_constructive(f.fork(Ledger()),world['refs']['h0'],world['refs']['h1'],world['certificate_ref'])
    assert c['strategy']=='FALLBACK_BOUNDED' and c['status']=='NEW_DISTINCTION'
    assert c['proof_status']=='unverified' and not c['execution_allowed']


def test_canonical_novelty_under_primitive_rename(world):
    f=frame(world);l,r=world['refs']['h0'],world['refs']['h1'];original=interpret_constructive(f.fork(Ledger()),l,r,world['certificate_ref'])
    h=copy.deepcopy(world['history']);names={a:'renamed_'+a for a in f.spec['parameters']['actions']}
    for e in h['tables']['events']:
        p=json.loads(e['content'])
        if 'word' in p:p['word']=[names[a] for a in p['word']]
        if 'source_spec' in p:
            spec=p['source_spec'];spec['parameters']['actions']=[names[a] for a in spec['parameters']['actions']]
            for t in spec['tests']:t['suffix']=[names[a] for a in t['suffix']]
        e['content']=json.dumps(p)
    renamed=load_frame(normalize_context(h,'007',[world['query']],'C2'),h,world['query'])
    # Old law correctly becomes stale after its bound source record is renamed.
    out=interpret_constructive(renamed.fork(Ledger()),l,r,world['certificate_ref'],known=(original['fingerprint'],))
    assert out['status']=='NO_NEW_DISTINCTION'


@pytest.mark.parametrize('fault',['C4','budget','project','missing','stale','germ'])
def test_source_fail_closed(world,fault):
    h=copy.deepcopy(world['history']);q=copy.deepcopy(world['query']);v=view(world)
    if fault=='C4':v=view(world,'C4')
    if fault=='budget':v=view(world,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
    if fault=='project':q['project']='FOREIGN'
    if fault=='missing':
        v['audit_context']['tables']['events']=v['audit_context']['tables']['events'][1:];v['certificate']['context_digest']=digest(v['audit_context'])
    if fault=='stale':q['version']=999;v=normalize_context(h,'007',[q],'C2')
    if fault=='germ':
        h['tables']['events'][0]['content']=json.dumps({'word':[],'version':1,'scope':q['scope'],'representation':'analytic_germ'})
        v=normalize_context(h,'007',[q],'C2')
    with pytest.raises(BindingError):load_frame(v,h,q)


def test_hidden_adapter_native_work_is_counted(tmp_path):
    w=create_world(tmp_path/'source.sqlite3',6);f=frame(w);p=copy.deepcopy(f.spec['parameters']);p['adapter_repeat']=2
    ledger=Ledger();port=Port(p,ledger);s=port.load([]);port.observe(s,f.spec['observer'])
    assert ledger.native['observe']==2
    assert ledger.work['input:adapter_observe']==1


def test_source_permutation_composition_is_noncommutative(tmp_path):
    w=create_world(tmp_path/'source.sqlite3',1);f=frame(w);p=f.port();a,b=f.spec['parameters']['actions'][1],f.spec['parameters']['actions'][5]
    assert p.load([a,b]).value!=p.load([b,a]).value
