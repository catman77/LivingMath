from live_transfer006 import interpret, attend


def test_portable_operations_exist():
    assert callable(interpret) and callable(attend)

import copy
import json
from pathlib import Path
import pytest
from live_transfer006_worlds import create_world,frame,view
from live_transfer006_oracle import pairs,attention,unpack,raw_run
from live_transfer006_source import load_frame,BindingError
from live_transfer006_baselines import flat_pair,old_pair
from normalizer import Budget,digest


@pytest.fixture(params=range(8))
def world(request,tmp_path):
    return create_world(tmp_path/'source.sqlite3',request.param)


def test_finite_witnesses_and_bounded_completeness(world):
    f=frame(world)
    for expected in pairs(world['history'],world['query']):
        out=interpret(f,expected['left'],expected['right'])
        assert (out['status']=='NEW_DISTINCTION')==expected['hidden'],(world['id'],expected,out)
        assert not out['execution_allowed'] and out['proof_status']=='unverified'
        if expected['hidden']:
            tid=out['witness']['test_id']
            assert out['predictions']==[expected['Sig_left'][tid],expected['Sig_right'][tid]]
            assert out['predictions'][0]!=out['predictions'][1]
            assert out['source_hashes'] and out['operations_trace']
        elif expected['current'][0]==expected['current'][1]:
            assert out['status']=='UNKNOWN_BOUNDED' and not out['asserts_equivalence']


def test_attention_ranking_and_primary_partiality(world):
    f=frame(world);out=attend(f);expected=attention(world['history'],world['query'])
    assert out['status']==expected['status']
    if expected['ranking']:
        assert out['test_id']==expected['selected_test_id'] and out['ties']==expected['ties']
        assert [{k:x[k] for k in expected['ranking'][0]} for x in out['ranking']]==expected['ranking']
        assert all(v['readout']['defined'] and all(v['readout']['admissibility']) for x in out['ranking'] for v in x['counterfactuals'])


def test_short_budget_and_renaming_do_not_create_equivalence(world):
    f=frame(world);a,b=f.spec['histories'][:2]
    short=interpret(f,a,b,max_calls=1)
    assert short['status']=='UNKNOWN_BOUNDED' and not short['execution_allowed']
    for expected in pairs(world['history'],world['query']):
        if expected['hidden']:
            out=interpret(f,expected['left'],expected['right'])
            again=interpret(f,expected['right'],expected['left'],known=(out['fingerprint'],),title='Changed title')
            assert again['status']=='NO_NEW_DISTINCTION';break


@pytest.mark.parametrize('case',['C4','budget','missing','hash','project','observer','oracle_hint','source_alias','mutated_frame'])
def test_adversarial_controls(world,case):
    source=copy.deepcopy(world['history']);q=copy.deepcopy(world['query']);v=view(world)
    if case=='C4':v=view(world,'C4')
    if case=='budget':v=view(world,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
    if case=='missing':
        v['audit_context']['tables']['events']=v['audit_context']['tables']['events'][1:]
        v['certificate']['context_digest']=digest(v['audit_context'])
    if case=='hash':v['source_catalog'][world['refs']['h0']]='0'*64
    if case=='project':q['project']='FOREIGN'
    if case=='oracle_hint':
        from normalizer import normalize_context
        for e in source['tables']['events']:
            if 'event:'+str(e['id'])==q['root_ref']:
                d=json.loads(e['content']);d['source_spec']['oracle_answer']='Pretend this is proven';e['content']=json.dumps(d)
        v=normalize_context(source,'finite',[q],'C2')
    if case in {'C4','budget','missing','hash','project','oracle_hint'}:
        with pytest.raises(BindingError):load_frame(v,source,q)
    else:
        f=load_frame(v,source,q);left=world['refs']['h0'];right=world['refs']['h1'];other=None
        if case=='observer':other={'projection':'primary','mod':13}
        if case=='source_alias':left='event:999999'
        if case=='mutated_frame':f.spec['version']=9
        out=interpret(f,left,right,observer=other)
        assert out['status']=='FAIL_CLOSED' and not out['execution_allowed']
