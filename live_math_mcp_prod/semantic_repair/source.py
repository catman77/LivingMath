"""Frozen catalogue, immutable prediction seal and actual bounded T retrieval."""
import hashlib
import json
from pathlib import Path

from artifact_genesis.contract import RawPacket
from semantic_grounding.contract import independent_spans, quoted
from davcore.ast import digest


class Vault:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.protocol = json.loads((root / 'protocol-freeze.json').read_text())
        for name, h in self.protocol['freeze_files'].items():
            path = (root / name).resolve(strict=True)
            if not path.is_relative_to(self.root) or hashlib.sha256(path.read_bytes()).hexdigest() != h:
                raise ValueError('FROZEN_SOURCE_DRIFT:' + name)
        self.catalog = json.loads((root / 'frozen/catalog.json').read_text())
        self.tasks = json.loads((root / 'frozen/tasks.json').read_text())
        self.access: list[dict] = []; self._seal: dict | None = None

    def packet(self, ident: str, seal: dict | None = None) -> RawPacket:
        meta = self.catalog[ident]
        if meta['partition'] != 'proposal' and (seal is None or self._seal != seal):
            raise PermissionError('EVIDENCE_BEFORE_MODEL_QUERY_SEAL')
        packet = RawPacket.model_validate_json((self.root / meta['path']).read_text())
        doc = (self.root / meta['document_path']).read_bytes()
        if hashlib.sha256(doc).hexdigest() != packet.document_sha256 or packet.edition != meta['edition']:
            raise ValueError('SOURCE_HASH_EDITION_DRIFT')
        for s in packet.spans:
            if doc[s.start:s.end] != s.text.encode():
                raise ValueError('SOURCE_SLICE_DRIFT')
        self.access.append({'id': ident, 'partition': meta['partition'], 'after_seal': self._seal is not None})
        return packet

    def seal(self, models: list[dict], queries: list[dict]) -> dict:
        if self._seal is not None:
            raise ValueError('IMMUTABLE_SEAL_ALREADY_EXISTS')
        body = {'model_sha256': digest(models), 'query_sha256': digest(queries),
                'protocol_sha256': hashlib.sha256((self.root / 'protocol-freeze.json').read_bytes()).hexdigest()}
        self._seal = {**body, 'seal_sha256': digest(body)}
        return dict(self._seal)

    def acquire(self, task: dict, train: RawPacket, family: dict, used: list[str], seal: dict) -> dict:
        if len(used) >= 3:
            return {'status': 'BUDGET_EXHAUSTED'}
        remaining = [k for k in task['acquisition_catalog'] if k not in used]
        if not remaining:
            return {'status': 'NO_DISCRIMINATING_CONTEXT_IN_CATALOG'}
        # Source-address order is a transparent heuristic; no imaginary information gain.
        ident = remaining[0]
        packet = self.packet(ident, seal)
        independent_spans(train, packet)
        return {'status': 'RECEIVED_SOURCE_BYTES', 'packet': packet.model_dump(),
                'packet_id': ident, 'question': task['question'],
                'disagreement': {'family_version': family['candidate_family_version'], 'dimensions': family['unresolved_dimensions']},
                'allowed_catalogue': task['acquisition_catalog'],
                'selection': 'Deterministic source-address catalogue priority, not optimality/probability',
                'received_bytes_sha256': digest([s.text for s in packet.spans]),
                'source_evidence': [quoted(s) for s in packet.spans]}


