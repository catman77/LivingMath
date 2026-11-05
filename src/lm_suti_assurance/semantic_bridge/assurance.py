"""Use existing source/task/review/candidate/check workflows; no new proof checker."""
from .. import core
from ..core import digest,canonical
from ..service import Service
from .records import seal


def assure(service,project,frame_ref,frame,edition,source,anchors):
    results=[]
    for claim in frame['claim_atoms']:
        if claim['kind']=='FORMAL_STRUCTURE':
            results.append({'claim_id':claim['id'],'target':'UNREGISTERED_FORMAL_STRUCTURE','status':'HOLD',
                            'reason_code':'NO_SUPPORTED_FINITE_CONTRACT','check_ref':None,'execution_permission':False})
            continue
        literal=claim['kind']=='LITERAL';anchor=anchors[claim['source_anchor_refs'][0]] if literal else None
        context={'source':edition['source_snapshot_digest'],'kind':claim['kind'],
                 'quote':{k:anchor[k] for k in ('byte_start','byte_end','quote_utf8','quote_sha256')} if literal else None,
                 'hypothesis_text':None if literal else claim['text']}
        key=digest(context);prefix='sb:'+key
        source_ids=[source['source_id']];snapshots={source['source_id']:source}
        if literal:
            # Strict preflight has already bound this exact slice to original bytes.
            # The original checker attests the deterministic JSON quote envelope only.
            sid='semantic-quote:'+key
            wrapped=core.contracts.SourceSnapshot.create(sid,canonical(context['quote']),source['rights']['origin'],kind='qa',
                                                         can_embed=source['rights']['can_embed']).record
            wrapped['rights']=dict(source['rights'])
            wrapped['provenance']={'method':'EXACT_UTF8_ANCHOR_ENVELOPE','original_source_sha256':source['sha256'],
                                   'author_endorsement_claimed':False}
            service.source(project,wrapped,edition['publication_policy'],prefix+':source')
            source_ids.append(sid);snapshots[sid]=wrapped
            term={'predicate':'field_equals','source_id':sid,'pointer':'/quote_utf8','value':anchor['quote_utf8']}
            kind='SOURCE_CLAIM';language='source-claim-v1';proposed='SOURCE_ATTESTED';predicates=['field_equals']
        else:
            term={'predicate':'hypothesis','text':claim['text']};kind='EMPIRICAL_HYPOTHESIS'
            language='natural-language';proposed='CONDITIONAL_HYPOTHESIS';predicates=['hypothesis']
        scope={'task_id':'semantic:'+key,'scope_version':1,'execution_permission':False,
               'source_snapshots':{sid:digest(snapshots[sid]) for sid in source_ids},
               'boundary':'literal quote bytes only' if literal else 'unverified literary interpretation only'}
        task={'task_id':scope['task_id'],'claim_kind':kind,'source_ids':source_ids,
              'assumptions':['Only pinned transcription bytes apply.','No author-intention, physical or legal truth is certified.'],
              'scope':scope,'allowed_predicates':predicates,
              'question':'Check exact source quote bytes.' if literal else 'Retain an unverified literary interpretation.'}
        if literal:task['record_ids']=[sid]
        t=service.task(project,{'schema':'lm-suti.assurance.task/0.1','project':project,'task':task},prefix+':task')
        service.review(project,t['task_ref'],'OWNER_CONFIRMED_SEMANTIC_SCOPE',
                       'Deterministic scope delegated in pinned edition review: '+edition['owner_review_reason'],prefix+':review')
        candidate={'schema':'symseq.assurance.candidate.v1','candidate_id':'semantic:'+key,'task_id':task['task_id'],
            'claim_kind':kind,'assertion':{'language':language,'content':canonical(term),'machine_term':term},
            'scope':scope,'assumptions':task['assumptions'],
            'source_refs':[core.contracts.source_ref(snapshots[sid]) for sid in source_ids],
            'evidence_refs':['sha256:'+digest(snapshots[sid]) for sid in source_ids],
            'proposed_status':proposed,'generator':{'kind':'OTHER','id':'semantic-application','config_digest':digest({'adapter':'semantic-bridge/1'})}}
        c=service.candidate(project,{'schema':'lm-suti.assurance.candidate/0.1','project':project,'task_ref':t['task_ref'],
                                   'format':'candidate','raw':canonical(candidate)},prefix+':candidate')
        checked=service.check(project,c['candidate_ref'],'direct',prefix+':check')
        results.append({'claim_id':claim['id'],'target':'SOURCE_QUOTE_BYTES_ONLY' if literal else 'INTERPRETATION_HYPOTHESIS',
                        'status':checked['status'],'reason_code':checked['reason_code'],'check_ref':checked['check_ref'],
                        'execution_permission':False})
    return seal('assurance',project,edition['source_snapshot_digest'],{'frame_ref':frame_ref,'claims':results,
        'epistemic_status':'UNKNOWN','source_prose_truth_verified':False},producer=frame['generator_ref'],parents=[frame_ref])
