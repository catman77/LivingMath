"""Local premises and b -> existing F/AdapterSpec. No query input or query cache."""
from davcore.ast import digest
from artifact_translation.contract import SourceGraph, ProposalRequest
from artifact_translation.generator import propose
from artifact_translation.checker import check_translation
from .contract import CompilerRequest, coordinate


def compile_model(premises: list[dict], binding: dict, *, disabled: tuple[str, ...] = (), profile: str = 'legacy007', context=None) -> dict:
    if profile != 'legacy007':
        from .realization import compile_typed
        return compile_typed(CompilerRequest.model_validate({'premises':premises, 'binding':binding, 'profile':profile}), disabled, context=context)
    request = CompilerRequest.model_validate({'premises': premises, 'binding': binding})
    ps = [p.model_dump(exclude_unset=True) for p in request.premises]
    if request.binding.project != 'LM_QA_REPAIR004':
        raise ValueError('FOREIGN_PROJECT')
    coords = sorted({coordinate(r) for p in ps for r in [p['src'], p['dst']]})
    if len(coords) > 8 or len(ps) > 12:
        return {'status': 'BOUND_INSUFFICIENT_FOR_QUERY', 'compiled_hash': digest(ps), 'coordinate_count': len(coords)}
    if not ps:
        return {'status': 'UNSUPPORTED_REPRESENTATION', 'compiled_hash': digest(ps), 'coordinate_count': 0}
    index = {r: i for i, r in enumerate(coords)}
    nodes = []
    for i, c in enumerate(coords):
        refs = sorted({ref for p in ps for r in [p['src'], p['dst']] if coordinate(r) == c for ref in p['source_refs']})
        nodes.append({'id': 'state_' + str(i), 'kind': 'predicate', 'source_refs': refs})
    relations = [{'id': p['id'], 'kind': p['relation'], 'src': 'state_' + str(index[coordinate(p['src'])]),
                  'dst': 'state_' + str(index[coordinate(p['dst'])]), 'source_refs': p['source_refs'], 'grade': 'B'} for p in ps]
    graph = SourceGraph.model_validate({'id': 'local_' + digest(ps)[:24], 'nodes': nodes, 'relations': relations})
    candidate = propose(ProposalRequest(graph=graph, allowed_edits=['catalytic']))['candidates'][0]
    reverse = check_translation(graph, candidate)
    if reverse['status'] != 'FORMAL_TRANSLATION_VALID':
        raise ValueError('EXISTING_SOURCE_REVERSE_CHECK_FAILED')
    inactive_ids=[]
    for p, reaction in zip(ps, candidate['network']['reactions']):
        inactive = any(request.binding.assignments.get(k) != v for k, v in (p.get('requires_binding') or {}).items())
        if inactive: inactive_ids.append(p['id'])
        if p['id'] in disabled or inactive:
            reaction['products'] = dict(reaction['reactants'])
    spec = {'kind': 'reaction_network', 'reaction_network': candidate['network']}
    semantics = {'spec': spec, 'premise_ids': [p['id'] for p in ps], 'coordinates': [list(c) for c in coords],
                 'source_hashes': sorted({p['source_hash'] for p in ps}),
                 'observer': '|'.join(sorted({p['observer_version'] for p in ps})),
                 'disabled_premises': sorted(disabled)}
    return {**semantics, 'status': 'COMPILED_CONDITIONAL_MODEL', 'compiled_hash': digest(semantics),
            'coordinate_count': len(coords), 'source_graph': graph.model_dump(), 'candidate': candidate,
            'inactive_premise_ids':inactive_ids,
            'coordinate_index': {digest(list(c)): i for c, i in index.items()}, 'reverse_check': reverse,
            'binding_id': request.binding.id, 'compiler_received_query': False,
            'mention_coordinate_bindings': [{'mention_id': r['mention_ref'], 'event_role': r['predicate'],
                'state_coordinate': 'v'+str(index[coordinate(r)]), 'stage': r['stage'], 'scope': r['scope'],
                'entity_coordinate_quotient': False} for p in ps for r in [p['src'], p['dst']]],
            'reverse_check_scope': 'Original source template; any disabled premise is explicitly withdrawn for deletion testing.',
            'losses': ['State coordinates denote scoped predicates, not entity identity.',
                       'Mentions and referent/sense assignments stay in H; no automatic species quotient.',
                       'Prescriptive/lyrical relations are conditional model premises, never measured effects.'],
            'proof_status': 'unverified', 'execution_permission': {'allowed': False}}


def compile_family(premises: list[dict], family: dict, dimensions: list[dict]) -> dict:
    """Assignments must have an effect path or an explicit projection limit."""
    from davcore.adapters import Adapter, AdapterSpec
    from .search import generate_queries
    unique: dict[str,dict]={}; branches=[]; tables: dict[str,dict]={}; effects=[]
    for b in family['bindings']:
        model=compile_model(premises,b)
        key=model['compiled_hash']
        if key not in unique:
            unique[key]=model
            if model['status']=='COMPILED_CONDITIONAL_MODEL':
                adapter=Adapter(AdapterSpec.model_validate(model['spec']))
                tables[key]={'states':list(adapter.states()),'operations':{
                    op:[adapter.apply(op,s) for s in adapter.states()] for op in adapter.ops}}
        branches.append({'binding':b,'model_hash':key,'queries':generate_queries(premises,model)})
    for d in dimensions:
        affected=[p['id'] for p in premises if d['id'] in (p.get('requires_binding') or {})]
        status='REALIZED_IN_MODEL' if affected else 'SOURCE_ONLY_NOT_TARGET_REALIZED'
        witnesses=[]
        for i,a in enumerate(branches):
            for b in branches[i+1:]:
                aa=a['binding']['assignments'];bb=b['binding']['assignments']
                if aa.get(d['id'])==bb.get(d['id']) or any(aa.get(k)!=bb.get(k) for k in aa if k!=d['id']):continue
                left=tables.get(a['model_hash']);right=tables.get(b['model_hash'])
                if left is None or right is None:continue
                difference=next(({'operation':op,'state':s,'outputs':[xs[j],right['operations'][op][j]]}
                    for op,xs in left['operations'].items() for j,s in enumerate(left['states'])
                    if xs[j]!=right['operations'][op][j]),None)
                witnesses.append({'bindings':[a['binding']['id'],b['binding']['id']],
                    'kind':'DISTINGUISHING_EXECUTION' if difference else 'EXHAUSTIVE_TARGET_PROJECTION_EQUIVALENCE',
                    'witness':difference,'states_checked':len(left['states']),'operations_checked':len(left['operations'])})
        if not affected and d.get('kind')=='irrelevant' and witnesses and all(w['witness'] is None for w in witnesses):
            status='IRRELEVANT_TO_THIS_QUERY'
        effects.append({'dimension':d,'status':status,'affected_premises':affected,'execution_witnesses':witnesses,
            'source_selection_resolved':False,'reason':'requires_binding changes a command' if affected else
                'Role/interpretation choice is not represented by this target projection; no claim of resolving it.'})
    return {'models':list(unique.values()),'branches':branches,'binding_effects':effects,
            'execution_tables':tables,'distinct_target_models':sum(m['status']=='COMPILED_CONDITIONAL_MODEL' for m in unique.values()),'source_binding_count':len(branches)}
