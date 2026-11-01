"""I*: finite native trace dependency construction; no world labels, environment or oracle."""
from itertools import combinations
import json
from pathlib import Path
import time

from live_transfer006 import interpret, attend, endpoint, initial_cache
from live_transfer006_primitives import Exhausted
from normalizer import canonical, digest
from concept_genesis012_source import Request, Frame, bind
from concept_genesis012_native import Ledger


def refusal(status: str, reason: str, **extra) -> dict:
    return {'status':status,'reason':reason,'proof_status':'unverified','execution_permission':{'allowed':False},
            'measurement_executed':False,'move_created':False,**extra}


def leaf_paths(value, path=()):
    if isinstance(value,(tuple,list)):
        for i,child in enumerate(value):yield from leaf_paths(child,path+(i,))
    else:yield path


def field_value(value, path):
    try:
        for index in path:value=value[index]
        return {'defined':True,'value':value}
    except (IndexError,TypeError):return {'defined':False,'value':None}


def census(frame: Frame, stage: str = 'enumeration') -> dict:
    frame.ledger.stage=stage;port=frame.port(4096)
    caches={ref:initial_cache(port,frame.words[ref]) for ref in frame.spec['histories']}
    return {ref:{t['id']:endpoint(port,caches[ref],t['suffix'],frame.spec['observer']) for t in frame.spec['tests']} for ref in frame.spec['histories']}


def discover(frame: Frame) -> dict:
    """Unchanged006 paired probing discovers the negative input, never an operator-chosen pair."""
    frame.ledger.stage='006_negative_discovery'
    refs=sorted(frame.spec['histories'],key=lambda r:(tuple(frame.spec['parameters']['actions'].index(a) for a in frame.words[r]),r))
    tested=0
    for left,right in combinations(refs,2):
        result=interpret(frame,left,right,max_calls=4096);tested+=1
        if result['status']=='NEW_DISTINCTION':
            suffix=result['witness']['suffix'];actions=frame.spec['parameters']['actions']
            return refusal('SOURCE_COUNTEREXAMPLE','Old primary-observation quotient fails under a native continuation.',
                counterexample={'claim_type':'COUNTEREXAMPLE','origin':'bounded_source_computation_not_external_measurement',
                    'scope':frame.query['scope'],'version':frame.query['version'],'observer':frame.spec['observer'],
                    'primitive_sha256':frame.spec['primitive_sha256'],'histories':[left,right],
                    'suffix_ordinals':[actions.index(a) for a in suffix],'readouts':result['predictions'],
                    'proof_status':'unverified'},tested_pairs=tested,costs=frame.ledger.summary(),trace=frame.ledger.trace)
        if result['status'] in {'FAIL_CLOSED','UNKNOWN_BOUNDED'} and sum(frame.ledger.counts.values())>=frame.ledger.limit:
            return refusal('BUDGET_EXHAUSTED','PAIR_PROBING_BOUND',costs=frame.ledger.summary(),trace=frame.ledger.trace)
    return refusal('NO_DISTINCTION_BOUNDED','No difference on the executed finite pair/domain census; no source equality asserted.',
        tested_pairs=tested,costs=frame.ledger.summary(),trace=frame.ledger.trace)


