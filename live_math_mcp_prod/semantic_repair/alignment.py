"""Local, directed source correspondence; not word equality or a new solver.

CODE_AGENT_PROPOSAL grammar/resources. Observation has no query/model input.
Verification re-reads bases. Source signatures carry no formal proof badge;
the existing DAV finite engine separately checks explicit K/C_a projections.
"""
import json
import re
from typing import Any

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from .observe import norm
from .scoped import Claim

VERSION = 'local-alignment007/1'
STRATEGY = 'alignment-frames006/1'
CONTEXT_STRATEGY = 'alignment-context007/1'
LEXICAL_RESOURCE: dict[str,Any] = {'version':'sound-inflection006/1', 'authorship':'CODE_AGENT_PROPOSAL',
    'scope':'Candidate Russian sound inflection only, not a semantic equality oracle.',
    'forms':{'громов':'гром', 'грома':'гром', 'звука':'звук', 'звуков':'звук'},
    'exceptions':'No animal/horn/maiden correspondence inferred from thunder; no reply/echo global synonymy.'}


def observe(packet: RawPacket, *, strategy: str = STRATEGY) -> dict:
    if strategy not in {STRATEGY,CONTEXT_STRATEGY}:
        raise ValueError('UNREGISTERED_ALIGNMENT_STRATEGY')
    spans = packet.spans + packet.context; frames = []; definitions = []
    contexts={};quoted=False
    for span in spans:
        t=span.text.strip()
        if t.startswith(('«','"')):quoted=True
        contexts[span.id]='QUOTED_OR_REPORTED' if quoted else 'ASSERTED_LOCAL'
        if quoted and t.endswith(('»','"')):quoted=False
    section = spans[0].source_address.get('section',packet.document_id)
    scope = 's_'+digest([packet.document_sha256,packet.edition,section])[:24]
    domain = 'local_domain_'+digest([packet.document_sha256,packet.edition,section])[:20]

    def add(stimulus, output, refs, actor, quantifier, time, polarity='POSITIVE', direction='FORWARD', stimulus_actor=None):
        output_predicate=norm(output)
        if packet.language=='ru':
            m=re.search(r'\bшлешь\s+(\w+)',output,re.I)
            n=re.search(r'\bсвой\s+(\w+)',output,re.I)
            if m:output_predicate=norm(m[1])
            elif n:output_predicate=norm(n[1])
            negative_back=re.search(r'\bнет\s+(\w+)',output,re.I)
            if direction=='BACK_TO_ADDRESSEE' and negative_back:output_predicate=norm(negative_back[1])
        row = {'stimulus':norm(stimulus), 'output':norm(output), 'actor':norm(actor),
            'output_predicate':output_predicate,'input_polarity':'POSITIVE','discourse':'ASSERTED_LOCAL',
            'stimulus_actor':norm(stimulus_actor or actor),
            'recipient':'local_environment' if direction=='FORWARD' else norm(actor),
            'direction':direction, 'quantifier':quantifier, 'time':time, 'polarity':polarity,
            'modality':'TEXTUAL_CLAIM' if packet.language=='en' else 'LYRICAL_CLAIM',
            'domain':domain,'scope':scope,'source_hash':packet.document_sha256,'edition':packet.edition,
            'source_refs':sorted({s.id for s in refs}), 'assurance':'SOURCE_LOCAL_READING',
            'observer':strategy,'mention_ids':['mention_'+digest([s.id,actor,direction])[:20] for s in refs]}
        row['occurrence_id']='occ_'+digest([packet.document_sha256,row['source_refs'],row['stimulus'],row['output'],direction])[:24]
        if any(contexts[s.id]=='QUOTED_OR_REPORTED' for s in refs):
            row['discourse']='QUOTED_OR_REPORTED';row['modality']='REPORTED_SPEECH'
        if quantifier=='NAMED_CASE': row['witness_id']=row['occurrence_id']
        row['frame_id']='frame_'+digest(row)[:24]; frames.append(row)

    # Natural-language local definitions are data about this passage, not code
    # or instructions to execute. This deliberately limited grammar calibrates
    # source-backed transport without declaring global word equivalence.
    for s in spans:
        m=re.fullmatch(r'Here,? (\w+) means (\w+)[.]?',s.text.strip(),re.I)
        if m:
            definitions.append({'from':norm(m[1]),'to':norm(m[2]),'source_refs':[s.id],
                'basis_kind':'SOURCE_LOCAL_PARSE','direction':'FORWARD','scope':scope})
        m=re.fullmatch(r'(Whenever|When) (?:a |an )?(\w+) reaches (\w+), (\w+) (does not send|sends) (?:a |an )?(\w+)[.]?',s.text.strip(),re.I)
        if m:
            add(m[2],m[6],[s],m[4],'ALL' if m[1].casefold()=='whenever' else 'NAMED_CASE',
                'GENERIC' if m[1].casefold()=='whenever' else 'EVENT',
                polarity='NEGATIVE' if m[5].casefold()=='does not send' else 'POSITIVE',
                stimulus_actor=m[3])
    # Rhetorical local enumeration, generic in nouns and number of listed cases.
    j=next((i for i,s in enumerate(spans) if re.search(r'на всякий \w+',s.text,re.I)),None)
    if j is not None and j>0 and any(re.search(r'\bли\b',s.text,re.I) for s in spans[:j]):
        tail=spans[j+1:]
        if any(re.search(r'\bты\b',s.text,re.I) for s in tail):
            for s in spans[:j]:
                for item in re.split(r'[,;]',s.text):
                    if re.search(r'\bли\b',item,re.I):
                        add(item,' '.join(t.text for t in tail),[s,*spans[j:]],
                            'local_second_person','ALL','CONDITIONAL_SCHEMA')
    # Auditory input + sending a response. The intervening list is preserved;
    # the later analogy is a boundary, not an identity assertion about the actor.
    for i,s in enumerate(spans):
        m=re.match(r'^\s*(Ты|Он|Она) внемлешь? (.+)',s.text,re.I)
        if not m: continue
        end=next((k for k in range(i+1,len(spans)) if re.search(r'\b(?:не )?шлешь\b',spans[k].text,re.I)),None)
        if end is None: continue
        output=spans[end].text; inputs=[m[2]]
        inputs += [re.sub(r'^\s*И\s+','',x.text,flags=re.I) for x in spans[i+1:end]]
        actor='local_second_person' if m[1].casefold()=='ты' else norm(m[1])
        sender = re.match(r'^\s*(Ты|Он|Она)\b', output, re.I)
        response_actor = (('local_second_person' if sender[1].casefold() == 'ты' else norm(sender[1]))
                          if sender else actor)
        for stimulus in inputs:
            if re.search(r'\b(?:Таков|как)\b',stimulus,re.I):continue
            add(stimulus,output,spans[i:end+1],response_actor,'UNKNOWN','PRESENT_GNOMIC_OR_EVENT',
                polarity='NEGATIVE' if re.search(r'\bне шлешь',output,re.I) else 'POSITIVE',
                stimulus_actor=actor)
    for s in spans:
        if re.search(r'нет (?:отзыва|ответа)',s.text,re.I):
            add('incoming reply',s.text,[s],'local_second_person','NAMED_CASE','PRESENT_GNOMIC_OR_EVENT',
                polarity='NEGATIVE',direction='BACK_TO_ADDRESSEE')
    occurrences=[{'id':f['occurrence_id'],'source_refs':f['source_refs'],'subject':f['actor'],
        'arguments':{'input_subject':f['stimulus_actor'],'recipient':f['recipient']},'polarity':f['polarity'],
        'modality':f['modality'],'time':f['time'],'discourse':f['discourse'],'frame_alternatives':[f['frame_id']]} for f in frames]
    return {'observer':strategy,'source_packet':packet.model_dump(),'frames':frames,'definitions':definitions,
        'context_readings':[{'frame_id':f['frame_id'],'head':stimulus_head(f['stimulus']),
            'temporal_alternatives':['GNOMIC','EVENT'] if f['time']=='PRESENT_GNOMIC_OR_EVENT' else [f['time']],
            'basis_refs':f['source_refs'],'assurance':'CODE_AGENT_LOCAL_HYPOTHESIS_NOT_SOURCE_FACT'} for f in frames]
            if strategy==CONTEXT_STRATEGY else [],
        'occurrences':occurrences,'capabilities':['Addressed conditional input/output','Separate event roles/signs',
            'Local directed lexical definitions','Finite rhetorical enumeration','Auditory list/response','Negative back-response'],
        'analogy_boundaries':[s.id for s in spans if re.search(r'Таков|как\b',s.text,re.I)],
        'unparsed_refs':[s.id for s in spans if not any(s.id in f['source_refs'] for f in frames)],
        'query_received':False,'model_proof_received':False,'authorship':'CODE_AGENT_PROPOSAL_GENERIC_GRAMMAR'}


