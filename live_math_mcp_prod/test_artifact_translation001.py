"""Acceptance tests written and frozen before the generator implementation."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from artifact_translation.contract import SourceGraph, ProposalRequest
from artifact_translation.generator import propose, semantic_fingerprint
from artifact_translation.network import Network, fire, enabled
from artifact_translation.checker import check_translation, repair, evaluate_laws
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import eq
from davcore.finite import check
from davcore.smt import check_smt


def graph():
    return SourceGraph.model_validate({
        'id': 'fixture',
        'nodes': [{'id': x, 'kind': 'symbolic_role', 'source_refs': ['span-'+x]} for x in ['a','b','c']],
        'relations': [
            {'id': 'ab','kind': 'sequence','src': 'a','dst': 'b','source_refs': ['span-a','span-b'],'grade': 'B'},
            {'id': 'bc','kind': 'sequence','src': 'b','dst': 'c','source_refs': ['span-b','span-c'],'grade': 'B'},
            {'id': 'ac','kind': 'contrast','src': 'a','dst': 'c','source_refs': ['span-a','span-c'],'grade': 'B'}],
        'scope': 'textual_relations_not_physical_time'})


def proposals():
    return propose(ProposalRequest(graph=graph(),max_candidates=12))['candidates']


def test_competing_conserved_and_catalytic_models():
    rows=proposals()
    valid=[x for x in rows if check_translation(graph(),x)['status']=='FORMAL_TRANSLATION_VALID']
    assert len({semantic_fingerprint(x) for x in valid})>=2
    assert {x['edit'] for x in valid}>={'transition','catalytic'}


def test_distinction_conflict_retained_and_repaired():
    bad=next(x for x in proposals() if x['edit']=='merge_roles')
    before=deepcopy(bad);failure=check_translation(graph(),bad)
    assert failure['status']=='FAIL_FIDELITY' and failure['conflicts']
    fixed=repair(graph(),bad)
    assert bad==before and fixed['original_counterexample']==failure['conflicts'][0]
    assert check_translation(graph(),fixed['candidate'])['status']=='FORMAL_TRANSLATION_VALID'


def test_source_reverse_map_forgery_is_rejected():
    c=next(x for x in proposals() if x['edit']=='transition')
    c=deepcopy(c);c['network']['reactions'][0]['source_relation_ids']=['nonexistent']
    assert check_translation(graph(),c)['status']=='FAIL_FIDELITY'


def test_network_rejects_real_chemistry_rates_and_bad_stoichiometry():
    c=next(x for x in proposals() if x['edit']=='transition')['network']
    for mutate in ['rate_law','chemical_species','negative']:
        d=deepcopy(c)
        if mutate=='rate_law':d['rate_law']='invented'
        elif mutate=='chemical_species':d['species'][0]['provenance_kind']='chemical_species'
        else:d['reactions'][0]['reactants'][d['species'][0]['id']]=-1
        with pytest.raises(ValidationError):Network.model_validate(d)


def test_guarded_reaction_preserves_disabled_state():
    c=next(x for x in proposals() if x['edit']=='transition');n=Network.model_validate(c['network'])
    assert not enabled(n,0,0) and fire(n,0,0)==0
    a=Adapter(AdapterSpec(kind='reaction_network',reaction_network=n))
    assert len(a.states())==2**len(n.species)
    assert check(a,eq('Id','Id'))['status']=='proved'
    assert check_smt(a,eq('Id','Id'))['reason']=='REACTION_SMT_NOT_IMPLEMENTED_USE_EXACT_FINITE'


def test_alpha_names_do_not_change_observed_semantics():
    c=next(x for x in proposals() if x['edit']=='transition');renamed=deepcopy(c)
    rename={s['id']:'renamed_'+str(i) for i,s in enumerate(c['network']['species'])}
    for s in renamed['network']['species']:s['id']=rename[s['id']];s['label']='unrelated name'
    for r in renamed['network']['reactions']:
        for k in ['reactants','products']:r[k]={rename[s]:v for s,v in r[k].items()}
    renamed['mapping']={k:rename[v] for k,v in renamed['mapping'].items()}
    assert semantic_fingerprint(c)==semantic_fingerprint(renamed)


def test_bounded_search_and_no_hidden_answer_input():
    req=ProposalRequest(graph=graph(),max_candidates=2)
    out=propose(req)
    assert len(out['candidates'])<=2 and out['search_status']=='SEARCH_EXHAUSTED'
    with pytest.raises(ValidationError):ProposalRequest.model_validate({**req.model_dump(),'expected_answer':True})
    assert all(x['empirically_realized']=='UNKNOWN' for x in out['candidates'])


def test_nested_dav_laws_keep_scope_and_negative_evidence():
    c=next(x for x in proposals() if x['edit']=='transition')
    rows=evaluate_laws(c,max_laws=24)
    assert any(x['status']=='refuted' and x['counterexample'] for x in rows)
    assert any(x['status']=='proved' and x['nontrivial'] for x in rows)
    assert all(x['proof_status']=='unverified' and not x['execution_permission']['allowed'] for x in rows)
