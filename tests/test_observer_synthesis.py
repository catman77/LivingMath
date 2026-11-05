import copy, hashlib, json, asyncio, base64, io, zipfile
from itertools import product
from pathlib import Path
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.white_star.pool import prepare
from lm_suti_assurance.symbolic_complex.service import ExtensionService
from lm_suti_assurance.observer_synthesis.learner import fit, predict
from lm_suti_assurance.observer_synthesis.features import encode, verify_feature
from lm_suti_assurance.observer_synthesis.data import validate_dataset
from lm_suti_assurance.errors import AssuranceError


def record(name, tokens, label=None, lines=None, pair=None):
    tokens = list(tokens)
    text = (
        "\n".join(" ".join(line) for line in lines)
        if lines is not None
        else " ".join(tokens)
    )
    r = {
        "id": name,
        "tokens": tokens,
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "generated test fixture",
            "edition": "generated/1",
        },
    }
    if lines is not None:
        r["lines"] = lines
    if label is not None:
        r["accepted"] = label
    if pair:
        r["pair_id"] = pair
    return r


def dataset(kind, records):
    d = {"schema": "livingmath-observer-dataset/1", "kind": kind, "records": records}
    return {**d, "sha256": digest(d)}


def request():
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": "0" * 64,
            "predict_ref": "1" * 64,
            "holdout_labels_visible": False,
            "structure_levels": ["word", "line"],
            "candidate_transformations": ["REVERSE"],
        },
        "feature_policy": {
            "enabled_builtins": [
                "literal",
                "alpha_pattern",
                "adjacency",
                "composition",
            ],
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
            "representation": "literal",
        },
        "search": {
            "seed": 137,
            "max_composition_depth": 4,
            "max_proposals": 128,
            "max_contexts": 64,
            "max_witnesses": 128,
            "max_cpu_ms": 4000,
        },
    }


def dyck(word):
    height = 0
    for t in word:
        height += 1 if t == "S" else -1
        if height < 0:
            return False
    return height == 0


def train():
    return [
        record("t" + str(i), w, dyck(w))
        for i, w in enumerate(
            [
                w
                for n in (2, 4, 6)
                for w in product("SP", repeat=n)
                if w.count("S") == w.count("P")
            ]
        )
    ]


def test_builtin_origin_and_actual_dependency_ablation():
    q = request()
    m = fit(train(), q)
    pair = next(f for f in m["feature_registry"] if f["feature_id"] == "pair_0_max")
    assert (
        pair["origin"] == "BUILTIN"
        and pair["construction_trace"] is None
        and pair["source_code_binding_sha256"]
    )
    assert "pair_0_max" in m["used_feature_ids"]
    q["feature_policy"]["feature_denylist"] = ["pair_0_max", "endpoint_equal"]
    masked = fit(train(), q)
    assert (
        "pair_0_max" not in masked["enabled_feature_ids"]
        and "pair_0_max" not in masked["used_feature_ids"]
    )
    assert not any(
        f["origin"] == "DERIVED_FROM_OPERATORS" for f in masked["feature_registry"]
    )
    for only in ("literal", "alpha_pattern", "adjacency"):
        q = request()
        q["feature_policy"]["enabled_builtins"] = [only]
        model = fit(train(), q)
        assert not any(f.startswith("pair_") for f in model["enabled_feature_ids"])


def test_true_existing_operator_composition_and_corrupt_origin():
    samples = [
        record(str(i), w, label)
        for i, (w, label) in enumerate(
            [(w, True) for w in ["ABBA", "BAAB", "AAAA", "BBBB"]]
            + [(w, False) for w in ["AABB", "BBAA", "ABAB", "BABA"]]
        )
    ]
    m = fit(samples, request())
    derived = [
        f for f in m["feature_registry"] if f["origin"] == "DERIVED_FROM_OPERATORS"
    ]
    assert derived
    rows = [{"record": r, "encoded": encode(r, "literal")} for r in samples]
    for feature in derived:
        assert verify_feature(feature, rows)["status"] == "CHECKED_FINITE_INSTANCE"
    bad = copy.deepcopy(derived[0])
    bad["construction_trace"][0]["operator_trace"][0]["operator"] = "invented"
    assert verify_feature(bad, rows)["status"] == "REJECTED"
    assert (
        verify_feature(
            {"origin": "DERIVED_FROM_OPERATORS", "execution_verified": True}, rows
        )["status"]
        == "REJECTED"
    )
    assert (
        m["competing_train_compatible_models"]
        and m["identifiability_status"] == "UNDERDETERMINED"
    )
    assert any(
        r["status"] == "UNKNOWN" and r["right_membership"] is None
        for r in m["context_relations"]
    )


