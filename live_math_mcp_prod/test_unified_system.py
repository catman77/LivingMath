"""Source-bound unified transport layer: no production writes or source runtime execution."""
import copy
from pathlib import Path

import pytest

from unified_system.assets import Assets,build
from unified_system.validation import check


@pytest.fixture(scope='module')
def assets(tmp_path_factory):
    target=tmp_path_factory.mktemp('unified-assets')/'data'
    build(Path(__file__).resolve().parent.parent,target)
    return Assets(target)


@pytest.mark.parametrize('source_id',['P1-001','P1-002'])
def test_original_real_SUTI_pairs_and_source_projection(assets,source_id):
    out=check(assets.bridge,source_id,None,None)
    assert all(r['valid'] for r in out['record_checks'])
    assert out['projection_collisions'] and not out['projection_collisions'][0]['source_records_equal']
    original=next(p for p in assets.bridge['pairs'] if p['id']==source_id)
    assert original['distinguished_field'] in out['projection_collisions'][0]['different_source_fields']
    assert out['source_sha256']==original['source_sha256']
    assert out['proof_status']=='unverified' and out['execution_permission']=={'allowed':False}


def test_bad_full_record_rejected_without_inventing_global_invariant(assets):
    pair=assets.bridge['pairs'][0]
    rows=copy.deepcopy(pair['records']);rows[0]['visibility']='NOT_A_SOURCE_ENUM'
    out=check(assets.bridge,pair['id'],rows,None)
    assert not out['record_checks'][0]['valid'] and out['record_checks'][1]['valid']


def test_refined_observer_preserves_source_distinction(assets):
    pair=assets.bridge['pairs'][0]
    out=check(assets.bridge,pair['id'],None,pair['observer']['fields']+[pair['distinguished_field']])
    assert not out['projection_collisions']


def test_unknown_source_or_invented_projection_field_is_rejected(assets):
    with pytest.raises(ValueError):check(assets.bridge,'unknown',None,None)
    with pytest.raises(ValueError):check(assets.bridge,'P1-001',None,['invented'])


def test_tampered_source_bytes_fail_binding(assets):
    other=copy.deepcopy(assets.bridge);pair=other['pairs'][0]
    other['schema_members'][pair['member']]['text']+=' '
    with pytest.raises(ValueError,match='HASH_DRIFT'):check(other,pair['id'],None,None)


def test_alchemical_bundle_preserves_exact_public_model(assets):
    root=Path(__file__).resolve().parent.parent
    assert (assets.root/'alch006.json').read_bytes()==(root/'alch006/final-model.json').read_bytes()
    assert len(assets.model['uncertainty'])==60 and assets.model['scope']['proof_status']=='unverified'


def test_bundle_manifest_detects_changed_asset(assets,tmp_path):
    import shutil
    p=tmp_path/'assets';shutil.copytree(assets.root,p)
    (p/'bridge.json').write_text('{}')
    with pytest.raises(ValueError,match='HASH_DRIFT'):Assets(p)
