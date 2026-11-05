"""Exact/metamorphic and real isolated-worker/MCP regression acceptance."""

import asyncio, base64, copy, hashlib, io, json, random, zipfile
from pathlib import Path
import pytest
from lm_suti_assurance.core import digest
from lm_suti_assurance.errors import AssuranceError
from lm_suti_assurance.symbolic.state import (
    Atom,
    SymbolicState,
    History,
    alpha,
    alpha_corpus,
    reduce_sp,
    apply,
    source_states,
)
from lm_suti_assurance.symbolic.observers import CADObserver, compare
from lm_suti_assurance.symbolic.executor import Executor
from lm_suti_assurance.symbolic.service import SymbolicService
from lm_suti_assurance.symbolic.bundle import export
from lm_suti_assurance.white_star.pool import prepare
from lm_suti_assurance.white_star.contracts import integrity

ROOT = Path(__file__).resolve().parents[1]


def request(text="SSPP\nSPSP\nPPSS\nPSPS", **search):
    r = json.loads(
        (
            ROOT / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
        ).read_text()
    )["request"]
    r["source"].update(text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    r["search"].update({"max_steps": 8, **search})
    return r


def word(text):
    return SymbolicState(tuple(Atom(c, ()) for c in text))


@pytest.fixture(scope="module")
def executor():
    assert prepare()["ready"]
    p = Executor()
    assert p.status()["ready"]
    yield p
    p.close()


@pytest.mark.parametrize("seed", range(30))
def test_SP_metamorphic_quotients_and_history(seed):
    rng = random.Random(seed)
    for _ in range(40):
        w = word("".join(rng.choice("SP") for _ in range(rng.randrange(41))))
        k = rng.randrange(len(w.atoms) + 1)
        pieces, _ = apply(w, "SPLIT", {"position": k})
        joined, _ = apply(pieces[0], "CONCAT", {}, pieces[1])
        assert joined[0] == w
        q = w.tokens.count("S") - w.tokens.count("P")
        normal, log = reduce_sp(w.tokens)
        assert normal == tuple(("S" if q >= 0 else "P") * abs(q))
        assert reduce_sp(normal)[0] == normal
        inv, _ = apply(w, "SP_INV", {})
        back, _ = apply(inv[0], "SP_INV", {})
        assert back[0] == w
        assert inv[0].tokens.count("S") - inv[0].tokens.count("P") == -q
        for kind in ("SP", "PS"):
            inserted, _ = apply(w, "INSERT_CANCEL_PAIR", {"position": k, "kind": kind})
            assert reduce_sp(inserted[0].tokens)[0] == normal
            assert inserted[0].tokens != w.tokens
        rename, _ = apply(
            w,
            "RENAME",
            {
                "mapping": (
                    {"S": "x", "P": "y"}
                    if set(w.tokens) == {"S", "P"}
                    else {t: "x" for t in set(w.tokens)}
                ),
                "scope": "global",
            },
        )
        assert alpha(rename[0].tokens) == alpha(w.tokens)
        reverse, _ = apply(w, "REVERSE", {})
        assert apply(reverse[0], "REVERSE", {})[0][0] == w
        # Independent rightmost reduction is not the implementation's oracle.
        current = list(w.tokens)
        while True:
            ks = [i for i in range(len(current) - 1) if current[i] != current[i + 1]]
            if not ks:
                break
            i = ks[-1]
            del current[i : i + 2]
        assert tuple(current) == normal


def test_four_distinct_relations_and_reduction_certificates():
    obs = CADObserver(["sp_reduce"])
    left, right = word("SSPP"), word("SPSP")
    claims = compare(left, right, obs)
    assert not next(c for c in claims if c["relation"] == "literal_word_equality")[
        "equal"
    ]
    assert not next(c for c in claims if c["relation"] == "alpha_equality")["equal"]
    assert next(c for c in claims if c["relation"] == "same_sp_normal_form")["equal"]
    assert alpha("ABBA") == alpha("BAAB")
    assert alpha_corpus(["AB", "AB"], "local") == alpha_corpus(["AB", "CD"], "local")
    assert alpha_corpus(["AB", "AB"]) != alpha_corpus(["AB", "CD"])
    assert reduce_sp("SSPP")[1][0]["positions"] == [1, 2]
    assert reduce_sp("SPSP")[1][0]["positions"] == [0, 1]
    a, b = word("SSPPSPSP"), word("SPSPSSPP")
    assert (
        a.word_hash != b.word_hash and reduce_sp(a.tokens)[0] == reduce_sp(b.tokens)[0]
    )
    assert (
        CADObserver(["sp_reduce"]).observe(a)["observers"]["sp_reduce"][
            "prefix_balance"
        ]
        != CADObserver(["sp_reduce"]).observe(b)["observers"]["sp_reduce"][
            "prefix_balance"
        ]
    )
    # q-only observer is explicitly a quotient; complete sp_reduce logs distinguish histories.
    assert reduce_sp(a.tokens)[0] == reduce_sp(b.tokens)[0]


def test_source_spans_boundaries_NFC_and_explicit_local_scope():
    r = request("A\u0301B\nA\u0301C")
    r["algebra"]["kind"] = "FREE"
    r["algebra"]["allow_reduce"] = False
    r["operators"] = ["REVERSE"]
    r["observers"] = ["literal"]
    r["normalization"] = "NFC"
    h = History()
    root, records, m = source_states(r, h)
    state = h.states[root]
    assert state.tokens == tuple("ÁBÁC") and m[
        "normalized_codepoint_to_original_bytes"
    ][0] == [0, 3]
    assert h.verify() and all(a.spans for a in state.atoms)
    renamed, _ = apply(
        state, "RENAME", {"mapping": {"Á": "X"}, "scope": "local", "record": 0}
    )
    assert renamed[0].tokens == tuple("XBÁC")
    for k in range(len(state.atoms) + 1):
        parts, _ = apply(state, "SPLIT", {"position": k})
        assert apply(parts[0], "CONCAT", {}, parts[1])[0][0] == state
    before = copy.deepcopy(state)
    CADObserver(
        [
            "literal",
            "alpha_pattern",
            "adjacency",
            "substring_contexts",
            "composition",
            "hierarchy",
        ]
    ).observe(state)
    assert state == before
    with pytest.raises(AssuranceError, match="RENAME_NOT_BIJECTIVE"):
        apply(word("AB"), "RENAME", {"mapping": {"A": "B"}})
    substituted, _ = apply(word("AB"), "SUBSTITUTE", {"mapping": {"A": "B"}})
    assert substituted[0].tokens == tuple("BB")
    with pytest.raises(AssuranceError, match="HISTORY_BROKEN"):
        h.add(state, ["f" * 64], "REVERSE", {})
    h.nodes[root]["parent_ids"] = [root]
    with pytest.raises(AssuranceError, match="HISTORY_BROKEN"):
        h.verify()


@pytest.mark.parametrize("unit", ["codepoint", "whitespace", "line", "literal_token"])
def test_segmentation_exact_source(unit):
    r = request("α!\nβ?")
    r["algebra"].update(kind="FREE", allow_reduce=False)
    r["operators"] = ["REVERSE"]
    r["observers"] = ["literal", "hierarchy"]
    r["segmentation"]["unit"] = unit
    if unit == "literal_token":
        r["segmentation"]["tokens"] = [
            {"token": "α", "byte_start": 0, "byte_end": 2},
            {"token": "β", "byte_start": 4, "byte_end": 6},
        ]
    h = History()
    root, records, source = source_states(r, h)
    assert len(records) == 2
    for atom in h.states[root].atoms:
        for sha, a, b in atom.spans:
            assert r["source"]["text"].encode()[a:b].decode()
    assert source["layout_status"] == "UNAVAILABLE"


def test_real_isolated_determinism_budget_and_old_bytes(executor):
    old = integrity()
    r = request()
    a = executor.run({"action": "explore", "request": r})
    b = executor.run({"action": "explore", "request": r})
    assert a["data"] == b["data"]
    assert (
        a["data"]["summary"]["steps"] == 8
        and a["data"]["checks"]["DAG_acyclic_and_hashed"]
    )
    assert old == integrity() and len(old) == 75
    small = request(max_observations=7, max_nodes=16)
    limited = executor.run({"action": "explore", "request": small})["data"]
    assert limited["summary"]["halt_reason"] in ("MAX_OBSERVATIONS", "MAX_NODES")
    for w in executor.status()["workers"]:
        assert (
            w["isolation"]["credentials_denied"]
            and w["isolation"]["filesystem_writes_denied"]
        )


@pytest.mark.parametrize(
    "defect,code",
    [
        ("hash", "SOURCE_MISMATCH"),
        ("alphabet", "INVALID_INPUT"),
        ("operator", "INVALID_INPUT"),
        ("budget", "INVALID_INPUT"),
        ("sp", "SP_ALGEBRA_REQUIRED"),
        ("span", "INVALID_SPAN"),
        ("history", "INVALID_INPUT"),
    ],
)
def test_negative_requests_have_typed_errors(executor, defect, code):
    r = request()
    if defect == "hash":
        r["source"]["sha256"] = "0" * 64
    elif defect == "alphabet":
        r["source"]["alphabet"] = []
    elif defect == "operator":
        r["operators"] = ["UNRESTRICTED_EXECUTE"]
    elif defect == "budget":
        r["search"]["max_steps"] = 4097
    elif defect == "sp":
        r["algebra"]["kind"] = "FREE"
    elif defect == "span":
        r["source"]["segments"] = [
            {"id": "bad", "kind": "line", "byte_start": 0, "byte_end": 47000}
        ]
    else:
        r["history"] = [{"parent_ids": ["absent"]}]
    with pytest.raises(AssuranceError, match=code):
        executor.run({"action": "explore", "request": r})


def test_full_MCP_idempotency_conflict_pagination_replay_project_isolation(
    tmp_path, executor
):
    from mcp.server.fastmcp import FastMCP
    from lm_suti_assurance.mcp import register_tools as old
    from lm_suti_assurance.semantic_bridge.mcp import register_tools as bridge
    from lm_suti_assurance.white_star.mcp import register_tools as white
    from lm_suti_assurance.symbolic.mcp import register_tools

    server = FastMCP("symbolic-qa")
    old(server, tmp_path)
    bridge(server, tmp_path)
    white(server, tmp_path)
    previous = {
        t.name: (t.parameters, t.output_schema)
        for t in server._tool_manager.list_tools()
    }
    service = register_tools(server, tmp_path, executor)
    now = {t.name: t for t in server._tool_manager.list_tools()}
    assert all(
        (now[n].parameters, now[n].output_schema) == s for n, s in previous.items()
    )

    async def call(name, args, error=False):
        reply = await server._tool_manager.call_tool(name, args)
        assert reply.isError == error
        return reply.structuredContent

    async def execute():
        args = {"project": "symbolic-qa", "request_key": "one", "request": request()}
        missing = await call("white_star_symbolic_explore", args, True)
        assert missing["error"]["code"] == "PROJECT_NOT_FOUND"
        service.base.new("symbolic-qa", "new")
        a = await call("white_star_symbolic_explore", args)
        assert a["data"]["status"] == "COMPLETED"
        ident = a["data"]["run_id"]
        count = len(service.workspace("symbolic-qa").history())
        b = await call("white_star_symbolic_explore", args)
        assert b == a and len(service.workspace("symbolic-qa").history()) == count
        changed = copy.deepcopy(args)
        changed["request"]["search"]["seed"] += 1
        assert (await call("white_star_symbolic_explore", changed, True))["error"][
            "code"
        ] == "REQUEST_CONFLICT"
        for view in (
            "input",
            "operations",
            "observations",
            "claims",
            "grammar",
            "evaluation",
            "history",
            "states",
            "source",
            "manifest",
            "checks",
            "report",
        ):
            offset = 0
            items = []
            while True:
                page = (
                    await call(
                        "white_star_symbolic_inspect",
                        {
                            "project": args["project"],
                            "run_id": ident,
                            "view": view,
                            "offset": offset,
                            "limit": 1,
                        },
                    )
                )["data"]
                assert not page["requires_artifact"]
                items += page["items"]
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            assert items
        export_page = (
            await call(
                "white_star_symbolic_inspect",
                {"project": args["project"], "run_id": ident, "view": "export"},
            )
        )["data"]
        ref = export_page["items"][0]["bundle_ref"]
        replay = await call(
            "white_star_symbolic_replay",
            {"project": args["project"], "bundle_ref": ref},
        )
        assert replay["data"]["status"] == "REPLAY_MATCH"
        service.base.new("other", "new")
        assert (
            await call(
                "white_star_symbolic_replay",
                {"project": "other", "bundle_ref": ref},
                True,
            )
        )["error"]["code"] == "NOT_FOUND"
        raw, manifest = export(service.workspace(args["project"]), ident)
        # Tamper the DAG bytes while preserving the outer ZIP CRC: manifest must reject it.
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            files = {n: z.read(n) for n in z.namelist()}
        name = next(n for n in files if n.startswith("objects/"))
        files[name] += b" "
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for n, v in files.items():
                z.writestr(n, v)
        with pytest.raises(AssuranceError, match="EXPORT_INTEGRITY_FAILURE"):
            executor.run(
                {
                    "action": "replay",
                    "bundle_base64": base64.b64encode(out.getvalue()).decode(),
                }
            )

    asyncio.run(execute())


def test_local_rename_is_a_bijection_only_in_declared_record():
    r = request("AB\nCD")
    r["algebra"].update(kind="FREE", allow_reduce=False)
    h = History()
    root, _, _ = source_states(r, h)
    s = h.states[root]
    renamed, _ = apply(
        s, "RENAME", {"mapping": {"A": "C"}, "scope": "local", "record": 0}
    )
    assert renamed[0].tokens == tuple("CBCD")
    assert alpha_corpus([s.tokens[:2], s.tokens[2:]], "local") == alpha_corpus(
        [renamed[0].tokens[:2], renamed[0].tokens[2:]], "local"
    )
    assert alpha(s.tokens) != alpha(renamed[0].tokens)
    with pytest.raises(AssuranceError, match="RENAME_NOT_BIJECTIVE"):
        apply(s, "RENAME", {"mapping": {"A": "C"}, "scope": "global"})


def test_alpha_equality_keeps_structural_boundaries():
    a = SymbolicState(word("AB").atoms, ((1, "record_end", "0"),))
    b = word("AB")
    claim = next(
        c
        for c in compare(a, b, CADObserver(["alpha_pattern"]))
        if c["relation"] == "alpha_equality"
    )
    assert not claim["equal"]


def test_real_job_cancellation_and_restart_are_append_only(tmp_path, executor):
    service = SymbolicService(str(tmp_path), executor)
    service.base.new("qa", "new")

    async def run():
        task = asyncio.create_task(
            service.explore("qa", "cancel", request(max_steps=64))
        )
        while not service.active:
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.gather(*list(service.active))
        rows = service.workspace("qa").history()
        ident = next(
            r["result"]["run_id"] for r in rows if r["action"] == "symbolic.start"
        )
        assert service.compact("qa", ident)["status"] == "COMPLETED"

    asyncio.run(run())
    w, start, _ = service.reserve("qa", "interrupted", request())
    before = service.workspace("qa").history()
    assert service.recover() == [start["run_id"]]
    after = service.workspace("qa").history()
    assert after[: len(before)] == before
    with pytest.raises(AssuranceError, match="INTERRUPTED"):
        service.compact("qa", start["run_id"])
    assert service.recover() == []
    from lm_suti_assurance.bundle import export_bundle

    with pytest.raises(AssuranceError, match="SYMBOLIC_EXPORT_REQUIRES_RUN_ID"):
        export_bundle(service.workspace("qa"))


def test_wall_budget_kills_only_the_job(monkeypatch):
    import time
    from lm_suti_assurance.symbolic import worker

    monkeypatch.setitem(worker.LIMITS, "worker_wall_s", 0.02)

    def delayed(*args):
        time.sleep(0.2)
        return {}

    monkeypatch.setattr(worker, "run", delayed)
    assert (
        worker.bounded({"action": "explore", "request": {}}, None)["error"]["code"]
        == "WORKER_LIMIT"
    )


def test_whole_record_fallback_is_recoverable_without_truncation(tmp_path, executor):
    service = SymbolicService(tmp_path, executor)
    service.base.new("large", "new")
    req = request("S" * 2000, max_steps=0, max_word_tokens=2048, max_nodes=4)
    run = asyncio.run(service.explore("large", "one", req))
    page = service.inspect("large", run["run_id"], "states", limit=1)
    assert page["requires_artifact"] and not page["items"] and page["artifact_ref"]
    items = []
    offset = 0
    while True:
        chunks = service.inspect(
            "large",
            run["run_id"],
            "artifact",
            artifact_ref=page["artifact_ref"],
            offset=offset,
            limit=128,
        )
        items.extend(chunks["items"])
        if chunks["next_offset"] is None:
            break
        offset = chunks["next_offset"]
    raw = b"".join(base64.b64decode(v["data_base64"]) for v in items)
    result = json.loads(raw)
    assert len(result["states"][0]["tokens"]) == 2000 and result["input"] == req


def test_NFC_literal_tokens_retain_original_cluster_span():
    req = request("A\u0301")
    req["normalization"] = "NFC"
    req["algebra"].update(kind="FREE", allow_reduce=False)
    req["segmentation"].update(
        unit="literal_token",
        tokens=[{"token": "A\u0301", "byte_start": 0, "byte_end": 3}],
    )
    h = History()
    root, _, _ = source_states(req, h)
    assert h.states[root].tokens == ("Á",) and h.states[root].atoms[0].spans[0][1:] == (
        0,
        3,
    )
    req["segmentation"]["tokens"] = [{"token": "A", "byte_start": 0, "byte_end": 1}]
    with pytest.raises(AssuranceError, match="NFC_TOKEN_SPLITS_CLUSTER"):
        source_states(req, History())


def test_history_identity_parameter_preserves_or_quotients_operation_paths(executor):
    req = request("S", max_steps=4)
    req["operators"] = ["SUBSTITUTE"]
    req["search"]["history_identity"] = "word"
    by_word = executor.run({"action": "explore", "request": req})["data"]
    req["search"]["history_identity"] = "provenance"
    by_history = executor.run({"action": "explore", "request": req})["data"]
    assert by_history["summary"]["nodes"] > by_word["summary"]["nodes"]
    assert {tuple(s["tokens"]) for s in by_history["states"]} == {
        tuple(s["tokens"]) for s in by_word["states"]
    }
