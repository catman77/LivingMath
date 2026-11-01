"""Independent source/stoichiometric checks, scoped DAV laws and retained repairs."""
from copy import deepcopy
from itertools import combinations
from typing import Any, Callable

from pydantic import ValidationError
from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Apply, Eq, Formula, Implies, Var, digest, term
from davcore.finite import check
from davcore.models import Budget
from .contract import SourceGraph, ProposalRequest
from .network import Network


def check_translation(graph: SourceGraph, candidate: dict) -> dict:
    conflicts: list[dict[str,Any]]=[];witnesses: list[dict[str,Any]]=[]
    def conflict(reason,refs,**details):
        conflicts.append({'reason':reason,'source_refs':sorted(set(refs)),**details})
    try:n=Network.model_validate(candidate['network'])
    except (ValidationError,KeyError) as exc:
        return {'status':'FAIL_FIDELITY','conflicts':[{'reason':'ILL_TYPED_NETWORK','detail':str(exc)}],
                'proof_status':'unverified','execution_permission':{'allowed':False}}
    species={s.id:s for s in n.species};mapping=candidate.get('mapping',{})
    if candidate.get('source_graph_sha256')!=digest(graph.model_dump()):
        conflict('SOURCE_GRAPH_BINDING_MISMATCH',[])
    relations={r.id:r for r in graph.relations};nodes={node.id:node for node in graph.nodes}
    for rel in graph.relations:
        if rel.kind in {'contrast','role','order'} and mapping.get(rel.src)==mapping.get(rel.dst):
            conflict('SOURCE_DISTINCTION_ERASED',rel.source_refs,relation_id=rel.id,
                     source_nodes=[rel.src,rel.dst],target=mapping.get(rel.src))
    if set(mapping)!=set(nodes):conflict('MAPPING_MUST_COVER_EXACT_SOURCE_NODES',[])
    groups: dict[str,list[str]]={}
    for source,target in mapping.items():groups.setdefault(target,[]).append(source)
    for target,origins in groups.items():
        if len(origins)>1 and not any(set(loss.get('source_nodes',[]))==set(origins) and
            loss.get('target_species')==target for loss in candidate.get('loss_ledger',[])):
            conflict('UNDECLARED_MANY_TO_ONE_LOSS',[ref for origin in origins if origin in nodes for ref in nodes[origin].source_refs],
                     source_nodes=origins,target_species=target)
    for node in graph.nodes:
        target=species.get(mapping.get(node.id))
        if target is None or not set(node.source_refs)<=set(target.source_refs):
            conflict('SOURCE_NODE_REVERSE_TRACE_MISSING',node.source_refs,node_id=node.id)
    valid_refs={ref for refs in [x.source_refs for x in graph.nodes]+[x.source_refs for x in graph.relations] for ref in refs}
    for s in n.species:
        if not set(s.source_refs)<=valid_refs:conflict('UNSUPPORTED_SPECIES_PROVENANCE',s.source_refs,species_id=s.id)
    reverse={r['reaction_id']:r for r in candidate.get('reverse_map',[])}
    for reaction in n.reactions:
        rev=reverse.get(reaction.id)
        if rev is None or rev.get('source_relation_ids')!=reaction.source_relation_ids:
            conflict('REACTION_REVERSE_MAP_DISAGREES',[],reaction_id=reaction.id)
        for rid in reaction.source_relation_ids:
            addressed=relations.get(rid)
            if addressed is None or addressed.kind in {'contrast','order','repeat'}:
                conflict('REACTION_HAS_NO_APPLICABLE_SOURCE_RELATION',[],reaction_id=reaction.id,relation_id=rid)
                continue
            witnesses.append({'reaction_id':reaction.id,'source_relation_id':rid,'source_refs':addressed.source_refs,
                'target_sorts':{'reactants':'complex: N^S','products':'complex: N^S'},
                'reactants':reaction.reactants,'products':reaction.products,'grade':'C',
                'interpretation_status':'Conditional encoding of a B relation, not empirical realization.'})
    # Independently reconstruct directed source reachability from stoichiometry; supports split intermediates.
    for rel in graph.relations:
        if rel.kind not in {'sequence','condition','role'}:continue
        source=mapping.get(rel.src);target=mapping.get(rel.dst);reached={source}
        steps=[]
        for _ in n.species:
            for r in n.reactions:
                if rel.id in r.source_relation_ids and set(r.reactants)&reached:
                    reached.update(r.products);steps.append(r.id)
        if target not in reached:
            conflict('SOURCE_ORIENTATION_NOT_RETURNED',rel.source_refs,relation_id=rel.id,
                     source_species=source,target_species=target)
        else:witnesses.append({'relation_id':rel.id,'reverse_reachable':True,'reaction_path_candidates':sorted(set(steps)),
                                'source_refs':rel.source_refs})
    return {'status':'FAIL_FIDELITY' if conflicts else 'FORMAL_TRANSLATION_VALID','conflicts':conflicts,
            'reverse_witnesses':witnesses,'source_graph_sha256':digest(graph.model_dump()),
            'semantic_adequacy':'EDITORIAL_B_REQUIRES_REVIEW_NOT_MACHINE_VERIFIED_MEANING',
            'empirically_realized':'UNKNOWN','proof_status':'unverified','execution_permission':{'allowed':False}}


