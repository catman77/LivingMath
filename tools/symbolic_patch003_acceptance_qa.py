"""Actual OAuth/MCP FIX-A/B acceptance, immutable history and approved old replay."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
from itertools import product
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from symbolic_patch003_mcp_qa import sp_request
from lm_suti_assurance.core import digest


def record(word, train=False):
    text = " ".join(word)
    result = {
        "id": digest({"text": text}),
        "tokens": list(word),
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "generated finite equality experiment",
            "edition": "fixed-binary-words/1",
        },
    }
    if train:
        result["accepted"] = word[1] == word[-2]
    return result


def observer_request(tref, qref, derive=True):
    return {
        "schema": "livingmath-symbolic-observer-synthesis-request/1",
        "task": {
            "mode": "context_relation_induction",
            "train_ref": tref,
            "predict_ref": qref,
            "holdout_labels_visible": False,
            "structure_levels": ["word"],
            "candidate_transformations": ["REVERSE"],
        },
        "feature_policy": {
            "enabled_builtins": ["alpha_pattern", "composition"],
            "feature_allowlist": ["derived:*"],
            "feature_denylist": ["pair_0_max", "pair_0_min", "pair_0_final"],
            "prohibit_undocumented_builtins": True,
            "synthesis_origin_required": True,
            "renaming_scope": "per_variant",
            "strict_source_boundaries": True,
            "representation": "literal",
            "derive_relations": derive,
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


async def run(a):
    out = a.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)

    def save(n, v):
        (out / n).write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")

    checks = []
    transcript = []

    def check(n, ok):
        checks.append({"check": n, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(n)

    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
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
                save("tools.json", listing.model_dump(mode="json"))
                save("initialize.json", init.model_dump(mode="json"))

                async def call(name, args, error=None):
                    r = await client.call_tool(name, args)
                    transcript.append(
                        {
                            "tool": name,
                            "arguments": args,
                            "response": r.model_dump(mode="json"),
                        }
                    )
                    with (out / "transcript.jsonl").open("a") as log:
                        log.write(json.dumps(transcript[-1], ensure_ascii=False) + "\n")
                    value = r.structuredContent or json.loads(r.content[0].text)
                    check(
                        name + " " + str(len(transcript)),
                        bool(r.isError and value["error"]["code"] == error)
                        if error
                        else not r.isError,
                    )
                    return value if error else value.get("data", value)

                async def section(
                    run, view, tool="white_star_symbolic_observer_inspect", owner=None
                ):
                    values = []
                    offset = 0
                    for _ in range(2048):
                        page = await call(
                            tool,
                            {
                                "project": owner or project,
                                "run_id": run,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if page["requires_artifact"]:
                            raw = []
                            pos = 0
                            for _ in range(2048):
                                part = await call(
                                    tool,
                                    {
                                        "project": owner or project,
                                        "run_id": run,
                                        "view": "artifact",
                                        "artifact_ref": page["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                raw += [
                                    base64.b64decode(c["data_base64"])
                                    for c in part["items"]
                                ]
                                if part["next_offset"] is None:
                                    break
                                pos = part["next_offset"]
                            else:
                                raise AssertionError("artifact pagination unbounded")
                            data = b"".join(raw)
                            check(
                                "section content SHA",
                                hashlib.sha256(data).hexdigest()
                                == part["artifact_sha256"],
                            )
                            value = json.loads(data)
                            return value if isinstance(value, list) else [value]
                        values += page["items"]
                        if page["next_offset"] is None:
                            return values
                        offset = page["next_offset"]
                    raise AssertionError("pagination unbounded")

                async def export(
                    run, name, tool="white_star_symbolic_observer_inspect", owner=None
                ):
                    rows = await section(run, "export", tool, owner)
                    raw = b"".join(base64.b64decode(c["data_base64"]) for c in rows)
                    ref = rows[0]["bundle_ref"]
                    check(name + " export SHA", hashlib.sha256(raw).hexdigest() == ref)
                    (out / (name + ".zip")).write_bytes(raw)
                    r = await call(
                        "white_star_symbolic_extension_replay",
                        {"project": owner or project, "bundle_ref": ref},
                    )
                    check(
                        name + " actual replay",
                        r["status"] == "REPLAY_MATCH"
                        and r["journal_hash_chain"] == "PASS",
                    )
                    save(name + "-replay.json", r)
                    return ref

                incoming = json.loads(a.run_ids.read_text())
                historical = {}
                # Read-only snapshot of the independent acceptance runs; no mutation/relabeling.
                for group, rows in incoming.items():
                    if group == "dataset_refs":
                        continue
                    tool = (
                        "white_star_symbolic_complex_inspect"
                        if group.startswith("complex_")
                        else "white_star_symbolic_observer_inspect"
                    )
                    for key, ident in rows.items():
                        if ident in historical:
                            continue
                        historical[ident] = (
                            await section(
                                ident, "summary", tool, "whitestar_dialog_test"
                            )
                        )[0]
                save("incoming-historical-runs.json", historical)
                if a.capture_only:
                    save("transcript.json", transcript)
                    save(
                        "result.json",
                        {
                            "status": "PASS",
                            "capture_only": True,
                            "historical_runs": len(historical),
                            "checks": len(checks),
                        },
                    )
                    return
                check(
                    "v0.4.4/83 actual tools",
                    len(listing.tools) == 83
                    and init.serverInfo.version == "v0.4.4-developer-preview",
                )
                baseline = {
                    r["name"]: r for r in json.loads(a.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                check(
                    "all82 prior schemas/annotations unchanged",
                    len(baseline) == 82
                    and all(
                        all(
                            v.get(k) == after[n].get(k)
                            for k in ["inputSchema", "outputSchema", "annotations"]
                        )
                        for n, v in baseline.items()
                    ),
                )
                check(
                    "all19 supplied historical records unchanged",
                    historical == json.loads(a.historical_before.read_text()),
                )
                project = "qa-p003accept-" + a.tag
                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                await call(
                    "assurance_project_new",
                    {"project": project + "-other", "request_key": "init"},
                )
                fix_a = {}
                for n, policy, missing in [
                    (6, "bigons_only", 32),
                    (6, "diamonds_only", 48),
                    (10, "none", 3360),
                ]:
                    result = await call(
                        "white_star_symbolic_complex_analyze",
                        {
                            "project": project,
                            "request_key": "FIX-A-" + policy,
                            "request": sp_request(n, policy),
                        },
                    )
                    s = result["summary"]
                    check(
                        "FIX-A " + policy,
                        s["selected_cells_policy"] == policy
                        and s["partial_attachment"]
                        and s["unresolved_peaks"] == missing
                        and s["pi1_status"] == "NOT_PROVED"
                        and "all_local_peaks_filled" not in s["assumptions"],
                    )
                    fix_a[policy] = result
                save("FIX_A.json", fix_a)
                train = [record(w, True) for w in product("AB", repeat=6)]
                queries = [record(w) for w in product("AB", repeat=8)]
                # Labels exist only here, outside and after the server-visible query data.
                labels = {r["id"]: r["tokens"][1] == r["tokens"][-2] for r in queries}
                check(
                    "FIX-B disjoint train/heldout and no query labels",
                    set(r["id"] for r in train).isdisjoint(labels)
                    and all("accepted" not in r for r in queries),
                )
                refs = {}
                for kind, rows in [("train", train), ("queries", queries)]:
                    ds = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": rows,
                    }
                    ds["sha256"] = digest(ds)
                    refs[kind] = (
                        await call(
                            "white_star_symbolic_dataset_store",
                            {"project": project, "request_key": kind, "dataset": ds},
                        )
                    )["dataset_ref"]
                q = observer_request(refs["train"], refs["queries"])
                positive = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "positive", "request": q},
                )
                repeated = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "positive", "request": q},
                )
                check("same request_key no new operation", repeated == positive)
                model = (await section(positive["run_id"], "model"))[0]
                pred = (await section(positive["run_id"], "pairwise_eval"))[0]
                save("FIX_B_MODEL.json", model)
                save("FIX_B_PREDICTIONS.json", pred)
                feature = next(
                    f
                    for f in model["feature_registry"]
                    if f["feature_id"] in model["used_feature_ids"]
                )
                check(
                    "new non-builtin feature actually used",
                    feature["origin"] == "DERIVED_FROM_OPERATORS"
                    and feature["execution_verified"]
                    and feature["operator_ast"]["offset"] == 1
                    and feature["semantic_alias_of"] is None
                    and feature["feature_id"]
                    not in {
                        f["feature_id"]
                        for f in model["feature_registry"]
                        if f["origin"] == "BUILTIN"
                    },
                )
                check(
                    "pair builtin dependencies disabled",
                    all(x.startswith("derived_") for x in model["enabled_feature_ids"])
                    and all(
                        x not in model["enabled_feature_ids"]
                        for x in ["pair_0_max", "pair_0_min", "pair_0_final"]
                    ),
                )
                args = {
                    "project": project,
                    "run_id": positive["run_id"],
                    "feature_id": feature["feature_id"],
                }
                v = await call("white_star_symbolic_observer_verify", args)
                check(
                    "independent64 full source witnesses",
                    v["status"] == "CHECKED_FINITE_INSTANCE"
                    and v["verified_witnesses"] == 64
                    and v["execution_permission"] is False,
                )
                save("FIX_B_VERIFIER.json", v)
                rejected = []
                for name in [
                    "AST",
                    "output_hash",
                    "unsupported_operator",
                    "source_span",
                ]:
                    bad = copy.deepcopy(feature)
                    bad["construction_trace"] = bad["construction_trace"][:1]
                    if name == "AST":
                        bad["operator_ast"]["left_operations"] = ["REVERSE"]
                    elif name == "output_hash":
                        bad["construction_trace"][0]["operator_trace"][0][
                            "output_word_hashes"
                        ][0] = "0" * 64
                    elif name == "unsupported_operator":
                        bad["construction_trace"][0]["operator_trace"][0][
                            "operator"
                        ] = "EVAL"
                    else:
                        next(
                            v
                            for v in bad["construction_trace"][0]["states"].values()
                            if v["source_spans"]
                        )["source_spans"][0][0][1] += 1
                    row = await call(
                        "white_star_symbolic_observer_verify",
                        args | {"certificate": bad},
                    )
                    check("REJECTED " + name, row["status"] == "REJECTED")
                    rejected.append({"mutation": name, "response": row})
                save("FIX_B_REJECTIONS.json", rejected)
                await call(
                    "white_star_symbolic_observer_verify",
                    args | {"project": project + "-other"},
                    "NOT_FOUND",
                )
                disabled = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "ablation",
                        "request": observer_request(
                            refs["train"], refs["queries"], False
                        ),
                    },
                )
                abl = (await section(disabled["run_id"], "pairwise_eval"))[0]

                def confusion(evaluation):
                    c = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
                    for p in evaluation["predictions"]:
                        truth = labels[p["record_id"]]
                        guess = p["score"] >= 0.5
                        c[
                            "TP"
                            if truth and guess
                            else "FN"
                            if truth
                            else "FP"
                            if guess
                            else "TN"
                        ] += 1
                    return c

                aconf, bconf = confusion(pred), confusion(abl)
                check(
                    "heldout256/256 vs ablated128/256",
                    aconf == {"TP": 128, "TN": 128, "FP": 0, "FN": 0}
                    and bconf["TP"] + bconf["TN"] == 128,
                )
                check(
                    "same train/query budgets in ablation",
                    positive["summary"]["train_records"]
                    == disabled["summary"]["train_records"]
                    == 64
                    and positive["summary"]["query_records"]
                    == disabled["summary"]["query_records"]
                    == 256,
                )
                seal = model["hypothesis_digest"]
                again = (await section(positive["run_id"], "model"))[0]
                check(
                    "frozen hypothesis after independent verification/rejections",
                    again["hypothesis_digest"] == seal,
                )
                newref = await export(positive["run_id"], "FIX-B-positive")
                oldsp = incoming["complex_all_local_peaks"]["4"]
                oldobs = incoming["observer_dyck"]["n8"]
                oldrefs = {}
                oldrefs["SP4"] = await export(
                    oldsp,
                    "old-PATCH003-SP4",
                    "white_star_symbolic_complex_inspect",
                    "whitestar_dialog_test",
                )
                oldrefs["Dyck"] = await export(
                    oldobs,
                    "old-PATCH003-Dyck",
                    "white_star_symbolic_observer_inspect",
                    "whitestar_dialog_test",
                )
                status = await call("bridge_system_status", {})
                check(
                    "old extension installed profile ready",
                    historical[oldsp]["kernel_binding"]
                    in status["historical_extension_replay_bindings"],
                )
                health = await call("service_health", {})
                doctor = await call("assurance_doctor", {})
                check(
                    "SQLite/audit/no execution grants",
                    health["sqlite_integrity"] == "ok"
                    and health["audit"]["ok"]
                    and not doctor["execution_permission"],
                )
                result = {
                    "status": "PASS",
                    "version": init.serverInfo.version,
                    "deployment_id": health["deployment_id"],
                    "project": project,
                    "checks": len(checks),
                    "FIX_A": "PASS",
                    "FIX_B": "PASS_FINITE_CONSTRUCTIVE_DEMONSTRATION",
                    "task": "second/penultimate token equality",
                    "positive_confusion": aconf,
                    "ablation_confusion": bconf,
                    "heldout_records": 256,
                    "positive_run_id": positive["run_id"],
                    "ablation_run_id": disabled["run_id"],
                    "feature_id": feature["feature_id"],
                    "hypothesis_digest": seal,
                    "extension_binding": positive["kernel_binding"],
                    "positive_bundle_ref": newref,
                    "old_profile_bundles": oldrefs,
                    "all19_historical_records_unchanged": True,
                    "endpoint": a.endpoint,
                    "public_HTTPS_tested": not bool(a.loopback_port),
                    "execution_permission": False,
                    "universal_invariant": "NOT_CLAIMED",
                }
                save("transcript.json", transcript)
                save("health.json", health)
                save("result.json", result)
                print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tag", default="capture")
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--historical-before", type=Path)
    p.add_argument(
        "--run-ids",
        type=Path,
        default=ROOT / "docs/LIVINGMATH_PATCH003_ACCEPTANCE_20261106/RUN_IDS.json",
    )
    p.add_argument("--capture-only", action="store_true")
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
