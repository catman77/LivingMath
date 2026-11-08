"""Opt-in dynamic CAT pair tie-break using the actual supplied primitives."""
from collections import Counter
from math import gcd
from ..core import digest
from ..symbolic.state import require
from .contracts import NUMERIC_POLICY


def distinctions(data, atlas):
    ids={c['id'] for c in data['concepts']};out=[]
    for view,chart in enumerate(atlas['charts']):
        require(chart['view']==view and bool(chart['aliases']),'REJECTED_PROVENANCE')
        pairs=set()
        for a in chart['aliases']:
            pair=a['concepts'];require(len(pair)==2 and pair[0]!=pair[1] and set(pair)<=ids,'REJECTED_PROVENANCE')
            pairs.add(tuple(sorted(pair)))
        out.append({'source_bound_concept_pairs':[list(p) for p in sorted(pairs)],
                    'distinction_key':next(iter(pairs)) if len(pairs)==1 else None,
                    'alias_resolution':'UNAMBIGUOUS' if len(pairs)==1 else 'DISTINCTION_AMBIGUOUS'})
    return out


def dynamic_search(data, atlas, protocol, source_ref=None, policy=NUMERIC_POLICY):
    # Imports resolve the hash-checked supplied files preloaded by runtime.load.
    # No reference_oracles module, labels, language scores or native modification.
    import cad
    from udav import WhiteStarOrbit, ReversibleUDAV, GraphTopology
    from source import Observation, WhiteStarSource
    from rotated_atlas import decode_observations
    matrices=tuple(tuple(c['matrix']) for c in atlas['charts']);n=len(matrices)
    require(1<=protocol['candidates_per_step']<=n,'INVALID_INPUT')
    identities=distinctions(data,atlas);seed=protocol['frozen_seed'];orbit=WhiteStarOrbit(seed);clock=ReversibleUDAV(seed);graph=GraphTopology()
    seen=Counter();phase=Counter();used=Counter();pairs_seen=set();prev=None;observations=[];audit=[];ambiguous=0;nonzero_pairs=set()
    stride=11
    while gcd(stride,n)!=1:stride+=1
    original=cad.CHARTS;cad.CHARTS=matrices
    try:
        for step in range(protocol['steps']):
            witness=orbit.next();require(witness.verify(),'REJECTED_PROVENANCE')
            first=(clock.step()+(step+1)*7+seed)%n
            views=tuple((first+i*stride)%n for i in range(protocol['candidates_per_step']))
            candidates=[];projections=[];scores=[];keys=[]
            for view in views:
                p=cad.project(witness,view);projections.append(p)
                nv,ne,nc=graph.novelty(prev,p.signature);primary=min(13,6*nv+3*ne+4*nc)
                identity=identities[view];pair=identity['distinction_key'];new_pair=pair not in pairs_seen if pair is not None else None
                score=(primary/13,1/(1+seen[p.signature]),1/(1+phase[p.signature[-1]]),1/(1+used[view]));scores.append(score)
                legacy=(primary,-seen[p.signature],-phase[p.signature[-1]],-used[view])
                keys.append((legacy[0],int(new_pair is True),*legacy[1:]) if policy==NUMERIC_POLICY else legacy)
                candidates.append({'view_id':view,'matrix':list(p.matrix),'aliases':atlas['charts'][view]['aliases'],**identity,
                                   'arithmetic_signature':list(p.signature),'novelty_primary':primary,'topology_score':[nv,ne,nc],
                                   'new_pair':new_pair,'seen_before':pair in pairs_seen if pair is not None else None,
                                   'legacy_score':list(score),'legacy_counters':{'signature':seen[p.signature],'phase':phase[p.signature[-1]],'view':used[view]},
                                   'source_ref':source_ref,'source_sha256':data['source']['sha256']})
            best=max(range(len(views)),key=keys.__getitem__);view=views[best];projection=projections[best];identity=identities[view];pair=identity['distinction_key']
            legacy_best=max(range(len(views)),key=lambda i:tuple(candidates[i]['legacy_score']))
            reason='NEW_CAT_PAIR_AFTER_EQUAL_PRIMARY' if best!=legacy_best else 'LEGACY_ORDER_WITH_PRIMARY_MAX'
            require(candidates[best]['novelty_primary']==max(c['novelty_primary'] for c in candidates),'PRIMARY_NOVELTY_DEGRADED')
            audit.append({'step':step,'selected_by':policy,'selected_index':best,'selected_view':view,'candidate_list_sha':digest(candidates),
                          'candidates':candidates,'novelty_primary':candidates[best]['novelty_primary'],'distinction_key':pair,
                          'seen_before':candidates[best]['seen_before'],'topology_score':candidates[best]['topology_score'],
                          'reason_tie_break':reason,'memory_before_sha256':digest({'seen':sorted(seen.items()),'phase':sorted(phase.items()),'used':sorted(used.items()),'pairs':sorted(pairs_seen),'previous':prev}),
                          'source_ref':source_ref,'direction_defined':any(witness.direction),'execution_permission':False})
            graph.add(prev,projection.signature);prev=projection.signature;seen[prev]+=1;phase[prev[-1]]+=1;used[view]+=1
            if pair is not None:
                pairs_seen.add(pair)
                if any(witness.direction):nonzero_pairs.add(pair)
            else:ambiguous+=1
            a,b=witness.direction
            observations.append(Observation(step,(witness.numerator.s,witness.numerator.p),(witness.denominator.s,witness.denominator.p),
                                (a,b),a+b,views,tuple(scores),view,projection.matrix,(projection.a,projection.b),bool(a or b),
                                projection.quotients,projection.gcd,projection.signature,WhiteStarSource.state_of(witness,projection)).to_dict())
    finally:cad.CHARTS=original
    stats={'steps':len(observations),'projections':len(observations)*protocol['candidates_per_step'],'charts_used':len(used),'available_charts':n,
           'full_signatures':len(seen),'observation_vertices':len(graph.parent),'observation_edges':len(graph.edges),'beta0':graph.beta0,'beta1':graph.beta1,
           'selection_policy':policy,'selected_unambiguous_pairs':len(pairs_seen),'selected_nonzero_pairs':len(nonzero_pairs),
           'ambiguous_aliases':ambiguous,'exact_pairs':sorted(pairs_seen),'LLM_calls':0,'network_calls':0}
    # audit is attached to each observation in the new path; legacy observations
    # and scores are never read/reordered. This trajectory owns its own memory.
    for record,entry in zip(observations,audit):record['selection_audit']=entry
    return observations,decode_observations(atlas,observations),stats


def run(request, adapter):
    from .symbolic import binding
    original=adapter.search
    def search(data,atlas,protocol):return dynamic_search(data,atlas,protocol,source_ref=digest(request))
    adapter.search=search
    try:result=adapter.explore(request)
    finally:adapter.search=original
    result.update(engine='white_star_udav_v2',selection_policy=NUMERIC_POLICY,selection_audit=[r['selection_audit'] for r in result['trace']],
                  manifest={'schema':'udav-numeric-policy/1','kernel_binding':binding('numeric'),'source_ref':digest(request),
                            'legacy_kernel':'UNCHANGED_SUPPLIED_CODE','source_relations_status':'DECLARED_INPUT_NOT_VERIFIED_FACTS','execution_permission':False})
    result.pop('artifact_sha256',None);result['artifact_sha256']=digest(result)
    return result