def construct(frame: Frame, negative_event_id: int | None, trace_access: bool = True) -> dict:
    frame.assert_bound()
    if negative_event_id is None:return refusal('NO_NEGATIVE_FEEDBACK','No source-backed failure to explain.')
    if not trace_access:return refusal('INSUFFICIENT_CONTEXT','INTERMEDIATE_TRACE_PROVENANCE_UNAVAILABLE')
    row=frame.events.get(negative_event_id)
    if row is None:return refusal('INSUFFICIENT_CONTEXT','MISSING_NEGATIVE_EVENT')
    negative=json.loads(row['content'])
    expected={'scope':frame.query['scope'],'version':frame.query['version'],'observer':frame.spec['observer'],'primitive_sha256':frame.spec['primitive_sha256']}
    if any(negative.get(k)!=v for k,v in expected.items()):return refusal('NO_VALID_INTERPRETATION','FOREIGN_OR_STALE_COUNTEREXAMPLE')
    left,right=negative.get('histories',[None,None]);actions=frame.spec['parameters']['actions']
    if left not in frame.spec['histories'] or right not in frame.spec['histories']:return refusal('NO_VALID_INTERPRETATION','NEGATIVE_HISTORY_NOT_BOUND')
    suffix=[actions[i] for i in negative['suffix_ordinals']]
    if suffix not in [t['suffix'] for t in frame.spec['tests']]:return refusal('NO_VALID_INTERPRETATION','NEGATIVE_OUTSIDE_DOMAIN')
    timings={};started=time.perf_counter_ns();cpu=time.process_time_ns()
    def mark(name):
        nonlocal started,cpu
        now=time.perf_counter_ns();current=time.process_time_ns()
        timings[name]={'wall_ns':now-started,'CPU_ns':current-cpu};started,cpu=now,current
    frame.ledger.stage='negative_replay';port=frame.port(4096)
    states={r:port.load(frame.words[r]) for r in frame.spec['histories']}
    caches={r:{():{'state':s,'admissibility':[]}} for r,s in states.items()}
    actual=[endpoint(port,caches[r],suffix,frame.spec['observer']) for r in (left,right)]
    if actual!=negative['readouts'] or actual[0]==actual[1]:return refusal('NO_VALID_INTERPRETATION','NEGATIVE_SOURCE_REPLAY_MISMATCH')
    mark('negative_replay')
    frame.ledger.stage='source_field_dependency'
    paths=sorted(set(leaf_paths(states[left].value))|set(leaf_paths(states[right].value)),key=lambda p:(len(p),p))
    responses={r:endpoint(port,caches[r],suffix,frame.spec['observer']) for r in frame.spec['histories']}
    path=None;mapping={};rejected=[]
    for candidate in paths:
        frame.ledger.charge('candidate_source_address')
        if field_value(states[left].value,candidate)==field_value(states[right].value,candidate):continue
        table={};coherent=True
        for ref,state in states.items():
            key=canonical(field_value(state.value,candidate));value=responses[ref]
            if key in table and table[key]!=value:coherent=False;break
            table[key]=value
        if coherent:path=candidate;mapping=table;break
        rejected.append({'path':list(candidate),'reason':'SAME_SOURCE_FIELD_DIFFERENT_RESIDUAL_READOUT'})
    if path is None:return refusal('NO_VALID_INTERPRETATION','NO_TRACE_ADDRESS_EXPLAINS_THE_NEGATIVE_CLASS',rejected_features=rejected)
    cells={}
    for ref,response in responses.items():cells.setdefault(canonical(response),[]).append(ref)
    concept={'source_address_path':list(path),'value_to_residual':mapping,
        'suffix_ordinals':negative['suffix_ordinals'],'scope':frame.query['scope'],'observer':frame.spec['observer'],
        'applicability_event_refs':sorted(states),'counterexample_ref':'event:'+str(negative_event_id),
        'predicts_only_this_registered_continuation':True,'asserts_future_congruence':False,
        'interpretations':[{'predicate_source_values':[json.loads(k) for k,v in mapping.items() if canonical(v)==outcome],
            'source_members':sorted(members),'prediction':json.loads(outcome)} for outcome,members in sorted(cells.items())]}
    # This is a source-generated conditional interpretation, not a claim of novelty beyond probing.
    ordinal=lambda word:[actions.index(a) for a in word]
    p={**frame.spec['parameters'],'actions':list(range(len(actions)))}
    fingerprint=digest({'source_instance':frame.spec['instance_ref'],'project':frame.query['project'],
        'native_definition':frame.spec['primitive_sha256'],'parameters':p,'observer':frame.spec['observer'],
        'domain':sorted(ordinal(t['suffix']) for t in frame.spec['tests']),'source_words':sorted(ordinal(w) for r,w in frame.words.items() if r in frame.spec['histories']),
        'path':list(path),'mapping':mapping,'suffix':negative['suffix_ordinals']})
    mark('source_dependency_construction')
    frame.ledger.stage='falsifier_of_stronger_congruence';falsifier=None
    for members in cells.values():
        for a,b in combinations(members,2):
            for test in frame.spec['tests']:
                values=[endpoint(port,caches[r],test['suffix'],frame.spec['observer']) for r in (a,b)]
                if values[0]!=values[1]:
                    falsifier={'claim_refuted':'Same generated feature implies all future readouts agree.',
                        'histories':[a,b],'suffix_ordinals':ordinal(test['suffix']),'readouts':values,
                        'effect':'Bounded residual concept remains valid only on its declared continuation; stronger congruence is false.'};break
            if falsifier:break
        if falsifier:break
    mark('falsifier_search')
    frame.ledger.stage='unchanged_T006';attention=attend(frame,max_calls=4096);mark('T006')
    return refusal('CANDIDATE_REFINEMENT','Native trace dependency constructed; no independent scientific novelty claim yet.',
        concept=concept,fingerprint=fingerprint,witness={'histories':[left,right],'suffix_ordinals':negative['suffix_ordinals'],'readouts':actual},
        falsifier=falsifier,attention=attention,rejected_features=rejected,stage_costs=timings,
        dependency_log={'pair_origin':'unchanged006 probing, not operator','guard_origin':'native trace field candidates + exact residual consistency',
            'interpretations_origin':'algorithmic partition of native readouts; no supplied theories/guard/path',
            'inputs':['bound source events','native operation definitions','replayed negative event'],
            'oracle_access':False,'actual_hidden_environment_access':False,'candidate_source_states_are_not_the_hidden_environment':True})


