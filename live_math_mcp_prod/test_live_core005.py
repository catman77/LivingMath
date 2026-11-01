"""Finite source, witness, attention and boundary checks for experimental005."""
from live_core005 import interpret_distinction, transfer_attention, apply_feedback


def test_experimental_operations_are_callable():
    assert callable(interpret_distinction) and callable(transfer_attention) and callable(apply_feedback)

import copy
import itertools
import json
from pathlib import Path

import pytest
from live_core005 import register_state, analytic_continuation
from live_core005_worlds import create_world, build_view, append_observation
from live_core005_oracle import all_pairs, attention, feedback, source_spec, execute
from normalizer import Budget, digest, normalize_context
from research_store import ResearchStore


@pytest.fixture(params=range(4))
def world(request,tmp_path):
    return create_world(tmp_path/'source.sqlite3',request.param)


def test_all_registered_pairs_have_exact_witness_and_no_missed_or_false_distinction(world):
    v=build_view(world)
    for pair in all_pairs(world['history'],world['query']):
        result=interpret_distinction(v,world['history'],world['query'],pair['left_ref'],pair['right_ref'])
        assert not result['execution_allowed'] and result['proof_status']=='unverified'
        assert (result['status']=='NEW_DISTINCTION') == pair['hidden_distinction'],pair
        if pair['hidden_distinction']:
            w=result['witness']
            a=next(s for s in pair['Sig_left'] if s['test_id']==w['test_id'])
            b=next(s for s in pair['Sig_right'] if s['test_id']==w['test_id'])
            assert a['suffix']==b['suffix']==w['suffix']
            assert a['readout']==w['left'] and b['readout']==w['right'] and w['left']!=w['right']
            assert result['guard']['source_family_only'] and not result['guard']['generalization_outside_guard']


def test_attention_exactly_matches_independent_pairwise_oracle(world):
    v=build_view(world);out=transfer_attention(v,world['history'],world['query'])
    expected=attention(world['history'],world['query'])
    assert out['status']==expected['status']=='ATTENTION_PROPOSED'
    assert out['test_id']==expected['selected_test_id']
    assert out['ties']==expected['optimal_test_ids']
    assert [{k:r[k] for k in ('test_id','cost','loss','expected_remaining')} for r in out['ranking']]==expected['ranks']
    assert not out['execution_allowed'] and not out['completion_allowed']


def test_negative_feedback_excludes_dependents_preserves_independent_and_sources(world):
    v=build_view(world);a=transfer_attention(v,world['history'],world['query'])
    after,ref=append_observation(world,a);post=build_view(after)
    out=apply_feedback(post,after['history'],after['query'],ref)
    receipt=json.loads(next(e for e in after['history']['tables']['events'] if 'event:'+str(e['id'])==ref)['content'])['observation']
    expected=feedback(world['history'],world['query'],receipt)
    assert {h['id']:h['status'] for h in out['hypotheses']}==expected
    assert expected['I']=='ACTIVE' and any(x=='EXCLUDED_DEPENDENCY' for x in expected.values())
    original={e['id']:e for e in world['history']['tables']['events']}
    current={e['id']:e for e in after['history']['tables']['events']}
    assert all(current[i]==r for i,r in original.items())
    t=transfer_attention(post,after['history'],after['query'],ref)
    oracle=attention(after['history'],after['query'],[i for i,s in expected.items() if s!='ACTIVE'])
    assert t['status']==oracle['status']
    if oracle['optimal_test_ids']:assert t['test_id']==oracle['selected_test_id']


def test_renaming_and_equal_state_different_source_do_not_create_novelty(world):
    v=build_view(world);refs=world['refs']
    out=interpret_distinction(v,world['history'],world['query'],refs['h3'],refs['h0'])
    assert out['status']=='NEW_DISTINCTION'
    renamed=interpret_distinction(v,world['history'],world['query'],refs['h3'],refs['h0'],
                                 known=(out['fingerprint'],),title='New impressive theory name')
    assert renamed['status']=='NO_NEW_DISTINCTION'
    duplicate=interpret_distinction(v,world['history'],world['query'],refs['h4'],refs['copy4'])
    assert refs['h4']!=refs['copy4'] and duplicate['status']=='NO_NEW_DISTINCTION'
    assert duplicate['source_refs'][1:] and len(duplicate['source_refs'])==3


@pytest.mark.parametrize('case',['C4','budget','missing','hash','catalog','foreign','stale','closed','point_germ','observer','alias'])
def test_fail_closed_required_controls(world,case):
    h=copy.deepcopy(world['history']);q=copy.deepcopy(world['query']);v=build_view(world)
    left,right=world['refs']['h3'],world['refs']['h0'];other=None
    if case=='C4':v=build_view(world,'C4')
    if case=='budget':v=build_view(world,'C3',Budget(max_output_bytes=4096,max_tokens=1024))
    if case=='missing':
        v['audit_context']['tables']['events']=[e for e in v['audit_context']['tables']['events'] if e['id']!=int(left.split(':')[1])]
        v['certificate']['context_digest']=digest(v['audit_context'])
    if case=='hash':v['audit_context']['tables']['events'][0]['content']+='tamper'
    if case=='catalog':v['source_catalog'][left]='0'*64
    if case=='foreign':q['project']='FOREIGN'
    if case in {'stale','closed'}:
        store=ResearchStore(Path(world['database']))
        store.frontier.update(q['move']['active_frontier_id'],1,{'status':'TESTING' if case=='stale' else 'REFUTED',
            **({} if case=='stale' else {'closure_reason':'Synthetic control','evidence_refs':[world['refs']['root']],
                'reopen_conditions':['New version with scoped evidence.']})})
        if case=='closed':q['version']=2
        from normalizer import read_history
        h=read_history(Path(world['database']),world['project']);v=normalize_context(h,'finite',[q],'C2')
    if case=='point_germ':left,right=world['refs']['point'],world['refs']['germ']
    if case=='alias':left=world['refs']['alias']
    if case=='observer':other='parity' if world['index']!=1 else 'x'
    out=interpret_distinction(v,h,q,left,right,other_observer=other)
    assert out['status']=='INSUFFICIENT_CONTEXT' and not out['execution_allowed'],(case,out)
    if case not in {'point_germ','observer','alias'}:
        assert transfer_attention(v,h,q)['status']=='INSUFFICIENT_CONTEXT'


def test_native_closed_form_matches_independent_execution(world):
    spec=source_spec(world['history'],world['query'])
    for row in world['history']['tables']['events']:
        data=json.loads(row['content'])
        if 'word' not in data:continue
        for test in spec['tests']:
            assert analytic_continuation(register_state(data['word']),test['suffix'])==execute(data['word']+test['suffix'])
