"""Versioned compilation to the existing capacity-one Network; no query imports."""
from itertools import product

from artifact_translation.network import Network
from davcore.ast import digest

from .contract import CompilerRequest, coordinate

PROFILE = 'typed008/1'
OBSERVER = 'typed-observer008/1'


def compile_typed(request: CompilerRequest, disabled: tuple[str,...] = (), *, context=None) -> dict:
    if request.profile!=PROFILE or context is None and request.binding.project!='LM_QA_REPAIR004':
        raise ValueError('TYPED_PROFILE_PROJECT_REQUIRED')
    ps=[p.model_dump(exclude_unset=True) for p in request.premises]
    if context is not None:context.require(request.binding.project,ps)
    if not ps or any(not p.get('realization') for p in ps):
        raise ValueError('ADDRESSED_REALIZATION_REQUIRED')
    if len({p['id'] for p in ps})!=len(ps) or set(disabled)-{p['id'] for p in ps}:
        raise ValueError('DUPLICATE_OR_FOREIGN_PREMISE')
    if len({(p['source_hash'],r['scope'],r.get('domain')) for p in ps for r in (p['src'],p['dst'])})!=1:
        raise ValueError('CROSS_SOURCE_SCOPE_REALIZATION')
    b=request.binding.assignments
    species: list[dict]=[]
    reactions: list[dict]=[]
    mapping: list[dict]=[]
    guards: list[dict]=[]
    assumptions: list[str]=[]
    observer: dict
    kinds={p['realization']['kind'] for p in ps}
    if kinds == {'STATE_TRANSITION'}:
        if ps[0]['realization']['transition']['version'] == 'source-transition012/1':
            from .realization012 import compile_semantics
            return compile_semantics(request, ps, disabled, context)
        from .realization011 import compile_transitions
        return compile_transitions(request, ps, disabled, context)

    def node(key, label, refs):
        existing=next((i for i,s in enumerate(species) if s['id']==key),None)
        if existing is not None:
            species[existing]['source_refs']=sorted(set(species[existing]['source_refs']+refs));return existing
        species.append({'id':key,'label':label[:120],'source_refs':sorted(set(refs))});return len(species)-1

    def reaction(p, reactants, products):
        if p['id'] in disabled or any(b.get(k)!=v for k,v in (p.get('requires_binding') or {}).items()):
            products=reactants.copy()
        reactions.append({'id':p['id'],'reactants':{species[i]['id']:1 for i in reactants},
            'products':{species[i]['id']:1 for i in products},'source_relation_ids':[p['id']]})

    if kinds=={'GUARDED_TRANSFORMATION'}:
        if set(b)!={'update_mode','middle_policy'} or b['update_mode'] not in {'REPLACE','ACCUMULATE'} or b['middle_policy'] not in {'LINK_LOCAL_ROLE','SEPARATE_OCCURRENCES'}:
            raise ValueError('GUARDED_INTERPRETATION_REQUIRED')
        linked=b['middle_policy']=='LINK_LOCAL_ROLE'; mode=b['update_mode']
        roles=[]
        for p in ps:
            pair=[]
            for r in (p['src'],p['dst']):
                # Explicit conditional quotient, never a change to legacy stage
                # or coordinate(). Guard and stage remain in the reverse map.
                identity=list(coordinate(r))
                if linked:identity[2]='CONDITIONAL_ROLE_WITH_SEPARATE_GUARDS'
                key='role_'+digest(identity)[:24]
                i=node(key,r['predicate'],p['source_refs']);pair.append(i)
                mapping.append({'source_role':r,'legacy_coordinate':list(coordinate(r)),'target_coordinate':i,
                    'basis':'CONDITIONAL_LOCAL_ROLE_QUOTIENT' if linked else 'EXACT_SCOPED_ROLE',
                    'entity_identity':False})
            roles.append(pair)
        for p,(a,c) in zip(ps,roles):
            gs=[]
            for g in p['realization']['guards']:
                if not set(g['source_refs'])<=set(p['source_refs']):raise ValueError('UNADDRESSED_GUARD')
                i=node(g['id'],g['text'],g['source_refs']);gs.append(i)
                guards.append({**g,'coordinate':i,'premise_id':p['id']})
            if not gs:raise ValueError('GUARDED_TRANSFORMATION_WITHOUT_GUARD')
            reaction(p,[a,*gs],list(dict.fromkeys(([a,c] if mode=='ACCUMULATE' else [c])+gs)))
        roots=sorted({x[0] for x in roles}-{x[1] for x in roles})
        # Local fixture initial conditions: the first addressed input only;
        # independent guard valuations are registered before any query.
        root=roles[0][0]
        initials=[(1<<root)+sum(v<<g['coordinate'] for v,g in zip(vals,guards)) for vals in product((0,1),repeat=len(guards))]
        observer={'kind':'GUARDED_TRANSFORMATION','role_pairs':roles,'guard_coordinates':[g['coordinate'] for g in guards]}
        assumptions=['Initial first input is present; other inputs/products absent; each textual guard is independently assumed or absent.',
            'Update interpretation '+mode+' is conditional, not a claim about matter.']
        if linked:assumptions.append('Same scoped predicate roles may connect across distinct guards; this is not substance identity.')
        interface={'uninitialized_roots':roots[1:],'global_composition_verified':False}
    else:
        if not kinds<={'NARRATIVE_OCCURRENCE','PRESCRIPTION','SIGNED_ASSERTION'} or ('SIGNED_ASSERTION' in kinds and len(kinds)>1):
            raise ValueError('MIXED_REALIZATION_REQUIRES_LOCAL_SLICE')
        signed=kinds=={'SIGNED_ASSERTION'}
        expected={'response_subject'} if signed else {'narrative_referent','story_time'}
        if set(b)!=expected or any(v not in {'CONTINUED_SUBJECT','OTHER_PARTICIPANT'} for k,v in b.items() if k!='story_time') or b.get('story_time','NARRATED_ORDER') not in {'NARRATED_ORDER','PHYSICAL_TIME_UNKNOWN'}:
            raise ValueError('TEXTUAL_INTERPRETATION_REQUIRED')
        # Caller order is source presentation order, not physical chronology.
        refs=sorted({r for p in ps for r in p['source_refs']})
        cursor=[node('cursor_'+str(i),'read prefix '+str(i),refs) for i in range(len(ps)+1)]
        tokens={}
        for label in (['incoming','outgoing','back_positive','back_negative'] if signed else ['prescribed','performed']):
            tokens[label]=node(label,label,refs)
        prescribed_seen=False
        for i,p in enumerate(ps):
            r=p['realization'];extra=[]
            if signed:
                if r['direction']=='INCOMING':
                    if r['sign']!='POSITIVE':raise ValueError('NEGATIVE_INPUT_NOT_SUPPORTED_IN_THIS_SLICE')
                    extra=[tokens['incoming']]
                elif r['direction']=='FORWARD':
                    if r['sign']!='POSITIVE':raise ValueError('NEGATIVE_FORWARD_REQUIRES_OWN_SIGNED_SLICE')
                    extra=[tokens['outgoing']]
                elif r['direction']=='BACK_TO_ADDRESSEE' and r['sign'] in {'POSITIVE','NEGATIVE'}:
                    extra=[tokens['back_positive' if r['sign']=='POSITIVE' else 'back_negative']]
                else:raise ValueError('SIGNED_DIRECTION_SIGN_REQUIRED')
            reactants=[cursor[i]]
            if not signed and r['kind']=='PRESCRIPTION':
                extra=[tokens['prescribed']]
                if prescribed_seen:reactants.append(tokens['prescribed'])
                prescribed_seen=True
            reaction(p,reactants,[cursor[i+1],*extra])
            mapping.append({'occurrence_id':r['occurrence_id'],'source_role':p['src'],
                'legacy_coordinate':list(coordinate(p['src'])),'cursor_transition':[i,i+1],
                'source_refs':p['source_refs'],'event_is_reading':True})
        initials=[1<<cursor[0]]
        observer={'kind':'SIGNED_RESPONSE' if signed else 'TEXTUAL_PROGRESSION','tokens':tokens,
            'cursor_coordinates':cursor,'occurrences':[p['realization']['occurrence_id'] for p in ps],
            'response_subject':b.get('response_subject'),
            'same_original_addressee':b.get('response_subject')=='CONTINUED_SUBJECT'}
        assumptions=['Cursor tracks presentation of addressed source occurrences, not a physical mechanism.',
            'No positive attestation is inferred from absence of its negative (and conversely).',
            'Story time and participant identity are not settled by source address order.']
        if signed:assumptions.append('Continuation of the subject across source packets is a candidate binding, never a FACT; analogy does not identify the poet.')
        interface={'other_slices_joined':False,'global_composition_verified':False}
    if len(species)>8 or len(reactions)>12 or len(guards)>4:
        return {'status':'BOUND_INSUFFICIENT_FOR_QUERY','profile':PROFILE,'coordinate_count':len(species),
            'compiled_hash':digest(ps),'losses':['Split source into addressed local slices; no silent truncation.']}
    network=Network.model_validate({'species':species,'reactions':reactions}).model_dump()
    semantics={'profile':PROFILE,'observer_version':OBSERVER,'spec':{'kind':'reaction_network','reaction_network':network},
        'premise_ids':[p['id'] for p in ps],'source_hashes':sorted({p['source_hash'] for p in ps}),
        'source_premises_hash':digest(ps),'binding_assignments':b,'disabled_premises':list(disabled),
        'initial_states':sorted(set(initials)),'observer':observer,'role_map':mapping,'guards':guards,
        'assumptions':assumptions,'interface':interface}
    if context is not None:semantics['source_context']=context.public()
    return {**semantics,'status':'COMPILED_CONDITIONAL_MODEL','compiled_hash':digest(semantics),
        'target_projection_hash':digest({'spec':semantics['spec'],'observer':observer}),
        'coordinate_count':len(species),'compiler_received_query':False,'proof_status':'unverified',
        'execution_permission':{'allowed':False},'losses':['Symbolic source reading only; no chemical, physiological or universal literary truth.']}