def test_blind_dyck_heldout_and_freeze():
    samples = train()
    assert len(samples) == 28
    q = request()
    m = fit(samples, q)
    seal = m["hypothesis_digest"]
    for n, expected, total in [(8, 14, 70), (10, 42, 252)]:
        words = [w for w in product("SP", repeat=n) if w.count("S") == w.count("P")]
        queries = [record("q" + str(i), w) for i, w in enumerate(words)]
        assert len(words) == total and sum(dyck(w) for w in words) == expected
        values = predict(m, queries)["predictions"]
        assert all((r["score"] >= 0.5) == dyck(w) for r, w in zip(values, words))
    assert (
        m["hypothesis_digest"] == seal and fit(samples, q)["hypothesis_digest"] == seal
    )
    query = record("bad", "SP", True)
    with pytest.raises(AssuranceError) as error:
        validate_dataset(dataset("queries", [query]))
    assert error.value.code == "HELDOUT_LABEL_LEAKAGE"


def test_contradiction_nonidentifiability_and_tie():
    q = request()
    q["feature_policy"]["representation"] = "global_alpha"
    samples = [record("a", "SP", True), record("b", "PS", False)]
    m = fit(samples, q)
    assert m["training_status"] == "CONTRADICTORY_TRAINING" and m["tree"] is None
    queries = [record("x", "XY", pair="pair"), record("y", "YX", pair="pair")]
    result = predict(m, queries)
    assert result["pairs"][0]["status"] == "NOT_IDENTIFIABLE"
    assert result["pairs"][0]["equality_witness"]
    q = request()
    q["feature_policy"]["enabled_builtins"] = []
    q["feature_policy"]["derive_relations"] = False
    m = fit(train(), q)
    assert m["enabled_feature_ids"] == []
    queries = [record("x", "SSPP", pair="pair"), record("y", "PSPS", pair="pair")]
    assert predict(m, queries)["pairs"][0]["status"] == "TIE"


@pytest.fixture(scope="module")
def executor():
    assert prepare()["ready"]
    pool = Executor()
    assert pool.status()["ready"]
    yield pool
    pool.close()


def test_real_worker_storage_replay_and_isolation(tmp_path, executor):
    from lm_suti_assurance.symbolic_complex.bundle import export

    service = ExtensionService(tmp_path, executor)
    service.base.new("qa", "new")
    service.base.new("other", "new")
    a = service.dataset_store("qa", "train", dataset("train", train()))
    b = service.dataset_store(
        "qa", "queries", dataset("queries", [record("q", "SSPP")])
    )
    q = request()
    q["task"].update(train_ref=a["dataset_ref"], predict_ref=b["dataset_ref"])
    first = asyncio.run(service.run("qa", "fit", "observer_synthesis_v1", q))
    assert first["status"] == "COMPLETED", first
    assert asyncio.run(service.run("qa", "fit", "observer_synthesis_v1", q)) == first
    with pytest.raises(AssuranceError):
        asyncio.run(service.run("other", "fit", "observer_synthesis_v1", q))
    raw, manifest = export(service.workspace("qa"), first["run_id"])
    r = executor.run(
        {"action": "extension_replay", "bundle_base64": base64.b64encode(raw).decode()}
    )["data"]
    assert (
        r["status"] == "REPLAY_MATCH" and r["result_digest"] == first["result_digest"]
    )
    data = service.inspect("qa", first["run_id"], "model")
    assert data["items"] or data["requires_artifact"]
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as source,
        zipfile.ZipFile(stream, "w") as target,
    ):
        for name in source.namelist():
            target.writestr(
                name,
                (
                    source.read(name) + b" "
                    if name == "journal.jsonl"
                    else source.read(name)
                ),
            )
    with pytest.raises(AssuranceError):
        executor.run(
            {
                "action": "extension_replay",
                "bundle_base64": base64.b64encode(stream.getvalue()).decode(),
            }
        )