def claim_for_frame(frame: dict) -> Claim:
    return Claim(predicate='CONDITIONAL_RELATION',subject='p_'+digest(frame['stimulus'])[:24],
        object='p_'+digest(frame['output'])[:24],domain=frame['domain'],quantifier=frame['quantifier'],
        polarity=frame['polarity'],modality=frame['modality'],time=frame['time'],stage='SCHEMATIC',
        scope=frame['scope'],source_hash=frame['source_hash'],edition=frame['edition'],
        participant=frame['actor'], stimulus_participant=frame['stimulus_actor'],
        recipient=frame['recipient'], direction=frame['direction'],witness_id=frame.get('witness_id'),
        input_polarity=frame.get('input_polarity'),discourse=frame.get('discourse'))


def request(frame: dict, claim: Claim, query_id: str, proposal_packet: RawPacket) -> dict:
    expected=claim_for_frame(frame)
    # Legacy q_s has no role slots. Keep it explicitly incomplete, never exact.
    skipped = {'assumptions','display'} | {k for k in ('participant','stimulus_participant','recipient','direction','witness_id','input_polarity','discourse')
                                         if getattr(claim,k) is None}
    if claim.model_dump(exclude=skipped)!=expected.model_dump(exclude=skipped):
        raise ValueError('SOURCE_CLAIM_FRAME_SIGNATURE_MISMATCH')
    return {'q_s_id':claim.identity(),'q_s':claim.model_dump(mode='json'),'q_t_id':query_id,'source_frame':frame,'version':VERSION,
        'proposal_packet':proposal_packet.model_dump(),
        'translation_binding':{'source_frame_id':frame['frame_id'],'target_query_id':query_id,
            'losses':['Finite proof does not attest predicate, role or temporal correspondence.'],
            'source_to_target_is_conditional':True}}


