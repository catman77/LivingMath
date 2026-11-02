import importlib.util
from pathlib import Path

from roblox_pred.formal_basis import graph_counts,fixed_projection,semantic_features,formal_features


def test_projection_is_fixed_dimension_and_graph_id_renaming_invariant():
    nodes=[{'id':'a','label':'collect resource','features':[]},{'id':'b','label':'buy upgrade','features':[]}]
    edges=[{'src':'a','dst':'b','kind':'TRANSITION'}]
    first=graph_counts(nodes,edges)
    renamed=[{**n,'id':n['id']+'2'} for n in nodes]
    second=graph_counts(renamed,[{'src':'a2','dst':'b2','kind':'TRANSITION'}])
    assert first==second
    vector=fixed_projection(first)
    assert len(vector)==512 and abs(sum(x*x for x in vector)-1)<1e-10


def test_missing_formal_graph_has_explicit_mask_not_fake_zero():
    values,available=formal_features([])
    assert not available and values=={'MISSING_FORMAL_MODEL':1.}
    assert any(fixed_projection(values))
    assert semantic_features([])[1] is False


def test_model_hash_and_actual_check_required():
    model={'compiled_hash':'one','observer':{'kind':'SOURCE_SEMANTICS012','states':[], 'source_annotations':[]}}
    assert not formal_features([{'model':model,'check':{'model_hash':'two','analysis':{'meta_transport_checked':True}}}])[1]
    assert not formal_features([{'model':model,'check':{'model_hash':'one','analysis':{}}}])[1]
    assert formal_features([{'model':model,'check':{'model_hash':'one','analysis':{'meta_transport_checked':True}}}])[1]


def test_source_renderer_does_not_send_targets_or_metadata():
    path=Path(__file__).parents[1]/'scripts/formal_worker.py'
    spec=importlib.util.spec_from_file_location('formal_worker_renderer_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row={'title':'Original test','model_description':'Collect food and use it to build a home.',
         'label':1,'current_players':123456,'genre':'NEVER_SEND_GENRE','split':'NEVER_SEND_SPLIT'}
    text=module.render(row)
    assert '123456' not in text and 'NEVER_SEND' not in text and 'label' not in text
    assert 'Collect food' in text


def test_raw_semantic_control_survives_formal_alignment_rejection():
    from roblox_pred.formal_basis import raw_semantic_views
    proposal={'readings':[{'id':'r1','states':[{'id':'a','label':'food'},{'id':'b','label':'upgrade'}],
        'relations':[{'id':'edge1','kind':'TRANSITION','src':'a','dst':'b'}]}]}
    records=[{'kind':'artifact_semantic_call','payload':{'role':'proposer012','result':{'status':'OK','output':proposal}}},
        {'kind':'artifact_semantic_call','payload':{'role':'critic012','result':{'status':'OK','output':{'assessments':[
            {'reading_id':'FOREIGN','relation_id':'FOREIGN','status':'HYPOTHESIS'}]}}}}]
    values,available=semantic_features(raw_semantic_views(records))
    assert available and values['count.edges']==1
    assert not formal_features([])[1]
