"""Frozen small study: raw competing H, sealed source challenge, bounded critique, DAV."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from artifact_genesis.journal import Journal
from artifact_genesis.source import save
from artifact_genesis.proposer import propose as grammar_propose
from artifact_genesis.audit import source_audit as grammar_audit
from davcore.ast import digest
from .source import GroundingVault
from .contract import PAIRS, validate_pair
from .critic import critique
from .process import run_worker
from .formal import formalize, calibration_controls
from .controls import run_controls


def jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))


async def run(root: Path, out: Path) -> dict:
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=False)
    vault = GroundingVault(root)
    if {k: list(v) for k, v in PAIRS.items()} != vault.criteria['hypothesis_pairs']:
        raise ValueError('FROZEN_HYPOTHESIS_RUBRIC_DRIFT')
    project = 'LM_QA_GROUNDING003'
    journal = Journal(out / 'research-journal.jsonl')
    proposals = []; inputs = []; commitments = []; counterreadings = []
    packets = {}; by_case = {}; timings = {'proposal_ms': 0., 'source_critique_ms': 0.,
                                          'B1_grammar_ms': 0., 'formal_ms': 0.}
    source_bytes = 0
    # All proposal calls finish before any challenge is revealed.
    for case in vault.cases:
        packet = vault.packet(case['train_packet'])
        request = {'packet': packet.model_dump(), 'family': case['family'], 'project': project}
        begin = time.monotonic()
        response = await run_worker('propose', request)
        timings['proposal_ms'] += (time.monotonic() - begin) * 1000
        hs = response['hypotheses']; validate_pair(hs, packet, project)
        inputs.append({'case_id': case['id'], 'phase': 'PRE_REVEAL', 'request': request, 'response': response})
        source_bytes += len(json.dumps(request, ensure_ascii=False).encode())
        by_case[case['id']] = hs; packets[case['id']] = packet
        for h in hs:
            proposals.append({'case_id': case['id'], 'H': h})
            counterreadings.append({'case_id': case['id'], 'hypothesis_id': h['hypothesis_id'], 'alternatives': h['alternatives']})
            p = {'case_id': case['id'], 'hypothesis_id': h['hypothesis_id'],
                 'prediction': h['prediction'], 'target_free': True, 'phase': 'PRE_REVEAL',
                 'source_input_sha256': digest(packet.model_dump()),
                 'challenge_packet_id': case['challenge_packet']}
            p['commitment_id'] = digest(p); commitments.append(p)
            journal.append('PROPOSED_SOURCE_H', h)
    jsonl(out / 'proposals.jsonl', proposals)
    jsonl(out / 'prediction-commitments.jsonl', commitments)
    seal = vault.seal(commitments)
    save(out / 'precommit-seal.json', {**seal,
         'proposals_file_sha256': hashlib.sha256((out / 'proposals.jsonl').read_bytes()).hexdigest(),
         'commitments_file_sha256': hashlib.sha256((out / 'prediction-commitments.jsonl').read_bytes()).hexdigest()})
    journal.append('ALL_SOURCE_PREDICTIONS_SEALED', seal)
    reviews = []; evidence = []; bindings = []; dav = []; revisions = []; losses = []
    ablations = []; control_checks = []; followups = []; critic_io = []
    for case in vault.cases:
        packet = packets[case['id']]
        challenge = vault.reveal(case, seal, packet)
        request = {'train': packet.model_dump(), 'challenge': challenge.model_dump(),
                   'family': case['family'], 'project': project}
        begin = time.monotonic()
        response = await run_worker('critique', request)
        timings['source_critique_ms'] += (time.monotonic() - begin) * 1000
        critic_io.append({'case_id': case['id'], 'phase': 'POST_SEAL', 'request': request, 'response': response})
        review = response['critique']
        row = {'case_id': case['id'], 'experiment': case['experiment'],
               'synthetic': case['synthetic'], 'new_primary_material': case['new_primary_material'],
               'review': review, 'external_annotations': [], 'semantic_review': 'SEMANTIC_REVIEW_PENDING'}
        reviews.append(row); journal.append('INDEPENDENT_SOURCE_CRITIQUE', row)
        evidence.append({'case_id': case['id'], 'source_evidence': review['independent_source_evidence'],
                         'proposal_evidence_overlap': False, 'evidence_kind': review['evidence_kind'],
                         'assumption_graph': review['assumption_graph'], 'synthetic': case['synthetic'],
                         'support_scope': review['status']})
        # Run unchanged 002 grammar on exactly the same train (no disjoint context).
        begin = time.monotonic()
        grammar = grammar_propose(packet)
        grammar_checks = [grammar_audit(h, packet) for h in grammar['hypotheses']]
        timings['B1_grammar_ms'] += (time.monotonic() - begin) * 1000
        ablated = critique(packet, None, case['family'])
        baseline = {'case_id': case['id'], 'B0': {'status': 'SOURCE_LEXICAL_MATCH', 'quotes': [s.text for s in packet.spans], 'role_decision': None},
                    'B1': {'implementation': 'UNCHANGED_GENESIS002', 'raw_output': grammar,
                           'source_proxy_audits': grammar_checks, 'reference_identity_decision': None},
                    'B2': {'independent_evidence_removed': True, 'source_critique': ablated},
                    'C': {'label': review['label'], 'status': review['status'], 'review_id': review['review_id']},
                    'comparison': 'C source-internal information gain is not external semantic accuracy or a matched scientific transfer win.'}
        ablations.append(baseline)
        if case['synthetic']:
            control_checks.append({'case_id': case['id'], 'hard_negative': case['hard_negative'],
                                   'expected': case['control_expected_label'], 'actual': review['label'],
                                   'passed': review['label'] == case['control_expected_label'],
                                   'scientific_evidence': False})
        selected = [h for h in by_case[case['id']] if h['prediction']['label'] == review['label']]
        supported = review['status'] == 'SOURCE_INTERNAL_SUPPORT' and len(selected) == 1
        formal = None
        if supported:
            begin = time.monotonic()
            formal = formalize(selected[0], review)
            timings['formal_ms'] += (time.monotonic() - begin) * 1000
            dav.append({'case_id': case['id'], 'synthetic': case['synthetic'], 'witness': formal})
            journal.append('SOURCE_FIRST_DAV_FINITE_CHECK', {'case_id': case['id'], 'witness': formal})
            bindings.append({'case_id': case['id'], 'bindings': formal['role_bindings'],
                             'source_distinctions': review['distinctions'], 'assumptions': review['assumption_graph']})
            losses.append(formal['loss'])
        else:
            bindings.append({'case_id': case['id'], 'status': 'UNRESOLVED',
                             'source_distinctions': review['distinctions'],
                             'bindings': [], 'next_source': review['next_test']})
            losses.append({'case_id': case['id'], 'source_distinctions': review['distinctions'],
                           'status': 'UNRESOLVED_NO_TARGET', 'source_quotes_retained': True})
        # Revisions append to original records; a target law never promotes source support.
        for h in by_case[case['id']]:
            current = deepcopy(h)
            current['parent_hypothesis_id'] = h['hypothesis_id']
            current.pop('hypothesis_id')
            accepted = supported and h['hypothesis_id'] == selected[0]['hypothesis_id']
            current['confidence_status'] = 'SOURCE_GROUNDED_CANDIDATE' if accepted else 'REJECTED_BY_SOURCE_CONTEXT' if supported else 'UNRESOLVED'
            current['counterevidence'] = [{'review_id': review['review_id'], 'label': review['label'],
                                         'source_evidence': review['independent_source_evidence']}]
            current['hypothesis_id'] = digest(current)
            revision = {'case_id': case['id'], 'old_H': h, 'new_H': current,
                        'basis': 'Disjoint source context; target truth cannot select a reading.',
                        'review_id': review['review_id'], 'original_retained': True,
                        'formal_counterexample': formal['necessity_probe']['with_premise']['counterexample'] if formal else None,
                        'source_truth_from_target': False}
            revisions.append(revision); journal.append('APPEND_ONLY_SOURCE_REVISION', revision)
        followup = {'case_id': case['id'], 'phase': 'POST_SOURCE_REVISION',
                    'prediction': review['next_test'], 'competing_labels': list(PAIRS[case['family']]),
                    'role_addresses': by_case[case['id']][0]['roles'], 'family': case['family'],
                    'required_semantic_discriminator': vault.criteria['semantic_discriminators'].get(case['family'],
                        'Explicit source identity/dependency statement, not co-predication or a repeated word.'),
                    'assumption_to_remove': review['assumption_graph'],
                    'target_free': True, 'status': 'NOT_RUN_NO_ADDITIONAL_FROZEN_CHALLENGE',
                    'remaining_unknown': review['label'] == 'UNRESOLVED'}
        followups.append(followup); journal.append('NEXT_FALSIFIABLE_SOURCE_TEST', followup)
    calibration = calibration_controls()
    adversarial = run_controls(vault)
    for row in calibration:
        journal.append('FORMAL_NEGATIVE_CONTROL', row)
    for row in adversarial:
        journal.append('SOURCE_COUNTERFACTUAL_CONTROL', row)
    lexical_vs_referential = [{'case_id': c['id'], 'family': c['family'],
                              'kind': 'LEXICAL_OR_COMPARISON' if c['family'] == 'analogy' else 'REFERENCE_OR_EVENT_SCOPE',
                              'annotation_status': c['annotation_status'], 'external_labels': []} for c in vault.cases]
    real = [r for r in reviews if not r['synthetic']]
    internal = [r for r in real if r['review']['status'] == 'SOURCE_INTERNAL_SUPPORT']
    discriminated = [r for r in reviews if r['review']['status'] == 'SOURCE_INTERNAL_SUPPORT']
    software = all(c['passed'] for c in control_checks + calibration + adversarial)
    result = {'scientific_status': 'SOURCE_INTERNAL_TRANSFER_ONLY' if internal else 'SEMANTIC_EVIDENCE_INSUFFICIENT',
              'G3': 'FAIL', 'semantic_review': 'SEMANTIC_REVIEW_PENDING', 'software_status': 'PASS' if software else 'FAIL',
              'decisions': len(reviews), 'raw_hypotheses': len(proposals), 'real_source_decisions': len(real),
              'real_source_internal_supported': len(internal), 'independently_annotated_relations': 0,
              'new_independently_validated_source_relations': 0, 'discriminating_source_decisions': len(discriminated),
              'source_discrimination_rate': len(discriminated) / len(reviews),
              'external_semantic_accuracy': None, 'synthetic_control_passed': sum(c['passed'] for c in control_checks),
              'synthetic_control_total': len(control_checks), 'hard_negatives': sum(c['hard_negative'] for c in control_checks),
              'additional_adversarial_controls': len(adversarial),
              'formal_encodings': len(dav), 'formal_tautologies_rejected_as_scientific_laws': sum(w['witness']['scientific_law_status'] == 'FAIL_TARGET_TAUTOLOGY' for w in dav),
              'proposer': 'NO_LLM_PROPOSER', 'blindness': 'ENGINEERING_HOLDOUT',
              'cycle_break': 'Independent semantic evidence acquisition and non-template generalization; source-internal definitions support local decisions only. Target guards encode their consequences.',
              'gates': {'G0': 'PASS_FROZEN_SOURCE', 'G1': 'PASS_COMPETING_RAW_H', 'G2': 'LIMITED_SOURCE_INTERNAL_SUPPORT',
                        'G3': 'FAIL', 'G4': 'PASS' if software else 'FAIL', 'G5': 'LOCAL_PASS_MCP_PENDING', 'G6': 'PENDING_CLEAN_REPLAY'},
              'proof_status': 'unverified', 'execution_permission': {'allowed': False},
              'production_changed': False, 'journal': Journal.verify(out / 'research-journal.jsonl')}
    for name, rows in [('counterreadings', counterreadings), ('role-bindings', bindings), ('independent-source-evidence', evidence),
                       ('source-critique', reviews), ('DAV-witnesses', dav), ('revision-history', revisions),
                       ('followup-predictions', followups), ('loss-ledger', losses), ('proposer-wire', inputs),
                       ('critic-wire', critic_io)]:
        jsonl(out / (name + '.jsonl'), rows)
    save(out / 'annotation-sample.json', lexical_vs_referential)
    save(out / 'controls.json', {'source_controls': control_checks, 'formal_controls': calibration, 'adversarial_controls': adversarial})
    save(out / 'ablation-comparison.json', {'cases': ablations, 'source_internal_support_count': len(internal),
         'external_accuracy': None, 'B0_vs_C': 'Different task capability: literal quotes versus bounded evidence-based decisions.',
         'B1_vs_C': 'Independent context unavailable to grammar002; no matched semantic generalization win claimed.',
         'B2_vs_C': 'All disjoint evidence removed on identical train; no resolved binding remains.'})
    save(out / 'source-access.json', {'accesses': vault.access, 'seal': seal})
    save(out / 'result.json', result)
    save(out / 'costs.json', {'LLM': {'status': 'NO_LLM_PROPOSER', 'calls': 0, 'tokens': None, 'model': None},
         'independent_annotator_hours': 0, 'annotation_status': 'SEMANTIC_REVIEW_PENDING',
         'proposal_worker_calls': len(vault.cases), 'critic_worker_calls': len(vault.cases), 'proposal_bytes': source_bytes,
         'branch_timing': timings, 'formal_encodings': len(dav),
         'formal_checks_in_binding_trials': 4 * len(dav),
         'timing_scope': 'Primary study only; B1 grammar and shared proposal timed separately. Controls/old replay/MCP reported separately.',
         'wall_ms': (time.monotonic() - started) * 1000})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(asyncio.run(run(args.root.resolve(), args.out.resolve())), ensure_ascii=False))
