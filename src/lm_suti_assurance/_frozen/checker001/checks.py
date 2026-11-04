"""Deterministic admission for fixed finite/source/bounded predicates, never prose truth."""
from pathlib import Path
from collections import Counter
from jsonschema import Draft202012Validator
from contracts import *
import finite_semantics as finite
from independent_vm import vm_behavior
from bounded_program import rotate_left

KINDS = {'FINITE_PROPOSITION', 'SOURCE_CLAIM', 'EXECUTABLE_BOUNDED', 'EMPIRICAL_HYPOTHESIS', 'FORMAL_PROPOSITION'}
ROOT = Path(__file__).parent


class GateError(ValueError):
    def __init__(self, reason, status='REJECTED'):
        self.reason, self.status = reason, status


def require(value, reason, status='REJECTED'):
    if not value:
        raise GateError(reason, status)


def pointer(value, path):
    if path == '':
        return value
    require(isinstance(path, str) and path.startswith('/'), 'INVALID_JSON_POINTER')
    try:
        for piece in path.split('/')[1:]:
            piece = piece.replace('~1', '/').replace('~0', '~')
            value = value[int(piece)] if isinstance(value, list) else value[piece]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise GateError('SOURCE_POINTER_MISSING')


def decode_query(query, bound):
    require(isinstance(query, dict) and set(query) == {'context_id', 'actions'}, 'INVALID_QUERY_CONTRACT')
    require(query['context_id'] in {'context:0', 'context:1'}, 'INVALID_CONTEXT_CONTRACT')
    actions = query['actions']
    require(isinstance(actions, list) and len(actions) <= bound, 'ACTION_BOUND_EXCEEDED')
    require(all(isinstance(a, dict) and set(a) == {'kind', 'id'} and a['kind'] == 'action' and a['id'] in {'action:a','action:b','action:read'} for a in actions), 'INVALID_ACTION_CONTRACT')
    return int(query['context_id'][-1]), [a['id'].split(':')[1] for a in actions]


def models_for(data, engine):
    trace = finite.trace if engine == 'direct' else finite.vm_trace
    key = finite.behavior if engine == 'direct' else vm_behavior
    models = {}
    for model in finite.MODELS:
        if all(trace(model, d['context'], d['actions']) == d['observations'] for d in data):
            models.setdefault(key(model), model)
    require(bool(models), 'INCONSISTENT_PUBLIC_OBSERVATIONS', 'HOLD')
    return list(models.values()), trace, key


