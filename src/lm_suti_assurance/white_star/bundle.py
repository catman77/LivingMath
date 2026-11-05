"""Private data-only exports; installed frozen code performs independent replay."""

import base64
import io
import json
from pathlib import Path
import zipfile
from .. import core
from ..core import canonical, digest, byte_digest, strict_json
from ..workspace import validate_history
from ..service import require
from ..policy import export_guard
from .contracts import VENDOR, integrity, preflight, source_evidence
from . import blobs

MAX_EXPORT = 64 * 1024 * 1024


def application_digest():
    root = Path(__file__).parent
    return digest(
        {p.name: byte_digest(p.read_bytes()) for p in sorted(root.glob("*.py"))}
    )


def logical(rows, objects):
    return digest(
        [
            (
                {
                    "run_id": objects[r["result"]["record_ref"]]["run_id"],
                    "status": objects[r["result"]["record_ref"]]["status"],
                    "result_digest": objects[r["result"]["record_ref"]][
                        "result_digest"
                    ],
                }
                if r["action"] == "white.finish"
                else {"action": r["action"], "result": r["result"]}
            )
            for r in rows
            if r["action"].startswith("white.") and r["action"] != "white.start"
        ]
    )


def export(workspace):
    with workspace.locked():
        return export_rows(workspace, workspace.history())


