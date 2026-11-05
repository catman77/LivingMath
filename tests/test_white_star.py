"""Acceptance regressions for the supplied algorithm and durable MCP adapters."""

import asyncio
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import pytest
from lm_suti_assurance import core
from lm_suti_assurance.core import canonical, digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.white_star.contracts import (
    VENDOR,
    TOOLS,
    RESPONSE,
    preflight,
    check_schema,
    integrity,
)
from lm_suti_assurance.white_star.pool import Pool, prepare, Worker
from lm_suti_assurance.white_star.service import WhiteStar
from lm_suti_assurance.white_star import blobs, views
from lm_suti_assurance.white_star.bundle import export


def fixture(name="original_request.json"):
    return json.loads((VENDOR / "fixtures" / name).read_text())


@pytest.fixture(scope="module")
def pool():
    assert prepare()["ready"]
    pool = Pool()
    assert pool.status()["ready"]
    yield pool
    pool.close()


@pytest.fixture
def setup(tmp_path, pool):
    s = WhiteStar(tmp_path / "state", pool)
    s.base.new("qa", "new")
    return s, "qa"


def explore(s, p, key="run", request=None):
    return asyncio.run(s.explore(p, key, request if request is not None else fixture()))


def reading(request, frame="F01"):
    return {
        "frame_id": frame,
        "text": "Явная QA-гипотеза, не математическая истина.",
        "evidence": request["encoding"]["concepts"][0]["evidence"],
        "added_assumptions": ["Explicit QA mapping only"],
        "uncertainties": ["Not source entailment"],
        "alternatives": ["Another reading remains possible"],
        "claim_atoms": [
            {
                "local_id": "q1",
                "text": "Generated QA target model hypothesis",
                "kind": "INTERPRETATION",
            }
        ],
    }


def test_A01_all75_unchanged_and_six_kernel_files():
    actual = integrity()
    assert len(actual) == 75
    for suffix in (
        "divzero_core.py",
        "cad.py",
        "udav.py",
        "source.py",
        "white_star.cpp",
        "fast_source.py",
    ):
        assert any(n.endswith("/" + suffix) for n in actual)


def test_A04_A05_A06_exact_historical_trace_and_aliases(pool):
    req = fixture("blok_request.json")
    out = pool.run({"action": "explore", "request": req})["data"]
    old = VENDOR / "code/experiments/llm_white_star_transfer/results"
    assert out["trace"] == [
        json.loads(line) for line in (old / "trace.jsonl").read_text().splitlines()
    ]
    expected = json.loads((old / "readouts.json").read_text())
    assert [
        {k: v for k, v in r.items() if k not in ("signed_weights", "claim_status")}
        for r in out["readouts"]
    ] == expected
    assert (
        out["summary"]["projections"] == 192
        and out["summary"]["unique_qualitative_modes"] == 52
    )
    assert (
        out["summary"]["unique_numeric_maps"] == 354
        and out["summary"]["labelled_maps"] == 360
    )
    req["atlas_profile"] = "base_v1"
    base = pool.run({"action": "explore", "request": req})["data"]
    old = VENDOR / "code/experiments/llm_white_star/results/trace.jsonl"
    assert base["trace"] == [json.loads(line) for line in old.read_text().splitlines()]


def test_A07_A19_exact_second_input_and_independent_native_state(pool):
    a = pool.run({"action": "explore", "request": fixture()})["data"]
    b = pool.run({"action": "explore", "request": fixture()})["data"]
    assert a == b and a["summary"]["projections"] == 96 and a["summary"]["steps"] == 32
    ids = {"key", "door", "wind", "home"}
    assert all(
        set(v["alias"]["concepts"]) <= ids
        for r in a["readouts"]
        for v in r["alternatives"]
    )


@pytest.mark.parametrize(
    "field,value,code",
    [("sha256", "0" * 64, "SOURCE_MISMATCH"), ("byte_start", 1, "EVIDENCE_MISMATCH")],
)
def test_A08_invalid_source_durably_fails_before_worker(setup, field, value, code):
    s, p = setup
    req = fixture()
    target = (
        req["encoding"]["source"]
        if field == "sha256"
        else req["encoding"]["concepts"][0]["evidence"][0]
    )
    target[field] = value

    class Never:
        def run(self, packet):
            raise AssertionError("Native search must not start")

    s.pool = Never()
    with pytest.raises(AssuranceError, match=code):
        explore(s, p, request=req)
    rows = s.workspace(p).history()
    run = s.workspace(p).get(rows[-1]["result"]["record_ref"])
    assert run["status"] == "FAILED" and run["error"]["code"] == code
    with pytest.raises(AssuranceError):
        s.frozen(p, "invalid-frozen", run["common_snapshot_ref"])


