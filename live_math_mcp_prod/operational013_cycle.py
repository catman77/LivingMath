"""Isolated013 adapter for the unchanged typed011 protocol and unchanged006 T.

The adapter names its own native source. It does not register as a007 source
or grant execution. The local operator retains activation and commit authority.
"""
import copy
from itertools import combinations
import json
from normalizer import canonical,digest,read_history
from native_preview008_contract import NativeRequest
from native_preview008_engine import check_sources,frontier
from typed_cycle011 import TypedCycle,journal_state,ordinal_parameters
from typed_cycle011_store import connect,scope
from typed_cycle011_contract import denied
from operational013 import LinearTransport,TransportRefusal
from operational013_native import Port,Ledger,definition_sha256
from operational013_costs import AuditedLedger
from operational013_source import Request,bound_fit,Frame,VisibleState
from live_transfer006 import attend,interpret
from research_cycle009 import material

ADAPTER='source013-native/v1'


class ForecastPort:
    def __init__(self,frame):
        self.frame=frame;self.native=Port(frame.declaration,frame.ledger)
        self.trace=self.native.trace;self.counts=self.native.counts
        self.actions=frame.spec['parameters']['actions']
    def load(self,word):
        image=self.frame.images.get(tuple(word))
        if image is None:raise ValueError('SOURCE_IMAGE_NOT_OBSERVED')
        return VisibleState(None,list(image),tuple(word))
    def admissible(self,state,action):
        self.frame.law.step(state.value,self.actions.index(action))
        return self.native.guard_image(state.value,self.actions.index(action))
    def extend(self,state,action):
        image=self.frame.law.step(state.value,self.actions.index(action))
        return VisibleState(None,image,state.history+(action,))
    def observe(self,state,observer):
        if observer!=self.frame.law.binding['observer']:raise ValueError('OBSERVER_ALIGNMENT_REQUIRED')
        return self.native.observe_image(state.value,observer)


class ForecastFrame(Frame):
    def port(self,max_calls=2048,seconds=5):
        self.assert_bound()
        self.ledger.limit=min(self.ledger.limit,max_calls)
        return ForecastPort(self)


