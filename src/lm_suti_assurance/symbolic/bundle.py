"""Bounded private data-only bundles; replay executes only installed, bound code."""

import base64, io, zipfile, re
from ..core import canonical, digest, byte_digest, strict_json
from ..workspace import validate_history
from ..white_star import blobs
from ..white_star.contracts import integrity
from ..policy import export_guard
from .kernel import binding, run
from .state import require

MAX = 64 * 1024 * 1024


def export(workspace, run_id):
    with workspace.locked():
        rows = workspace.history()
        selected = [
            r
            for r in rows
            if r["action"] in ("symbolic.start", "symbolic.finish")
            and r["result"]["run_id"] == run_id
        ]
        require(len(selected) == 2, "RUN_NOT_COMPLETED")
        refs = {ref for r in selected for ref in r["object_refs"]}
        objects = {ref: workspace.get(ref) for ref in refs}
        finish = objects[selected[1]["result"]["record_ref"]]
        require(finish["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
        files = {
            "journal.jsonl": b"".join((canonical(r) + "\n").encode() for r in rows)
        }
        files.update(
            {
                "objects/" + ref + ".json": canonical(value).encode()
                for ref, value in objects.items()
            }
        )
        manifest = {
            "schema": "livingmath-symbolic-package/1",
            "project": workspace.project,
            "run_id": run_id,
            "audience": "private",
            "files": {n: byte_digest(raw) for n, raw in sorted(files.items())},
            "kernel_binding": finish["kernel_binding"],
            "numeric_kernel_binding": finish["numeric_kernel_binding"],
            "result_digest": finish["result_digest"],
            "journal_head": rows[-1]["hash"],
            "execution_permission": False,
        }
        require(sum(map(len, files.values())) <= MAX, "BUNDLE_SIZE_LIMIT")
        for raw in files.values():
            export_guard(raw.decode())
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


def replay(encoded, clock):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        require(False, "INVALID_BUNDLE")
    require(len(raw) <= MAX, "BUNDLE_SIZE_LIMIT")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            require(
                len(names) == len(set(names))
                and len(names) <= 1024
                and sum(i.file_size for i in infos) <= MAX,
                "INVALID_BUNDLE",
            )
            require(
                all(
                    n in ("manifest.json", "journal.jsonl")
                    or re.fullmatch(r"objects/[0-9a-f]{64}\.json", n)
                    for n in names
                ),
                "INVALID_BUNDLE",
            )
            files = {i.filename: z.read(i) for i in infos}
        manifest = strict_json(files.pop("manifest.json").decode())
        require(manifest["schema"] == "livingmath-symbolic-package/1", "INVALID_BUNDLE")
        require(manifest["kernel_binding"] == binding(), "KERNEL_BINDING_MISMATCH")
        require(
            manifest["numeric_kernel_binding"] == digest(integrity()),
            "NUMERIC_KERNEL_BINDING_MISMATCH",
        )
        require(
            manifest["files"] == {n: byte_digest(v) for n, v in sorted(files.items())},
            "EXPORT_INTEGRITY_FAILURE",
        )
        rows = [
            strict_json(line) for line in files["journal.jsonl"].decode().splitlines()
        ]
        require(validate_history(rows) == manifest["journal_head"], "HISTORY_BROKEN")
        objects = {
            n[8:-5]: strict_json(v.decode())
            for n, v in files.items()
            if n.startswith("objects/")
        }
        require(
            all(digest(v) == ref for ref, v in objects.items()),
            "ARTIFACT_INTEGRITY_FAILURE",
        )

        class Objects:
            def get(self, ref):
                return objects[ref]

        selected = [
            r
            for r in rows
            if r["action"] in ("symbolic.start", "symbolic.finish")
            and r["result"]["run_id"] == manifest["run_id"]
        ]
        require(
            len(selected) == 2
            and selected[0]["action"] == "symbolic.start"
            and selected[1]["action"] == "symbolic.finish",
            "HISTORY_BROKEN",
        )
        require(
            all(ref in objects for r in selected for ref in r["object_refs"]),
            "MISSING_DEPENDENCIES",
        )
        start = objects[selected[0]["result"]["start_ref"]]
        finish = objects[selected[1]["result"]["record_ref"]]
        require(
            start["project"] == finish["project"] == manifest["project"]
            and start["run_id"] == finish["run_id"] == manifest["run_id"],
            "HISTORY_BROKEN",
        )
        request = objects[start["input_ref"]]
        saved = blobs.get(Objects(), finish["result_ref"])
        computed = run(request, clock)
        require(
            finish["result_digest"]
            == manifest["result_digest"]
            == digest(saved)
            == digest(computed),
            "REPLAY_MISMATCH",
        )
        return {
            "status": "REPLAY_MATCH",
            "run_id": manifest["run_id"],
            "result_digest": digest(computed),
            "kernel_binding": binding(),
            "structural_recomputed": True,
            "journal_hash_chain": "PASS",
            "unrelated_legacy_operations": "NOT_REEXECUTED",
            "execution_permission": False,
        }
    except (
        zipfile.BadZipFile,
        KeyError,
        UnicodeError,
        ValueError,
        RuntimeError,
    ) as exc:
        from ..errors import AssuranceError

        if isinstance(exc, AssuranceError):
            raise
        require(False, "INVALID_BUNDLE")
