from copy import deepcopy
from fractions import Fraction
from itertools import product
import json
import unittest

from formal_core import (load_case, reachability, audit_observed, qualitative, projective,
                         pair_cells, check_certificate, encode)
from annotate import make_certificate
from formal_audit import mutation_audit


class FormalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.trace, cls.frames, cls.prose = load_case()
        cls.reachable = reachability(cls.data)
        cls.certificate = json.loads(encode(make_certificate(cls.data, cls.trace, cls.frames, cls.prose)))

    def test_full_pipeline_replay_and_annotated_certificate(self):
        verdict = check_certificate(self.data, self.trace, self.frames, self.certificate)
        self.assertEqual(verdict["bindings"], 18)
        self.assertEqual(verdict["semantic_fidelity"], "UNASSESSED_BY_CHECKER")

    def test_complete_partition_has_exact_realisable_witnesses(self):
        for pair in self.reachable["pairs"]:
            u, v = pair["vectors"]
            states = {tuple(s["state"]) for s in pair["states"]}
            self.assertLessEqual(len(pair["cells"]), 11)
            for cell in pair["cells"]:
                a, b = cell["witness"]
                self.assertGreater(a + b, 0)
                self.assertGreaterEqual(min(a, b), 0)
                self.assertEqual(Fraction(a, a + b), Fraction(cell["t"]))
                x, y = u[0] * a + u[1] * b, v[0] * a + v[1] * b
                self.assertEqual(tuple(cell["coordinates"]), (x, y))
                self.assertEqual(tuple(cell["state"]), qualitative(pair["concepts"], x, y))
            # An independent bounded rational grid is a regression check, not
            # the completeness proof (which uses all affine boundaries).
            for a in range(17):
                for b in range(17):
                    if a or b:
                        x, y = u[0] * a + u[1] * b, v[0] * a + v[1] * b
                        self.assertIn(qualitative(pair["concepts"], x, y), states)

    def test_closed_form_boundary_example(self):
        pair = pair_cells("a", "b", [1, 0], [0, 1])
        expected = {
            ("a", "b", "UNRESOLVED", "b"),
            ("a", "b", "ALIGN", "b"),
            ("a", "b", "ALIGN", "BALANCED"),
            ("a", "b", "ALIGN", "a"),
            ("a", "b", "UNRESOLVED", "a"),
        }
        self.assertEqual({tuple(s["state"]) for s in pair["states"]}, expected)
        with self.assertRaises(ValueError):
            pair_cells("a", "b", [-2, -4], [2, 4])

    def test_exact_common_scale_and_row_permutation_invariance(self):
        for pair in self.reachable["pairs"]:
            for cell in pair["cells"]:
                names = pair["concepts"]
                x, y = cell["coordinates"]
                for scale in [Fraction(-7, 3), Fraction(5, 2), Fraction(1)]:
                    self.assertEqual(qualitative(names, x, y), qualitative(names[::-1], y * scale, x * scale))
                    self.assertEqual(projective(names, x, y), projective(names[::-1], y * scale, x * scale))
        # Equal qualitative mode deliberately does not imply equal ratios.
        self.assertEqual(qualitative(["a", "b"], 1, 2), qualitative(["a", "b"], 1, 3))
        self.assertNotEqual(projective(["a", "b"], 1, 2), projective(["a", "b"], 1, 3))

    def test_sign_triangle_balance_and_fixed_relations(self):
        for a, b, c in product([-1, 1], repeat=3):
            self.assertEqual((a * b) * (b * c) * (c * a), 1)
        known = {tuple(p["concepts"]): p for p in self.reachable["pairs"]}
        self.assertEqual(known["death", "restart"]["relation_types"], ["ALIGN"])
        self.assertEqual(known["death", "no_exit"]["relation_types"], ["TENSION"])

    def test_observed_claims_use_the_declared_quotient(self):
        audit = audit_observed(self.data, self.trace, self.frames, self.reachable)
        self.assertEqual(self.reachable["summary"]["qualitative_states"], 344)
        self.assertEqual(self.reachable["summary"]["fixed_relation_pairs"], 44)
        self.assertEqual(audit["summary"]["unique_qualitative_states"], 58)
        self.assertTrue(audit["summary"]["first_six_motifs_distinct"])
        example = audit["arithmetic_new_but_qualitatively_repeated"][0]
        self.assertEqual((example["step"], example["previous_step"]), (31, 24))
        self.assertNotEqual(example["new_arithmetic_signature"], example["previous_arithmetic_signature"])

    def test_faults_are_rejected_but_meaning_is_not_falsely_certified(self):
        mutations = mutation_audit(self.data, self.trace, self.frames, self.certificate)
        self.assertEqual(mutations["rejected_faults"], 11)
        self.assertEqual(mutations["contentless_text_control"]["semantic_status"], "UNASSESSED_BY_CHECKER")

    def test_frame_substitution_and_scope_omission_rejected(self):
        changed = deepcopy(self.frames)
        changed[0], changed[1] = changed[1], changed[0]
        with self.assertRaisesRegex(ValueError, "assembly"):
            check_certificate(self.data, self.trace, changed, self.certificate, replay=False)
        changed = deepcopy(self.certificate)
        changed["source_assertions"] = []
        with self.assertRaisesRegex(ValueError, "assertion register"):
            check_certificate(self.data, self.trace, self.frames, changed, replay=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
