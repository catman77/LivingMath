"""Acceptance PATCH001: external labels stay outside the grammar module."""

import copy, json, hashlib
from pathlib import Path
import pytest
from lm_suti_assurance.symbolic.grammar import (
    fit,
    probability,
    prediction,
    relation_value,
)
from lm_suti_assurance.core import digest

TRAIN = [
    {"tokens": list(w), "accepted": label}
    for label, words in [
        (True, ["ABBA", "BAAB", "AAAA", "BBBB"]),
        (False, ["AABB", "BBAA", "ABAB", "BABA"]),
    ]
    for w in words
]
HELDOUT = [
    "ABCCBA",
    "ABCBCA",
    "ABCABC",
    "ABBAABBA",
    "AABBAA",
    "ABABBA",
    "BAABAB",
    "AAAAAA",
    "ABABAB",
]


def test_train_derived_recurring_fragment_relation_corrects_endpoint_failure():
    model = fit(TRAIN)
    assert model["relational_rule_ast"]["composition"] == "iterate_on_inner_fragment"
    assert all((probability(model, list(w)) >= 0.5) == (w == w[::-1]) for w in HELDOUT)
    assert model["status"] == model["identifiability_status"] == "UNDERDETERMINED"
    assert (
        model["candidate_status"] == "EMPIRICAL"
        and len(model["train_compatible_candidates"]) >= 2
    )
    assert model["rule_witnesses"] and model["counterexample_candidates"]
    assert any(
        prediction(model, list(w))["family_verdict"] == "INCONCLUSIVE"
        for w in ("ABCBCA", "ABABBA", "BAABAB")
    )
    for candidate in model["train_compatible_candidates"]:
        assert candidate["training_errors"] == 0
        if "ast" in candidate:
            assert all(
                relation_value(candidate["ast"], s["tokens"]) == s["accepted"]
                for s in TRAIN
            )
    for probe in model["counterexample_candidates"]:
        assert (
            probe["label"] == "REQUIRED_FROM_EXTERNAL_HOLDER"
            and len(set(probe["candidate_predictions"].values())) > 1
        )
        assert probe["tokens"] not in [s["tokens"] for s in TRAIN]


def test_no_predict_input_or_name_label_in_rule_derivation():
    g = fit(TRAIN)
    before = copy.deepcopy(g)
    for words in (HELDOUT, ["opaque", "unrelated", "sample"]):
        for word in words:
            prediction(g, list(word))
    assert g == before and fit(list(reversed(TRAIN))) == g
    for scope in ("local", "global"):
        renamed = [
            {
                "tokens": [{"A": "X", "B": "Y"}[t] for t in s["tokens"]],
                "accepted": s["accepted"],
            }
            for s in TRAIN
        ]
        other = fit(renamed, renaming_scope=scope)
        assert other["relational_rule_ast"] == g["relational_rule_ast"]
        for w in HELDOUT:
            mapped = [{"A": "X", "B": "Y", "C": "Z"}[t] for t in w]
            assert (probability(other, mapped) >= 0.5) == (
                probability(g, list(w)) >= 0.5
            )


def test_relational_AST_budget_and_missing_observers_remain_explicit():
    tiny = fit(TRAIN, max_rules=3)
    assert (
        not tiny["relational_rule_ast"]
        and tiny["identifiability_status"] == "UNDERDETERMINED"
    )
    no_composition = fit(TRAIN, observers=["literal", "adjacency"])
    assert not no_composition["relational_rule_ast"]
    assert (
        no_composition["candidate_derivation_trace"][0]["reason"]
        == "REQUIRED_RELATIONAL_OBSERVERS_ABSENT"
    )


@pytest.fixture(scope="module")
def executor():
    from lm_suti_assurance.white_star.pool import prepare
    from lm_suti_assurance.symbolic.executor import Executor

    assert prepare()["ready"]
    pool = Executor()
    assert pool.status()["ready"]
    yield pool
    pool.close()


