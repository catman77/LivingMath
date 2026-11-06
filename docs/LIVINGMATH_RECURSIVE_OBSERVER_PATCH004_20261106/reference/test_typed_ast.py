#!/usr/bin/env python3
import copy, unittest
from typed_ast_reference import (AST_PAL, AST_COPY, issue, verify, evaluate,
     words_of_length, pal_oracle, copy_oracle, Rejected, NotProved, token_source, digest)

class TestTypedComposition(unittest.TestCase):
    def test_pal_complete_n4_n6_n8(self):
        for n in (4,6,8):
            ws=words_of_length(n)
            cert=issue(AST_PAL, ws, 8)
            self.assertEqual(verify(cert,ws)['verified_witnesses'],2**n)
            self.assertEqual([x['value'] for x in cert['witnesses']], [pal_oracle(x) for x in ws])
    def test_copy_complete_n4_n6_n8(self):
        for n in (4,6,8):
            ws=words_of_length(n)
            cert=issue(AST_COPY,ws,8)
            self.assertEqual(verify(cert,ws)['verified_witnesses'],2**n)
            self.assertEqual([x['value'] for x in cert['witnesses']], [copy_oracle(x) for x in ws])
    def test_odd(self):
        for n in (1,3,5,7):
            for w in words_of_length(n):
                self.assertTrue(evaluate(AST_PAL,w,8)[0]==pal_oracle(w))
                self.assertFalse(evaluate(AST_COPY,w,8)[0])
    def test_unicode_source_spans(self):
        w=('кот','лес','кот')
        source=token_source(w)
        self.assertEqual(source['text'].encode('utf-8')[source['spans'][0][0]:source['spans'][0][1]],'кот'.encode())
        self.assertEqual(verify(issue(AST_PAL,[w],8),[w])['verified_witnesses'],1)
    def test_reject_tampered_result(self):
        c=issue(AST_PAL,words_of_length(4),8)
        b=copy.deepcopy(c);b['witnesses'][0]['value']=False;b['witness_set_digest']=digest(b['witnesses'])
        with self.assertRaisesRegex(Rejected,'OPERATOR_REPLAY_MISMATCH'):verify(b)
    def test_reject_tampered_trace_even_with_rehash(self):
        c=issue(AST_PAL,words_of_length(4),8)
        b=copy.deepcopy(c);b['witnesses'][0]['trace'][0]['op']='MAGIC';b['witness_set_digest']=digest(b['witnesses'])
        with self.assertRaisesRegex(Rejected,'OPERATOR_REPLAY_MISMATCH'):verify(b)
    def test_reject_tampered_utf8_span(self):
        c=issue(AST_PAL,[('кот','лес','кот')],8)
        b=copy.deepcopy(c);b['witnesses'][0]['source']['spans'][0][0]=1;b['witness_set_digest']=digest(b['witnesses'])
        with self.assertRaisesRegex(Rejected,'UTF8_SOURCE'):verify(b)
    def test_reject_tampered_source_hash(self):
        c=issue(AST_COPY,words_of_length(4),8)
        b=copy.deepcopy(c);b['witnesses'][0]['source']['sha256']='0'*64;b['witness_set_digest']=digest(b['witnesses'])
        with self.assertRaisesRegex(Rejected,'UTF8_SOURCE'):verify(b)
    def test_reject_missing_witness(self):
        ws=words_of_length(4);c=issue(AST_PAL,ws,8)
        b=copy.deepcopy(c);b['witnesses'].pop();b['witness_set_digest']=digest(b['witnesses'])
        with self.assertRaisesRegex(Rejected,'WITNESS_MISSING'):verify(b,ws)
    def test_reject_false_universal_claim(self):
        c=issue(AST_PAL,words_of_length(4),8);c['universal_invariant']=True
        with self.assertRaisesRegex(Rejected,'FALSE_UNIVERSAL_CLAIM'):verify(c)
    def test_reject_unsupported_ast(self):
        with self.assertRaisesRegex(Rejected,'AST_NOT_IN_TYPED_ALLOWLIST'):
            issue({'composition':'PythonEval','code':'print(1)'},words_of_length(2),8)
    def test_reject_malformed_ast_mutation(self):
        c=issue(AST_PAL,words_of_length(4),8)
        b=copy.deepcopy(c);b['ast']['trim_left']=2;b['ast_digest']=digest(b['ast'])
        with self.assertRaisesRegex(Rejected,'AST_NOT_IN_TYPED_ALLOWLIST'):verify(b)
    def test_scope_guard(self):
        with self.assertRaisesRegex(NotProved,'OUT_OF_DECLARED_SCOPE'):
            evaluate(AST_PAL,tuple('S'*9),8)
        with self.assertRaisesRegex(Rejected,'OUT_OF_SCOPE'):
            c=issue(AST_PAL,words_of_length(4),8)
            w=tuple('S'*9)
            c['witnesses'].append({'tokens':list(w),'source':token_source(w),'value':True,'trace':[]})
            c['witness_set_digest']=digest(c['witnesses']);verify(c)
    def test_no_destruction_of_token_order(self):
        self.assertTrue(evaluate(AST_PAL,tuple('SPPS'),8)[0])
        self.assertFalse(evaluate(AST_PAL,tuple('SPSP'),8)[0])
        self.assertTrue(evaluate(AST_COPY,tuple('SPSP'),8)[0])
        self.assertFalse(evaluate(AST_COPY,tuple('SPPS'),8)[0])
    def test_distinguish_endpoint_from_pal(self):
        w=tuple('SPSPPS')
        self.assertEqual(w[0],w[-1]);self.assertFalse(evaluate(AST_PAL,w,8)[0])
    def test_dyck_not_same_as_balanced(self):
        def dyck(w):
            h=0
            for a in w:
                h += (1 if a=='S' else -1)
                if h<0: return False
            return h==0
        self.assertTrue('PS' .count('P') == 'PS'.count('S'))
        self.assertFalse(dyck('PS'))
        self.assertTrue(dyck('SP'))

if __name__=='__main__':unittest.main(verbosity=2)
