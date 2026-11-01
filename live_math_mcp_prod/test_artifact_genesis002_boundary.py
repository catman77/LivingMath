"""Cross-process, semantic-scope, source and append-only adversarial checks."""
import asyncio
from copy import deepcopy

import pytest

from artifact_genesis.audit import source_audit
from artifact_genesis.contract import RawPacket
from artifact_genesis.process import run_worker
from artifact_genesis.proposer import propose
from artifact_genesis.source import packet_from_text,build_fixture_vault,SourceVault
from artifact_genesis.journal import Journal


def test_raw_worker_never_imports_editor_generator_or_target_checker():
    p=packet_from_text('safe','A thing moves.\nAnd another thing changes.\n')
    result=asyncio.run(run_worker('worker',p.model_dump()))
    assert result['isolation']['forbidden_modules_loaded']==[]
    assert result['isolation']['probes']=={'file':'DENIED','socket':'DENIED'}


def test_embedded_labels_cannot_be_smuggled_as_grammar_or_source_metadata():
    p=packet_from_text('source','If the lamp lights, the latch closes.\n')
    d=p.model_dump();d['grammar']={'expected_labels':['condition']}
    with pytest.raises(ValueError):RawPacket.model_validate(d)
    d=p.model_dump();d['spans'][0]['source_address']={'source_graph':{'x':'y'}}
    with pytest.raises(ValueError):RawPacket.model_validate(d)


def test_conditional_H_roles_are_exact_independently_addressed_subclauses():
    p=packet_from_text('source','If the lamp lights, the latch closes.\n')
    h=next(h for h in propose(p)['hypotheses'] if h['proposed_relation']['claim']=='explicit_conditional')
    assert source_audit(h,p)['status']=='PROXY_SUPPORTED'
    bad=deepcopy(h);bad['roles'][0]['start']+=1
    assert source_audit(bad,p)['status']=='REJECTED_SOURCE'
    bad=deepcopy(h);bad['source_spans']=['foreign-document:span']
    assert source_audit(bad,p)['status']=='REJECTED_SOURCE'


def test_local_history_detects_modification_and_cannot_be_reopened(tmp_path):
    p=tmp_path/'journal.jsonl';j=Journal(p);j.append('PROPOSED',{'H':'old'});j.append('REVISED',{'H':'new','parent':'old'})
    assert Journal.verify(p)['entries']==2
    with pytest.raises(FileExistsError):Journal(p)
    p.write_text(p.read_text().replace('new','forged'))
    with pytest.raises(ValueError):Journal.verify(p)


def test_postchecker_rejects_changed_prediction_seal_without_target_help(tmp_path):
    p=packet_from_text('held','Without this no thing may change.\n')
    payload={'packet':p.model_dump(),'predictions':[{'id':'p','language':'en','source_relation':'negated_prerequisite'}],
             'seal':{'prediction_sha256':'0'*64}}
    with pytest.raises(ValueError):asyncio.run(run_worker('postcheck',payload))


def test_sealed_visibility_and_cross_document_context(tmp_path):
    root=build_fixture_vault(tmp_path);v=SourceVault(root)
    with pytest.raises(PermissionError):v.packet('hidden')
    p=v.packet('train');other=packet_from_text('other','A different source speaks.\n')
    data=p.model_dump();data['context']=[other.spans[0].model_dump()]
    with pytest.raises(ValueError):RawPacket.model_validate(data)