def evaluate(database: Path, request: Request, mode: str = 'genesis') -> dict:
    start=time.perf_counter_ns();cpu=time.process_time_ns();frame=None;ledger=Ledger(request.max_calls,5)
    try:
        frame,binding=bind(database,request,ledger)
        binding_cost={'wall_ns':time.perf_counter_ns()-start,'CPU_ns':time.process_time_ns()-cpu}
        if mode=='negative':out=discover(frame)
        elif mode=='baseline':
            t=time.perf_counter_ns();c=time.process_time_ns();table=census(frame,'B1_census')
            census_cost={'wall_ns':time.perf_counter_ns()-t,'CPU_ns':time.process_time_ns()-c}
            t=time.perf_counter_ns();c=time.process_time_ns();frame.ledger.stage='B1_T006';attention=attend(frame,max_calls=4096)
            out=refusal('BASELINE_FINITE_CENSUS','Unchanged006 endpoint/T, no concept generator.',table=table,attention=attention,
                stage_costs={'B1_census':census_cost,'T006':{'wall_ns':time.perf_counter_ns()-t,'CPU_ns':time.process_time_ns()-c}})
        else:out=construct(frame,request.negative_event_id,request.trace_access)
        out.update(binding=binding)
        out.setdefault('stage_costs',{})['source_normalization_binding']=binding_cost
    except Exhausted as error:out=refusal('BUDGET_EXHAUSTED',str(error))
    except (ValueError,KeyError,TypeError,IndexError) as error:out=refusal('INSUFFICIENT_CONTEXT',str(error))
    out.update(wall_ns=time.perf_counter_ns()-start,CPU_ns=time.process_time_ns()-cpu,
        costs=ledger.summary(),raw_trace=ledger.trace)
    if len(canonical(out).encode())>8_000_000:return refusal('BUDGET_EXHAUSTED','OUTPUT_BOUND')
    return out