def test_exact_source_validation_and_empty_builtin_allowlist():
    q = request()
    q["feature_policy"].update(feature_allowlist=[], derive_relations=True)
    model = fit(train(), q)
    assert not model["used_feature_ids"] and not model["enabled_feature_ids"]
    data = dataset("queries", [record("q", "SP")])
    data["records"][0]["source"]["sha256"] = "0" * 64
    data["sha256"] = digest({k: v for k, v in data.items() if k != "sha256"})
    with pytest.raises(AssuranceError) as err:
        validate_dataset(data)
    assert err.value.code == "SOURCE_MISMATCH"


def test_saved_history_uses_only_real_operations_and_denies_cross_project(
    tmp_path, executor
):
    from lm_suti_assurance.symbolic.service import SymbolicService
    from lm_suti_assurance.symbolic_complex.checker import verify
    from lm_suti_assurance.white_star.blobs import get

    old = SymbolicService(tmp_path, executor)
    old.base.new("qa", "new")
    q = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
        ).read_text()
    )["request"]
    q["search"].update(max_steps=4, max_nodes=64)
    original = asyncio.run(old.explore("qa", "old", q))
    service = ExtensionService(tmp_path, executor)
    request = {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "saved_symbolic_history",
            "project": "qa",
            "run_id": original["run_id"],
            "only_verified_edges": True,
        },
        "cells": {"policy": "all_local_peaks", "join_depth_limit": 1},
        "analysis": ["graph_cycles", "homology_F2", "pi1_certificate"],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }
    result = asyncio.run(service.run("qa", "saved", "symbolic_complex_v1", request))
    assert result["status"] == "COMPLETED", result
    assert result["summary"]["pi1_status"] == "NOT_PROVED"
    w, r = service.load("qa", result["run_id"])
    artifact = get(w, r["result_ref"])
    assert verify(artifact)["status"] == "NOT_PROVED"
    original_artifact = get(w, original["result_ref"])
    assert len(artifact["vertices"]) == len(original_artifact["states"])
    bad = copy.deepcopy(artifact)
    bad["edges"][0]["provenance"]["history_node_id"] = "f" * 64
    assert verify(bad)["status"] == "REJECTED"
    request["complex_source"]["project"] = "other"
    with pytest.raises(AssuranceError) as err:
        asyncio.run(service.run("qa", "foreign", "symbolic_complex_v1", request))
    assert err.value.code == "PROJECT_ISOLATION"


def test_explicit_empirical_conflict_mode_keeps_every_label_and_reports_conflict():
    q = request()
    q["feature_policy"]["representation"] = "global_alpha"
    q["task"]["conflict_policy"] = "retain_as_empirical"
    samples = [record("a", "SP", True), record("b", "PS", False)]
    m = fit(samples, q)
    assert m["status"] == "CONTRADICTORY_TRAINING" and m["empirical_conflict_training"]
    assert (
        m["training_conflicts"]
        and not m["excluded_record_refs"]
        and len(m["source_train_refs"]) == 2
    )
    assert m["competing_train_compatible_models"] == [] and m["tree"] is not None
    assert (
        predict(m, [record("x", "XY", pair="pair"), record("y", "YX", pair="pair")])[
            "pairs"
        ][0]["status"]
        == "NOT_IDENTIFIABLE"
    )


