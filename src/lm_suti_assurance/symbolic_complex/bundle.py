"""Data-only extension packages replay through installed hash-bound engines."""

import base64, io, zipfile, re
from contextlib import nullcontext
from ..core import canonical, digest, byte_digest, strict_json
from ..workspace import validate_history
from ..white_star import blobs
from ..symbolic.state import require
from ..policy import export_guard

MAX = 64 * 1024 * 1024


def export(w, run_id, rows=None):
    with w.locked() if rows is None else nullcontext():
        rows = w.history() if rows is None else rows
        selected = [
            r
            for r in rows
            if r["action"] in ("extension.start", "extension.finish")
            and r["result"]["run_id"] == run_id
        ]
        require(len(selected) == 2, "RUN_NOT_COMPLETED")
        refs = {i for row in selected for i in row["object_refs"]}
        objects = {r: w.get(r) for r in refs}
        finish = objects[selected[1]["result"]["record_ref"]]
        require(finish["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
        files = {
            "journal.jsonl": b"".join((canonical(r) + "\n").encode() for r in rows)
        }
        files.update(
            {
                "objects/" + r + ".json": canonical(o).encode()
                for r, o in objects.items()
            }
        )
        require(sum(len(b) for b in files.values()) <= MAX, "BUNDLE_SIZE_LIMIT")
        for raw in files.values():
            export_guard(raw.decode())
        manifest = {
            "schema": "livingmath-symbolic-extension-package/1",
            "project": w.project,
            "run_id": run_id,
            "engine": finish["engine"],
            "kernel_binding": finish["kernel_binding"],
            "result_digest": finish["result_digest"],
            "files": {n: byte_digest(b) for n, b in sorted(files.items())},
            "journal_head": rows[-1]["hash"],
            "execution_permission": False,
        }
        files["manifest.json"] = canonical(manifest).encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, raw in sorted(files.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                z.writestr(info, raw)
        require(out.tell() <= MAX, "BUNDLE_SIZE_LIMIT")
        return out.getvalue(), manifest


def replay(encoded):
    from .app import binding, execute

    try:
        raw = base64.b64decode(encoded, validate=True)
        require(len(raw) <= MAX, "BUNDLE_SIZE_LIMIT")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            require(
                len(names) == len(set(names))
                and len(names) <= 2048
                and sum(i.file_size for i in infos) <= MAX,
                "INVALID_BUNDLE",
            )
            require(
                all(
                    n in ("manifest.json", "journal.jsonl")
                    or re.fullmatch("objects/[0-9a-f]{64}\\.json", n)
                    for n in names
                ),
                "INVALID_BUNDLE",
            )
            files = {i.filename: z.read(i) for i in infos}
        m = strict_json(files.pop("manifest.json").decode())
        require(
            m["schema"] == "livingmath-symbolic-extension-package/1"
            and m["kernel_binding"] == binding(),
            "KERNEL_BINDING_MISMATCH",
        )
        require(
            m["files"] == {n: byte_digest(b) for n, b in sorted(files.items())},
            "EXPORT_INTEGRITY_FAILURE",
        )
        rows = [
            strict_json(line) for line in files["journal.jsonl"].decode().splitlines()
        ]
        require(validate_history(rows) == m["journal_head"], "HISTORY_BROKEN")
        objects = {
            n[8:-5]: strict_json(b.decode())
            for n, b in files.items()
            if n.startswith("objects/")
        }
        require(
            all(digest(o) == r for r, o in objects.items()),
            "ARTIFACT_INTEGRITY_FAILURE",
        )

        class Store:
            def get(self, ref):
                return objects[ref]

        selected = [
            r
            for r in rows
            if r["action"] in ("extension.start", "extension.finish")
            and r["result"]["run_id"] == m["run_id"]
        ]
        require(
            len(selected) == 2
            and selected[0]["action"] == "extension.start"
            and selected[1]["action"] == "extension.finish",
            "HISTORY_BROKEN",
        )
        require(
            all(ref in objects for row in selected for ref in row["object_refs"]),
            "MISSING_DEPENDENCIES",
        )
        start = objects[selected[0]["result"]["start_ref"]]
        finish = objects[selected[1]["result"]["record_ref"]]
        require(
            start["project"] == finish["project"] == m["project"]
            and start["run_id"] == finish["run_id"] == m["run_id"],
            "HISTORY_BROKEN",
        )
        packet = blobs.get(Store(), start["snapshot_ref"])
        saved = blobs.get(Store(), finish["result_ref"])
        result = execute(packet["engine"], packet["request"], packet["resolved"])
        require(
            digest(result)
            == digest(saved)
            == finish["result_digest"]
            == m["result_digest"],
            "REPLAY_MISMATCH",
        )
        return {
            "status": "REPLAY_MATCH",
            "run_id": m["run_id"],
            "engine": m["engine"],
            "result_digest": digest(result),
            "kernel_binding": binding(),
            "journal_hash_chain": "PASS",
            "independent_checks": result["checks"],
            "execution_permission": False,
        }
    except (ValueError, KeyError, UnicodeError, zipfile.BadZipFile):
        require(False, "INVALID_BUNDLE")
