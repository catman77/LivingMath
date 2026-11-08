"""Lazy finite argument cursors on real stored states; never an oracle search."""
from collections import deque
from math import gcd
import time
from ..core import digest
from ..symbolic.state import apply, require, alpha, reduce_sp
from ..symbolic.observers import witness_set
from .contracts import SYMBOLIC_POLICY


def structural_classes(state, observer):
    """Quotients are observations only; never merge source/history identities."""
    names = set(observer.names)
    out = set()
    if 'alpha_pattern' in names:
        value = observer.observe(state)['observers']['alpha_pattern']
        out.add('alpha:' + digest(value))
    if 'adjacency' in names:
        a = alpha(state.tokens)
        out.add('adjacency:' + digest([list(zip(a, a[1:])), sorted(set((p,k) for p,k,_ in state.boundaries))]))
    if 'sp_reduce' in names:
        normal, _ = reduce_sp(state.tokens)
        out.add('sp:' + digest(normal))
    return out


def family_size(state, op, roots, sample_cap):
    n = len(state.atoms)
    if op == 'SPLIT': return n + 1
    if op == 'INSERT_CANCEL_PAIR': return 2 * (n + 1)
    if op == 'CONCAT': return len(roots)
    if op in ('RENAME','SUBSTITUTE'): return min(sample_cap, max(1, len(set(state.tokens))))
    return 1