def _words(text):
    return {LEXICAL_RESOURCE['forms'].get(w,w) for w in re.findall(r'\w+',text.casefold())}


def candidates(req: dict, observed: dict, *, bound: int = 32) -> dict:
    if not 1<=bound<=32: raise ValueError('ALIGNMENT_CANDIDATE_BOUND')
    a=req['source_frame']; output=[]
    for b in observed['frames']:
        # Retrieval relevance is lexical input overlap, never a proof outcome.
        overlap=sorted(_words(a['stimulus']) & _words(b['stimulus']))
        if not overlap: continue
        # Positive evidence V requires V=>S. Negative evidence not-V can
        # transport to not-S only with S=>V (contraposition). Polarity selects
        # an entailment direction, never the desired support/refutation label.
        origin, destination = ((b['output'], a['output']) if b['polarity']=='POSITIVE'
                               else (a['output'], b['output']))
        defs=[d for d in observed['definitions'] if d['from']==origin and d['to']==destination]
        same=a['output']==b['output']
        explicit=bool(defs or same)
        readings=[('EXPLICIT_LOCAL','KEEP_TIME','KEEP_ACTOR')] if explicit else [
            ('PARALLEL_RESPONSE','GNOMIC','SAME_LOCAL_ACTOR'),
            ('PARALLEL_RESPONSE','EVENT','SAME_LOCAL_ACTOR'),
            ('PARALLEL_RESPONSE','GNOMIC','DISTINCT_ACTOR'),
            ('LITERAL_PREDICATES','KEEP_TIME','KEEP_ACTOR')]
        for predicate,time,actor in readings:
            refs=sorted(set(a['source_refs']+b['source_refs']+[r for d in defs for r in d['source_refs']]))
            body={'version':VERSION,'q_s_id':req['q_s_id'],'q_t_id':req['q_t_id'],
                'source_frame_id':a['frame_id'],'validation_frame_id':b['frame_id'],
                'ordered_predicates':[a['output'],b['output']], 'predicate_reading':predicate,
                'time_reading':time,'participant_reading':actor,'input_overlap':overlap,
                'domain_map':[a['domain'],b['domain']], 'source_scope':[a['scope'],b['scope']],
                'basis_refs':refs,'basis_kind':'SOURCE_LOCAL_PARSE' if explicit else 'RESEARCH_HYPOTHESIS',
                'assumptions':[] if explicit else ['Parallel response descriptions are locally aligned.',
                    'Gnomic time and same local addressee are candidates, not source facts.'],
                'applicability':'Only these ordered source frames and input overlap; no reciprocity or global synonymy.',
                'lexical_resource_version':LEXICAL_RESOURCE['version']}
            body['id']='a_'+digest(body)[:24];output.append(body)
    return {'candidates':output[:bound],'total':len(output),'truncated':len(output)>bound,
        'complete_within_registered_search':len(output)<=bound,'version':digest(output),
        'not_complete_human_interpretations':True,'selection':'All relevant registered readings, no DAV/q truth ranking.'}