def request(text="SSPPSPSP", identity="word"):
    root = Path(__file__).resolve().parents[1]
    value = json.loads(
        (
            root / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
        ).read_text()
    )["request"]
    value["source"].update(text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    value["search"].update(
        seed=119,
        max_steps=128,
        max_nodes=256,
        max_word_tokens=64,
        history_identity=identity,
    )
    return value


def test_local_saturation_certificate_does_not_claim_full_operator_closure(executor):
    value = executor.run({"action": "explore", "request": request()})["data"]
    assert (
        value["summary"]["halt_reason"] == "NO_NOVEL_CANDIDATES"
        and value["summary"]["steps"] < 128
    )
    cert = value["search_diagnostics"][0]
    assert not cert["global_exhaustion_proved"] and cert["unseen_variants_may_exist"]
    assert (
        cert["tested_variants"] and "INSERT_CANCEL_PAIR" in cert["unproposed_operators"]
    )
    assert all(not c.get("new_outputs") for c in cert["tested_variants"])
    assert cert["current_node_id"] in {n["node_id"] for n in value["history"]}
    provenance = executor.run(
        {"action": "explore", "request": request(identity="provenance")}
    )["data"]
    assert provenance["summary"]["nodes"] > value["summary"]["nodes"]
    assert provenance["summary"]["halt_reason"] != "NO_NOVEL_CANDIDATES"
    assert len({s["word_hash"] for s in provenance["states"]}) < len(
        provenance["states"]
    )


def test_saved_run_comparisons_have_source_spans_and_exact_reductions(
    tmp_path, executor
):
    import asyncio
    from lm_suti_assurance.symbolic.service import SymbolicService

    service = SymbolicService(tmp_path, executor)
    service.base.new("qa", "new")

    def run(text, key):
        return asyncio.run(service.explore("qa", key, request(text)))["run_id"]

    ab = run("SSPPSPSP", "ab")
    ba = run("SPSPSSPP", "ba")
    cd = run("SPPSPSSP", "cd")
    dc = run("PSSPSPPS", "dc")
    for left, right in ((ab, ba), (cd, dc)):
        c = service.inspect("qa", left, "comparison", compare_run_id=right)["items"][0]
        assert not c["same_literal"] and c["same_sp_normal_form"]
        assert not c["same_history"] and not c["same_op_trace"]
        assert c["literal_witness"]["left"]["original_byte_spans"]
        assert (
            c["sp_witness"]["left_reduction_route"]
            and c["sp_witness"]["right_reduction_route"]
        )
    same = service.compare("qa", ab, ab)
    assert all(
        same[n]
        for n in (
            "same_literal",
            "same_alpha",
            "same_sp_normal_form",
            "same_history",
            "same_op_trace",
            "same_observer_signature",
        )
    )
    positive = run("SSP", "plus")
    negative = run("PPS", "minus")
    dual = service.compare("qa", positive, negative)
    assert (
        not dual["same_sp_normal_form"]
        and dual["sp_witness"]["q_left"] == -dual["sp_witness"]["q_right"] == 1
    )
    service.base.new("other", "new")
    from lm_suti_assurance.errors import AssuranceError

    with pytest.raises(AssuranceError, match="NOT_FOUND"):
        service.compare("other", ab, ba)


def test_worker_CPU_and_memory_limits_are_actual_child_limits(monkeypatch):
    from lm_suti_assurance.symbolic import worker

    def exhaust_memory(*args):
        return bytearray(1024 * 1024 * 1024)

    monkeypatch.setattr(worker, "run", exhaust_memory)
    assert (
        worker.bounded({"action": "explore", "request": {}}, None)["error"]["code"]
        == "WORKER_LIMIT"
    )

    def busy(*args):
        while True:
            pass

    monkeypatch.setattr(worker, "run", busy)
    monkeypatch.setitem(worker.LIMITS, "worker_cpu_s", 1)
    monkeypatch.setitem(worker.LIMITS, "worker_wall_s", 3)
    assert (
        worker.bounded({"action": "explore", "request": {}}, None)["error"]["code"]
        == "WORKER_LIMIT"
    )


def test_rule_witness_indices_resolve_the_frozen_training_array():
    model = fit(TRAIN)
    for witness in model["rule_witnesses"]:
        sample = model["train_samples"][witness["train_id"]]
        assert witness["tokens"] == sample["tokens"] and witness[
            "train_sample_digest"
        ] == digest(sample)
        assert "/grammar_hypotheses/0/train_samples/" in witness["input_pointer"]


def test_comparison_passes_actual_FastMCP_strict_JSON_boundary(tmp_path, executor):
    import asyncio
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.symbolic.mcp import register_tools

    server = FastMCP("patch001")
    service = register_tools(server, tmp_path, executor)
    service.base.new("qa", "new")

    async def run():
        a = await service.explore("qa", "a", request("SSPP"))
        b = await service.explore("qa", "b", request("SPSP"))
        response = await server._tool_manager.call_tool(
            "white_star_symbolic_inspect",
            {
                "project": "qa",
                "run_id": a["run_id"],
                "view": "comparison",
                "compare_run_id": b["run_id"],
            },
        )
        assert (
            not response.isError
            and response.structuredContent["data"]["items"][0]["same_sp_normal_form"]
        )

    asyncio.run(run())


def test_current_and_historical_profiles_share_the_original_quota():
    import threading, time
    from concurrent.futures import ThreadPoolExecutor
    from lm_suti_assurance.symbolic.executor import SharedBudget
    from lm_suti_assurance.errors import AssuranceError

    budget = SharedBudget()
    lock = threading.Lock()
    active = [0]
    peak = [0]

    def work():
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.01)
        with lock:
            active[0] -= 1

    with ThreadPoolExecutor(max_workers=6) as threads:
        list(threads.map(lambda _: budget.call(work), range(6)))
    assert peak[0] == 2
    for _ in range(18):
        assert budget.slots.acquire(blocking=False)
    try:
        with pytest.raises(AssuranceError, match="WORKER_LIMIT"):
            budget.call(lambda: None)
    finally:
        for _ in range(18):
            budget.slots.release()
