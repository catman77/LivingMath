"""Fast checks of shipped *reference* oracles. Does NOT certify the future server patch.
Run: python -m unittest discover -s tests -v
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "reference_oracles"
sys.path.insert(0, str(REF))


class Baselines(unittest.TestCase):
    def test_split_oracle(self):
        import oracle_substrings as m
        result, plan = m.plan_greedy()
        self.assertEqual(len(result), 22)
        self.assertLessEqual(len(plan), 24)
        self.assertEqual(result, m.TARGET)

    def test_numeric_reference(self):
        import independent_native_reference as m
        q = m.atlas([(i, i*i) for i in range(1,9)])
        self.assertEqual(len(q), 112)
        for (seed, k), expected in m.EXPECTED.items():
            got = m.native_reference(seed, k, q)
            self.assertEqual(got['selected'], expected)
        self.assertEqual(len(m.EXPECTED), 4)

    def test_factorial_baseline_budget(self):
        import factorial_frontier as m
        self.assertEqual(m.ATTEMPTS, 72)
        self.assertEqual(len(m.TARGET), 22)
        self.assertEqual(len(m.SEEDS), 30)

    def test_frozen_comparator_available(self):
        import frozen_counterfactual as f
        self.assertIn('pair_after_novelty', Path(f.__file__).read_text())
        self.assertEqual(len(f.CHARTS), 112)

    def test_manifest_and_dont_confuse_hashes(self):
        doc = json.loads((ROOT/'fixtures/CODE_BASELINE.json').read_text())
        self.assertEqual(len(doc['git_blob_sha']), 8)
        self.assertEqual(doc['tool_count_observed'], 94)
        self.assertTrue(all(len(h)==40 for h in doc['git_blob_sha'].values()))
        self.assertEqual(len(doc['known_mcp_runs']), 8)

if __name__ == '__main__':
    unittest.main()
