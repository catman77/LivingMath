"""Strict source-backed boundary for006; contains no witness or attention answers."""
import copy
from dataclasses import dataclass,field
import hashlib
import json
import re

import jsonschema
from normalizer import canonical,digest,reconstruct_context,SCHEMA_PATH,auditor_fingerprint,strict_json
from live_transfer006_primitives import Port,primitive_fingerprint

SPEC_KEYS={'family','parameters','histories','independent_ref','tests','hypotheses','observer','representation',
           'scope','version','unknowns','primitive_sha256','known_failures','current_observation'}
BAD_KEYS={'local_rule','omitted_guard','oracle','oracle_answer','truth_table','Sig','optimal_test','answer','witness'}


class BindingError(ValueError):
    pass


def payload(row: dict) -> dict:
    value,quality=strict_json(row['content'])
    if quality!='EXACT_JSON' or not isinstance(value,dict):raise BindingError('AMBIGUOUS_SOURCE')
    return value


def ref_id(ref: str) -> int:
    if not isinstance(ref,str) or not re.fullmatch(r'event:[1-9][0-9]*',ref):raise BindingError('INVALID_SOURCE_ID')
    return int(ref.split(':')[1])


def forbidden(value) -> bool:
    if isinstance(value,dict):return bool(set(value)&BAD_KEYS) or any(forbidden(x) for x in value.values())
    if isinstance(value,list):return any(forbidden(x) for x in value)
    return False


@dataclass
class Frame:
    spec: dict
    query: dict
    events: dict
    words: dict
    _seal: str = field(init=False,repr=False)

    def __post_init__(self):
        self._seal=digest([self.spec,self.query,self.events,self.words])

    def assert_bound(self):
        if self._seal!=digest([self.spec,self.query,self.events,self.words]):raise BindingError('MUTATED_BOUND_FRAME')

    def port(self,max_calls: int = 2048,seconds: float = 2) -> Port:
        return Port(copy.deepcopy(self.spec['parameters']),max_calls,seconds)

    def sources(self, refs: list[str]) -> list[dict]:
        return [{'ref':r,'project':self.query['project'],'sha256':digest(self.events[ref_id(r)])} for r in sorted(set(refs))]


def load_frame(view: dict, source: dict, query: dict) -> Frame:
    try:
        jsonschema.validate(view,json.loads(SCHEMA_PATH.read_text()))
        if view['normalizer_version']!='004.1':raise BindingError('NORMALIZER_VERSION')
        if view['status']!='COMPLETE' or view['level']=='C4' or not view['audit_context']:raise BindingError('INCOMPLETE_OR_C4')
        if view['project']!=query['project'] or source['project']!=query['project']:raise BindingError('FOREIGN_PROJECT')
        if digest(query) not in view['certificate']['candidate_hashes']:raise BindingError('UNREGISTERED_DOMAIN')
        if view['certificate']['auditor_code_digest']!=auditor_fingerprint():raise BindingError('AUDITOR_VERSION')
        if view['certificate']['schema_digest']!=hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest():raise BindingError('SCHEMA_VERSION')
        if digest(view['audit_context'])!=view['certificate']['context_digest']:raise BindingError('CONTEXT_HASH')
        full=reconstruct_context(view,source);events={r['id']:r for r in full['tables']['events']}
        projected={r['id']:r for r in view['audit_context']['tables']['events']}
        if view['source_catalog']!={'event:'+str(i):digest(r) for i,r in events.items()}:raise BindingError('CATALOG_HASH')
        if any(e['project']!=query['project'] for e in events.values()):raise BindingError('FOREIGN_SOURCE')
        if any(projected.get(i)!=events.get(i) or i not in events for i in query['move']['parent_event_ids']):raise BindingError('MISSING_SOURCE')
        if any(projected.get(i)!=r for i,r in events.items() if r['kind'] in {'failure','failed_check','counterexample','rca'} or r['status'] in {'refuted','counterexample'}):raise BindingError('MISSING_ADVERSE')
        obligation=next(r for r in full['tables']['research_obligations'] if r['id']==query['move']['active_frontier_id'])
        if obligation['project']!=query['project'] or obligation['current_version']!=query['version']:raise BindingError('STALE_OR_FOREIGN_VERSION')
        declarations=[json.loads(r['payload_json']) for r in full['tables']['research_obligation_versions'] if r['obligation_id']==obligation['id']]
        active=next(r for r in declarations if r['version']==query['version'])
        if active['scope']!=query['scope'] or active['status'] not in {'OPEN','TESTING'}:raise BindingError('CLOSED_OR_STALE_SCOPE')
        spec=payload(projected[ref_id(query['root_ref'])])['source_spec']
        if set(spec)!=SPEC_KEYS or forbidden(spec):raise BindingError('UNDECLARED_FIELD_OR_ANSWER_LEAK')
        if (spec['scope'],spec['version'])!=(query['scope'],query['version']):raise BindingError('STALE_SOURCE_SCOPE')
        if spec['primitive_sha256']!=primitive_fingerprint() or spec['representation']!='native_primitive_port/v1':raise BindingError('PRIMITIVE_BINDING')
        p=spec['parameters']
        if p['family']!=spec['family'] or not 2<=len(p['actions'])<=7 or len(set(p['actions']))!=len(p['actions']):raise BindingError('PRIMITIVE_ALPHABET')
        if len(spec['histories'])>16 or len(spec['tests'])>32 or len(spec['hypotheses'])>32:raise BindingError('FAMILY_BOUND')
        words={}
        for ref in spec['histories']+[spec['independent_ref']]:
            row=projected[ref_id(ref)];data=payload(row)
            if data['version']!=query['version'] or data['representation']!='native_primitive_port/v1':raise BindingError('HISTORY_VERSION_REPRESENTATION')
            if ref in spec['histories'] and data['scope']!=query['scope']:raise BindingError('HISTORY_SCOPE')
            word=data['word']
            if len(word)>6 or not set(word)<=set(p['actions']):raise BindingError('HISTORY_ALPHABET')
            words[ref]=word
        for i,test in enumerate(spec['tests']):
            if not 1<=len(test['suffix'])<=2 or not set(test['suffix'])<=set(p['actions']) or test['ordinal']!=i or type(test['cost']) is not int or test['cost']<0:raise BindingError('TEST_DOMAIN')
        if len({t['id'] for t in spec['tests']})!=len(spec['tests']):raise BindingError('TEST_IDS')
        ids={h['id'] for h in spec['hypotheses']}
        if len(ids)!=len(spec['hypotheses']):raise BindingError('HYPOTHESIS_IDS')
        for h in spec['hypotheses']:
            if type(h['weight']) is not int or h['weight']<=0 or h['ref'] not in words or not set(h['depends_on'])<=ids:raise BindingError('HYPOTHESIS_BINDING')
        if spec['observer']['projection']!='primary' or (spec['observer']['mod'] is not None and (type(spec['observer']['mod']) is not int or spec['observer']['mod']<1)):raise BindingError('OBSERVER')
        return Frame(spec,query,projected,words)
    except BindingError:raise
    except (ValueError,TypeError,KeyError,StopIteration,jsonschema.ValidationError):raise BindingError('INVALID_OR_MISSING_CONTEXT') from None
