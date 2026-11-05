"""Real HTTPS/OAuth QA; fixture encoder and actual client decoder are separate."""

import argparse
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from lm_suti_assurance.core import canonical
from lm_suti_assurance.white_star.contracts import VENDOR, TOOLS, RESPONSE, check_schema


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def model_proposal(family, claim):
    values = {
        "observation_invariant": {
            "A": [[1, 0], [0, 2]],
            "C": [[1, 0]],
            "x": [[1], [1]],
        },
        "control_invariant": {
            "A": [[1, 0], [0, 1]],
            "B": [[1], [0]],
            "C": [[1, 0]],
            "w": [[0, 1]],
            "x": [[3], [1]],
            "u": [[-3]],
        },
        "cyclic_order": {
            "U": [[1, 1], [0, 1]],
            "L": [[1, 0], [1, 1]],
            "P": [[2, 0], [0, 1]],
            "x": [[1], [0]],
        },
    }
    return {
        "schema": "levinmas-white-star-model/1",
        "family": family,
        "matrices": values.get(family, {}),
        "claim_ref": claim,
        "frame_refs": ["F01"],
        "mapping_assumptions": [
            "QA reuses the supplied rational exemplar as an explicit illustrative target model; not automatically inferred from prose, not native SUTI, not physics."
        ],
        "obligations": {
            "observation_invariant": ["invariant_identity", "hidden_state_change"],
            "control_invariant": ["invariant_identity", "partial_improvement"],
            "cyclic_order": ["conjugacy", "different_action"],
        }.get(family, ["invariant_identity"]),
    }


