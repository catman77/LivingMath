"""Explicit flat baseline and input-only adapter to the unchanged005 module."""
import copy
from fractions import Fraction
import json
import time
import sys
import cProfile

import live_core005 as old
from normalizer import normalize_context


def raw_endpoint(port,frame,ref,suffix):
    s=port.load(frame.words[ref]);flags=[]
    for a in suffix:
        allowed=port.admissible(s,a);flags.append(allowed)
        if not allowed:return {'defined':False,'observation':None,'admissibility':flags}
        s=port.extend(s,a)
    return {'defined':True,'observation':port.observe(s,frame.spec['observer']),'admissibility':flags}


def flat_pair(frame,left,right):
    port=frame.port(32768,10);start=time.perf_counter()
    current=[port.observe(port.load(frame.words[r]),frame.spec['observer']) for r in (left,right)]
    signatures=[{t['id']:raw_endpoint(port,frame,r,t['suffix']) for t in frame.spec['tests']} for r in (left,right)]
    differences=[t['id'] for t in frame.spec['tests'] if signatures[0][t['id']]!=signatures[1][t['id']]]
    return {'hidden':current[0]==current[1] and bool(differences),'different_tests':differences,
            'primitive_calls':port.counts,'seconds':time.perf_counter()-start,'signatures':signatures}


def flat_attention(frame):
    port=frame.port(32768,10);start=time.perf_counter()
    active=[h for h in frame.spec['hypotheses'] if h['question']=='current' and h['predictive']
            and port.observe(port.load(frame.words[h['ref']]),frame.spec['observer'])==frame.spec['current_observation']]
    ranks=[]
    for t in frame.spec['tests']:
        values=[raw_endpoint(port,frame,h['ref'],t['suffix']) for h in active]
        if len(values)<2 or not all(v['defined'] for v in values) or all(v==values[0] for v in values):continue
        total=sum(h['weight'] for h in active)
        remaining=sum(Fraction(h['weight'])*sum(values[i]==v for v in values) for i,h in enumerate(active))/total
        loss=t['cost']+Fraction(7,3)*remaining
        ranks.append((loss,t['cost'],t['ordinal'],t['id']))
    ranks.sort()
    return {'test_id':ranks[0][3] if ranks else None,'primitive_calls':port.counts,'seconds':time.perf_counter()-start}


def old_input(world,frame):
    """Lossless math I/O re-encoding on mod5 only; no source/canonical DB writes."""
    if frame.spec['family']!='register' or frame.spec['parameters']['modulus']!=5:
        return world['history'],world['query'],False
    history=copy.deepcopy(world['history']);p=frame.spec['parameters'];query=world['query']
    words={ref:[p['actions'].index(x) for x in w] for ref,w in frame.words.items()}
    for event in history['tables']['events']:
        value=json.loads(event['content']);value['representation']=old.REPRESENTATION
        ref='event:'+str(event['id'])
        if ref in words:value['word']=words[ref]
        if ref==query['root_ref']:
            spec=frame.spec
            hs=[]
            for h in spec['hypotheses']:
                native=old.register_state(words[h['ref']])
                if h['question']=='current' and native[0]!=spec['current_observation']:continue
                question='current' if h['question']=='current' else 'independent'
                hs.append({'id':h['id'],'history_ref':h['ref'],'weight':h['weight'],'question':question,
                           'predictive':h['predictive'],'depends_on':h['depends_on']})
            value['source_spec']={'representation':old.REPRESENTATION,'kernel_sha256':old.kernel_fingerprint(),
                'scope':query['scope'],'version':query['version'],'histories':spec['histories'],
                'independent_ref':spec['independent_ref'],'tests':[dict(t,suffix=[p['actions'].index(x) for x in t['suffix']]) for t in spec['tests']],
                'hypotheses':hs,'observer':'x','forbidden_y':None,'uncertainty_price':'7/3','unknowns':spec['unknowns']}
        event['content']=json.dumps(value,sort_keys=True)
    return history,query,True


def old_pair(world,frame,left,right):
    history,q,translated=old_input(world,frame);v=normalize_context(history,'baseline005',[q],'C2')
    counts={'register_state':0,'analytic_continuation':0,'observe':0};original={n:getattr(old,n) for n in counts}
    codes={f.__code__:n for n,f in original.items()}
    profiler=cProfile.Profile();start=time.perf_counter();previous=sys.getprofile()
    try:
        profiler.enable();out=old.interpret_distinction(v,history,q,left,right)
    finally:
        profiler.disable();sys.setprofile(previous)
    for entry in profiler.getstats():
        if entry.code in codes:counts[codes[entry.code]]+=entry.callcount
    return {'output':out,'seconds':time.perf_counter()-start,'actual_function_calls':counts,
            'primary_boundary_calls':{'extend':0,'observe':0,'admissible':0},
            'boundary_note':'005 does not use this protocol; zero boundary calls is not zero computational work.',
            'input_reencoded_mod5_only':translated}


def old_attention(world,frame):
    history,q,translated=old_input(world,frame);v=normalize_context(history,'baseline005',[q],'C2')
    start=time.perf_counter();out=old.transfer_attention(v,history,q)
    return {'output':out,'seconds':time.perf_counter()-start,'input_reencoded_mod5_only':translated}
