"""Experimental I/T for one finite native arithmetic family; no MCP or write API.

I constructs a constant-size set of algebraic probes, not a Sig truth table.
T groups analytic readouts; exhaustive word execution belongs to the oracle.
"""
import copy
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import re

import jsonschema
from normalizer import canonical, digest, reconstruct_context, SCHEMA_PATH, auditor_fingerprint, strict_json

VERSION = '005.1'
REPRESENTATION = 'native_two_register_mod5_v1'
UNCERTAINTY_PRICE = Fraction(7, 3)


class MissingContext(ValueError):
    pass


def register_state(word: list[int]) -> tuple[int, int]:
    x, y = 0, 1
    for k in word:
        x, y = (x + k * y) % 5, (y + k) % 5
    return x, y


def analytic_continuation(state: tuple[int, int], suffix: list[int]) -> tuple[int, int]:
    """Closed form for the registered suffixes of length at most two."""
    x, y = state
    total = sum(suffix)
    cross = suffix[0] * suffix[1] if len(suffix) == 2 else 0
    return (x + total * y + cross) % 5, (y + total) % 5


def observe(state: tuple[int, int], observer: str) -> int:
    x, _ = state
    if observer == 'x':
        return x
    if observer == 'parity':
        return x % 2
    if observer == 'constant':
        return 0
    raise MissingContext('UNSUPPORTED_OBSERVER')


def kernel_fingerprint() -> str:
    return hashlib.sha256(''.join(inspect.getsource(f) for f in
        (register_state, analytic_continuation, observe)).encode()).hexdigest()


def _result(status: str, **fields) -> dict:
    return {'status': status, 'origin': 'experimental_algorithm', 'core_version': VERSION,
            'execution_allowed': False, 'completion_allowed': False, 'proof_status': 'unverified', **fields}


def _payload(row: dict) -> dict:
    try:
        value, quality = strict_json(row['content'])
        if quality != 'EXACT_JSON' or not isinstance(value, dict):
            raise ValueError()
        return value
    except (KeyError, ValueError, TypeError):
        raise MissingContext('UNPARSEABLE_SOURCE') from None


def _ref_id(ref: str) -> int:
    if not isinstance(ref, str) or not re.fullmatch(r'event:[1-9][0-9]*', ref):
        raise MissingContext('INVALID_SOURCE_REFERENCE')
    return int(ref.split(':')[1])


