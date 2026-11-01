"""Adversarial boundary and scope regressions beyond the frozen scientific acceptance."""
import asyncio
import json

import pytest

from artifact_translation.contract import ProposalRequest
from artifact_translation.contract import SourceGraph
from artifact_translation.generator import propose, semantic_fingerprint
from artifact_translation.checker import independent_apply, check_translation
from artifact_translation.mcp import generate, private_clone_guard
from artifact_translation.network import Network, apply
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import eq
from davcore.finite import check
from test_artifact_translation001 import graph


def test_generator_process_has_no_checker_or_external_input():
    result=asyncio.run(generate(ProposalRequest(graph=graph())))
    assert result['worker_isolation']['checker_imported'] is False
    assert result['worker_isolation']['hidden_answer_supplied'] is False
    assert result['worker_isolation']['filesystem_after_imports']=='DENIED'
    assert result['worker_isolation']['filesystem_probe_denied']
    assert result['worker_isolation']['network_probe_denied']
    assert result['duplicates'] and any(x['edit']=='split_roles' for x in result['duplicates'])


def test_all_reaction_transitions_have_independent_stoichiometric_replay():
    rows=propose(ProposalRequest(graph=graph()))['candidates']
    for row in rows:
        n=Network.model_validate(row['network']);a=Adapter(AdapterSpec(kind='reaction_network',reaction_network=n))
        for state in a.states():
            for operation in a.ops:
                assert apply(n,operation,state)==independent_apply(n,operation,state)


def test_no_unsound_complete_proof_of_empirical_or_projected_adapter():
    n=Network.model_validate(propose(ProposalRequest(graph=graph()))['candidates'][0]['network'])
    empirical=Adapter(AdapterSpec(kind='reaction_network',reaction_network=n,fidelity='empirical'))
    assert check(empirical,eq('Id','Id'))['status']=='consistent_with_observations'
    projected=Adapter(AdapterSpec(kind='reaction_network',reaction_network=n,mask=1))
    with pytest.raises(ValueError,match='PROJECTED_ADAPTER'):check(projected,eq('Id','Id'))


def test_descriptor_cannot_be_smuggled_into_previous_kind():
    n=Network.model_validate(propose(ProposalRequest(graph=graph()))['candidates'][0]['network'])
    with pytest.raises(ValueError):AdapterSpec(kind='gate6',reaction_network=n)
    with pytest.raises(ValueError):AdapterSpec(kind='reaction_network')


def test_hidden_guard_is_not_deduplicated_as_identical_observed_dynamics():
    rows=propose(ProposalRequest(graph=graph()))['candidates']
    c=next(x for x in rows if x['edit']=='catalytic');hidden=next(x for x in rows if x['edit']=='latent_guard')
    assert semantic_fingerprint(c)!=semantic_fingerprint(hidden)


def test_reverse_orientation_cannot_pass_source_fidelity():
    row=next(x for x in propose(ProposalRequest(graph=graph()))['candidates'] if x['edit']=='reverse_orientation')
    assert any(x['reason']=='SOURCE_ORIENTATION_NOT_RETURNED' for x in check_translation(graph(),row)['conflicts'])


def test_critical_many_to_one_mapping_has_explicit_loss_even_with_reverse_refs():
    row=next(x for x in propose(ProposalRequest(graph=graph()))['candidates'] if x['edit']=='merge_roles')
    failures=check_translation(graph(),row)['conflicts']
    assert failures[0]['reason']=='SOURCE_DISTINCTION_ERASED'
    assert any(x['kind']=='ROLE_COLLAPSE' for x in row['loss_ledger'])
    assert not any(x['reason']=='SOURCE_NODE_REVERSE_TRACE_MISSING' for x in failures)


def test_clone_guard_rejects_alias_to_source_and_world_writable_root(tmp_path):
    root=tmp_path/'private';root.mkdir(mode=0o700);canonical=root/'research.sqlite3';dav=root/'dav.sqlite3'
    canonical.write_text('fixture');dav.write_text('fixture')
    receipt={'purpose':'ARTIFACT_TRANSLATION001_PRIVATE_BACKUP_CLONES',
             'canonical':{'source':str(canonical),'inode':canonical.stat().st_ino},
             'dav':{'source':str(dav),'inode':dav.stat().st_ino}}
    p=root/'clone-receipt.json';p.write_text(json.dumps(receipt));p.chmod(0o600)
    with pytest.raises(ValueError,match='PRODUCTION_DATABASE_FORBIDDEN'):private_clone_guard(root,canonical,dav)
    root.chmod(0o755)
    with pytest.raises(ValueError,match='OWNER_ONLY'):private_clone_guard(root,canonical,dav)


def test_noncritical_many_to_one_still_requires_an_explicit_loss_ledger():
    from copy import deepcopy
    g=SourceGraph.model_validate({'id':'cooccur','nodes':[
        {'id':'a','source_refs':['s1']},{'id':'b','source_refs':['s2']}],
        'relations':[{'id':'r','kind':'cooccur','src':'a','dst':'b','source_refs':['s1','s2']}]})
    c=deepcopy(propose(ProposalRequest(graph=g,allowed_edits=['transition']))['candidates'][0])
    c['mapping']['b']=c['mapping']['a'];c['network']['species'][0]['source_refs']=['s1','s2']
    assert any(x['reason']=='UNDECLARED_MANY_TO_ONE_LOSS' for x in check_translation(g,c)['conflicts'])


def test_contrast_control_must_retain_mapping_loss_after_removing_constraint():
    from copy import deepcopy
    from davcore.ast import digest
    original=graph();packet=original.model_dump()
    bad=next(x for x in propose(ProposalRequest(graph=original))['candidates'] if x['edit']=='merge_roles')
    packet['relations']=[r for r in packet['relations'] if r['kind']!='contrast']
    counterfactual=deepcopy(bad);counterfactual['source_graph_sha256']=digest(packet)
    assert check_translation(SourceGraph.model_validate(packet),counterfactual)['status']=='FORMAL_TRANSLATION_VALID'
    assert check_translation(original,bad)['status']=='FAIL_FIDELITY'
    counterfactual['loss_ledger']=[]
    assert check_translation(SourceGraph.model_validate(packet),counterfactual)['status']=='FAIL_FIDELITY'


def test_lexical_baseline_candidate_id_is_stable_across_python_hash_seeds():
    import os
    import subprocess
    import sys
    script="""
from artifact_translation.contract import SourceGraph, ProposalRequest
from artifact_translation.generator import propose
from artifact_translation.experiment import lexical_baseline
g=SourceGraph.model_validate({'id':'seed-test','nodes':[
    {'id':x,'source_refs':['s'+x]} for x in 'abcd'],
    'relations':[{'id':'r1','kind':'cooccur','src':'a','dst':'c','source_refs':['sa','sc']},
                 {'id':'r2','kind':'cooccur','src':'b','dst':'d','source_refs':['sb','sd']}]})
c=propose(ProposalRequest(graph=g,allowed_edits=['transition']))['candidates'][0]
spans={k:{'exact_quote':v} for k,v in zip(['sa','sb','sc','sd'],['left one','left two','right one','right two'])}
print(lexical_baseline({'graph':g.model_dump()},c,{},spans)['candidate_id'])
"""
    values=[subprocess.check_output([sys.executable,'-B','-c',script],env={**os.environ,'PYTHONHASHSEED':str(seed)},text=True).strip()
            for seed in [0,1,4,13]]
    assert len(set(values))==1