def semantic_check(candidate, task, sources, engine, emit):
    kind = candidate['claim_kind']; term = candidate['assertion'].get('machine_term'); proposed = candidate.get('proposed_status', 'UNSPECIFIED')
    if kind == 'FORMAL_PROPOSITION':
        raise GateError('FORMAL_ADMISSION_ADAPTER_UNAVAILABLE', 'HOLD')
    if kind == 'EMPIRICAL_HYPOTHESIS':
        require(candidate['assertion']['language'] == 'natural-language', 'CLAIM_LANGUAGE_KIND_MISMATCH')
        require(isinstance(term, dict), 'EMPIRICAL_METHOD_MISSING', 'HOLD')
        require(term.get('predicate') in {'hypothesis','observation'}, 'EMPIRICAL_NOT_A_FINITE_PROOF', 'HOLD')
        require(proposed not in {'PROVED_FORMAL','ENTAILED_UNDER_PUBLIC_CONTRACT','SOURCE_ATTESTED'}, 'EMPIRICAL_TRUTH_NOT_ESTABLISHED', 'HOLD')
        if proposed == 'OBSERVATION_RECORDED':
            require(term.get('predicate') == 'observation' and task.get('observation_record') is not None, 'OBSERVATION_EVIDENCE_MISSING', 'HOLD')
            require(term.get('record') == task['observation_record'], 'OBSERVATION_RECORD_MISMATCH')
            emit('observation', {'method': task['observation_record'], 'causality_established': False})
            return 'ACCEPT', 'OBSERVATION_RECORDED', 'EMPIRICAL_RECORD', 'OBSERVATION_ONLY'
        if proposed == 'CONDITIONAL_HYPOTHESIS':
            emit('unverified_empirical_hypothesis', {'assumptions': task['assumptions'], 'world_truth_checked': False})
            return 'UNKNOWN', 'UNKNOWN', 'NONE', 'EMPIRICAL_CONDITIONAL_VALIDITY_UNCHECKED'
        return 'UNKNOWN', 'UNKNOWN', 'NONE', 'EMPIRICAL_EVIDENCE_INCOMPLETE'
    require(set(candidate['assertion'])=={'language','content','machine_term'}, 'UNRECOGNIZED_ASSERTION_FIELD')
    require(isinstance(term, dict), 'MACHINE_TERM_MISSING', 'HOLD')
    try:
        text_term = strict_json(candidate['assertion']['content'])
    except (ValueError, TypeError):
        raise GateError('CLAIM_TEXT_NOT_BOUND_TO_MACHINE_TERM')
    require(canonical(text_term) == canonical(term), 'CLAIM_TEXT_TERM_MISMATCH')
    require(term.get('predicate') in task['allowed_predicates'], 'PREDICATE_OUTSIDE_TASK_SCOPE')
    fields={'trace_equals':{'predicate','query','trace','coverage'},'field_equals':{'predicate','source_id','pointer','value','coverage'},'projection_relation':{'predicate','projected_fields','required_fields','expectation','coverage'},'permission_granted':{'predicate','action','coverage'},'preserves_popcount':{'predicate','input_domain','coverage'},'preserves_value':{'predicate','input_domain','coverage'}}
    require(set(term)<=fields[term['predicate']], 'UNRECOGNIZED_ASSERTION_FIELD')
    require(term.get('coverage', 'full') == 'full', 'INCOMPLETE_EXHAUSTIVE_EVIDENCE', 'HOLD')
    if kind == 'FINITE_PROPOSITION':
        require(candidate['assertion']['language'] == 'finite-logic-v1', 'CLAIM_LANGUAGE_KIND_MISMATCH')
        spec = strict_json(sources[task['primary_source']]['content_utf8'])
        require(canonical(spec['hypothesis_class']) == canonical(finite.public_class()), 'PUBLIC_CLASS_CHANGED')
        bound = task['scope']['max_actions']; q = term.get('query'); context, actions = decode_query(q, bound)
        require(q == task['query'], 'QUERY_OUTSIDE_FROZEN_SCOPE')
        models, trace, key = models_for(spec['observations'], engine)
        distribution = Counter(tuple(trace(m, context, actions)) for m in models)
        witnesses = []
        for value in sorted(distribution):
            model = min(m for m in models if tuple(trace(m, context, actions)) == value)
            witnesses.append({'hypothetical_model': {'a': model[0], 'b': model[1], 'sensor': model[2]},
                'trace': list(value), 'class_count': distribution[value], 'fits_all_observations': True})
        evidence = {'query': q, 'complete_public_class_size': 192, 'posterior_behavior_classes': len(models),
            'distribution': [{'trace': list(v), 'count': n} for v,n in sorted(distribution.items())],
            'countermodels': witnesses[:2], 'answer_status': 'UNKNOWN' if len(distribution)>1 else 'UNIQUE_FINITE',
            'enumeration_digest': digest(sorted([[key(m), trace(m, context, actions)] for m in models]))}
        value = term.get('trace')
        if proposed == 'UNKNOWN':
            emit('finite_ambiguity' if len(distribution)>1 else 'missed_certifiable', evidence)
            return 'UNKNOWN', 'UNKNOWN', 'FINITE_EXHAUSTIVE', 'MULTIPLE_ADMISSIBLE_CONTINUATIONS' if len(distribution)>1 else 'GENERATOR_ABSTAINED_CERTIFIABLE'
        require(isinstance(value, list) and len(value) == len(actions)+1 and all(type(v) is int and v in [0,1] for v in value), 'INVALID_TRACE_CONTRACT')
        match = distribution.get(tuple(value), 0)
        if proposed == 'CONDITIONAL_HYPOTHESIS':
            require(match>0, 'NO_ADMISSIBLE_CONDITIONAL_WORLD')
            emit('finite_conditional', evidence)
            return 'ACCEPT', 'CONDITIONAL_HYPOTHESIS', 'CONDITIONAL_CHECK', 'SUPPORTED_NOT_ENTAILED'
        require(proposed == 'ENTAILED_UNDER_PUBLIC_CONTRACT', 'FINITE_ASSURANCE_NOT_REQUESTED', 'HOLD')
        emit('finite_exhaustive' if match == len(models) else 'finite_counterexample', evidence)
        if match != len(models):
            return 'REJECT', 'REJECTED', 'FINITE_EXHAUSTIVE', 'FALSE_ENTAILED_ANSWER_UNKNOWN' if len(distribution)>1 else 'FALSE_FINITE_PROPOSITION'
        return 'ACCEPT', 'CHECKED_FINITE', 'FINITE_EXHAUSTIVE', 'EXHAUSTIVE_FULL_DECLARED_CLASS'
    if kind == 'SOURCE_CLAIM':
        require(candidate['assertion']['language'] == 'source-claim-v1', 'CLAIM_LANGUAGE_KIND_MISMATCH')
        require(proposed in {'SOURCE_ATTESTED','UNSPECIFIED'}, 'SOURCE_IS_NOT_MATHEMATICAL_PROOF', 'HOLD')
        records = [strict_json(sources[sid]['content_utf8']) for sid in task['record_ids']]
        if term['predicate'] == 'field_equals':
            sid = term.get('source_id'); require(sid in task['record_ids'], 'SOURCE_FIELD_OUTSIDE_TASK')
            actual = pointer(strict_json(sources[sid]['content_utf8']), term.get('pointer'))
            emit('source_field', {'source_id':sid, 'pointer':term['pointer'], 'actual':actual, 'content_truth_established':False})
            require(canonical(actual) == canonical(term.get('value')), 'SOURCE_FIELD_VALUE_FALSE')
            return 'ACCEPT','SOURCE_ATTESTED','SOURCE_BYTE_SPAN','EXACT_SOURCE_FIELD_ONLY'
        if term['predicate'] == 'permission_granted':
            # A source flag is never an external execution/publication permission.
            emit('permission_boundary', {'publication_status':records[0].get('publication_status'), 'execution_permission':False})
            raise GateError('SOURCE_FLAG_IS_NOT_EXTERNAL_PERMISSION')
        require(term.get('projected_fields') == task['projected_fields'] and term.get('required_fields') == task['required_fields'], 'DECLARED_Q_SCOPE_CHANGED')
        projected = [{k:pointer(v,'/'+k) for k in term['projected_fields']} for v in records]
        different = sorted(k for k in term['required_fields'] if canonical(pointer(records[0],'/'+k)) != canonical(pointer(records[1],'/'+k)))
        equal_projection = canonical(projected[0]) == canonical(projected[1]); lost = equal_projection and bool(different)
        emit('source_projection', {'source_ids':task['record_ids'], 'projection':projected, 'different_required_fields':different,
            'relation':'LOSS_DETECTED' if lost else 'PRESERVED_FOR_DECLARED_Q' if not different else 'DISTINGUISHED', 'rights_origins':[sources[s]['rights']['origin'] for s in task['record_ids']], 'absolute_identity_claimed':False})
        expectation = term.get('expectation')
        require(expectation in {'loss_detected','preserved'}, 'UNKNOWN_PROJECTION_CLAIM')
        require(lost if expectation=='loss_detected' else not different, 'FALSE_PROJECTION_PRESERVATION')
        return 'ACCEPT','SOURCE_ATTESTED','SOURCE_BYTE_SPAN','LOSS_DETECTED' if lost else 'PRESERVED_FOR_DECLARED_Q'
    if kind == 'EXECUTABLE_BOUNDED':
        require(candidate['assertion']['language'] == 'bounded-program-v1', 'CLAIM_LANGUAGE_KIND_MISMATCH')
        source = sources[task['primary_source']]
        require(byte_digest((ROOT/'bounded_program.py').read_bytes()) == source['sha256'], 'PROGRAM_SOURCE_CHANGED')
        require(proposed == 'ENTAILED_UNDER_PUBLIC_CONTRACT', 'BOUNDED_ASSURANCE_NOT_REQUESTED', 'HOLD')
        require(term.get('input_domain') == [0,15] == task['scope']['input_domain'], 'BOUNDED_DOMAIN_CHANGED')
        rows=[]
        for value in range(16):
            output = rotate_left(value) if engine=='direct' else int(f'{value:04b}'[1:]+f'{value:04b}'[0],2)
            good = output.bit_count()==value.bit_count() if term['predicate']=='preserves_popcount' else output==value
            rows.append([value,output,good])
        emit('bounded_exhaustive', {'all_16_inputs':rows, 'unbounded_claim':False})
        if not all(row[2] for row in rows):
            return 'REJECT','REJECTED','FINITE_EXHAUSTIVE','BOUNDED_PROGRAM_COUNTEREXAMPLE'
        return 'ACCEPT','CHECKED_FINITE','FINITE_EXHAUSTIVE','ALL_16_INPUTS_EXHAUSTED'
    raise GateError('UNSUPPORTED_CLAIM_KIND','HOLD')


