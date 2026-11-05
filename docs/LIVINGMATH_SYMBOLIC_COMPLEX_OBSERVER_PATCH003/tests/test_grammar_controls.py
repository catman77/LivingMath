#!/usr/bin/env python3
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reference'))
from grammar_controls import balanced_words, dyck, alpha, alpha_with_line_boundaries, same_encoding_with_conflicting_labels, exact_dyck_table

class GrammarControls(unittest.TestCase):
    def test_true_counts(self):
        self.assertEqual(exact_dyck_table(), {2:{'balanced':2,'dyck':1},
                          4:{'balanced':6,'dyck':2},6:{'balanced':20,'dyck':5},
                          8:{'balanced':70,'dyck':14},10:{'balanced':252,'dyck':42}})

    def test_history_and_denotation_distinct(self):
        self.assertEqual('SSPP'.count('S')-'SSPP'.count('P'),0)
        self.assertEqual('SPSP'.count('S')-'SPSP'.count('P'),0)
        self.assertNotEqual('SSPP','SPSP')
        self.assertNotEqual(alpha('SSPP'),alpha('SPSP'))

    def test_alpha_bijection(self):
        self.assertEqual(alpha('SSPP'),alpha('PPSS'))
        self.assertNotEqual('SSPP','PPSS')
        self.assertEqual(alpha('ABBA'),alpha('BAAB'))

    def test_contradictory_labels_are_detectable(self):
        self.assertTrue(same_encoding_with_conflicting_labels('SSPP','PPSS',alpha))
        self.assertFalse(same_encoding_with_conflicting_labels('SSPP','SPSP',alpha))

    def test_boundaries_matter(self):
        left=[('A','B'),('C','D')]
        right=[('A',),('B','C','D')]
        self.assertEqual(alpha(''.join(''.join(x) for x in left)),
                         alpha(''.join(''.join(x) for x in right)))
        self.assertNotEqual(alpha_with_line_boundaries(left),alpha_with_line_boundaries(right))

    def test_sp_inversion_is_not_dyck_equivalence(self):
        self.assertTrue(dyck('SSPP'))
        self.assertFalse(dyck('PPSS'))

if __name__=='__main__':
    unittest.main(verbosity=2)
