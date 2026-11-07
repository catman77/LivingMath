"""Real MCP PATCH004 gates. External scoring and supplied-AST controls are explicit."""

import argparse, asyncio, base64, copy, hashlib, json, sys
from itertools import product
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream
from recursive_observer_experiment import request, score
from symbolic_patch003_mcp_qa import sp_request, lab_record, dyck


async def run(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    checks = []
    calls = []
    gates = {}
    runs = {}
    models = {}
    scores = {}

    def check(name, ok):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(name)

    def gate(ident, ok, evidence):
        gates[ident] = {"status": "PASS" if ok else "FAIL", "evidence": evidence}
        save("gates.json", gates)
        check(ident, ok)

    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    project = "qa-recursive004-" + a.tag
    other = project + "-other"
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

                async def call(name, args, error=None):
                    result = await client.call_tool(name, args)
                    calls.append(
                        {
                            "tool": name,
                            "arguments": args,
                            "response": result.model_dump(mode="json"),
                        }
                    )
                    with (out / "transcript.jsonl").open("a") as f:
                        f.write(json.dumps(calls[-1], ensure_ascii=False) + "\n")
                    payload = result.structuredContent or json.loads(
                        result.content[0].text
                    )
                    if error:
                        check(
                            name + " expected " + error,
                            bool(
                                result.isError
                                and payload.get("error", {}).get("code") == error
                            ),
                        )
                        return payload
                    check(name + " response " + str(len(calls)), not result.isError)
                    return payload.get("data", payload)

                async def section(
                    run_id,
                    view,
                    tool="white_star_symbolic_observer_inspect",
                    owner=None,
                ):
                    items = []
                    offset = 0
                    for _ in range(4096):
                        page = await call(
                            tool,
                            {
                                "project": owner or project,
                                "run_id": run_id,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if page.get("requires_artifact"):
                            chunks = []
                            pos = 0
                            for _ in range(4096):
                                chunk = await call(
                                    tool,
                                    {
                                        "project": owner or project,
                                        "run_id": run_id,
                                        "view": "artifact",
                                        "artifact_ref": page["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                chunks.extend(
                                    base64.b64decode(i["data_base64"])
                                    for i in chunk["items"]
                                )
                                if chunk["next_offset"] is None:
                                    break
                                pos = chunk["next_offset"]
                            raw = b"".join(chunks)
                            check(
                                "complete source-bound artifact",
                                hashlib.sha256(raw).hexdigest()
                                == chunk["artifact_sha256"],
                            )
                            value = json.loads(raw)
                            return value if isinstance(value, list) else [value]
                        items += page["items"]
                        if page["next_offset"] is None:
                            return items
                        offset = page["next_offset"]
                    raise AssertionError("page bound")

                async def bundle(
                    run_id,
                    name,
                    inspect="white_star_symbolic_observer_inspect",
                    replay="white_star_symbolic_extension_replay",
                    owner=None,
                ):
                    chunks = await section(run_id, "export", inspect, owner)
                    raw = b"".join(base64.b64decode(c["data_base64"]) for c in chunks)
                    ref = chunks[0]["bundle_ref"]
                    check("bundle SHA " + name, hashlib.sha256(raw).hexdigest() == ref)
                    (out / (name + ".zip")).write_bytes(raw)
                    result = await call(
                        replay, {"project": owner or project, "bundle_ref": ref}
                    )
                    save(name + "-replay.json", result)
                    return result

                before = {
                    t["name"]: t for t in json.loads(a.baseline.read_text())["tools"]
                }
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                if a.allow_formal_api:
                    from formal001_compat import legacy_view
                    after=legacy_view(after)
                check(
                    "actual v046/83 tools",
                    init.serverInfo.version == a.expected_version
                    and len(after) == len(before) == 83,
                )
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
                for name, old in before.items():
                    changed = copy.deepcopy(after[name]["inputSchema"])
                    if (
                        name == "white_star_symbolic_observer_synthesize"
                        and "promotion_policy"
                        not in old["inputSchema"]["properties"]["request"]["properties"]
                    ):
                        added = changed["properties"]["request"]["properties"].pop(
                            "promotion_policy", None
                        )
                        check(
                            "only optional bounded promotion_policy added",
                            added is not None
                            and "promotion_policy"
                            not in changed["properties"]["request"].get("required", []),
                        )
                    check(
                        "unchanged old schema/annotations " + name,
                        changed == old["inputSchema"]
                        and after[name]["outputSchema"] == old["outputSchema"]
                        and after[name]["annotations"] == old["annotations"],
                    )
                status = await call("bridge_system_status", {})
                save("status.json", status)
                check(
                    "new capabilities READY and old symbolic binding",
                    status["observer_synthesis_v1"]["status"] == "READY"
                    and status["observer_synthesis_v1"]["version"]
                    == a.expected_observer_version
                    and status["symbolic_v1"]["kernel_binding"]
                    == "7ce5c5ba0620b4dad1b3f1b62b2cba3338a1efb4a7852a6e1bf768fe5fd0a0c9",
                )
                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                await call(
                    "assurance_project_new", {"project": other, "request_key": "init"}
                )

                async def store(kind, records, key, owner=None):
                    ds = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": records,
                    }
                    ds["sha256"] = digest(ds)
                    return (
                        await call(
                            "white_star_symbolic_dataset_store",
                            {
                                "project": owner or project,
                                "request_key": key,
                                "dataset": ds,
                            },
                        )
                    )["dataset_ref"]

                train = {
                    k: json.loads((a.fixture / (k + "_train.json")).read_text())
                    for k in ["pal", "copy"]
                }
                queries = {
                    n: json.loads(
                        (a.fixture / ("query_" + str(n) + ".json")).read_text()
                    )
                    for n in [6, 8]
                }
                trainrefs = {
                    k: await store("train", v, "train-" + k) for k, v in train.items()
                }
                queryrefs = {
                    n: await store("queries", v, "query-" + str(n))
                    for n, v in queries.items()
                }

                async def synth(kind, n, key, q=None, owner=None, read_model=True):
                    q = copy.deepcopy(q or request())
                    q["task"].update(
                        train_ref=trainrefs[kind], predict_ref=queryrefs[n]
                    )
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {"project": owner or project, "request_key": key, "request": q},
                    )
                    check("completed " + key, row["status"] == "COMPLETED")
                    runs[key] = row
                    save("runs.json", runs)
                    model = (
                        (await section(row["run_id"], "model", owner=owner))[0]
                        if read_model
                        else None
                    )
                    predictions = (
                        await section(row["run_id"], "pairwise_eval", owner=owner)
                    )[0]["predictions"]
                    return row, model, predictions, q

                predictions = {}
                configs = {}
                features = {}
                for kind in ["pal", "copy"]:
                    for n in [6, 8]:
                        key = kind + "-n" + str(n)
                        row, model, pred, q = await synth(kind, n, key)
                        models[key] = model
                        predictions[key] = pred
                        configs[key] = q
                        feature = next(
                            f
                            for f in model["feature_registry"]
                            if f["feature_id"] in model["used_feature_ids"]
                        )
                        features[key] = feature
                        checked = await call(
                            "white_star_symbolic_observer_verify",
                            {
                                "project": project,
                                "run_id": row["run_id"],
                                "feature_id": feature["feature_id"],
                            },
                        )
                        check(
                            "independent positive " + key,
                            checked["status"] == "CHECKED_INSTANCE"
                            and checked["verified_witnesses"] == len(train[kind])
                            and not checked["execution_permission"],
                        )
                        save(key + "-verification.json", checked)
                    for seed in [42]:
                        q = request(seed)
                        row, model, pred, _ = await synth(
                            kind, 6, kind + "-seed" + str(seed), q
                        )
                        models[kind + "-seed42"] = model
                        predictions[kind + "-seed42"] = pred
                        check(
                            "same selected AST on seed " + kind,
                            feature["operator_ast_digest"]
                            == next(
                                f
                                for f in model["feature_registry"]
                                if f["feature_id"] in model["used_feature_ids"]
                            )["operator_ast_digest"],
                        )
                    q = request()
                    q["feature_policy"]["derive_relations"] = False
                    row, model, pred, _ = await synth(kind, 6, kind + "-no-derive", q)
                    predictions[kind + "-no-derive"] = pred
                    check(
                        "no derivation actually disables feature " + kind,
                        not model["used_feature_ids"],
                    )
                    q = request()
                    q["feature_policy"]["feature_denylist"].append(
                        features[kind + "-n6"]["feature_id"]
                    )
                    row, model, pred, _ = await synth(kind, 6, kind + "-denied", q)
                    predictions[kind + "-denied"] = pred
                    check(
                        "actual feature denied " + kind, not model["used_feature_ids"]
                    )
                # Scorer is outside the server, after immutable models/predictions.
                for key, pred in predictions.items():
                    kind = key.split("-")[0]
                    n = 8 if key.endswith("n8") else 6
                    labels = json.loads(
                        (
                            a.fixture
                            / "external-label-holder"
                            / ("gold_" + str(n) + ".json")
                        ).read_text()
                    )["labels"][kind.upper()]
                    scores[key] = score(pred, labels)
                save("models.json", models)
                save("predictions.json", predictions)
                save("scores.json", scores)
                pal = models["pal-n6"]
                pf = features["pal-n6"]
                pr = runs["pal-n6"]
                cf = features["copy-n6"]
                cr = runs["copy-n6"]
                gate(
                    "A01",
                    len(train["pal"]) == 16
                    and any(
                        r.get("ast", {}).get("composition")
                        == "iterate_on_inner_fragment"
                        and r.get("status") == "TRAIN_COMPATIBLE"
                        for r in pal["derivation_trace"]
                    ),
                    pr["run_id"],
                )
                gate(
                    "A02",
                    pf["origin"] == "DERIVED_FROM_OPERATORS"
                    and pf["template_origin"] == "COMPOSITIONAL_AST_PROMOTION"
                    and pf["feature_id"] in pal["used_feature_ids"]
                    and pf["operator_ast"]["composition"]
                    == "iterate_on_inner_fragment",
                    pf["feature_id"],
                )
                gate(
                    "A03",
                    pf["verifier_result"]["status"] == "CHECKED_INSTANCE"
                    and pf["verifier_result"]["verified_witnesses"] == 16,
                    "pal-n6-verification.json",
                )
                for ident, key, tp, tn in [
                    ("A04", "pal-n6", 8, 56),
                    ("A05", "pal-n8", 16, 240),
                    ("B02", "copy-n6", 8, 56),
                    ("B03", "copy-n8", 16, 240),
                ]:
                    s = scores[key]
                    gate(
                        ident,
                        (s["TP"], s["TN"], s["FP"], s["FN"], s["UNKNOWN"])
                        == (tp, tn, 0, 0, 0),
                        key,
                    )
                gate(
                    "A07",
                    all(
                        scores[k + "-seed42"]["balanced_accuracy"] == 1
                        for k in ["pal", "copy"]
                    ),
                    ["pal-seed42", "copy-seed42"],
                )
                gate(
                    "A08",
                    all(
                        scores[k + "-no-derive"]["TP"] == 0
                        and scores[k + "-no-derive"]["FN"] == 8
                        for k in ["pal", "copy"]
                    ),
                    "scores.json",
                )
                gate(
                    "A09",
                    all(
                        scores[k + "-denied"]["TP"] == 0
                        and scores[k + "-denied"]["FN"] == 8
                        for k in ["pal", "copy"]
                    ),
                    "scores.json",
                )
                gate(
                    "A10",
                    pal["hypothesis_digest"] == models["pal-n8"]["hypothesis_digest"]
                    and models["copy-n6"]["hypothesis_digest"]
                    == models["copy-n8"]["hypothesis_digest"]
                    and all("accepted" not in r for q in queries.values() for r in q),
                    "models.json / queries",
                )
                gate(
                    "B01",
                    cf["operator_ast"]["composition"] == "compare_fragments"
                    and cf["candidate_provenance"]["origin"] == "AUTO_DISCOVERED"
                    and cf["operator_ast"]["cut"]["position"] == "MIDPOINT_EXACT_EVEN"
                    and len(train["copy"]) == 20,
                    cr["run_id"],
                )
                gate(
                    "B05",
                    cf["verifier_result"]["status"] == "CHECKED_INSTANCE"
                    and scores["copy-denied"]["balanced_accuracy"] == 0.5,
                    cf["feature_id"],
                )
                for parent in pf["parent_feature_refs"]:
                    q = request()
                    q["feature_policy"]["feature_denylist"].append(parent)
                    _, m, _, _ = await synth(
                        "pal", 6, "parent-" + parent.replace(":", "-"), q
                    )
                    check(
                        "parent dependency enforced " + parent,
                        not m["used_feature_ids"],
                    )
                # Actual old induction, source binding, explicit route provenance.
                old_request = json.loads(
                    (
                        ROOT / "tests/fixtures/composition_source_request.json"
                    ).read_text()
                )
                source = await call(
                    "white_star_symbolic_explore",
                    {
                        "project": project,
                        "request_key": "source-symbolic",
                        "request": old_request,
                    },
                )
                source_id = source["run_id"]
                q = request()
                q["source_run_id"] = source_id
                q["promotion_policy"]["candidate_sources"] = ["source_run_id"]
                sr, sm, _, sq = await synth("pal", 6, "source-supplied", q)
                sf = next(
                    f
                    for f in sm["feature_registry"]
                    if f["feature_id"] in sm["used_feature_ids"]
                )
                check(
                    "actual source supplied origin",
                    sf["candidate_provenance"]["origin"] == "SOURCE_SUPPLIED"
                    and sf["candidate_provenance"]["source_run_id"] == source_id,
                )
                sourcecheck = await call(
                    "white_star_symbolic_observer_verify",
                    {
                        "project": project,
                        "run_id": sr["run_id"],
                        "feature_id": sf["feature_id"],
                    },
                )
                check(
                    "source candidate independently checked",
                    sourcecheck["status"] == "CHECKED_INSTANCE",
                )
                wrong = copy.deepcopy(train["pal"])
                wrong[0]["accepted"] = not wrong[0]["accepted"]
                wrongref = await store("train", wrong, "wrong-train")
                bad = copy.deepcopy(sq)
                bad["task"]["train_ref"] = wrongref
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "source-train-mismatch",
                        "request": bad,
                    },
                    "SOURCE_TRAIN_MISMATCH",
                )
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": other, "request_key": "foreign-dataset", "request": sq},
                    "NOT_FOUND",
                )
                othertrain = await store("train", train["pal"], "other-train", other)
                otherquery = await store("queries", queries[6], "other-query", other)
                bad = copy.deepcopy(sq)
                bad["task"].update(train_ref=othertrain, predict_ref=otherquery)
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": other, "request_key": "foreign-source", "request": bad},
                    "NOT_FOUND",
                )
                await call(
                    "white_star_symbolic_observer_inspect",
                    {"project": other, "run_id": pr["run_id"]},
                    "NOT_FOUND",
                )
                original_source = request()
                original_source["source_run_id"] = (
                    "80457c8536c12fb4e18e302c14542ca4568e9c83cb650def98af3fb49cd92baa"
                )
                original_source["task"].update(
                    train_ref="f7502b97fbb2c101cbd061b68e7036dd07038d862cb4df015ab6b1160005e452",
                    predict_ref="0c79f9fa14e9ce1d38570f9dc83368a1d42881a9cc251866056a4c976cda4ae1",
                )
                original_source["promotion_policy"]["candidate_sources"] = [
                    "source_run_id"
                ]
                old_bridge = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": "whitestar_dialog_test",
                        "request_key": "PATCH004-existing-source-" + a.tag,
                        "request": original_source,
                    },
                )
                old_model = (
                    await section(
                        old_bridge["run_id"], "model", owner="whitestar_dialog_test"
                    )
                )[0]
                old_feature = next(
                    f
                    for f in old_model["feature_registry"]
                    if f["feature_id"] in old_model["used_feature_ids"]
                )
                old_check = await call(
                    "white_star_symbolic_observer_verify",
                    {
                        "project": "whitestar_dialog_test",
                        "run_id": old_bridge["run_id"],
                        "feature_id": old_feature["feature_id"],
                    },
                )
                check(
                    "actual pre-patch source run promoted independently",
                    old_check["status"] == "CHECKED_INSTANCE"
                    and old_feature["candidate_provenance"]["source_run_id"]
                    == original_source["source_run_id"],
                )
                save(
                    "original-source-bridge.json",
                    {
                        "run": old_bridge,
                        "feature": old_feature,
                        "verification": old_check,
                    },
                )
                gate(
                    "A06",
                    sourcecheck["status"] == "CHECKED_INSTANCE",
                    {
                        "source": source_id,
                        "derived": sr["run_id"],
                        "origin": "SOURCE_SUPPLIED",
                    },
                )
                gate("A12", True, "foreign source/dataset/run requests rejected")
                # Certificates are actively replayed; all wrappers are recomputed.
                attacks = {}
                for name, ident in [
                    ("output_hash", "A13"),
                    ("position", "A14"),
                    ("missing", "A15"),
                    ("operator", "A17"),
                    ("origin", "A18"),
                    ("universal", "A19"),
                    ("position_bool", "TYPE_BOOL"),
                    ("readout_integer", "TYPE_INT"),
                    ("outer_digest", "OUTER_DIGEST"),
                    ("provenance", "B06"),
                ]:
                    bad = copy.deepcopy(pf)
                    if name == "output_hash":
                        bad["construction_trace"][0]["operator_trace"][0][
                            "output_word_hashes"
                        ][0] = "0" * 64
                    elif name in ["position", "position_bool"]:
                        step = next(
                            s
                            for w in bad["construction_trace"]
                            for s in w["operator_trace"]
                            if s.get("operator") == "SPLIT"
                            and s["args"]["position"] == 1
                        )
                        step["args"]["position"] = 2 if name == "position" else True
                    elif name == "missing":
                        bad["construction_trace"].pop()
                    elif name == "operator":
                        bad["construction_trace"][0]["operator_trace"][0][
                            "operator"
                        ] = "RUN_SCRIPT"
                    elif name == "origin":
                        bad["origin"] = "BUILTIN"
                    elif name == "universal":
                        bad["construction_trace"][0]["universal_invariant"] = True
                    elif name == "readout_integer":
                        step = next(
                            s
                            for w in bad["construction_trace"]
                            for s in w["operator_trace"]
                            if s.get("operation") == "literal_word_equality"
                        )
                        step["value"] = int(step["value"])
                    elif name == "provenance":
                        bad["candidate_provenance"]["origin"] = "SOURCE_SUPPLIED"
                    bad["witness_set_digest"] = digest(bad["construction_trace"])
                    bad["digest"] = digest(
                        {k: v for k, v in bad.items() if k != "digest"}
                    )
                    if name == "outer_digest":
                        bad["digest"] = "0" * 64
                    rejected = await call(
                        "white_star_symbolic_observer_verify",
                        {
                            "project": project,
                            "run_id": pr["run_id"],
                            "feature_id": pf["feature_id"],
                            "certificate": bad,
                        },
                    )
                    attacks[name] = rejected
                    check(
                        "hostile certificate rejected " + name,
                        rejected["status"] == "REJECTED"
                        and not rejected["execution_permission"]
                        and bool(rejected.get("field_path")),
                    )
                    if ident != "B06":
                        gate(ident, True, name)
                save("rejected-certificates.json", attacks)

                # Unicode sources, not ASCII spans pretending to be UTF-8 evidence.
                def renamed(rows):
                    return [
                        lab_record(
                            r["id"],
                            ["кот" if t == "S" else "лес" for t in r["tokens"]],
                            r.get("accepted"),
                        )
                        for r in rows
                    ]

                ur = await store("train", renamed(train["pal"]), "utf8-train")
                uq = await store("queries", renamed(queries[6]), "utf8-query")
                u = request()
                u["task"].update(train_ref=ur, predict_ref=uq)
                record = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "utf8", "request": u},
                )
                um = (await section(record["run_id"], "model"))[0]
                uf = next(
                    f
                    for f in um["feature_registry"]
                    if f["feature_id"] in um["used_feature_ids"]
                )
                bad = copy.deepcopy(uf)
                next(
                    v
                    for w in bad["construction_trace"]
                    for v in w["states"].values()
                    if v["source_spans"]
                )["source_spans"][0][0][1] += 1
                bad["witness_set_digest"] = digest(bad["construction_trace"])
                bad["digest"] = digest({k: v for k, v in bad.items() if k != "digest"})
                negative = await call(
                    "white_star_symbolic_observer_verify",
                    {
                        "project": project,
                        "run_id": record["run_id"],
                        "feature_id": uf["feature_id"],
                        "certificate": bad,
                    },
                )
                up = (await section(record["run_id"], "pairwise_eval"))[0][
                    "predictions"
                ]
                check(
                    "global bijective renaming predictions preserved",
                    [p["score"] for p in up]
                    == [p["score"] for p in predictions["pal-n6"]],
                )
                gate(
                    "A16",
                    negative["status"] == "REJECTED",
                    "actual Cyrillic source spans",
                )
                scope_query = lab_record("scope-9", list("S" * 9))
                scope_ref = await store("queries", [scope_query], "out-of-scope")
                q = copy.deepcopy(configs["pal-n6"])
                q["task"]["predict_ref"] = scope_ref
                scoped = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "scope-9", "request": q},
                )
                p = (await section(scoped["run_id"], "pairwise_eval"))[0][
                    "predictions"
                ][0]
                gate(
                    "A20",
                    p["score"] is None and p["status"] == "UNKNOWN",
                    scoped["run_id"],
                )
                leak = copy.deepcopy(queries[6][:1])
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
                repeat = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "pal-n6",
                        "request": configs["pal-n6"],
                    },
                )
                fresh = await call(
                    "white_star_symbolic_observer_synthesize",
                    {
                        "project": project,
                        "request_key": "pal-identical-fresh",
                        "request": configs["pal-n6"],
                    },
                )
                changed = copy.deepcopy(configs["pal-n6"])
                changed["promotion_policy"]["max_tokens"] = 6
                await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "pal-n6", "request": changed},
                    "REQUEST_KEY_CONFLICT",
                )
                gate(
                    "A21",
                    repeat["run_id"] == pr["run_id"]
                    and fresh["run_id"] != pr["run_id"]
                    and fresh["result_digest"] == pr["result_digest"],
                    "fresh key deterministic digest / old key immutable",
                )
                replayed = await bundle(pr["run_id"], "pal-operator")
                gate(
                    "A22",
                    replayed["status"] == "REPLAY_MATCH"
                    and replayed["journal_hash_chain"] == "PASS",
                    replayed,
                )
                await bundle(cr["run_id"], "copy-operator")
                # Baseline contexts: exactly the old literal route, not composition mode.
                contains_results = {}
                for pair in ["SP", "PS", "SS"]:
                    ts = [
                        lab_record(
                            "train-" + str(n) + "-" + str(i),
                            w,
                            any(
                                tuple(w[j : j + 2]) == tuple(pair)
                                for j in range(len(w) - 1)
                            ),
                        )
                        for n in [1, 2, 3]
                        for i, w in enumerate(product("SP", repeat=n))
                    ]
                    qs = [
                        lab_record("query-" + str(i), w)
                        for i, w in enumerate(product("SP", repeat=6))
                    ]
                    t = await store("train", ts, "contains-" + pair + "-train")
                    qref = await store("queries", qs, "contains-" + pair + "-query")
                    q = request()
                    q.pop("promotion_policy")
                    q["task"].update(train_ref=t, predict_ref=qref)
                    row = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": project,
                            "request_key": "contains-" + pair,
                            "request": q,
                        },
                    )
                    m = (await section(row["run_id"], "model"))[0]
                    pred = (await section(row["run_id"], "pairwise_eval"))[0][
                        "predictions"
                    ]
                    expected = {
                        r["id"]: any(
                            tuple(r["tokens"][j : j + 2]) == tuple(pair)
                            for j in range(5)
                        )
                        for r in qs
                    }
                    s = score(pred, expected)
                    contains_results[pair] = s
                    f = next(
                        f
                        for f in m["feature_registry"]
                        if f["feature_id"] in m["used_feature_ids"]
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
                        "old context actual verify " + pair,
                        v["status"] == "CHECKED_INSTANCE",
                    )
                gate(
                    "A23",
                    all(s["accuracy"] == 1 for s in contains_results.values()),
                    contains_results,
                )
                counts = {
                    2: (3, 2, 0, 0, 0),
                    4: (9, 14, 6, 8, 6),
                    6: (29, 74, 46, 80, 46),
                    8: (99, 354, 256, 560, 256),
                    10: (351, 1614, 1264, 3360, 1264),
                }
                for n, expected in counts.items():
                    row = await call(
                        "white_star_symbolic_complex_analyze",
                        {
                            "project": project,
                            "request_key": "sp-" + str(n),
                            "request": sp_request(n),
                        },
                    )
                    s = row["summary"]
                    check(
                        "SP counts " + str(n),
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
                        == expected
                        and s["dim_H1_F2"] == 0,
                    )
                    v = await call(
                        "white_star_symbolic_complex_verify",
                        {"project": project, "run_id": row["run_id"]},
                    )
                    check(
                        "SP independent checker " + str(n),
                        v["status"] == "CHECKED_INSTANCE",
                    )
                    if n == 10:
                        await bundle(
                            row["run_id"],
                            "sp10",
                            inspect="white_star_symbolic_complex_inspect",
                        )
                for policy in ["none", "bigons_only", "diamonds_only"]:
                    row = await call(
                        "white_star_symbolic_complex_analyze",
                        {
                            "project": project,
                            "request_key": "partial-" + policy,
                            "request": sp_request(6, policy),
                        },
                    )
                    v = await call(
                        "white_star_symbolic_complex_verify",
                        {"project": project, "run_id": row["run_id"]},
                    )
                    check(
                        "partial no pi1 proof " + policy,
                        v["pi1_status"] == "NOT_PROVED",
                    )
                gate(
                    "A24",
                    True,
                    "SP2/4/6/8/10 exact counts, real checker and partial-cell negatives",
                )
                numeric_project = project + "-numeric"
                await call(
                    "assurance_project_new",
                    {"project": numeric_project, "request_key": "init"},
                )
                numerical = []
                for profile in ["base_v1", "cj_v1"]:
                    q = json.loads(
                        (
                            ROOT
                            / "docs/LEVINMAS_WHITESTAR_MCP_001/fixtures/original_request.json"
                        ).read_text()
                    )
                    q["atlas_profile"] = profile
                    row = await call(
                        "white_star_explore",
                        {
                            "project": numeric_project,
                            "request_key": "numeric-" + profile,
                            "request": q,
                        },
                    )
                    check("numeric completed " + profile, row["status"] == "COMPLETED")
                    numerical.append(
                        await bundle(
                            row["run_id"],
                            "numeric-" + profile,
                            inspect="white_star_inspect",
                            replay="white_star_replay",
                            owner=numeric_project,
                        )
                    )
                symbolic_replay = await bundle(
                    source_id,
                    "symbolic-source",
                    inspect="white_star_symbolic_inspect",
                    replay="white_star_symbolic_replay",
                )
                historical = {}
                for file in sorted(a.historical.glob("*.json")):
                    old = json.loads(file.read_text())["record"]
                    tool = (
                        "white_star_symbolic_inspect"
                        if old["engine"] == "symbolic_v1"
                        else "white_star_symbolic_observer_inspect"
                    )
                    current = (
                        await section(
                            old["run_id"], "summary", tool, "whitestar_dialog_test"
                        )
                    )[0]
                    check(
                        "original immutable " + file.stem,
                        digest(current) == digest(old),
                    )
                    historical[file.stem] = current
                save("historical-runs.json", historical)
                fresh_manifest = json.loads(
                    (
                        ROOT
                        / "docs/LIVINGMATH_RECURSIVE_OBSERVER_PATCH004_20261106/reports/live_research_manifest.json"
                    ).read_text()
                )
                for index, old in enumerate(fresh_manifest["fresh_live_runs"]):
                    original = json.loads(
                        (a.historical / ("FRESH_" + str(index) + ".json")).read_text()
                    )
                    q = original["packet"]["request"]
                    same = await call(
                        "white_star_symbolic_observer_synthesize",
                        {
                            "project": "whitestar_dialog_test",
                            "request_key": old["request_key"],
                            "request": q,
                        },
                    )
                    check(
                        "historical exact key preserved " + str(index),
                        digest(same) == digest(original["record"]),
                    )
                old_verification = await call(
                    "white_star_symbolic_observer_verify",
                    {
                        "project": "qa-fixb2-prod",
                        "run_id": "e1a9e5b090f6a3d0491f7d640a91b6fbbe548de61432e05a61c54350f681f718",
                        "feature_id": "derived_2aadef27f9235974c974",
                    },
                )
                check(
                    "old v045 feature verification through approved profile",
                    old_verification["status"] == "CHECKED_INSTANCE",
                )
                await bundle(
                    "e1a9e5b090f6a3d0491f7d640a91b6fbbe548de61432e05a61c54350f681f718",
                    "old-v045",
                    owner="qa-fixb2-prod",
                )
                gate(
                    "A11",
                    len(historical) == 19,
                    "historical-runs.json + original key replay",
                )
                gate(
                    "A25",
                    all(v["status"] == "PASS" for v in numerical)
                    and symbolic_replay["status"] == "REPLAY_MATCH",
                    "numeric profiles and old immutable symbolic/observer replay",
                )
                # COPY weak-rule counterexample: equal endpoints and equal bags,
                # unequal halves. It never enters training.
                weak = lab_record("weak", list("SSPPSS"))
                ref = await store("queries", [weak], "weak-query")
                q = copy.deepcopy(configs["copy-n6"])
                q["task"]["predict_ref"] = ref
                row = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "weak-copy", "request": q},
                )
                p = (await section(row["run_id"], "pairwise_eval"))[0]["predictions"][0]
                gate(
                    "B04",
                    p["score"] < 0.5
                    and weak["tokens"][0] == weak["tokens"][-1]
                    and sorted(weak["tokens"][:3]) == sorted(weak["tokens"][3:]),
                    row["run_id"],
                )
                from lm_suti_assurance.observer_synthesis.composition_ast import (
                    execute,
                    declared_domain,
                )
                from lm_suti_assurance.observer_synthesis.composition_checker import (
                    execute_checked,
                )
                from lm_suti_assurance.observer_synthesis.contexts import record_state

                supplied = {
                    "composition": "compare_fragments",
                    "cut": {"operator": "SPLIT", "position": "MIDPOINT_EXACT_EVEN"},
                    "comparison": "literal_word_equality",
                    "expected_equal": True,
                }
                local = []
                for n in [6, 8]:
                    for r in queries[n]:
                        state = record_state(r)
                        v, tr, states = execute(
                            supplied,
                            state,
                            declared_domain(request()["promotion_policy"]),
                            certify=True,
                        )
                        w = {
                            "record_ref": digest(r),
                            "source_sha256": r["source"]["sha256"],
                            "input_state_ref": digest(state.data()),
                            "decision": v,
                            "operator_trace": tr,
                            "states": states,
                        }
                        check(
                            "supplied local AST execution " + r["id"],
                            execute_checked(
                                supplied,
                                r,
                                w,
                                declared_domain(request()["promotion_policy"]),
                            )
                            == v,
                        )
                    local.append(
                        {
                            "n": n,
                            "witnesses": len(queries[n]),
                            "origin": "MANUALLY_SUPPLIED_EVALUATOR_CONTROL",
                            "discovery_claimed": False,
                        }
                    )
                save("local-supplied-control.json", local)
                gate(
                    "B06",
                    attacks["provenance"]["status"] == "REJECTED",
                    {
                        "local_evaluator_control": local,
                        "MCP_source_origin_forgery": "REJECTED",
                        "not_counted_as_discovery": True,
                    },
                )
                # Additional roadmap controls use the frozen model and external
                # expected predictions, never pass labels to the worker queries.
                transfer = {}
                for kind in ["pal", "copy"]:
                    for mode in ["reverse_queries", "opaque_global_bijection"]:
                        mapping = {"S": "atom_97f34a", "P": "atom_a051ce"}
                        rows = [
                            lab_record(
                                r["id"],
                                list(reversed(r["tokens"]))
                                if mode == "reverse_queries"
                                else [mapping[t] for t in r["tokens"]],
                            )
                            for r in queries[6]
                        ]
                        qr = await store("queries", rows, kind + "-" + mode + "-query")
                        q = copy.deepcopy(configs[kind + "-n6"])
                        if mode == "opaque_global_bijection":
                            tr = [
                                lab_record(
                                    r["id"],
                                    [mapping[t] for t in r["tokens"]],
                                    r["accepted"],
                                )
                                for r in train[kind]
                            ]
                            q["task"]["train_ref"] = await store(
                                "train", tr, kind + "-" + mode + "-train"
                            )
                        q["task"]["predict_ref"] = qr
                        rr = await call(
                            "white_star_symbolic_observer_synthesize",
                            {
                                "project": project,
                                "request_key": kind + "-" + mode,
                                "request": q,
                            },
                        )
                        pp = (await section(rr["run_id"], "pairwise_eval"))[0][
                            "predictions"
                        ]
                        check(
                            "roadmap transfer " + kind + " " + mode,
                            [p["score"] for p in pp]
                            == [p["score"] for p in predictions[kind + "-n6"]],
                        )
                        transfer[kind + "-" + mode] = {
                            "status": "PASS",
                            "run_id": rr["run_id"],
                            "queries": len(rows),
                        }
                save("roadmap-controls.json", transfer)
                # P2: measured short orientation-dependent grammar, then obey stop.
                dt = [
                    lab_record("dyck-" + str(n) + "-" + str(i), w, dyck(w))
                    for n in [2, 4]
                    for i, w in enumerate(product("SP", repeat=n))
                ]
                dtr = await store("train", dt, "dyck-train")
                q = request()
                q["task"].update(train_ref=dtr, predict_ref=queryrefs[6])
                dr = await call(
                    "white_star_symbolic_observer_synthesize",
                    {"project": project, "request_key": "dyck-short", "request": q},
                )
                dm = (await section(dr["run_id"], "model"))[0]
                p2 = {
                    "C01": {
                        "status": "MEASURED_NO_NEW_COMPOSITION"
                        if not dm["used_feature_ids"]
                        else "MEASURED_EMPIRICAL_CANDIDATE",
                        "run_id": dr["run_id"],
                        "model_status": dm["synthesis_status"],
                        "orientation_counterexample": {
                            "same_equality_pattern": ["SP", "PS"],
                            "labels": [True, False],
                        },
                    },
                    "C02": {
                        "status": "NOT_RUN_STOP_CRITERION",
                        "reason": "No new short Dyck composition; roadmap forbids next large corpus stage",
                    },
                    "C03": {
                        "status": "NOT_RUN_WITH_C02",
                        "reason": "No cross-century semantic-transfer claim",
                    },
                }
                save("P2.json", p2)
                health = await call("service_health", {})
                save("health.json", health)
                check(
                    "SQLite healthy",
                    health["sqlite_integrity"] == "ok" and health["audit"]["ok"],
                )
                after_model = (await section(pr["run_id"], "model"))[0]
                check(
                    "no verification/mutation changed frozen model",
                    digest(after_model) == digest(pal),
                )
                required = {"A" + str(i).zfill(2) for i in range(1, 26)} | {
                    "B" + str(i).zfill(2) for i in range(1, 7)
                }
                check(
                    "all31 required gates accounted",
                    set(gates) >= required
                    and all(gates[i]["status"] == "PASS" for i in required),
                )
                save("transcript.json", calls)
                save(
                    "result.json",
                    {
                        "status": "PASS_P0_P1_FINITE",
                        "checks": len(checks),
                        "gates": gates,
                        "P2": p2,
                        "project": project,
                        "version": init.serverInfo.version,
                        "endpoint": a.endpoint,
                        "public_HTTPS_tested": a.endpoint.startswith("https://"),
                        "execution_permission": False,
                        "run_ids": {k: v["run_id"] for k, v in runs.items()},
                        "scores": scores,
                    },
                )
                print(
                    json.dumps(
                        {
                            "status": "PASS_P0_P1_FINITE",
                            "checks": len(checks),
                            "gates": len(required),
                            "project": project,
                        }
                    )
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--allow-formal-api",action="store_true")
    p.add_argument("--expected-version", default="v0.4.6-developer-preview")
    p.add_argument(
        "--expected-observer-version",
        default="observer_synthesis_v1/3-compositional-promotion",
    )
    p.add_argument("--allow-role-api", action="store_true")
    p.add_argument("--retry-resource-busy", action="store_true")
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--loopback-port", type=int)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--historical", type=Path, required=True)
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    asyncio.run(run(p.parse_args()))