def _load(view: dict, source: dict, query: dict) -> dict:
    try:
        jsonschema.validate(view, json.loads(SCHEMA_PATH.read_text()))
        if view['status'] != 'COMPLETE' or view['level'] == 'C4' or not view['audit_context']:
            raise MissingContext('C4_OR_INCOMPLETE_CONTEXT')
        if view['normalizer_version'] != '004.1':
            raise MissingContext('UNSUPPORTED_NORMALIZER_VERSION')
        project = query['project']
        if project != source['project'] or project != view['project']:
            raise MissingContext('FOREIGN_PROJECT')
        if digest(query) not in view['certificate']['candidate_hashes']:
            raise MissingContext('UNREGISTERED_QUERY')
        if view['certificate'].get('auditor_code_digest') != auditor_fingerprint():
            raise MissingContext('STALE_AUDITOR_BINDING')
        if view['certificate'].get('schema_digest') != hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest():
            raise MissingContext('STALE_SCHEMA_BINDING')
        context = view['audit_context']
        if digest(context) != view['certificate']['context_digest']:
            raise MissingContext('TAMPERED_CONTEXT_HASH')
        recovered = reconstruct_context(view, source)
        original = {r['id']: r for r in recovered['tables']['events']}
        retained = {r['id']: r for r in context['tables']['events']}
        if any(r['project'] != project for r in original.values()):
            raise MissingContext('FOREIGN_SOURCE')
        if view['source_catalog'] != {'event:'+str(i): digest(r) for i,r in original.items()}:
            raise MissingContext('TAMPERED_SOURCE_CATALOG')
        required = query['move']['parent_event_ids']
        if any(i not in retained or retained[i] != original[i] for i in required):
            raise MissingContext('MISSING_OR_CHANGED_SOURCE')
        if any(retained.get(i) != r for i,r in original.items()
               if r['kind'] in {'counterexample','failure','failed_check','rca'} or r['status'] in {'refuted','counterexample'}):
            raise MissingContext('MISSING_ADVERSE_SOURCE')
        obligations = recovered['tables']['research_obligations']
        obligation = next((r for r in obligations if r['id'] == query['move']['active_frontier_id']), None)
        if obligation is None or obligation['project'] != project or obligation['current_version'] != query['version']:
            raise MissingContext('STALE_OR_FOREIGN_OBLIGATION')
        versions = recovered['tables']['research_obligation_versions']
        current = next(json.loads(r['payload_json']) for r in versions
                       if r['obligation_id'] == obligation['id'] and json.loads(r['payload_json'])['version'] == query['version'])
        if current['status'] not in {'OPEN','TESTING'} or current['scope'] != query['scope']:
            raise MissingContext('CLOSED_OR_WRONG_SCOPE')
        spec = _payload(retained[_ref_id(query['root_ref'])])['source_spec']
        if spec['kernel_sha256'] != kernel_fingerprint() or spec['representation'] != REPRESENTATION:
            raise MissingContext('UNSUPPORTED_SOURCE_REPRESENTATION')
        if (spec['scope'], spec['version']) != (query['scope'], query['version']):
            raise MissingContext('STALE_SOURCE_SCOPE_VERSION')
        if len(spec['histories']) > 32 or len(spec['tests']) > 24:
            raise MissingContext('SOURCE_FAMILY_BOUND')
        if spec['uncertainty_price'] != str(UNCERTAINTY_PRICE):
            raise MissingContext('UNREGISTERED_OBJECTIVE')
        for ref in spec['histories'] + [spec['independent_ref']]:
            row = retained.get(_ref_id(ref))
            if row is None:
                raise MissingContext('MISSING_HISTORY_SOURCE')
            payload = _payload(row)
            word = payload['word']
            if (payload['representation'] != REPRESENTATION or payload['version'] != query['version']
                    or not isinstance(word, list) or len(word) > 4
                    or any(type(k) is not int or not 0 <= k < 5 for k in word)):
                raise MissingContext('UNSUPPORTED_HISTORY_REPRESENTATION')
            if ref in spec['histories'] and payload['scope'] != query['scope']:
                raise MissingContext('HISTORY_SCOPE_MISMATCH')
        ids = [h['id'] for h in spec['hypotheses']]
        if len(ids) > 32 or len(set(ids)) != len(ids):
            raise MissingContext('INVALID_HYPOTHESIS_FAMILY')
        for hyp in spec['hypotheses']:
            if (type(hyp['weight']) is not int or hyp['weight'] <= 0
                    or type(hyp['predictive']) is not bool
                    or hyp['question'] not in {'current','independent'}
                    or not set(hyp['depends_on']) <= set(ids)
                    or hyp['history_ref'] not in spec['histories'] + [spec['independent_ref']]
                    or (hyp['question'] == 'current' and hyp['history_ref'] not in spec['histories'])):
                raise MissingContext('INVALID_HYPOTHESIS_BINDING')
        if len({t['id'] for t in spec['tests']}) != len(spec['tests']):
            raise MissingContext('DUPLICATE_TEST_ID')
        for test in spec['tests']:
            suffix = test['suffix']
            if not 1 <= len(suffix) <= 2 or any(type(k) is not int or not 0 <= k < 5 for k in suffix):
                raise MissingContext('UNSUPPORTED_CONTINUATION')
            if type(test['cost']) is not int or test['cost'] < 0:
                raise MissingContext('INVALID_COST')
        observe((0,1),spec['observer'])
        return {'spec': spec, 'events': retained, 'query': query, 'input_digest': view['input_digest']}
    except MissingContext:
        raise
    except (ValueError, KeyError, TypeError, StopIteration, jsonschema.ValidationError):
        raise MissingContext('MISSING_OR_INVALID_CONTEXT') from None


def _state(ctx: dict, ref: str) -> tuple[int,int]:
    return register_state(_payload(ctx['events'][_ref_id(ref)])['word'])


def _readout(ctx: dict, ref: str, test: dict) -> list:
    state = analytic_continuation(_state(ctx, ref), test['suffix'])
    forbidden = ctx['spec']['forbidden_y']
    return [observe(state,ctx['spec']['observer']), forbidden is None or state[1] != forbidden]