def validate_prediction(task: dict, observation: dict, query: dict, evidence: RawPacket) -> dict:
    """A deliberately narrow independent source test; weaker evidence never wins."""
    import re
    text = '\n'.join(s.text for s in evidence.spans).casefold()
    labels = observation['labels']
    relevant = [labels[query[k]] for k in ['src_predicate', 'dst_predicate']]
    # Source-internal three-role unity supports connectivity, not physical causality.
    norm_labels = ' '.join(relevant)
    explicit_union = bool(re.search(r'\btrinitie\b', text) and re.search(r'\bvnit[ei]', text))
    both_named = all((word[:-1] if len(word) > 4 and word.endswith('e') else word) in text for word in norm_labels.split())
    if explicit_union and both_named and query['depth'] >= 2:
        return {'status': 'SOURCE_INTERNAL_SUPPORT', 'supported_scope': 'Conditional prescribed connectivity; not material identity or physical time',
                'source_refs': [s.id for s in evidence.spans], 'reason': 'Separate three-role unity prescription names both composed endpoints; terminal-e orthography is a lexical proxy, not referent identity.'}
    return {'status': 'UNRESOLVED', 'source_refs': [s.id for s in evidence.spans],
            'reason': 'No independent exact relation/direction/modality/quantifier witness. A joy-day statement does not validate all passing things becoming dear.',
            'source_prediction': relevant}


def observation_obligation(observation: dict, family: dict, *, has_query: bool) -> dict:
    """A singleton/empty Γ must still request a registered observation strategy."""
    unparsed = [r['span']['span_id'] if 'span_id' in r['span'] else r['span'].get('id')
                for r in observation.get('observation_trace', []) if r['status'] == 'UNPARSED_CLAUSE']
    if unparsed or not observation['premises']:
        return {'kind':'UNPARSED_CLAUSE', 'addresses':unparsed,
                'reason':'Missing local relation, irrespective of binding count.'}
    if family['unresolved_dimensions']:
        return {'kind':'UNKNOWN_BINDING', 'addresses':[], 'reason':'Conditional participant or interpretation remains ambiguous.'}
    if not has_query:
        return {'kind':'INCOMPATIBLE_SCOPE_JOIN', 'addresses':[], 'reason':'No admitted path; reread guards/roles without synthesizing a bridge.'}
    return {'kind':'EXACT_VALIDATION_MISSING', 'addresses':[], 'reason':'Exact scoped q needs a distinct source witness.'}


class ObservationReads:
    """Finite I/T policy over existing source packets, not a general planner."""
    def __init__(self, limit: int = 3):
        if not 1 <= limit <= 3:
            raise ValueError('SOURCE_ACTION_BOUND')
        self.limit = limit
        self.seen: set[tuple[str, str]] = set()
        self.actions: list[dict] = []

    def read(self, packet: RawPacket, strategy: str, obligation: dict) -> dict:
        from .observe005 import STRATEGIES
        if strategy not in (*STRATEGIES, 'source-validation005/1', 'scope-evidence004/1', 'alignment-frames006/1','alignment-context007/1'):
            raise ValueError('UNREGISTERED_READ_STRATEGY')
        key = (digest(packet.model_dump()), strategy)
        if key in self.seen:
            raise ValueError('UNCHANGED_ADDRESS_STRATEGY_ALREADY_READ')
        if len(self.actions) >= self.limit:
            raise ValueError('SOURCE_ACTION_BOUND')
        self.seen.add(key)
        record = {'action':len(self.actions)+1, 'packet_id':packet.id, 'strategy':strategy,
            'obligation':obligation, 'received_packet_hash':key[0],
            'source_evidence':[quoted(s) for s in packet.spans], 'effect':'PENDING_RECOMPUTATION'}
        self.actions.append(record)
        return record


def family_correspondence(old: dict, new: dict) -> dict:
    pairs = [{'old':a['id'], 'new':b['id']} for a in old['bindings'] for b in new['bindings']
             if all(k not in b['assignments'] or b['assignments'][k] == v for k,v in a['assignments'].items())]
    return {'old_version':old['candidate_family_version'], 'new_version':new['candidate_family_version'],
        'pairs':pairs, 'old_count':len(old['bindings']), 'new_count':len(new['bindings']),
        'policy':'Shared assignments correspond; new dimensions may expand family. Never assume subset.',
        'dependent_results':'REQUIRES_REVALIDATION', 'prior_certificates':'RETAINED_IN_ORIGINAL_MODEL_SCOPE',
        'prior_negative_results':'RETAINED_APPEND_ONLY'}