class OperationalCycle(TypedCycle):
    def context(self,req):
        if req.source_adapter_id!=ADAPTER:raise ValueError('UNSUPPORTED_013_ADAPTER')
        if req.question.context_level=='C4':raise ValueError('C4_IS_NOT_AUDIT_SUFFICIENT')
        if len(canonical(req.model_dump()).encode())>req.budget.input_bytes:raise ValueError('INPUT_BYTE_BOUND')
        history=read_history(self.database,req.project)
        check_sources(history,req.source_event_ids,req.source_bindings,exact=True)
        events={r['id']:r for r in history['tables']['events']}
        if set(events)!=set(req.source_event_ids):raise ValueError('INCOMPLETE_SOURCE_CLOSURE')
        current=frontier(history,req.active_frontier_id,req.active_frontier_version)
        root=json.loads(events[req.question.root_event_id]['content']);spec=copy.deepcopy(root['source_spec'])
        with connect(self.database) as c:
            registered=scope(c,req.project)
            receipts=[json.loads(r[0]) for r in c.execute('SELECT payload_json FROM typed011_receipts WHERE project=? ORDER BY id',(req.project,))]
        fixture=events[registered['fixture_id']]
        if digest(fixture)!=registered['fixture_sha256']:raise ValueError('FIXTURE_SOURCE_DRIFT')
        if (spec['version'],spec['scope'],spec['observer'])!=(req.active_frontier_version,current['scope'],req.observer.model_dump()):
            raise ValueError('SOURCE_VERSION_SCOPE_OBSERVER')
        if current['scope']!=registered['scope'] or spec['primitive_sha256']!=definition_sha256():raise ValueError('SOURCE_CODE_OR_SCOPE_DRIFT')
        if digest(ordinal_parameters(spec['parameters']))!=registered['operation_definition_sha256']:raise ValueError('OPERATIONS_DRIFT')
        if any('event:'+str(eid) not in spec['histories'] for eid in (req.question.left_history_id,req.question.right_history_id)):
            raise ValueError('FOREIGN_OR_UNDECLARED_QUESTION_HISTORY')
        if req.question.feedback_event_id is not None and req.question.feedback_event_id not in {r['event_id'] for r in receipts}:
            raise ValueError('FOREIGN_OR_UNCOMMITTED_FEEDBACK')
        fitted=bound_fit(self.database,Request(project=req.project,obligation_id=req.active_frontier_id,version=req.active_frontier_version,
            root_event_id=req.question.root_event_id,source_bindings=req.source_bindings,observer=req.observer))
        law=LinearTransport.restore(fitted['law'])
        if law.status!='CANDIDATE_TRANSPORT':raise ValueError('NO_TRANSFER_LAW')
        actions=spec['parameters']['actions'];ordinal=lambda w:[actions.index(a) for a in w]
        words={ref:json.loads(events[int(ref.split(':')[1])]['content'])['word'] for ref in spec['histories']+[spec['independent_ref']]}
        frame=ForecastFrame(spec['parameters'],events,words,req.question.root_event_id,current['scope'],req.project,AuditedLedger(req.budget.native_calls),req.active_frontier_version)
        # Replace only protocol data; the mathematics of006 is unchanged.
        frame.spec.update(spec);frame.law=law
        observations=json.loads(events[root['observations_event_id']]['content'])
        frame.images={():observations['origin']}
        for t in observations['transitions']:
            word=[actions[i] for i in t['history']]
            frame.images[tuple(word)]=t['before'];frame.images[tuple(word+[actions[t['action']]])]=t['after']
        frame._seal=digest([frame.declaration,frame.spec,frame.query,frame.words])
        port=frame.port();frame.ledger.stage='T_feedback_filter'
        # Intersect ALL committed observations; never revive a previously excluded guard.
        for h in frame.spec['hypotheses']:
            if h['question']!='current':continue
            for receipt in receipts:
                event=events.get(receipt['event_id'])
                if event is None:raise ValueError('MISSING_COMMITTED_FEEDBACK')
                measurement=json.loads(event['content'])['measurement_binding']
                with connect(self.database) as c:
                    pcrow=c.execute('SELECT payload_json FROM typed011_precommits WHERE id=?',(measurement['precommit_id'],)).fetchone()
                oldpc=json.loads(pcrow[0])
                if measurement['scope']!=current['scope'] or measurement['observer']!=spec['observer']:raise ValueError('FOREIGN_FEEDBACK')
                # Sealed environment and future heldouts are absent from this forecast.
                image=frame.images[tuple(words[h['ref']])]
                for action in oldpc['suffix_ordinals']:
                    if not port.native.guard_image(image,action):raise ValueError('FEEDBACK_GUARD')
                    image=law.step(image,action)
                readout={'defined':True,'observation':port.native.observe_image(image,spec['observer']),
                         'admissibility':[True]*len(oldpc['suffix_ordinals'])}
                if readout!=measurement['observed']:
                    h['predictive']=False;h['excluded_by']=receipt['event_id'];break
        active=[h['ref'] for h in frame.spec['hypotheses'] if h['question']=='current' and h['predictive']]
        claim=digest({'family':registered['source_family_id'],'native':definition_sha256(),'observer':spec['observer'],
                      'scope':current['scope'],'histories':sorted(ordinal(words[r]) for r in active),
                      'domain':[ordinal(t['suffix']) for t in spec['tests']]})
        frame._seal=digest([frame.declaration,frame.spec,frame.query,frame.words])
        # Private per-call context, never a caller-supplied selected test.
        spec['_frame']=frame;spec['_normalization']=fitted['normalization']
        return history,current,spec,registered,claim,ordinal

    def preview(self,request):
        try:
            req=NativeRequest.model_validate(request)
            history,current,spec,registered,claim,ordinal=self.context(req)
            frame=spec['_frame'];active=[h['ref'] for h in frame.spec['hypotheses'] if h['question']=='current' and h['predictive']]
            frame.ledger.stage='I_law_witness';witness=None
            for left,right in combinations(active,2):
                candidate=interpret(frame,left,right,max_calls=req.budget.native_calls)
                if candidate['status']=='NEW_DISTINCTION':
                    w=candidate['witness'];witness={'histories':[left,right],'suffix':w['suffix'],
                        'test_id':w['test_id'],'readouts':candidate['predictions']};break
            frame.ledger.stage='T_unchanged006';attention=attend(frame,max_calls=req.budget.native_calls)
            raw={'suffix_ordinals':ordinal(witness['suffix']),'readouts':witness['readouts']} if witness else {'witness':None}
            raw_sha=digest(raw)
            with connect(self.database) as c:
                state=journal_state(c,req.project,current['scope'],registered['source_family_id'],claim,raw_sha)
            source_hashes=frame.sources(['event:'+str(i) for i in req.source_event_ids])
            out=denied(state if witness else 'NO_INFORMATIVE_TEST','Empirical013 transport forecasts; source interpretation is not mathematical proof.',
                witness=witness,attention=attention,raw_distinction=raw,raw_distinction_sha256=raw_sha,
                source_hashes=source_hashes,claim_fingerprint=claim,source_family_id=registered['source_family_id'],
                operation_definition_sha256=registered['operation_definition_sha256'],normalization=spec['_normalization'],
                authoritative_novelty={'snapshot_complete':True,'caller_known_ignored':True},
                cost_ledger=frame.ledger.summary(),native_trace=frame.ledger.rows,
                independent_branch=[h for h in attention.get('hypotheses',[]) if h['question']=='independent'],
                I_supplies_optimal_test_id=False,source_adapter_id=ADAPTER)
            out['preview_digest']=digest({'request':req.model_dump(),'raw':raw_sha,'claim':claim,'attention':material(attention)})
            if len(canonical(out).encode())>req.budget.output_bytes:raise ValueError('OUTPUT_BYTE_BOUND')
            return out
        except (ValueError,KeyError,TypeError,TransportRefusal) as error:
            return denied('INSUFFICIENT_CONTEXT',str(error))
