"""014 purpose/guard/feedback tests; old006/013 mathematics is not replaced."""
import pytest
from operational013 import LinearTransport
from law_validation014 import select_validation,dispatch
from law_validation014_native import Port


def fixture():
    d={'algebra':'affine','initial':[1,0],'arity':2,'guard_width':4,'clock_period':0}
    p=Port(d);trans=[]
    for h in ([],[0],[1],[0,0],[0,1],[1,0],[1,1]):
        s=p.load(h)
        for a in (0,1):trans.append({'before':p.inspect(s),'after':p.inspect(p.extend(s,a)),'action':a,'history':h})
    law=LinearTransport.fit([1,0],trans,{'observer':{'projection':'primary','mod':None}})
    return law,Port(d),[{'id':'q0','word':[0,1,0,1],'cost':4,'ordinal':0},{'id':'q1','word':[1,0,1,0],'cost':4,'ordinal':1}]


def test_singleton_routes_to_real_untested_law_probe():
    law,p,domain=fixture()
    singleton={'status':'NO_INFORMATIVE_TEST','hypotheses':[{'id':'h','question':'current','predictive':True,'status':'ACTIVE'}]}
    out=dispatch(singleton,law,p,[1,0],[],domain,[])
    assert out['purpose']=='VALIDATE_TRANSFER' and out['selected']['id']=='q0'
    assert out['new_distinction_claimed'] is False
    assert all(r['operation']!='E' for r in p.ledger.rows)


def test_exhaustion_is_not_an_invented_alternative():
    law,p,domain=fixture();seen=[t['word'] for t in domain]
    out=select_validation(law,p,[1,0],[],domain,seen)
    assert out['status']=='NO_UNTESTED_GUARDED_PROBE'
    assert not out['execution_permission']['allowed']


def test_counterexample_blocks_validation_without_synthetic_guard_repair():
    law,p,domain=fixture()
    out=select_validation(law,p,[1,0],[],domain,[],review_required=True)
    assert out['status']=='REQUIRES_REVIEW' and p.ledger.rows==[]


def test_partial_guard_refuses_even_native_admissible_path():
    law,p,domain=fixture();p.declaration['guard_width']=1
    assert select_validation(law,p,[1,0],[],domain,[])['status']=='GUARD_INSUFFICIENT'


def test_no_posterior_cannot_be_relabelled_singleton():
    law,p,domain=fixture()
    assert dispatch({'status':'NO_INFORMATIVE_TEST','hypotheses':[]},law,p,[1,0],[],domain,[])['status']=='UNKNOWN_BOUNDED'


def test_actual011_contract_remains_strict():
    from typed_cycle011_contract import MeasurementEnvelope
    from law_validation014_contract import Envelope014
    assert MeasurementEnvelope.model_fields['predictions'].metadata[0].min_length==2
    assert Envelope014.model_fields['predictions'].metadata[0].min_length==1


def test_four_step_readout_extension_does_not_relax_legacy():
    from pydantic import ValidationError
    from research_engine010_contract import Readout
    from law_validation014_contract import Readout014
    data={'defined':True,'observation':2,'admissibility':[True]*4}
    assert Readout014.model_validate(data).model_dump()==data
    with pytest.raises(ValidationError):Readout.model_validate(data)