def verify(req: dict, observed: dict, candidate: dict, *, disabled_basis: tuple[str,...] = ()) -> dict:
    # Re-observe exact raw bytes and regenerate membership. A signed arbitrary
    # mapping or a fabricated observation record is not an admissible basis.
    raw=RawPacket.model_validate(observed['source_packet']); canonical=observe(raw,strategy=observed['observer'])
    if canonical!={k:v for k,v in observed.items() if k!='isolation'}:
        raise ValueError('OBSERVATION_OR_SOURCE_BINDING_DRIFT')
    proposal=observe(RawPacket.model_validate(req['proposal_packet']))
    if req['source_frame'] not in proposal['frames']:
        raise ValueError('PROPOSAL_FRAME_OR_SOURCE_BINDING_DRIFT')
    claimed=Claim.model_validate_json(json.dumps(req['q_s']))
    rebuilt=request(req['source_frame'],claimed,req['q_t_id'],RawPacket.model_validate(req['proposal_packet']))
    if req!=rebuilt:raise ValueError('CLAIM_TRANSLATION_BINDING_DRIFT')
    registered=candidates(req,canonical)['candidates']
    if candidate not in registered: raise ValueError('UNREGISTERED_OR_MUTATED_CORRESPONDENCE')
    a=req['source_frame'];b=next(f for f in canonical['frames'] if f['frame_id']==candidate['validation_frame_id'])
    reasons=[]
    if set(disabled_basis)&set(candidate['basis_refs']): reasons.append('ALIGNMENT_BASIS_REMOVED')
    for key in ['source_hash','edition','scope','domain','direction','recipient','modality','input_polarity','discourse']:
        if a[key]!=b[key]: reasons.append(key.upper()+'_MISMATCH')
    if a['actor']!=b['actor'] or a['stimulus_actor']!=b['stimulus_actor'] or candidate['participant_reading']=='DISTINCT_ACTOR': reasons.append('PARTICIPANT_BINDING_MISMATCH')
    # Lexical intersection is retrieval evidence, not antecedent entailment.
    # This narrow hotfix has no independently checked stimulus bridge.
    if a['stimulus'] != b['stimulus']:
        reasons.append('STIMULUS_ENTAILMENT_NOT_ESTABLISHED')
    hypothetical=candidate['basis_kind']=='RESEARCH_HYPOTHESIS'
    predicate_ok=candidate['predicate_reading']!='LITERAL_PREDICATES'
    if not predicate_ok: reasons.append('PREDICATE_ALIGNMENT_MISSING')
    if a['quantifier']!=b['quantifier'] and not (hypothetical and candidate['time_reading']=='GNOMIC'):
        reasons.append('QUANTIFIER_DOMAIN_COVERAGE_MISSING')
    if a['time']!=b['time'] and not (hypothetical and candidate['time_reading']=='GNOMIC'):
        reasons.append('TEMPORAL_INTERPRETATION_MISSING')
    if a['quantifier']==b['quantifier']=='NAMED_CASE' and a.get('witness_id')!=b.get('witness_id'):
        reasons.append('ADDRESSED_WITNESS_IDENTITY_REQUIRED')
    # The quantifier/tense bridge in GNOMIC is explicitly a hypothesis. It may
    # license a conditional finite calculation, never exact source attestation.
    conflict=any(f['stimulus']==b['stimulus'] and f['actor']==b['actor'] and f['direction']==b['direction']
        and f.get('output_predicate')==b.get('output_predicate') and f['polarity']!=b['polarity']
        and (f['quantifier']==b['quantifier']=='ALL' or (f.get('witness_id') and f.get('witness_id')==b.get('witness_id')))
        for f in canonical['frames'])
    if conflict: reasons.append('CONFLICTING_SOURCE_FRAMES')
    return {'candidate_id':candidate['id'],'basis_valid':not bool(set(disabled_basis)&set(candidate['basis_refs'])),
        'assurance':'CONDITIONAL_HYPOTHESIS' if hypothetical else 'SOURCE_LOCAL_PARSE',
        'reasons':reasons,'applicable':not reasons,'consistent':not conflict,
        'source_frame':a,'validation_frame':b,'preserved_polarity':a['polarity']==b['polarity'],
        'basis_scope':'Packet-bound frames and local definition, not expert or empirical review.'}


