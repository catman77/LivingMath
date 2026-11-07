"""Real OAuth/MCP mixed-length acceptance; external scoring after all inference."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest
from recursive_observer_experiment import request, score
from generator005_fixture import record

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream


async def run(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save(n, v):
        (out / n).write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")

    checks = []
    calls = []
    models = {}
    runs = {}
    predictions = {}
    configs = {}

    def check(n, ok):
        checks.append({"check": n, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(n)

    protocol = json.loads((a.fixture / "PROTOCOL.json").read_text())
    raw = (a.fixture / "inputs.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == protocol["inputs_sha256"]
    data = json.loads(raw)
    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    project = "qa-generator005-" + a.tag
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        if a.retry_resource_busy:
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
                init = await client.initialize()
                listing = await client.list_tools()
                save("initialize.json", init.model_dump(mode="json"))
                save("tools.json", listing.model_dump(mode="json"))
                check("actual server version", init.serverInfo.version == a.version)

                async def call(name, args, error=None):
                    r = await client.call_tool(name, args)
                    row = {
                        "tool": name,
                        "arguments": args,
                        "response": r.model_dump(mode="json"),
                    }
                    calls.append(row)
                    with (out / "transcript.jsonl").open("a") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    v = r.structuredContent or json.loads(r.content[0].text)
                    check(
                        name
                        + (
                            " expected " + error
                            if error
                            else " call " + str(len(calls))
                        ),
                        bool(r.isError and v.get("error", {}).get("code") == error)
                        if error
                        else not r.isError,
                    )
                    return v.get("data", v)

                async def section(run, view, owner=None):
                    values = []
                    offset = 0
                    for _ in range(4096):
                        page = await call(
                            "white_star_symbolic_observer_inspect",
                            {
                                "project": owner or project,
                                "run_id": run,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if page.get("requires_artifact"):
                            chunks = []
                            pos = 0
                            for _ in range(4096):
                                q = await call(
                                    "white_star_symbolic_observer_inspect",
                                    {
                                        "project": owner or project,
                                        "run_id": run,
                                        "view": "artifact",
                                        "artifact_ref": page["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                chunks += [
                                    base64.b64decode(x["data_base64"])
                                    for x in q["items"]
                                ]
                                if q["next_offset"] is None:
                                    break
                                pos = q["next_offset"]
                            raw = b"".join(chunks)
                            check(
                                "source artifact SHA",
                                hashlib.sha256(raw).hexdigest() == q["artifact_sha256"],
                            )
                            v = json.loads(raw)
                            return v if isinstance(v, list) else [v]
                        values += page["items"]
                        if page["next_offset"] is None:
                            return values
                        offset = page["next_offset"]
                    raise AssertionError("pagination bound")

                async def store(kind, records, key):
                    d = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": records,
                    }
                    d["sha256"] = digest(d)
                    return (
                        await call(
                            "white_star_symbolic_dataset_store",
                            {"project": project, "request_key": key, "dataset": d},
                        )
                    )["dataset_ref"]

                before = {
                    t["name"]: t for t in json.loads(a.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                if a.allow_formal_api:
                    from formal001_compat import legacy_view
                    after=legacy_view(after)
                if a.allow_role_api:
                    schema = after["white_star_symbolic_observer_synthesize"][
                        "inputSchema"
                    ]["properties"]["request"]["properties"]["promotion_policy"][
                        "properties"
                    ]
                    schema["mode"]["enum"].remove("role_branching_ast")
                    for key in [
                        "role_max_tokens",
                        "role_max_cells",
                        "role_max_split_trials",
                    ]:
                        schema.pop(key)
                    after["white_star_symbolic_observer_verify"]["inputSchema"][
                        "properties"
                    ].pop("query_id")
                check(
                    "83 input output annotation schemas unchanged",
                    len(after) == len(before) == 83
                    and all(
                        all(
                            after[n][k] == v[k]
                            for k in ["inputSchema", "outputSchema", "annotations"]
                        )
                        for n, v in before.items()
                    ),
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                names = (
                    ["B", "B_SS", "B_PP", "B_SP", "B_PS"]
                    if a.before
                    else list(data["cases"])
                )
                refs = {
                    n: await store("train", data["cases"][n], "train-" + n)
                    for n in names
                }
                qr = {
                    n: await store("queries", data["queries"][n], "query-" + n)
                    for n in ["6", "7", "8"]
                }
                baseline_counts = {
                    "B": (14, 2),
                    "B_SS": (7, 0),
                    "B_PP": (7, 0),
                    "B_SP": (10, 2),
                    "B_PS": (10, 2),
                }
                for name in names:
                    lengths = (
                        [6]
                        if a.before
                        else [7]
                        if name in ["mix1234", "odd135", "odd13"]
                        else [8]
                        if name in ["even246", "mix126"]
                        else [6, 8]
                    )
                    for seed in [137] if a.before else [137, 42]:
                        for n in lengths if seed == 137 else lengths[:1]:
                            key = name + "-s" + str(seed) + "-n" + str(n)
                            q = request(seed)
                            q["promotion_policy"]["candidate_sources"] = [
                                "derivation_trace"
                            ]
                            q["task"].update(
                                train_ref=refs[name], predict_ref=qr[str(n)]
                            )
                            row = await call(
                                "white_star_symbolic_observer_synthesize",
                                {"project": project, "request_key": key, "request": q},
                            )
                            check("completed " + key, row["status"] == "COMPLETED")
                            runs[key] = row
                            configs[key] = q
                            save("runs.json", runs)
                            m = (await section(row["run_id"], "model"))[0]
                            p = (await section(row["run_id"], "pairwise_eval"))[0][
                                "predictions"
                            ]
                            models[key] = m
                            predictions[key] = p
                            d = m["composition_diagnostics"]["candidate_generation"]
                            if a.before:
                                check(
                                    "old exact candidate counts " + name,
                                    (d["seen"], d["train_compatible"])
                                    == baseline_counts[name],
                                )
                                check(
                                    "old causal negative " + name,
                                    bool(m["used_feature_ids"])
                                    == (name not in ["B_SS", "B_PP"]),
                                )
                                continue
                            check(
                                "new catalog diagnostics " + key,
                                d["grammar_version"]
                                == "mixed_length_typed_composition/1"
                                and d["bounded_search_complete"]
                                and d["search_budget"]["max_ast_nodes"] == 32,
                            )
                            compatible = [
                                x
                                for x in d["candidate_records"]
                                if x["train_status"] == "TRAIN_COMPATIBLE"
                            ]
                            check(
                                "retained recursive candidate " + key,
                                name.startswith("copy")
                                or any(
                                    x["kind"] == "iterate_on_inner_fragment"
                                    for x in compatible
                                ),
                            )
                            f = next(
                                f
                                for f in m["feature_registry"]
                                if f["feature_id"] in m["used_feature_ids"]
                            )
                            expected = (
                                "compare_fragments"
                                if name.startswith("copy")
                                else "aligned_token_equality"
                                if name == "odd13"
                                else "iterate_on_inner_fragment"
                            )
                            check(
                                "selected typed AST " + key,
                                f["operator_ast"]["composition"] == expected,
                            )
                            v = await call(
                                "white_star_symbolic_observer_verify",
                                {
                                    "project": project,
                                    "run_id": row["run_id"],
                                    "feature_id": f["feature_id"],
                                },
                            )
                            check(
                                "independent full train " + key,
                                v["status"] == "CHECKED_INSTANCE"
                                and v["verified_witnesses"] == len(data["cases"][name])
                                and not v["execution_permission"],
                            )
                            check(
                                "finite claims " + key,
                                f["claim_status"] == "CHECKED_FINITE_INSTANCE"
                                and not f["known_invariance_scope"][
                                    "universal_invariant"
                                ]
                                and m["identifiability_status"] == "UNDERDETERMINED",
                            )
                            if seed == 42:
                                check(
                                    "stable AST second seed " + name,
                                    f["operator_ast_digest"]
                                    == next(
                                        f
                                        for f in models[name + "-s137-n" + str(n)][
                                            "feature_registry"
                                        ]
                                        if f["feature_id"]
                                        in models[name + "-s137-n" + str(n)][
                                            "used_feature_ids"
                                        ]
                                    )["operator_ast_digest"],
                                )
                save("models.json", models)
                save("predictions.json", predictions)
                if not a.before:
                    # Explicit proposal truncation and real runtime failure must not masquerade as impossibility.
                    q = copy.deepcopy(configs["even24-s137-n6"])
                    q["search"]["max_proposals"] = 1
                    r = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "proposal-bound",
                            "request": q,
                        },
                    )
                    m = (await section(r["run_id"], "model"))[0]
                    d = m["composition_diagnostics"]["candidate_generation"]
                    check(
                        "bounded search incomplete is explicit",
                        d["search_status"] == "BOUNDED_SEARCH_INCOMPLETE"
                        and d["candidate_budget_exhausted"]
                        and not m["used_feature_ids"]
                        and any(
                            x["generation_status"] == "NOT_GENERATED"
                            for x in d["candidate_records"]
                        ),
                    )
                    q = copy.deepcopy(configs["mix126-s137-n8"])
                    q["search"]["max_cpu_ms"] = 1
                    limited = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "runtime-bound",
                            "request": q,
                        },
                        "BUDGET_EXCEEDED",
                    )
                    failed = (await section(limited["error"]["run_id"], "summary"))[0]
                    check(
                        "runtime exhausted is FAILED without false prediction",
                        failed["status"] == "FAILED"
                        and failed["error"]["code"] == "BUDGET_EXCEEDED"
                        and "result_ref" not in failed
                        and not limited["execution_permission"],
                    )
                    # Immutable existing0.4.6 source records route through the approved old profile.
                    historical = {}
                    for file in sorted(a.historical.glob("*.json")):
                        old = json.loads(file.read_text())
                        r = old["record"]
                        s = (
                            await section(
                                r["run_id"], "summary", "whitestar_dialog_test"
                            )
                        )[0]
                        check("old record immutable " + file.stem, s == r)
                        historical[file.stem] = s
                    old = json.loads((a.historical / "PAL4_base.json").read_text())
                    m = old["result"]["model"]
                    f = next(
                        f
                        for f in m["feature_registry"]
                        if f["feature_id"] in m["used_feature_ids"]
                    )
                    v = await call(
                        "white_star_symbolic_observer_verify",
                        {
                            "project": "whitestar_dialog_test",
                            "run_id": old["record"]["run_id"],
                            "feature_id": f["feature_id"],
                        },
                    )
                    check(
                        "old0.4.6 checker selected by binding",
                        v["status"] == "CHECKED_INSTANCE",
                    )
                    save("historical-runs.json", historical)
                    for key in ["mix1234-s137-n7", "copy52-s137-n8"]:
                        chunks = await section(runs[key]["run_id"], "export")
                        raw = b"".join(
                            base64.b64decode(x["data_base64"]) for x in chunks
                        )
                        ref = chunks[0]["bundle_ref"]
                        check(
                            "export hash " + key, hashlib.sha256(raw).hexdigest() == ref
                        )
                        (out / (key + ".zip")).write_bytes(raw)
                        v = await call(
                            "white_star_symbolic_extension_replay",
                            {"project": project, "bundle_ref": ref},
                        )
                        check(
                            "new replay " + key,
                            v["status"] == "REPLAY_MATCH"
                            and v["journal_hash_chain"] == "PASS",
                        )
                        save(key + "-replay.json", v)
                    # Idempotency and content-addressed result determinism with a fresh key.
                    key = "mix1234-s137-n7"
                    q = configs[key]
                    same = await call(
                        "white_star_symbolic_observer_synthesize",
                        {"project": project, "request_key": key, "request": q},
                    )
                    fresh = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "fresh-identical",
                            "request": q,
                        },
                    )
                    check(
                        "request idempotency and fresh digest",
                        same["run_id"] == runs[key]["run_id"]
                        and fresh["run_id"] != same["run_id"]
                        and fresh["result_digest"] == same["result_digest"],
                    )
                # First access to external gold follows every inference and replay.
                raw = (a.fixture / "external-gold.json").read_bytes()
                assert (
                    hashlib.sha256(raw).hexdigest() == protocol["external_gold_sha256"]
                )
                gold = json.loads(raw)
                scores = {}
                for key, p in predictions.items():
                    name = key.split("-s")[0]
                    n = key.rsplit("-n", 1)[1]
                    kind = "copy" if name.startswith("copy") else "mirror"
                    s = score(p, gold[n][kind])
                    seen = {tuple(r["tokens"]) for r in data["cases"][name]}
                    s["train_word_overlap"] = sum(
                        tuple(r["tokens"]) in seen for r in data["queries"][n]
                    )
                    scores[key] = s
                    if not a.before:
                        check(
                            "finite exact transfer " + key,
                            s["FP"] == s["FN"] == s["UNKNOWN"] == 0
                            if name != "odd13"
                            else s["FP"] == 48 and s["FN"] == 0,
                        )
                save("scores.json", scores)
                save("transcript.json", calls)
                health = await call("service_health", {})
                save("health.json", health)
                check(
                    "SQLite and audit healthy",
                    health["sqlite_integrity"] == "ok" and health["audit"]["ok"],
                )
                save("transcript.json", calls)
                result = {
                    "status": "PASS_BASELINE_REPRODUCED"
                    if a.before
                    else "PASS_FINITE_PATCH005",
                    "project": project,
                    "version": init.serverInfo.version,
                    "endpoint": a.endpoint,
                    "public_HTTPS_tested": a.endpoint.startswith("https://"),
                    "checks": len(checks),
                    "MCP_calls": len(calls),
                    "run_ids": {k: v["run_id"] for k, v in runs.items()},
                    "scores": scores,
                    "external_gold_loaded_after_inference": True,
                    "execution_permission": False,
                }
                save("result.json", result)
                print(
                    json.dumps(
                        {
                            "status": result["status"],
                            "checks": len(checks),
                            "calls": len(calls),
                            "project": project,
                        }
                    )
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--allow-formal-api",action="store_true")
    p.add_argument("--allow-role-api", action="store_true")
    p.add_argument("--retry-resource-busy", action="store_true")
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--tag", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--historical", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--before", action="store_true")
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
