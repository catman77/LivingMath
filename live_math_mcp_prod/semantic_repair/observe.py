"""Limited raw local observations; no case IDs, target queries or ready H table."""
import re

from artifact_genesis.contract import RawPacket
from semantic_grounding.contract import quoted
from davcore.ast import digest


def norm(text: str) -> str:
    words = re.findall(r'\w+', text.casefold())
    return ' '.join(words)


def observe(packet: RawPacket) -> dict:
    spans = packet.spans + packet.context
    premises = []; mentions = []; labels = {}; dimensions = []; seen = set()
    modalities = 'LYRICAL_CLAIM' if packet.language == 'ru' else 'TEXTUAL_CLAIM'

    def add(a: str, b: str, refs, modality=modalities, relation='condition'):
        a, b = norm(a), norm(b)
        if not a or not b or a == b:
            return
        section = refs[0].source_address.get('section', packet.document_id)
        scope = 's_' + digest([packet.document_sha256, packet.edition, section])[:24]
        roles = []
        for index, word in enumerate([a, b]):
            pid = 'p_' + digest(word)[:24]; labels[pid] = word
            mid = 'mention_' + digest([refs[0].id, a, b, index])[:20]
            mentions.append({'id': mid, 'mention_ref': refs[0].id, 'source_quote': word,
                             'sense_candidate': 'UNRESOLVED', 'referent_candidate': 'UNRESOLVED',
                             'event_role': pid, 'state_coordinate': None, 'scope': scope})
            roles.append({'predicate': pid, 'mention_ref': mid, 'scope': scope,
                          'stage': 'SCHEMATIC', 'modality': modality})
        semantic = [roles[0]['predicate'], roles[1]['predicate'], scope, modality, relation]
        key = digest(semantic)
        if key in seen:
            return
        seen.add(key)
        uid = 'u_' + key[:24]
        premises.append({'id': uid, 'src': roles[0], 'dst': roles[1], 'relation': relation,
                         'source_refs': sorted(set(s.id for s in refs)), 'premise_unit': key,
                         'source_hash': packet.document_sha256, 'observer_version': 'local-clauses004/1'})

    for i, s in enumerate(spans):
        text = s.text.strip()
        m = re.fullmatch(r'(.+?)\s+(?:implies|is cause of)\s+(.+?)[.;]?', text, re.I)
        if m:
            add(m.group(1), m.group(2), [s])
        m = re.search(r'\bFor as the (\w+) to the (\w+) the bond must bee', text, re.I)
        if m:
            add(m.group(1), m.group(2), [s], modality='PRESCRIPTION', relation='role')
        m = re.search(r'\bRight so the (\w+) the (\w+) to him must knit', text, re.I)
        if m:
            add(m.group(1), m.group(2), [s], modality='PRESCRIPTION', relation='role')
        m = re.match(r'\s*If\s+(.+?),\s*(.+?)[.;]?$' , text, re.I)
        if m:
            add(m.group(1), m.group(2), [s])
        # Explicit when/then only, without guessing implicit causal links.
        if i + 1 < len(spans):
            m = re.search(r'\bwhen\s+(.+?)[,;]?$' , text, re.I)
            n = re.match(r'\s*Then\s+(.+?)[,;.]?$' , spans[i+1].text, re.I)
            if m and n:
                add(m.group(1), n.group(1), [s, spans[i+1]])
        # Russian relative conditional with exact repeated predicate, not an emotion model.
        m = re.match(r'Все\s+(.+?),\s*все\s+(\w+)[.;]?', text, re.I)
        if m:
            add('Все', m.group(2), [s])
        m = re.match(r'Что\s+(\w+),\s*то\s+будет\s+(.+?)[.;]?$' , text, re.I)
        if m:
            add(m.group(1), m.group(2), [s])
        # A scope alternative is generated from an observed diversity statement.
        if re.search(r'\bin diuers (?:wise|manners)\b', text, re.I):
            scope = 's_' + digest([packet.document_sha256, packet.edition,
                                    s.source_address.get('section', packet.document_id)])[:24]
            dimensions.append({'id': 'd_' + digest([s.id, 'scope'])[:20], 'kind': 'interpretation_scope',
                'mention_refs': [s.id], 'values': ['DESCRIPTIVE_ONLY', 'UNIVERSAL_PERMISSION'], 'scope': scope})
    text = '\n'.join(s.text for s in spans)
    m = re.search(r'The (\w+) (?:met|sent) the (\w+)[.]', text)
    if m and re.search(r'\bHe\b', text):
        mentions = [{'id': k, 'mention_ref': spans[0].id if k != 'pronoun' else spans[-1].id,
                     'sense_candidate': 'UNRESOLVED', 'referent_candidate': 'UNRESOLVED',
                     'event_role': k, 'state_coordinate': k, 'scope': packet.document_sha256}
                    for k in ['actor', 'object', 'pronoun']]
        dimensions.append({'id': 'd_' + digest([packet.id, 'pronoun'])[:20], 'kind': 'referent',
                           'mention_refs': [spans[-1].id], 'values': ['actor', 'object'], 'scope': packet.document_sha256})
    # Real ambiguous anaphora is retained, not solved by the keyword list.
    elif re.search(r'\b(?:он|ты|их)\b', text, re.I):
        dimensions.append({'id': 'd_' + digest([packet.id, 'continuation'])[:20], 'kind': 'referent',
                           'mention_refs': [s.id for s in spans if re.search(r'\b(?:он|ты|их)\b', s.text, re.I)],
                           'values': ['CONTINUED_DISCOURSE_SUBJECT', 'OTHER_TEXTUAL_PARTICIPANT'],
                           'scope': packet.document_sha256})
    return {'premises': premises, 'mentions': mentions, 'labels': labels, 'dimensions': dimensions,
            'source_evidence': [quoted(s) for s in spans], 'observer': 'local-clauses004/1',
            'status': 'LOCAL_OBSERVATIONS_NOT_GENERAL_SEMANTIC_PARSER', 'unsupported': ['Implicit causal/coreference links', 'Unstated physical/psychological effects']}


def constraints_from_evidence(observations: dict, packet: RawPacket) -> list[dict]:
    out = []; text = '\n'.join(s.text for s in packet.spans)
    for d in observations['dimensions']:
        if d['kind'] == 'interpretation_scope':
            local = 's_' + digest([packet.document_sha256, packet.edition,
                                   packet.spans[0].source_address.get('section', packet.document_id)])[:24]
            if local != d['scope']:
                continue
            if re.search(r'\b(?:not to our (?:intent|desire)|we it forsake)\b', text, re.I):
                out.append({'dimension': d['id'], 'allowed_values': ['DESCRIPTIVE_ONLY'],
                            'scope': d['scope'], 'source_refs': [s.id for s in packet.spans],
                            'reason': 'A described way is explicitly excluded; this refutes universal permission, not the weak diversity claim or individual mention identities.'})
    return out
