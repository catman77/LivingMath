"""Real SDK/OAuth acceptance for Formal Bridge; frozen gold loaded after inference."""

import argparse, asyncio, base64, copy, hashlib, itertools, json, sys
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import digest
from recursive_observer_experiment import request
from role006_fixture import record

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "live_math_mcp_prod"))
from unified_client_qa import authenticate
from dav_acceptance import TappedStream


async def run(a):
    out = a.output
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    checks = []
    calls = []
    results = {}
    runs = {}
    predictions = {}
    metrics = {}
    trrefs = {}
    qrefs = {}
    comparison = {}

    def save(n, v):
        (out / n).write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")

    def check(name, ok):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL"})
        save("checks.json", checks)
        if not ok:
            raise AssertionError(name)

    protocol = json.loads((a.fixture / "PROTOCOL.json").read_text())
    for n, h in protocol["files"].items():
        check(
            "sealed " + n, hashlib.sha256((a.fixture / n).read_bytes()).hexdigest() == h
        )
    data = json.loads((a.fixture / "inputs.json").read_text())
    auth = authenticate(
        a.origin, a.password, out / "oauth.private.json", a.loopback_port
    )
    headers = {"Authorization": "Bearer " + auth["token"]["access_token"]}
    if a.loopback_port:
        headers["Host"] = "livingmath.example"
    project = "qa-formal001-" + a.tag
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
                init = await client.initialize()
                listing = await client.list_tools()
                save("initialize.json", init.model_dump(mode="json"))
                save("tools.json", listing.model_dump(mode="json"))
                check("actual server version", init.serverInfo.version == a.version)
                tools = {t.name: t.model_dump(mode="json") for t in listing.tools}
                baseline = {
                    t["name"]: t for t in json.loads(a.baseline.read_text())["tools"]
                }
                check(
                    "all83 old schemas unchanged",
                    all(tools.get(n) == v for n, v in baseline.items()),
                )
                check(
                    "eight additive formal tools published",
                    set(tools) - set(baseline)
                    == {
                        "formal_" + n
                        for n in [
                            "store",
                            "synthesize",
                            "inspect",
                            "verify",
                            "contrast",
                            "interpret",
                            "model_check",
                            "replay",
                        ]
                    },
                )

                async def call(name, args, error=False):
                    r = await client.call_tool(name, args)
                    v = r.structuredContent or json.loads(r.content[0].text)
                    c = {
                        "tool": name,
                        "arguments": args,
                        "response": r.model_dump(mode="json"),
                    }
                    calls.append(c)
                    with (out / "transcript.jsonl").open("a") as f:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                    check(
                        name + " " + str(len(calls)) + (" denied" if error else ""),
                        bool(r.isError) == error,
                    )
                    return v.get("data", v)

                async def readrun(run_ref, view="result", object_ref=None):
                    offset = 0
                    chunks = []
                    items = []
                    for _ in range(4096):
                        args = {
                            "project": project,
                            "run_ref": run_ref,
                            "view": view,
                            "offset": offset,
                            "limit": 128,
                        }
                        if object_ref:
                            args["object_ref"] = object_ref
                        v = await call("formal_inspect", args)
                        if v.get("encoding") == "base64":
                            chunks.append(base64.b64decode(v["data"], validate=True))
                        elif "items" in v:
                            items += v["items"]
                        else:
                            return v
                        if v["next_offset"] is None:
                            if chunks:
                                raw = b"".join(chunks)
                                check(
                                    "chunked object SHA",
                                    hashlib.sha256(raw).hexdigest() == v["sha256"],
                                )
                                return json.loads(raw)
                            return items
                        offset = v["next_offset"]
                    raise AssertionError("pagination bound")

                async def oldsection(rid, view):
                    items = []
                    offset = 0
                    for _ in range(4096):
                        page = await call(
                            "white_star_symbolic_observer_inspect",
                            {
                                "project": project,
                                "run_id": rid,
                                "view": view,
                                "offset": offset,
                                "limit": 128,
                            },
                        )
                        if page.get("requires_artifact"):
                            chunks = []
                            pos = 0
                            for _ in range(4096):
                                c = await call(
                                    "white_star_symbolic_observer_inspect",
                                    {
                                        "project": project,
                                        "run_id": rid,
                                        "view": "artifact",
                                        "artifact_ref": page["artifact_ref"],
                                        "offset": pos,
                                        "limit": 128,
                                    },
                                )
                                chunks.extend(
                                    base64.b64decode(x["data_base64"])
                                    for x in c["items"]
                                )
                                if c["next_offset"] is None:
                                    break
                                pos = c["next_offset"]
                            raw = b"".join(chunks)
                            check(
                                "complete old artifact SHA",
                                hashlib.sha256(raw).hexdigest() == c["artifact_sha256"],
                            )
                            v = json.loads(raw)
                            return v if isinstance(v, list) else [v]
                        items += page["items"]
                        if page["next_offset"] is None:
                            return items
                        offset = page["next_offset"]
                    raise AssertionError("old section page bound")

                async def op(name, key, **args):
                    r = await call(
                        "formal_" + name,
                        {"project": project, "request_key": key, **args},
                    )
                    check("formal job completed " + key, r["status"] == "COMPLETED")
                    runs[key] = r
                    metrics[key] = r.get("metrics", {})
                    v = await readrun(r["run_ref"])
                    results[key] = v
                    save("runs.json", runs)
                    save("metrics.json", metrics)
                    save(key + ".json", v)
                    return r, v

                async def ds(name, rows, kind):
                    d = {
                        "schema": "livingmath-observer-dataset/1",
                        "kind": kind,
                        "records": rows,
                    }
                    d["sha256"] = digest(d)
                    r = await call(
                        "white_star_symbolic_dataset_store",
                        {"project": project, "request_key": name, "dataset": d},
                    )
                    return r["dataset_ref"]

                await call(
                    "assurance_project_new", {"project": project, "request_key": "init"}
                )
                save("health.json", await call("service_health", {}))
                save("status.json", await call("bridge_system_status", {}))
                # Original same-input comparison: no query labels or manual ASTs.
                for name, case in data["cases"].items():
                    trrefs[name] = await ds(name + "-train", case["train"], "train")
                    qrefs[name] = await ds(name + "-query", case["queries"], "queries")
                    for mode in ["role_branching_ast", "auto"]:
                        q = request(137)
                        q["task"].update(
                            train_ref=trrefs[name], predict_ref=qrefs[name]
                        )
                        q["feature_policy"]["enabled_builtins"] = []
                        q["promotion_policy"]["mode"] = mode
                        old = await call(
                            "white_star_symbolic_observer_synthesize",
                            {
                                "project": project,
                                "request_key": name + "-" + mode,
                                "request": q,
                            },
                        )
                        check(
                            "old mode completed " + name + mode,
                            old["status"] == "COMPLETED",
                        )
                        values = (await oldsection(old["run_id"], "pairwise_eval"))[0][
                            "predictions"
                        ]
                        comparison[name + "-" + mode] = {
                            "run": old,
                            "predictions": values,
                        }
                        save("comparison.json", comparison)
                    backend = "dfa" if name.startswith("regular") else "cfg"
                    r, v = await op(
                        "synthesize",
                        name + "-formal",
                        train_ref=trrefs[name],
                        predict_ref=qrefs[name],
                        constraints={"kind": backend},
                    )
                    predictions[name] = v["predictions"]
                    save("predictions.json", predictions)
                    check(
                        "fit labels hidden " + name,
                        v["checks"]["holdout_labels_read"] is False
                        and v["checks"]["hypothesis_frozen_before_queries"] is True,
                    )
                    # Match same sealed request with fresh key; canonical model/result identical.
                    if name in ["cfg_anbn", "cfg_dyck2_new_stratified"]:
                        rr, vv = await op(
                            "synthesize",
                            name + "-fresh",
                            train_ref=trrefs[name],
                            predict_ref=qrefs[name],
                            constraints={"kind": backend},
                        )
                        check(
                            "fresh key deterministic " + name,
                            v == vv and r["run_ref"] != rr["run_ref"],
                        )
                    # Active questions before any extra annotation. Ground-truth label absent.
                    if name in ["cfg_anbn", "regular_even_a"]:
                        candidates = v["model"]["candidates"]
                        check(
                            "multiple compatible hypotheses " + name,
                            len(candidates) >= 2,
                        )
                        ids = [c["candidate_id"] for c in candidates]
                        _, cv = await op(
                            "contrast",
                            name + "-contrast",
                            run_ref=r["run_ref"],
                            candidate_refs=ids[:16],
                        )
                        check(
                            "contrast is actual disagreement " + name,
                            cv["status"] == "DISTINGUISHING_QUERY"
                            and len(set(cv["prediction_vector"])) > 1
                            and cv["correct_label"] is None,
                        )
                        if name == "cfg_anbn":
                            check(
                                "epsilon first discriminator",
                                cv["query"]["tokens"] == [],
                            )
                    if "enriched_queries" in case:
                        train = case["train"] + case.get("annotation", [])
                        newref = await ds(
                            name + "-external-annotation-v2", train, "train"
                        )
                        qr = await ds(
                            name + "-enriched", case["enriched_queries"], "queries"
                        )
                        rr, vv = await op(
                            "synthesize",
                            name + "-annotated",
                            train_ref=newref,
                            predict_ref=qr,
                            constraints={"kind": backend},
                        )
                        predictions[name + "-enriched"] = vv["predictions"]
                        save("predictions.json", predictions)
                        check(
                            "annotation generation scope " + name,
                            (newref != trrefs[name]) == bool(case.get("annotation")),
                        )
                        check(
                            "enriched definite predictions " + name,
                            all(
                                p["status"] == "CHECKED_INSTANCE"
                                for p in vv["predictions"]
                            ),
                        )
                        if name == "regular_even_a":
                            check(
                                "two state induced DFA",
                                len(vv["model"]["candidates"][0]["ast"]["states"]) == 2,
                            )
                        if backend == "dfa":
                            predictions[name + "-enriched-pre-active"] = vv[
                                "predictions"
                            ]
                            annotations = []
                            for generation in range(4):
                                cs = vv["model"]["candidates"]
                                if len(cs) < 2:
                                    break
                                _, cv = await op(
                                    "contrast",
                                    name + "-active-query-" + str(generation),
                                    run_ref=rr["run_ref"],
                                    candidate_refs=[c["candidate_id"] for c in cs[:16]],
                                )
                                if cv["status"] == "NO_DIFFERENCE_WITHIN_BOUND":
                                    break
                                check(
                                    "active external question " + name,
                                    cv["status"] == "DISTINGUISHING_QUERY"
                                    and cv["correct_label"] is None,
                                )
                                tokens = cv["query"]["tokens"]
                                holder = json.loads(
                                    (
                                        a.fixture / "external-annotations.json"
                                    ).read_text()
                                )
                                label = holder[name][digest(tokens)]
                                check(
                                    "active question outside existing train " + name,
                                    all(r["tokens"] != tokens for r in train),
                                )
                                annotation = record(
                                    tokens, label, prefix="active-" + str(generation)
                                )
                                train = [*train, annotation]
                                annotations.append(
                                    {
                                        "query": cv,
                                        "external_label": label,
                                        "train_record": annotation,
                                    }
                                )
                                newref = await ds(
                                    name + "-active-train-" + str(generation),
                                    train,
                                    "train",
                                )
                                rr, vv = await op(
                                    "synthesize",
                                    name + "-active-" + str(generation),
                                    train_ref=newref,
                                    predict_ref=qr,
                                    constraints={"kind": "dfa"},
                                )
                            save(name + "-ACTIVE_ANNOTATIONS.json", annotations)
                            predictions[name + "-enriched"] = vv["predictions"]
                            save("predictions.json", predictions)
                            check(
                                "active final model train-compatible " + name,
                                vv["model"]["status"] == "TRAIN_COMPATIBLE",
                            )

                # Verify actual two-alternative forest, typed role mistakes and bound/cycle statuses.
                grammar = data["grammar_controls"]["grammars"]

                def convert(x):
                    terms = sorted(
                        {
                            s[2:]
                            for rr in x["rules"].values()
                            for rhs in rr
                            for s in rhs
                            if s.startswith("t:")
                        }
                    )
                    ps = []
                    for nt, rr in x["rules"].items():
                        for rhs in rr:
                            ps.append(
                                {
                                    "id": "p" + str(len(ps)),
                                    "lhs": nt,
                                    "rhs": [
                                        {"op": "TERM", "value": s[2:]}
                                        if s.startswith("t:")
                                        else {"op": "NT_REF", "name": s[2:]}
                                        for s in rhs
                                    ]
                                    or [{"op": "EPS"}],
                                }
                            )
                    return {
                        "schema": "formal-grammar-ir/1",
                        "terminals": terms,
                        "nonterminals": list(x["rules"]),
                        "start": x["start"],
                        "productions": ps,
                    }

                stored = {}
                for n in ["ambiguous_concat", "dyck2", "dyck2_untyped"]:
                    r, _ = await op(
                        "store",
                        "control-" + n,
                        kind="grammar",
                        data=convert(grammar[n]),
                    )
                    stored[n] = r
                sr, _ = await op(
                    "store", "record-aaa", kind="record", data=record(list("aaa"))
                )
                _, forest = await op(
                    "verify",
                    "ambiguous-forest",
                    run_ref=stored["ambiguous_concat"]["run_ref"],
                    source_ref=sr["stored_object_ref"],
                )
                check(
                    "two aaa derivations preserved",
                    forest["status"] == "CHECKED_INSTANCE"
                    and len(forest["proof"]["trees"]) == 2,
                )
                dr, _ = await op(
                    "contrast",
                    "typed-vs-untyped",
                    run_ref=stored["dyck2"]["run_ref"],
                    candidate_refs=[
                        stored[n]["stored_object_ref"]
                        for n in ["dyck2", "dyck2_untyped"]
                    ],
                )
                dv = results["typed-vs-untyped"]
                check(
                    "typed/untyped actual disagreement",
                    dv["status"] == "DISTINGUISHING_QUERY"
                    and len(set(dv["prediction_vector"])) == 2,
                )
                source, _ = await op(
                    "store", "record-nested", kind="record", data=record(list("SABP"))
                )
                _, good = await op(
                    "verify",
                    "source-proof",
                    run_ref=stored["dyck2"]["run_ref"],
                    source_ref=source["stored_object_ref"],
                )
                check(
                    "source proof positive",
                    good["status"] == "CHECKED_INSTANCE"
                    and good["verification"]["decision"] is True,
                )
                tamper = []
                for mutation in ["sha", "rule", "span", "start", "token", "order"]:
                    bad = copy.deepcopy(good["proof"])
                    if mutation == "sha":
                        bad["source_sha256"] = "0" * 64
                    elif mutation == "start":
                        bad["start_symbol"] = "alien"
                    elif mutation == "span":
                        bad["token_spans"][0][0] += 1
                    elif mutation == "rule":
                        bad["forest"][0]["families"][0]["production_id"] = "alien"
                    elif mutation == "token":
                        bad["tokens"][0] = "alien"
                    elif mutation == "order":
                        next(
                            f
                            for x in bad["forest"]
                            for f in x["families"]
                            if len(f["children"]) > 1
                        )["children"].reverse()
                    br, _ = await op(
                        "store", "tamper-" + mutation, kind="proof", data=bad
                    )
                    rr, tv = await op(
                        "verify",
                        "reject-" + mutation,
                        run_ref=stored["dyck2"]["run_ref"],
                        source_ref=source["stored_object_ref"],
                        proof_ref=br["stored_object_ref"],
                    )
                    check(
                        "tamper rejected " + mutation,
                        tv["status"] == "REJECTED_PROOF"
                        and tv["execution_permission"] is False,
                    )
                    tamper.append(
                        {
                            "mutation": mutation,
                            "run_ref": rr["run_ref"],
                            "status": tv["status"],
                        }
                    )
                save("PROOF_TAMPER_MATRIX.json", tamper)
                _, bv = await op(
                    "verify",
                    "proof-bound",
                    run_ref=stored["dyck2"]["run_ref"],
                    source_ref=source["stored_object_ref"],
                    budget={"max_steps": 1},
                )
                check(
                    "bound not false",
                    bv["status"] == "UNKNOWN_BOUND"
                    and bv["verification"]["decision"] is None,
                )
                # Three manual PROPOSED readings, actual source links and two finite models.
                f = data["fol"]
                s = {
                    "text_utf8": f["source"]["text"],
                    "sha256": f["source"]["sha256"],
                    "rights": f["source"]["rights"],
                    "spans": [],
                    "context_refs": [],
                }
                sr, _ = await op("store", "fol-source", kind="source", data=s)
                props = [
                    {
                        "formula_ast": c["formula_ast"],
                        "assumptions": [],
                        "token_role_links": [
                            {"byte_utf8": x["byte_utf8"], "literal": x["literal"]}
                            for x in c["source_token_links"]
                        ],
                        "construction_trace": [
                            {
                                "origin": "EXPLICIT_HUMAN_ANNOTATION",
                                "id": c["candidate_id"],
                            }
                        ],
                    }
                    for c in f["candidates"]
                ]
                sig = {"sorts": f["nonempty_sorts"], "predicates": f["signature"]}
                ir, iv = await op(
                    "interpret",
                    "fol-three",
                    source_ref=sr["stored_object_ref"],
                    candidate_provider={
                        "kind": "human",
                        "provenance": {
                            "origin": "supplied source-bound hand annotations",
                            "not_automatic_NLP": True,
                        },
                    },
                    target_signature=sig,
                    proposals=props,
                )
                check(
                    "three retained typed proposed interpretations",
                    len(iv["candidates"]) == 3
                    and all(
                        c["type_status"] == "TYPED"
                        and c["proof_status"] == "PROPOSED"
                        and c["source_ref"] == sr["stored_object_ref"]
                        for c in iv["candidates"]
                    ),
                )
                models = []
                for i, m in enumerate(f["finite_models"]):
                    mr, _ = await op(
                        "store",
                        "fol-model-" + str(i),
                        kind="model",
                        data={**m["model"], "world": "closed"},
                    )
                    vec = []
                    for j, c in enumerate(iv["candidates"]):
                        _, mv = await op(
                            "model_check",
                            "fol-model-" + str(i) + "-candidate-" + str(j),
                            run_ref=ir["run_ref"],
                            candidate_ref=c["candidate_id"],
                            model_ref=mr["stored_object_ref"],
                        )
                        vec.append(mv["truth"])
                        check(
                            "finite model status separated",
                            mv["proof_status"] == "FINITE_MODEL_CHECKED"
                            and mv["semantic_alignment_status"] == "PROPOSED",
                        )
                    check(
                        "known source-bound truth vector " + str(i),
                        vec == list(m["truth_vector"].values()),
                    )
                    models.append({"name": m["name"], "truth_vector": vec})
                for i, j in [(0, 1), (0, 2), (1, 2)]:
                    _, cv = await op(
                        "contrast",
                        "fol-pair-" + str(i) + str(j),
                        run_ref=ir["run_ref"],
                        candidate_refs=[
                            iv["candidates"][k]["candidate_id"] for k in [i, j]
                        ],
                    )
                    check(
                        "FOL finite countermodel " + str(i) + str(j),
                        cv["status"] == "FINITE_COUNTERMODEL"
                        and len(set(cv["truth_vector"])) == 2,
                    )
                bad = copy.deepcopy(props[0])
                bad["formula_ast"]["body"]["body"]["args"].reverse()
                _, ivbad = await op(
                    "interpret",
                    "fol-invalid-type",
                    source_ref=sr["stored_object_ref"],
                    candidate_provider={
                        "kind": "imported",
                        "provenance": {"origin": "adversarial wrong type"},
                    },
                    target_signature=sig,
                    proposals=[bad],
                )
                check(
                    "wrong type rejected",
                    ivbad["candidates"][0]["type_status"] == "TYPE_REJECTED"
                    and ivbad["candidates"][0]["proof_status"] == "PROPOSED",
                )
                save(
                    "TYPECHECK_AND_MODEL_COUNTEREXAMPLES.json",
                    {"manual_proposals": iv, "models": models, "rejected_type": ivbad},
                )
                # Replays, request-key conflict/idempotency and cross-project refs through MCP.
                key = "cfg_anbn-formal"
                r = runs[key]
                case = data["cases"]["cfg_anbn"]
                same = await call(
                    "formal_synthesize",
                    {
                        "project": project,
                        "request_key": key,
                        "train_ref": trrefs["cfg_anbn"],
                        "predict_ref": qrefs["cfg_anbn"],
                        "constraints": {"kind": "cfg"},
                    },
                )
                check("same key no new operation", same == r)
                await call(
                    "formal_synthesize",
                    {
                        "project": project,
                        "request_key": key,
                        "train_ref": trrefs["cfg_anbn"],
                        "predict_ref": qrefs["cfg_anbn"],
                        "constraints": {"kind": "dfa"},
                    },
                    True,
                )
                other = project + "-other"
                await call(
                    "assurance_project_new", {"project": other, "request_key": "init"}
                )
                await call(
                    "formal_synthesize",
                    {
                        "project": other,
                        "request_key": "foreign",
                        "train_ref": trrefs["cfg_anbn"],
                        "predict_ref": qrefs["cfg_anbn"],
                        "constraints": {"kind": "cfg"},
                    },
                    True,
                )
                await call(
                    "formal_contrast",
                    {
                        "project": project,
                        "request_key": "invalid-anchor",
                        "run_ref": "0" * 64,
                        "candidate_refs": [
                            stored[n]["stored_object_ref"]
                            for n in ["dyck2", "dyck2_untyped"]
                        ],
                    },
                    True,
                )
                for key in [
                    "cfg_anbn-formal",
                    "cfg_dyck2_new_stratified-formal",
                    "regular_even_a-annotated",
                    "fol-three",
                ]:
                    _, rv = await op(
                        "replay", "replay-" + key, run_ref=runs[key]["run_ref"]
                    )
                    check("exact replay " + key, rv["status"] == "REPLAY_MATCH")
                save(
                    "OFFLINE_BUNDLE.json",
                    await readrun(runs["cfg_anbn-formal"]["run_ref"], "bundle"),
                )
                # External scoring after every inference and probe has completed.
                gold = json.loads((a.fixture / "external-gold.json").read_text())
                matrix = {}

                def score(rows, target, legacy=False):
                    vals = {
                        r.get("record_id", r.get("id")): (
                            (None if r.get("score") is None else r["score"] >= 0.5)
                            if legacy
                            else r.get("decision")
                        )
                        for r in rows
                    }
                    counts = dict(TP=0, TN=0, FP=0, FN=0, UNKNOWN=0)
                    for rid, y in target.items():
                        v = vals.get(rid)
                        if v is None:
                            counts["UNKNOWN"] += 1
                        else:
                            counts[
                                "TP" if y and v else "FN" if y else "FP" if v else "TN"
                            ] += 1
                    return {
                        **counts,
                        "total": len(target),
                        "positive_rate": sum(target.values()) / len(target),
                        "balanced_accuracy": 0.5
                        * (
                            counts["TP"] / max(1, sum(target.values()))
                            + counts["TN"] / max(1, len(target) - sum(target.values()))
                        ),
                    }

                for name, rows in predictions.items():
                    matrix[name] = score(rows, gold[name.removesuffix("-pre-active")])
                    save("FORMAL_LANGUAGE_MATRIX.json", matrix)
                    check(
                        "finite epistemic boundary " + name,
                        all(
                            r.get("verification", {}).get("UNIVERSAL_INVARIANT")
                            is not True
                            for r in rows
                        ),
                    )
                    if name != "noncfg_anbncn_canary" and not name.endswith(
                        "-pre-active"
                    ):
                        check(
                            "holdout exact " + name,
                            matrix[name]["FP"]
                            == matrix[name]["FN"]
                            == matrix[name]["UNKNOWN"]
                            == 0,
                        )
                for key, v in comparison.items():
                    matrix[key] = score(
                        v["predictions"], gold[key.rsplit("-", 1)[0]], True
                    )
                save("FORMAL_LANGUAGE_MATRIX.json", matrix)
                save("predictions.json", predictions)
                save("comparison.json", comparison)
                save("transcript.json", calls)
                save(
                    "result.json",
                    {
                        "status": "PASS_FINITE_FORMAL001",
                        "checks": len(checks),
                        "MCP_calls": len(calls),
                        "project": project,
                        "version": a.version,
                        "public_HTTPS_tested": a.loopback_port is None,
                        "models": {k: r["run_ref"] for k, r in runs.items()},
                        "external_gold_loaded_after_inference": True,
                        "UNIVERSAL_INVARIANT": False,
                        "execution_permission": False,
                    },
                )
                print("FORMAL001_PASS", len(checks), len(calls), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--origin", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--version", default="v0.4.9-developer-preview")
    p.add_argument(
        "--password",
        type=Path,
        default=Path.home() / ".config/livingmath/login-password",
    )
    p.add_argument("--loopback-port", type=int)
    asyncio.run(run(p.parse_args()))