def export_rows(workspace, rows, audience="private", include_source_bytes=True):
    require(audience == "private", "PUBLICATION_POLICY_VIOLATION")
    require(bool(rows), "PROJECT_NOT_FOUND")
    refs = {ref for row in rows for ref in row["object_refs"]}
    objects = {r: workspace.get(r) for r in refs}
    dependencies = []
    from ..policy import can_publish

    if not include_source_bytes:
        dependencies.extend(refs)
    for row in rows:
        if row["action"] == "source.add":
            value = objects[row["result"]["source_ref"]]
            if not can_publish(
                value["snapshot"], value["publication_policy"], audience
            ):
                dependencies.append(row["result"]["source_ref"])
    for row in rows:
        if row["action"] == "white.start":
            record = objects[row["result"]["start_ref"]]
            common = objects[record["common_snapshot_ref"]]
            if common["source"]["rights"] not in (
                "PUBLIC_DOMAIN",
                "ORIGINAL_TEST_FIXTURE",
                "USER_AUTHORIZED_PRIVATE",
                "DECLARED_USER_AUTHORIZED",
            ):
                dependencies.append(record["common_snapshot_ref"])
    files = {"journal.jsonl": b"".join((canonical(r) + "\n").encode() for r in rows)}
    if not dependencies:
        files.update(
            {
                "objects/" + r + ".json": canonical(v).encode()
                for r, v in objects.items()
            }
        )
    for raw in files.values():
        export_guard(raw.decode())
    manifest = {
        "schema": "levinmas-white-star-package/1",
        "project": workspace.project,
        "audience": "private",
        "files": {n: byte_digest(v) for n, v in sorted(files.items())},
        "kernel_hashes": integrity(),
        "application_digest": application_digest(),
        **core.identity(),
        "journal_head": rows[-1]["hash"],
        "logical_digest": logical(rows, objects),
        "source_dependencies": sorted(set(dependencies)),
        "R3": "PENDING",
        "execution_permission": False,
    }
    files["package_manifest.json"] = canonical(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            z.writestr(info, raw)
    require(
        len(out.getvalue()) <= 24 * 1024 * 1024
        and sum(len(v) for v in files.values()) <= MAX_EXPORT,
        "BUNDLE_SIZE_LIMIT",
    )
    return out.getvalue(), manifest


def replay_inside_worker(encoded, adapter, ops):
    # Code and native loading already happened in the fixed worker supervisor.
    from ..offline import isolated
    from ..bundle import MemoryWorkspace, replay_rows
    from .formal import evaluate
    from .suti import build_output

    core.identity()
    core.module("checks")
    with isolated():
        raw = base64.b64decode(encoded, validate=True)
        require(len(raw) <= 24 * 1024 * 1024, "BUNDLE_SIZE_LIMIT")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            require(
                len(names) == len(set(names))
                and len(names) <= 4096
                and sum(i.file_size for i in infos) <= MAX_EXPORT,
                "BUNDLE_EXPANSION_LIMIT",
            )
            for i in infos:
                require(
                    not i.filename.startswith("/")
                    and "\\" not in i.filename
                    and not any(p in ("", ".", "..") for p in i.filename.split("/"))
                    and (i.external_attr >> 16) & 0o170000 != 0o120000,
                    "UNSAFE_ZIP_MEMBER",
                )
            files = {i.filename: z.read(i) for i in infos}
        manifest = strict_json(files.pop("package_manifest.json").decode())
        require(
            manifest["schema"] == "levinmas-white-star-package/1"
            and manifest["audience"] == "private"
            and manifest["execution_permission"] is False
            and manifest["R3"] == "PENDING",
            "MANIFEST_INVALID",
        )
        require(
            set(files) == set(manifest["files"])
            and all(byte_digest(v) == manifest["files"][n] for n, v in files.items()),
            "MANIFEST_SHA_MISMATCH",
        )
        require(
            manifest["kernel_hashes"] == integrity()
            and manifest["application_digest"] == application_digest(),
            "MIGRATION_REQUIRED",
        )
        require(
            all(manifest[k] == v for k, v in core.identity().items()),
            "FROZEN_CORE_INTEGRITY_FAILURE",
        )
        require(not manifest["source_dependencies"], "MISSING_SOURCE_DEPENDENCY")
        objects = {}
        for n, v in files.items():
            if n.startswith("objects/") and n.endswith(".json"):
                ref = n[8:-5]
                require(byte_digest(v) == ref, "OBJECT_DIGEST_MISMATCH")
                objects[ref] = strict_json(v.decode())
            else:
                require(n == "journal.jsonl", "UNKNOWN_BUNDLE_MEMBER")
        rows = [
            strict_json(line) for line in files["journal.jsonl"].decode().splitlines()
        ]
        require(
            validate_history(rows) == manifest["journal_head"], "JOURNAL_HEAD_MISMATCH"
        )
        require(
            set(objects) == {r for row in rows for r in row["object_refs"]},
            "OBJECT_SET_MISMATCH",
        )
        workspace = MemoryWorkspace(objects)
        completed = {}
        checks = []
        # Recompute the unchanged assurance actions, retaining their original order.
        old = [r for r in rows if not r["action"].startswith("white.")]
        replay_rows(old, objects, manifest["project"], "direct", audience="private")
        for row in rows:
            if not row["action"].startswith("white."):
                continue
            result = row["result"]
            require(
                result.get("execution_permission") is False, "EXECUTION_GRANT_FORBIDDEN"
            )
            if row["action"] == "white.start":
                start = objects[result["start_ref"]]
                require(
                    start["project"] == manifest["project"], "CROSS_PROJECT_REFERENCE"
                )
                inp = objects[start["input_ref"]]
                common = objects[start["common_snapshot_ref"]]
                require(
                    digest(inp) == start["input_digest"]
                    and digest(common) == start["common_snapshot_sha256"],
                    "INPUT_DIGEST_MISMATCH",
                )
            elif row["action"] == "white.finish":
                record = objects[result["record_ref"]]
                require(
                    record["project"] == manifest["project"], "CROSS_PROJECT_REFERENCE"
                )
                if record["status"] != "COMPLETED":
                    continue
                stored = blobs.get(workspace, record["result_ref"])
                require(
                    digest(stored) == record["result_digest"], "RESULT_DIGEST_MISMATCH"
                )
                inp = objects[record["input_ref"]]
                if record["engine"] == "white_star":
                    preflight(inp)
                    actual = adapter.explore(inp)
                    require(
                        canonical(actual) == canonical(stored),
                        "NUMERIC_REPLAY_MISMATCH",
                    )
                else:
                    common = objects[record["common_snapshot_ref"]]
                    actual = build_output(
                        common,
                        record["common_snapshot_ref"],
                        inp["decoder_slots"],
                        stored["assurance_source_ref"],
                        stored["decisions"],
                    )
                    require(
                        canonical(actual) == canonical(stored),
                        "SUTI_INGRESS_REPLAY_MISMATCH",
                    )
                    for decision in stored["decisions"]:
                        checked = objects[decision["check_ref"]]
                        require(
                            checked["status"]
                            == decision["status"]
                            == "SOURCE_ATTESTED",
                            "SOURCE_ASSURANCE_MISMATCH",
                        )
                completed[record["run_id"]] = (record, stored)
            elif row["action"] == "white.reading":
                require(result["run_id"] in completed, "READING_RUN_MISSING")
                record, stored = completed[result["run_id"]]
                for ref in result["reading_refs"]:
                    reading = objects[ref]
                    require(
                        reading["project"] == manifest["project"]
                        and reading["status"] == "INTERPRETATION",
                        "READING_PROVENANCE_MISMATCH",
                    )
                    require(
                        reading["reading"]["frame_id"]
                        in {f["id"] for f in stored["selected_frames"]},
                        "FRAME_NOT_IN_RUN",
                    )
                    for e in reading["reading"]["evidence"]:
                        source_evidence(
                            stored["common_snapshot"]["source"], e, "/reading/evidence"
                        )
            elif row["action"] == "white.model":
                check = objects[result["check_ref"]]
                proposal = objects[check["proposal_ref"]]
                actual = evaluate(proposal, ops)
                require(
                    canonical(actual) == canonical(check["result"]),
                    "MATRIX_REPLAY_MISMATCH",
                )
                checks.append(actual["status"])
            else:
                require(False, "UNKNOWN_JOURNAL_ACTION")
        require(
            logical(rows, objects) == manifest["logical_digest"],
            "LOGICAL_DIGEST_MISMATCH",
        )
        return {
            "schema": "levinmas-white-star-replay/1",
            "status": "PASS",
            "logical_digest": manifest["logical_digest"],
            "runs_recomputed": len(completed),
            "matrix_statuses": checks,
            "network": "DISABLED",
            "LLM": "NOT_CALLED",
            "OAuth": "NOT_USED",
            "R3": "PENDING",
            "execution_permission": False,
        }


def is_bundle(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info = z.getinfo("package_manifest.json")
            if info.file_size > 262144:
                return False
            return (
                strict_json(z.read(info).decode()).get("schema")
                == "levinmas-white-star-package/1"
            )
    except (ValueError, KeyError, zipfile.BadZipFile, UnicodeError):
        return False