def _sources(ctx: dict, refs: list[str]) -> list[dict]:
    return [{'ref':ref, 'project':ctx['query']['project'], 'sha256':digest(ctx['events'][_ref_id(ref)])}
            for ref in sorted(set(refs))]


def interpret_distinction(view: dict, source: dict, query: dict, left_ref: str,
                          right_ref: str, known: tuple = (), other_observer: str | None = None,
                          title: str = '') -> dict:
    """Construct one source-bound distinction; renamed titles do not affect novelty."""
    try:
        ctx = _load(view,source,query);spec = ctx['spec']
        if other_observer is not None and other_observer != spec['observer']:
            raise MissingContext('OBSERVER_ALIGNMENT_REQUIRED')
        if left_ref not in spec['histories'] or right_ref not in spec['histories']:
            raise MissingContext('HISTORY_OUTSIDE_QUERY_SCOPE')
        left,right = _state(ctx,left_ref),_state(ctx,right_ref)
        sources = _sources(ctx,[query['root_ref'],left_ref,right_ref])
        current = [observe(left,spec['observer']),observe(right,spec['observer'])]
        if current[0] != current[1]:
            return _result('NO_NEW_DISTINCTION',reason='CURRENT_OBSERVATIONS_ALREADY_DIFFER',source_refs=sources)
        if left == right:
            return _result('NO_NEW_DISTINCTION',reason='SAME_NATIVE_CONTINUATION_STATE; source identities remain distinct',source_refs=sources)
        fingerprint = digest({'project':query['project'],'scope':query['scope'],'version':query['version'],
            'kernel':spec['kernel_sha256'],'observer':spec['observer'],'forbidden_y':spec['forbidden_y'],
            'states':sorted([left,right]),'suffix_family':sorted(t['suffix'] for t in spec['tests'])})
        if fingerprint in known:
            return _result('NO_NEW_DISTINCTION',reason='ALREADY_RECORDED_STRUCTURAL_DISTINCTION',fingerprint=fingerprint,source_refs=sources)
        # Bounded constructive probes: unit change, force0/1, hit a guard boundary.
        # No full Sig, oracle table, history enumeration or generic solver is used.
        probes = [1]
        for x,y in (left,right):
            if y:
                probes += [(-x * pow(y,-1,5)) % 5, ((1-x) * pow(y,-1,5)) % 5]
            if spec['forbidden_y'] is not None:
                probes.append((spec['forbidden_y']-y) % 5)
        by_suffix = {tuple(t['suffix']):t for t in spec['tests']}
        for k in dict.fromkeys(probes):
            test = by_suffix.get((k,))
            if test is None:
                continue
            a,b = _readout(ctx,left_ref,test),_readout(ctx,right_ref,test)
            if a != b:
                adverse = [f'event:{i}' for i,r in ctx['events'].items() if r['kind'] in {'counterexample','failed_check','failure'}]
                return _result('NEW_DISTINCTION',fingerprint=fingerprint,
                    statement='Current observation omits a continuation-relevant register or admissibility boundary.',
                    source_refs=sources,history_refs=[left_ref,right_ref],current_observation=current,
                    witness={'test_id':test['id'],'suffix':test['suffix'],'left':a,'right':b},
                    guard={'project':query['project'],'scope':query['scope'],'version':query['version'],
                           'observer':spec['observer'],'left_state':list(left),'right_state':list(right),
                           'source_family_only':True,'generalization_outside_guard':False},
                    assumptions=['Exact native mod5 recurrence and declared observer/K only.','Source declarations are not independently verified.'],
                    known_counterexamples=_sources(ctx,adverse),unknowns=spec['unknowns'],
                    failure_condition='Invalidate if the bound sources/version/observer change or the cited finite suffix yields equal observation/admissibility.',
                    construction_trace={'method':'unit/coordinate-target/guard-boundary algebra','probes':list(dict.fromkeys(probes))})
        return _result('INSUFFICIENT_CONTEXT',reason='NO_CONSTRUCTIVE_WITNESS_FOR_REGISTERED_FAMILY',source_refs=sources)
    except MissingContext as error:
        return _result('INSUFFICIENT_CONTEXT',reason=str(error))