@pytest.mark.parametrize("value", [True, False, 1.0, float("nan")])
def test_A09_integer_is_strict(value):
    req = fixture()
    req["encoding"]["protocol"]["steps"] = value
    with pytest.raises(AssuranceError, match="INVALID_INPUT"):
        preflight(req)


def test_A09_unknown_fields_and_policy():
    req = fixture()
    req["encoding"]["concepts"][0]["execute"] = "evil"
    with pytest.raises(AssuranceError):
        preflight(req)
    req = fixture()
    req["encoding"]["protocol"]["semantic_reranking"] = True
    with pytest.raises(AssuranceError):
        preflight(req)


def test_A10_expanded_atlas_never_truncated(setup):
    s, p = setup
    req = fixture()
    sample = req["encoding"]["concepts"][0]
    req["encoding"]["concepts"] = []
    for i in range(1, 47):
        req["encoding"]["concepts"].append(
            {**sample, "id": "c" + str(i), "coordinates": [i, i * i + 1]}
        )
    with pytest.raises(AssuranceError, match="ATLAS_LIMIT_EXCEEDED"):
        explore(s, p, request=req)


def test_A11_tiny_budget_keeps_empty(setup):
    s, p = setup
    req = fixture()
    req["encoding"]["protocol"].update(steps=1, frame_size=1)
    r = explore(s, p, request=req)
    assert (
        r["status"] == "COMPLETED"
        and r["summary"]["steps"] == 1
        and r["selected_frame_ids"] == []
    )


def test_A12_A13_concurrent_key_idempotence_and_conflict(setup):
    s, p = setup

    class Count:
        calls = 0

        def run(self, packet):
            self.calls += 1
            return s_pool.run(packet)

    s_pool = s.pool
    count = Count()
    s.pool = count
    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda _: explore(s, p, "same"), range(2)))
    assert results[0]["run_id"] == results[1]["run_id"] and count.calls == 1
    assert explore(s, p, "same")["status"] == "COMPLETED" and count.calls == 1
    req = fixture()
    req["encoding"]["protocol"]["seed"] = 43
    with pytest.raises(AssuranceError, match="REQUEST_CONFLICT"):
        explore(s, p, "same", req)
    assert (
        len([r for r in s.workspace(p).history() if r["action"] == "white.start"]) == 1
    )


def test_A14_cross_project_refs_are_inadmissible(setup):
    s, p = setup
    r = explore(s, p)
    s.base.new("other", "new")
    with pytest.raises(AssuranceError, match="NOT_FOUND"):
        s.load("other", r["run_id"])
    with pytest.raises(AssuranceError, match="NOT_FOUND"):
        s.frozen("other", "bad", r["common_snapshot_ref"])
    with pytest.raises(AssuranceError, match="NOT_FOUND"):
        views.inspect(s, p, r["run_id"], "artifact", artifact_ref="0" * 64)


def test_A15_recovery_is_append_only_and_complete_survives(setup):
    s, p = setup
    done = explore(s, p)
    w, unfinished, _ = s.reserve(p, "interrupted", fixture(), "white_star")
    prefix = (w.path / "journal.jsonl").read_bytes()
    recovered = WhiteStar(s.base.root, s.pool)
    assert recovered.recover() == [unfinished["run_id"]]
    assert (w.path / "journal.jsonl").read_bytes().startswith(prefix)
    assert recovered.load(p, done["run_id"])[1]["status"] == "COMPLETED"
    assert recovered.load(p, unfinished["run_id"])[1]["status"] == "INTERRUPTED"
    assert recovered.recover() == []