def validate_scoped_prediction(observation: dict, claim, evidence: RawPacket) -> dict:
    """Extract a small independent witness vocabulary, then compare signatures.

    Never fill missing witness fields from the target claim. The only supported
    union grammar concerns explicit normative connectivity. Poetry paraphrases
    remain unresolved rather than consulting a task-name/answer table.
    """
    import itertools
    import re
    from .scoped import Claim, compare
    from .observe import norm
    text = ' '.join(s.text for s in evidence.spans)
    section = evidence.spans[0].source_address.get('section', evidence.document_id)
    scope = 's_' + digest([evidence.document_sha256, evidence.edition, section])[:24]
    domain = 'local_domain_' + digest([evidence.document_sha256, evidence.edition, section])[:20]
    refs = [s.id for s in evidence.spans]; witnesses = []
    union = re.search(r'Of (\w+), (\w+) and (\w+)', text, re.I)
    if union and re.search(r'trinitie.*must.*vnit[ei]', text, re.I):
        # Registered terminal-e spelling proxy; no entity/coreference quotient.
        names = set()
        for word in union.groups():
            word = norm(word); names.add(word)
            if len(word) > 4:
                names.add(word[:-1] if word.endswith('e') else word+'e')
        for a,b in itertools.permutations(sorted(names),2):
            witnesses.append(Claim(predicate='NORMATIVE_CONNECTIVITY', subject='p_'+digest(a)[:24], object='p_'+digest(b)[:24],
                domain=domain, quantifier='ALL', polarity='POSITIVE', modality='PRESCRIPTION', time='NORMATIVE_SCHEMA',
                stage='SCHEMATIC', scope=scope, source_hash=evidence.document_sha256, edition=evidence.edition,
                assumptions=('Text-internal prescribed connectivity only.',)))
    # Explicit joy-day statement is a different existential/future claim. It is
    # never treated as DearLater, even if a finite model proves the latter.
    if re.search(r'День веселья.*настанет', text, re.I):
        witnesses.append(Claim(predicate='JOY_DAY_EXISTS', subject='day', object='joy', domain=domain,
            quantifier='SOME', polarity='POSITIVE', modality='LYRICAL_CLAIM', time='FUTURE_EVENT',
            stage='later_state', scope=scope, source_hash=evidence.document_sha256, edition=evidence.edition))
    comparisons = [compare(claim,w,refs) for w in witnesses]
    exact = next((x for x in comparisons if x['status']=='SUPPORTS_EXACT_CLAIM'),None)
    answer = exact or (comparisons[0] if comparisons else compare(claim,None,refs))
    return {**answer, 'extracted_witnesses':[w.model_dump() for w in witnesses],
            'validation_observer':'source-validation005/1',
            'strength_boundary':'Normative connectivity does not support symbolic execution or material transformation.'}


def effective_method(claim_ids: list[str], query_ids: list[str], model_hashes: list[str], *,
                     observer_hash: str, correspondence_hash: str, resources: dict, criterion: str) -> dict:
    body={'q_s_ids':claim_ids,'q_t_ids':query_ids,'model_hashes':model_hashes,
        'observer_code_sha256':observer_hash,'correspondence_code_sha256':correspondence_hash,
        'resources':resources,'criterion':criterion}
    return {**body,'effective_version':digest(body)}