def repair(graph: SourceGraph, candidate: dict) -> dict:
    original=check_translation(graph,candidate)
    if not original['conflicts']:raise ValueError('NO_CONFLICT_TO_REPAIR')
    problem=original['conflicts'][0]
    if problem['reason']!='SOURCE_DISTINCTION_ERASED':raise ValueError('NO_SOURCE_GROUNDED_LOCAL_REPAIR_RULE')
    # Restore only the two independently source-addressed roles; other model choices remain intact.
    from .generator import propose
    out=propose(ProposalRequest(graph=graph,allowed_edits=['split_roles']))['candidates'][0]
    touched={r.id for r in graph.relations if set([r.src,r.dst])&set(problem['source_nodes'])}
    old_rx={r['id']:r for r in candidate['network']['reactions']}
    for r in out['network']['reactions']:
        if not set(r['source_relation_ids'])&touched:
            if r!=old_rx[r['id']]:raise ValueError('REPAIR_CHANGED_UNAFFECTED_SOURCE_RELATION')
    return {'candidate':out,'original_candidate_id':candidate['candidate_id'],'original_counterexample':deepcopy(problem),
            'original_result_retained':True,'repair_operation':'split source-distinct roles',
            'source_refs':problem['source_refs'],'untouched_relations_preserved':True,'revision':1,
            'proof_status':'unverified','execution_permission':{'allowed':False}}


def independent_apply(n: Network, op: str, x: int) -> int:
    """Arithmetic stoichiometric reference, independent of the bit-mask command implementation."""
    if op in ['Id','One','Zero']:return {'Id':x,'One':1,'Zero':0}[op]
    v=[int(b) for b in reversed(format(x,'0'+str(len(n.species))+'b'))]
    if op[0]=='S':return v[int(op[1:])]
    r=n.reactions[int(op[1:])]
    left=[r.reactants.get(s.id,0) for s in n.species];right=[r.products.get(s.id,0) for s in n.species]
    final=[a-b+c for a,b,c in zip(v,left,right)]
    possible=all(a>=b for a,b in zip(v,left)) and all(0<=a<=1 for a in final)
    if op[0]=='E':return int(possible)
    return sum(a*2**i for i,a in enumerate(final)) if possible else x


