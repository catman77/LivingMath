"""Raw competing readings, without source critic, gold labels or target evaluator."""
import re
from typing import Any

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from .contract import PAIRS, quoted


def _role(span, start: int, end: int, slot: str) -> dict:
    return {'id': 'mention_' + digest([span.id, start, end, slot])[:20],
            'name': span.text[start:end], 'span_id': span.id,
            'start': span.start + len(span.text[:start].encode()),
            'end': span.start + len(span.text[:end].encode()),
            'slot': slot, 'reference_identity': 'UNRESOLVED'}


def roles(packet: RawPacket, family: str) -> list[dict]:
    """Extract mention addresses; surface identity is not reference identity."""
    spans = packet.spans
    if family == 'anaphora':
        participants = []
        for s in spans:
            m = re.match(r'The (\w+) (?:met|sent|examined) the (\w+)', s.text, re.I)
            if m:
                participants = [_role(s, *m.span(1), 'actor'), _role(s, *m.span(2), 'object')]
            m = re.match(r'Но (\w+) (\w+)', s.text)
            if m:
                participants = [_role(s, *m.span(2), 'actor_form'), _role(s, *m.span(1), 'object_form')]
        if participants:
            for s in spans:
                m = re.search(r'\b(?:He|he|тот|он)\b', s.text)
                if m:
                    participants.append(_role(s, *m.span(), 'anaphor'))
                    break
            return participants
    if family in {'scope', 'identity'}:
        occurrences: dict[str, list[tuple[Any, int, int]]] = {}
        stop = {'this', 'that', 'the', 'with', 'from', 'shall', 'thou'}
        for s in spans:
            for m in re.finditer(r'\b\w{4,}\b', s.text):
                k = m.group().casefold()
                if k not in stop:
                    occurrences.setdefault(k, []).append((s, m.start(), m.end()))
        repeated = [v for v in occurrences.values() if len(v) >= 2]
        if repeated:
            a, b = max(repeated, key=lambda v: (len(v), len(v[0][0].text[v[0][1]:v[0][2]])))[:2]
            return [_role(*a, 'first_mention'), _role(*b, 'second_mention')]
    if family == 'order':
        found = []
        for s in spans:
            m = re.search(r'\bchap(?:ter|iter)\b.*?\bof\s+(.+?)[,.]?(?:$)', s.text, re.I)
            if m:
                found.append(_role(s, *m.span(1), 'chapter_or_operation'))
        if len(found) >= 2:
            return found[:2]
    if family == 'analogy':
        for s in spans:
            m = re.match(r'(.+?),?\s+(?:как|as|like)\s+(.+?)[,.]?$', s.text, re.I)
            if m:
                return [_role(s, *m.span(1), 'described'), _role(s, *m.span(2), 'comparison')]
    if family == 'material_agent':
        for s in spans:
            m = re.match(r'А\s+(\w+)\s+тем\s+(\w+)', s.text)
            if m:
                return [_role(s, *m.span(1), 'actor'), _role(s, *m.span(2), 'instrument')]
    if family == 'actor_object':
        for s in spans:
            m = re.match(r'Но (\w+) (\w+)', s.text)
            if m:
                return [_role(s, *m.span(2), 'actor_form'), _role(s, *m.span(1), 'object_form')]
    chosen = spans[-2:] if family in {'identity', 'necessity'} else [spans[0], spans[-1]]
    if len(chosen) == 1:
        chosen = chosen * 2
    return [_role(s, 0, len(s.text), 'unresolved_event_' + str(i)) for i, s in enumerate(chosen)]


def propose(packet: RawPacket, family: str, project: str = 'LM_QA_GROUNDING003') -> list[dict]:
    if family not in PAIRS:
        raise ValueError('UNKNOWN_GROUNDING_QUESTION')
    rs = roles(packet, family)
    quotes = [quoted(s) for s in packet.spans + packet.context]
    text = '\n'.join(s.text for s in packet.spans)
    out = []
    for claim in PAIRS[family]:
        expected = {'TEXT_ORDER_ONLY': 'UNRESOLVED', 'PROCESS_PREREQUISITE': 'ORDERED'}.get(claim, claim)
        src, dst = rs[0]['id'], rs[1]['id']
        interpretation = 'Relation between the addressed mention/event slots, not physical entities.'
        reference_query = None
        if family == 'anaphora':
            chosen = rs[0] if claim == 'SAME_ROLE' else rs[1]
            reference_query = {'anaphor': rs[2]['id'] if len(rs) == 3 else 'FUTURE_SOURCE_MENTION_NOT_YET_ADDRESSED',
                               'candidate_referent': chosen['id'], 'comparison_anchor': rs[0]['id'],
                               'comparison': claim, 'actor_and_object_identity_asserted': False}
            if len(rs) == 3:
                src, dst = rs[2]['id'], chosen['id']
            interpretation = 'Observed/future pronoun selects one participant, compared with the first actor. SAME_ROLE never merges actor and object.'
        h = {'project': project, 'packet_id': packet.id, 'source_packet_sha256': digest(packet.model_dump()), 'document_id': packet.document_id,
             'document_sha256': packet.document_sha256, 'edition': packet.edition,
             'source_spans': [e['span_id'] for e in quotes], 'quoted_evidence': quotes,
             'roles': rs, 'family': family,
             'proposed_relation': {'kind': 'order' if family == 'order' else 'role',
                                   'src': src, 'dst': dst, 'claim': claim,
                                   'interpretation': interpretation, 'reference_query': reference_query,
                                   'relation_level': 'ARGUMENT_SLOTS_NOT_ENTITY_EQUALITY' if family in {'actor_object', 'material_agent'} else 'SPECIFIC_SOURCE_MENTIONS_OR_EVENTS'},
             'argument': {'basis': 'Two addressed surface mentions/events permit competing bindings.',
                          'falsifier': 'Disjoint explicit definition, counterreference or scope restriction.'},
             'alternatives': [v for v in PAIRS[family] if v != claim],
             'prediction': {'label': expected, 'evidence_required': 'New, exact-addressed independent context distinguishing the two readings.',
                            'target_free': True, 'reference_anchor': rs[0]['name']},
             'negation': bool(re.search(r'\b(?:not|no|never|neuer|не|ни)\b', text, re.I)),
             'modality': 'SOURCE_UTTERANCE_NOT_ESTABLISHED_EVENT', 'counterevidence': [],
             'confidence_status': 'UNVERIFIED', 'target_binding': None, 'proposer': 'NO_LLM_PROPOSER',
             'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
        h['hypothesis_id'] = digest(h)
        out.append(h)
    return out
