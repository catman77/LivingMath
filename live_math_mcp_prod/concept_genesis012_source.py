"""SELECT-only source binding and a sealed frame implementing the existing006 protocol."""
import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Literal

from pydantic import Field
from native_preview008_contract import DataModel, Project, EventID, Observer, SourceBinding
from normalizer import Budget, canonical, digest, normalize_context, read_history, reconstruct_context
from native_preview008_engine import check_sources, frontier
from concept_genesis012_native import Ledger, Port, definition_sha256


class Request(DataModel):
    project: Project
    obligation_id: EventID
    version: EventID
    root_event_id: EventID
    source_bindings: list[SourceBinding] = Field(min_length=1, max_length=128)
    observer: Observer
    negative_event_id: EventID | None = None
    context_level: Literal['C2','C3','C4'] = 'C2'
    trace_access: bool = True
    max_calls: int = Field(default=4096, ge=1, le=4096)


@dataclass
class Frame:
    spec: dict
    query: dict
    events: dict
    words: dict
    ledger: Ledger = field(default_factory=Ledger)
    _seal: str = field(init=False, repr=False)

    def __post_init__(self): self._seal = digest([self.spec,self.query,self.events,self.words])

    def assert_bound(self):
        if self._seal != digest([self.spec,self.query,self.events,self.words]): raise ValueError('MUTATED_BOUND_FRAME')
        if self.spec['primitive_sha256'] != definition_sha256(): raise ValueError('SOURCE_DEFINITION_DRIFT')

    def port(self, max_calls: int = 4096, seconds: float = 5) -> Port:
        self.assert_bound();self.ledger.limit=min(self.ledger.limit,max_calls)
        self.ledger.seconds=min(self.ledger.seconds,seconds)
        return Port(copy.deepcopy(self.spec['parameters']),self.words,self.ledger)

    def sources(self, refs: list[str]) -> list[dict]:
        return [{'ref':ref,'project':self.query['project'],'sha256':digest(self.events[int(ref.split(':')[1])])} for ref in sorted(set(refs))]

    def fork(self) -> 'Frame':
        return Frame(copy.deepcopy(self.spec),copy.deepcopy(self.query),copy.deepcopy(self.events),copy.deepcopy(self.words),Ledger(self.ledger.limit,5))


def bind(database: Path, request: Request, ledger: Ledger | None = None) -> tuple[Frame, dict]:
    if len(canonical(request.model_dump()).encode()) > 65536: raise ValueError('INPUT_BOUND')
    if request.context_level == 'C4': raise ValueError('C4_IS_NOT_AUDIT_SUFFICIENT')
    history=read_history(database,request.project,Budget(max_events=128,max_source_bytes=500000,max_output_bytes=1000000,max_tokens=100000,max_milliseconds=5000))
    ids=[b.event_id for b in request.source_bindings]
    check_sources(history,ids,request.source_bindings,exact=True)
    events={e['id']:e for e in history['tables']['events']}
    if set(ids)!=set(events):raise ValueError('INCOMPLETE_SOURCE_CLOSURE')
    active=frontier(history,request.obligation_id,request.version)
    root=events.get(request.root_event_id)
    if root is None:raise ValueError('MISSING_ROOT')
    payload=json.loads(root['content']);spec=payload['source_spec']
    required={'parameters','histories','independent_ref','tests','observer','scope','version','primitive_sha256','representation','instance_ref'}
    if set(spec)!=required:raise ValueError('UNDECLARED_SOURCE_FIELD')
    if spec['scope']!=active['scope'] or spec['version']!=request.version:raise ValueError('SOURCE_SCOPE_OR_VERSION')
    if spec['observer']!=request.observer.model_dump():raise ValueError('OBSERVER_MISMATCH')
    if spec['primitive_sha256']!=definition_sha256() or spec['representation']!='source012-native/v1':raise ValueError('SOURCE_DEFINITION_DRIFT')
    if len(spec['histories'])>16 or not 1<=len(spec['tests'])<=32:raise ValueError('SOURCE_DOMAIN_BOUND')
    actions=spec['parameters']['actions']
    if len(set(actions))!=len(actions) or not 2<=len(actions)<=5:raise ValueError('ACTION_BOUND')
    words={}
    for ref in spec['histories']+[spec['independent_ref']]:
        eid=int(ref.split(':')[1]);row=events.get(eid)
        if row is None:raise ValueError('MISSING_OR_FOREIGN_HISTORY')
        item=json.loads(row['content'])
        if item['version']!=request.version or item['representation']!='source012-native/v1':raise ValueError('HISTORY_REPRESENTATION_VERSION')
        if ref in spec['histories'] and item['scope']!=active['scope']:raise ValueError('HISTORY_SCOPE')
        if len(item['word'])>6 or not set(item['word'])<=set(actions):raise ValueError('HISTORY_ALPHABET')
        words[ref]=item['word']
    for i,t in enumerate(spec['tests']):
        if set(t)!={'id','ordinal','suffix','cost'} or t['ordinal']!=i or len(t['suffix']) not in (1,2) or not set(t['suffix'])<=set(actions) or type(t['cost']) is not int or t['cost']<0:
            raise ValueError('TEST_DOMAIN')
    if request.negative_event_id is not None and request.negative_event_id not in events:raise ValueError('MISSING_OR_FOREIGN_NEGATIVE_EVENT')
    query={'id':'genesis012','project':request.project,'root_ref':'event:'+str(root['id']),'scope':active['scope'],'version':request.version,
        'move':{'active_frontier_id':request.obligation_id,'parent_event_ids':ids,'proposed_operation':{'mechanism':'readonly_source_refinement','intent':'advisory'}}}
    view=normalize_context(history,'source-native concept genesis',[query],request.context_level)
    if view['status']!='COMPLETE' or not view.get('audit_context'):raise ValueError('NORMALIZATION_INCOMPLETE')
    recovered=reconstruct_context(view,history)
    if {e['id']:e for e in recovered['tables']['events']}!={e['id']:e for e in history['tables']['events']}:
        raise ValueError('NORMALIZATION_RECOVERY_DRIFT')
    port=Port(spec['parameters'],words,ledger or Ledger(request.max_calls,5))
    observations=[port.observe(port.load(words[r]),spec['observer']) for r in spec['histories']]
    if len(set(observations))!=1:raise ValueError('NOT_ONE_CURRENT_OBSERVATION_CLASS')
    compiled={**copy.deepcopy(spec),'current_observation':observations[0],'known_failures':[],
        'unknowns':['No source equality or unbounded future equivalence is asserted.'],
        'hypotheses':[{'id':r,'ref':r,'weight':1,'predictive':True,'question':'current','depends_on':[]} for r in spec['histories']]+
            [{'id':'IND','ref':spec['independent_ref'],'weight':1,'predictive':False,'question':'independent','depends_on':[]}]}
    # Input validation calls are included in the same cost ledger as inference.
    frame=Frame(compiled,query,events,words,port.ledger)
    return frame,{'normalizer':'004.1','view_digest':digest(view),'source_hashes':frame.sources(['event:'+str(i) for i in ids]),
        'source_bytes':len(canonical(history).encode()),'loss_ledger':view['loss_ledger'],
        'normalization_source_recovery':'EXACT','source_identity':spec['instance_ref']}
