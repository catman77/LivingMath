"""Copy model content; bind only authentic context, quotes and workflow metadata."""
from ..core import digest
from ..errors import AssuranceError
from .records import seal, proposal, validate
from .anchors import make_anchor


def bind(record, edition_ref, edition, source, parent_values):
    proposed=proposal(record['raw_proposal']);project=record['project_id']
    if record['generation_mode']=='HOSTED_MODEL' and record['receipt'].get('status')!='OK':
        raise AssuranceError('MODEL_UNAVAILABLE' if record['receipt'].get('status') in ('MODEL_UNAVAILABLE','CONFIGURATION_ERROR','TRANSPORT_ERROR') else 'GENERATOR_POLICY_VIOLATION')
    if record['parent_frames'] and record['phase']!='revise':
        raise AssuranceError('INITIAL_FRAME_HAS_PARENTS')
    if record['phase']=='revise' and not parent_values:
        raise AssuranceError('REVISION_PARENT_REQUIRED')
    if len(parent_values)>1 and (record['operation']!='MERGE' or not record['merge_resolution'].strip()):
        raise AssuranceError('MERGE_RESOLUTION_REQUIRED')
    for parent in parent_values:
        validate('frame',parent)
        if parent['project_id']!=project:
            raise AssuranceError('CROSS_PROJECT_REFERENCE')
        if parent['poem_ref']!=edition_ref or parent['source_snapshot_digest']!=edition['source_snapshot_digest']:
            raise AssuranceError('SOURCE_VERSION_CHANGED_REQUIRES_NEW_TASK')
    if parent_values and record['generation_mode']=='HOSTED_MODEL':
        context=record['receipt'].get('request',{}).get('initial_frozen_frame')
        if context is None or semantic_content(context)!=semantic_content(parent_values[0]):
            raise AssuranceError('MODEL_REVISION_CONTEXT_MISMATCH')
    if record['generation_mode']=='HOSTED_MODEL':
        request=record['receipt'].get('request',{})
        if request.get('source_text')!=source['content_utf8'] or request.get('phase')!=record['phase']:
            raise AssuranceError('MODEL_SOURCE_CONTEXT_MISMATCH')
    anchors={}
    def refs(quotes):
        result=[]
        for quote in quotes:
            a=make_anchor(project,edition_ref,edition,source,quote);ref=digest(a);anchors[ref]=a;result.append(ref)
        return result
    atoms=[{'id':c['id'],'kind':'LITERAL','text':c['text'],'source_anchor_refs':refs([c['quote']]),
            'premises':[],'epistemic_status':'UNKNOWN','alternatives':[]} for c in proposed['literal_observations']]
    atoms += [{'id':c['id'],'kind':c['kind'],'text':c['text'],'source_anchor_refs':refs(c['evidence']),
               'premises':c['premises'],'epistemic_status':'UNKNOWN' if c['evidence'] else 'UNSUPPORTED_INTERPRETATION',
               'alternatives':c['alternatives']} for c in proposed['interpretations']]
    motifs=[{'label':m['label'],'source_anchor_refs':refs(m['evidence'])} for m in proposed['motifs']]
    relations=[{k:v for k,v in r.items() if k!='evidence'}|{'source_anchor_refs':refs(r['evidence']),'epistemic_status':'UNKNOWN'} for r in proposed['relations']]
    raw_ref=digest(record)
    frame=seal('frame',project,edition['source_snapshot_digest'],{
        'frame_id':'frame:'+digest({'project':project,'proposal':raw_ref,'edition':edition_ref})[:24],
        'poem_ref':edition_ref,'revision_index':1+max((p['revision_index'] for p in parent_values),default=0),
        'parent_frame_ids':[p['frame_id'] for p in parent_values],'generator_ref':record['producer_ref'],
        'generation_mode':record['generation_mode'],'seed_or_unknown':None,
        'model_version_or_unknown':record['model_version_or_unknown'],'claim_atoms':atoms,'motifs':motifs,
        'relations':relations,'temporal_reading':proposed['temporal_reading'],'scope':edition['scope'],
        'assumptions':proposed['assumptions'],'limitations':proposed['limitations'],'open_questions':proposed['open_questions'],
        'counterreadings':proposed['counterreadings'],'declared_observables':proposed['observables'],
        'source_bindings':[{'source_ref':edition['source_ref'],'snapshot_digest':edition['source_snapshot_digest'],
                            'source_sha256':source['sha256']}],
        'projection_contract_refs':[],'status':'REVISED' if parent_values else 'PROPOSED',
        'raw_proposal_ref':raw_ref,'claimed_invariants':proposed['claimed_invariants']},
        origin=record['generation_mode'],producer=record['producer_ref'],parents=record['parent_frames'])
    return frame,anchors,proposed


def revision(record, frame_ref, frame, parents, anchors, proposed):
    previous={c['id']:c for p in parents for c in p['claim_atoms']};current={c['id']:c for c in frame['claim_atoms']}
    before_rel={r['id']:r for p in parents for r in p['relations']};after_rel={r['id']:r for r in frame['relations']}
    old_anchors={a for p in parents for c in p['claim_atoms'] for a in c['source_anchor_refs']}
    return seal('revision-edge',frame['project_id'],frame['source_snapshot_digest'],{
        'parent_frames':record['parent_frames'],'child_frame':frame_ref,'operation':record['operation'],
        'rationale':proposed['revision_rationale'],'merge_resolution':record['merge_resolution'],
        'new_source_anchor_refs':sorted(set(anchors)-old_anchors),'added_claims':sorted(set(current)-set(previous)),
        'withdrawn_claims':sorted(set(previous)-set(current)),
        'changed_claims':sorted(k for k in set(current)&set(previous) if digest(current[k])!=digest(previous[k])),
        'changed_relations':sorted(k for k in set(before_rel)|set(after_rel) if before_rel.get(k)!=after_rel.get(k)),
        'preserved_claims':sorted(k for k in set(current)&set(previous) if digest(current[k])==digest(previous[k])),
        'changed_scope':any(p['scope']!=frame['scope'] for p in parents),'claimed_invariants':proposed['claimed_invariants'],
        'loss_witness_refs':[],'status_before':[p['status'] for p in parents],'status_after':frame['status']},
        producer=record['producer_ref'],parents=[*record['parent_frames'],frame_ref])


def semantic_content(frame):
    # Exporting an operator-diagnostic-free provenance version changes IDs only.
    # Compare every declared semantic/source field, never repair the model text.
    ignored={'content_digest','producer_ref','parent_refs','frame_id','parent_frame_ids','generator_ref','raw_proposal_ref'}
    return digest({k:v for k,v in frame.items() if k not in ignored})