def assess(req: dict, observed: dict, family: dict | None = None, *, disabled_basis: tuple[str,...] = ()) -> dict:
    family=family if family is not None else candidates(req,observed)
    # A caller cannot delete inconvenient variants or declare a cut family full.
    expected=candidates(req,observed)
    full=family==expected and not family['truncated'] and bool(family['candidates'])
    rows=[]
    for c in family['candidates']:
        v=verify(req,observed,c,disabled_basis=disabled_basis)
        supported=v['applicable'] and v['preserved_polarity']; refuted=v['applicable'] and not v['preserved_polarity']
        # Do not assume P=>Q because the precomputed answer is favourable.
        # This is a source-signature result, NOT a DAV entailment certificate.
        formal = {'status':'unknown', 'reason':'TARGET_ENTAILMENT_NOT_RUN',
                  'kind':'SOURCE_FRAME_COMPARISON_NOT_FORMAL_PROOF',
                  'metrics':{'source_signature_checks':1}}
        status='UNRESOLVED'
        complete_roles = all(req['q_s'].get(k) is not None
                             for k in ('participant','stimulus_participant','recipient','direction'))
        if v['assurance']=='SOURCE_LOCAL_PARSE' and v['applicable'] and complete_roles:
            status='SUPPORTS_EXACT_CLAIM' if supported else 'REFUTES_EXACT_CLAIM' if refuted else 'UNRESOLVED'
        transport=check_transport(compile_transport(req['source_frame'],observed,c,disabled_basis=disabled_basis),req)
        rows.append({'candidate':c,'verification':v,'status':status,'conditional_entailment':False, 'conditional_alignment_compatible':bool(supported),
            'source_transport':transport,
            'finite_K_V_and_C_a':{'satisfiable':None,'states':None, 'deprecated_field':True,
                'evidence':formal,'assumptions_source_attested':v['assurance']=='SOURCE_LOCAL_PARSE',
                'scope':'Directional implication of the admitted local frame. Not universal physical response.'}})
    # A statement about a provably different explicit actor is not a competing
    # interpretation of the addressed claim. Retain it with an exclusion reason.
    relevant=[]
    for row in rows:
        v=row['verification']; x=v['source_frame']; y=v['validation_frame']
        disjoint=any(x[k]!=y[k] for k in ('source_hash','edition','scope','domain','direction','recipient','modality','actor','stimulus_actor'))
        row['eligibility']='EXCLUDED_SOURCE_SIGNATURE' if disjoint else 'RELEVANT_OR_UNRESOLVED'
        if not disjoint: relevant.append(row)
    exact=full and bool(relevant) and all(r['status']=='SUPPORTS_EXACT_CLAIM' for r in relevant)
    refuted=full and bool(relevant) and all(r['status']=='REFUTES_EXACT_CLAIM' for r in relevant)
    obligations=sorted({reason for r in rows for reason in r['verification']['reasons']})
    if not rows: obligations=['QUANTIFIER_DOMAIN_COVERAGE_MISSING','PREDICATE_ALIGNMENT_MISSING']
    if any(r['verification']['assurance']=='CONDITIONAL_HYPOTHESIS' for r in rows):
        obligations += ['PREDICATE_BASIS_REQUIRES_REVIEW','TEMPORAL_AND_PARTICIPANT_READING_UNRESOLVED']
    return {'q_s_id':req['q_s_id'],'q_t_id':req['q_t_id'],'family':family,'branches':rows,
        'status':'SUPPORTS_EXACT_CLAIM' if exact else 'REFUTES_EXACT_CLAIM' if refuted else 'UNRESOLVED',
        'conditional_support':False,
        'conditional_alignment_compatible':any(r['conditional_alignment_compatible'] for r in relevant),
        'robust_in_registered_family':exact,
        'target_query_verified':False, 'target_entailment_status':'NOT_RUN',
        'conditional_source_models':sum(r['source_transport'].get('entails',False) and r['candidate']['basis_kind']=='RESEARCH_HYPOTHESIS' for r in relevant),
        'computation_complete':full,'obligations':sorted(set(obligations)),
        'conflict':any(not r['verification']['consistent'] for r in rows),
        'proof_status':'unverified','execution_permission':{'allowed':False}}


