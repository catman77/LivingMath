"""Release approval and actual worker timeout boundaries, no production mutation."""
import asyncio
import hashlib
import json

import pytest

from unified_deploy import load
from unified_system import VERSION


def test_exact_package_approval_is_independent_of_old_deployment_authorization(tmp_path):
    base=tmp_path/'base.py';base.write_text('public immutable base')
    authorization=tmp_path/'base-authorization.json';authorization.write_text('{}')
    layer=tmp_path/'layer';layer.mkdir();(layer/'manifest.json').write_text('{}')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    cfg={'version':VERSION,'authorization':'Publish SUTI-Bridge-LivingMath MCP for direct ChatGPT testing',
        'base_entry':str(base),'base_entry_sha256':sha(base),'base_authorization':str(authorization),
        'base_authorization_sha256':sha(authorization),'layer':str(layer),'layer_manifest_sha256':sha(layer/'manifest.json'),
        'mode':'production','artifact_package_sha256':'a'*64,'artifact_schema_sha256':'b'*64,'deployment_id':'exact-instance'}
    file=tmp_path/'config.json';file.write_text(json.dumps(cfg));file.chmod(0o600)
    with pytest.raises(ValueError,match='OWNER_APPROVAL'):load(file)
    approval=tmp_path/'approval.json';approval.write_text('{}');approval.chmod(0o600)
    cfg['artifact_owner_approval']=str(approval);file.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='FINGERPRINT'):load(file)
    approved={'version':VERSION,'package_sha256':cfg['artifact_package_sha256'],
        'layer_manifest_sha256':cfg['layer_manifest_sha256'],'schema_sha256':cfg['artifact_schema_sha256'],
        'instance_id':cfg['deployment_id'],'action':'APPROVE_EXACT_ARTIFACT_PROFILE_PROMOTION'}
    approval.write_text(json.dumps(approved));assert load(file)['_layer']==layer
    for field in ['package_sha256','layer_manifest_sha256','schema_sha256','instance_id']:
        wrong={**approved,field:'different'};approval.write_text(json.dumps(wrong))
        with pytest.raises(ValueError,match='FINGERPRINT'):load(file)


def test_actual_inherited_six_second_subprocess_deadline(tmp_path,monkeypatch):
    from semantic_repair import worker
    script=tmp_path/'private_timeout_probe.py';script.write_text('import time\ntime.sleep(30)\n')
    # Local-only fault harness. No public request accepts a worker path.
    monkeypatch.setattr(worker,'__file__',str(script))
    with pytest.raises(TimeoutError):asyncio.run(worker.call('observe',{}))
