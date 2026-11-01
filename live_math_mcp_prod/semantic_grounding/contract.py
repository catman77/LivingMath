"""Address/evidence contracts. These records add no executable expression language."""
from typing import Literal

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from davcore.models import StrictModel

Family = Literal['order', 'scope', 'identity', 'necessity', 'anaphora', 'analogy',
                 'actor_object', 'material_agent']

PAIRS = {
    'order': ('TEXT_ORDER_ONLY', 'PROCESS_PREREQUISITE'),
    'scope': ('SAME_ROLE', 'DIFFERENT_ROLE'),
    'identity': ('SAME_ROLE', 'DIFFERENT_ROLE'),
    'necessity': ('ORDERED', 'UNRESOLVED'),
    'anaphora': ('SAME_ROLE', 'DIFFERENT_ROLE'),
    'analogy': ('SAME_ROLE', 'ANALOGY_ONLY'),
    'actor_object': ('SAME_ROLE', 'DIFFERENT_ROLE'),
    'material_agent': ('SAME_ROLE', 'DIFFERENT_ROLE'),
}


class ProposalRequest(StrictModel):
    packet: RawPacket
    family: Family
    project: str


class CritiqueRequest(StrictModel):
    train: RawPacket
    challenge: RawPacket
    family: Family
    project: str


def quoted(span) -> dict:
    return {'span_id': span.id, 'document_id': span.document_id,
            'document_sha256': span.document_sha256, 'edition': span.edition,
            'start': span.start, 'end': span.end, 'quote': span.text}


def independent_spans(train: RawPacket, evidence: RawPacket) -> None:
    if (train.document_id, train.document_sha256, train.edition) != (
        evidence.document_id, evidence.document_sha256, evidence.edition
    ):
        raise ValueError('CROSS_SOURCE_EDITION_OR_HASH')
    if not evidence.spans:
        raise ValueError('EMPTY_INDEPENDENT_SOURCE_EVIDENCE')
    for a in train.spans + train.context:
        for b in evidence.spans + evidence.context:
            if a.id == b.id or max(a.start, b.start) < min(a.end, b.end):
                raise ValueError('PROPOSAL_EVIDENCE_OVERLAP')


def validate_pair(rows: list[dict], packet: RawPacket, project: str = 'LM_QA_GROUNDING003') -> None:
    if len(rows) != 2 or len({h['hypothesis_id'] for h in rows}) != 2:
        raise ValueError('TWO_DISTINCT_COMPETING_H_REQUIRED')
    if rows[0]['prediction']['label'] == rows[1]['prediction']['label']:
        raise ValueError('NONDISCRIMINATING_PREDICTIONS')
    spans = {s.id: s for s in packet.spans + packet.context}
    for h in rows:
        if h['project'] != project:
            raise ValueError('CROSS_PROJECT_HYPOTHESIS')
        if (h['document_id'], h['document_sha256'], h['edition']) != (
            packet.document_id, packet.document_sha256, packet.edition
        ):
            raise ValueError('H_SOURCE_BINDING_DRIFT')
        if h['target_binding'] is not None or h['proof_status'] != 'unverified' or h['execution_permission'] != {'allowed': False}:
            raise ValueError('RAW_H_HAS_TARGET_OR_AUTHORITY')
        refs = set()
        for e in h['quoted_evidence']:
            if e['span_id'] not in spans or e != quoted(spans[e['span_id']]):
                raise ValueError('FALSE_SOURCE_QUOTE_OR_ADDRESS')
            refs.add(e['span_id'])
        if not refs or set(h['source_spans']) != refs:
            raise ValueError('SOURCE_REFS_DISAGREE')
        for role in h['roles']:
            s = spans[role['span_id']]
            if role['span_id'] not in refs or not s.start <= role['start'] < role['end'] <= s.end:
                raise ValueError('ROLE_OUTSIDE_SOURCE_EVIDENCE')
            if s.text.encode()[role['start']-s.start:role['end']-s.start].decode() != role['name']:
                raise ValueError('ROLE_QUOTE_DRIFT')
        expected = {k: v for k, v in h.items() if k != 'hypothesis_id'}
        if digest(expected) != h['hypothesis_id']:
            raise ValueError('HYPOTHESIS_HASH_DRIFT')
