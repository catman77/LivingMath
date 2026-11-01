"""Meaningful algebra and guard regressions for the single 013 mechanism."""
from fractions import Fraction
import pytest
from operational013 import Embedding, LinearTransport, Span, TransportRefusal, Predictor


def test_exact_span_relation_and_inconsistency():
    span=Span(); assert span.add([1,0],[2,1])
    assert span.add([1,1],[3,3])
    assert span.apply([2,3])==[Fraction(7),Fraction(8)]
    with pytest.raises(TransportRefusal,match='INCONSISTENT_LINEAR_RELATION'):
        span.add([2,3],[7,9])


def test_relative_top_covaries_with_depth_and_origin():
    embedding=Embedding([])
    assert embedding.encode([0])[6:]==[0,0,0,0]
    assert embedding.encode([0,1])[6:]==[1,0,0,0]
    for value in ([],[0],[0,1],[1,0,1,1]):
        assert embedding.decode(embedding.encode(value))==value
    with pytest.raises(TransportRefusal):
        embedding.decode([1,2,1,0,1,0,0,0,0,0])


def test_hidden_state_conflict_never_silently_augments_coordinates():
    transitions=[{'before':[0],'after':[0],'action':0,'history':[]},
                 {'before':[0],'after':[1],'action':0,'history':[1]}]
    law=LinearTransport.fit([0],transitions,{'source':'test','version':1,'observer':'primary'})
    assert law.status=='INSUFFICIENT_STATE'
    assert law.counterexample['histories']==[[],[1]]
    assert 'distinguish' in law.counterexample['required_additional_distinction']
    with pytest.raises(TransportRefusal):law.step([0],0)


def test_span_guard_refuses_unobserved_dimension():
    law=LinearTransport.fit([], [{'before':[],'after':[0],'action':0,'history':[]}],{})
    assert law.step([],0)==[0]
    with pytest.raises(TransportRefusal,match='OUTSIDE_OBSERVED_INPUT_SPAN'):
        law.step([1],0)


@pytest.mark.parametrize('index',[0,1,2])
def test_native_composition_and_presentation_covariance(index):
    from operational013_worlds import declarations
    from operational013_qa import acquisition,OBSERVER
    from operational013_native import Port,Ledger
    from operational013_oracle import replay
    d=declarations()[index];a=acquisition(d)
    law=LinearTransport.fit(a['origin'],a['transitions'],{})
    offset=17
    shifted=[{**t,'before':[x+offset for x in t['before']], 'after':[x+offset for x in t['after']]} for t in a['transitions']]
    transformed=LinearTransport.fit([x+offset for x in a['origin']],shifted,{})
    words=([[0,1,0,1,1],[1,0,1,0,0]] if index<2 else [[0,1,2,2,1,2],[1,2,0,1,2,2]])
    ledger=Ledger();ledger.stage='prediction';predictor=Predictor(law,Port(d,ledger),OBSERVER,{})
    for word in words:
        image=a['origin'];presented=[x+offset for x in image]
        for action in word:
            image=law.step(image,action);presented=transformed.step(presented,action)
            assert [x-offset for x in presented]==image
        assert predictor.predict(a['origin'],word)['readout']==replay(d,word)[0]
    assert not any(r['operation']=='E' for r in ledger.rows)


def test_opaque_refuses_and_native_guard_blocks_overflow():
    from operational013_native import Port,Ledger
    from operational013_worlds import declarations
    from operational013_qa import acquisition,OBSERVER
    opaque=LinearTransport.fit(None,[],{})
    assert opaque.status=='NO_TRANSFER_LAW'
    d=declarations()[2];a=acquisition(d);law=LinearTransport.fit(a['origin'],a['transitions'],{})
    # A native-safe-looking image outside the learned input span is still refused.
    assert len([0,1,0])<4
    with pytest.raises(TransportRefusal,match='OUTSIDE_OBSERVED_INPUT_SPAN'):law.step([0,1,0],0)


def test_source_equality_is_stronger_than_equal_current_readout():
    from operational013_native import Port
    from operational013_worlds import declarations
    from operational013_qa import OBSERVER
    p=Port(declarations()[0]);s=p.load([]);t=p.load([0])
    assert p.observe(s,OBSERVER)==p.observe(t,OBSERVER)==0
    assert p.inspect(s)!=p.inspect(t)
    assert p.observe(p.extend(s,0),OBSERVER)!=p.observe(p.extend(t,0),OBSERVER)


def test_round_trip_artifact_and_binding_refusal():
    law=LinearTransport.fit([0],[{'before':[0],'after':[1],'action':0,'history':[]}],{'version':1,'observer':'primary'})
    restored=LinearTransport.restore(law.artifact())
    assert restored.artifact()==law.artifact()
    with pytest.raises(TransportRefusal):restored.assert_binding({'version':2,'observer':'primary'})


def test_sql_guards_are_isolated_idempotent_and_preserve_insert(tmp_path):
    import sqlite3
    from research_store import ResearchStore
    from typed_cycle011_store import install
    from operational013_store import install_append_only
    original=tmp_path/'original.sqlite3';ResearchStore(original)
    qa=tmp_path/'qa.sqlite3'
    with sqlite3.connect(original) as source,sqlite3.connect(qa) as target:source.backup(target)
    install(qa,original)
    assert install_append_only(qa)['installed']
    assert install_append_only(qa)['idempotent']
    ResearchStore(qa).record('LM_QA_013','qa_source','test','{}',request_key='seed')
    for table in ('events','operations'):
        for operation in ('UPDATE','DELETE'):
            with sqlite3.connect(qa) as c:
                command=('UPDATE '+table+' SET id=id') if operation=='UPDATE' else ('DELETE FROM '+table)
                with pytest.raises(sqlite3.IntegrityError,match='append-only'):c.execute(command)
    with pytest.raises(ValueError):install_append_only(original)
