"""Actual theta-source fixtures, not replacement Xi toy data."""
import json
from pathlib import Path
import zipfile
import pytest
from real_xi015_source import load_native,address
from real_xi015_math import discover,predict,assess,binding_fingerprint,require_binding
from real_xi015_stream import records


@pytest.fixture(scope='session')
def actual_native(tmp_path_factory):
    root=tmp_path_factory.mktemp('xi015-native')
    archive=Path(__file__).parent.parent/'docs/RH_XI_ROUTES_EXPORT_001.zip'
    from checkout_test_support import native_source
    native_source(root, archive)
    return load_native(root)


def data():return json.loads((Path(__file__).parent/'testdata/xi015_actual_anchors.json').read_text())


def test_real_source_schema_and_published_h_transfer(actual_native):
    d=data();model=discover(actual_native,list(zip(d['A'][:2],d['B'][:2])),d['nodes'])
    assert model['status']=='LAW_CANDIDATE' and not model['old013_induction']
    for a,b in zip(d['A'],d['B']):
        prediction=predict(actual_native,a,d['nodes'][str(a['source_address']['node'])],'.001')
        assert assess(prediction,b,(a,b))['PASS']
        assert address(a)==address(b)


def test_changed_true_source_binding_requires_rebind():
    identity={'source_address':data()['A'][0]['source_address'],'origin_id':0,'h':'.0005','t':'14.134725141734694',
              'observer':'complex-interval','version':1,'definition_sha256':data()['archive_sha256']}
    assert binding_fingerprint(identity)==binding_fingerprint({**identity,'display_label':'new name'})
    for key,value in [('origin_id',1),('h','.002'),('t','15'),('observer','scalar'),('version',2),('definition_sha256','0'*64)]:
        with pytest.raises(ValueError,match='REBIND'):require_binding({**identity,key:value},identity)


def test_interval_failure_is_not_silently_accepted():
    a,b=data()['A'][0],data()['B'][0]
    wrong={'re':['0','0'],'im':['0','0']}
    assert not assess(wrong,b,(a,b))['PASS']


def test_streaming_parser_handles_arrays_larger_than_chunk(tmp_path):
    row=data()['A'][0];many=[{**row,'index':i} for i in range(400)]
    p=tmp_path/'large.json';p.write_text(json.dumps({'source_nodes':[],'origins':[],'cases':[{'id':'actual-fixture-parser-control','edges':many}]}))
    decoded=[v for kind,k,v in records(p) if kind=='edge']
    assert decoded==many


def test_typed_observer_preserves_actual_complex_evidence(actual_native):
    from real_xi015_typed import evaluate_observer,sha,SOURCE
    d=data();predictions=[]
    for a in d['A']:
        predictions.append({'index':a['index'],'binding':{'h':'.001','source_address':a['source_address'],'origin_id':a['origin_id']},
            'C_source_candidate':predict(actual_native,a,d['nodes'][str(a['source_address']['node'])],'.001')})
    q={'h':'.001','predictions':predictions,'anchors':{str(a['index']):[a,b] for a,b in zip(d['A'],d['B'])},
       'observer_code_sha256':sha(SOURCE/'real_xi015_math.py')}
    assert evaluate_observer(q,d['B'])[0]==0
    with pytest.raises(ValueError,match='ORDER'):evaluate_observer(q,list(reversed(d['B'])))
    q['predictions'][0]['C_source_candidate']={'re':['0','0'],'im':['0','0']}
    assert evaluate_observer(q,d['B'])[0]==1
