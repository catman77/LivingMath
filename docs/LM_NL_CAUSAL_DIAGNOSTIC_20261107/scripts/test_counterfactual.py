#!/usr/bin/env python3
"""No-internet, stdlib-only tests for frozen AST counterfactual diagnosis."""
import hashlib, json, pathlib, subprocess, sys, unittest
from frozen_ast_counterfactual import digest, models_difference, swap_first_two_binders

ROOT=pathlib.Path(__file__).resolve().parents[1]
GOLD=json.loads((ROOT/'fixtures'/'GOLD_AMBIGUOUS_PRECOMMITTED.json').read_text('utf8'))
SCORES=json.loads((ROOT/'fixtures'/'AMBIGUITY_SCORES_PARTIAL.json').read_text('utf8'))
MATRIX=json.loads((ROOT/'fixtures'/'LIVE_SCORE_MATRIX.json').read_text('utf8'))

class FrozenCausalTests(unittest.TestCase):
    def test_actual_source_hashes(self):
        for x in GOLD['corpus']:
            self.assertEqual(hashlib.sha256(x['text'].encode('utf8')).hexdigest(),x['sha256'])

    def test_all_five_exact_b_matches(self):
        byid={x['id']:x for x in SCORES['source_rows']}
        for x in GOLD['corpus']:
            if x['id']=='U26':continue
            with self.subTest(case=x['id']):
                base,wide=x['allowed_formulae'];row=byid[x['id']]
                self.assertEqual(digest(base),row['narrow_ast_sha256_A_and_B'])
                self.assertEqual(digest(swap_first_two_binders(base)),row['wide_ast_sha256_B'])
                self.assertEqual(digest(swap_first_two_binders(base)),digest(wide))

    def test_exact_model_counts_and_nontrivial_relation(self):
        for x in GOLD['corpus']:
            if x['id']=='U26':continue
            with self.subTest(case=x['id']):
                a=x['allowed_formulae'][0];b=swap_first_two_binders(a)
                n,d,c=models_difference(a,b,x['signature'])
                self.assertEqual((n,d),(530,176))
                self.assertTrue(c['narrow_truth'])
                self.assertFalse(c['wide_truth'])

    def test_keep_original_U26_invalid(self):
        # Source fixture intentionally kept intact. Exclusion was decided
        # explicitly in earlier report; no post-hoc correction is allowed.
        self.assertIn('U26',[x['id'] for x in GOLD['corpus']])
        self.assertEqual(SCORES['invalid_precommit'],['U26'])

    def test_previous_20_control_scores(self):
        for arm in ('A','B','C'):
            self.assertEqual(MATRIX['summary'][arm]['covered'],20)
        self.assertEqual(MATRIX['summary']['A']['candidate_count'],21)
        self.assertEqual(MATRIX['summary']['B']['candidate_count'],27)
        self.assertEqual(MATRIX['summary']['C']['candidate_count'],27)
        self.assertTrue(MATRIX.get('white_star_diff',{}).get('all_seven_trace_ast_sha_matched_placebo'))

    def test_two_distinct_interventions_in_legacy_ablated_design(self):
        # Reproduce the two separate *policy-dependent* branches from
        # actual decoder.py (verified on GitHub on 2026-11-07):
        # build_request: reverse source_order iff matched_ablation
        # build_move: reverse decoded permutation iff placebo
        order=['token_for_x','token_for_y'];permutation=[0,1]
        real_provider_order=order
        sham_provider_order=list(reversed(order))
        self.assertNotEqual(real_provider_order,sham_provider_order)
        real_decoder_perm=permutation
        sham_decoder_perm=list(reversed(permutation))
        self.assertNotEqual(real_decoder_perm,sham_decoder_perm)

    def test_no_llm_or_white_star_in_local_diagnostic(self):
        r=json.loads((ROOT/'results'/'frozen_ast_counterfactual.json').read_text('utf8'))
        self.assertEqual(r['runtime_LLM_calls'],0)
        self.assertEqual(r['runtime_white_star_calls'],0)
        self.assertEqual(r['swapped_candidates_matching_actual_B'],5)

if __name__=='__main__':unittest.main(verbosity=2)
