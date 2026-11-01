"""Source-bound014 dispatcher and precommit. No oracle, environment or operator import."""
import copy
import json
import itertools
import os
from normalizer import canonical,digest,read_history,normalize_context,reconstruct_context
from native_preview008_engine import check_sources,frontier
from research_store import ResearchStore
from frontier import ResearchMoveFingerprint
from typed_cycle011 import ordinal_parameters,journal_state
from typed_cycle011_store import assert_isolated,connect,scope
from typed_cycle011_contract import denied
from research_cycle009 import operation,selected_claim
from operational013 import LinearTransport
from operational013_native import Ledger
from operational013_source import Frame,VisibleState
from live_transfer006 import attend,endpoint,initial_cache
from law_validation014 import dispatch,forecast
from law_validation014_native import Port,native_sha
from law_validation014_contract import Request014,Precommit014,ADAPTER
from law_validation014_receipt import ReceiptValidator014

_LEDGERS=itertools.count()


class MeteredLedger(Ledger):
    def __init__(self,limit=2048):
        super().__init__(limit);self.identity=next(_LEDGERS)
    def charge(self,operation,**fields):
        super().charge(operation,**fields)
        destination=os.environ.get('LM014_NATIVE_LEDGER')
        if destination:
            with open(destination,'a') as stream:stream.write(canonical({'ledger':self.identity,**self.rows[-1]})+'\n')


class ForecastPort:
    def __init__(self,frame):
        self.frame=frame;self.native=Port(frame.declaration,frame.ledger)
        self.trace=self.native.trace;self.counts=self.native.counts
        self.actions=frame.spec['parameters']['actions']
    def load(self,word):
        image=self.frame.images.get(tuple(word))
        if image is None:raise ValueError('UNOBSERVED_CONTEXT')
        return VisibleState(None,list(image),tuple(word))
    def admissible(self,state,action):return self.native.guard_image(state.value,self.actions.index(action))
    def extend(self,state,action):
        value=self.frame.law.step(state.value,self.actions.index(action))
        return VisibleState(None,value,state.history+(action,))
    def observe(self,state,observer):return self.native.observe_image(state.value,observer)


class ForecastFrame(Frame):
    def port(self,max_calls=2048,seconds=5):
        self.assert_bound();self.ledger.limit=min(self.ledger.limit,max_calls);return ForecastPort(self)


