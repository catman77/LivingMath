"""Actual OAuth/MCP role acceptance and set-valued finite continuation experiments."""

import argparse, asyncio, base64, copy, hashlib, itertools, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest
from recursive_observer_experiment import request, score
from role006_fixture import record

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream


def normalize(schema):
    out = copy.deepcopy(schema)
    p = out["white_star_symbolic_observer_synthesize"]["inputSchema"]["properties"][
        "request"
    ]["properties"]["promotion_policy"]["properties"]
    p["mode"]["enum"].remove("role_branching_ast")
    for n in ["role_max_tokens", "role_max_cells", "role_max_split_trials"]:
        p.pop(n)
    out["white_star_symbolic_observer_verify"]["inputSchema"]["properties"].pop(
        "query_id"
    )
    return out


async def run(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save(n, v):
        (out / n).write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")

    checks = []
    calls = []
    runs = {}
    models = {}
    preds = {}
    configs = {}

    def check(n, ok):
        checks.append({"check": n, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(n)

    protocol = json.loads((a.fixture / "PROTOCOL.json").read_text())
    raw = (a.fixture / "inputs.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == protocol["files"]["inputs.json"]
    data = json.loads(raw)
    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    project = "qa-role006-" + a.tag
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
                save("initialize.json", init.model_dump(mode="json"))
                save("tools.json", listing.model_dump(mode="json"))
                check("server version actual", init.serverInfo.version == a.version)

                async def call(name, args, error=None):
                    r = await client.call_tool(name, args)
                    c = {
                        "tool": name,
                        "arguments": args,
                        "response": r.model_dump(mode="json"),
                    }
                    calls.append(c)
                    with (out / "transcript.jsonl").open("a") as f:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                    v = r.structuredContent or json.loads(r.content[0].text)
                    check(
                        name
                        + " "
                        + str(len(calls))
                        + (" expected " + error if error else ""),
                        bool(r.isError and v.get("error", {}).get("code") == error)
                        if error
                        else not r.isError,
                    )
                    return v.get("data", v)

                async def section(rid, view, owner=None):
                    items = []
                    offset = 0
                    for _ in range(4096):
                        p = await call(
                            "white_star_symbolic_observer_inspect",
                            {
                                "project": owner or project,
                                "run_id": rid,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if p.get("requires_artifact"):
                            raw = []
                            pos = 0
                            for _ in range(4096):
                                c = await call(
                                    "white_star_symbolic_observer_inspect",
                                    {
                                        "project": owner or project,
                                        "run_id": rid,
                                        "view": "artifact",
                                        "artifact_ref": p["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                raw.extend(
                                    base64.b64decode(x["data_base64"])
                                    for x in c["items"]
                                )
                                if c["next_offset"] is None:
                                    break
                                pos = c["next_offset"]
                            raw = b"".join(raw)
                            check(
                                "complete artifact SHA",
                                hashlib.sha256(raw).hexdigest() == c["artifact_sha256"],
                            )
                            v = json.loads(raw)
                            return v if isinstance(v, list) else [v]
                        items += p["items"]
                        if p["next_offset"] is None:
                            return items
                        offset = p["next_offset"]
                    raise AssertionError("page bound")

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
                comp = after if a.phase == "baseline" else normalize(after)
                check(
                    "83 schemas preserved except declared additive role inputs",
                    len(comp) == len(before) == 83
                    and all(
                        all(
                            comp[n][k] == v[k]
                            for k in ["inputSchema", "outputSchema", "annotations"]
                        )
                        for n, v in before.items()
                    ),
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                tr = await store("train", data["train"], "train84")
                q8 = await store("queries", data["queries"], "holdout8")
                minimal = await store("train", data["minimal"], "minimal")
                branch = await store("train", data["branch_train"], "branch")
                probe = await store("queries", data["probes"], "probes")
                check(
                    "exact provided sealed source refs preserved",
                    tr == protocol["source_train_ref"]
                    and q8 == protocol["source_query_ref"],
                )

                def config(trainref, queryref, seed=137):
                    q = request(seed)
                    q["promotion_policy"]["mode"] = (
                        "compositional_ast"
                        if a.phase == "baseline"
                        else "role_branching_ast"
                    )
                    q["promotion_policy"]["candidate_sources"] = ["derivation_trace"]
                    q["task"].update(train_ref=trainref, predict_ref=queryref)
                    return q

                async def synth(key, q, read_model=True):
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {"project": project, "request_key": key, "request": q},
                    )
                    check("completed " + key, row["status"] == "COMPLETED")
                    runs[key] = row
                    configs[key] = q
                    save("runs.json", runs)
                    m = (
                        (await section(row["run_id"], "model"))[0]
                        if read_model
                        else None
                    )
                    p = (await section(row["run_id"], "pairwise_eval"))[0][
                        "predictions"
                    ]
                    preds[key] = p
                    if m is not None:
                        models[key] = m
                    return row, m, p

                async def verify(key, feature, query=None, certificate=None):
                    args = {
                        "project": project,
                        "run_id": runs[key]["run_id"],
                        "feature_id": feature["feature_id"],
                    }
                    if query is not None:
                        args["query_id"] = query
                    if certificate is not None:
                        args["certificate"] = certificate
                    return await call("white_star_symbolic_observer_verify", args)

                def feature(m):
                    return next(
                        f
                        for f in m["feature_registry"]
                        if f["feature_id"] in m["used_feature_ids"]
                    )

                if a.phase == "baseline":
                    _, m, _ = await synth("old84", config(tr, q8))
                    d = m["composition_diagnostics"]["candidate_generation"]
                    check(
                        "old equality catalog18 and zero compatible",
                        d["seen"] == 18 and d["train_compatible"] == 0,
                    )
                    for seed in [7, 137, 991]:
                        _, m, _ = await synth(
                            "old-minimal-" + str(seed), config(minimal, probe, seed)
                        )
                        d = m["composition_diagnostics"]["candidate_generation"]
                        check(
                            "old minimal catalog10 and zero compatible",
                            d["seen"] == 10 and d["train_compatible"] == 0,
                        )
                elif a.phase == "accept":
                    for seed in [7, 137, 991]:
                        row, m, p = await synth(
                            "minimal-" + str(seed), config(minimal, probe, seed)
                        )
                        f = feature(m)
                        check(
                            "oriented minimal with rivals",
                            f["operator_ast"]["roles"] == {"OPEN": "S", "CLOSE": "P"}
                            and m["role_diagnostics"]["catalog"]["compatible"] > 1
                            and any(
                                x["counterexamples"]
                                for x in m["role_diagnostics"]["candidates"]
                            ),
                        )
                        v = await verify("minimal-" + str(seed), f)
                        check("independent minimal", v["status"] == "CHECKED_INSTANCE")
                    row, m, p = await synth("branch", config(branch, probe))
                    bf = feature(m)
                    bp = await verify("branch", bf, data["probes"][2]["id"])
                    check(
                        "two actual nonempty branches",
                        bp["status"] == "CHECKED_INSTANCE"
                        and [c["tokens"] for c in bp["certificate"]["tree"]["children"]]
                        == [list("SP"), list("SP")],
                    )
                    save("TWO_BRANCH_PROOF.json", bp)
                    for seed in [137, 42]:
                        _, m, p = await synth("full-" + str(seed), config(tr, q8, seed))
                        f = feature(m)
                        v = await verify("full-" + str(seed), f)
                        check(
                            "full84 independent and finite",
                            v["status"] == "CHECKED_INSTANCE"
                            and v["verified_witnesses"] == 84
                            and f["claim_status"] == "CHECKED_FINITE_INSTANCE"
                            and not f["known_invariance_scope"]["universal_invariant"]
                            and m["identifiability_status"] == "UNDERDETERMINED",
                        )
                        save("VERIFIED_" + str(seed) + ".json", v)
                    full = feature(models["full-137"])
                    check(
                        "two seeds same role program",
                        full["operator_ast_digest"]
                        == feature(models["full-42"])["operator_ast_digest"],
                    )
                    _, pm, _ = await synth("full-probes", config(tr, probe))
                    pf = feature(pm)
                    check(
                        "freeze independent of queries",
                        pm["hypothesis_digest"]
                        == models["full-137"]["hypothesis_digest"],
                    )
                    negative = await verify("full-probes", pf, data["probes"][1]["id"])
                    positive = await verify("full-probes", pf, data["probes"][2]["id"])
                    check(
                        "fixed roles distinguish SP PS",
                        negative["verification"]["decision"] is False
                        and positive["verification"]["decision"] is True,
                    )
                    save("NEGATIVE_PROOF.json", negative)
                    attacks = {}
                    for name in [
                        "role",
                        "split",
                        "missing_second_branch",
                        "SHA",
                        "NF",
                        "negative_DP",
                        "missing_cell",
                    ]:
                        c = copy.deepcopy(
                            negative["certificate"]
                            if name in ["negative_DP", "missing_cell"]
                            else positive["certificate"]
                        )
                        if name == "role":
                            c["tree"]["roles"][0]["role"] = "CLOSE"
                        elif name == "split":
                            c["tree"]["trace"][0]["args"]["position"] += 1
                        elif name == "missing_second_branch":
                            c["tree"]["children"].pop()
                        elif name == "SHA":
                            c["source_sha256"] = "0" * 64
                        elif name == "NF":
                            c["tree"] = {"normal_form": []}
                        elif name == "negative_DP":
                            c["cells"][-1]["value"] = True
                        else:
                            c["cells"].pop()
                        v = await verify(
                            "full-probes",
                            pf,
                            data["probes"][
                                1 if name in ["negative_DP", "missing_cell"] else 2
                            ]["id"],
                            c,
                        )
                        check("tamper " + name, v["status"] == "REJECTED")
                        attacks[name] = v
                    # Rehash both feature wrappers after corrupting a negative interval equation.
                    bad = copy.deepcopy(bf)
                    w = next(
                        w
                        for w in bad["construction_trace"]
                        if not w["proof"]["decision"]
                    )
                    w["proof"]["cells"][-1]["value"] = True
                    bad["witness_set_digest"] = digest(bad["construction_trace"])
                    bad["digest"] = digest(
                        {k: v for k, v in bad.items() if k != "digest"}
                    )
                    v = await verify("branch", bf, certificate=bad)
                    check(
                        "rehashed semantic negative tamper rejected",
                        v["status"] == "REJECTED",
                    )
                    attacks["rehashed_feature"] = v
                    for name in ["origin", "universal"]:
                        c = copy.deepcopy(bf)
                        if name == "origin":
                            c["origin"] = "BUILTIN"
                        else:
                            c["known_invariance_scope"]["universal_invariant"] = True
                        c["witness_set_digest"] = digest(c["construction_trace"])
                        c["digest"] = digest(
                            {k: v for k, v in c.items() if k != "digest"}
                        )
                        v = await verify("branch", bf, certificate=c)
                        check("feature tamper " + name, v["status"] == "REJECTED")
                        attacks[name] = v

                    # Covariant renaming learned afresh from actual UTF8 train, not a supplied AST.
                    def renamed(rows):
                        return [
                            record(
                                ["кот" if t == "S" else "лес" for t in r["tokens"]],
                                r.get("accepted"),
                                "u",
                            )
                            for r in rows
                        ]

                    ut = await store("train", renamed(data["train"]), "unicode-train")
                    uq = await store(
                        "queries", renamed(data["queries"]), "unicode-queries"
                    )
                    up = await store(
                        "queries", renamed(data["probes"]), "unicode-probes"
                    )
                    _, um, _ = await synth("unicode", config(ut, uq))
                    uf = feature(um)
                    check(
                        "data-learned Unicode roles",
                        uf["operator_ast"]["roles"] == {"OPEN": "кот", "CLOSE": "лес"},
                    )
                    _, ump, _ = await synth("unicode-probes", config(ut, up))
                    upf = feature(ump)
                    v = await verify(
                        "unicode-probes", upf, renamed(data["probes"])[2]["id"]
                    )
                    c = copy.deepcopy(v["certificate"])
                    c["input_state"]["source_spans"][0][0][2] -= 1
                    z = await verify(
                        "unicode-probes", upf, renamed(data["probes"])[2]["id"], c
                    )
                    check(
                        "actual UTF8 span corruption rejected",
                        z["status"] == "REJECTED",
                    )
                    attacks["UTF8"] = z
                    save("REJECTED_CERTIFICATES.json", attacks)
                    q = config(tr, q8)
                    q["feature_policy"]["derive_relations"] = False
                    _, m, _ = await synth("no-derive", q)
                    check("no derive effective", not m["used_feature_ids"])
                    for token in [
                        full["feature_id"],
                        "primitive:ATOM_ROLE",
                        "primitive:BRANCH_AND",
                    ]:
                        q = config(tr, q8)
                        q["feature_policy"]["feature_denylist"].append(token)
                        _, m, _ = await synth("deny-" + token.replace(":", "-"), q)
                        check("deny effective " + token, not m["used_feature_ids"])
                    q = config(minimal, probe)
                    q["promotion_policy"]["role_max_cells"] = 6
                    _, m, p = await synth("cell-bound", q)
                    check(
                        "query cell bound yields UNKNOWN",
                        p[2]["score"] is None and p[2]["status"] == "UNKNOWN",
                    )
                    v = await verify("cell-bound", feature(m), data["probes"][2]["id"])
                    check("budget proof not CHECKED", v["status"] == "UNKNOWN")
                    q = config(tr, q8)
                    q["promotion_policy"]["max_recursion_steps"] = 3
                    _, m, p = await synth("depth-bound", q)
                    check(
                        "depth limit never False",
                        all(x["score"] is None and x["status"] == "UNKNOWN" for x in p),
                    )
                    q = config(tr, q8)
                    q["search"]["max_proposals"] = 1
                    _, m, _ = await synth("proposal-bound", q)
                    check(
                        "untried catalog explicit",
                        m["role_diagnostics"]["catalog"]["search_status"]
                        == "BOUNDED_SEARCH_INCOMPLETE"
                        and m["role_diagnostics"]["catalog"]["untried_ast_digests"],
                    )
                    same = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "full-137",
                            "request": configs["full-137"],
                        },
                    )
                    fresh = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "fresh-identical",
                            "request": configs["full-137"],
                        },
                    )
                    check(
                        "key and content idempotency",
                        same["run_id"] == runs["full-137"]["run_id"]
                        and fresh["run_id"] != same["run_id"]
                        and fresh["result_digest"] == same["result_digest"],
                    )
                    other = project + "-other"
                    await call(
                        "assurance_project_new",
                        {"project": other, "request_key": "init"},
                    )
                    await call(
                        "white_star_symbolic_observer_verify",
                        {
                            "project": other,
                            "run_id": runs["full-137"]["run_id"],
                            "feature_id": full["feature_id"],
                        },
                        "NOT_FOUND",
                    )
                    leak = copy.deepcopy(data["queries"][:1])
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
                    chunks = await section(runs["full-137"]["run_id"], "export")
                    raw = b"".join(base64.b64decode(c["data_base64"]) for c in chunks)
                    ref = chunks[0]["bundle_ref"]
                    check("export hash", hashlib.sha256(raw).hexdigest() == ref)
                    (out / "role-full.zip").write_bytes(raw)
                    v = await call(
                        "white_star_symbolic_extension_replay",
                        {"project": project, "bundle_ref": ref},
                    )
                    check(
                        "role replay exact",
                        v["status"] == "REPLAY_MATCH"
                        and v["journal_hash_chain"] == "PASS",
                    )
                    save("REPLAY.json", v)
                else:
                    # Same training/configuration for every block. All8191 concatenations are measured.
                    seals = []
                    decisions = {}
                    proof_statuses = set()
                    for offset in range(0, len(data["continuations"]), a.batch_size):
                        batch = data["continuations"][offset : offset + a.batch_size]
                        ref = await store("queries", batch, "p1-query-" + str(offset))
                        q = config(tr, ref)
                        q["promotion_policy"]["role_max_tokens"] = 12
                        row, m, p = await synth("p1-" + str(offset), q, offset == 0)
                        seal = row["summary"]["hypothesis_digest"]
                        seals.append(seal)
                        if offset == 0:
                            save("FROZEN_MODEL.json", m)
                        for r, item in zip(batch, p):
                            check(
                                "finite continuation observed " + r["id"],
                                item["score"] is not None
                                and item["status"] == "PREDICTION"
                                and item.get("operator_evidence")
                                and all(
                                    x["independent_status"] == "CHECKED_INSTANCE"
                                    for x in item["operator_evidence"]
                                ),
                            )
                            decisions["".join(r["tokens"])] = {
                                "accepted": item["score"] >= 0.5,
                                "record_id": r["id"],
                                "source_sha256": r["source"]["sha256"],
                                "run_id": row["run_id"],
                                "proof_digest": item["operator_evidence"][0][
                                    "execution_witness_digest"
                                ],
                            }
                        save("OBSERVATIONS.json", decisions)
                    check(
                        "one frozen P1 hypothesis across batches", len(set(seals)) == 1
                    )
                    check("8191 distinct words measured", len(decisions) == 8191)
                    horizons = {}
                    for n in range(1, 7):
                        words = [
                            "".join(w)
                            for k in range(n + 1)
                            for w in itertools.product("SP", repeat=k)
                        ]
                        groups = {}
                        matrix = []
                        for u in words:
                            suffixes = [
                                v for v in words if decisions[u + v]["accepted"]
                            ]
                            key = digest(suffixes)
                            groups.setdefault(
                                key, {"suffixes": suffixes, "prefixes": []}
                            )["prefixes"].append(u)
                            matrix.append(
                                [int(decisions[u + v]["accepted"]) for v in words]
                            )
                        keys = sorted(groups)
                        witnesses = []
                        for i, k in enumerate(keys):
                            for l in keys[i + 1 :]:
                                suffix = min(
                                    set(groups[k]["suffixes"])
                                    ^ set(groups[l]["suffixes"]),
                                    key=lambda x: (len(x), x),
                                )
                                u = groups[k]["prefixes"][0]
                                v = groups[l]["prefixes"][0]
                                witnesses.append(
                                    {
                                        "prefixes": [u, v],
                                        "distinguishing_suffix": suffix,
                                        "left_observation": decisions[u + suffix],
                                        "right_observation": decisions[v + suffix],
                                    }
                                )
                        check(
                            "actual continuation sets N=" + str(n),
                            len(groups) == n + 2
                            and any(g["suffixes"] == [] for g in groups.values()),
                        )
                        horizons[str(n)] = {
                            "prefixes": words,
                            "classes": groups,
                            "class_count": len(groups),
                            "membership_matrix": matrix,
                            "distinguishing_witnesses": witnesses,
                            "frozen_hypothesis_digest": seals[0],
                            "scope": "prefix/suffix lengths<=N; no infinite-language identification claim",
                        }
                    save("CONTINUATION_CLASSES.json", horizons)
                # Gold access only after inference. No runtime solver or program generation reads this file.
                raw = (a.fixture / "external-gold.json").read_bytes()
                assert (
                    hashlib.sha256(raw).hexdigest()
                    == protocol["files"]["external-gold.json"]
                )
                gold = json.loads(raw)
                scores = {}
                if a.phase == "continuations":
                    check(
                        "independent external continuation labels match",
                        all(
                            v["accepted"] == gold["continuations"][v["record_id"]]
                            for v in decisions.values()
                        ),
                    )
                else:
                    for key in (
                        ["old84"]
                        if a.phase == "baseline"
                        else ["full-137", "full-42", "no-derive", "unicode"]
                    ):
                        p = preds[key]
                        labels = (
                            gold["holdout"]
                            if key != "unicode"
                            else {
                                r["id"]: gold["holdout"][old["id"]]
                                for r, old in zip(
                                    renamed(data["queries"]), data["queries"]
                                )
                            }
                        )
                        scores[key] = score(p, labels)
                    if a.phase == "accept":
                        for key in ["full-137", "full-42", "unicode"]:
                            check(
                                "TP14 TN242 no FP FN " + key,
                                all(
                                    scores[key][k] == v
                                    for k, v in {
                                        "TP": 14,
                                        "TN": 242,
                                        "FP": 0,
                                        "FN": 0,
                                        "UNKNOWN": 0,
                                    }.items()
                                ),
                            )
                    else:
                        check(
                            "old result retained not success",
                            all(
                                scores["old84"][k] == v
                                for k, v in {
                                    "TP": 0,
                                    "TN": 242,
                                    "FP": 0,
                                    "FN": 14,
                                }.items()
                            ),
                        )
                save("scores.json", scores)
                save("models.json", models)
                save("predictions.json", preds)
                save("transcript.json", calls)
                health = await call("service_health", {})
                check(
                    "SQLite/audit",
                    health["sqlite_integrity"] == "ok" and health["audit"]["ok"],
                )
                save("health.json", health)
                save("transcript.json", calls)
                save(
                    "result.json",
                    {
                        "status": "PASS_FINITE_ROLE006"
                        if a.phase != "baseline"
                        else "PASS_BASELINE_NO_ROLE_EXPRESSIVITY",
                        "phase": a.phase,
                        "project": project,
                        "version": init.serverInfo.version,
                        "endpoint": a.endpoint,
                        "public_HTTPS_tested": a.endpoint.startswith("https://"),
                        "checks": len(checks),
                        "MCP_calls": len(calls),
                        "runs": {k: v["run_id"] for k, v in runs.items()},
                        "scores": scores,
                        "external_gold_loaded_after_inference": True,
                        "execution_permission": False,
                        "UNIVERSAL_INVARIANT": False,
                    },
                )
                print(
                    json.dumps(
                        {
                            "status": "PASS",
                            "phase": a.phase,
                            "checks": len(checks),
                            "MCP_calls": len(calls),
                            "project": project,
                        }
                    )
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--loopback-port", type=int)
    p.add_argument(
        "--phase", choices=["baseline", "accept", "continuations"], required=True
    )
    p.add_argument("--tag", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
