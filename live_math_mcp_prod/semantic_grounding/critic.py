"""Bounded independent-context critic. No proposer rationale or target imports."""
import re

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from .contract import PAIRS, independent_spans, quoted


def _norm(text: str) -> str:
    return text.casefold().replace('vntill', 'until').replace('vntil', 'until').replace('neuer', 'never')


def _english_participants(packet: RawPacket) -> tuple[str, str] | None:
    # Reconstruct the two syntax slots independently, without proposed role IDs.
    for span in packet.spans:
        words = re.findall(r'\w+', span.text.casefold())
        if len(words) >= 5 and words[0] == 'the' and words[3] == 'the':
            return words[1], words[4]
    return None


def critique(train: RawPacket, challenge: RawPacket | None, family: str) -> dict:
    if family not in PAIRS:
        raise ValueError('UNKNOWN_GROUNDING_QUESTION')
    if challenge is not None:
        independent_spans(train, challenge)
    source = '\n'.join(s.text for s in train.spans)
    context = '\n'.join(s.text for s in challenge.spans) if challenge is not None else ''
    t, c = _norm(source), _norm(context)
    label = 'UNRESOLVED'
    reason = 'No disjoint source evidence establishes either competing binding.'
    kind = 'UNRESOLVED'
    assumptions: list[dict] = []
    scope_observations: list[dict] = []
    witnesses = []
    if challenge is not None:
        if family == 'anaphora':
            slots = _english_participants(train)
            definitions = re.findall(r'["“]he["”]\s+refers to the\s+(\w+)', c)
            if slots and definitions:
                values = set(definitions)
                if len(values) > 1 or not values <= set(slots):
                    reason = 'Independent referent definitions conflict or name an unintroduced participant.'
                else:
                    referent = next(iter(values))
                    label = 'SAME_ROLE' if referent == slots[0] else 'DIFFERENT_ROLE'
                    reason = 'A separate narrator definition binds the pronoun to an explicitly named participant.'
                    kind = 'EXPLICIT_REFERENT_DEFINITION'
                witnesses = [s for s in challenge.spans if re.search(r'["“]he["”]\s+refers', s.text, re.I)]
                assumptions.append({'claim': 'Narrator definition applies within this account only.', 'kind': 'SCOPE_LIMIT'})
            elif re.search(r'\b(?:тот|он)\b', c):
                witnesses = [s for s in challenge.spans if re.search(r'\b(?:тот|он|раб|владыки)\b', s.text, re.I)]
                reason = 'Narrative subject continuation suggests a reading, but no separate explicit definition identifies the pronoun with one initial participant.'
        elif family == 'order':
            prerequisite = re.search(r'\buntil\b[\s\S]+\bnever\s+begin\b', c)
            # Two independently recurring source predicates, not only the marker until.
            anchors = {w[:5] for w in re.findall(r'\b\w{7,}\b', t)
                       if w not in {'chapiter', 'chapter', 'followeth', 'therefore'}}
            linked = [a for a in sorted(anchors) if re.search(r'\b' + re.escape(a) + r'\w*', c)]
            chapter_positions = []
            for span in train.spans:
                if not re.search(r'\bchap(?:ter|iter)\b.*\bof\b', span.text, re.I):
                    continue
                hits = [re.search(r'\b' + re.escape(w[:5]) + r'\w*', c)
                        for w in re.findall(r'\b\w{7,}\b', _norm(span.text))
                        if w not in {'chapiter', 'chapter', 'followeth', 'therefore'}]
                positions = [m.start() for m in hits if m is not None]
                if positions:
                    chapter_positions.append(min(positions))
            forward = len(chapter_positions) >= 2 and chapter_positions[0] < chapter_positions[1]
            if prerequisite and len(linked) >= 2 and forward:
                label, kind = 'ORDERED', 'EXPLICIT_OPERATIONAL_PREREQUISITE'
                reason = 'A separate until/never-begin prohibition connects the two source predicates; chapter order alone did not establish it.'
                witnesses = list(challenge.spans)
                assumptions.append({'claim': 'An authorial prescription is interpreted as a prerequisite within this textual procedure, not physical time or causal truth.', 'kind': 'TEXTUAL_SCOPE'})
            elif prerequisite and len(linked) >= 2 and not forward:
                reason = 'The independent prerequisite does not preserve the proposed source-role orientation; retain it as counterevidence, not an ordered binding.'
                witnesses = list(challenge.spans)
            elif 'not a required order' in c:
                reason = 'Independent context explicitly restricts the order to headings, not operations.'
                witnesses = list(challenge.spans)
        elif family == 'scope':
            # Independent author definitions, including controlled homonymy.
            defs = re.search(r'first\s+["“](\w+)["”]\s+denotes\s+(.+?);\s*the second\s+["“]\1["”]\s+denotes\s+(.+?)[.]?$', c)
            same = re.search(r'both occurrences of ["“](\w+)["”] refer to the same person', c)
            two = re.search(r'\btwo\s+(\w+)\b', c)
            if defs:
                word = defs.group(1)
                if len(re.findall(r'\b' + re.escape(word) + r'\b', t)) >= 2:
                    label = 'DIFFERENT_ROLE' if defs.group(2).strip(' .') != defs.group(3).strip(' .') else 'UNRESOLVED'
                    kind = 'EXPLICIT_DIFFERENT_DEFINITIONS'
                    reason = 'Disjoint definitions give different senses to the same printed word; word identity cannot establish referent identity.'
                    witnesses = list(challenge.spans)
            elif same and len(re.findall(r'\b' + re.escape(same.group(1)) + r'\b', t)) >= 2:
                label, kind = 'SAME_ROLE', 'EXPLICIT_COREFERENCE_DEFINITION'
                reason = 'A separate sentence explicitly co-refers the two occurrences.'
                witnesses = list(challenge.spans)
            elif two and 'second' in c and re.search(r'\bgrosse\b', c):
                singular = two.group(1).removesuffix('s')
                if len(re.findall(r'\b' + re.escape(singular) + r'\b', t)) >= 2:
                    kind = 'AUTHOR_DISTINGUISHES_TWO_SCOPES_UNASSIGNED'
                    reason = 'Two named scopes are attested, but no independent witness assigns the two proposal mentions to different scopes. Term inventory is not mention reference identity.'
                    witnesses = list(challenge.spans)
                    scope_observations.append({'term': singular, 'named_scopes': 2,
                                               'specific_proposal_mentions_assigned': False})
                    assumptions.append({'claim': 'Distinct named procedural scopes; no assertion of modern substances or physical entity identity.', 'kind': 'SCOPE_LIMIT'})
        elif family == 'analogy':
            comparison = re.search(r'\b(?:как|as|like)\b', t)
            notes = [s for s in challenge.spans if s.source_address.get('kind') == 'AUTHOR_FOOTNOTE'
                     and re.search(r'\b(?:древо|дерево)\b', s.text, re.I)]
            if comparison and notes:
                label, kind = 'ANALOGY_ONLY', 'AUTHOR_NOTE_AND_COMPARISON'
                reason = 'The original author note defines the named object as a tree; the comparison preserves an image, not a literal watchman identity.'
                witnesses = notes
                assumptions.append({'claim': 'Original author note belongs to this named poem object; no allegorical/persona identification follows.', 'kind': 'EDITORIAL_LINK_SCOPE'})
        elif family == 'actor_object':
            if re.search(r'\bчеловека\s+человек\b', t) and re.search(r'\bраб\s+у\s+ног\b[\s\S]+\bвладыки\b', c):
                label, kind = 'DIFFERENT_ROLE', 'CASE_SLOTS_AND_OPPOSED_NARRATIVE_ROLES'
                reason = 'Accusative/nominative slots are distinct and the later servant-at-master relation supports distinct narrative roles; this does not identify every pronoun or equate master with king.'
                witnesses = [s for s in challenge.spans if re.search(r'\b(?:раб|владыки)\b', s.text, re.I)]
                assumptions.append({'claim': 'Ordinary non-reflexive narrative reading; exact entity mapping remains unresolved.', 'kind': 'DEFEASIBLE_READING'})
        elif family == 'material_agent':
            m = re.search(r'\bтем\s+(\w+)\b', t)
            instrument = m.group(1)[:-2] if m and m.group(1).endswith(('ом', 'ем')) else None
            if instrument and re.search(r'\b' + re.escape(instrument) + r'\b', c):
                label, kind = 'DIFFERENT_ROLE', 'AGENT_VERSUS_INSTRUMENTAL_WITH_CONTEXT'
                reason = 'The acting subject and instrumental object occupy different roles; separate descriptions recur with the instrument lemma. Chemical identity and real-world effects remain unknown.'
                witnesses = list(challenge.spans)
                assumptions.append({'claim': 'Local instrumental-case normalization only; no species or physical measurement.', 'kind': 'MORPHOLOGICAL_PROXY'})
        elif family == 'identity':
            reason = 'Body/spirit and corporal/spiritual words denote roles or qualities; no disjoint explicit identity statement binds the four role occurrences.'
            witnesses = list(challenge.spans)
        elif family == 'necessity':
            reason = 'The context supplies a conditional textual knitting claim, not evidence that induration implies confixation; retain the old P=1,Q=0 countermodel.'
            witnesses = list(challenge.spans)
    negation = bool(re.search(r'\b(?:not|no|never|neuer|не|ни)\b', source + '\n' + context, re.I))
    result = {
        'family': family, 'label': label,
        'status': 'SOURCE_INTERNAL_SUPPORT' if label != 'UNRESOLVED' else 'UNRESOLVED',
        'evidence_kind': kind, 'reason': reason,
        'independent_source_evidence': [quoted(s) for s in witnesses],
        'train_packet_sha256': digest(train.model_dump()),
        'challenge_packet_sha256': digest(challenge.model_dump()) if challenge is not None else None,
        'assumption_graph': assumptions,
        'term_scope_observations': scope_observations,
        'distinctions': {'word_identity': 'LEXICAL_ONLY_NOT_REFERENCE_IDENTITY',
                         'reference_identity': label if kind in {'EXPLICIT_REFERENT_DEFINITION', 'EXPLICIT_COREFERENCE_DEFINITION'} else 'UNRESOLVED',
                         'actor_object': 'Separate mention slots retained',
                         'order': 'Procedural prescription' if label == 'ORDERED' else 'No procedural order established',
                         'negation': negation, 'analogy': label == 'ANALOGY_ONLY',
                         'modality': 'Textual prescription/definition/image, never established world event'},
        'independent_semantic_review': 'SEMANTIC_REVIEW_PENDING',
        'event_occurrence_established': False, 'target_used': False,
        'next_test': ('Acquire a disjoint definition assigning each specific proposal mention to its referent or named scope; the existence of two term senses is insufficient.'
                      if scope_observations else
                      'Acquire an explicit source definition of the disputed referents, or independently annotate their links before consulting target outputs.'
                      if label == 'UNRESOLVED' else 'Test a new disjoint passage with the same competing predictions; obtain independent semantic annotations.'),
        'proof_status': 'unverified', 'execution_permission': {'allowed': False},
    }
    result['review_id'] = digest(result)
    return result
