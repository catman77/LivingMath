"""Local independent finite reference tests. Not tests of installed MCP code."""
import copy
import unittest
from dyck_certificates import (words, dyck_prefix, cancel_normal_form, make_positive_witness,
    check_positive_witness, build_full_table, independently_check_full_table, census, sha)

class TestFiniteDyck(unittest.TestCase):
    def test_boundary_example(self):
        self.assertEqual(cancel_normal_form('SP'), ())
        self.assertEqual(cancel_normal_form('PS'), ())
        self.assertTrue(dyck_prefix('SP'))
        self.assertFalse(dyck_prefix('PS'))

    def test_exact_census(self):
        for n, zero, dyck in [(2,2,1),(4,6,2),(6,20,5),(8,70,14),(10,252,42)]:
            c = census(n)
            self.assertEqual((c['zero'], c['dyck']), (zero, dyck))

    def test_valid_positive_witnesses_all_words_up_to_10(self):
        for n in range(11):
            for w in words(n):
                proof = make_positive_witness(w)
                truth = dyck_prefix(w)
                self.assertEqual(proof is not None, truth, (n, ''.join(w)))
                if proof is not None:
                    self.assertTrue(check_positive_witness(w, proof), ''.join(w))

    def test_complete_table_all_words_up_to_8(self):
        for n in range(9):
            for w in words(n):
                cert = build_full_table(w)
                self.assertTrue(independently_check_full_table(w, cert))
                root = next(x for x in cert['table'] if x['i']==0 and x['j']==n)
                self.assertEqual(root['value'], dyck_prefix(w))

    def test_branching_example(self):
        proof = make_positive_witness('SSPPSP')
        self.assertIsNotNone(proof)
        self.assertEqual(proof['split']['close_at'], 3)
        self.assertEqual(proof['inner_proof']['kind'], 'OPEN_INNER_CLOSE_AFTER')
        self.assertEqual(proof['after_proof']['kind'], 'OPEN_INNER_CLOSE_AFTER')
        self.assertTrue(check_positive_witness('SSPPSP', proof))

    def test_wrong_split_rejected(self):
        p = make_positive_witness('SSPPSP')
        q = copy.deepcopy(p)
        q['split']['close_at'] = 1
        self.assertFalse(check_positive_witness('SSPPSP', q))

    def test_missing_branch_rejected(self):
        p = make_positive_witness('SSPPSP')
        del p['after_proof']
        self.assertFalse(check_positive_witness('SSPPSP', p))

    def test_bad_sha_rejected(self):
        p = make_positive_witness('SSPPSP')
        p['sha256'] = '0' * 64
        self.assertFalse(check_positive_witness('SSPPSP', p))

    def test_renaming_contract_is_role_sensitive(self):
        self.assertTrue(dyck_prefix(('S','P')))
        self.assertFalse(dyck_prefix(('P','S')))
        # Only simultaneous renaming of tokens AND declared roles preserves it.
        self.assertTrue(dyck_prefix(('A','B'),opener='A',closer='B'))
        self.assertFalse(dyck_prefix(('B','A'),opener='A',closer='B'))

    def test_normal_form_never_sufficient_on_balanced_words(self):
        for n in [2,4,6,8,10]:
            balanced = [w for w in words(n) if cancel_normal_form(w)==()]
            self.assertTrue(any(dyck_prefix(w) for w in balanced))
            self.assertTrue(any(not dyck_prefix(w) for w in balanced))

    def test_negative_table_wrong_root_rejected(self):
        cert = build_full_table('PS')
        for entry in cert['table']:
            if (entry['i'], entry['j'])==(0,2):
                entry['value'] = True
        self.assertFalse(independently_check_full_table('PS', cert))

    def test_negative_table_missing_entry_rejected(self):
        cert = build_full_table('PS')
        cert['table'].pop()
        self.assertFalse(independently_check_full_table('PS', cert))

    def test_negative_table_wrong_interior_rejected(self):
        cert = build_full_table('SSPP')
        for x in cert['table']:
            if (x['i'],x['j']) == (1,3):
                x['value'] = False
        self.assertFalse(independently_check_full_table('SSPP', cert))

    def test_negative_table_forged_sha_rejected(self):
        cert = build_full_table('PS')
        cert['token_sha256']='f'*64
        self.assertFalse(independently_check_full_table('PS',cert))

    def test_unknown_atom_rejected(self):
        with self.assertRaises(ValueError):
            dyck_prefix(('S','Z','P'))

    def test_oriented_branching_not_reducible_to_single_inner(self):
        p = make_positive_witness('SPSP')
        self.assertTrue(check_positive_witness('SPSP',p))
        self.assertEqual(p['after_proof']['kind'],'OPEN_INNER_CLOSE_AFTER')

    def test_hash_is_deterministic(self):
        self.assertEqual(sha(('S','P')),sha(('S','P')))
        self.assertNotEqual(sha(('S','P')),sha(('P','S')))

if __name__=='__main__':
    unittest.main(verbosity=2)

class TestContinuationStructure(unittest.TestCase):
    def test_right_context_classes(self):
        from dyck_certificates import future_class_census
        for n in range(1, 7):
            result = future_class_census(n)
            self.assertEqual(result['distinguishable_future_classes'], n + 2)

    def test_symbolic_closers_distinguish_every_open_depth(self):
        from dyck_certificates import prefix_future_signature
        for i in range(7):
            a = ('S',) * i
            signature = prefix_future_signature(a, 6)
            for j in range(7):
                closing = ('P',) * j
                self.assertEqual(closing in signature, i == j)

    def test_bad_prefix_is_irreversible(self):
        from dyck_certificates import prefix_future_signature
        self.assertFalse(prefix_future_signature(('P',), 6))
        self.assertFalse(prefix_future_signature(('P','S','P'), 6))

    def test_continuation_role_swap_requires_swapped_roles(self):
        from dyck_certificates import prefix_future_signature
        right = prefix_future_signature(('S',), 1)
        self.assertIn(('P',), right)
        swapped = prefix_future_signature(('P',), 1)
        self.assertNotIn(('S',), swapped)
        transformed = prefix_future_signature(('A',), 1, opener='A', closer='B')
        self.assertIn(('B',), transformed)

class TestUtf8Lineage(unittest.TestCase):
    def test_utf8_byte_positions(self):
        from dyck_certificates import utf8_token_spans, check_utf8_token_spans
        v = utf8_token_spans(('кот','лес'))
        self.assertEqual([(x['byte_start'],x['byte_end']) for x in v['spans']],[(0,6),(7,13)])
        self.assertTrue(check_utf8_token_spans(v))

    def test_utf8_bad_span_rejected_even_if_source_digest_is_good(self):
        from dyck_certificates import utf8_token_spans, check_utf8_token_spans
        v = utf8_token_spans(('кот','лес'))
        v['spans'][0]['byte_end'] = 3
        self.assertFalse(check_utf8_token_spans(v))

    def test_utf8_fake_word_rejected(self):
        from dyck_certificates import utf8_token_spans, check_utf8_token_spans
        v = utf8_token_spans(('кот','лес'))
        v['tokens'][1] = 'лук'
        self.assertFalse(check_utf8_token_spans(v))