def test_real_fastmcp_boundary_for_complex_and_observer_tools(tmp_path, executor):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.symbolic_complex.mcp import register_tools
    from lm_suti_assurance.symbolic_complex.contracts import REQUEST

    server = FastMCP("extension-test")
    service = register_tools(server, tmp_path, executor)
    service.base.new("qa", "new")
    q = {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "sp_balanced_fixture",
            "max_length": 4,
            "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
            "edge_identity": "source_position_rule",
        },
        "cells": {"policy": "all_local_peaks", "join_depth_limit": 1},
        "analysis": ["graph_cycles", "homology_F2", "pi1_certificate"],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }

    async def run():
        value = await server._tool_manager.call_tool(
            "white_star_symbolic_complex_analyze",
            {"project": "qa", "request_key": "p0", "request": q},
            convert_result=False,
        )
        assert value.structuredContent["ok"]
        record = value.structuredContent["data"]
        assert record["summary"]["pi1_status"] == "PROVED_TRIVIAL_WITH_CERTIFICATE"
        response = await server._tool_manager.call_tool(
            "white_star_symbolic_complex_verify",
            {
                "project": "qa",
                "run_id": record["run_id"],
                "certificate_ref": record["section_refs"]["paths"],
            },
            convert_result=False,
        )
        assert response.structuredContent["data"]["status"] == "CHECKED_INSTANCE"
        result = await server._tool_manager.call_tool(
            "white_star_symbolic_complex_verify",
            {
                "project": "qa",
                "run_id": record["run_id"],
                "certificate": {"paths": None},
            },
            convert_result=False,
        )
        assert result.structuredContent["data"]["status"] == "NOT_PROVED"

    asyncio.run(run())


def test_context_composition_reencodes_after_permutation_and_keeps_source_lineage():
    q = request()
    q["task"]["candidate_transformations"] = ["SWAP_LINES_2_3"]
    q["feature_policy"]["representation"] = "global_alpha"
    lines = [["a", "b"], ["c", "a"], ["b", "c"], ["d", "a"]]
    other = [lines[i] for i in [0, 2, 1, 3]]
    samples = [
        record("first", [x for l in lines for x in l], True, lines),
        record("second", [x for l in other for x in l], False, other),
    ]
    model = fit(samples, q)
    relations = model["context_relations"]
    assert relations
    assert all(r["structural_scope"] == "line_in_source_record" for r in relations)
    assert all(
        r["operator_trace"]
        and all("input_lineage_digest" in step for step in r["operator_trace"])
        for r in relations
    )
    assert any(r["status"] == "DISTINGUISHED" for r in relations)
    assert all(
        r["source_sha256"] in {s["source"]["sha256"] for s in samples}
        for r in relations
    )


def test_operator_only_synthesis_does_not_compute_hidden_builtin_features(monkeypatch):
    from lm_suti_assurance.observer_synthesis import features

    samples = [
        record(str(i), w, label)
        for i, (w, label) in enumerate(
            [(w, True) for w in ["ABBA", "BAAB", "AAAA", "BBBB"]]
            + [(w, False) for w in ["AABB", "BBAA", "ABAB", "BABA"]]
        )
    ]
    q = request()
    q["feature_policy"]["feature_allowlist"] = ["derived:*"]
    model = fit(samples, q)
    assert model["enabled_feature_ids"] and all(
        n.startswith("derived_") for n in model["enabled_feature_ids"]
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "builtin calculator must not run in operator-only prediction"
        )

    monkeypatch.setattr(features.grammar, "features", forbidden)
    result = predict(model, [record("query", "ABCCBA")])
    assert result["predictions"][0]["score"] is not None


def test_export_pages_freeze_one_journal_prefix_and_reuse_cache(
    tmp_path, executor, monkeypatch
):
    from lm_suti_assurance.symbolic_complex import bundle

    service = ExtensionService(tmp_path, executor)
    service.base.new("qa", "new")
    q = {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "sp_balanced_fixture",
            "max_length": 4,
            "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
            "edge_identity": "source_position_rule",
        },
        "cells": {"policy": "all_local_peaks", "join_depth_limit": 1},
        "analysis": ["graph_cycles", "homology_F2"],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }
    row = asyncio.run(service.run("qa", "complex", "symbolic_complex_v1", q))
    first = service.inspect("qa", row["run_id"], "export")
    service.dataset_store("qa", "later", dataset("queries", [record("extra", "SP")]))

    def forbidden(*args, **kwargs):
        raise AssertionError("immutable export snapshot must not rebuild")

    monkeypatch.setattr(bundle, "export", forbidden)
    again = service.inspect("qa", row["run_id"], "export")
    assert first == again
    ref = first["items"][0]["bundle_ref"]
    path = service.workspace("qa").path / ".extension-exports" / (ref + ".zip")
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(AssuranceError) as error:
        service.inspect("qa", row["run_id"], "export")
    assert error.value.code == "EXPORT_INTEGRITY_FAILURE"
