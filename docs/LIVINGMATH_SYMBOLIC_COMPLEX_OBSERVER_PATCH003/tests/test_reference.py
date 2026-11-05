#!/usr/bin/env python3
"""Unittest acceptance oracle; runs without network/MCP."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reference'))
from sp_complex_reference import SPComplex, balanced_words

EXPECTED = {
    2: (3, 2, 0, 0, 0),
    4: (9, 14, 6, 8, 6),
    6: (29, 74, 46, 80, 46),
    8: (99, 354, 256, 560, 256),
    10: (351, 1614, 1264, 3360, 1264),
}

class TestSPComplex(unittest.TestCase):
    def test_exhaustive_counts(self):
        for n, expect in EXPECTED.items():
            with self.subTest(n=n):
                r = SPComplex(n).invariants()
                self.assertEqual(tuple(r[k] for k in ('vertices','edges','beta1_graph','faces','rank_d2_F2')), expect)
                self.assertEqual(r['H1_F2_dim'], 0)
                self.assertEqual(r['unresolved_peaks'], 0)
                self.assertEqual(r['pi1_status'], 'PROVED_TRIVIAL_WITH_CERTIFICATE')

    def test_graph_without_2cells_is_not_pi1_trivial(self):
        for n in (4,6,8):
            r = SPComplex(n, faces='none').invariants()
            self.assertEqual(r['H1_F2_dim'], r['beta1_graph'])
            self.assertEqual(r['pi1_status'], 'NOT_PROVED')

    def test_partial_2cells_not_a_pi1_proof(self):
        for policy in ('bigons','diamonds'):
            r = SPComplex(8, faces=policy).invariants()
            self.assertEqual(r['pi1_status'], 'NOT_PROVED')
            self.assertLess(r['faces'], r['peak_total'])

    def test_sp_equivalences_are_distinct_relations(self):
        self.assertEqual('SSPP'.count('S') - 'SSPP'.count('P'), 0)
        self.assertEqual('SPSP'.count('S') - 'SPSP'.count('P'), 0)
        self.assertNotEqual('SSPP', 'SPSP')
        self.assertEqual(len(balanced_words(6)), 20)
        self.assertEqual(len(balanced_words(10)), 252)

    def test_face_corruption_must_fail(self):
        c = SPComplex(6)
        face = next(f for f in c.faces if f.kind == 'diamond')
        from dataclasses import replace
        c.faces[face.id] = replace(face, right=(face.right[0],))
        with self.assertRaises(AssertionError):
            c.verify_faces()

    def test_reproducible(self):
        self.assertEqual(SPComplex(10).invariants(), SPComplex(10).invariants())

if __name__ == '__main__':
    unittest.main(verbosity=2)