def stimulus_head(text: str) -> str:
    words=re.split(r'\b(?:в|на|за|под|над|у)\b',norm(text))[0].split()
    if 'ли' in words:words=words[words.index('ли')+1:]
    return LEXICAL_RESOURCE['forms'].get(words[-1],words[-1]) if words else ''


def compile_transport(source_frame: dict, observed: dict, candidate: dict, *, disabled_basis: tuple[str,...] = ()) -> dict:
    """Compile explicit K/C_a before receiving any formula/verdict to check.

    Vocabulary may include the addressed proposal frame, but its assertion is
    never a K premise. Facts are validation rules and directed local definitions.
    C_a hypotheses remain visibly unproved source assumptions.
    """
    from davcore.ast import implication
    a=source_frame;frames=observed['frames'];atoms: list[list[Any]]=[];rules=[]
    def atom(f,kind,label):
        context=[f['stimulus_actor'] if kind=='input' else f['actor'],f['recipient'],f['direction'],
                 f['domain'],f['modality'],f['time'],f.get('discourse')]
        value=[kind,label,*context]
        if value not in atoms:atoms.append(value)
        return atoms.index(value)
    def rule(i,j,sign,refs,kind,antecedent_sign='POSITIVE'):
        if set(refs)&set(disabled_basis):return
        rules.append({'from':i,'to':j,'polarity':sign,'input_polarity':antecedent_sign,
            'source_refs':refs,'kind':kind})
    atom(a,'input',a['stimulus']);atom(a,'output',a.get('output_predicate',a['output']))
    for f in frames:
        i=atom(f,'input',f['stimulus']);j=atom(f,'output',f.get('output_predicate',f['output']))
        rule(i,j,f['polarity'],f['source_refs'],'K_VALIDATION_RULE',f.get('input_polarity','POSITIVE'))
    # Directed lexical definitions are instantiated in the same typed context.
    for d in observed['definitions']:
        for i,x in enumerate(atoms):
            for j,y in enumerate(atoms):
                if x[0]==y[0]=='output' and x[1]==d['from'] and y[1]==d['to'] and x[2:]==y[2:]:
                    rule(i,j,'POSITIVE',d['source_refs'],'K_DIRECTED_DEFINITION')
    b=next(f for f in frames if f['frame_id']==candidate['validation_frame_id'])
    # These arrows encode an *explicit* candidate, not the final supported bool.
    # They are absent in literal/event/other-actor branches and retained as H.
    if (observed['observer']==CONTEXT_STRATEGY and candidate['basis_kind']=='RESEARCH_HYPOTHESIS' and candidate['predicate_reading']=='PARALLEL_RESPONSE'
        and candidate['time_reading']=='GNOMIC' and candidate['participant_reading']=='SAME_LOCAL_ACTOR'
        and a['actor']==b['actor'] and a['stimulus_actor']==b['stimulus_actor']
        and a['direction']==b['direction'] and a['modality']==b['modality']
        and stimulus_head(a['stimulus'])==stimulus_head(b['stimulus'])):
        rule(atom(a,'input',a['stimulus']),atom(b,'input',b['stimulus']),'POSITIVE',candidate['basis_refs'],'C_a_UNATTESTED_STIMULUS_READING')
        rule(atom(b,'output',b.get('output_predicate',b['output'])),atom(a,'output',a.get('output_predicate',a['output'])),
             'POSITIVE',candidate['basis_refs'],'C_a_UNATTESTED_OUTPUT_TIME_READING')
    if len(atoms)>8:return {'status':'BOUND_INSUFFICIENT','atoms':atoms,'rules':rules,'max_species':8}
    refs=sorted({r for f in frames for r in f['source_refs']}) or a['source_refs']
    network={'species':[{'id':'v'+str(i),'label':'source atom '+str(i),'source_refs':refs} for i in range(len(atoms))],
        'reactions':[{'id':'identity','reactants':{'v0':1},'products':{'v0':1},'source_relation_ids':['vocabulary_identity']}]}
    constraints=[{**r,'formula':implication('S'+str(r['from']),'One' if r['input_polarity']=='POSITIVE' else 'Zero',
        'S'+str(r['to']),'One' if r['polarity']=='POSITIVE' else 'Zero').canonical_ast()} for r in rules]
    body={'status':'COMPILED_EXPLICIT_K_C','atoms':atoms,'constraints':constraints,
        'spec':{'kind':'reaction_network','reaction_network':network},'candidate_id':candidate['id'],
        'source_frame_id':a['frame_id'],'hypothesis_bases':[r for r in rules if r['kind'].startswith('C_a')],
        'compiler_received_query_formula':False,'compiler_received_verdict':False}
    return {**body,'premise_seal':digest(body)}


