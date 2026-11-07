"""Twenty-five explicit human-annotated controlled inputs; no NLP accuracy claim."""

import argparse, asyncio, base64, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream


async def run(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    calls = []
    checks = []
    runs = []
    save = lambda n, v: (out / n).write_text(
        json.dumps(v, ensure_ascii=False, indent=2) + "\n"
    )
    f = json.loads((a.fixture / "inputs.json").read_text())["fol"]
    sig = {"sorts": f["nonempty_sorts"], "predicates": f["signature"]}
    sentences = [
        "Каждый исследователь проверил хотя бы одну гипотезу.",
        "Одну общую гипотезу проверил каждый исследователь.",
        "Каждый исследователь проверил ровно одну гипотезу.",
    ]
    corpus = []
    for i in range(25):
        j = i % 3
        text = "Контекст №" + str(i) + ".\n" + sentences[j]
        raw = text.encode()
        start = len(("Контекст №" + str(i) + ".\n").encode())
        source = {
            "text_utf8": text,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "spans": [],
            "context_refs": [],
            "rights": "original-controlled-human-annotation-formal001",
        }
        proposal = {
            "formula_ast": f["candidates"][j]["formula_ast"],
            "assumptions": [],
            "token_role_links": [
                {"byte_utf8": [start, len(raw)], "literal": sentences[j]}
            ],
            "construction_trace": [
                {
                    "kind": "EXPLICIT_HUMAN_ORACLE",
                    "source": "controlled microcorpus, no automatic extraction",
                    "reading": j,
                }
            ],
        }
        corpus.append(
            {
                "source": source,
                "proposal": proposal,
                "reading": j,
                "expected_models": [
                    list(m["truth_vector"].values())[j] for m in f["finite_models"]
                ],
            }
        )
    save("FROZEN_CORPUS.json", corpus)
    save(
        "CORPUS_PROTOCOL.json",
        {
            "count": 25,
            "sha256": hashlib.sha256(
                (out / "FROZEN_CORPUS.json").read_bytes()
            ).hexdigest(),
            "proposer": "HAND_AUTHORED_ORACLE",
            "before_MCP_calls": True,
            "human_intent_agreement": None,
            "automatic_NLP": "NOT_IMPLEMENTED_NOT_CLAIMED",
        },
    )
    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    project = "qa-formal001-nl-" + a.tag
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        from mcp_retry_transport import install

        install(http, out / "HTTP_RETRIES.jsonl")
        async with streamable_http_client(a.endpoint, http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                TappedStream(read, out / "wire.jsonl", "server_to_client"),
                TappedStream(write, out / "wire.jsonl", "client_to_server"),
            ) as client:
                await client.initialize()

                def check(name, ok):
                    checks.append({"name": name, "status": "PASS" if ok else "FAIL"})
                    save("checks.json", checks)
                    if not ok:
                        raise AssertionError(name)

                async def call(name, args):
                    r = await client.call_tool(name, args)
                    calls.append(
                        {
                            "tool": name,
                            "arguments": args,
                            "response": r.model_dump(mode="json"),
                        }
                    )
                    save("transcript.json", calls)
                    v = r.structuredContent or json.loads(r.content[0].text)
                    check(name + " " + str(len(calls)), not r.isError)
                    return v.get("data", v)

                async def op(name, key, **kw):
                    r = await call(
                        "formal_" + name, {"project": project, "request_key": key, **kw}
                    )
                    check("completed " + key, r["status"] == "COMPLETED")
                    runs.append(r)
                    v = await call(
                        "formal_inspect",
                        {"project": project, "run_ref": r["run_ref"], "view": "result"},
                    )
                    return r, v

                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                models = []
                for i, m in enumerate(f["finite_models"]):
                    r, _ = await op(
                        "store",
                        "model-" + str(i),
                        kind="model",
                        data={**m["model"], "world": "closed"},
                    )
                    models.append(r["stored_object_ref"])
                ids = []
                for i, c in enumerate(corpus):
                    sr, _ = await op(
                        "store", "source-" + str(i), kind="source", data=c["source"]
                    )
                    rr, v = await op(
                        "interpret",
                        "proposal-" + str(i),
                        source_ref=sr["stored_object_ref"],
                        candidate_provider={
                            "kind": "human",
                            "provenance": {
                                "origin": "explicit controlled microcorpus",
                                "generation": "manual formula choice; generic server type/source checking",
                            },
                        },
                        target_signature=sig,
                        proposals=[c["proposal"]],
                    )
                    candidate = v["candidates"][0]
                    ids.append(candidate["candidate_id"])
                    check(
                        "typed proposed source alignment " + str(i),
                        candidate["type_status"] == "TYPED"
                        and candidate["proof_status"] == "PROPOSED"
                        and candidate["source_sha256"] == c["source"]["sha256"]
                        and candidate["source_ref"] == sr["stored_object_ref"],
                    )
                    for j, m in enumerate(models):
                        _, check_result = await op(
                            "model_check",
                            "truth-" + str(i) + "-" + str(j),
                            run_ref=rr["run_ref"],
                            candidate_ref=candidate["candidate_id"],
                            model_ref=m,
                        )
                        check(
                            "finite manual-oracle model " + str(i) + "-" + str(j),
                            check_result["truth"] == c["expected_models"][j]
                            and check_result["proof_status"] == "FINITE_MODEL_CHECKED"
                            and check_result["semantic_alignment_status"] == "PROPOSED",
                        )
                check("different source derivations not collapsed", len(set(ids)) == 25)
                save("runs.json", runs)
                save(
                    "result.json",
                    {
                        "status": "PASS_CONTROLLED_MANUAL_FORMAL001",
                        "project": project,
                        "checks": len(checks),
                        "MCP_calls": len(calls),
                        "source_aligned_proposals": 25,
                        "finite_model_checks": 50,
                        "automatic_NLP": "NOT_IMPLEMENTED_NOT_CLAIMED",
                        "human_agreement": None,
                        "execution_permission": False,
                        "public_HTTPS_tested": a.loopback_port is None,
                    },
                )
                print("CONTROLLED_PASS", len(checks), len(calls), flush=True)


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
