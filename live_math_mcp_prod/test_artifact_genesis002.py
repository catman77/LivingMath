"""Pre-registered engineering acceptance for raw-source hypothesis genesis."""
from copy import deepcopy

import pytest

from artifact_genesis.contract import RawPacket
from artifact_genesis.proposer import propose
from artifact_genesis.audit import source_audit
from artifact_genesis.binding import bind_and_challenge, nontriviality
from artifact_genesis.source import packet_from_text, SourceVault


def sample():
    return packet_from_text('fixture','The pilot turns the wheel.\nAnd the pilot closes the hatch.\nBut the guard does not turn the wheel.\n',language='en')


def test_raw_packets_have_no_editorial_relation_or_target_fields():
    p=sample()
    with pytest.raises(ValueError):RawPacket.model_validate({**p.model_dump(),'relations':[]})
    result=propose(p)
    assert len(result['hypotheses'])>=2
    assert all(h['target_binding'] is None and h['alternatives'] for h in result['hypotheses'])


def test_source_audit_rejects_fake_quotes_and_edition_hash_drift():
    p=sample();h=propose(p)['hypotheses'][0]
    assert source_audit(h,p)['quotes_valid']
    bad=deepcopy(h);bad['quoted_evidence'][0]['quote']+=' fabricated'
    assert source_audit(bad,p)['status']=='REJECTED_SOURCE'
    bad=deepcopy(h);bad['document_sha256']='0'*64
    assert source_audit(bad,p)['status']=='REJECTED_SOURCE'
    bad=deepcopy(h);bad['edition']='other-edition'
    assert source_audit(bad,p)['status']=='REJECTED_SOURCE'


def test_independent_source_audit_does_not_accept_target_confirmation():
    p=sample();h=propose(p)['hypotheses'][0]
    with pytest.raises(TypeError):source_audit(h,p,target_result={'status':'proved'})


def test_negation_and_subject_hypotheses_have_competing_readings():
    rows=propose(sample())['hypotheses']
    assert any(h['family']=='negation_subject' for h in rows)
    assert any(source_audit(h,sample())['status']!='PROXY_SUPPORTED' for h in rows)


def test_binding_requires_source_audit_and_retains_dav_counterexample():
    p=sample();rows=propose(p)['hypotheses']
    h=next(h for h in rows if h['family']=='joint_analogy' and source_audit(h,p)['status']=='PROXY_SUPPORTED')
    with pytest.raises(ValueError):bind_and_challenge(h,{'status':'REJECTED_SOURCE'})
    result=bind_and_challenge(h,source_audit(h,p))
    assert result['counterexample']['actual_relation'] is False
    assert result['revision']['old_binding']!=result['revision']['new_binding']
    assert result['revision']['source_truth_established'] is False


def test_empty_premise_cannot_pass_as_nontrivial_law():
    from davcore.adapters import Adapter,AdapterSpec
    from davcore.ast import implication
    a=Adapter(AdapterSpec(kind='graph'))
    result=nontriviality(a,implication('S0','S0','P','P'))
    assert result['status']=='FAIL_VACUOUS_LAW'


def test_holdout_cannot_be_opened_before_prediction_seal(tmp_path):
    from artifact_genesis.source import build_fixture_vault
    root=build_fixture_vault(tmp_path)
    vault=SourceVault(root)
    with pytest.raises(PermissionError):vault.packet('hidden')
    assert vault.packet('train').spans
    seal=vault.seal([{'id':'prediction','source_relation':'condition','target_free':True}])
    assert vault.packet('hidden',seal=seal).spans
    broken={**seal,'prediction_sha256':'0'*64}
    with pytest.raises(ValueError):vault.packet('hidden',seal=broken)
