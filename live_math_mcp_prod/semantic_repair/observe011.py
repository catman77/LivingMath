"""Independent address critic and source-first alignment to existing Premise/H."""
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from semantic_repair.inference011 import canonical_packet
from semantic_repair.observe009 import observe as registered_observer
from semantic_repair.relations011 import SourceProposals, SourceReview, SemanticState

NEGATION = re.compile(r'\b(?:не|нет|нельзя|никогда|not|never|no|without)\b', re.I)
KINETIC = {'TRANSITION', 'SEQUENCE', 'CONDITION'}


def source_nodes(reading):
    """Reify addressed textual occurrences, never physical identities or features."""
    nodes = {s.id: s for s in reading.states}
    referenced = {v for r in reading.relations for v in (r.src, r.dst)} - nodes.keys()
    for relation in reading.relations:
        if relation.id in referenced:
            nodes[relation.id] = SemanticState.model_validate({
                'id': relation.id, 'label': relation.predicate, 'evidence': relation.evidence,
                'features': [], **{k: getattr(relation, k) for k in
                    ('participant', 'referent', 'polarity', 'tense', 'modality', 'quantifier', 'scope')}})
    return nodes


def source_critic(packet: dict, proposals: dict, review: dict | None) -> dict:
    """Exact address/provenance checks do not certify natural-language meaning."""
    canonical, mapping = canonical_packet(packet)
    spans = {s['id']: s for s in canonical['spans'] + canonical['context']}
    proposed = SourceProposals.model_validate(proposals)
    reviewed = SourceReview.model_validate(review) if review is not None else None
    decisions = {}
    losses = []
    dimensions = {'participant', 'referent', 'predicate', 'quantifier', 'polarity',
        'tense', 'modal', 'scope', 'text_order_vs_event_order', 'projection'}
    if reviewed:
        for assessment in reviewed.assessments:
            key = (assessment.reading_id, assessment.relation_id)
            if key in decisions:
                raise ValueError('DUPLICATE_INDEPENDENT_CRITIC_ASSESSMENT')
            decisions[key] = assessment.model_dump()
    def exact(citation):
        return citation.ref in spans and citation.quote in spans[citation.ref]['text']
    grounded_states = {}
    aligned = []
    for reading in proposed.readings:
        for state in source_nodes(reading).values():
            okay = all(exact(c) for c in state.evidence) and all(exact(f.evidence) for f in state.features)
            grounded_states[(reading.id, state.id)] = okay
            if not okay:
                losses.append({'reason': 'UNGROUNDED_STATE_OR_FEATURE', 'reading_id': reading.id, 'state_id': state.id})
        for relation in reading.relations:
            key = (reading.id, relation.id)
            assessment = decisions.get(key)
            status = assessment['status'] if assessment else 'UNKNOWN'
            flags = []
            if not assessment:
                flags.append('NO_INDEPENDENT_SOURCE_REVIEW')
            elif assessment['status'] == 'HYPOTHESIS' and (
                    not assessment['evidence'] or set(assessment['distinctions_checked']) != dimensions):
                status = 'UNKNOWN'
                flags.append('INCOMPLETE_INDEPENDENT_SOURCE_REVIEW')
            cited = all(exact(c) for c in relation.evidence)
            cited &= all(grounded_states[(reading.id, endpoint)] for endpoint in (relation.src, relation.dst))
            if assessment and not all(exact(type(relation.evidence[0]).model_validate(c)) for c in assessment['evidence']):
                flags.append('UNGROUNDED_CRITIC_CITATION')
                status = 'UNSUPPORTED'
            if not cited:
                status = 'UNSUPPORTED'
                flags.append('UNGROUNDED_SOURCE_ANNOTATION')
            if relation.kind in KINETIC and relation.polarity == 'POSITIVE' and any(NEGATION.search(c.quote) for c in relation.evidence):
                # Conservative scope warning, never automatic linguistic refutation.
                flags.append('POLARITY_SCOPE_REQUIRES_REVIEW')
                status = 'CONFLICT' if status == 'CONFLICT' else 'UNKNOWN'
            refs = sorted({mapping[c.ref] for c in relation.evidence if c.ref in mapping})
            aligned.append({'reading_id': reading.id, 'relation_id': relation.id,
                'status': status, 'exact_citations': cited, 'source_refs': refs,
                'source_assessment': assessment, 'review_flags': flags,
                'semantic_assurance': 'SOURCE_HYPOTHESIS_NOT_TRUTH_VERIFICATION'})
    valid_keys = {(r.id, rel.id) for r in proposed.readings for rel in r.relations}
    if set(decisions) - valid_keys:
        raise ValueError('CRITIC_REFERENCES_FOREIGN_RELATION')
    return {'version': 'alignment011/1', 'relations': aligned, 'losses': losses,
        'independent_source_review': reviewed is not None, 'proof_status': 'unverified'}


