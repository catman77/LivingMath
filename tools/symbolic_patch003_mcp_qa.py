"""Actual MCP acceptance for finite complexes, observers and the frozen real corpus."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from symbolic_patch003_research import request as observer_request, score, query_control


def sp_request(n=6, policy="all_local_peaks"):
    return {
        "schema": "livingmath-symbolic-complex-request/1",
        "complex_source": {
            "kind": "sp_balanced_fixture",
            "max_length": n,
            "rewrite_rules": ["SP_TO_EMPTY", "PS_TO_EMPTY"],
            "edge_identity": "source_position_rule",
        },
        "cells": {"policy": policy, "join_depth_limit": 1},
        "analysis": [
            "graph_cycles",
            "homology_F2",
            "path_coherence",
            "pi1_certificate",
        ],
        "budgets": {
            "max_vertices": 500,
            "max_edges": 2500,
            "max_cells": 5000,
            "max_cpu_ms": 4000,
        },
    }


def lab_record(ident, word, label=None):
    tokens = list(word)
    text = " ".join(tokens)
    r = {
        "id": ident,
        "tokens": tokens,
        "source": {
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "rights": "generated finite mathematical test fixture",
            "edition": "generated/1",
        },
    }
    if label is not None:
        r["accepted"] = label
    return r


def dyck(word):
    value = 0
    for x in word:
        value += 1 if x == "S" else -1
        if value < 0:
            return False
    return value == 0


async def run(args):
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    checks = []
    transcript = []
    runs = {}
    project = "qa-patch003-" + args.tag

    def check(name, ok):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        assert ok, name

    auth = authenticate(
        args.origin, args.password, out / "oauth.private.json", args.loopback_port
    )
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
                TappedStream(read, out / "wire.jsonl", "server_to_client"),
                TappedStream(write, out / "wire.jsonl", "client_to_server"),
            ) as client:
                init = await client.initialize()
                listing = await client.list_tools()
                save("initialize.json", init.model_dump(mode="json"))
                save("tools.json", listing.model_dump(mode="json"))
                check(
                    "actual tool count/version",
                    len(listing.tools) == args.expected_tool_count
                    and init.serverInfo.version == args.expected_version,
                )
                before = {
                    t["name"]: t for t in json.loads(args.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                check(
                    "all75 previous input/output schemas and annotations exact",
                    all(
                        all(
                            before[n].get(k) == after[n].get(k)
                            for k in ["inputSchema", "outputSchema", "annotations"]
                        )
                        for n in before
                    ),
                )

                async def call(name, arguments, error=None):
                    result = await client.call_tool(name, arguments)
                    transcript.append(
                        {
                            "tool": name,
                            "arguments": arguments,
                            "response": result.model_dump(mode="json"),
                        }
                    )
                    with (out / "transcript.jsonl").open("a") as log:
                        log.write(json.dumps(transcript[-1], ensure_ascii=False) + "\n")
                    value = result.structuredContent or json.loads(
                        result.content[0].text
                    )
                    if error:
                        check(
                            name + " expected " + error,
                            result.isError and value["error"]["code"] == error,
                        )
                    else:
                        check(name + " " + str(len(transcript)), not result.isError)
                    return value if error else value.get("data", value)

                async def section(
                    run_id,
                    view,
                    tool="white_star_symbolic_complex_inspect",
                    owner=project,
                ):
                    values = []
                    offset = 0
                    for _ in range(2048):
                        page = await call(
                            tool,
                            {
                                "project": owner,
                                "run_id": run_id,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if page["requires_artifact"]:
                            chunks = []
                            start = 0
                            for _ in range(1024):
                                block = await call(
                                    tool,
                                    {
                                        "project": owner,
                                        "run_id": run_id,
                                        "view": "artifact",
                                        "artifact_ref": page["artifact_ref"],
                                        "offset": start,
                                        "limit": 128,
                                    },
                                )
                                chunks += block["items"]
                                if block["next_offset"] is None:
                                    break
                                start = block["next_offset"]
                            else:
                                raise AssertionError("artifact pagination unbounded")
                            raw = b"".join(
                                base64.b64decode(c["data_base64"]) for c in chunks
                            )
                            value = json.loads(raw)
                            return value if isinstance(value, list) else [value]
                        values += page["items"]
                        if page["next_offset"] is None:
                            return values
                        offset = page["next_offset"]
                    raise AssertionError("pagination unbounded")

                async def explore(q, key):
                    row = await call(
                        "white_star_symbolic_complex_analyze",
                        {"project": project, "request_key": key, "request": q},
                    )
                    check(key + " completed", row["status"] == "COMPLETED")
                    runs[key] = row
                    return row

                async def export(run, key, tool="white_star_symbolic_complex_inspect"):
                    parts = await section(run, "export", tool)
                    raw = b"".join(base64.b64decode(c["data_base64"]) for c in parts)
                    ref = parts[0]["bundle_ref"]
                    check(
                        key + " actual export SHA",
                        hashlib.sha256(raw).hexdigest() == ref,
                    )
                    (out / (key + ".zip")).write_bytes(raw)
                    replay = await call(
                        "white_star_symbolic_extension_replay",
                        {"project": project, "bundle_ref": ref},
                    )
                    check(
                        key + " real replay",
                        replay["status"] == "REPLAY_MATCH"
                        and replay["journal_hash_chain"] == "PASS",
                    )
                    return ref, replay

                counter = [0]

                async def store(kind, records, key):
                    refs = []
                    batch = []

                    async def commit(records):
                        data = {
                            "schema": "livingmath-observer-dataset/1",
                            "kind": kind,
                            "records": records,
                        }
                        data["sha256"] = digest(data)
                        counter[0] += 1
                        result = await call(
                            "white_star_symbolic_dataset_store",
                            {
                                "project": project,
                                "request_key": key + "-" + str(counter[0]),
                                "dataset": data,
                            },
                        )
                        refs.append(result["dataset_ref"])

                    for record in records:
                        candidate = batch + [record]
                        if batch and (
                            len(candidate) > 256
                            or len(
                                json.dumps(
                                    candidate, ensure_ascii=False, separators=(",", ":")
                                ).encode()
                            )
                            > 220000
                        ):
                            await commit(batch)
                            batch = []
                        batch.append(record)
                    if batch:
                        await commit(batch)
                    if len(refs) == 1:
                        return refs[0]
                    data = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": "collection",
                        "parts": refs,
                        "record_kind": kind,
                    }
                    data["sha256"] = digest(data)
                    row = await call(
                        "white_star_symbolic_dataset_store",
                        {
                            "project": project,
                            "request_key": key + "-collection",
                            "dataset": data,
                        },
                    )
                    check(
                        key + " all records registered",
                        row["record_count"] == len(records),
                    )
                    return row["dataset_ref"]

                status = await call("bridge_system_status", {})
                save("root-status.json", status)
                check(
                    "new true READY capabilities",
                    all(
                        status[n]["status"] == "READY"
                        for n in [
                            "symbolic_complex_v1",
                            "observer_synthesis_v1",
                            "pairwise_context_v1",
                        ]
                    ),
                )
                check(
                    "old symbolic binding unchanged",
                    status["symbolic_v1"]["kernel_binding"]
                    == "7ce5c5ba0620b4dad1b3f1b62b2cba3338a1efb4a7852a6e1bf768fe5fd0a0c9",
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "new"}
                )
                expected = {
                    2: (3, 2, 0, 0, 0),
                    4: (9, 14, 6, 8, 6),
                    6: (29, 74, 46, 80, 46),
                    8: (99, 354, 256, 560, 256),
                    10: (351, 1614, 1264, 3360, 1264),
                }
                for n, count in expected.items():
                    row = await explore(sp_request(n), "sp-" + str(n))
                    s = row["summary"]
                    check(
                        "SP2C counts N" + str(n),
                        tuple(
                            s[k]
                            for k in [
                                "vertices",
                                "edges",
                                "graph_beta1",
                                "verified_cells",
                                "rank_d2_F2",
                            ]
                        )
                        == count
                        and s["dim_H1_F2"] == 0,
                    )
                    verified = await call(
                        "white_star_symbolic_complex_verify",
                        {
                            "project": project,
                            "run_id": row["run_id"],
                            "certificate_ref": row["section_refs"]["paths"],
                        },
                    )
                    check(
                        "SP independent proof N" + str(n),
                        verified["status"] == "CHECKED_INSTANCE"
                        and verified["pi1_status"] == "PROVED_TRIVIAL_WITH_CERTIFICATE",
                    )
                primary = runs["sp-10"]
                again = await explore(sp_request(10), "sp-10")
                check("same request key returns exact row", again == primary)
                replica = await explore(sp_request(10), "sp-10-replica")
                check(
                    "distinct key same result digest",
                    replica["run_id"] != primary["run_id"]
                    and replica["result_digest"] == primary["result_digest"],
                )
                for policy in ["none", "bigons_only", "diamonds_only"]:
                    row = await explore(sp_request(10, policy), "sp-" + policy)
                    check(
                        policy + " no false pi1",
                        row["summary"]["pi1_status"] == "NOT_PROVED",
                    )
                    if policy == "none":
                        check(
                            "graph pi1 free rank1264",
                            row["summary"]["dim_H1_F2"]
                            == row["summary"]["graph_beta1"]
                            == 1264,
                        )
                small = runs["sp-4"]
                proof = (await section(small["run_id"], "paths"))[0]
                bad = copy.deepcopy(proof)
                bad["lemmas"][0]["dependencies"] = [bad["lemmas"][0]["edge_id"]]
                rejected = await call(
                    "white_star_symbolic_complex_verify",
                    {
                        "project": project,
                        "run_id": small["run_id"],
                        "certificate": {"paths": bad},
                    },
                )
                check(
                    "tampered proof REJECTED with obligations",
                    rejected["status"] == "REJECTED" and rejected["failed_obligations"],
                )
                absent = await call(
                    "white_star_symbolic_complex_verify",
                    {
                        "project": project,
                        "run_id": small["run_id"],
                        "certificate": {"paths": None},
                    },
                )
                check("missing proof NOT_PROVED", absent["status"] == "NOT_PROVED")
                edges = await section(small["run_id"], "edges")
                edges[0]["match_span"]["token_start"] = 99
                badedge = await call(
                    "white_star_symbolic_complex_verify",
                    {
                        "project": project,
                        "run_id": small["run_id"],
                        "certificate": {"edges": edges},
                    },
                )
                check("bad position rejected", badedge["status"] == "REJECTED")
                invalid = sp_request(11)
                await call(
                    "white_star_symbolic_complex_analyze",
                    {"project": project, "request_key": "bad-n", "request": invalid},
                    "INVALID_INPUT",
                )
                invalid = sp_request(10)
                invalid["budgets"]["max_vertices"] = 5
                await call(
                    "white_star_symbolic_complex_analyze",
                    {
                        "project": project,
                        "request_key": "low-budget",
                        "request": invalid,
                    },
                    "BUDGET_EXCEEDED",
                )
                await call(
                    "assurance_project_new",
                    {"project": project + "-other", "request_key": "new"},
                )
                await call(
                    "white_star_symbolic_complex_inspect",
                    {
                        "project": project + "-other",
                        "run_id": primary["run_id"],
                        "view": "summary",
                    },
                    "NOT_FOUND",
                )
                complex_ref, replayed = await export(primary["run_id"], "sp-10")
                save("sp-replay.json", replayed)
                from itertools import product

                train = [
                    lab_record("t" + str(i), w, dyck(w))
                    for i, w in enumerate(
                        [
                            w
                            for n in [2, 4, 6]
                            for w in product("SP", repeat=n)
                            if w.count("S") == w.count("P")
                        ]
                    )
                ]
                words = [
                    w
                    for n in [8, 10]
                    for w in product("SP", repeat=n)
                    if w.count("S") == w.count("P")
                ]
                queries = [lab_record("q" + str(i), w) for i, w in enumerate(words)]
                tref = await store("train", train, "dyck-train")
                qref = await store("queries", queries, "dyck-queries")
                q = observer_request("literal")
                q["task"].update(
                    train_ref=tref,
                    predict_ref=qref,
                    candidate_transformations=["REVERSE"],
                    conflict_policy="report_only",
                )
                response = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "dyck", "request": q},
                )
                runs["dyck"] = response
                check(
                    "Dyck full train28 test322",
                    response["summary"]["train_records"] == 28
                    and response["summary"]["query_records"] == 322,
                )
                model = (
                    await section(
                        response["run_id"],
                        "model",
                        "white_star_symbolic_observer_inspect",
                    )
                )[0]
                pred = (
                    await section(
                        response["run_id"],
                        "pairwise_eval",
                        "white_star_symbolic_observer_inspect",
                    )
                )[0]
                save("dyck-model.json", model)
                save("dyck-predictions.json", pred)
                check(
                    "70+252 blind decisions exact",
                    all(
                        (p["score"] >= 0.5) == dyck(w)
                        for p, w in zip(pred["predictions"], words)
                    ),
                )
                f = next(
                    f
                    for f in model["feature_registry"]
                    if f["feature_id"] == "pair_0_max"
                )
                check(
                    "pair_0_max honestly BUILTIN",
                    f["origin"] == "BUILTIN"
                    and f["construction_trace"] is None
                    and f["source_code_binding_sha256"],
                )
                check(
                    "grammar remains underdetermined",
                    model["identifiability_status"] == "UNDERDETERMINED",
                )
                repeated = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "dyck", "request": q},
                )
                check("observer idempotency", repeated == response)
                changed = copy.deepcopy(q)
                changed["search"]["seed"] += 1
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "dyck", "request": changed},
                    "REQUEST_KEY_CONFLICT",
                )
                forged = {
                    "schema": "livingmath-observer-dataset/1",
                    "kind": "queries",
                    "records": [lab_record("leak", "SP", True)],
                }
                forged["sha256"] = digest(forged)
                await call(
                    "white_star_symbolic_dataset_store",
                    {"project": project, "request_key": "leak", "dataset": forged},
                    "HELDOUT_LABEL_LEAKAGE",
                )
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project + "-other",
                        "request_key": "cross",
                        "request": q,
                    },
                    "NOT_FOUND",
                )
                ablations = {}
                for enabled in ["literal", "alpha_pattern", "adjacency"]:
                    masked = copy.deepcopy(q)
                    masked["feature_policy"].update(
                        enabled_builtins=[enabled], derive_relations=False
                    )
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "ablate-" + enabled,
                            "request": masked,
                        },
                    )
                    m = (
                        await section(
                            row["run_id"],
                            "model",
                            "white_star_symbolic_observer_inspect",
                        )
                    )[0]
                    p = (
                        await section(
                            row["run_id"],
                            "pairwise_eval",
                            "white_star_symbolic_observer_inspect",
                        )
                    )[0]
                    check(
                        enabled + " no hidden pair features",
                        all(
                            not name.startswith("pair_")
                            for name in m["enabled_feature_ids"]
                        ),
                    )
                    ablations[enabled] = {
                        "model": m,
                        "correct": sum(
                            (r["score"] >= 0.5) == dyck(w)
                            for r, w in zip(p["predictions"], words)
                        ),
                        "total": 322,
                    }
                save("feature-ablation.json", ablations)
                observer_ref, _ = await export(
                    response["run_id"], "dyck", "white_star_symbolic_observer_inspect"
                )
                research = {}
                if args.frozen:
                    train = json.loads((args.frozen / "train.json").read_text())
                    queries = json.loads((args.frozen / "queries.json").read_text())
                    tref = await store("train", train, "corpus-train")
                    qref = await store("queries", queries, "corpus-queries")
                    configs = json.loads(
                        (args.research / "FROZEN_CONFIGURATIONS.json").read_text()
                    )
                    for name, template in configs.items():
                        q = copy.deepcopy(template)
                        q["task"].update(train_ref=tref, predict_ref=qref)
                        if name in [
                            "renaming_control",
                            "boundary_control",
                            "provenance_control",
                        ]:
                            altered, _ = query_control(queries, name)
                            q["task"]["predict_ref"] = await store(
                                "queries", altered, name
                            )
                        row = await call(
                            "white_star_symbolic_observer_synthesize",
                            {
                                "project": project,
                                "request_key": "corpus-" + name,
                                "request": q,
                            },
                        )
                        runs["corpus-" + name] = row
                        evaluation = (
                            await section(
                                row["run_id"],
                                "pairwise_eval",
                                "white_star_symbolic_observer_inspect",
                            )
                        )[0]
                        expected = json.loads(
                            (args.research / (name + ".artifacts.json")).read_text()
                        )
                        check(
                            name + " exact offline model seal and predictions",
                            row["summary"]["hypothesis_digest"]
                            == expected["model"]["hypothesis_digest"]
                            and evaluation == expected["pairwise_eval"],
                        )
                        save("corpus-" + name + "-evaluation.json", evaluation)
                        research[name] = {
                            "run_id": row["run_id"],
                            "summary": row["summary"],
                            "evaluation": evaluation,
                        }
                        if name == "global_alpha":
                            _, r = await export(
                                row["run_id"],
                                "corpus-global-alpha",
                                "white_star_symbolic_observer_inspect",
                            )
                            save("corpus-replay.json", r)
                    # The server never receives this label file; grading happens only here.
                    labels = json.loads(
                        (args.frozen / "external-label-holder/labels.json").read_text()
                    )
                    for name, data in research.items():
                        mapping = json.loads(
                            (args.research / (name + ".label-map.json")).read_text()
                        )
                        data["scores"] = score(
                            data["evaluation"],
                            {new: labels[old] for new, old in mapping.items()},
                        )
                        data.pop("evaluation")
                    save("nostradamus-results.json", research)
                health = await call("service_health", {})
                doctor = await call("assurance_doctor", {})
                save("health.json", health)
                save("doctor.json", doctor)
                check(
                    "SQLite and canonical audit healthy",
                    health["sqlite_integrity"] == "ok" and health["audit"]["ok"],
                )
                check(
                    "no approval escalation",
                    doctor["execution_permission"] is False
                    and doctor["native_SUTI"] == "NOT_EXECUTED",
                )
                save("runs.json", runs)
                result = {
                    "status": "PASS",
                    "checks": len(checks),
                    "project": project,
                    "version": init.serverInfo.version,
                    "deployment_id": health["deployment_id"],
                    "tool_count": len(listing.tools),
                    "P0": "ACCEPTED_P0",
                    "P1": "ACCEPTED_P1",
                    "P2": "RESEARCH_COMPLETED_P2" if research else "NOT_RUN",
                    "complex_run_id": primary["run_id"],
                    "complex_bundle_ref": complex_ref,
                    "observer_run_id": response["run_id"],
                    "observer_bundle_ref": observer_ref,
                    "old_symbolic_binding": status["symbolic_v1"]["kernel_binding"],
                    "extension_binding": status["symbolic_complex_v1"][
                        "kernel_binding"
                    ],
                    "endpoint": args.endpoint,
                    "public_HTTPS_tested": not bool(args.loopback_port),
                    "execution_permission": False,
                }
                save("transcript.json", transcript)
                save("result.json", result)
                print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--expected-tool-count", type=int, default=82)
    p.add_argument("--expected-version", default="v0.4.3-developer-preview")
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--frozen", type=Path)
    p.add_argument("--research", type=Path)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
