"""Addressed S/H transport; speech and observation are not executable changes."""
import hashlib
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest

from .inference011 import canonical_packet
from .observe009 import observe as registered_observer
from .observe011 import source_nodes
from .relations012 import SourceProposals012, SourceReview012

DIMENSIONS = {'participant', 'referent', 'predicate', 'quantifier', 'polarity',
    'tense', 'modal', 'scope', 'text_order_vs_event_order', 'projection'}


def align(packet: dict, proposals: dict, review: dict | None, *, assurance: str = 'REAL_LLM_SOURCE_PROPOSER') -> dict:
    raw = RawPacket.model_validate(packet)
    canonical, mapping = canonical_packet(packet)
    spans = {s['id']: s for s in canonical['spans'] + canonical['context']}
    proposed = SourceProposals012.model_validate(proposals)
    reviewed = SourceReview012.model_validate(review) if review is not None else None
    decisions = {(a.reading_id, a.relation_id): a for a in reviewed.assessments} if reviewed else {}
    if reviewed and len(decisions) != len(reviewed.assessments):
        raise ValueError('DUPLICATE_SOURCE_CRITIC_ASSESSMENT')
    valid = {(h.id, r.id) for h in proposed.readings for r in h.relations}
    if set(decisions) - valid:
        raise ValueError('CRITIC_REFERENCES_FOREIGN_RELATION')
    observation = registered_observer(raw)
    alignment: list[dict] = []
    losses: list[dict] = []

    def exact(c):
        return c.ref in spans and c.quote in spans[c.ref]['text']

    def addresses(citations):
        result = []
        for c in citations:
            if not exact(c): continue
            span = spans[c.ref]; text = span['text']; offset = 0; matches = []
            while (index := text.find(c.quote, offset)) >= 0:
                start = span['start'] + len(text[:index].encode())
                matches.append([start, start + len(c.quote.encode())])
                offset = index + max(1, len(c.quote))
            result.append({'ref': mapping[c.ref], 'quote_sha256': hashlib.sha256(c.quote.encode()).hexdigest(),
                'byte_ranges': matches, 'ambiguous_occurrence': len(matches) != 1})
        return result

    def quote_guard(citations):
        flags = []
        for c in citations:
            if not exact(c): continue
            text = spans[c.ref]['text']
            quoted = []
            for match in re.finditer(r'«([^»]*)»|“([^”]*)”|"([^"]*)"', text):
                n = next(i for i in (1, 2, 3) if match.group(i) is not None)
                quoted.append((match.start(n), match.end(n)))
            hits = [m.start() for m in re.finditer(re.escape(c.quote), text)]
            for start in hits:
                end = start + len(c.quote)
                flags.append('INSIDE' if any(a <= start and end <= b for a, b in quoted)
                    else 'OVERLAP' if any(start < b and end > a for a, b in quoted) else 'OUTSIDE')
        return 'REPORTED' if flags and all(v == 'INSIDE' for v in flags) else 'AMBIGUOUS' if any(v != 'OUTSIDE' for v in flags) else 'NOT_QUOTED'

    for reading in proposed.readings:
        states = source_nodes(reading)
        originals = {s.id for s in reading.states}
        grounded = {key: all(exact(c) for c in state.evidence) and all(exact(f.evidence) for f in state.features)
            for key, state in states.items()}
        admitted = set(originals)

        def state_descriptor(state, reading=reading, originals=originals):
            fs = sorted(state.features, key=lambda f: (spans[f.evidence.ref]['start'], spans[f.evidence.ref]['text'].find(f.evidence.quote)))
            anchors = [(f.evidence.ref, f.evidence.quote) for f in fs]
            known_order = len(set(anchors)) == len(anchors) and all(spans[f.evidence.ref]['text'].count(f.evidence.quote) == 1 for f in fs)
            return {'key': reading.id + ':' + state.id, 'label': state.label,
                'features': [f.feature for f in fs], 'source_refs': sorted({mapping[c.ref] for c in state.evidence + [f.evidence for f in fs] if exact(c)}),
                'feature_order_known': known_order, 'feature_multiplicity_known': known_order,
                'node_kind': 'predicate' if state.id in originals else 'textual_clause',
                'source_coordinates': {k: getattr(state, k) for k in ('participant', 'referent', 'quantifier', 'polarity', 'modality', 'tense', 'scope')},
                'addresses': addresses(state.evidence), 'feature_addresses': addresses([f.evidence for f in fs]),
                'level': getattr(state, 'level', 'SOURCE_EVENT')}

        profiles = []
        for observer in reading.observers:
            samples = []
            profile_grounded = all(exact(c) for c in observer.evidence)
            for sample in observer.samples:
                values = {}
                proofs = {}
                for v in sample.values:
                    known = profile_grounded and v.value is not None and bool(v.evidence) and all(exact(c) for c in v.evidence)
                    values[v.feature] = v.value if known else None
                    proofs[v.feature] = addresses(v.evidence)
                    if v.value is not None and not known:
                        losses.append({'reason': 'UNGROUNDED_OBSERVATION_VALUE', 'critical': True,
                            'reading_id': reading.id, 'observer_id': observer.id, 'state_id': sample.state_id, 'feature': v.feature})
                samples.append({'state_key': reading.id + ':' + sample.state_id,
                    'values': {f: values.get(f) for f in observer.features}, 'addresses': proofs})
            profiles.append({'id': reading.id + ':' + observer.id, 'owner': observer.owner,
                'criterion': observer.criterion, 'features': observer.features, 'samples': samples,
                'addresses': addresses(observer.evidence), 'source_status': 'HYPOTHESIS' if profile_grounded else 'UNSUPPORTED'})
        premises = []
        for relation in reading.relations:
            audit = decisions.get((reading.id, relation.id))
            status = audit.status if audit else 'UNKNOWN'
            citations = relation.evidence + relation.source_claim.evidence + relation.source_claim.speaker_evidence
            okay = all(exact(c) for c in citations) and grounded[relation.src] and grounded[relation.dst]
            flags = []
            if not okay:
                losses.append({'reason': 'UNGROUNDED_SOURCE_CLAIM', 'critical': True, 'reading_id': reading.id,
                    'relation_id': relation.id, 'addresses': addresses(citations)})
                continue
            if audit is None or set(audit.distinctions_checked) != DIMENSIONS or not audit.attribution_checked or not audit.observer_mask_checked:
                status = 'UNKNOWN'; flags.append('INCOMPLETE_SOURCE_REVIEW')
            elif not all(exact(c) for c in audit.evidence):
                status = 'UNSUPPORTED'; flags.append('UNGROUNDED_CRITIC')
            source_claim = relation.source_claim
            if source_claim.mode in {'ATTRIBUTED', 'QUOTED'} and not source_claim.speaker_evidence:
                status = 'UNKNOWN'; flags.append('SPEAKER_NOT_ADDRESSED')
            quoted = quote_guard(source_claim.evidence)
            if quoted != 'NOT_QUOTED' and source_claim.mode not in {'ATTRIBUTED', 'QUOTED'}:
                status = 'UNKNOWN'; flags.append('ATTRIBUTION_SCOPE_REQUIRES_REVIEW')
            endpoints = {relation.src, relation.dst}
            if len(admitted | endpoints) > 8:
                losses.append({'reason': 'SOURCE_EVENT_REIFICATION_BOUND', 'critical': True,
                    'reading_id': reading.id, 'relation_id': relation.id, 'addresses': addresses(citations)})
                continue
            admitted |= endpoints
            left, right = state_descriptor(states[relation.src]), state_descriptor(states[relation.dst])
            claim = {'id': 'claim_' + digest([raw.document_sha256, reading.id, relation.model_dump()])[:24],
                **source_claim.model_dump(exclude={'evidence', 'speaker_evidence'}),
                'observer_id': reading.id + ':' + source_claim.observer_id if source_claim.observer_id else None,
                'addresses': addresses(citations),
                'source_status': status, 'quotation_guard': quoted}
            scope = 's_' + digest([raw.document_sha256, reading.id])[:24]

            def role(state, descriptor, scope=scope):
                return {'predicate': 'p_' + digest(descriptor['key'])[:24], 'mention_ref': descriptor['source_refs'][0],
                    'scope': scope, 'stage': descriptor['key'], 'domain': scope,
                    'modality': 'PRESCRIPTION' if state.modality == 'PRESCRIBED' else 'NARRATED_EVENT' if state.modality == 'NARRATED' else 'TEXTUAL_CLAIM',
                    'quantifier': state.quantifier, 'polarity': state.polarity if state.polarity != 'CONFLICT' else 'UNKNOWN',
                    'participant': state.participant, 'time': state.tense}
            descriptor = {'version': 'source-transition012/1', 'source': left, 'target': right,
                'relation_kind': relation.kind, 'polarity': relation.polarity, 'modality': relation.modality,
                'order_kind': relation.order_kind, 'critic_status': status, 'review_flags': flags,
                'claim': {k: getattr(relation, k) for k in ('predicate', 'participant', 'referent', 'quantifier', 'tense', 'scope')},
                'source_projection': {k: getattr(relation, k) for k in ('projection', 'projection_features', 'interpretation_note')},
                'source_claim': claim, 'interpretation_assumptions': relation.interpretation_assumptions,
                'executable_assumption_supported': bool(audit and audit.executable_assumption_supported and status == 'HYPOTHESIS')}
            refs = sorted(set(left['source_refs'] + right['source_refs'] + [mapping[c.ref] for c in citations]))
            body = {'src': role(states[relation.src], left), 'dst': role(states[relation.dst], right),
                'relation': 'condition', 'source_refs': refs, 'source_hash': raw.document_sha256,
                'observer_version': 'discourse005/1', 'semantics': 'UNKNOWN', 'assumptions': [],
                'realization': {'version': 'typed008/1', 'kind': 'STATE_TRANSITION', 'guards': [],
                    'source_order': min(spans[c.ref]['start'] for c in relation.evidence),
                    'occurrence_id': 'occ_' + digest(claim['id'])[:24], 'label': relation.predicate, 'transition': descriptor}}
            premises.append(body)
            alignment.append({'reading_id': reading.id, 'relation_id': relation.id, 'status': status,
                'exact_citations': okay, 'source_refs': refs, 'source_assessment': audit.model_dump() if audit else None,
                'review_flags': flags, 'source_verified': False})
        if premises:
            first = premises[0]['realization']['transition']
            first.update(observers=profiles, declared_states=[state_descriptor(s) for key, s in states.items() if key in admitted and grounded[key]],
                initial_keys=[reading.id + ':' + key for key in reading.initial_state_ids])
            extra_refs = {ref for s in first['declared_states'] for ref in s['source_refs']}
            for profile in profiles:
                extra_refs.update(a['ref'] for a in profile['addresses'])
                extra_refs.update(a['ref'] for sample in profile['samples'] for aa in sample['addresses'].values() for a in aa)
            premises[0]['source_refs'] = sorted(set(premises[0]['source_refs']) | extra_refs)
            for p in premises:
                unit = digest(p); p.update(id='u_' + unit[:24], premise_unit=unit)
            observation['slices'].append({'kind': 'STATE_TRANSITION', 'premises': premises,
                'dimensions': [{'id': 'observation', 'values': ['SOURCE_SCOPED012'], 'kind': 'NAMED_SOURCE_OBSERVERS'}]})
        losses += [{'reason': 'UNKNOWN_LINK', 'reading_id': reading.id, 'detail': s, 'critical': False} for s in reading.unknowns]
    observation.update(observer='observer012/1', source_proposals=proposals, source_critic=review,
        source_alignment={'version': 'alignment012/1', 'relations': alignment}, general_source_loss_ledger=losses,
        proposer_assurance=assurance, source_semantics='QUOTED_ATTRIBUTED_HYPOTHESES_NOT_WORLD_FACTS')
    observation['source_coverage_losses'] += losses
    return observation
