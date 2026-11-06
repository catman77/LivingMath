import copy
import unittest
from pal_copy_oracle import (words,eval_pal_recursive,eval_copy_halves,verify_pal_trace,
                              candidate_ast, labelled_data, train_errors)

class TestFiniteOracle(unittest.TestCase):
    def test_pal_all_lengths_0_to_8(self):
        for n in range(9):
            for w in words(n):
                result,trace=eval_pal_recursive(w)
                self.assertEqual(result,w==tuple(reversed(w)))
                self.assertTrue(verify_pal_trace(w,result,trace))
    def test_copy_all_lengths_0_to_8(self):
        for n in range(9):
            for w in words(n):
                result,_=eval_copy_halves(w)
                self.assertEqual(result,n%2==0 and w[:n//2]==w[n//2:])
    def test_mixed_lengths_pal_consistent(self):
        for lengths in ([4],[2,4],[1,2,3,4],[1,3,5],[2,4,6]):
            self.assertEqual(train_errors(list(labelled_data(lengths))),[])
    def test_minimal_positive_conflict_is_not_mathematical(self):
        four=list(labelled_data([4]));
        for word in ('SS','PP'):
            train=four+[{'word':word,'length':2,'accepted':True}]
            self.assertEqual(train_errors(train),[])
    def test_minimal_negative_control(self):
        four=list(labelled_data([4]));
        for word in ('SP','PS'):
            train=four+[{'word':word,'length':2,'accepted':False}]
            self.assertEqual(train_errors(train),[])
    def test_wrong_label_is_detected(self):
        rows=list(labelled_data([4]));rows[0]['accepted']=False
        self.assertEqual(train_errors(rows),['SSSS'])
    def test_tampered_trace_rejected(self):
        w=tuple('SSPPSS')
        answer,trace=eval_pal_recursive(w)
        bad=copy.deepcopy(trace);bad[0]['inner']=['P']
        self.assertFalse(verify_pal_trace(w,answer,bad))
    def test_tampered_recurrence_decision_rejected(self):
        w=tuple('SSPSSS')
        answer,trace=eval_pal_recursive(w)
        self.assertFalse(verify_pal_trace(w,not answer,trace))
    def test_out_of_scope_unknown(self):
        a,_=eval_pal_recursive(tuple('S'*10));b,_=eval_copy_halves(tuple('S'*10))
        self.assertIsNone(a);self.assertIsNone(b)
    def test_rename_invariance(self):
        for w in words(6):
            ren=tuple({'S':'кот','P':'лес'}[x] for x in w)
            self.assertEqual(eval_pal_recursive(w)[0],eval_pal_recursive(ren)[0])
    def test_no_endpoint_shortcut(self):
        w=tuple('SSPSSS')
        self.assertEqual(w[0],w[-1]);self.assertFalse(eval_pal_recursive(w)[0])
    def test_ast_is_typed_template_not_hardcoded_answer(self):
        a=candidate_ast()
        self.assertEqual(a['composition'],'iterate_on_inner_fragment')
        self.assertEqual(a['relation']['right_operations'],['REVERSE','SPLIT'])
    def test_train_4_counts(self):
        rows=list(labelled_data([4]));self.assertEqual((len(rows),sum(x['accepted'] for x in rows)),(16,4))
    def test_train_2_plus_4_counts(self):
        rows=list(labelled_data([2,4]));self.assertEqual((len(rows),sum(x['accepted'] for x in rows)),(20,6))
    def test_train_1_to_4_counts(self):
        rows=list(labelled_data([1,2,3,4]));self.assertEqual((len(rows),sum(x['accepted'] for x in rows)),(30,12))
    def test_pal_holdout_6_counts(self):
        rows=list(labelled_data([6]));self.assertEqual((len(rows),sum(x['accepted'] for x in rows)),(64,8))
    def test_pal_holdout_8_counts(self):
        rows=list(labelled_data([8]));self.assertEqual((len(rows),sum(x['accepted'] for x in rows)),(256,16))

if __name__=='__main__':
    unittest.main()
