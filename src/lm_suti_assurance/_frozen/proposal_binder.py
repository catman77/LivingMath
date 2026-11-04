"""COPY/CANONICALIZE ONLY. This module does not import or invoke a checker."""
import copy
from common002 import canonical,digest,byte_digest,source_ref,binder_digest
from proposal_schema import parse_delta,ProposalError,KINDS

LANGUAGE={'FINITE_PROPOSITION':'finite-logic-v1','SOURCE_CLAIM':'source-claim-v1',
    'EXECUTABLE_BOUNDED':'bounded-program-v1','EMPIRICAL_HYPOTHESIS':'natural-language'}


def compile_delta(raw: str,task: dict,sources: dict,runtime: dict) -> dict:
    delta=parse_delta(raw);context={}
    for sid in task['source_ids']:
        source=sources.get(sid)
        if source is None or source.get('content_utf8') is None:raise ProposalError('MISSING_SOURCE_BYTES','BINDING')
        if source.get('source_id')!=sid or byte_digest(source['content_utf8'].encode())!=source.get('sha256'):raise ProposalError('SOURCE_SHA_MISMATCH','BINDING')
        if digest(source)!=task['scope']['source_snapshots'][sid]:raise ProposalError('SOURCE_OR_RIGHTS_SCOPE_DRIFT','BINDING')
        if not source.get('rights',{}).get('origin'):raise ProposalError('SOURCE_RIGHTS_ORIGIN_REQUIRED','BINDING')
        context[sid]=digest(source)
    raw_sha=byte_digest(raw.encode());base={'proposal_raw_sha256':raw_sha,'binder_version':'proposal-binder/1','binder_digest':binder_digest(),
        'task_id':task['task_id'],'source_snapshot_bindings':context,'runtime_digest':digest(runtime),'execution_permission':False,
        'source_refs':[source_ref(sources[s]) for s in task['source_ids']],
        'source_rights_origin':{s:sources[s]['rights']['origin'] for s in task['source_ids']}}
    if delta['intent']=='ABSTAIN':
        return {**base,'record_kind':'NoProposalRecord','proposal':delta,'candidate':None,'compiled_candidate_sha256':None,
            'semantic_status':'NO_PROPOSAL','positive_assurance':False,'checker_invoked':False,
            'field_provenance':{'/reason':'MODEL_DELTA:/reason','/intent':'MODEL_DELTA:/intent','/task_id':'TRUSTED_TASK:/task_id','/source_snapshot_bindings':'AUTHENTIC_SOURCE_SNAPSHOTS'}}
    kind=delta['kind']
    if kind not in KINDS[task['claim_kind']]:raise ProposalError('DELTA_KIND_OUTSIDE_TASK','BINDING')
    p={};model_fields={}
    if kind=='FINITE_TRACE':
        p={'predicate':'trace_equals','query':copy.deepcopy(task['query']),'trace':copy.deepcopy(delta['trace'])}
        strength={'ENTAILED':'ENTAILED_UNDER_PUBLIC_CONTRACT','CONDITIONAL':'CONDITIONAL_HYPOTHESIS'}[delta['strength']]
        model_fields={'/assertion/machine_term/trace':'MODEL_DELTA:/trace','/proposed_status':'MODEL_DELTA:/strength (literal enum mapping)',
            '/assertion/machine_term/query':'TRUSTED_TASK:/query','/assertion/machine_term/predicate':'MODEL_DELTA:/kind (literal enum mapping)'}
    elif kind=='SOURCE_PROJECTION':
        p={'predicate':'projection_relation','projected_fields':copy.deepcopy(task['projected_fields']),
            'required_fields':copy.deepcopy(task['required_fields']),
            'expectation':{'LOSS_DETECTED':'loss_detected','PRESERVED_FOR_DECLARED_Q':'preserved'}[delta['relation']]}
        strength='SOURCE_ATTESTED';model_fields={'/assertion/machine_term/expectation':'MODEL_DELTA:/relation (literal enum mapping)',
            '/assertion/machine_term/projected_fields':'TRUSTED_TASK:/projected_fields','/assertion/machine_term/required_fields':'TRUSTED_TASK:/required_fields'}
    elif kind=='SOURCE_FIELD':
        if delta['source_id'] not in task['source_ids']:raise ProposalError('SOURCE_ID_OUTSIDE_TASK','BINDING')
        p={'predicate':'field_equals','source_id':delta['source_id'],'pointer':delta['pointer'],'value':copy.deepcopy(delta['value'])};strength='SOURCE_ATTESTED'
        model_fields={f'/assertion/machine_term/{k}':f'MODEL_DELTA:/{k}' for k in ['source_id','pointer','value']}
    elif kind=='SOURCE_PERMISSION':
        p={'predicate':'permission_granted','action':delta['action']};strength='SOURCE_ATTESTED';model_fields={'/assertion/machine_term/action':'MODEL_DELTA:/action'}
    elif kind=='BOUNDED_PROPERTY':
        p={'predicate':{'PRESERVES_POPCOUNT':'preserves_popcount','PRESERVES_VALUE':'preserves_value'}[delta['property']],
            'input_domain':copy.deepcopy(task['scope']['input_domain'])};strength='ENTAILED_UNDER_PUBLIC_CONTRACT'
        model_fields={'/assertion/machine_term/predicate':'MODEL_DELTA:/property (literal enum mapping)',
            '/assertion/machine_term/input_domain':'TRUSTED_TASK:/scope/input_domain'}
    elif kind=='EMPIRICAL_HYPOTHESIS':
        # Preserve the model's text verbatim, including mistaken assertions of proof.
        # The original empirical checker admits no physical truth from this term.
        p={'predicate':'hypothesis','text':delta['text']};strength='CONDITIONAL_HYPOTHESIS'
        model_fields={'/assertion/machine_term/text':'MODEL_DELTA:/text','/assertion/machine_term/predicate':'MODEL_DELTA:/kind (literal enum mapping)'}
    provenance={'/schema':'CandidateRecord v1 constant','/candidate_id':'TRUSTED_RUNTIME:/call_id + raw SHA',
        '/task_id':'TRUSTED_TASK:/task_id','/claim_kind':'TRUSTED_TASK:/claim_kind','/scope':'TRUSTED_TASK:/scope',
        '/assumptions':'TRUSTED_TASK:/assumptions','/source_refs':'AUTHENTIC_SOURCE_SNAPSHOTS:source_id/SHA/full byte spans',
        '/evidence_refs':'AUTHENTIC_SOURCE_SNAPSHOTS:complete snapshot digests including rights.origin',
        '/assertion/language':'TRUSTED_TASK:/claim_kind (existing language mapping)',
        '/assertion/content':'CANONICAL_JSON_OF_EXACT_COMPILED_MACHINE_TERM','/generator':'TRUSTED_RUNTIME:actual model identity/configuration',
        '/proposed_status':'MODEL_DELTA:/kind (fixed request-status mapping, never checker-derived)',
        '/assertion/machine_term/predicate':'MODEL_DELTA:/kind (literal enum mapping)',**model_fields}
    c={'schema':'symseq.assurance.candidate.v1','candidate_id':runtime['call_id']+':'+raw_sha[:16],
        'task_id':task['task_id'],'claim_kind':task['claim_kind'],'assertion':{'language':LANGUAGE[task['claim_kind']],
        'content':canonical(p),'machine_term':p},'scope':copy.deepcopy(task['scope']),'assumptions':copy.deepcopy(task['assumptions']),
        'source_refs':[source_ref(sources[s]) for s in task['source_ids']],
        'evidence_refs':['sha256:'+digest(sources[s]) for s in task['source_ids']],
        'proposed_status':strength,'generator':{'kind':runtime['kind'],'id':runtime['model_id'],'config_digest':runtime['config_digest']}}
    return {**base,'record_kind':'CompiledCandidateRecord','proposal':delta,'candidate':c,'compiled_candidate_sha256':digest(c),
        'positive_assurance':False,'checker_invoked':False,'field_provenance':provenance}