def arguments(state, op, index, roots, history):
    n = len(state.atoms)
    if op == 'SPLIT': return {'position': index}, None
    if op == 'INSERT_CANCEL_PAIR': return {'position': index // 2, 'kind': ('SP','PS')[index % 2]}, None
    if op == 'CONCAT': return {'other_parent': roots[index]}, history.states[roots[index]]
    if op in ('RENAME','SUBSTITUTE'):
        tokens = sorted(set(state.tokens));mapping = {}
        if tokens:
            if op == 'RENAME':
                if len(tokens) > 1: mapping = {t:tokens[(i+index+1)%len(tokens)] for i,t in enumerate(tokens)}
                else: mapping = {tokens[0]: tokens[0]} # finite sample, not all bijections
            else: mapping = {tokens[index % len(tokens)]: tokens[(index+1)%len(tokens)]}
        return {'mapping': mapping, 'scope': 'global'}, None
    return {}, None


def search(request, history, roots, observer, clock_factory):
    import heapq
    budget = request['search'];seed=budget['seed'];operators=sorted(set(request['operators']))
    deadline=time.thread_time()+budget.get('cpu_budget_ms',4000)/1000
    cap=budget['max_candidates_per_step'];max_obs=budget.get('max_observations',8192);max_tokens=budget.get('max_total_tokens',131072)
    total=sum(len(s.atoms) for s in history.states.values())
    require(len(history.nodes)<=budget['max_nodes'] and total<=max_tokens,'INITIAL_NODE_LIMIT')
    observations={i:observer.observe(s) for i,s in history.states.items()}
    require(len(observations)<=max_obs,'INITIAL_OBSERVATION_LIMIT')
    raw_seen=set().union(*(witness_set(o) for o in observations.values()))
    structural_seen=set().union(*(structural_classes(s,observer) for s in history.states.values()))
    initial_raw=len(raw_seen);initial_structural=len(structural_seen)
    structural_defined=bool(set(observer.names)&{'alpha_pattern','adjacency','sp_reduce'})
    words={s.word_hash:i for i,s in history.states.items()};groups={};heap=[];attempted=set();family_tried={};visits={};trace=[];applies=0;proposals=0
    coverage={o:dict(proposed=0,applied=0,new_outputs=0,duplicates=0,forbidden=0,resource_limited=0,duplicate_parameters=0) for o in operators}
    sampled=set();halt='MAX_STEPS';current=roots[0];rounds=0
    # One heap entry per raw-word/operator group, one member cursor per actual
    # node. Grouping schedules work; it never collapses DAG nodes or provenance.
    def register(ident):
        s=history.states[ident]
        for op in operators:
            group=digest([s.tokens,op]);n=family_size(s,op,roots,cap)
            if op in ('RENAME','SUBSTITUTE'): sampled.add(op)
            if group not in groups:
                rank=digest([seed,'state',s.tokens,op]);size=n
                start=int(digest([seed,'argument',group])[:16],16)%size
                stride=1+int(digest([seed,'stride',group])[:16],16)%size
                while gcd(stride,size)!=1: stride+=1
                groups[group]={'op':op,'members':deque(),'round':0,'size':size,'start':start,'stride':stride,'rank':rank,'queued':False,'length':len(s.atoms),'discovery':len(groups)}
            g=groups[group];g['members'].append([ident,0]);family_tried[ident,op]=0
            if not g['queued']:
                heapq.heappush(heap,(int(g['length']<2),g['round']//g['size'],g['discovery'],g['rank'],group));g['queued']=True
    for ident in history.nodes: register(ident)
    def take():
        nonlocal proposals
        while heap:
            _,_,_,_,key=heapq.heappop(heap);g=groups[key];g['queued']=False
            if not g['members']:continue
            node,count=g['members'].popleft();op=g['op'];size=g['size']
            # Each node has a complete lazy affine permutation of its finite
            # descriptor indices. Raw-word group rounds bound redundant histories.
            index=(g['start']+g['stride']*count)%size
            args,other=arguments(history.states[node],op,index,roots,history)
            ident=(node,op,digest(args));g['round']+=1;count+=1
            if count<size:g['members'].appendleft([node,count])
            if g['members']:
                heapq.heappush(heap,(int(g['length']<2),g['round']//g['size'],g['discovery'],g['rank'],key));g['queued']=True
            proposals+=1;coverage[op]['proposed']+=1
            if ident in attempted:
                coverage[op]['duplicate_parameters']+=1
                continue
            attempted.add(ident);family_tried[node,op]+=1
            return node,op,args,other
        return None
    def counters():
        remaining=sum(max(0,family_size(history.states[i],o,roots,cap)-n) for (i,o),n in family_tried.items())
        return {'frontier_remaining':remaining,'unexpanded_nontrivial':len({i for (i,o),n in family_tried.items() if len(history.states[i].atoms)>=2 and n<family_size(history.states[i],o,roots,cap)}),'global_exhaustion_proved':False}
    for step in range(budget['max_steps']):
        candidates=[];stop=None
        for slot in range(cap):
            if time.thread_time()>=deadline:halt='CPU_BOUND';break
            work=take()
            if work is None:halt='KNOWN_DESCRIPTOR_FRONTIER_EXHAUSTED';break
            node,op,args,other=work;state=history.states[node];parents=[node]
            call_args=dict(args)
            if op=='CONCAT':parents.append(call_args.pop('other_parent'))
            visits[node]=visits.get(node,0)+1;applies+=1;coverage[op]['applied']+=1
            outputs,events=apply(state,op,call_args,other)
            candidate={'slot':slot,'input_node':node,'operator':op,'parents':parents,'args':args,'parameter_key':digest(args),'applied':True,'produced_output_count':len(outputs),'outputs':[],'new_outputs':[],'output_parts':[],'new_raw_observation':[],'new_structural_class':[]}
            if any(len(s.atoms)>budget['max_word_tokens'] for s in outputs):
                candidate['status']='WORD_TOKEN_LIMIT';coverage[op]['forbidden']+=1;candidates.append(candidate);continue
            planned=[];local_words=dict(words)
            for part,s in enumerate(outputs):
                if budget.get('history_identity','word')=='word' and s.word_hash in local_words:
                    planned.append((part,s,local_words[s.word_hash],False));continue
                value={'parent_ids':parents,'op':op,'op_args':{**call_args,'output_part':part},'source_spans':sorted(set(x for a in s.atoms for x in a.spans)),'output_word_hash':s.word_hash,'events':list(events)}
                ident=digest(value);new=ident not in observations and not any(t[2]==ident for t in planned)
                planned.append((part,s,ident,new));local_words.setdefault(s.word_hash,ident)
            fresh=[t for t in planned if t[3]]
            if len(history.nodes)+len(fresh)>budget['max_nodes']:stop='MAX_NODES'
            elif len(observations)+len(fresh)>max_obs:stop='MAX_OBSERVATIONS'
            elif total+sum(len(s.atoms) for _,s,_,_ in fresh)>max_tokens:stop='MAX_TOTAL_TOKENS'
            if stop:
                candidate.update(status=stop,resource_limited=True,produced_output_hashes=[s.word_hash for s in outputs]);coverage[op]['resource_limited']+=1;candidates.append(candidate);break
            new_raw=set();new_structure=set()
            for part,s,ident,new in planned:
                if new:
                    actual=history.add(s,parents,op,{**call_args,'output_part':part},events);require(actual==ident,'HISTORY_BROKEN');total+=len(s.atoms)
                    obs=observer.observe(s);observations[ident]=obs;new_raw|=witness_set(obs)-raw_seen;new_structure|=structural_classes(s,observer)-structural_seen
                    words.setdefault(s.word_hash,ident);candidate['new_outputs'].append(ident);register(ident)
                candidate['outputs'].append(ident);candidate['output_parts'].append({'part':part,'node_id':ident,'new':new,'observed_output':s.data()})
            raw_seen|=new_raw;structural_seen|=new_structure
            coverage[op]['new_outputs']+=len(fresh);coverage[op]['duplicates']+=len(outputs)-len(fresh)
            candidate.update(status='GENERATED' if fresh else 'DUPLICATE_OUTPUT',new_raw_observation=sorted(new_raw),new_structural_class=sorted(new_structure));candidates.append(candidate)
        usable=[i for i,c in enumerate(candidates) if c['new_outputs']]
        pareto=[i for i in usable if not any(set(candidates[i]['new_structural_class'])<set(candidates[j]['new_structural_class']) for j in usable)] if structural_defined else usable
        chosen=min(pareto,key=lambda i:digest([seed,'choice',step,candidates[i]['parameter_key']])) if pareto else None
        part=None
        if chosen is not None:
            c=candidates[chosen];part=int(digest([seed,'output',step])[:8],16)%len(c['new_outputs']);current=c['new_outputs'][part]
            part=next(p['part'] for p in c['output_parts'] if p['node_id']==current)
        trace.append({'step':step,'input_node':candidates[0]['input_node'] if candidates else current,'candidates':candidates,'pareto_indices':pareto,'selected_index':chosen,'chosen_output_part':part,'current_node':current,'selection':'frontier_coverage_then_structural_set_inclusion' if structural_defined else 'STRUCTURAL_NOVELTY_UNDEFINED','pareto_filtered_count':len(usable)-len(pareto)})
        rounds+=1
        if stop:halt=stop;break
        if not candidates or halt in ('KNOWN_DESCRIPTOR_FRONTIER_EXHAUSTED','CPU_BOUND'):break
    parameter={o:{'attempted_unique':sum(n for (i,op),n in family_tried.items() if op==o),'applicable_known':sum(family_size(history.states[i],op,roots,cap) for (i,op) in family_tried if op==o),'status':'ARGUMENT_FAMILY_PARTIAL' if o in sampled else 'FINITE_DESCRIPTOR_COVERAGE','sampled_budget_per_node':cap if o in sampled else None} for o in operators}
    definitions={'alpha_pattern':'Declared CAD alpha scope and boundary positions', 'adjacency':'Global alpha-normalized oriented adjacency with boundary types; not a local-history quotient', 'sp_reduce':'SP/PS cancellation normal form, only declared SP algebra'}
    summary={'steps':rounds,'attempted_candidates':applies,'proposed':proposals,'applied':applies,'nodes':len(history.nodes),'observations':len(observations),'total_stored_tokens':total,'unique_literal_words':len({s.tokens for s in history.states.values()}),'history_identity':budget.get('history_identity','word'),'halt_reason':halt,'policy':SYMBOLIC_POLICY,'parameter_coverage':parameter,'operation_coverage':coverage,'new_raw_observation':len(raw_seen)-initial_raw,'new_structural_class':len(structural_seen)-initial_structural if structural_defined else None,'structural_novelty_status':'DEFINED_ON_DECLARED_QUOTIENTS' if structural_defined else 'STRUCTURAL_NOVELTY_UNDEFINED','pareto_filtered_count':sum(t['pareto_filtered_count'] for t in trace),'structural_class_definitions':{k:v for k,v in definitions.items() if k in observer.names},'quotient_classes_do_not_merge_source_or_history':True,'produced_output_units':sum(c['produced_output_count'] for t in trace for c in t['candidates']),'new_outputs':sum(v['new_outputs'] for v in coverage.values()),'duplicates':sum(v['duplicates'] for v in coverage.values()),'forbidden':sum(v['forbidden'] for v in coverage.values()),'resource_limited':sum(v['resource_limited'] for v in coverage.values()),'parent_revisits':sum(n-1 for n in visits.values()),'budget_remaining':{'apply':budget['max_steps']*cap-applies,'nodes':budget['max_nodes']-len(history.nodes),'total_tokens':max_tokens-total,'observations':max_obs-len(observations)},'budgets':{**budget,'max_observations':max_obs,'max_total_tokens':max_tokens},**counters()}
    diagnostic={'kind':'observed','status':'PARTIAL_PARAMETER_COVERAGE','halt_reason':halt,'sampled_families':sorted(sampled),'scope':'Stored states and finite descriptors only; sampled mapping families are not exhaustive',**counters()}
    return {'ops_trace':trace,'structural_observations':[{'node_id':i,**o,'structural_quotient_classes':sorted(structural_classes(history.states[i],observer))} for i,o in observations.items()],'search_diagnostics':[diagnostic],'search_summary':summary,'final_node_id':current}