def check(candidate, task, sources, *, engine='direct', expected_verifier_digest=None):
    require(engine in {'direct','compiled'}, 'UNKNOWN_ENGINE')
    vd = verifier_digest(); sd = digest({sid:digest(sources.get(sid)) for sid in task['source_ids']}); scope = digest(task['scope']); witnesses={}
    def emit(kind,payload):
        w = Witness({'schema':'symseq.assurance.witness.v1','kind':kind,'source_digest':sd,'scope_digest':scope,'payload':payload})
        witnesses[w.ref]=w.record
    try:
        require(expected_verifier_digest is None or expected_verifier_digest==vd, 'REPLAY_MISMATCH_VERIFIER_DIGEST','HOLD')
        errors=list(Draft202012Validator(load(ROOT/'ASSURANCE_CLAIM_V1.schema.json')).iter_errors(candidate))
        require(not errors, 'CANDIDATE_SCHEMA_INVALID')
        require(candidate['task_id']==task['task_id'] and candidate['claim_kind']==task['claim_kind'], 'TASK_OR_CLAIM_KIND_CHANGED')
        require(canonical(candidate['scope'])==canonical(task['scope']), 'FROZEN_SCOPE_CHANGED')
        require(canonical(candidate['assumptions'])==canonical(task['assumptions']), 'FROZEN_ASSUMPTIONS_CHANGED')
        refs=candidate['source_refs']; require(len(refs)==len(task['source_ids']) and len({x['source_id'] for x in refs})==len(refs), 'SOURCE_BINDING_INCOMPLETE')
        require({x['source_id'] for x in refs}==set(task['source_ids']), 'SOURCE_BINDING_CHANGED')
        for ref in refs:
            sid=ref['source_id'];source=sources.get(sid)
            require(source is not None, 'SOURCE_MISSING','HOLD')
            require(source.get('source_id')==sid, 'SOURCE_ID_MISMATCH')
            require(digest(source)==task['scope']['source_snapshots'][sid], 'SOURCE_VERSION_OR_RIGHTS_CHANGED')
            rights=source.get('rights',{})
            require(bool(rights.get('origin')) and rights.get('status')=='DECLARED_USER_AUTHORIZED', 'SOURCE_RIGHTS_ORIGIN_REQUIRED','HOLD')
            require(rights.get('can_embed') is True and source.get('content_utf8') is not None, 'REPLAY_DEPENDENCY_MISSING','HOLD')
            require(Draft202012Validator(load(ROOT/'SOURCE_SNAPSHOT_V1.schema.json')).is_valid(source), 'SOURCE_SNAPSHOT_SCHEMA_INVALID')
            raw=source['content_utf8'].encode('utf-8')
            require(byte_digest(raw)==source['sha256']==ref['sha256'], 'SOURCE_SHA_MISMATCH')
            require(type(ref.get('byte_start')) is int and type(ref.get('byte_end')) is int and 0<=ref['byte_start']<ref['byte_end']<=len(raw), 'SOURCE_BYTE_SPAN_INVALID')
            # Full object coverage avoids attesting a field using an unrelated valid fragment.
            require(ref['byte_start']==0 and ref['byte_end']==len(raw), 'SOURCE_SPAN_DOES_NOT_COVER_ASSERTION')
            if ref.get('pointer') is not None:pointer(strict_json(source['content_utf8']),ref['pointer'])
            if source.get('schema_id'):
                schema=sources.get(source['schema_id']); require(schema is not None, 'SOURCE_SCHEMA_MISSING','HOLD')
                require(Draft202012Validator(strict_json(schema['content_utf8'])).is_valid(strict_json(source['content_utf8'])), 'SUTI_RECORD_SCHEMA_INVALID')
        require(set(candidate['evidence_refs'])=={'sha256:'+digest(sources[s]) for s in task['source_ids']}, 'EVIDENCE_REFERENCE_UNBOUND')
        decision,status,kind,reason=semantic_check(candidate,task,sources,engine,emit)
    except GateError as exc:
        decision='HOLD' if exc.status=='HOLD' else 'REJECT';status=exc.status;kind='NONE';reason=exc.reason
        if not witnesses:emit('contract_failure',{'reason':reason,'scientific_refutation_claimed':False})
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        decision,status,kind,reason='REJECT','REJECTED','NONE','INVALID_TYPED_TERM'
        emit('contract_failure',{'reason':reason,'error_type':type(exc).__name__,'scientific_refutation_claimed':False})
    record={'schema':'symseq.assurance.decision.v1','candidate_digest':claim_digest(candidate),
        'source_digest':sd,'scope_digest':scope,'verifier_id':'assurance001/v1','verifier_digest':vd,
        'decision':decision,'assurance_status':status,'claim_kind':candidate.get('claim_kind') if candidate.get('claim_kind') in KINDS else 'FINITE_PROPOSITION',
        'check_kind':kind,'reason_code':reason,'witness_refs':sorted(witnesses),'dependencies':['sha256:'+digest(sources.get(s)) for s in task['source_ids']], 'execution_permission':False}
    record['decision_digest']=digest(record)
    Draft202012Validator(load(ROOT/'ASSURANCE_DECISION_V1.schema.json')).validate(record)
    return record,witnesses