class LawCycle014(ReceiptValidator014):
    def source_preview(self,request):
        try:
            req=Request014.model_validate(request)
            _,_,_,spec,_,frame,law,law_fp,_,_,_=self.context(req)
            frame.ledger.stage='source_law_preview'
            probes=[]
            if law.status=='CANDIDATE_TRANSPORT':
                port=Port(frame.declaration,frame.ledger)
                origin=law.embedding.decode([1]+[0]*9)
                probes=[{'id':p['id'],'word':p['word'],'prediction':forecast(law,port,origin,p['word'])} for p in spec['validation_domain']]
            return denied(law.status,'Source-bound013 induction;014 adds attention only.',law=law.artifact(),law_fingerprint=law_fp,
                          probes=probes,costs=frame.ledger.summary(),native_trace=frame.ledger.rows)
        except (ValueError,KeyError,TypeError) as error:return denied('INSUFFICIENT_CONTEXT',str(error))

    def context(self,req):
        if req.source_adapter_id!=ADAPTER:raise ValueError('UNSUPPORTED_ADAPTER')
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
        if (current['scope'],req.active_frontier_version,req.observer.model_dump())!=(spec['scope'],spec['version'],spec['observer']):raise ValueError('SCOPE_VERSION_OBSERVER')
        if digest(events[registered['fixture_id']])!=registered['fixture_sha256']:raise ValueError('FIXTURE_IDENTITY_DRIFT')
        if spec['primitive_sha256']!=native_sha() or registered['native_definition_sha256']!=native_sha():raise ValueError('NATIVE_CODE_DRIFT')
        if digest(ordinal_parameters(spec['parameters']))!=registered['operation_definition_sha256']:raise ValueError('OPERATION_DEFINITION_DRIFT')
        if any('event:'+str(eid) not in spec['histories'] for eid in (req.question.left_history_id,req.question.right_history_id)):raise ValueError('FOREIGN_QUESTION_HISTORY')
        if req.question.feedback_event_id is not None and req.question.feedback_event_id not in {r['event_id'] for r in receipts}:raise ValueError('UNCOMMITTED_OR_FOREIGN_FEEDBACK')
        candidate={'id':'law014','project':req.project,'root_ref':'event:'+str(req.question.root_event_id),'scope':current['scope'],'version':spec['version']}
        view=normalize_context(history,'bounded source law validation',[candidate],'C2')
        if view['status']!='COMPLETE' or not view.get('audit_context'):raise ValueError('NORMALIZATION_INCOMPLETE')
        recovered=reconstruct_context(view,history)
        if {r['id']:r for r in recovered['tables']['events']}!=events:raise ValueError('SOURCE_RECOVERY_DRIFT')
        observed=json.loads(events[root['observations_event_id']]['content'])
        binding={'source_event_id':root['source_event_id'],'scope':current['scope'],'version':spec['version'],'observer':spec['observer'],'native_sha256':native_sha()}
        law=LinearTransport.fit(observed['origin'],observed['transitions'],binding)
        law_fp=digest({'origin':law.embedding.origin,'actions':law.artifact()['actions'],'native':native_sha(),'operation':registered['operation_definition_sha256']})
        words={r:json.loads(events[int(r.split(':')[1])]['content'])['word'] for r in spec['histories']+[spec['independent_ref']]}
        frame=ForecastFrame(spec['parameters'],events,words,req.question.root_event_id,current['scope'],req.project,MeteredLedger(req.budget.native_calls),spec['version'])
        frame.spec.update(spec);frame.law=law;frame.images={():observed['origin']}
        actions=spec['parameters']['actions'];ordinal=lambda w:[actions.index(a) for a in w]
        for t in observed['transitions']:
            w=[actions[i] for i in t['history']];frame.images[tuple(w)]=t['before'];frame.images[tuple(w+[actions[t['action']]])]=t['after']
        frame._seal=digest([frame.declaration,frame.spec,frame.query,frame.words])
        frame.ledger.stage='feedback';port=frame.port();review=False
        executed=copy.deepcopy(observed['executed_words']);covered=[]
        for receipt in receipts:
            event=events[receipt['event_id']];env=json.loads(event['content'])['measurement_binding']
            if env['schema_version']!='bound-measurement014/v1' or env['law_fingerprint']!=law_fp:raise ValueError('FEEDBACK_LAW_OR_SCHEMA')
            if env['purpose']=='VALIDATE_TRANSFER':
                executed.append(env['context_word']+env['suffix_ordinals']);covered.extend(zip(env['suffix_ordinals'],env['suffix_ordinals'][1:]))
                if env['outcome']=='FAILURE':review=True
                continue
            any_match=False
            for h in frame.spec['hypotheses']:
                if h['question']!='current' or not h['predictive']:continue
                predicted=endpoint(port,initial_cache(port,words[h['ref']]),[actions[i] for i in env['suffix_ordinals']],spec['observer'])
                if predicted!=env['observed']:h['predictive']=False;h['excluded_by']=receipt['event_id']
                else:any_match=True
            if not any_match:review=True
        frame._seal=digest([frame.declaration,frame.spec,frame.query,frame.words])
        return req,history,current,spec,registered,frame,law,law_fp,executed,covered,review

    def preview(self,request):
        try:
            req=Request014.model_validate(request)
            req,history,current,spec,registered,frame,law,law_fp,executed,covered,review=self.context(req)
            if law.status!='CANDIDATE_TRANSPORT':return denied(law.status,'No transferable coordinate law.',counterexample=law.counterexample)
            frame.ledger.stage='DISCRIMINATE_T006';discrimination=attend(frame,max_calls=req.budget.native_calls)
            active=[h for h in discrimination.get('hypotheses',[]) if h['question']=='current' and h['predictive'] and h['status']=='ACTIVE']
            context_word=[];image=law.embedding.decode([1]+[0]*9)
            if len(active)==1:
                context_word=[spec['parameters']['actions'].index(a) for a in frame.words[active[0]['ref']]]
                image=frame.images[tuple(frame.words[active[0]['ref']])]
            frame.ledger.stage='VALIDATE_TRANSFER_selector'
            attention=dispatch(discrimination,law,Port(frame.declaration,frame.ledger),image,context_word,
                spec['validation_domain'],executed,covered,review)
            if attention['status']!='ATTENTION_PROPOSED':
                return denied(attention['status'],'Finite source law attention; no automatic activation.',attention=attention,
                    discrimination=discrimination,independent_branch=[h for h in discrimination.get('hypotheses',[]) if h['question']=='independent'],
                    counterexample_policy='No narrowing without source premises; failed law requires review.',costs=frame.ledger.summary())
            purpose=attention['purpose']
            if purpose=='DISCRIMINATE':
                test,chosen=selected_claim(discrimination);suffix=test['suffix'];alternatives=test['counterfactuals'];coordinate=None
                context_word=[spec['parameters']['actions'].index(a) for a in frame.words[chosen['source_ref']]]
                expected=chosen['readout'];tested=chosen['hypothesis'];test_id=test['test_id']
            else:
                selected=attention['selected'];suffix=[spec['parameters']['actions'][a] for a in selected['word']]
                expected=selected['prediction']['readout'];coordinate=selected['prediction']['coordinate'];tested=active[0]['id'];test_id=selected['id']
                alternatives=[{'kind':'LAW_TRANSFER_PREDICTION','source_ref':active[0]['ref'],'readout':expected,'coordinate':coordinate}]
            raw={'purpose':purpose,'context_word':context_word,'suffix_ordinals':[spec['parameters']['actions'].index(a) for a in suffix],
                 'expected':expected,'coordinate':coordinate,'law':law_fp}
            claim=digest({'family':registered['source_family_id'],'scope':current['scope'],**raw})
            with connect(self.database) as c:
                novelty=journal_state(c,req.project,current['scope'],registered['source_family_id'],claim,digest(raw))
            if novelty=='REQUIRES_REVIEW':return denied(novelty,'Novelty journal conflict.')
            out=denied('PROPOSAL_READY','DISCRIMINATE differs from VALIDATE_TRANSFER; neither proves the law.',purpose=purpose,
                discrimination=discrimination,attention=attention,selected_test={'test_id':test_id,'suffix':suffix},
                alternatives=alternatives,tested_hypothesis=tested,expected_readout=expected,expected_coordinate=coordinate,
                context_word=context_word,law_fingerprint=law_fp,claim_fingerprint=claim,raw_distinction=raw,
                raw_distinction_sha256=digest(raw),novelty=novelty,source_family_id=registered['source_family_id'],
                costs=frame.ledger.summary(),native_trace=frame.ledger.rows,
                normalization={'version':'004.1','source_recovery':'EXACT'},
                independent_branch=[h for h in discrimination.get('hypotheses',[]) if h['question']=='independent'])
            out['preview_digest']=digest({k:out[k] for k in ('purpose','selected_test','alternatives','context_word','law_fingerprint','claim_fingerprint')})
            return out
        except (ValueError,KeyError,TypeError) as error:return denied('INSUFFICIENT_CONTEXT',str(error))

    def precommit(self,request,request_key):
        assert_isolated(self.database);req=Request014.model_validate(request);args=req.model_dump();args['question']['known_fingerprints']=[]
        if not isinstance(request_key,str) or not request_key.strip() or len(request_key)>128:raise ValueError('INVALID_REQUEST_KEY')
        request_sha=digest(args)
        with connect(self.database) as c:
            prior=c.execute('SELECT * FROM typed011_precommits WHERE project=? AND (request_key=? OR request_sha=?)',(req.project,request_key,request_sha)).fetchone()
            if prior:
                if prior['request_sha']!=request_sha:raise ValueError('PRECOMMIT_KEY_CONFLICT')
                return self._link(dict(prior))
        out=self.preview(args)
        if out['status']!='PROPOSAL_READY' or out['novelty']!='NEW_DISTINCTION':raise ValueError('NO_NEW_ALLOWED_PROPOSAL:'+out['status'])
        _,_,current,spec,registered,_,_,_,_,_,_=self.context(req)
        test=out['selected_test'];op=operation({'fixture_sha256':registered['fixture_content_sha256']},test['test_id'],out['expected_readout'],'014 '+out['purpose'])
        op['premises']+=['Exact014 request '+request_sha,'Law fingerprint '+out['law_fingerprint'],'Purpose '+out['purpose']]
        pc=Precommit014(project=req.project,obligation_id=req.active_frontier_id,obligation_version=req.active_frontier_version,scope=current['scope'],
            native_request=Request014.model_validate(args),source_bindings=req.source_bindings,source_family_id=registered['source_family_id'],
            native_definition_sha256=native_sha(),operation_definition_sha256=registered['operation_definition_sha256'],observer=req.observer,
            test_id=test['test_id'],suffix=test['suffix'],suffix_ordinals=[spec['parameters']['actions'].index(a) for a in test['suffix']],
            admissibility_guard=[True]*len(test['suffix']),alternatives=out['alternatives'],tested_hypothesis=out['tested_hypothesis'],
            expected_readout=out['expected_readout'],proposal_fingerprint=ResearchMoveFingerprint.build(op).digest,
            claim_fingerprint=out['claim_fingerprint'],raw_distinction_sha256=out['raw_distinction_sha256'],preview_digest=out['preview_digest'],
            purpose=out['purpose'],law_fingerprint=out['law_fingerprint'],context_word=out['context_word'],expected_coordinate=out['expected_coordinate']).model_dump()
        store=ResearchStore(self.database)
        with connect(self.database,True) as c:
            self._sources_current(c,pc)
            cur=c.execute('INSERT INTO typed011_precommits(project,request_key,request_sha,digest,payload_json,operation_json,preview_json) VALUES (?,?,?,?,?,?,?)',
                (req.project,request_key,request_sha,digest(pc),canonical(pc),canonical(op),canonical(out)))
            row=dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?',(cur.lastrowid,)).fetchone())
            store._audit(c,'typed011_precommitted',{'precommit_id':row['id'],'digest':row['digest']})
        return self._link(row)