def observe_state(model: dict, state: int) -> dict:
    o=model['observer']
    if not 0<=state<1<<model['coordinate_count']:raise ValueError('INVALID_STATE_SORT')
    if o['kind'] == 'SOURCE_SEMANTICS012':
        from .realization012 import observe
        return observe(model, state)
    if o['kind'] == 'SOURCE_TRANSITION':
        from .realization011 import observe_transition
        return observe_transition(model, state)
    if o['kind']=='GUARDED_TRANSFORMATION':
        return {'roles':[(state>>i)&1 for i in range(model['coordinate_count']) if i not in o['guard_coordinates']],
            'guards':[(state>>i)&1 for i in o['guard_coordinates']]}
    tokens={k:(state>>i)&1 for k,i in o['tokens'].items()}
    cursors=[i for i,c in enumerate(o['cursor_coordinates']) if (state>>c)&1]
    result={'tokens':tokens,'read_prefix':cursors[0] if len(cursors)==1 else 'INVALID_OR_NONCURSOR_MARKING'}
    if o['kind']=='SIGNED_RESPONSE':
        pair=(tokens['back_positive'],tokens['back_negative'])
        result.update(back_status={(0,0):'UNKNOWN',(1,0):'POSITIVE',(0,1):'NEGATIVE',(1,1):'CONFLICT'}[pair],
            outgoing_any_actor=bool(tokens['outgoing']),
            outgoing_for_original_addressee='ATTESTED_UNDER_BINDING' if tokens['outgoing'] and o['same_original_addressee'] else 'UNKNOWN')
    else:
        result.update(prescription='ATTESTED' if tokens['prescribed'] else 'UNKNOWN',
            performance='ATTESTED' if tokens['performed'] else 'UNKNOWN')
    return result