def _updated(ctx: dict, feedback_ref: str | None) -> list[dict]:
    hyps = copy.deepcopy(ctx['spec']['hypotheses'])
    for h in hyps:
        h['status'] = 'ACTIVE'
    if feedback_ref is None:
        return hyps
    event = ctx['events'].get(_ref_id(feedback_ref))
    if event is None or event['kind'] != 'counterexample':
        raise MissingContext('MISSING_COUNTEREXAMPLE')
    data = _payload(event)['observation']
    if (data['scope'],data['version'],data['observer']) != (ctx['query']['scope'],ctx['query']['version'],ctx['spec']['observer']):
        raise MissingContext('FEEDBACK_SCOPE_VERSION_OBSERVER_MISMATCH')
    test = next((t for t in ctx['spec']['tests'] if t['id'] == data['test_id']),None)
    actual = data['readout']
    if test is None or not isinstance(actual,list) or len(actual)!=2 or type(actual[0]) is not int or type(actual[1]) is not bool:
        raise MissingContext('INVALID_OBSERVATION')
    for h in hyps:
        if h['question'] == 'current' and h['predictive'] and _readout(ctx,h['history_ref'],test) != actual:
            h.update(status='EXCLUDED_BY_OBSERVATION',evidence_ref=feedback_ref)
    changed = True
    while changed:
        changed = False;excluded = {h['id'] for h in hyps if h['status'] != 'ACTIVE'}
        for h in hyps:
            if h['status'] == 'ACTIVE' and set(h['depends_on']) & excluded:
                h.update(status='EXCLUDED_DEPENDENCY',evidence_ref=feedback_ref);changed = True
    return hyps


def apply_feedback(view: dict, source: dict, query: dict, feedback_ref: str) -> dict:
    """Derived provisional exclusions only; immutable source claims are retained."""
    try:
        ctx = _load(view,source,query);hyps = _updated(ctx,feedback_ref)
        return _result('FEEDBACK_APPLIED',hypotheses=hyps,source_refs=_sources(ctx,[query['root_ref'],feedback_ref]),
                       source_mutations=0,interpretation='Observed contradiction excludes this bound prediction, not mathematical truth.')
    except MissingContext as error:
        return _result('INSUFFICIENT_CONTEXT',reason=str(error))


def transfer_attention(view: dict, source: dict, query: dict, feedback_ref: str | None = None) -> dict:
    """Choose an informative next measurement; proposals never authorize execution."""
    try:
        ctx = _load(view,source,query);spec = ctx['spec'];hyps = _updated(ctx,feedback_ref)
        active = [h for h in hyps if h['status']=='ACTIVE' and h['predictive'] and h['question']=='current']
        if len(active) < 2:
            return _result('NO_INFORMATIVE_TEST',reason='Fewer than two remaining alternatives',hypotheses=hyps)
        total = sum(Fraction(h['weight']) for h in active)
        ranks=[]
        for test in spec['tests']:
            groups={}
            for h in active:
                key=tuple(_readout(ctx,h['history_ref'],test))
                count,weight=groups.get(key,(0,Fraction(0)))
                groups[key]=(count+1,weight+Fraction(h['weight']))
            if len(groups)<2:
                continue
            expected=sum(count*weight for count,weight in groups.values())/total
            loss=Fraction(test['cost'])+UNCERTAINTY_PRICE*expected
            ranks.append((loss,test['cost'],test['id'],test,expected,len(groups)))
        if not ranks:
            return _result('NO_INFORMATIVE_TEST',reason='Registered tests do not partition remaining alternatives',hypotheses=hyps)
        ranks.sort(key=lambda r:r[:3]);best=ranks[0]
        return _result('ATTENTION_PROPOSED',test_id=best[2],suffix=best[3]['suffix'],cost=best[1],
            expected_remaining=str(best[4]),loss=str(best[0]),
            ties=sorted(r[2] for r in ranks if r[0]==best[0]),hypotheses=hyps,
            ranking=[{'test_id':r[2],'cost':r[1],'expected_remaining':str(r[4]),'loss':str(r[0]),'outcome_groups':r[5]} for r in ranks],
            source_refs=_sources(ctx,[query['root_ref']]+[h['history_ref'] for h in active]),unknowns=spec['unknowns'],
            failure_condition='Recompute after any source, version, admissibility, observer, prior or measured feedback change.')
    except (MissingContext, ZeroDivisionError) as error:
        return _result('INSUFFICIENT_CONTEXT',reason=str(error))
