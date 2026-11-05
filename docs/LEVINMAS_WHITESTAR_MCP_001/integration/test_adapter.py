from copy import deepcopy
import json
from pathlib import Path
import unittest

from white_star_adapter import ROOT, ContractError, encode, explore


class AdapterContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = json.loads((ROOT/'fixtures/blok_request.json').read_text())
        cls.result = explore(cls.request)

    def test_exact_003_trace_and_all_alias_readouts(self):
        base = ROOT/'code/experiments/llm_white_star_transfer/results'
        trace = [json.loads(x) for x in (base/'trace.jsonl').read_text().splitlines()]
        self.assertEqual(encode(self.result['trace']), encode(trace))
        expected = json.loads((base/'readouts.json').read_text())
        actual = [{k: v for k, v in r.items() if k not in ('signed_weights', 'claim_status')}
                  for r in self.result['readouts']]
        self.assertEqual(encode(actual), encode(expected))
        self.assertEqual(self.result['summary']['projections'], 192)
        self.assertEqual(self.result['summary']['unique_qualitative_modes'], 52)
        self.assertEqual(len(self.result['selected_frames']), 6)

    def test_base_profile_matches_001_trace(self):
        request = deepcopy(self.request); request['atlas_profile'] = 'base_v1'
        actual = explore(request)
        expected = [json.loads(x) for x in (ROOT/'code/experiments/llm_white_star/results/trace.jsonl').read_text().splitlines()]
        self.assertEqual(encode(actual['trace']), encode(expected))
        self.assertEqual(actual['summary']['unique_numeric_maps'], 180)

    def test_replay_and_request_immutability(self):
        before = encode(self.request)
        self.assertEqual(encode(explore(self.request)), encode(self.result))
        self.assertEqual(encode(self.request), before)

    def test_second_text_no_blok_names_or_model_calls(self):
        request = json.loads((ROOT/'fixtures/original_request.json').read_text())
        result = explore(request)
        self.assertEqual(result['summary']['steps'], 32)
        self.assertEqual(result['summary']['projections'], 96)
        ids = {c['id'] for c in request['encoding']['concepts']}
        self.assertEqual(ids, {'key', 'door', 'wind', 'home'})
        for r in result['readouts']:
            for alias in r['alternatives']:
                self.assertTrue(set(alias['alias']['concepts']) <= ids)
        self.assertEqual(result['status']['prose'], 'NOT_GENERATED')

    def test_input_mutations_rejected(self):
        changes = [
            lambda q: q['encoding']['source'].__setitem__('sha256', '0'*64),
            lambda q: q['encoding']['concepts'][0]['evidence'][0].__setitem__('byte_start', 1),
            lambda q: q['encoding']['protocol'].__setitem__('steps', True),
            lambda q: q['encoding']['protocol'].__setitem__('steps', 4097),
            lambda q: q['encoding']['protocol'].__setitem__('semantic_reranking', True),
            lambda q: q.__setitem__('atlas_profile', 'hidden_full_search'),
        ]
        for change in changes:
            q = deepcopy(self.request); change(q)
            with self.assertRaises((ValueError, ContractError)): explore(q)

    def test_expanded_atlas_limit_is_checked_before_native_run(self):
        q = deepcopy(self.request)
        proto = q['encoding']['concepts'][0]
        q['encoding']['concepts'] = []
        for i in range(1, 47):
            c = deepcopy(proto); c.update(id=f'c{i}', coordinates=[i, i*i+1])
            q['encoding']['concepts'].append(c)
        q['encoding']['source_relations'] = []
        with self.assertRaisesRegex(ContractError, 'exceeds native limit'):
            explore(q)

    def test_tiny_budget_returns_partial_frame_count(self):
        q = deepcopy(self.request)
        q['encoding']['protocol'].update(steps=1, frame_size=1)
        r = explore(q)
        self.assertEqual(r['summary']['steps'], 1)
        self.assertEqual(r['summary']['nonzero_observations'], 0)
        self.assertEqual(r['selected_frames'], [])

    def test_common_input_hash_changes_only_with_common_input(self):
        q = deepcopy(self.request)
        q['encoding']['concepts'][0]['coordinates'] = [-3, -4]
        changed = explore(q)
        self.assertEqual(changed['common_snapshot_sha256'], self.result['common_snapshot_sha256'])
        self.assertNotEqual(changed['encoding_sha256'], self.result['encoding_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
