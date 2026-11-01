"""Family-independent source-law constructor; frozen006.2 supplies fallback and T."""
import copy
import time

from normalizer import digest
from live_transfer006 import interpret as bounded,endpoint,metadata,result
from live_transfer006_primitives import Exhausted
from live_transfer006_source import BindingError
from live_constructive007_laws import verify

VERSION='007.2'


def identity(frame,left,right):
    alphabet=frame.spec['parameters']['actions'];word=lambda w:[alphabet.index(a) for a in w]
    p=copy.deepcopy(frame.spec['parameters']);p['actions']=list(range(len(alphabet)))
    return digest({'project':frame.query['project'],'scope':frame.query['scope'],'version':frame.query['version'],
        'primitive_definition':frame.spec['primitive_sha256'],'observer':frame.spec['observer'],'parameters':p,
        'words':sorted([word(frame.words[left]),word(frame.words[right])]),'domain':[word(t['suffix']) for t in frame.spec['tests']]})


def interpret_constructive(frame,left,right,certificate_ref=None,known=(),max_calls=2048):
    start=time.perf_counter();port=frame.port(max_calls);ledger=port.ledger;refs=[r for r in (left,right) if r in frame.spec['histories']]
    receipt={'status':'NOT_CHECKED'};candidate=None
    def finish(out,strategy):
        out.update(constructor_version=VERSION,strategy=strategy,law=receipt,candidate=candidate,cost_ledger=ledger.summary())
        return out
    def fallback(reason):
        ledger.stage='fallback_B1';out=bounded(frame,left,right,known=known,max_calls=max_calls)
        out['fallback_reason']=reason
        return finish(out,'FALLBACK_BOUNDED')
    try:
        frame.assert_bound()
        if len(refs)!=2:raise BindingError('HISTORY_BINDING')
        law_start=time.perf_counter();law,receipt=verify(frame,certificate_ref,ledger)
        receipt['validation_wall_seconds']=time.perf_counter()-law_start
        if law is None:return fallback(receipt['reason'])
        ledger.stage='source_preparation'
        a=port.load(frame.words[left]);b=port.load(frame.words[right])
        observations=[port.observe(a,frame.spec['observer']),port.observe(b,frame.spec['observer'])]
        fp=identity(frame,left,right)
        if observations[0]!=observations[1]:
            return finish(result('NO_NEW_DISTINCTION',reason='ALREADY_OBSERVED',**metadata(frame,refs,port,start)),'CERTIFIED_CONTEXT')
        if fp in known:return finish(result('NO_NEW_DISTINCTION',reason='SEEN_STRUCTURAL_DISTINCTION',fingerprint=fp,**metadata(frame,refs,port,start)),'CERTIFIED_CONTEXT')
        ledger.stage='coordinate_construction';fa=law.features(a,ledger);fb=law.features(b,ledger)
        coordinate=next((i for i in range(law.width) if i in law.coordinate_actions and fa[i]!=fb[i]),None)
        if coordinate is None:return fallback('NO_COVERED_DIFFERING_COORDINATE')
        ordinal=law.coordinate_actions[coordinate];action=frame.spec['parameters']['actions'][ordinal]
        # Index construction checks membership only; no predictions or suffix search.
        ledger.charge('registered_domain_membership_entries',len(frame.spec['tests']))
        domain={tuple(t['suffix']):t for t in frame.spec['tests']}
        test=domain.get((action,))
        if test is None:return fallback('CONSTRUCTED_PRIMITIVE_OUTSIDE_D')
        candidate={'coordinate':coordinate,'operation_ordinal':ordinal,'test_id':test['id'],'suffix':[action],
                   'basis':'Equal current observations and a differing source-certified injectively observed feature.'}
        ledger.stage='mandatory_native_validation'
        one=endpoint(port,{():{'state':a,'admissibility':[]}},[action],frame.spec['observer'])
        two=endpoint(port,{():{'state':b,'admissibility':[]}},[action],frame.spec['observer'])
        if one==two:return fallback('LAW_NATIVE_READOUT_MISMATCH')
        out=result('NEW_DISTINCTION',fingerprint=fp,
            novelty_basis={'current_observations':observations,'same_current_observation':True,'prior_distinctions':list(known),
                           'source_identity_implies_equivalence':False,'law_feature_coordinate':coordinate},
            witness={'test_id':test['id'],'suffix':[action]},predictions=[one,two],admissibility_trace=[one['admissibility'],two['admissibility']],
            guard={'histories':[left,right],'scope':frame.query['scope'],'version':frame.query['version'],
                   'observer':frame.spec['observer'],'law_source':certificate_ref,'substitution_allowed':False},
            **metadata(frame,refs+[certificate_ref],port,start))
        return finish(out,'CONSTRUCTIVE_VALIDATED')
    except Exhausted as error:
        return finish(result('UNKNOWN_BOUNDED',reason=str(error),asserts_equivalence=False,**metadata(frame,refs,port,start)),'BUDGET_REFUSAL')
    except (BindingError,ValueError,KeyError,TypeError) as error:
        return finish(result('FAIL_CLOSED',reason=str(error),**metadata(frame,refs,port,start)),'SOURCE_REFUSAL')