def align(packet: dict, proposals: dict, review: dict | None, *, assurance='REAL_LLM_SOURCE_PROPOSER') -> dict:
    raw = RawPacket.model_validate(packet)
    observation = registered_observer(raw)
    canonical, mapping = canonical_packet(packet)
    by = {s['id']: s for s in canonical['spans'] + canonical['context']}
    alignment = source_critic(packet, proposals, review)
    decisions = {(a['reading_id'], a['relation_id']): a for a in alignment['relations']}
    proposed = SourceProposals.model_validate(proposals)
    additions = []
    ledger = list(alignment['losses'])
    scope = 's_' + digest([raw.document_sha256, raw.edition, 'source011'])[:24]
    for reading in proposed.readings:
        states = source_nodes(reading)
        original_states = {s.id for s in reading.states}
        admitted = set(original_states)
        premises = []
        scope_flags = []
        if any(r.kind == 'REPEAT' and r.polarity in {'NEGATIVE', 'CONFLICT'} for r in reading.relations):
            scope_flags.append('NEGATED_REPEAT_IN_SCOPE')
        if any(decisions[(reading.id, r.id)]['status'] == 'CONFLICT' for r in reading.relations):
            scope_flags.append('SOURCE_CONFLICT_RETAINED')
        for relation in reading.relations:
            decision = decisions[(reading.id, relation.id)]
            additions_needed = {relation.src, relation.dst} - admitted
            if len(admitted | additions_needed) > 8:
                ledger.append({'reason': 'TEXTUAL_EVENT_REIFICATION_BOUND',
                    'reading_id': reading.id, 'relation_id': relation.id,
                    'source_refs': decision['source_refs'], 'preserved_in_source_proposal': True})
                continue
            if relation.src == relation.dst and relation.kind in {'ORDER', 'REORDERED', 'NEGATED'}:
                ledger.append({'reason': 'SOURCE_ONLY_SELF_METARELATION', **decision})
                continue
            if not decision['exact_citations']:
                ledger.append({'reason': 'UNSUPPORTED_SOURCE_RELATION', **decision})
                continue
            admitted.update(additions_needed)
            refs = set(decision['source_refs'])
            def state(s):
                citations = list(s.evidence) + [f.evidence for f in s.features]
                source_refs = sorted({mapping[c.ref] for c in citations})
                refs.update(source_refs)
                # The projection's presentation order is checked independently
                # from proposer list order; the feature naming remains a hypothesis.
                features = sorted(s.features, key=lambda f: (by[f.evidence.ref]['start'],
                    by[f.evidence.ref]['text'].find(f.evidence.quote)))
                anchors = [(f.evidence.ref, f.evidence.quote) for f in features]
                unique = len(set(anchors)) == len(anchors)
                located = all(by[f.evidence.ref]['text'].count(f.evidence.quote) == 1 for f in features)
                if not unique or not located:
                    ledger.append({'reason': 'AMBIGUOUS_FEATURE_OCCURRENCE_OR_MULTIPLICITY',
                        'reading_id': reading.id, 'state_id': s.id, 'source_refs': source_refs})
                return {'key': reading.id + ':' + s.id, 'label': s.label,
                    'features': [f.feature for f in features], 'source_refs': source_refs,
                    'node_kind': 'predicate' if s.id in original_states else 'textual_clause',
                    'feature_order_known': unique and located,
                    'feature_multiplicity_known': unique and located}
            left, right = state(states[relation.src]), state(states[relation.dst])
            def role(s, descriptor):
                return {'predicate': 'p_' + digest([scope, descriptor['key']])[:24],
                    'mention_ref': descriptor['source_refs'][0], 'scope': scope,
                    'stage': 'SOURCE_STATE_' + descriptor['key'],
                    'modality': {'ASSERTED': 'TEXTUAL_CLAIM', 'NARRATED': 'NARRATED_EVENT',
                        'PRESCRIBED': 'PRESCRIPTION', 'CONDITIONAL': 'TEXTUAL_CLAIM',
                        'POSSIBLE': 'UNKNOWN', 'UNKNOWN': 'UNKNOWN'}[s.modality],
                    'domain': 'source_' + digest([raw.document_sha256, reading.id])[:24],
                    'quantifier': s.quantifier, 'polarity': s.polarity if s.polarity != 'CONFLICT' else 'UNKNOWN',
                    'participant': s.participant, 'time': s.tense}
            descriptor = {'version': 'source-transition011/1', 'source': left, 'target': right,
                'relation_kind': relation.kind, 'polarity': relation.polarity,
                'modality': relation.modality, 'order_kind': relation.order_kind,
                'projection_features': relation.projection_features, 'critic_status': decision['status'],
                'review_flags': decision['review_flags'] + scope_flags,
                'claim': {k: getattr(relation, k) for k in
                    ('predicate', 'participant', 'referent', 'quantifier', 'tense', 'scope')}}
            body = {'src': role(states[relation.src], left), 'dst': role(states[relation.dst], right),
                'relation': 'condition', 'source_refs': sorted(refs), 'source_hash': raw.document_sha256,
                'observer_version': 'discourse005/1', 'semantics': 'UNKNOWN',
                'assumptions': ['Conditional source reading ' + reading.id,
                    'Natural-language rationale remains in the source ledger, not the compiler.',
                    'Source critic: ' + decision['status']],
                'realization': {'version': 'typed008/1', 'kind': 'STATE_TRANSITION',
                    'guards': [], 'source_order': min(by[c.ref]['start'] for c in relation.evidence),
                    'occurrence_id': 'occ_' + digest([raw.document_sha256, reading.id, relation.id])[:24],
                    'label': relation.predicate, 'transition': descriptor}}
            unit = digest(body)
            premises.append({**body, 'id': 'u_' + unit[:24], 'premise_unit': unit})
            if decision['status'] != 'HYPOTHESIS':
                ledger.append({'reason': 'SOURCE_RELATION_' + decision['status'], **decision})
        if premises and any(p['realization']['transition']['relation_kind'] in KINETIC for p in premises):
            additions.append({'kind': 'STATE_TRANSITION', 'premises': premises,
                'dimensions': [{'id': 'observation', 'values': ['SEQUENCE', 'MULTISET', 'SET', 'PARTIAL_SET'],
                    'kind': 'explicit_source_observer_projection'}]})
        elif premises:
            ledger.append({'reason': 'SOURCE_ONLY_RELATIONS_NO_DECLARED_EXECUTABLE_TRANSITION',
                'reading_id': reading.id, 'relation_ids': [p['id'] for p in premises]})
        for unknown in reading.unknowns:
            ledger.append({'reason': 'UNKNOWN_LINK', 'reading_id': reading.id, 'detail': unknown})
    observation['slices'] += additions
    observation.update(observer='general011/1', source_proposals=proposals,
        source_critic=review, source_alignment=alignment, general_source_loss_ledger=ledger,
        proposer_assurance=assurance, source_semantics='CONDITIONAL_HYPOTHESES')
    covered = {r for s in observation['slices'] for p in s['premises'] for r in p['source_refs']}
    observation['unparsed_refs'] = sorted({s.id for s in raw.spans + raw.context} - covered)
    observation['source_coverage_losses'] += ledger
    return observation


def symbolic_fallback(packet: dict) -> dict:
    """Useful legacy partials without pretending to have a general model."""
    observation = registered_observer(RawPacket.model_validate(packet))
    observation.update(observer='general011/1', proposer_assurance='NO_GENERAL_SEMANTIC_PROPOSER',
        source_proposals={'version': 'source-relations011/1', 'readings': [],
            'losses': ['No owner-authorized model backend; only registered009 partials are available.']},
        general_source_loss_ledger=[{'reason': 'NO_GENERAL_SEMANTIC_PROPOSER'}])
    return observation