def test_A16_whole_pages_and_large_artifact_fallback(setup):
    s, p = setup
    r = explore(s, p)
    rows = []
    offset = 0
    while True:
        page = views.inspect(s, p, r["run_id"], "trace", offset, 7)
        rows += page["items"]
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert len(rows) == 32 and rows == s.result(p, r["run_id"])[2]["trace"]
    req = fixture()
    req["encoding"]["uncertainties"] = ["x" * 8000 for _ in range(20)]
    large = explore(s, p, "large", req)
    page = views.inspect(s, p, large["run_id"], "decoder")
    assert page["requires_artifact"] and page["items"] == [] and page["artifact_ref"]
    page = views.inspect(
        s, p, large["run_id"], "artifact", artifact_ref=page["artifact_ref"]
    )
    assert page["items"] and len(canonical(page).encode()) < 120000


def test_A17_A18_MCP_strict_metadata_and_old_schemas(setup):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.mcp import register_tools as old
    from lm_suti_assurance.semantic_bridge.mcp import register_tools as semantic
    from lm_suti_assurance.white_star.mcp import register_tools

    s, p = setup
    server = FastMCP("qa")
    old(server, s.base.root)
    semantic(server, s.base.root)
    before = {t.name: t.parameters for t in server._tool_manager.list_tools()}
    register_tools(server, s.base.root, s.pool)
    after = {t.name: t for t in server._tool_manager.list_tools()}
    assert (
        all(after[n].parameters == v for n, v in before.items())
        and len(after) == len(before) + 8
    )
    assert all(after[n].output_schema == RESPONSE for n in TOOLS)

    async def run():
        reply = await server._tool_manager.call_tool(
            "white_star_explore",
            {"project": p, "request_key": "mcp", "request": fixture(), "unknown": True},
        )
        assert (
            reply.isError
            and reply.structuredContent["error"]["code"] == "INVALID_INPUT"
        )
        reply = await server._tool_manager.call_tool("white_star_status", {})
        assert (
            not reply.isError and reply.structuredContent["data"]["status"] == "READY"
        )

    asyncio.run(run())


