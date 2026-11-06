"""Real MCP FIX-B2 acceptance of original inputs, promotion, baselines and attacks."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from context_promotion_experiment import requests, score
from lm_suti_assurance.core import digest


async def run(a):
    o = a.output
    o.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save(n, v):
        (o / n).write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")

    checks = []
    transcript = []
    project = "qa-fixb2-" + a.tag

    def check(n, ok):
        checks.append({"check": n, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(n)

    auth = authenticate(a.origin, a.password, o / "oauth.private.json", a.loopback_port)
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
                TappedStream(read, o / "wire.jsonl", "server_to_client"),
                TappedStream(write, o / "wire.jsonl", "client_to_server"),
            ) as c:
                init = await c.initialize()
                listing = await c.list_tools()
                save("tools.json", listing.model_dump(mode="json"))
                save("initialize.json", init.model_dump(mode="json"))

                async def call(name, args, error=None):
                    r = await c.call_tool(name, args)
                    transcript.append(
                        {
                            "tool": name,
                            "arguments": args,
                            "response": r.model_dump(mode="json"),
                        }
                    )
                    with (o / "transcript.jsonl").open("a") as f:
                        f.write(json.dumps(transcript[-1], ensure_ascii=False) + "\n")
                    v = r.structuredContent or json.loads(r.content[0].text)
                    check(
                        name + " " + str(len(transcript)),
                        bool(r.isError and v["error"]["code"] == error)
                        if error
                        else not r.isError,
                    )
                    return v if error else v.get("data", v)

                async def section(
                    run, view, tool="white_star_symbolic_observer_inspect", owner=None
                ):
                    out = []
                    offset = 0
                    for _ in range(2048):
                        p = await call(
                            tool,
                            {
                                "project": owner or project,
                                "run_id": run,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if p["requires_artifact"]:
                            raw = []
                            pos = 0
                            for _ in range(1024):
                                block = await call(
                                    tool,
                                    {
                                        "project": owner or project,
                                        "run_id": run,
                                        "view": "artifact",
                                        "artifact_ref": p["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                raw += [
                                    base64.b64decode(x["data_base64"])
                                    for x in block["items"]
                                ]
                                if block["next_offset"] is None:
                                    break
                                pos = block["next_offset"]
                            data = b"".join(raw)
                            check(
                                "artifact SHA",
                                hashlib.sha256(data).hexdigest()
                                == block["artifact_sha256"],
                            )
                            v = json.loads(data)
                            return v if isinstance(v, list) else [v]
                        out += p["items"]
                        if p["next_offset"] is None:
                            return out
                        offset = p["next_offset"]
                    raise AssertionError("unbounded pages")

                manifest = json.loads(a.manifest.read_text())
                history = {}
                for group in ["complex", "observer"]:
                    tool = (
                        "white_star_symbolic_complex_inspect"
                        if group == "complex"
                        else "white_star_symbolic_observer_inspect"
                    )
                    for name, rid in manifest[group].items():
                        row = (
                            await section(rid, "summary", tool, manifest["project"])
                        )[0]
                        original = json.loads(
                            (a.original / (name + ".json")).read_text()
                        )
                        check("immutable original " + name, row == original["record"])
                        history[name] = row
                save("historical-runs.json", history)
                if a.capture_only:
                    save("transcript.json", transcript)
                    save(
                        "result.json",
                        {
                            "status": "PASS",
                            "capture_only": True,
                            "checks": len(checks),
                            "historical_runs": 16,
                        },
                    )
                    return
                check(
                    "actual version/83 tools",
                    init.serverInfo.version == "v0.4.5-developer-preview"
                    and len(listing.tools) == 83,
                )
                before = {
                    t["name"]: t for t in json.loads(a.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                check(
                    "all83 schemas and annotations unchanged",
                    len(before) == 83
                    and all(
                        all(
                            v.get(k) == after[n].get(k)
                            for k in ["inputSchema", "outputSchema", "annotations"]
                        )
                        for n, v in before.items()
                    ),
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "new"}
                )
                await call(
                    "assurance_project_new",
                    {"project": project + "-other", "request_key": "new"},
                )

                async def store(kind, records, key):
                    ds = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": records,
                    }
                    ds["sha256"] = digest(ds)
                    return (
                        await call(
                            "white_star_symbolic_dataset_store",
                            {"project": project, "request_key": key, "dataset": ds},
                        )
                    )["dataset_ref"]

                train = json.loads((a.fixture / "train.json").read_text())
                queries = json.loads((a.fixture / "queries.json").read_text())
                proto = json.loads((a.fixture / "PROTOCOL.json").read_text())
                check(
                    "frozen disjoint labels-free input",
                    digest(train) == proto["train_digest"]
                    and digest(queries) == proto["query_digest"]
                    and all("accepted" not in r for r in queries)
                    and {r["id"] for r in train}.isdisjoint(r["id"] for r in queries),
                )
                tref = await store("train", train, "primary-train")
                qref = await store("queries", queries, "primary-queries")
                configs = requests(a.fixture)
                runs = {}
                evaluations = {}
                models = {}
                for name, q in configs.items():
                    q["task"].update(train_ref=tref, predict_ref=qref)
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {"project": project, "request_key": name, "request": q},
                    )
                    check("completed " + name, row["status"] == "COMPLETED")
                    runs[name] = row
                    models[name] = (await section(row["run_id"], "model"))[0]
                    evaluations[name] = (await section(row["run_id"], "pairwise_eval"))[
                        0
                    ]
                    expected = json.loads((a.offline / (name + ".json")).read_text())[
                        "data"
                    ]
                    check(
                        "exact offline seal/predictions " + name,
                        models[name]["hypothesis_digest"]
                        == expected["model"]["hypothesis_digest"]
                        and evaluations[name] == expected["pairwise_eval"],
                    )
                m = models["promoted"]
                child = next(
                    f for f in m["feature_registry"] if f.get("role") == "PREDICTIVE"
                )
                check(
                    "registered derived actually used",
                    child["feature_id"] in m["used_feature_ids"]
                    and child["origin"] == "DERIVED_FROM_OPERATORS"
                    and child["execution_verified"]
                    and all(x.startswith("derived_") for x in m["enabled_feature_ids"])
                    and child["required_observers"] == [],
                )
                q = copy.deepcopy(configs["promoted"])
                q["feature_policy"]["feature_denylist"].append(
                    child["parent_feature_refs"][0]
                )
                row = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "parent-disabled",
                        "request": q,
                    },
                )
                runs["parent_disabled"] = row
                models["parent_disabled"] = (await section(row["run_id"], "model"))[0]
                evaluations["parent_disabled"] = (
                    await section(row["run_id"], "pairwise_eval")
                )[0]
                check(
                    "parent disable really blocks feature",
                    child["feature_id"]
                    not in models["parent_disabled"]["enabled_feature_ids"]
                    and models["parent_disabled"]["synthesis_status"]
                    == "NO_VERIFIABLE_NEW_OBSERVER",
                )
                verify_args = {
                    "project": project,
                    "run_id": runs["promoted"]["run_id"],
                    "feature_id": child["feature_id"],
                }
                good = await call("white_star_symbolic_observer_verify", verify_args)
                check(
                    "independent CHECKED_INSTANCE",
                    good["status"] == "CHECKED_INSTANCE"
                    and good["verified_witnesses"] == 14
                    and not good["universal_invariant"],
                )
                save("valid-derived-feature.json", child)
                save("independent-verification.json", good)
                rejections = []
                for attack in [
                    "intermediate_output_hash",
                    "source_span",
                    "operator",
                    "origin",
                    "hidden_labels",
                    "parent",
                ]:
                    bad = copy.deepcopy(child)
                    w = next(
                        w
                        for w in bad["construction_trace"]
                        if any("operator" in step for step in w["operator_trace"])
                    )
                    step = next(s for s in w["operator_trace"] if "operator" in s)
                    if attack == "intermediate_output_hash":
                        step["output_word_hashes"][0] = "0" * 64
                    elif attack == "source_span":
                        next(s for s in w["states"].values() if s["source_spans"])[
                            "source_spans"
                        ][0][0][1] += 1
                    elif attack == "operator":
                        step["operator"] = "EVAL"
                    elif attack == "origin":
                        bad["origin"] = "BUILTIN"
                    elif attack == "hidden_labels":
                        bad["promotion_proof"]["heldout_labels"] = {
                            "secret-query": True
                        }
                    else:
                        bad["dependency_features"][0]["origin"] = "BUILTIN"
                    reply = await call(
                        "white_star_symbolic_observer_verify",
                        verify_args | {"certificate": bad},
                    )
                    check("REJECTED " + attack, reply["status"] == "REJECTED")
                    rejections.append({"attack": attack, "response": reply})
                save("hostile-certificates.json", rejections)
                await call(
                    "white_star_symbolic_observer_verify",
                    verify_args | {"project": project + "-other"},
                    "NOT_FOUND",
                )
                leak = copy.deepcopy(queries[:1])
                leak[0]["accepted"] = True
                ds = {
                    "schema": "livingmath-observer-dataset/1",
                    "kind": "queries",
                    "records": leak,
                }
                ds["sha256"] = digest(ds)
                await call(
                    "white_star_symbolic_dataset_store",
                    {"project": project, "request_key": "leak", "dataset": ds},
                    "HELDOUT_LABEL_LEAKAGE",
                )
                repeated = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "promoted",
                        "request": configs["promoted"],
                    },
                )
                check("idempotency", repeated == runs["promoted"])
                altered = copy.deepcopy(configs["promoted"])
                altered["search"]["seed"] += 1
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "promoted", "request": altered},
                    "REQUEST_KEY_CONFLICT",
                )
                # The original negative/smoke scenarios are re-run in the QA workspace.
                mirrored = {}
                for name in manifest["observer"]:
                    old = json.loads((a.original / (name + ".json")).read_text())
                    packet = old["packet"]
                    ref1 = await store(
                        "train",
                        packet["resolved"]["train"],
                        "mirror-" + name + "-train",
                    )
                    ref2 = await store(
                        "queries",
                        packet["resolved"]["queries"],
                        "mirror-" + name + "-query",
                    )
                    request = copy.deepcopy(packet["request"])
                    request["task"].update(train_ref=ref1, predict_ref=ref2)
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "mirror-" + name,
                            "request": request,
                        },
                    )
                    check("mirror completed " + name, row["status"] == "COMPLETED")
                    model = (await section(row["run_id"], "model"))[0]
                    ev = (await section(row["run_id"], "pairwise_eval"))[0]
                    mirrored[name] = {
                        "run": row,
                        "promotion_statistics": model["promotion_statistics"],
                        "used_feature_ids": model["used_feature_ids"],
                        "evaluation": ev,
                    }
                    if name in ["dyck_builtin_ban", "dyck_no_builtins"]:
                        check(
                            "no false universal grammar " + name,
                            model["identifiability_status"] == "UNDERDETERMINED"
                            and model["synthesis_status"]
                            == "NO_VERIFIABLE_NEW_OBSERVER"
                            and model["promotion_statistics"]["failed_obligations"],
                        )
                save("mirrored-original-observers.json", mirrored)
                # All inference is now frozen. Only the external client reads test labels.
                labels = json.loads(
                    (a.fixture / "external-label-holder/labels.json").read_text()
                )
                check(
                    "sealed label digest",
                    digest(labels) == proto["external_labels_digest"],
                )
                scored = {}
                for name, ev in evaluations.items():
                    scored[name] = {
                        str(n): score(
                            [
                                r
                                for r in ev["predictions"]
                                if len(
                                    next(
                                        q for q in queries if q["id"] == r["record_id"]
                                    )["tokens"]
                                )
                                == n
                            ],
                            labels,
                        )
                        for n in [4, 5]
                    }
                check(
                    "48/48 versus effective ablation",
                    scored["promoted"]["4"]["correct"] == 16
                    and scored["promoted"]["5"]["correct"] == 32
                    and scored["no_derivation"]["4"]["correct"] == 5
                    and scored["no_derivation"]["5"]["correct"] == 6,
                )
                save("scores.json", scored)
                save("runs.json", runs)
                save("frozen-model.json", m)
                save("predictions.json", evaluations["promoted"])
                model_again = (await section(runs["promoted"]["run_id"], "model"))[0]
                check("verification cannot mutate frozen rule", model_again == m)

                async def export(
                    run, key, owner=project, tool="white_star_symbolic_observer_inspect"
                ):
                    chunks = await section(run, "export", tool, owner)
                    raw = b"".join(base64.b64decode(x["data_base64"]) for x in chunks)
                    ref = chunks[0]["bundle_ref"]
                    check(key + " export SHA", hashlib.sha256(raw).hexdigest() == ref)
                    (o / (key + ".zip")).write_bytes(raw)
                    replay = await call(
                        "white_star_symbolic_extension_replay",
                        {"project": owner, "bundle_ref": ref},
                    )
                    check(
                        key + " replay",
                        replay["status"] == "REPLAY_MATCH"
                        and replay["journal_hash_chain"] == "PASS",
                    )
                    save(key + "-replay.json", replay)
                    return ref

                exported = await export(runs["promoted"]["run_id"], "promoted-observer")
                oldref = await export(
                    manifest["observer"]["contains_SP_no_builtins_derived"],
                    "old-v044-observer",
                    manifest["project"],
                )
                health = await call("service_health", {})
                doctor = await call("assurance_doctor", {})
                check(
                    "SQLite/audit/no execution grants",
                    health["sqlite_integrity"] == "ok"
                    and health["audit"]["ok"]
                    and not doctor["execution_permission"],
                )
                save("health.json", health)
                result = {
                    "status": "PASS_FINITE_FIX_B2",
                    "version": init.serverInfo.version,
                    "deployment_id": health["deployment_id"],
                    "project": project,
                    "checks": len(checks),
                    "tool_count": len(listing.tools),
                    "original16_runs_preserved": True,
                    "feature_id": child["feature_id"],
                    "parent_feature_id": child["parent_feature_refs"][0],
                    "positive_run_id": runs["promoted"]["run_id"],
                    "hypothesis_digest": m["hypothesis_digest"],
                    "verification_status": good["status"],
                    "bundle_ref": exported,
                    "old_v044_bundle_ref": oldref,
                    "kernel_binding": runs["promoted"]["kernel_binding"],
                    "scores": scored,
                    "promotion_statistics": m["promotion_statistics"],
                    "endpoint": a.endpoint,
                    "public_HTTPS_tested": not bool(a.loopback_port),
                    "execution_permission": False,
                    "universal_invariant": False,
                }
                save("transcript.json", transcript)
                save("result.json", result)
                print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tag", default="capture")
    p.add_argument("--capture-only", action="store_true")
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--fixture", type=Path)
    p.add_argument("--offline", type=Path)
    p.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs/LIVINGMATH_V044_REACCEPTANCE_20261106/RUN_MANIFEST.json",
    )
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