def independent_verdict(n: Network, f: Formula) -> dict:
    def evaluate(t,x):
        return x if isinstance(t,Var) else independent_apply(n,t.operation,evaluate(t.argument,x))
    def atom(e,x):return evaluate(e.left,x)==evaluate(e.right,x)
    failures=[];support=0
    for x in range(2**len(n.species)):
        p=True if isinstance(f.body,Eq) else atom(f.body.premise,x)
        c=atom(f.body if isinstance(f.body,Eq) else f.body.conclusion,x)
        support+=p
        if p and not c:failures.append(x)
    return {'status':'refuted' if failures else 'proved','counterexample_states':failures,'support':support}


def evaluate_laws(candidate: dict, max_laws: int = 24, sink: Callable | None = None) -> list[dict]:
    if not 1<=max_laws<=24:raise ValueError('LAW_SEARCH_BOUND')
    n=Network.model_validate(candidate['network']);a=Adapter(AdapterSpec(kind='reaction_network',reaction_network=n))
    formulas=[]
    for i,j in combinations(range(len(n.reactions)),2):
        lhs=Apply(operation='R'+str(j),argument=term('R'+str(i)))
        rhs=Apply(operation='R'+str(i),argument=term('R'+str(j)))
        conclusion=Eq(left=lhs,right=rhs)
        formulas.append(('commutation',Formula(body=conclusion)))
        for k in range(len(n.species)):
            for value in ['Zero','One']:
                formulas.append(('conditional_commutation',Formula(body=Implies(
                    premise=Eq(left=term('S'+str(k)),right=term(value)),conclusion=conclusion))))
    rows=[]
    for kind,f in formulas[:max_laws]:
        result=check(a,f,budget=Budget(max_states=256,deadline_ms=5000));reference=independent_verdict(n,f)
        if reference['status']!=result['status']:raise ValueError('INDEPENDENT_STOICHIOMETRIC_CHECK_DISAGREES')
        if result['counterexample'] and result['counterexample']['state'] not in reference['counterexample_states']:
            raise ValueError('COUNTEREXAMPLE_REPLAY_DISAGREES')
        if sink:sink({'candidate_id':candidate['candidate_id'],'result':result,'independent':reference})
        rows.append({'candidate_id':candidate['candidate_id'],'kind':kind,'formula':f.canonical_ast(),
            'law_id':digest(f.canonical_ast()),'status':result['status'],'nontrivial':bool(result['status']=='proved' and
                result['support']>0 and result['nontrivial_conclusion_failures']>0),
            'support':result['support'],'conclusion_failures':result['nontrivial_conclusion_failures'],
            'counterexample':result['counterexample'],'scope':result['scope'],'independent':reference,
            'derivation':'Exact enumeration of guarded stoichiometric command compositions, independently replayed.',
            'reverse_source_relations':[r.source_relation_ids for r in n.reactions],
            'new_source_law_status':'UNESTABLISHED_REQUIRES_WITHHELD_SOURCE_TEST',
            'evaluation_trace_sha256':digest(result['evaluation_trace']),'grade':'E_RELATIVE_TO_C',
            'proof_status':'unverified','execution_permission':{'allowed':False}})
    return rows


def pareto(rows: list[dict]) -> dict:
    """No scalar score; larger benefits, smaller complexity. Identical vectors remain ties."""
    frontier=[];dominated=[]
    for row in rows:
        v=row['metrics'];dominators=[]
        for other in rows:
            w=other['metrics']
            benefit=['source_fidelity','nontriviality','heldout_predictive_relation','transfer_stability','epistemic_integrity']
            at_least=all(w[k]>=v[k] for k in benefit) and w['model_complexity']<=v['model_complexity']
            strict=any(w[k]>v[k] for k in benefit) or w['model_complexity']<v['model_complexity']
            if at_least and strict:dominators.append(other['candidate_id'])
        if dominators:dominated.append({'candidate_id':row['candidate_id'],'dominated_by':dominators})
        else:frontier.append(row)
    return {'frontier':frontier,'dominated':dominated,'order':'Pareto; ties retained; no weighted sum'}
