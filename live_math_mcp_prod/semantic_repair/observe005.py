"""Registered, bounded source projections. Grammar rules never receive task IDs.

Open engineering calibrations informed these rules (CODE_AGENT_PROPOSAL).
Unparsed clauses and interpretive assumptions remain visible; this is not a
general semantic parser. No lexical emotion equivalence or causal completion.
"""
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from semantic_grounding.contract import quoted
from .observe import observe as legacy, norm

STRATEGIES = ('clauses005/1', 'discourse005/1')


def observe(packet: RawPacket, *, strategy: str = STRATEGIES[0]) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError('UNREGISTERED_OBSERVER_STRATEGY')
    old = legacy(packet); spans = packet.spans + packet.context
    ps = []; mentions = []; labels = {}; consumed: set[str] = set(); seen = set()
    section = spans[0].source_address.get('section', packet.document_id) if spans else packet.document_id
    scope = 's_' + digest([packet.document_sha256, packet.edition, section])[:24]
    domain = 'local_domain_' + digest([packet.document_sha256, packet.edition, section])[:20]

    def add(a, b, refs, *, modality='TEXTUAL_CLAIM', semantics='CONDITIONAL',
            quantifier='ALL', time='CONDITIONAL_SCHEMA', assumptions=(), participant='scoped_argument',
            guard='', source_roles=None):
        # An explicit metatextual reading instruction is not part of a predicate.
        b = re.sub(r';\s*this vnderstand\s*$', '', b, flags=re.I)
        a, b = norm(a), norm(b)
        if not a or not b or a == b:
            return
        roles = []
        for i, label in enumerate([a, b]):
            pid = 'p_' + digest(label)[:24]; labels[pid] = label
            mid = 'mention_' + digest([refs[0].id, a, b, i])[:20]
            role = {'predicate': pid, 'mention_ref': mid, 'scope': scope,
                    'stage': guard or 'SCHEMATIC', 'modality': modality, 'domain': domain,
                    'quantifier': quantifier, 'polarity': 'POSITIVE', 'participant': participant, 'time': time}
            if source_roles:
                # Preserve an explicitly different polarity/stage; never guess
                # that similar labels make incompatible roles identical.
                role.update({k: source_roles[i][k] for k in ['stage']})
            roles.append(role)
            mentions.append({'id': mid, 'mention_ref': refs[min(i, len(refs)-1)].id,
                'source_quote': refs[min(i, len(refs)-1)].text, 'predicate_label': label,
                'referent_candidate': 'UNRESOLVED', 'sense_candidate': 'UNRESOLVED',
                'event_role': participant, 'state_coordinate': None, 'scope': scope})
        semantic = [a, b, scope, modality, semantics, quantifier, time, participant, guard, list(assumptions)]
        key = digest(semantic)
        if key in seen:
            consumed.update(s.id for s in refs); return
        seen.add(key); consumed.update(s.id for s in refs)
        ps.append({'id': 'u_' + key[:24], 'src': roles[0], 'dst': roles[1],
            'relation': 'role' if semantics == 'NORMATIVE_CONNECTIVITY' else 'condition',
            'source_refs': sorted({s.id for s in refs}), 'premise_unit': key,
            'source_hash': packet.document_sha256, 'observer_version': strategy,
            'semantics': semantics, 'assumptions': list(assumptions)})

    # Preserve existing explicit bonds, relative quantification, and calibration
    # conditionals. Their finite reading is stated, rather than upgrading to fact.
    by = {s.id: s for s in spans}
    for p in old['premises']:
        a, b = [old['labels'][p[k]['predicate']] for k in ['src', 'dst']]
        refs = [by[r] for r in p['source_refs']]
        normative = p['relation'] == 'role'
        causal = any(re.search(r'is cause of', s.text, re.I) for s in refs)
        add(a, b, refs, modality=p['src']['modality'],
            semantics='NORMATIVE_CONNECTIVITY' if normative else ('UNKNOWN' if causal else 'CONDITIONAL'),
            time='NORMATIVE_SCHEMA' if normative else 'CONDITIONAL_SCHEMA',
            assumptions=('Text-internal prescribed connectivity only.',) if normative else ('Conditional textual reading; domain remains local.',),
            source_roles=[p['src'], p['dst']])
    dimensions = list(old['dimensions'])
    if strategy == STRATEGIES[1]:
        # Multiline WHEN with optional implicit THEN, including "That when".
        # It creates separate conditions, not an unattested bridge between them.
        for i, s in enumerate(spans[:-1]):
            m = re.search(r'\bwhen\s+(.+?)[,;:]?$', s.text.strip(), re.I)
            following = spans[i+1].text.strip()
            if m and re.match(r'(?:Then\s+)?(?:A |the |is |may )', following, re.I):
                add(m.group(1), re.sub(r'^Then\s+', '', following, flags=re.I), [s, spans[i+1]],
                    assumptions=('Conditional textual reading; domain remains local.',))
        # Equivalent punctuation-delimited clause on one or several lines.
        # Track every overlapping original span; wrapping never invents bytes.
        joined = ' '.join(s.text.strip() for s in spans)
        ranges = []; offset = 0
        for s in spans:
            ranges.append((offset,offset+len(s.text.strip()),s)); offset += len(s.text.strip())+1
        for m in re.finditer(r'\bwhen\s+([^,;]+?)[,;]\s*(?:Then\s+)?((?:A|the|is|may)\s+[^,;.]+)',joined,re.I):
            refs = [s for a,b,s in ranges if a<m.end() and b>m.start()]
            add(m.group(1),m.group(2),refs,assumptions=('Conditional textual reading; domain remains local.',))
        # Inverted "into A the B ... When guard ... Shall be converted".
        for i in range(len(spans)-2):
            a, b, c = spans[i:i+3]
            m = re.search(r'into (\w+) the (\w+)', a.text, re.I)
            g = re.match(r'When (.+?)[,;.]?$', b.text.strip(), re.I)
            if m and g and re.search(r'shall be conuerted', c.text, re.I):
                add(m.group(2), m.group(1), [a,b,c], guard=norm(g.group(1)),
                    assumptions=('Only under stated guard: '+norm(g.group(1)),))
            m = re.search(r'of the (\w+) then (\w+) haue', a.text, re.I)
            if m and re.match(r'By ', b.text.strip()):
                add(m.group(1), m.group(2), [a,b], guard=norm(b.text),
                    assumptions=('Only under stated guard: '+norm(b.text),))
        # Conditional discourse boundary. Subsequent pronoun predication is
        # retained as sequence under a reading, never as causal implication.
        for i in range(len(spans)-2):
            a,b,c = spans[i:i+3]
            if re.search(r'\bлишь\b', a.text, re.I) and re.search(r'коснется', b.text, re.I):
                add(a.text+' '+b.text, c.text, [a,b,c], modality='LYRICAL_CLAIM',
                    assumptions=('Conditional textual reading; domain remains local.',))
                tail = spans[i+3:]
                for t in tail:
                    if re.search(r'\bон\b', t.text, re.I):
                        add(c.text, t.text, [c,t], modality='LYRICAL_CLAIM', semantics='NARRATIVE_SEQUENCE',
                            quantifier='NAMED_CASE', time='DISCOURSE_SEQUENCE', participant='UNRESOLVED_PRONOUN',
                            assumptions=('Continuation is not a causal bridge; pronoun binding unresolved.',))
        # Rhetorical finite enumeration followed by explicit universal clause.
        # Membership is a conditional grammatical reading of *listed* sounds;
        # no reciprocal response and no identity with the final analogy target.
        all_index = next((i for i,s in enumerate(spans) if re.search(r'на всякий \w+', s.text, re.I)), None)
        if all_index is not None and all_index > 0 and len(spans) > all_index+2:
            lead = spans[:all_index]; tail = spans[all_index:]
            if any(re.search(r'\bли\b', s.text, re.I) for s in lead):
                m = re.search(r'на всякий (\w+)', tail[0].text, re.I)
                assert m is not None
                category = m.group(1)
                assumptions = ('Rhetorical list instantiates the following local universal; finite listed cases only.',)
                response = ' '.join(s.text for s in tail[1:])
                for s in lead:
                    for item in re.split(r'[,;]', s.text):
                        if re.search(r'\bли\b', item, re.I):
                            add(item, category, [s,tail[0]], modality='LYRICAL_CLAIM', semantics='CLASS_INSTANTIATION',
                                assumptions=assumptions, participant='local_addressee')
                add(category, response, tail, modality='LYRICAL_CLAIM', assumptions=assumptions, participant='local_addressee')
                dimensions.append({'id':'d_'+digest([scope,'rhetorical_reference'])[:20], 'kind':'referent',
                    'mention_refs':[s.id for s in tail], 'scope':scope,
                    'values':['LOCAL_DISCOURSE_ADDRESSEE','UNRESOLVED_ADDRESSEE']})
        # Narration records adjacency only; it does not assert touch caused the
        # next transformation, nor turn a subsequent command into performance.
        for i,s in enumerate(spans[:-1]):
            if re.search(r'коснулся\s+он', s.text, re.I):
                add(s.text, spans[i+1].text, [s,spans[i+1]], modality='NARRATED_EVENT',
                    semantics='NARRATIVE_SEQUENCE', quantifier='NAMED_CASE', time='NARRATIVE_LOCAL_ORDER',
                    participant='UNRESOLVED_ACTOR_AND_NARRATOR',
                    assumptions=('Narrated sequence only; causality and command fulfilment not asserted.',))
    trace = [{'span':quoted(s), 'status':'OBSERVED' if s.id in consumed else 'UNPARSED_CLAUSE',
              'function':'semantic_repair.observe005.observe',
              'reason':None if s.id in consumed else 'No installed relation rule; no missing bridge synthesized.'} for s in spans]
    return {'premises':ps, 'mentions':mentions, 'labels':labels, 'dimensions':dimensions,
        'source_evidence':[quoted(s) for s in spans], 'observer':strategy, 'observation_trace':trace,
        'status':'BOUNDED_CONDITIONAL_TEXTUAL_PROJECTION', 'authorship':'CODE_AGENT_PROPOSAL_GENERIC_RULES',
        'unsupported':['Unstated causal bridges','Unresolved referent identity','General metaphor and physical identification']}
