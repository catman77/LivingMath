"""Bounded real MCP acceptance for PATCH001/002; historical runs stay immutable."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from collections import Counter
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from lm_suti_assurance.core import digest


async def run(args):
    out = args.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    auth = authenticate(
        args.origin, args.password, out / "oauth.private.json", args.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if args.loopback_port:
        headers["Host"] = "livingmath.example"
    checks = []
    calls = []
    matrix = {}
    history_project = "whitestar_dialog_test"
    fixture = json.loads(
        (
            ROOT
            / "docs/LIVINGMATH_SYMBOLIC_V1_ACCEPTANCE_PATCH001/fixtures/acceptance_runs.json"
        ).read_text()
    )
    project = ("qa-patch002-" if args.patch002 else "qa-patch001-") + args.tag

    def check(name, ok):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        assert ok, name

    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        async with streamable_http_client(args.endpoint, http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                TappedStream(read, out / "wire.jsonl", "server_to_client"),
                TappedStream(write, out / "wire.jsonl", "client_to_server"),
            ) as c:
                init = await c.initialize()
                listing = await c.list_tools()
                save("initialize.json", init.model_dump(mode="json"))
                save("tools.json", listing.model_dump(mode="json"))
                check(
                    "75 tools and actual version",
                    len(listing.tools) == 75
                    and init.serverInfo.version == args.expected_version,
                )
                before = {
                    t["name"]: t for t in json.loads(args.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                unchanged = [
                    n
                    for n in before
                    if all(
                        before[n].get(k) == after[n].get(k)
                        for k in ("inputSchema", "outputSchema", "annotations")
                    )
                ]
                check(
                    (
                        "all75 schemas unchanged"
                        if args.patch002
                        else "74 schemas unchanged"
                    ),
                    (
                        (len(unchanged) == 75)
                        if args.patch002
                        else (
                            len(unchanged) == 74
                            and "white_star_symbolic_inspect" not in unchanged
                        )
                    ),
                )
                old = before["white_star_symbolic_inspect"]["inputSchema"]
                new = after["white_star_symbolic_inspect"]["inputSchema"]
                check(
                    (
                        "inspect schema unchanged"
                        if args.patch002
                        else "inspect extension additive"
                    ),
                    (
                        (old == new)
                        if args.patch002
                        else (
                            old["required"] == new["required"]
                            and set(old["properties"]["view"]["enum"])
                            <= set(new["properties"]["view"]["enum"])
                            and set(new["properties"]) - set(old["properties"])
                            == {"compare_run_id"}
                            and before["white_star_symbolic_inspect"].get(
                                "outputSchema"
                            )
                            == after["white_star_symbolic_inspect"].get("outputSchema")
                        )
                    ),
                )

                async def call(name, arguments, error=None):
                    reply = await c.call_tool(name, arguments)
                    calls.append(
                        {
                            "tool": name,
                            "arguments": arguments,
                            "response": reply.model_dump(mode="json"),
                        }
                    )
                    save("transcript.json", calls)
                    value = reply.structuredContent or json.loads(reply.content[0].text)
                    if error:
                        check(
                            "typed " + error + " " + str(len(calls)),
                            reply.isError and value["error"]["code"] == error,
                        )
                    else:
                        check(name + " " + str(len(calls)), not reply.isError)
                    return value

                async def view(run_id, name, owner=project, **extra):
                    values = []
                    offset = 0
                    while True:
                        page = (
                            await call(
                                "white_star_symbolic_inspect",
                                {
                                    "project": owner,
                                    "run_id": run_id,
                                    "view": name,
                                    "offset": offset,
                                    "limit": 32,
                                    **extra,
                                },
                            )
                        )["data"]
                        if page["requires_artifact"]:
                            chunks = []
                            start = 0
                            while True:
                                block = (
                                    await call(
                                        "white_star_symbolic_inspect",
                                        {
                                            "project": owner,
                                            "run_id": run_id,
                                            "view": "artifact",
                                            "artifact_ref": page["artifact_ref"],
                                            "offset": start,
                                            "limit": 128,
                                        },
                                    )
                                )["data"]
                                chunks += block["items"]
                                if block["next_offset"] is None:
                                    break
                                start = block["next_offset"]
                            result = json.loads(
                                b"".join(
                                    base64.b64decode(v["data_base64"]) for v in chunks
                                )
                            )
                            mapping = {
                                "operations": "ops_trace",
                                "observations": "structural_observations",
                                "grammar": "grammar_hypotheses",
                                "evaluation": "heldout_eval",
                                "claims": "equivalence_claims",
                                "diagnostics": "search_diagnostics",
                            }
                            item = result[mapping.get(name, name)]
                            return item if isinstance(item, list) else [item]
                        values += page["items"]
                        if page["next_offset"] is None:
                            return values
                        offset = page["next_offset"]

                async def explore(req, key):
                    value = (
                        await call(
                            "white_star_symbolic_explore",
                            {"project": project, "request_key": key, "request": req},
                        )
                    )["data"]
                    check("completed " + key, value["status"] == "COMPLETED")
                    return value

                status = await call("bridge_system_status", {})
                save("root-status.json", status)
                check(
                    "patch READY and historical profile approved",
                    status["symbolic_v1"]["status"] == "READY"
                    and ("patch002" if args.patch002 else "patch001")
                    in status["symbolic_v1"]["version"]
                    and fixture["server"]["kernel_binding"]
                    in status["symbolic_v1"]["historical_replay_bindings"],
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "new"}
                )
                template = json.loads(
                    (
                        ROOT
                        / "docs/LIVINGMATH_SYMBOLIC_V1/fixtures/mcp_request_example.json"
                    ).read_text()
                )["request"]
                template["search"].update(
                    max_steps=16, max_nodes=256, max_word_tokens=128
                )
                first = await explore(template, "zero")
                save("first-run.json", first)
                matrix["AC01"] = "PASS"
                claims = await view(first["run_id"], "claims")
                check(
                    "literal zero histories stay different",
                    all(
                        not x["equal"]
                        for x in claims
                        if x["relation"] == "literal_word_equality"
                    ),
                )
                check(
                    "zero normal forms equal",
                    all(
                        x["equal"]
                        for x in claims
                        if x["relation"] == "same_sp_normal_form"
                    ),
                )
                matrix["AC02"] = "PASS"
                repeat = await explore(template, "zero")
                check("idempotent run exact", repeat == first)
                replica = await explore(template, "zero-copy")
                check(
                    "different keys same structural digest",
                    replica["run_id"] != first["run_id"]
                    and replica["result_digest"] == first["result_digest"],
                )
                matrix["AC07"] = "PASS"

                def free(text):
                    r = copy.deepcopy(template)
                    r["source"].update(
                        text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
                    )
                    r["algebra"].update(kind="FREE", allow_reduce=False)
                    r["operators"] = ["CONCAT", "SPLIT", "RENAME", "REVERSE"]
                    r["observers"] = [
                        "literal",
                        "alpha_pattern",
                        "adjacency",
                        "substring_contexts",
                        "composition",
                        "hierarchy",
                    ]
                    return r

                async def compare(a, b):
                    return (await view(a, "comparison", compare_run_id=b))[0]

                a = await explore(free("ABBA\nBAAB\nABAB"), "alpha-a")
                b = await explore(free("XYYX\nYXXY\nXYXY"), "alpha-b")
                comp = await compare(a["run_id"], b["run_id"])
                check(
                    "global alpha exact witness",
                    comp["same_alpha"]
                    and not comp["same_literal"]
                    and comp["literal_witness"]["left"]["original_byte_spans"],
                )
                matrix["AC03"] = "PASS"
                a = await explore(free("ABAB\nBABA\nABBA\nBAAB"), "order-a")
                b = await explore(free("ABBA\nBAAB\nABAB\nBABA"), "order-b")
                comp = await compare(a["run_id"], b["run_id"])
                check(
                    "record order explicit",
                    not comp["same_literal"] and not comp["same_history"],
                )
                matrix["AC04"] = "PASS"
                runs = {}
                for name, text in [
                    ("ab", "SSPPSPSP"),
                    ("ba", "SPSPSSPP"),
                    ("cd", "SPPSPSSP"),
                    ("dc", "PSSPSPPS"),
                ]:
                    r = copy.deepcopy(template)
                    r["source"].update(
                        text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
                    )
                    r["source"]["segments"] = [
                        {
                            "id": "left",
                            "kind": "supplied_component",
                            "byte_start": 0,
                            "byte_end": 4,
                        },
                        {
                            "id": "right",
                            "kind": "supplied_component",
                            "byte_start": 4,
                            "byte_end": 8,
                        },
                    ]
                    runs[name] = await explore(r, name)
                for x, y in [("ab", "ba"), ("cd", "dc")]:
                    comp = await compare(runs[x]["run_id"], runs[y]["run_id"])
                    check(
                        x + "/" + y + " explicit SP/order/route witnesses",
                        not comp["same_literal"]
                        and comp["same_sp_normal_form"]
                        and not comp["same_op_trace"]
                        and bool(comp["sp_witness"]["left_reduction_route"])
                        and bool(comp["composition_witness"]["left_declared_segments"]),
                    )
                matrix["AC05"] = "PASS"
                old_ab = (
                    await view(fixture["compositions"]["ab"], "input", history_project)
                )[0]
                sat = await explore(old_ab, "saturation")
                all_diagnostics = await view(sat["run_id"], "diagnostics")
                diagnostics = all_diagnostics[0]
                check(
                    "local saturated with unproposed insertion",
                    (
                        sat["summary"]["fallback_count"] > 0
                        if args.patch002
                        else (
                            sat["summary"]["halt_reason"] == "NO_NOVEL_CANDIDATES"
                            and sat["summary"]["steps"] < 128
                        )
                    )
                    and diagnostics["global_exhaustion_proved"] is False
                    and "INSERT_CANCEL_PAIR" in diagnostics["unproposed_operators"],
                )
                old_trace = await view(
                    fixture["compositions"]["ab"], "operations", history_project
                )
                new_trace = await view(sat["run_id"], "operations")
                prefix = next(
                    (
                        d["step"]
                        for d in all_diagnostics
                        if d.get("status") == "FRONTIER_FALLBACK"
                    ),
                    len(new_trace),
                )
                check(
                    "UDAV unchanged exact trace prefix",
                    new_trace[:prefix] == old_trace[:prefix],
                )
                provenance = copy.deepcopy(old_ab)
                provenance["search"]["history_identity"] = "provenance"
                paths = await explore(provenance, "paths")
                states = await view(paths["run_id"], "states")
                check(
                    "provenance paths retained",
                    paths["summary"]["nodes"] > sat["summary"]["nodes"]
                    and len({s["word_hash"] for s in states}) < len(states),
                )
                matrix["AC06"] = "PASS"
                chunks = await view(first["run_id"], "export")
                raw = b"".join(base64.b64decode(v["data_base64"]) for v in chunks)
                bundle_ref = chunks[0]["bundle_ref"]
                check(
                    "private export hash exact",
                    hashlib.sha256(raw).hexdigest() == bundle_ref,
                )
                (out / "new-symbolic.zip").write_bytes(raw)
                replay = await call(
                    "white_star_symbolic_replay",
                    {"project": project, "bundle_ref": bundle_ref},
                )
                check(
                    "new structural replay",
                    replay["data"]["status"] == "REPLAY_MATCH"
                    and replay["data"]["result_digest"] == first["result_digest"],
                )
                historical = await call(
                    "white_star_symbolic_replay",
                    {
                        "project": history_project,
                        "bundle_ref": fixture["replay"]["bundle_ref"],
                    },
                )
                check(
                    "historical v040 exact replay",
                    historical["data"]["result_digest"]
                    == fixture["replay"]["result_digest"]
                    and historical["data"]["journal_hash_chain"] == "PASS",
                )
                matrix["AC08"] = "PASS"
                original = (
                    await view(
                        fixture["grammar_palindrome"]["run_id"],
                        "input",
                        history_project,
                    )
                )[0]
                request = copy.deepcopy(original)
                words = [
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
                request["task"]["predict"] = [list(w) for w in words]
                pred_run = await explore(request, "relations")
                grammar = (await view(pred_run["run_id"], "grammar"))[0]
                evaluation = (await view(pred_run["run_id"], "evaluation"))[0]
                save("new-grammar.json", grammar)
                save("new-predictions.json", evaluation)
                check(
                    "selected relation9/9 without duplicate",
                    all(
                        (p["membership_probability"] >= 0.5) == (w == w[::-1])
                        for p, w in zip(evaluation["predictions"], words)
                    ),
                )
                check(
                    "explicit candidate versus family status",
                    grammar["candidate_status"] == "EMPIRICAL"
                    and grammar["identifiability_status"] == "UNDERDETERMINED"
                    and grammar["counterexample_candidates"]
                    and grammar["rule_witnesses"],
                )
                check(
                    "old false positives show disagreement",
                    all(
                        p["decision"]["family_verdict"] == "INCONCLUSIVE"
                        for p, w in zip(evaluation["predictions"], words)
                        if w in ("ABCBCA", "ABABBA", "BAABAB")
                    ),
                )
                second = copy.deepcopy(request)
                second["task"]["predict"] = [
                    list(w) for w in ["XYZZYX", "opaque", "different"]
                ]
                masked = await explore(second, "mask")
                check(
                    "queries do not choose hypothesis",
                    (await view(masked["run_id"], "grammar"))[0]["hypothesis_digest"]
                    == grammar["hypothesis_digest"],
                )
                matrix["AC09"] = "PASS"
                matrix["AC14"] = "PASS_WITH_UNDERDETERMINED_FAMILY"
                probe = grammar["counterexample_candidates"][0]
                label = probe["tokens"] == list(reversed(probe["tokens"]))
                augmented = copy.deepcopy(request)
                augmented["task"]["train"].append(
                    {"tokens": probe["tokens"], "accepted": label}
                )
                augmented["task"]["predict"] = [probe["tokens"]]
                active = await explore(augmented, "active-query")
                active_eval = (await view(active["run_id"], "evaluation"))[0]
                check(
                    "external active query cycle",
                    active_eval["predictions"][0]["decision"][
                        "selected_candidate_accepts"
                    ]
                    == label,
                )
                matrix["AC15"] = "PASS"
                unicode = free("Тихии\u0306 дом\nОкно и тень")
                unicode["normalization"] = "NFC"
                u = await explore(unicode, "unicode")
                source = (await view(u["run_id"], "source"))[0]
                check(
                    "NFC and source-byte map retained",
                    source["normalization"] == "NFC"
                    and source["normalized_text"] != source["original"]["text"],
                )
                matrix["AC10"] = "PASS"
                mallarme = (await view(fixture["mallarme"], "input", history_project))[
                    0
                ]
                check(
                    "exact accepted Mallarme source",
                    mallarme["source"]["sha256"]
                    == "fa7e64241104d5b195e9542f568a329937d11eb6a590f3af12870db63172c91a",
                )
                mallarme["search"].update(max_steps=16, max_nodes=256)
                m = await explore(mallarme, "mallarme-original")
                permuted = copy.deepcopy(mallarme)
                text = "\n".join(reversed(mallarme["source"]["text"].split("\n")))
                permuted["source"].update(
                    text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
                )
                mp = await explore(permuted, "mallarme-permuted")
                check(
                    "Mallarme line-order witness",
                    not (await compare(m["run_id"], mp["run_id"]))["same_literal"],
                )
                letters = Counter(
                    c for c in mallarme["source"]["text"] if c.isascii() and c.isalpha()
                )
                a, b = next(
                    (a, b)
                    for a in sorted(letters)
                    for b in sorted(letters)
                    if a < b and letters[a] == letters[b]
                )
                renamed = copy.deepcopy(mallarme)
                text = mallarme["source"]["text"].translate(str.maketrans({a: b, b: a}))
                renamed["source"].update(
                    text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
                )
                mr = await explore(renamed, "mallarme-renamed")
                cmp = await compare(m["run_id"], mr["run_id"])
                check(
                    "Mallarme equal-frequency renaming witness",
                    Counter(text) == Counter(mallarme["source"]["text"])
                    and cmp["same_alpha"]
                    and not cmp["same_literal"],
                )
                matrix["AC11"] = "PASS_STRUCTURAL_ONLY"
                old = await call("white_star_status", {})
                check(
                    "native ready2profiles75hashes",
                    old["data"]["status"] == "READY"
                    and old["data"]["profiles"] == ["base_v1", "cj_v1"]
                    and len(old["data"]["kernel_hashes"]) == 75,
                )
                legacy = await call(
                    "white_star_inspect",
                    {
                        "project": history_project,
                        "run_id": fixture["legacy"],
                        "view": "summary",
                    },
                )
                save("historical-white.json", legacy)
                numerical_replay = await call(
                    "white_star_replay",
                    {
                        "project": "qa-ws-onboarding-20261105",
                        "bundle_ref": "2b3d744c0b7f0a0beb54f8d634a4cae345f387740fdafac7e0d20e8b57c912a5",
                    },
                )
                check(
                    "numerical replay actually recomputed",
                    numerical_replay["data"]["status"] == "PASS"
                    and numerical_replay["data"]["runs_recomputed"] == 1
                    and numerical_replay["data"]["network"] == "DISABLED",
                )
                matrix["AC12"] = "PASS"
                bad = copy.deepcopy(template)
                bad["source"]["sha256"] = "0" * 64
                err = await call(
                    "white_star_symbolic_explore",
                    {"project": project, "request_key": "bad-sha", "request": bad},
                    "SOURCE_MISMATCH",
                )
                check(
                    "SHA error has precise path",
                    err["error"]["field_path"] == "/source/sha256",
                )
                matrix["AC13"] = "PASS"
                historical_ids = [
                    fixture["sp_exact"],
                    fixture["identity_word"],
                    *fixture["free_rename"],
                    *fixture["free_permutation"],
                    *fixture["compositions"].values(),
                    fixture["replay"]["reference"],
                    fixture["replay"]["replicate"],
                    fixture["grammar_palindrome"]["run_id"],
                    *fixture["heldout_isolation"]["run_ids"],
                    fixture["unicode"],
                    fixture["mallarme"],
                ]
                saved = {}
                for ident in historical_ids:
                    saved[ident] = (await view(ident, "summary", history_project))[0]
                save("historical-summaries.json", saved)
                caps = status["symbolic_v1"]["limits"]
                check(
                    "limits unchanged CPU RAM queue",
                    caps["worker_cpu_s"] == 5
                    and caps["worker_wall_s"] == 6
                    and caps["worker_memory_bytes"] == 536870912
                    and caps["concurrent_jobs"] == 2
                    and caps["queue"] == 16,
                )
                matrix["AC16"] = "PASS_BOUNDED_GATES_NOT_FULL_PENTEST"
                if args.patch002:
                    from symbolic_patch002_acceptance import live_checks

                    patch002 = await live_checks(
                        explore, view, call, check, save, compare, project
                    )
                    save("PATCH002_ACCEPTANCE.json", patch002)
                health = await call("service_health", {})
                doctor = await call("assurance_doctor", {})
                save("health.json", health)
                save("doctor.json", doctor)
                check(
                    "SQLite audit and independent approval intact",
                    health["audit"]["ok"]
                    and health["sqlite_integrity"] == "ok"
                    and doctor["execution_permission"] is False
                    and doctor["native_SUTI"] == "NOT_EXECUTED",
                )
                save("ACCEPTANCE_MATRIX.json", matrix)
                result = {
                    "status": "PASS",
                    "checks": len(checks),
                    "acceptance": matrix,
                    "version": init.serverInfo.version,
                    "deployment_id": health["deployment_id"],
                    "project": project,
                    "run_id": first["run_id"],
                    "result_digest": first["result_digest"],
                    "bundle_ref": bundle_ref,
                    "kernel_binding": first["kernel_binding"],
                    "endpoint": args.endpoint,
                    "public_HTTPS_tested": not args.loopback_port,
                    "execution_permission": False,
                }
                save("result.json", result)
                print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--expected-version", default="v0.4.1-developer-preview")
    p.add_argument("--patch002", action="store_true")
    p.add_argument("--loopback-port", type=int)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