def evidence_use(journal, packet: RawPacket, role: str, effective_version: str, prior: list[dict],
                 *, method_changed: bool = False) -> dict:
    """Extend the existing Journal. Origin, addresses and dependency use matter.

    Unknown historical origins are never certified independent. Copy/nonce/hash
    changes cannot reset prior use. This is a lineage record, not a new store.
    """
    if role not in {'proposal','alignment-acquisition','development','validation','regression','source-internal-recheck'}:
        raise ValueError('UNREGISTERED_EVIDENCE_ROLE')
    origins=[]
    for s in packet.spans+packet.context:
        address={k:v for k,v in s.source_address.items() if k not in {'cache','nonce','signature','path'}}
        upstream=address.get('upstream_sha256',packet.document_id)
        origins.append({'origin':upstream,'edition':packet.edition,'start':s.start,'end':s.end,
            'address':address,'quote_hash':hashlib.sha256(s.text.encode()).hexdigest()})
    overlaps=[]
    for row in prior:
        for a in origins:
            for b in row['origins']:
                if a['quote_hash']==b['quote_hash'] or (a['origin']==b['origin'] and a['edition']==b['edition'] and (
                    max(a['start'],b['start'])<min(a['end'],b['end']) or a['address']==b['address'])):
                    overlaps.append(row['entry_hash'])
    prior_use=bool(overlaps)
    fresh=role=='validation' and not prior_use and not method_changed
    body={'packet_id':packet.id,'packet_hash':digest(packet.model_dump()),'origins':origins,'role':role,
        'effective_version':effective_version,'method_changed_after_reveal':method_changed,
        'previous_origin_uses':sorted(set(overlaps)),'fresh_for_this_prediction':fresh,
        'assessment':'SOURCE_INTERNAL_RECHECK' if prior_use else 'UNUSED_IN_DECLARED_LINEAGE_ONLY',
        'historical_or_statistical_independence':'NOT_ASSERTED'}
    record=journal.append('SOURCE_EVIDENCE_USE',body)
    result={**body,'entry_hash':record['entry_hash']};prior.append(result);return result


def require_current_alignment(certificate: dict, method: dict, family_version: str) -> None:
    if certificate['effective_version']!=method['effective_version'] or certificate['family_version']!=family_version:
        raise ValueError('STALE_ALIGNMENT_REQUIRES_REVALIDATION')


def journal_revalidation(journal, row: dict) -> dict:
    # Raw resource measurements remain in alignment-results.jsonl. Chaining a
    # volatile duration here would also randomize all subsequent provenance IDs.
    from artifact_translation.replay import normalized
    return journal.append('SOURCE_CLAIM_REVALIDATION',{
        'raw_result_artifact':'alignment-results.jsonl','semantic_result':normalized(row)})


class ObligationQueue:
    """Bounded data-dependent I/T selection over an explicit existing catalogue."""
    def __init__(self, budget: int = 3):
        if not 1<=budget<=4:raise ValueError('SOURCE_ACTION_BOUND')
        self.budget=budget;self.used: set[str]=set();self.executed=0

    def choose(self, obligations: list[dict], actions: list[dict]) -> dict:
        if not obligations:return {'stop':'DONE_BOUNDED_RECONSTRUCTION'}
        available=[a for a in actions if a['id'] not in self.used]
        if not available:return {'stop':'CATALOGUE_EXHAUSTED'}
        if self.executed>=self.budget:return {'stop':'BUDGET_EXHAUSTED'}
        scored=[(len({o['kind'] for o in obligations}&set(a['covers'])),a) for a in available]
        scored=[x for x in scored if x[0]>0]
        if not scored:return {'stop':'CAPABILITY_UNSUPPORTED','unhandled':[o['kind'] for o in obligations]}
        score,action=sorted(scored,key=lambda x:(-x[0],x[1].get('cost',1),x[1]['id']))[0]
        return {'action':action,'covers_obligations':score,'policy':'Most declared obligation kinds, then cost, then source address; no target-truth ranking.'}

    def complete(self, action: dict) -> None:
        if action['id'] in self.used:raise ValueError('DUPLICATE_OBLIGATION_ACTION')
        self.used.add(action['id']);self.executed+=1