async def run(a):
    sys.path.insert(0, str(a.legacy_client))
    from unified_client_qa import authenticate
    from dav_acceptance import TappedStream

    a.private.mkdir(mode=0o700, parents=True, exist_ok=True)
    a.out.mkdir(mode=0o700, parents=True, exist_ok=True)
    authfile = a.private / "oauth.private.json"
    auth = (
        json.loads(authfile.read_text())
        if authfile.exists()
        else authenticate(a.origin, a.password_file, authfile)
    )
    phase = a.phase
    calls = []
    checks = []
    if (a.out / "checks.json").exists():
        checks = json.loads((a.out / "checks.json").read_text())

    def check(name, value):
        checks.append({"id": phase + ":" + name, "status": "PASS" if value else "FAIL"})
        save(a.out / "checks.json", checks)
        if not value:
            raise AssertionError(name)

    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            a.origin + "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json,text/event-stream"},
        )
        check("UNAUTHORIZED_DENIED", r.status_code == 401)
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + auth["token"]["access_token"]},
        timeout=120,
    ) as http:
        async with streamable_http_client(a.origin + "/mcp", http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                TappedStream(read, a.out / (phase + "-wire.jsonl"), "server_to_client"),
                TappedStream(
                    write, a.out / (phase + "-wire.jsonl"), "client_to_server"
                ),
            ) as client:
                init = await client.initialize()
                listing = await client.list_tools()
                save(a.out / (phase + "-initialize.json"), init.model_dump(mode="json"))
                save(
                    a.out / (phase + "-tools-list.json"),
                    listing.model_dump(mode="json"),
                )
                old = json.loads(a.baseline.read_text())["tools"]
                after = {t.name: t.model_dump(mode="json") for t in listing.tools}
                check(
                    "OLD64_INPUT_SCHEMAS_PRESERVED",
                    len(old) == 64
                    and all(
                        after[t["name"]]["inputSchema"] == t["inputSchema"] for t in old
                    ),
                )
                check(
                    "72_REAL_TOOLS_V03",
                    len(after) == 72
                    and init.serverInfo.version == "v0.3.0-developer-preview",
                )
                check(
                    "OUTPUT_SCHEMAS_AND_ANNOTATIONS",
                    all(
                        after[n]["outputSchema"] == RESPONSE
                        and after[n]["annotations"]["readOnlyHint"]
                        == TOOLS[n]["annotations"]["readOnlyHint"]
                        for n in TOOLS
                    ),
                )

                async def call(name, args, expected_error=None):
                    start = time.perf_counter()
                    r = await client.call_tool(name, args)
                    calls.append(
                        {
                            "tool": name,
                            "request": args,
                            "response": r.model_dump(mode="json"),
                            "round_trip_s": time.perf_counter() - start,
                        }
                    )
                    save(a.out / (phase + "-mcp-transcript.json"), calls)
                    value = r.structuredContent or json.loads(r.content[0].text)
                    if name in TOOLS:
                        check_schema(value, RESPONSE)
                        if expected_error:
                            assert (
                                r.isError and value["error"]["code"] == expected_error
                            ), value
                            return value["error"]
                        assert not r.isError, value
                        return value["data"]
                    assert not r.isError, (name, r.content)
                    return value

                status = await call("white_star_status", {})
                save(a.out / "white-star-status.json", status)
                check(
                    "NATIVE_READY_75_SHA_ISOLATED",
                    status["status"] == "READY"
                    and len(status["kernel_hashes"]) == 75
                    and all(
                        w["isolation"]["credentials_denied"]
                        and w["isolation"]["filesystem_writes_denied"]
                        for w in status["worker"]["workers"]
                    ),
                )
                check(
                    "NO_NATIVE_SUTI_OR_EXECUTION_PROMOTION",
                    status["SUTI_native_runtime"] == "NOT_EXECUTED"
                    and status["execution_permission"] is False
                    and status["R3"] == "PENDING",
                )
                health = await call("service_health", {})
                save(a.out / "health.json", health)
                baseline = json.loads(
                    (a.baseline.parent / "service_health_BEFORE.json").read_text()
                )["parsed"]
                check(
                    "LEGACY_EVENTS_AND_AUDIT_UNCHANGED",
                    health["event_count"] == baseline["event_count"]
                    and health["audit"] == baseline["audit"]
                    and health["sqlite_integrity"] == "ok",
                )
                if phase == "setup":
                    ids = {}
                    for case, filename in [
                        ("blok", "blok_request.json"),
                        ("original", "original_request.json"),
                    ]:
                        project = "qa-whitestar-" + case
                        await call(
                            "assurance_project_new",
                            {"project": project, "request_key": "qa-create"},
                        )
                        request = json.loads(
                            (VENDOR / "fixtures" / filename).read_text()
                        )
                        white = await call(
                            "white_star_explore",
                            {
                                "project": project,
                                "request_key": "qa-white",
                                "request": request,
                            },
                        )
                        again = await call(
                            "white_star_explore",
                            {
                                "project": project,
                                "request_key": "qa-white",
                                "request": request,
                            },
                        )
                        check(
                            case + ":IDEMPOTENT_REAL_EXPLORATION",
                            white["run_id"] == again["run_id"]
                            and white["result_digest"] == again["result_digest"],
                        )
                        check(
                            case + ":EXACT_COUNTERS",
                            white["summary"]["steps"]
                            == request["encoding"]["protocol"]["steps"]
                            and white["summary"]["projections"]
                            == request["encoding"]["protocol"]["steps"] * 3,
                        )
                        bridge = await call(
                            "semantic_run_frozen",
                            {
                                "project": project,
                                "request_key": "qa-bridge",
                                "common_snapshot_ref": white["common_snapshot_ref"],
                                "decoder_slots": 6,
                            },
                        )
                        comparison = await call(
                            "semantic_compare_runs",
                            {
                                "project": project,
                                "left": {
                                    "engine": "white_star",
                                    "run_id": white["run_id"],
                                },
                                "right": {"engine": "suti", "run_id": bridge["run_id"]},
                                "protocol": {
                                    "mode": "MATCHED_INPUT",
                                    "decoder_protocol_id": "whitestar-client-decoder/1",
                                },
                            },
                        )
                        check(
                            case + ":REAL_MATCHED_INPUT",
                            comparison["status"] == "MATCHED_INPUT"
                            and comparison["same_common_snapshot"],
                        )
                        ids[case] = {
                            "project": project,
                            "request": request,
                            "white_star": white,
                            "suti": bridge,
                        }
                        for engine, value in [("white_star", white), ("suti", bridge)]:
                            page = await call(
                                "white_star_inspect",
                                {
                                    "project": project,
                                    "run_id": value["run_id"],
                                    "view": "decoder",
                                },
                            )
                            assert (
                                len(page["items"]) == 1
                                and not page["requires_artifact"]
                            ), page
                            save(
                                a.out
                                / "decoder-packets"
                                / (case + "-" + engine + ".json"),
                                page["items"][0],
                            )
                        trace = []
                        offset = 0
                        while True:
                            page = await call(
                                "white_star_inspect",
                                {
                                    "project": project,
                                    "run_id": white["run_id"],
                                    "view": "trace",
                                    "offset": offset,
                                    "limit": 7,
                                },
                            )
                            trace += page["items"]
                            if page["next_offset"] is None:
                                break
                            offset = page["next_offset"]
                        check(
                            case + ":WHOLE_TRACE_PAGES",
                            len(trace) == request["encoding"]["protocol"]["steps"],
                        )
                        if a.label=='production':
                            fresh=await call('white_star_explore',{'project':project,'request_key':'qa-production-smoke','request':request})
                            check(case+':ACTUAL_NEW_PRODUCTION_NUMERIC_JOB',fresh['run_id']!=white['run_id'] and fresh['result_digest']==white['result_digest'] and fresh['status']=='COMPLETED')
                        changed = copy.deepcopy(request)
                        changed["encoding"]["protocol"]["seed"] = 43
                        await call(
                            "white_star_explore",
                            {
                                "project": project,
                                "request_key": "qa-white",
                                "request": changed,
                            },
                            "REQUEST_CONFLICT",
                        )
                    save(a.out / "RUN_IDS.json", ids)
                    project = "qa-whitestar-negative"
                    await call(
                        "assurance_project_new",
                        {"project": project, "request_key": "qa-create"},
                    )
                    request = json.loads(
                        (VENDOR / "fixtures/original_request.json").read_text()
                    )
                    bad = copy.deepcopy(request)
                    bad["encoding"]["source"]["sha256"] = "0" * 64
                    source_error = await call(
                        "white_star_explore",
                        {
                            "project": project,
                            "request_key": "bad-source",
                            "request": bad,
                        },
                        "SOURCE_MISMATCH",
                    )
                    check("SOURCE_FAILURE_DURABLE_RUN_ID", bool(source_error["run_id"]))
                    bad = copy.deepcopy(request)
                    bad["encoding"]["protocol"]["steps"] = True
                    await call(
                        "white_star_explore",
                        {"project": project, "request_key": "bool", "request": bad},
                        "INVALID_INPUT",
                    )
                    small = copy.deepcopy(request)
                    small["encoding"]["protocol"].update(steps=1, frame_size=1)
                    tiny = await call(
                        "white_star_explore",
                        {"project": project, "request_key": "tiny", "request": small},
                    )
                    check(
                        "EMPTY_RESULT_NOT_INVENTED_READINGS",
                        tiny["selected_frame_ids"] == []
                        and tiny["status"] == "COMPLETED",
                    )
                    bad = copy.deepcopy(request)
                    sample = bad["encoding"]["concepts"][0]
                    bad["encoding"]["concepts"] = [
                        {**sample, "id": "c" + str(i), "coordinates": [i, i * i + 1]}
                        for i in range(1, 47)
                    ]
                    await call(
                        "white_star_explore",
                        {
                            "project": project,
                            "request_key": "oversize-atlas",
                            "request": bad,
                        },
                        "ATLAS_LIMIT_EXCEEDED",
                    )
                    check(
                        "SERVER_HEALTHY_AFTER_ERRORS",
                        (await call("white_star_status", {}))["status"] == "READY",
                    )
                else:
                    ids = json.loads((a.out / "RUN_IDS.json").read_text())
                    decoders = json.loads(a.decoders.read_text())
                    recorded = {}
                    for case, values in ids.items():
                        project = values["project"]
                        recorded[case] = {}
                        for engine in ("white_star", "suti"):
                            run = values[engine]
                            decoded = decoders[case + "-" + engine]
                            receipt = await call(
                                "white_star_record_interpretation",
                                {
                                    "project": project,
                                    "run_id": run["run_id"],
                                    "request_key": "qa-decoder",
                                    "readings": decoded["readings"],
                                    "provenance": decoded["provenance"],
                                },
                            )
                            again = await call(
                                "white_star_record_interpretation",
                                {
                                    "project": project,
                                    "run_id": run["run_id"],
                                    "request_key": "qa-decoder",
                                    "readings": decoded["readings"],
                                    "provenance": decoded["provenance"],
                                },
                            )
                            check(
                                case + ":" + engine + ":REAL_CLIENT_READINGS_RETAINED",
                                receipt == again
                                and len(receipt["reading_refs"])
                                == len(decoded["readings"])
                                and receipt["status"] == "INTERPRETATION",
                            )
                            recorded[case][engine] = receipt
                        comparison = await call(
                            "semantic_compare_runs",
                            {
                                "project": project,
                                "left": {
                                    "engine": "white_star",
                                    "run_id": values["white_star"]["run_id"],
                                },
                                "right": {
                                    "engine": "suti",
                                    "run_id": values["suti"]["run_id"],
                                },
                                "protocol": {
                                    "mode": "MATCHED_INPUT",
                                    "decoder_protocol_id": "whitestar-client-decoder/1",
                                },
                            },
                        )
                        save(a.out / (case + "-comparison.json"), comparison)
                        check(
                            case + ":MATCHED_WITH_ACTUAL_DECODINGS",
                            comparison["status"] == "MATCHED_INPUT",
                        )
                    blok = ids["blok"]
                    run_id = blok["white_star"]["run_id"]
                    project = blok["project"]
                    claim = recorded["blok"]["white_star"]["claim_refs"][0]
                    for family in (
                        "observation_invariant",
                        "control_invariant",
                        "cyclic_order",
                    ):
                        proposal = model_proposal(family, claim)
                        valid = await call(
                            "white_star_validate_model",
                            {
                                "project": project,
                                "run_id": run_id,
                                "proposal": proposal,
                            },
                        )
                        repeated = await call(
                            "white_star_validate_model",
                            {
                                "project": project,
                                "run_id": run_id,
                                "proposal": proposal,
                            },
                        )
                        check(
                            family + ":CHECKED_INSTANCE_IDEMPOTENT",
                            valid == repeated and valid["status"] == "CHECKED_INSTANCE",
                        )
                        bad = copy.deepcopy(proposal)
                        if family == "observation_invariant":
                            bad["matrices"]["A"][0][0] = 2
                        elif family == "control_invariant":
                            bad["matrices"]["B"][1][0] = 1
                        else:
                            bad["matrices"]["x"] = [[0], [0]]
                        negative = await call(
                            "white_star_validate_model",
                            {"project": project, "run_id": run_id, "proposal": bad},
                        )
                        check(
                            family + ":COUNTEREXAMPLE_NORMAL_TOOL_RESULT",
                            negative["status"] == "REJECTED"
                            and negative["execution_permission"] is False,
                        )
                    unknown = await call(
                        "white_star_validate_model",
                        {
                            "project": project,
                            "run_id": run_id,
                            "proposal": model_proposal("physics-unregistered", claim),
                        },
                    )
                    check(
                        "UNSUPPORTED_NOT_FALSE_FORMAL_SUCCESS",
                        unknown["status"] == "UNSUPPORTED_MODEL",
                    )
                    for case, values in ids.items():
                        project = values["project"]
                        run_id = values["white_star"]["run_id"]
                        offset = 0
                        chunks = []
                        while True:
                            page = await call(
                                "white_star_inspect",
                                {
                                    "project": project,
                                    "run_id": run_id,
                                    "view": "export",
                                    "offset": offset,
                                    "limit": 1,
                                },
                            )
                            chunks += page["items"]
                            if page["next_offset"] is None:
                                break
                            offset = page["next_offset"]
                        ref = chunks[0]["bundle_ref"]
                        raw = b"".join(
                            base64.b64decode(c["data_base64"]) for c in chunks
                        )
                        check(
                            case + ":PRIVATE_EXPORT_COMPLETE",
                            hashlib.sha256(raw).hexdigest() == ref,
                        )
                        (a.out / (case + "-private.zip")).write_bytes(raw)
                        replay = await call(
                            "white_star_replay", {"project": project, "bundle_ref": ref}
                        )
                        save(a.out / (case + "-replay.json"), replay)
                        check(
                            case + ":REAL_MCP_OFFLINE_REPLAY",
                            replay["status"] == "PASS"
                            and replay["LLM"] == "NOT_CALLED",
                        )
                    original = ids["original"]
                    changed = copy.deepcopy(original["request"])
                    changed["encoding"]["concepts"][0][
                        "label"
                    ] = "Другая сохранённая разметка"
                    other = await call(
                        "white_star_explore",
                        {
                            "project": original["project"],
                            "request_key": "qa-unmatched-control",
                            "request": changed,
                        },
                    )
                    mismatch = await call(
                        "semantic_compare_runs",
                        {
                            "project": original["project"],
                            "left": {"engine": "white_star", "run_id": other["run_id"]},
                            "right": {
                                "engine": "suti",
                                "run_id": original["suti"]["run_id"],
                            },
                            "protocol": {
                                "mode": "MATCHED_INPUT",
                                "decoder_protocol_id": "whitestar-client-decoder/1",
                            },
                        },
                    )
                    check(
                        "ACTUAL_UNMATCHED_INPUT_CONTROL",
                        mismatch["status"] == "UNMATCHED_INPUT"
                        and mismatch["same_source_bytes"],
                    )
                    save(a.out / "unmatched-control.json", mismatch)
                    save(a.out / "RECORDED_INTERPRETATIONS.json", recorded)
                    save(
                        a.out / "result.json",
                        {
                            "status": "PASS",
                            "origin": a.origin,
                            "tools": 72,
                            "old_input_schemas_preserved": 64,
                            "checks": checks,
                            "production_or_stage": a.label,
                            "project_ids": [v["project"] for v in ids.values()],
                            "server_model_calls": 0,
                            "client_decoder_calls": 4,
                            "R3": "PENDING",
                            "SUTI_native_runtime": "NOT_EXECUTED",
                        },
                    )
                save(
                    a.out / (phase + "-result.json"),
                    {
                        "status": "PASS",
                        "phase": phase,
                        "checks": checks,
                        "origin": a.origin,
                        "tools": 72,
                    },
                )
                print(
                    canonical(
                        {
                            "status": "PASS",
                            "phase": phase,
                            "origin": a.origin,
                            "checks": len(checks),
                        }
                    )
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for n in ("private", "out", "password-file", "legacy-client", "baseline"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--decoders", type=Path)
    p.add_argument("--origin", required=True)
    p.add_argument("--phase", choices=["setup", "finish"], required=True)
    p.add_argument("--label", default="staging")
    asyncio.run(run(p.parse_args()))