def check_transport(compiled: dict, req: dict) -> dict:
    from davcore.adapters import Adapter, AdapterSpec
    from davcore.ast import Formula, implication
    from davcore.finite import check, witness, Meter
    from davcore.models import Budget
    if compiled['status']!='COMPILED_EXPLICIT_K_C':return {'status':'NOT_RUN','reason':compiled['status'],'entails':False}
    claim=Claim.model_validate_json(json.dumps(req['q_s']))
    if req!=request(req['source_frame'],claim,req['q_t_id'],RawPacket.model_validate(req['proposal_packet'])):
        raise ValueError('SOURCE_QUESTION_BINDING_DRIFT')
    if req['source_frame']['frame_id']!=compiled['source_frame_id']:raise ValueError('SOURCE_FRAME_AFTER_SEAL_DRIFT')
    body={k:v for k,v in compiled.items() if k!='premise_seal'}
    if digest(body)!=compiled['premise_seal']:raise ValueError('SOURCE_PREMISES_AFTER_SEAL_DRIFT')
    adapter=Adapter(AdapterSpec.model_validate(compiled['spec']));meter=Meter(Budget())
    fs=[Formula.model_validate(c['formula']) for c in compiled['constraints']]
    models=[s for s in adapter.states() if all(witness(adapter,f,s,meter)['actual_relation'] for f in fs)]
    # Addressed input/output were installed as vocabulary positions 0,1 before K;
    # the goal is bound only now. No goal is used to choose K's admissible states.
    q=implication('S0','One' if req['source_frame'].get('input_polarity','POSITIVE')=='POSITIVE' else 'Zero',
        'S1','One' if req['q_s']['polarity']=='POSITIVE' else 'Zero')
    active=[s for s in models if witness(adapter,q,s,meter)['premise']['actual_equal']]
    evidence=check(adapter,q,states=models)
    opposite=implication('S0','One','S1','Zero' if req['q_s']['polarity']=='POSITIVE' else 'One')
    negative=check(adapter,opposite,states=models)
    entails=bool(models and active and evidence['status']=='consistent_with_observations')
    return {'status':'EXHAUSTIVE_DECLARED_K_C_CHECK','compiled':compiled,'formula':q.canonical_ast(),
        'satisfiable':bool(models),'model_states':models,'active_antecedent_states':active,
        'entails':entails,'entails_opposite':bool(models and active and negative['status']=='consistent_with_observations'),
        'evidence':evidence,'opposite_evidence':negative,'hypotheses_source_attested':not compiled['hypothesis_bases'],
        'model_enumeration_complete':True,'scope':'All valuations satisfying explicit K/C_a in this finite source projection; not human-world truth.',
        'target_query_verified':False,'proof_status':'unverified','execution_permission':{'allowed':False}}
