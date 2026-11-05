"""Actual owner OAuth + MCP acceptance, usable on rehearsal or the public endpoint."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from lm_suti_assurance.core import digest


async def run(args):
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    out = args.output

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    token = args.token or out / "oauth.private.json"
    auth = (
        json.loads(token.read_text())
        if token.exists()
        else authenticate(args.origin, args.password, token, args.loopback_port)
    )
    checks = []
    calls = []

    def check(name, ok):
        checks.append({"invariant": name, "result": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        assert ok, name

    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if args.loopback_port:
        headers["Host"] = "livingmath.example"
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        async with streamable_http_client(args.endpoint, http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                TappedStream(read, out / "mcp-wire.jsonl", "server_to_client"),
                TappedStream(write, out / "mcp-wire.jsonl", "client_to_server"),
            ) as client:
                info = await client.initialize()
                listing = await client.list_tools()
                save("initialize.json", info.model_dump(mode="json"))
                save("tools-list.json", listing.model_dump(mode="json"))
                check("REAL_75_TOOLS", len(listing.tools) == 75)
                check(
                    "SERVER_RELEASE",
                    info.serverInfo.version == "v0.4.0-developer-preview",
                )
                before = {
                    v["name"]: v for v in json.loads(args.baseline.read_text())["tools"]
                }
                after = {v.name: v.model_dump(mode="json") for v in listing.tools}
                check(
                    "ALL_72_OLD_CONTRACTS_UNCHANGED",
                    len(before) == 72
                    and all(
                        n in after
                        and all(
                            v.get(k) == after[n].get(k)
                            for k in ("inputSchema", "outputSchema", "annotations")
                        )
                        for n, v in before.items()
                    ),
                )

                async def call(name, arguments, error=None):
                    reply = await client.call_tool(name, arguments)
                    calls.append(
                        {
                            "tool": name,
                            "arguments": arguments,
                            "response": reply.model_dump(mode="json"),
                        }
                    )
                    save("mcp-transcript.json", calls)
                    value = reply.structuredContent or json.loads(reply.content[0].text)
                    if error:
                        check(
                            "TYPED_" + error + "_" + str(len(calls)),
                            reply.isError and value["error"]["code"] == error,
                        )
                    else:
                        check("CALL_" + name + "_" + str(len(calls)), not reply.isError)
                    return value

                status = await call("bridge_system_status", {})
                save("bridge-status.json", status)
                check(
                    "ROOT_SYMBOLIC_CAPABILITIES_READY",
                    status["symbolic_v1"]["status"] == "READY"
                    and status["symbolic_v1"]["version"] == "symbolic_v1/1",
                )
                old_status = await call("white_star_status", {})
                check(
                    "OLD_NATIVE_READY_AND_SUPPLIED_BYTES",
                    old_status["data"]["status"] == "READY"
                    and len(old_status["data"]["kernel_hashes"]) == 75,
                )
                request = json.loads(
                    (
                        Path(__file__).resolve().parents[1]
                        / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
                    ).read_text()
                )["request"]
                project = "qa-symbolic-v1-" + args.tag
                await call(
                    "white_star_symbolic_explore",
                    {"project": project, "request_key": "sp-one", "request": request},
                    "PROJECT_NOT_FOUND",
                )
                registration = await call(
                    "assurance_project_new",
                    {"project": project, "request_key": "project-init-v1"},
                )
                check("REGISTERED_PROJECT", registration["status"] == "CREATED")

                async def explore(req, key):
                    return (
                        await call(
                            "white_star_symbolic_explore",
                            {"project": project, "request_key": key, "request": req},
                        )
                    )["data"]

                first = await explore(request, "sp-one")
                save("first-run.json", first)
                check(
                    "REAL_SYMBOLIC_COMPLETED",
                    first["status"] == "COMPLETED"
                    and first["engine"] == "symbolic_v1"
                    and bool(first["run_id"]),
                )
                second = await explore(request, "sp-one")
                check("RUN_IDEMPOTENT_SAME_DATA", first == second)
                conflict = copy.deepcopy(request)
                conflict["search"]["seed"] += 1
                await call(
                    "white_star_symbolic_explore",
                    {"project": project, "request_key": "sp-one", "request": conflict},
                    "REQUEST_CONFLICT",
                )
                artifacts = {}

                async def view(ident, name):
                    offset = 0
                    values = []
                    while True:
                        page = (
                            await call(
                                "white_star_symbolic_inspect",
                                {
                                    "project": project,
                                    "run_id": ident,
                                    "view": name,
                                    "offset": offset,
                                    "limit": 32,
                                },
                            )
                        )["data"]
                        if page["requires_artifact"]:
                            chunks = []
                            start = 0
                            while True:
                                artifact = (
                                    await call(
                                        "white_star_symbolic_inspect",
                                        {
                                            "project": project,
                                            "run_id": ident,
                                            "view": "artifact",
                                            "artifact_ref": page["artifact_ref"],
                                            "offset": start,
                                            "limit": 128,
                                        },
                                    )
                                )["data"]
                                chunks.extend(artifact["items"])
                                if artifact["next_offset"] is None:
                                    break
                                start = artifact["next_offset"]
                            complete = json.loads(
                                b"".join(
                                    base64.b64decode(c["data_base64"]) for c in chunks
                                )
                            )
                            mapping = {
                                "operations": "ops_trace",
                                "observations": "structural_observations",
                                "claims": "equivalence_claims",
                                "grammar": "grammar_hypotheses",
                                "evaluation": "heldout_eval",
                            }
                            value = complete[mapping.get(name, name)]
                            return value if isinstance(value, list) else [value]
                        values.extend(page["items"])
                        if page["next_offset"] is None:
                            return values
                        offset = page["next_offset"]

                for name in (
                    "input",
                    "operations",
                    "observations",
                    "claims",
                    "grammar",
                    "evaluation",
                    "history",
                    "states",
                    "source",
                    "checks",
                    "manifest",
                    "report",
                ):
                    artifacts[name] = await view(first["run_id"], name)
                    check("INSPECT_" + name, bool(artifacts[name]))
                save("artifacts.json", artifacts)
                pair = [
                    c
                    for c in artifacts["claims"]
                    if c["relation"] == "same_sp_normal_form"
                ]
                check(
                    "FOUR_ZERO_HISTORIES_ALL_SAME_NORMAL_FORM",
                    len(pair) == 6
                    and all(c["equal"] and c["kind"] == "proved_exact" for c in pair),
                )
                check(
                    "ZERO_HISTORIES_LITERAL_DISTINCT",
                    all(
                        not c["equal"]
                        for c in artifacts["claims"]
                        if c["relation"] == "literal_word_equality"
                    ),
                )
                check(
                    "NO_VERIFIED_NO_GRANT",
                    first["execution_permission"] is False
                    and not any(c["kind"] == "verified" for c in artifacts["claims"]),
                )
                # Export/replay uses a real private persisted bundle, never a fabricated worker response.
                chunks = await view(first["run_id"], "export")
                raw = b"".join(base64.b64decode(c["data_base64"]) for c in chunks)
                bundle_ref = chunks[0]["bundle_ref"]
                check(
                    "EXPORT_SHA_AND_CHUNKS",
                    hashlib.sha256(raw).hexdigest() == bundle_ref
                    and len(chunks) == chunks[0]["chunk_count"],
                )
                (out / "symbolic-run.zip").write_bytes(raw)
                replay = await call(
                    "white_star_symbolic_replay",
                    {"project": project, "bundle_ref": bundle_ref},
                )
                check(
                    "REAL_RECOMPUTED_REPLAY",
                    replay["data"]["status"] == "REPLAY_MATCH"
                    and replay["data"]["result_digest"] == first["result_digest"],
                )
                await call(
                    "assurance_project_new",
                    {"project": project + "-other", "request_key": "new"},
                )
                await call(
                    "white_star_symbolic_replay",
                    {"project": project + "-other", "bundle_ref": bundle_ref},
                    "NOT_FOUND",
                )
                for defect, code in [
                    ("hash", "SOURCE_MISMATCH"),
                    ("alphabet", "INVALID_INPUT"),
                    ("operator", "INVALID_INPUT"),
                    ("budget", "INVALID_INPUT"),
                    ("span", "INVALID_SPAN"),
                    ("history", "INVALID_INPUT"),
                    ("SP-domain", "SP_ALGEBRA_REQUIRED"),
                ]:
                    bad = copy.deepcopy(request)
                    if defect == "hash":
                        bad["source"]["sha256"] = "0" * 64
                    elif defect == "alphabet":
                        bad["source"]["alphabet"] = []
                    elif defect == "operator":
                        bad["operators"] = ["UNKNOWN_EXECUTION"]
                    elif defect == "budget":
                        bad["search"]["max_steps"] = 4097
                    elif defect == "span":
                        bad["source"]["segments"] = [
                            {
                                "id": "broken",
                                "kind": "line",
                                "byte_start": 0,
                                "byte_end": 48000,
                            }
                        ]
                    elif defect == "history":
                        bad["history"] = [{"parent_ids": ["missing"]}]
                    else:
                        bad["algebra"]["kind"] = "FREE"
                    await call(
                        "white_star_symbolic_explore",
                        {
                            "project": project,
                            "request_key": "bad-" + defect,
                            "request": bad,
                        },
                        code,
                    )

                def free(text, scope="global"):
                    req = copy.deepcopy(request)
                    req["source"].update(
                        text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
                    )
                    req["algebra"].update(kind="FREE", allow_reduce=False)
                    req["operators"] = ["CONCAT", "SPLIT", "RENAME", "REVERSE"]
                    req["observers"] = [
                        "literal",
                        "alpha_pattern",
                        "adjacency",
                        "substring_contexts",
                        "composition",
                        "hierarchy",
                    ]
                    req["segmentation"]["renaming_scope"] = scope
                    req["search"]["max_steps"] = 8
                    return req

                abba = await explore(free("ABBA\nBAAB"), "alpha-isolated")
                claims = await view(abba["run_id"], "claims")
                check(
                    "ABBA_BAAB_ISOLATED_ALPHA",
                    next(c for c in claims if c["relation"] == "alpha_equality")[
                        "equal"
                    ],
                )
                patterns = {}
                for scope in ("global", "local"):
                    for label, text in [("same", "AB\nAB"), ("distinct", "AB\nCD")]:
                        run = await explore(free(text, scope), scope + "-" + label)
                        observations = await view(run["run_id"], "observations")
                        patterns[scope + "-" + label] = observations[0]["observers"][
                            "alpha_pattern"
                        ]
                check(
                    "GLOBAL_SCOPE_PRESERVES_CROSS_WORD_IDENTITY",
                    patterns["global-same"] != patterns["global-distinct"],
                )
                check(
                    "LOCAL_SCOPE_DECLARED_QUOTIENT",
                    patterns["local-same"] == patterns["local-distinct"],
                )
                req = free("ABBA")
                req["task"] = {
                    "mode": "predictive",
                    "train": [
                        {"tokens": list(a + middle + b), "accepted": a == b}
                        for a in "AB"
                        for b in "AB"
                        for middle in ("ABAB", "BABA", "AABB", "BBAA")
                    ],
                    "predict": [
                        list("A" + "ABBA" * 5 + "A"),
                        list("A" + "ABBA" * 5 + "B"),
                    ],
                }
                predicted = await explore(req, "predictive")
                evaluation = (await view(predicted["run_id"], "evaluation"))[0]
                grammar = (await view(predicted["run_id"], "grammar"))[0]
                check(
                    "PREDICTIONS_AFTER_FROZEN_HYPOTHESIS",
                    [
                        p["membership_probability"] >= 0.5
                        for p in evaluation["predictions"]
                    ]
                    == [True, False]
                    and all(
                        p["hypothesis_digest"] == grammar["hypothesis_digest"]
                        for p in evaluation["predictions"]
                    ),
                )
                old_run = args.historical_run
                if old_run:
                    await call(
                        "white_star_inspect",
                        {
                            "project": "qa-ws-onboarding-20261105",
                            "run_id": old_run,
                            "view": "frames",
                        },
                    )
                    if args.historical_bundle:
                        old = await call(
                            "white_star_replay",
                            {
                                "project": "qa-ws-onboarding-20261105",
                                "bundle_ref": args.historical_bundle,
                            },
                        )
                        check(
                            "PREUPGRADE_NUMERICAL_BUNDLE_REPLAYS",
                            old["data"]["status"] == "PASS"
                            and old["data"]["runs_recomputed"] == 1
                            and old["data"]["network"] == "DISABLED",
                        )
                health = await call("service_health", {})
                save("health.json", health)
                doctor = await call("assurance_doctor", {})
                save("doctor.json", doctor)
                check(
                    "SQLITE_AND_CANONICAL_AUDIT_OK",
                    health["sqlite_integrity"] == "ok" and health["audit"]["ok"],
                )
                check(
                    "ORIGINAL_APPROVAL_BOUNDARIES",
                    doctor["status"] == "PASS"
                    and doctor["native_SUTI"] == "NOT_EXECUTED"
                    and doctor["execution_permission"] is False,
                )
                result = {
                    "status": "PASS",
                    "checks": len(checks),
                    "version": info.serverInfo.version,
                    "deployment_id": health["deployment_id"],
                    "tool_count": 75,
                    "endpoint": args.endpoint,
                    "origin": args.origin,
                    "public_HTTPS_tested": not args.loopback_port,
                    "project": project,
                    "run_id": first["run_id"],
                    "bundle_ref": bundle_ref,
                    "result_digest": first["result_digest"],
                    "kernel_binding": first["kernel_binding"],
                    "old_72_schemas_unchanged": True,
                    "execution_permission": False,
                }
                save("result.json", result)
                print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--token", type=Path)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    p.add_argument("--historical-run")
    p.add_argument("--historical-bundle")
    asyncio.run(run(p.parse_args()))
