"""Bounded structural proposals. No corpus words, Gate IDs, evaluator or hidden data."""
from copy import deepcopy
from typing import Any
from davcore.ast import digest
from .contract import ProposalRequest
from .network import Network, fire


def semantic_fingerprint(candidate: dict) -> str:
    """Exact observation/continuation relation, anchored by source order, ignoring labels.

    Hidden markings with identical observed continuations collapse; AST/JSON names are not
    the equivalence criterion. This quotient is a dedup key, never a congruence assertion.
    """
    n=Network.model_validate(candidate['network']);mapping=candidate['mapping']
    anchors=[mapping[x] for x in candidate['source_order']]
    positions={s.id:i for i,s in enumerate(n.species)}
    def observe(x):return tuple((x>>positions[s])&1 for s in anchors)
    table: dict[tuple,set[tuple]]={}
    for x in range(2**len(n.species)):
        row=tuple(observe(fire(n,j,x)) for j in range(len(n.reactions)))
        table.setdefault(observe(x),set()).add(row)
    return digest(sorted((key,sorted(values)) for key,values in table.items()))


def _build(request: ProposalRequest, edit: str) -> dict | None:
    g=request.graph
    species: list[dict[str,Any]]=[{'id':'v'+str(i),'label':'symbol_'+str(i),'source_refs':n.source_refs,
              'provenance_kind':'symbolic_species'} for i,n in enumerate(g.nodes)]
    mapping={n.id:species[i]['id'] for i,n in enumerate(g.nodes)}
    losses=[];assumptions=['Text relation orientation is a conditional symbolic interpretation, not physical time.',
                            'All binary initial markings; explicit capacity-one guard; no kinetic law.']
    critical=next((r for r in g.relations if r.kind=='contrast'),
                  next((r for r in g.relations if r.kind=='role'),None))
    if edit=='merge_roles':
        if critical is None:return None
        mapping[critical.dst]=mapping[critical.src]
        source_refs={ref for node in g.nodes if node.id in {critical.src,critical.dst} for ref in node.source_refs}
        next(s for s in species if s['id']==mapping[critical.src])['source_refs']=sorted(source_refs)
        losses.append({'source_relation_id':critical.id,'kind':'ROLE_COLLAPSE','status':'UNRESOLVED',
                       'source_nodes':[critical.src,critical.dst],'target_species':mapping[critical.src],
                       'reason':'Adversarial many-to-one mapping erases a declared distinction.'})
    reactions: list[dict[str,Any]]=[]
    for rel in g.relations:
        if rel.kind in {'contrast','order','repeat'}:
            losses.append({'source_relation_id':rel.id,'kind':'METARELATION_NOT_KINETIC_REACTION',
                           'status':'RETAINED_IN_SOURCE_GUARD','reason':'Textual distinction/order is not a measured transition.'})
            continue
        a,b=mapping[rel.src],mapping[rel.dst]
        if edit=='reverse_orientation':a,b=b,a
        products={b:1}
        if edit in {'catalytic','latent_guard'}:products[a]=1
        reactions.append({'id':'reaction_'+str(len(reactions)),'reactants':{a:1},'products':products,
                          'source_relation_ids':[rel.id]})
    if not reactions:return None
    if edit in {'latent_guard','split_intermediate'}:
        if len(species)>=8 or len(reactions)>=12:return None
        rel=next(r for r in g.relations if r.id==reactions[0]['source_relation_ids'][0])
        extra='aux'+str(len(species))
        species.append({'id':extra,'label':'unidentified_symbolic_coordinate','source_refs':rel.source_refs,
                        'provenance_kind':'symbolic_species'})
        if edit=='latent_guard':
            for reaction in reactions:
                reaction['reactants'][extra]=1;reaction['products'][extra]=1
            assumptions.append('C: additional unobserved prerequisite is a competing hypothesis, UNKNOWN in the source.')
        else:
            first=reactions[0];target=first['products'];first['products']={extra:1}
            reactions.append({'id':'reaction_'+str(len(reactions)),'reactants':{extra:1},'products':target,
                              'source_relation_ids':first['source_relation_ids']})
            assumptions.append('C: a symbolic intermediate is an optional refinement, not an attested physical entity.')
    network=Network.model_validate({'species':species,'reactions':reactions})
    c={'source_graph_id':g.id,'source_graph_sha256':digest(g.model_dump()),'source_order':[n.id for n in g.nodes],
       'edit':edit,'network':network.model_dump(),'mapping':mapping,'loss_ledger':losses,'assumptions':assumptions,
       'reverse_map':[{'reaction_id':r.id,'source_relation_ids':r.source_relation_ids,
                       'grade':'C','explanation':'Conditional target encoding of the addressed editorial relation.'} for r in network.reactions],
       'grades':{'source_attestation':'A','relation_annotation':'B','network':'C','conditional_consequences':'E',
                 'empirical_world':'F:UNKNOWN'},'empirically_realized':'UNKNOWN',
       'unknowns':['modern chemical identities','rates','physical time','physical realization'],
       'proof_status':'unverified','execution_permission':{'allowed':False}}
    c['candidate_id']=digest(c)
    return c


def propose(request: ProposalRequest) -> dict:
    rows=[];seen: dict[str,str]={};duplicates=[];considered=0
    for edit in request.allowed_edits:
        if considered>=request.max_candidates:break
        considered+=1;c=_build(request,edit)
        if c is None:continue
        key=semantic_fingerprint(c)
        if key in seen:
            duplicates.append({'edit':edit,'equivalent_to':seen[key],'observed_semantics_sha256':key})
            continue
        c['observed_semantics_sha256']=key;seen[key]=c['candidate_id'];rows.append(c)
    return {'candidates':rows,'duplicates':duplicates,'considered':considered,
            'search_status':'SEARCH_EXHAUSTED','search_space':{'edits':request.allowed_edits,
                'max_candidates':request.max_candidates,'exhausted_full_declared_edit_list':considered==len(request.allowed_edits),
                'scope':'Only this finite edit family; no claim of universal search completeness.'},
            'worker_input_contains_only':'source relation identifiers, types, references and budget',
            'proof_status':'unverified','execution_permission':{'allowed':False}}


def rename_symbols(candidate: dict) -> dict:
    out=deepcopy(candidate);mapping={s['id']:'alpha_'+str(i) for i,s in enumerate(out['network']['species'])}
    for s in out['network']['species']:s['id']=mapping[s['id']];s['label']='unrelated_'+s['id']
    for r in out['network']['reactions']:
        for side in ['reactants','products']:r[side]={mapping[k]:v for k,v in r[side].items()}
    out['mapping']={k:mapping[v] for k,v in out['mapping'].items()}
    return out
