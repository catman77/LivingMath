"""004-bound observed source transitions and compatibility frame for unchanged I/T."""
from dataclasses import dataclass
import json
import time
from normalizer import canonical,digest,read_history,normalize_context,reconstruct_context
from native_preview008_contract import DataModel,SourceBinding,Project,EventID,Observer
from native_preview008_engine import check_sources,frontier
from operational013 import LinearTransport
from operational013_native import Port,Ledger,definition_sha256


class Request(DataModel):
    project:Project
    obligation_id:EventID
    version:EventID
    root_event_id:EventID
    source_bindings:list[SourceBinding]
    observer:Observer


def bound_fit(database,request):
    wall,cpu=time.perf_counter_ns(),time.process_time_ns()
    history=read_history(database,request.project)
    check_sources(history,[b.event_id for b in request.source_bindings],request.source_bindings,exact=True)
    events={e['id']:e for e in history['tables']['events']}
    if set(events)!={b.event_id for b in request.source_bindings}:raise ValueError('INCOMPLETE_SOURCE_CLOSURE')
    current=frontier(history,request.obligation_id,request.version)
    source=json.loads(events[request.root_event_id]['content'])
    if source['native_definition_sha256']!=definition_sha256():raise ValueError('SOURCE_CODE_DRIFT')
    if source['scope']!=current['scope'] or source['version']!=request.version:raise ValueError('SOURCE_SCOPE_VERSION')
    if source['observer']!=request.observer.model_dump():raise ValueError('OBSERVER_ALIGNMENT_REQUIRED')
    candidate={'id':'law013','project':request.project,'root_ref':'event:'+str(request.root_event_id),
               'scope':current['scope'],'version':request.version}
    view=normalize_context(history,'guarded operational transport',[candidate],'C2')
    if view['status']!='COMPLETE' or not view.get('audit_context'):raise ValueError('NORMALIZATION_INCOMPLETE')
    recovered=reconstruct_context(view,history)
    if {e['id']:e for e in recovered['tables']['events']}!=events:raise ValueError('SOURCE_RECOVERY_DRIFT')
    observations=json.loads(events[source['observations_event_id']]['content'])
    # The induction function sees no family parameters, filenames or heldout commitment.
    binding={'source_event_id':source['fixture_event_id'],'native_sha256':definition_sha256(),
             'scope':current['scope'],'version':request.version,'observer':request.observer.model_dump()}
    normalized={'wall_ns':time.perf_counter_ns()-wall,'CPU_ns':time.process_time_ns()-cpu}
    wall,cpu=time.perf_counter_ns(),time.process_time_ns()
    law=LinearTransport.fit(observations['origin'],observations['transitions'],binding)
    return {'law':law.artifact(),'normalization':{'version':'004.1','view_sha256':digest(view),'recovery':'EXACT'},
            'timings':{'normalization':normalized,'law_fit':{'wall_ns':time.perf_counter_ns()-wall,'CPU_ns':time.process_time_ns()-cpu}},
            'constructor_inputs':['origin','observed transitions','source/scope/version/observer binding'],
            'execution_permission':{'allowed':False},'proof_status':'unverified'}


@dataclass
class VisibleState:
    native:object
    value:object
    history:tuple


class VisiblePort:
    def __init__(self,native):
        self.native=native;self.trace=native.trace;self.counts=native.counts;self.ledger=native.ledger
    def _wrap(self,state):return VisibleState(state,self.native.inspect(state),state.history)
    def load(self,word):return self._wrap(self.native.load(word))
    def extend(self,state,action):return self._wrap(self.native.extend(state.native,action))
    def observe(self,state,observer):return self.native.observe(state.native,observer)
    def admissible(self,state,action):return self.native.admissible(state.native,action)


class Frame:
    """Protocol adapter only; original006/012 mathematics is called unchanged."""
    def __init__(self,declaration,events,words,root_id,scope,project,ledger=None,version=1):
        self.declaration=declaration;self.events=events;self.words=words;self.ledger=ledger or Ledger()
        self.ledger.trace=self.ledger.rows  # Existing012 protocol name; no source or cost change.
        refs=list(words);ind=refs[-1];refs=refs[:-1]
        from itertools import product
        tests=[{'id':'t'+str(i),'ordinal':i,'suffix':list(w),'cost':len(w)-1}
               for i,w in enumerate([w for n in (1,2) for w in product(range(declaration['arity']),repeat=n)])]
        observer={'projection':'primary','mod':None}
        self.query={'project':project,'scope':scope,'version':version,'root_ref':'event:'+str(root_id)}
        self.spec={'histories':refs,'independent_ref':ind,'tests':tests,'observer':observer,
            'parameters':{**declaration,'actions':list(range(declaration['arity']))},'primitive_sha256':definition_sha256(),
            'instance_ref':'event:'+str(root_id),'known_failures':[],'unknowns':['No universal equivalence.'],
            'current_observation':0,'hypotheses':[{'id':ref,'ref':ref,'weight':1,'predictive':True,'question':'current','depends_on':[]} for ref in refs]+
              [{'id':'IND','ref':ind,'weight':1,'predictive':False,'question':'independent','depends_on':[]}]}
        self._seal=digest([self.declaration,self.spec,self.query,self.words])
    def assert_bound(self):
        if self._seal!=digest([self.declaration,self.spec,self.query,self.words]):raise ValueError('MUTATED_SOURCE_FRAME')
    def port(self,max_calls=20000,seconds=5):
        self.assert_bound()
        return VisiblePort(Port(self.declaration,self.ledger))
    def sources(self,refs):
        return [{'ref':r,'project':self.query['project'],'sha256':digest(self.events[int(r.split(':')[1])])} for r in sorted(set(refs))]
