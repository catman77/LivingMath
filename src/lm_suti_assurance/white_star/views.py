"""Stable whole-record pages and explicit large-artifact fallback."""

import base64
from ..core import canonical, digest
from ..service import require
from . import blobs


def inspect(
    service, project, run_id, view="summary", offset=0, limit=64, artifact_ref=None
):
    w, record = service.load(project, run_id)
    require(
        type(offset) is int
        and offset >= 0
        and type(limit) is int
        and 1 <= limit <= 128,
        "INVALID_INPUT",
    )
    if view == "summary":
        items = [record]
    else:
        require(record["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
        result = blobs.get(w, record["result_ref"])
        if view == "input":
            inp = w.get(record["input_ref"])
            common = w.get(record["common_snapshot_ref"])
            items = [
                {"source": common["source"]},
                {"schema": common["schema"], "uncertainties": common["uncertainties"]},
            ]
            items += [{"concept": c} for c in common["concepts"]] + [
                {"source_relation": r} for r in common["source_relations"]
            ]
            if record["engine"] == "white_star":
                items += [
                    {
                        "projection": {
                            k: v
                            for k, v in inp["encoding"].items()
                            if k
                            not in (
                                "source",
                                "concepts",
                                "source_relations",
                                "uncertainties",
                            )
                        }
                    },
                    {
                        "concept_coordinates": [
                            {
                                "id": c["id"],
                                "coordinates": c["coordinates"],
                                "encoding_rationale": c["encoding_rationale"],
                            }
                            for c in inp["encoding"]["concepts"]
                        ]
                    },
                ]
        elif view == "atlas":
            items = result.get("atlas", {}).get("charts", [])
        elif view == "trace":
            items = result.get("trace", [])
        elif view == "frames":
            items = result["frames"]
        elif view == "decoder":
            items = [result["decoder_packet"]]
        elif view in ("readings", "checks"):
            with w.locked():
                rows = w.history()
            action = "white.reading" if view == "readings" else "white.model"
            refs = [
                ref
                for row in rows
                if row["action"] == action and row["result"]["run_id"] == run_id
                for ref in (
                    row["result"]["reading_refs"]
                    if view == "readings"
                    else [row["result"]["check_ref"]]
                )
            ]
            items = [{"ref": ref, "value": w.get(ref)} for ref in refs]
        elif view == "artifact":
            require(artifact_ref == record["result_ref"], "NOT_FOUND")
            root = w.get(artifact_ref)
            items = [
                {"index": i, "data_base64": w.get(ref)["data"], "chunk_sha256": ref}
                for i, ref in enumerate(root["chunks"])
            ]
        elif view == "report":
            items = [
                {
                    "summary": result["summary"],
                    "boundary": "Numeric novelty is not literary value; source bytes do not certify interpretation",
                    "metrics": record["metrics"],
                    "interpretation_status": "UNASSESSED",
                }
            ]
        elif view == "export":
            from .bundle import export

            raw, manifest = export(w)
            cache = w.path / ".white-star-exports"
            from ..workspace import private_dir, atomic_write

            private_dir(cache)
            ref = __import__("hashlib").sha256(raw).hexdigest()
            target = cache / (ref + ".zip")
            if not target.exists():
                atomic_write(target, raw)
            else:
                require(target.read_bytes() == raw, "EXPORT_INTEGRITY_FAILURE")
            chunks = [raw[n : n + 48 * 1024] for n in range(0, len(raw), 48 * 1024)]
            items = [
                {
                    "bundle_ref": ref,
                    "index": i,
                    "chunk_count": len(chunks),
                    "data_base64": base64.b64encode(chunk).decode(),
                }
                for i, chunk in enumerate(chunks)
            ]
        else:
            require(False, "INVALID_INPUT")
    output = []
    used = 0
    for item in items[offset : offset + limit]:
        size = len(canonical(item).encode())
        if used + size > 112 * 1024:
            break
        output.append(item)
        used += size
    fallback = offset < len(items) and not output
    return {
        "schema": "levinmas-white-star-page/1",
        "project": project,
        "run_id": run_id,
        "view": view,
        "offset": offset,
        "total": len(items),
        "items": output,
        "next_offset": (
            offset + len(output)
            if offset + len(output) < len(items) and not fallback
            else None
        ),
        "requires_artifact": fallback,
        "artifact_ref": record.get("result_ref") if fallback else None,
        "artifact_hint": (
            "Read view=artifact with artifact_ref, concatenate base64 chunks and select requested JSON field"
            if fallback
            else None
        ),
        "execution_permission": False,
    }


def compare(service, project, left, right, protocol):
    lw, lr, lv = service.result(project, left["run_id"])
    rw, rr, rv = service.result(project, right["run_id"])
    require(
        lr["engine"] == left["engine"] and rr["engine"] == right["engine"],
        "INVALID_INPUT",
    )
    same = (
        lr["common_snapshot_sha256"] == rr["common_snapshot_sha256"]
        and lv["common_snapshot"] == rv["common_snapshot"]
    )
    records = []
    for r, v in ((lr, lv), (rr, rv)):
        with lw.locked():
            rows = lw.history()
        readings = [
            lw.get(ref)
            for row in rows
            if row["action"] == "white.reading"
            and row["result"]["run_id"] == r["run_id"]
            for ref in row["result"]["reading_refs"]
        ]
        records.append(
            {
                "run_id": r["run_id"],
                "engine": r["engine"],
                "backend": v.get("backend", "UNCHANGED_WHITE_STAR_CAD_UDAV"),
                "common_snapshot_sha256": r["common_snapshot_sha256"],
                "encoding_or_projection_sha256": v.get(
                    "encoding_sha256", v.get("projection_sha256")
                ),
                "summary": v["summary"],
                "metrics": r["metrics"],
                "decoder_packet_ref": r["result_ref"],
                "decoder_packet_pointer": "/decoder_packet",
                "interpretations": len(readings),
                "decoder_provenance": [
                    v["provenance"].get("declaration") for v in readings
                ],
                "interpretation_refs": [digest(v) for v in readings],
                "interpretation_status": "INTERPRETATION_NOT_VERIFIED",
                "SUTI_native_runtime": "NOT_EXECUTED",
                "projection_losses": {
                    "fields_not_used": (
                        ["coordinates", "axes", "protocol"]
                        if r["engine"] == "suti"
                        else []
                    ),
                    "common_snapshot_fields_lost": [],
                    "scope": "Common snapshot preserved; geometry is a declared separate assumption, not source meaning",
                },
            }
        )
    return {
        "schema": "levinmas-semantic-comparison/1",
        "status": "MATCHED_INPUT" if same else "UNMATCHED_INPUT",
        "requested_mode": protocol["mode"],
        "same_source_bytes": lr["source_sha256"] == rr["source_sha256"],
        "same_common_snapshot": same,
        "runs": records,
        "decoder_protocol_id": protocol["decoder_protocol_id"],
        "LLM_calls_in_comparison": 0,
        "literary_value": "NOT_MEASURED_BY_NUMERIC_COUNTERS",
        "scope": "Actual frozen-source Bridge assurance versus White Star, not native SUTI; no claim of superiority",
        "execution_permission": False,
    }