def test_project_onboarding_error_and_real_MCP_retry(tmp_path, pool, monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.mcp import register_tools as old
    from lm_suti_assurance.white_star.mcp import register_tools

    server = FastMCP("onboarding")
    old(server, tmp_path)
    service = register_tools(server, tmp_path, pool)
    jobs = []
    native = pool.run

    def counted(request):
        jobs.append(request["action"])
        return native(request)

    monkeypatch.setattr(pool, "run", counted)
    args = {"project": "new-dialog", "request_key": "first", "request": fixture()}

    async def call(name, arguments):
        return await server._tool_manager.call_tool(name, arguments)

    async def run():
        failed = await call("white_star_explore", args)
        error = failed.structuredContent["error"]
        assert failed.isError and error["code"] == "PROJECT_NOT_FOUND"
        assert error["field_path"] == "/project" and error["run_id"] is None
        assert "assurance_project_new" in error["message"]
        assert '"project":"new-dialog"' in error["message"]
        assert not service.workspace("new-dialog").history() and not jobs

        status = (await call("white_star_status", {})).structuredContent["data"]
        registration = copy.deepcopy(status["workflow"]["project_registration"])
        assert registration["tool"] == "assurance_project_new"
        registration["arguments"]["project"] = args["project"]
        await call(registration["tool"], registration["arguments"])
        registered = service.workspace("new-dialog").history()
        assert len(registered) == 1 and registered[0]["action"] == "project.new"

        reply = await call("white_star_explore", args)
        data = reply.structuredContent["data"]
        assert not reply.isError and data["status"] == "COMPLETED"
        assert data["run_id"] and jobs == ["explore"]
        count = len(service.workspace("new-dialog").history())
        repeated = await call("white_star_explore", args)
        assert repeated.structuredContent["data"]["run_id"] == data["run_id"]
        assert len(service.workspace("new-dialog").history()) == count
        assert jobs == ["explore"]
        for view in ("frames", "decoder"):
            page = await call(
                "white_star_inspect",
                {"project": args["project"], "run_id": data["run_id"], "view": view},
            )
            assert not page.isError and page.structuredContent["data"]["items"]

        missing = await call(
            "white_star_inspect", {"project": args["project"], "run_id": "0" * 64}
        )
        assert (
            missing.isError
            and missing.structuredContent["error"]["code"] == "NOT_FOUND"
        )

    asyncio.run(run())


def test_A20_A21_real_bridge_common_snapshot_and_mismatch(setup):
    s, p = setup
    w = explore(s, p)
    b = s.frozen(p, "bridge", w["common_snapshot_ref"])
    comparison = views.compare(
        s,
        p,
        {"engine": "white_star", "run_id": w["run_id"]},
        {"engine": "suti", "run_id": b["run_id"]},
        {"mode": "MATCHED_INPUT", "decoder_protocol_id": "same"},
    )
    assert comparison["status"] == "MATCHED_INPUT"
    result = s.result(p, b["run_id"])[2]
    assert (
        result["backend"].startswith("SemanticBridge001")
        and result["SUTI_native_runtime"] == "NOT_EXECUTED"
    )
    assert len(result["decisions"]) == 4 and result["summary"]["missing_slots"] == 2
    assert all(
        s.workspace(p).get(v["check_ref"])["status"] == "SOURCE_ATTESTED"
        for v in result["decisions"]
    )
    req = fixture()
    req["encoding"]["concepts"][0]["label"] = "Other extraction"
    other = explore(s, p, "unmatched", req)
    comparison = views.compare(
        s,
        p,
        {"engine": "white_star", "run_id": other["run_id"]},
        {"engine": "suti", "run_id": b["run_id"]},
        {"mode": "MATCHED_INPUT", "decoder_protocol_id": "same"},
    )
    assert comparison["status"] == "UNMATCHED_INPUT" and comparison["same_source_bytes"]


def add_reading(s, p, r):
    return s.readings(p, r["run_id"], "reading", [reading(fixture())])


def test_A22_readings_and_claims_immutable_idempotent(setup):
    s, p = setup
    r = explore(s, p)
    a = add_reading(s, p, r)
    assert a == add_reading(s, p, r)
    claim = s.workspace(p).get(a["claim_refs"][0])
    assert (
        claim["status"] == "INTERPRETATION" and claim["execution_permission"] is False
    )
    bad = reading(fixture())
    bad["evidence"][0]["quote"] = "Invented"
    with pytest.raises(AssuranceError, match="EVIDENCE_MISMATCH"):
        s.readings(p, r["run_id"], "bad", [bad])


def model(family, claim):
    matrices = {
        "observation_invariant": {
            "A": [[1, 0], [0, 2]],
            "C": [[1, 0]],
            "x": [[1], [1]],
        },
        "control_invariant": {
            "A": [[1, 0], [0, 1]],
            "B": [[1], [0]],
            "C": [[1, 0]],
            "w": [[0, 1]],
            "x": [[3], [1]],
            "u": [[-3]],
        },
        "cyclic_order": {
            "U": [[1, 1], [0, 1]],
            "L": [[1, 0], [1, 1]],
            "P": [[2, 0], [0, 1]],
            "x": [[1], [0]],
        },
    }
    return {
        "schema": "levinmas-white-star-model/1",
        "family": family,
        "matrices": matrices.get(family, {}),
        "claim_ref": claim,
        "frame_refs": ["F01"],
        "mapping_assumptions": [
            "Explicit linear-system interpretation, not source-entailment or physics"
        ],
        "obligations": {
            "observation_invariant": ["invariant_identity", "hidden_state_change"],
            "control_invariant": ["invariant_identity", "partial_improvement"],
            "cyclic_order": ["conjugacy", "different_action"],
        }.get(family, ["invariant_identity"]),
    }


@pytest.mark.parametrize(
    "family", ["observation_invariant", "control_invariant", "cyclic_order"]
)
def test_A23_formal_families_positive_negative_idempotent(setup, family):
    s, p = setup
    r = explore(s, p)
    claim = add_reading(s, p, r)["claim_refs"][0]
    proposal = model(family, claim)
    check_schema(
        proposal,
        TOOLS["white_star_validate_model"]["inputSchema"]["properties"]["proposal"],
    )
    a = asyncio.run(s.model(p, r["run_id"], proposal))
    assert a["status"] == "CHECKED_INSTANCE" and a == asyncio.run(
        s.model(p, r["run_id"], proposal)
    )
    bad = copy.deepcopy(proposal)
    if family == "observation_invariant":
        bad["matrices"]["A"][0][0] = 2
    elif family == "control_invariant":
        bad["matrices"]["B"][1][0] = 1
    else:
        bad["matrices"]["x"] = [[0], [0]]
    b = asyncio.run(s.model(p, r["run_id"], bad))
    assert b["status"] == "REJECTED" and any(not x["pass"] for x in b["obligations"])
    assert b["execution_permission"] is False


@pytest.mark.parametrize("value", [True, 1.0, "1/0", "1/2.0", str(1 << 257)])
def test_A23_bad_rationals_never_accepted(setup, value):
    s, p = setup
    r = explore(s, p)
    claim = add_reading(s, p, r)["claim_refs"][0]
    proposal = model("observation_invariant", claim)
    proposal["matrices"]["A"][0][0] = value
    with pytest.raises(AssuranceError):
        asyncio.run(s.model(p, r["run_id"], proposal))


def test_A24_unknown_physics_and_dimensions(setup):
    s, p = setup
    r = explore(s, p)
    claim = add_reading(s, p, r)["claim_refs"][0]
    assert (
        asyncio.run(s.model(p, r["run_id"], model("chemistry", claim)))["status"]
        == "UNSUPPORTED_MODEL"
    )
    v = model("cyclic_order", claim)
    for k in ("U", "L", "P"):
        v["matrices"][k] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert asyncio.run(s.model(p, r["run_id"], v))["status"] == "UNSUPPORTED_MODEL"


def test_A25_A26_full_replay_and_one_byte_tamper(setup):
    s, p = setup
    r = explore(s, p)
    s.frozen(p, "bridge", r["common_snapshot_ref"])
    claim = add_reading(s, p, r)["claim_refs"][0]
    asyncio.run(s.model(p, r["run_id"], model("observation_invariant", claim)))
    raw, manifest = export(s.workspace(p))
    value = s.pool.run(
        {"action": "replay", "bundle_base64": base64.b64encode(raw).decode()}
    )["data"]
    assert (
        value["status"] == "PASS"
        and value["logical_digest"] == manifest["logical_digest"]
        and value["runs_recomputed"] == 2
    )
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {i.filename: z.read(i) for i in z.infolist()}
    name = next(n for n in files if n.startswith("objects/"))
    files[name] += b" "
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, v in files.items():
            z.writestr(n, v)
    with pytest.raises(AssuranceError, match="MANIFEST_SHA_MISMATCH"):
        s.pool.run(
            {
                "action": "replay",
                "bundle_base64": base64.b64encode(out.getvalue()).decode(),
            }
        )


def test_A27_actual_native_missing_isolated_and_restored(pool):
    native = next((VENDOR / "code/experiments/white_star/native/build").glob("*.so"))
    held = native.with_suffix(".test-held")
    native.rename(held)
    try:
        with pytest.raises(AssuranceError, match="ENGINE_UNAVAILABLE"):
            Worker()
    finally:
        held.rename(native)
    assert (
        pool.run({"action": "explore", "request": fixture()})["data"]["summary"][
            "steps"
        ]
        == 32
    )


def test_A27_actual_timeout_does_not_take_down_supervisor(monkeypatch):
    from lm_suti_assurance.white_star import worker
    import time

    class Slow:
        search = None

        def explore(self, request):
            time.sleep(1)
            return {}

    monkeypatch.setitem(worker.LIMITS, "worker_wall_s", 0.05)
    value = worker.bounded({"action": "explore", "request": fixture()}, Slow(), None)
    assert value["error"]["code"] == "WORKER_LIMIT"


def test_A28_actual_split_timings_and_no_module_collisions(pool):
    assert "fast_source" not in sys.modules and "rotated_atlas" not in sys.modules
    a = pool.run({"action": "explore", "request": fixture()})
    assert (
        a["metrics"]["numeric_kernel_search_s"] >= 0
        and a["metrics"]["result_serialization_s"] >= 0
    )
    assert a["metrics"]["job_cpu_s"] < 5 and a["metrics"]["max_rss_kib"] < 512 * 1024
    assert all(w["isolation"]["credentials_denied"] for w in pool.status()["workers"])


def test_shared_export_facade_and_missing_source_policy(setup):
    from lm_suti_assurance.bundle import export_bundle
    from lm_suti_assurance.white_star.bundle import export_rows

    s, p = setup
    explore(s, p)
    raw, manifest = export_bundle(s.workspace(p), "private")
    assert manifest["schema"] == "levinmas-white-star-package/1"
    with s.workspace(p).locked():
        raw, manifest = export_rows(
            s.workspace(p), s.workspace(p).history(), "private", False
        )
    assert manifest["source_dependencies"]
    with pytest.raises(AssuranceError, match="MISSING_SOURCE_DEPENDENCY"):
        s.pool.run(
            {"action": "replay", "bundle_base64": base64.b64encode(raw).decode()}
        )
    with pytest.raises(AssuranceError, match="PUBLICATION_POLICY_VIOLATION"):
        export_bundle(s.workspace(p), "public")


def test_worker_capacity_is_explicit_and_old_service_stays_alive(pool):
    held = []
    try:
        for _ in range(18):
            assert pool.slots.acquire(False)
            held.append(True)
        with pytest.raises(AssuranceError, match="WORKER_LIMIT"):
            pool.run({"action": "explore", "request": fixture()})
    finally:
        for _ in held:
            pool.slots.release()
    assert pool.status()["ready"]


def test_session_cancellation_cannot_abandon_accepted_run(setup):
    import threading, time

    s, p = setup
    original = s.pool
    started = threading.Event()

    class Slower:
        def run(self, packet):
            started.set()
            time.sleep(0.06)
            return original.run(packet)

    s.pool = Slower()

    async def exercise():
        task = asyncio.create_task(s.explore(p, "disconnect", fixture()))
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.gather(*s.active)
        return await s.explore(p, "disconnect", fixture())

    assert asyncio.run(exercise())["status"] == "COMPLETED"


def test_startup_recovery_accepts_real_JSON_config_path_string(tmp_path):
    service = WhiteStar(str(tmp_path / "state"))
    service.base.new("qa", "new")
    assert service.recover() == []


def test_deep_input_is_a_typed_domain_error():
    req = fixture()
    deep = {}
    node = deep
    for _ in range(52):
        node["nested"] = {}
        node = node["nested"]
    req["encoding"]["provenance"] = deep
    with pytest.raises(AssuranceError, match="INVALID_INPUT"):
        preflight(req)


def test_countermodel_is_checked_separately_from_main_example(setup):
    s, p = setup
    r = explore(s, p)
    claim = add_reading(s, p, r)["claim_refs"][0]
    proposal = model("observation_invariant", claim)
    proposal["obligations"] = ["invariant_identity", "countermodel"]
    proposal["matrices"]["A"] = [[1, 0], [0, 1]]
    proposal["countermodel"] = {"A": [[1, 0], [0, 2]]}
    assert (
        asyncio.run(s.model(p, r["run_id"], proposal))["status"] == "CHECKED_INSTANCE"
    )
    proposal["countermodel"] = {"A": [[1, 0], [0, 1]]}
    assert asyncio.run(s.model(p, r["run_id"], proposal))["status"] == "REJECTED"


def test_two_projects_compute_concurrently_with_independent_native_states(setup):
    s, p = setup
    s.base.new("second", "new")
    with ThreadPoolExecutor(2) as ex:
        one = ex.submit(explore, s, p, "parallel")
        two = ex.submit(explore, s, "second", "parallel")
        a, b = one.result(), two.result()
    assert a["run_id"] != b["run_id"] and a["result_digest"] == b["result_digest"]
    assert s.result(p, a["run_id"])[2]["trace"][0]["witness"] == [0, 0]
    with pytest.raises(AssuranceError, match="NOT_FOUND"):
        s.load(p, b["run_id"])


@pytest.mark.parametrize("family", ["control_invariant", "cyclic_order"])
def test_separate_generic_countermodels_checked_with_witnesses(setup, family):
    s, p = setup
    r = explore(s, p)
    claim = add_reading(s, p, r)["claim_refs"][0]
    proposal = model(family, claim)
    proposal["obligations"].append("countermodel")
    proposal["countermodel"] = (
        {"B": [[1, 0], [0, 1]], "u": [[-3], [-1]]}
        if family == "control_invariant"
        else {"x": [[1], [0]]}
    )
    assert (
        asyncio.run(s.model(p, r["run_id"], proposal))["status"] == "CHECKED_INSTANCE"
    )
    proposal["countermodel"] = (
        {"B": [[1], [0]], "u": [[-3]]}
        if family == "control_invariant"
        else {"x": [[0], [0]]}
    )
    assert asyncio.run(s.model(p, r["run_id"], proposal))["status"] == "REJECTED"
