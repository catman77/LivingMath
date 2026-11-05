from copy import deepcopy
from fractions import Fraction
import json
import unittest

from rotated_atlas import (HERE, load_case, expand, exact_field, search, audit_search,
                           reference_replay, rotate, decode_observations, qualitative)
from formal_models import verify_transfers, mat, mul, inverse2, serial
from transfer_audit import transfer_mutations


class TransferContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.old_trace, cls.frames, cls.prose = load_case()
        cls.protocol = json.loads((HERE/'protocol.json').read_text())
        cls.proposal = json.loads((HERE/'transfer_proposal.json').read_text())
        cls.atlas = expand(cls.data)
        cls.field = exact_field(cls.data, cls.atlas)
        cls.trace, cls.readouts, cls.diagnostics = search(cls.data, cls.atlas, cls.protocol)

    def test_native_matches_unchanged_reference_under_same_budget(self):
        self.assertTrue(reference_replay(self.data, self.atlas, self.trace, self.protocol))
        self.assertEqual(self.diagnostics['steps'], 64)
        self.assertEqual(self.diagnostics['projections'], 192)
        self.assertTrue(all(len(r['candidate_views'])==3 for r in self.trace))

    def test_complete_mode_extension_and_old_modes_retained(self):
        summary = self.field['summary']
        self.assertEqual((summary['old_modes'], summary['new_modes']), (344,720))
        self.assertTrue(summary['old_modes_preserved'])
        self.assertEqual(summary['fixed_relation_pairs'],0)
        for pair in self.field['pairs']:
            self.assertEqual(len(pair['witnesses']),8)
            for w in pair['witnesses']:
                a,b=w['witness'];m=self.atlas['charts'][w['view']]['matrix']
                self.assertGreater(a+b,0)
                self.assertGreaterEqual(min(a,b),0)
                x,y=m[0]*a+m[1]*b,m[2]*a+m[3]*b
                self.assertEqual(qualitative(w['alias']['concepts'],x,y),tuple(w['state']))

    def test_independent_constructive_inverse_for_every_pair_and_mode(self):
        # Independent of the boundary partition: inverse images of eight
        # representative outputs must enter I(Q+) or J(Q+) up to common sign.
        representatives=[(1,1),(2,1),(1,2),(1,-1),(2,-1),(1,-2),(0,1),(1,0)]
        for chart in self.atlas['charts'][:180]:
            c=chart['matrix'];inverse=inverse2(mat([c[:2],c[2:]]))
            for x,y in representatives:
                z=mul(inverse,mat([[x],[y]]));za,zb=z[0][0],z[1][0]
                solutions=[]
                for sign in (1,-1):
                    for phase in ('I','J'):
                        # q = z, or J^-1 z=(z_b,-z_a).
                        a,b=(sign*za,sign*zb) if phase=='I' else (sign*zb,-sign*za)
                        if a>=0 and b>=0:
                            m=c if phase=='I' else rotate(c)
                            px,py=m[0]*a+m[1]*b,m[2]*a+m[3]*b
                            self.assertEqual((px,py),(sign*x,sign*y))
                            solutions.append((phase,a,b))
                self.assertTrue(solutions)
        c=(4,3,3,4);turned=rotate(c)
        self.assertEqual(qualitative(['death','restart'],7,7)[2],'ALIGN')
        self.assertEqual(qualitative(['death','restart'],turned[0]+turned[1],turned[2]+turned[3])[2],'TENSION')

    def test_numeric_duplicates_keep_all_semantic_aliases(self):
        charts=self.atlas['charts']
        self.assertEqual(len(charts),354)
        self.assertEqual(sum(len(c['aliases']) for c in charts),360)
        self.assertEqual(len({tuple(c['matrix']) for c in charts}),354)
        for chart in charts:
            for alias in chart['aliases']:
                expected=tuple(alias['original_matrix']) if alias['orientation']=='I' else rotate(alias['original_matrix'])
                self.assertEqual(expected,tuple(chart['matrix']))
        for chart in [c for c in charts if len(c['aliases'])>1]:
            m=chart['matrix']
            r=dict(step=123,view=chart['view'],witness=[1,1],coordinates=[m[0]+m[1],m[2]+m[3]])
            decoded=decode_observations(self.atlas,[r])
            self.assertEqual(len(decoded[0]['alternatives']),len(chart['aliases']))

    def test_budget_tradeoff_is_reported_not_hidden(self):
        audit=audit_search(self.data,self.atlas,self.readouts,self.field)
        self.assertEqual(audit['unique_modes'],52)
        self.assertEqual(audit['newly_possible_modes_visited'],10)
        self.assertEqual(audit['ambiguous_numeric_observations'],0)

    def test_three_formal_models_with_concrete_counterexamples(self):
        checked=verify_transfers(self.proposal,self.data,self.prose)
        a,b,c=checked['units']
        self.assertEqual(a['x_next'],[[1],[2]])
        self.assertEqual(a['observed'],[[1]])
        self.assertEqual(b['x_after_control'],[[0],[1]])
        self.assertEqual(b['countermodel_final_state'],[[0],[0]])
        self.assertEqual(c['first'],[[2,2],[1,2]])
        self.assertEqual(c['last'],[[2,1],[2,2]])
        self.assertEqual(c['characteristic_polynomial'],[1,-4,2])
        self.assertNotEqual(c['first_output'],c['last_output'])

    def test_invalid_target_models_rejected(self):
        faults=transfer_mutations(self.proposal,self.data,self.prose)
        self.assertEqual(len(faults),6)
        self.assertTrue(all(f['status']=='REJECTED' for f in faults))

    def test_false_source_attribution_and_wrong_order_rejected(self):
        changed=deepcopy(self.proposal)
        changed['units'][0]['source']['source_status']='EMPIRICAL_LAW'
        with self.assertRaises(ValueError): verify_transfers(changed,self.data,self.prose)
        changed=deepcopy(self.proposal)
        changed['units'][2]['last_order']=['lamp','street','pharmacy']
        with self.assertRaises(ValueError): verify_transfers(changed,self.data,self.prose)


if __name__=='__main__':
    unittest.main(verbosity=2)
