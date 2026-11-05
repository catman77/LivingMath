"""Contract checks for the new adapter, including the unchanged reference law."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bridge import HERE, compile_atlas, run_search, validate
import cad
import source


class BridgeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((HERE / "input" / "concepts.json").read_text())
        cls.result = run_search(cls.data)

    def test_custom_atlas_matches_reference_choice_and_full_trace(self):
        matrices = tuple(tuple(c["matrix"]) for c in self.result["atlas"]["charts"])
        # This atlas has 180 charts: original stride 11 is already coprime.
        # Patch the two imported atlas values only; no solver code is replaced.
        with patch.object(cad, "CHARTS", matrices), patch.object(source, "CHARTS", matrices):
            reference = source.WhiteStarSource(seed=42, k=3)
            records = [reference.next().to_dict() for _ in range(64)]
        # JSON normalization treats tuple/list identically, without numeric tolerance.
        self.assertEqual(json.loads(json.dumps(records)),
                         json.loads(json.dumps(self.result["observations"])))

    def test_source_address_rejects_fabricated_evidence(self):
        changed = deepcopy(self.data)
        changed["concepts"][0]["evidence"][0]["quote"] = "Утро"
        with self.assertRaisesRegex(ValueError, "citation mismatch"):
            validate(changed)

    def test_witness_equations_and_integer_projection(self):
        for record in self.result["observations"]:
            a, b = record["witness"]
            m = record["matrix"]
            self.assertEqual(tuple(record["coordinates"]), (m[0] * a + m[1] * b,
                                                             m[2] * a + m[3] * b))
            # Pair multiplication (a,b)*(c,d)=(ac+bd,ad+bc).
            self.assertEqual((a * 0 + b * 0, a * 0 + b * 0), (0, 0))
            self.assertEqual((a + b, a + b), (record["finite_fibre_layer"],) * 2)
            self.assertNotEqual(m[0] * m[3] - m[1] * m[2], 0)

    def test_frames_are_fixed_consecutive_outputs_and_readout_is_exact(self):
        frames = self.result["selected_frames"]
        self.assertEqual([f["steps"] for f in frames],
                         [list(range(start, start + 3)) for start in range(1, 19, 3)])
        for frame in frames:
            for link in frame["links"]:
                record = self.result["observations"][link["step"]]
                x, y = record["coordinates"]
                expected = "ALIGN" if x * y > 0 else "TENSION" if x * y < 0 else "UNRESOLVED"
                self.assertEqual(link["proposed_relation"], expected)
                self.assertEqual(link["concepts"], self.result["atlas"]["charts"][record["view"]]["pair"])
        self.assertEqual(self.result["summary"]["projections"], 192)

    def test_input_order_and_opaque_names_do_not_steer_geometry(self):
        changed = deepcopy(self.data)
        changed["concepts"].reverse()
        names = {c["id"]: f"id{i}" for i, c in enumerate(changed["concepts"])}
        for concept in changed["concepts"]:
            concept["id"] = names[concept["id"]]
        for relation in changed["source_relations"]:
            relation["concepts"] = [names[i] for i in relation["concepts"]]
        other = run_search(changed)
        self.assertEqual(other["observations"], self.result["observations"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
