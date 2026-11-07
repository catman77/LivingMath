"""Explicit epsilon/nonnullable, Unicode covariance and two further proposed readings."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest
from role006_fixture import record

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream


async def run(a):
    o = a.output
    o.mkdir(mode=0o700, parents=True, exist_ok=False)
    calls = []
    checks = []
    runs = []
    save = lambda n, v: (o / n).write_text(
        json.dumps(v, ensure_ascii=False, indent=2) + "\n"
    )
    data = json.loads((a.fixture / "inputs.json").read_text())
    project = "qa-formal001-aux-" + a.tag
    auth = authenticate(a.origin, a.password, o / "oauth.private.json", a.loopback_port)
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        from mcp_retry_transport import install

        install(http, o / "HTTP_RETRIES.jsonl")
        async with streamable_http_client(a.endpoint, http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                TappedStream(read, o / "wire.jsonl", "server_to_client"),
                TappedStream(write, o / "wire.jsonl", "client_to_server"),
            ) as client:
                await client.initialize()

                def check(n, ok):
                    checks.append({"name": n, "status": "PASS" if ok else "FAIL"})
                    save("checks.json", checks)
                    if not ok:
                        raise AssertionError(n)

                async def call(n, args):
                    r = await client.call_tool(n, args)
                    v = r.structuredContent or json.loads(r.content[0].text)
                    calls.append(
                        {
                            "tool": n,
                            "arguments": args,
                            "response": r.model_dump(mode="json"),
                        }
                    )
                    save("transcript.json", calls)
                    check(n + " " + str(len(calls)), not r.isError)
                    return v.get("data", v)

                async def result(r):
                    chunks = []
                    offset = 0
                    while True:
                        v = await call(
                            "formal_inspect",
                            {
                                "project": project,
                                "run_ref": r["run_ref"],
                                "view": "result",
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if v.get("encoding") != "base64":
                            return v
                        chunks.append(base64.b64decode(v["data"]))
                        offset = v["next_offset"]
                        if offset is None:
                            raw = b"".join(chunks)
                            check(
                                "complete chunk SHA",
                                hashlib.sha256(raw).hexdigest() == v["sha256"],
                            )
                            return json.loads(raw)

                async def op(n, k, **kw):
                    r = await call(
                        "formal_" + n, {"project": project, "request_key": k, **kw}
                    )
                    check("complete " + k, r["status"] == "COMPLETED")
                    runs.append(r)
                    v = await result(r)
                    save(k + ".json", v)
                    return r, v

                async def dataset(k, rows, kind):
                    d = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": rows,
                    }
                    d["sha256"] = digest(d)
                    return (
                        await call(
                            "white_star_symbolic_dataset_store",
                            {"project": project, "request_key": k, "dataset": d},
                        )
                    )["dataset_ref"]

                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                train = (
                    data["cases"]["cfg_anbn"]["train"]
                    + data["cases"]["cfg_anbn"]["annotation"]
                )
                query = [record(list(w)) for w in ["", "ab", "aabb", "abab"]]
                tr = await dataset("start-train", train, "train")
                qr = await dataset("start-queries", query, "queries")
                r, v = await op(
                    "synthesize",
                    "nonnullable-start",
                    train_ref=tr,
                    predict_ref=qr,
                    constraints={"kind": "cfg"},
                )
                check(
                    "epsilon false positive fixed by separate annotation",
                    [p["decision"] for p in v["predictions"]]
                    == [False, True, True, False],
                )
                candidates = [
                    c
                    for c in v["model"]["candidates"]
                    if len(c["ast"]["nonterminals"]) == 2
                ]
                check("independent start induced", bool(candidates))
                sr, _ = await op(
                    "store", "epsilon-source", kind="record", data=query[0]
                )
                _, proof = await op(
                    "verify",
                    "nonnullable-two-NT-proof",
                    run_ref=r["run_ref"],
                    candidate_ref=candidates[0]["candidate_id"],
                    source_ref=sr["stored_object_ref"],
                )
                check(
                    "inner epsilon never forces start epsilon",
                    proof["status"] == "CHECKED_INSTANCE"
                    and proof["verification"]["decision"] is False
                    and proof["proof"]["status"] == "REJECT_COMPLETE",
                )
                # Simultaneous renaming of train/query terminals, no true query label sent.
                rename = {"S": "Ω", "P": "λ", "A": "ж", "B": "β"}
                c = data["cases"]["cfg_dyck2_new_stratified"]

                def image(r):
                    t = [rename[x] for x in r["tokens"]]
                    x = record(t, r.get("accepted"), prefix="unicode")
                    x["id"] = r["id"]
                    return x

                train = [image(r) for r in c["train"]]
                query = [image(r) for r in c["enriched_queries"]]
                tr = await dataset("unicode-train", train, "train")
                qr = await dataset("unicode-queries", query, "queries")
                _, uv = await op(
                    "synthesize",
                    "unicode-pairs",
                    train_ref=tr,
                    predict_ref=qr,
                    constraints={"kind": "cfg"},
                )
                labels = json.loads((a.fixture / "external-gold.json").read_text())[
                    "cfg_dyck2_new_stratified-enriched"
                ]
                check(
                    "Unicode finite covariance80/80",
                    all(
                        p["status"] == "CHECKED_INSTANCE"
                        and p["decision"] == labels[p["record_id"]]
                        for p in uv["predictions"]
                    ),
                )
                q = lambda k, v, s, b: {"quant": k, "var": v, "sort": s, "body": b}
                var = lambda v: {"var": v}
                atom = lambda pred, *vs: {"pred": pred, "args": [var(v) for v in vs]}
                cases = [
                    (
                        "scope",
                        "Некоторые сотрудники не одобрили все заявки.",
                        {
                            "sorts": ["employee", "application"],
                            "predicates": {"Approved": ["employee", "application"]},
                        },
                        [
                            q(
                                "exists",
                                "e",
                                "employee",
                                {
                                    "not": q(
                                        "forall",
                                        "a",
                                        "application",
                                        atom("Approved", "e", "a"),
                                    )
                                },
                            ),
                            {
                                "not": q(
                                    "forall",
                                    "a",
                                    "application",
                                    q(
                                        "exists",
                                        "e",
                                        "employee",
                                        atom("Approved", "e", "a"),
                                    ),
                                )
                            },
                        ],
                        {
                            "domains": {
                                "employee": ["e1", "e2"],
                                "application": ["a1", "a2"],
                            },
                            "relations": {"Approved": [["e1", "a1"], ["e2", "a2"]]},
                            "world": "closed",
                        },
                        [True, False],
                    ),
                    (
                        "negation",
                        "Все модели не прошли проверку.",
                        {"sorts": ["model"], "predicates": {"Passed": ["model"]}},
                        [
                            q("forall", "m", "model", {"not": atom("Passed", "m")}),
                            {"not": q("forall", "m", "model", atom("Passed", "m"))},
                        ],
                        {
                            "domains": {"model": ["m1", "m2"]},
                            "relations": {"Passed": [["m1"]]},
                            "world": "closed",
                        },
                        [False, True],
                    ),
                ]
                for name, text, sig, formulas, model, expected in cases:
                    source = {
                        "text_utf8": text,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "spans": [],
                        "context_refs": [],
                        "rights": "original-controlled-manual-scope-variants",
                    }
                    sr, _ = await op(
                        "store", name + "-source", kind="source", data=source
                    )
                    props = [
                        {
                            "formula_ast": f,
                            "assumptions": [],
                            "token_role_links": [
                                {"byte_utf8": [0, len(text.encode())], "literal": text}
                            ],
                            "construction_trace": [
                                {
                                    "origin": "EXPLICIT_PROPOSED_SCOPE_READING",
                                    "no_author_intent_adjudication": True,
                                }
                            ],
                        }
                        for f in formulas
                    ]
                    r, v = await op(
                        "interpret",
                        name + "-readings",
                        source_ref=sr["stored_object_ref"],
                        candidate_provider={
                            "kind": "human",
                            "provenance": {
                                "origin": "explicit alternative quantifier/negation scope, not NLP output"
                            },
                        },
                        target_signature=sig,
                        proposals=props,
                    )
                    mr, _ = await op("store", name + "-model", kind="model", data=model)
                    values = []
                    for i, cc in enumerate(v["candidates"]):
                        _, mv = await op(
                            "model_check",
                            name + "-model-" + str(i),
                            run_ref=r["run_ref"],
                            candidate_ref=cc["candidate_id"],
                            model_ref=mr["stored_object_ref"],
                        )
                        values.append(mv["truth"])
                        check(
                            "meaning still proposed " + name,
                            cc["proof_status"] == "PROPOSED"
                            and cc["type_status"] == "TYPED",
                        )
                    check(
                        "negation/quantifier countermodel " + name, values == expected
                    )
                    _, cv = await op(
                        "contrast",
                        name + "-contrast",
                        run_ref=r["run_ref"],
                        candidate_refs=[cc["candidate_id"] for cc in v["candidates"]],
                    )
                    check(
                        "actual finite semantic discriminator " + name,
                        cv["status"] == "FINITE_COUNTERMODEL"
                        and len(set(cv["truth_vector"])) == 2,
                    )
                save("runs.json", runs)
                save(
                    "result.json",
                    {
                        "status": "PASS_AUX_FORMAL001",
                        "project": project,
                        "checks": len(checks),
                        "MCP_calls": len(calls),
                        "unicode_queries": 80,
                        "additional_ambiguous_sources": 2,
                        "generation": "MANUAL_PROPOSALS_NOT_NLP",
                        "execution_permission": False,
                        "public_HTTPS_tested": a.loopback_port is None,
                    },
                )
                print("AUX PASS", len(checks), len(calls))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
