"""Executed synthetic counterfactuals, separate from primary-source evidence."""
from copy import deepcopy

from artifact_genesis.source import packet_from_text
from .critic import critique
from .proposer import propose
from .contract import independent_spans, validate_pair


def fixture(train_lines: list[str], context_lines: list[str], language: str = 'en'):
    full = packet_from_text('controlled', '\n'.join(train_lines + context_lines) + '\n', language)
    n = len(train_lines)
    return full.model_copy(update={'spans': full.spans[:n]}), full.model_copy(update={'spans': full.spans[n:]})


def run_controls(vault) -> list[dict]:
    out = []

    def check(name, passed, **evidence):
        out.append({'control': name, 'passed': bool(passed), 'scientific_evidence': False, 'evidence': evidence})

    train, context = fixture(['The pilot met the engineer.', 'He returned at dawn.'],
                             ['In this account, "he" refers to the pilot.'])
    base = critique(train, context, 'anaphora')
    renamed, changed = fixture(['The archivist met the gardener.', 'He returned at dawn.'],
                               ['In this account, "he" refers to the archivist.'])
    r = critique(renamed, changed, 'anaphora')
    check('alpha_rename_preserves_reference_decision', base['label'] == r['label'] == 'SAME_ROLE')
    inverted, changed = fixture(['The engineer met the pilot.', 'He returned at dawn.'],
                                ['In this account, "he" refers to the pilot.'])
    r = critique(inverted, changed, 'anaphora')
    check('subject_object_inversion_changes_relative_binding', r['label'] == 'DIFFERENT_ROLE', review=r)
    negated, changed = fixture(['The pilot met the engineer.', 'He did not return at dawn.'],
                               ['In this account, "he" refers to the pilot.'])
    r = critique(negated, changed, 'anaphora')
    check('negation_retained_no_event_upgrade', r['label'] == 'SAME_ROLE' and r['distinctions']['negation']
          and not r['event_occurrence_established'], review=r)
    bad, changed = fixture(['The pilot met the engineer.', 'He returned at dawn.'],
                           ['In this account, "he" does not refer to the pilot.'])
    r = critique(bad, changed, 'anaphora')
    check('negated_definition_does_not_bind', r['label'] == 'UNRESOLVED', review=r)
    bad, changed = fixture(['The pilot met the engineer.', 'He returned at dawn.'],
                           ['In this account, "he" refers to the pilot.', 'In this account, "he" refers to the engineer.'])
    r = critique(bad, changed, 'anaphora')
    check('broken_coreference_keeps_both_definitions', r['label'] == 'UNRESOLVED'
          and len(r['independent_source_evidence']) == 2, review=r)
    for name, packet in [('overlap', train), ('hash', context.model_copy(update={'document_sha256': '0' * 64})),
                         ('edition', context.model_copy(update={'edition': 'forged'})),
                         ('cross_source', context.model_copy(update={'document_id': 'foreign'}))]:
        try:
            independent_spans(train, packet)
        except ValueError:
            check(name + '_source_boundary_rejected', True)
        else:
            check(name + '_source_boundary_rejected', False)
    hs = propose(train, 'anaphora')
    for name, mutate in [('fake_quote', lambda h: h['quoted_evidence'][0].update(quote='invented')),
                         ('foreign_project', lambda h: h.update(project='LM_OTHER')),
                         ('verified', lambda h: h.update(proof_status='verified'))]:
        wrong = deepcopy(hs); mutate(wrong[0])
        try:
            validate_pair(wrong, train)
        except ValueError:
            check(name + '_rejected', True)
        else:
            check(name + '_rejected', False)
    c = next(c for c in vault.cases if c['id'] == 'e1-order')
    t = vault.packet(c['train_packet'])
    # Test orientation with a separate constructed document, not altered frozen bytes.
    # Move the second chapter mention before the first while preserving the words.
    first = next(s.text for s in t.spans if 'Chapiter' in s.text)
    second = next(s.text for s in t.spans if 'chapter' in s.text)
    witness = ['For vntill thy naturall Seperation is done, thy secret Coniunction thou shalt never begin.']
    heading, statement = fixture([second, first], witness)
    r = critique(heading, statement, 'order')
    forward, same = fixture([first, second], witness)
    check('predicate_order_inversion_cannot_return_forward_binding', r['label'] == 'UNRESOLVED'
          and critique(forward, same, 'order')['label'] == 'ORDERED', review=r)
    pure, statement = fixture([first, second], ['The same chapters and their words occur in this book.'])
    check('textual_order_and_repetition_are_not_process_order', critique(pure, statement, 'order')['label'] == 'UNRESOLVED')
    original = next(c for c in vault.cases if c['id'] == 'e2-material-agent')
    t = vault.packet(original['train_packet'])
    wrong, statement = fixture(['А яд тем царем напитал', t.spans[1].text], ['Яд каплет сквозь его кору,'], 'ru')
    check('material_actor_swap_not_silently_identified', critique(wrong, statement, 'material_agent')['label'] == 'UNRESOLVED')
    wrong, statement = fixture(['Анчар есть часовой.'], ['Древо яда.'], 'ru')
    check('false_analogy_without_comparison_not_accepted', critique(wrong, statement, 'analogy')['label'] == 'UNRESOLVED')
    return out
