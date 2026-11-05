"""Reuse the private atomic workspace/worker pool; append-only extension lifecycles."""

import asyncio, base64, json
from pathlib import Path
from ..core import digest, canonical, strict_json
from ..errors import AssuranceError
from ..service import Service
from ..symbolic.service import SymbolicService
from ..symbolic.state import require
from ..white_star import blobs
from ..workspace import private_dir, atomic_write
from ..observer_synthesis.data import validate_dataset
from .app import binding


class ExtensionService:
    def __init__(self, root, executor):
        self.base = Service(Path(root))
        self.executor = executor
        self.active = set()

    def workspace(self, project):
        return self.base.workspace(project)

    def load(self, project, run_id):
        w = self.workspace(project)
        with w.locked():
            rows = w.history()
            start = next(
                (
                    r
                    for r in rows
                    if r["action"] == "extension.start"
                    and r["result"]["run_id"] == run_id
                ),
                None,
            )
            require(start is not None, "NOT_FOUND")
            end = next(
                (
                    r
                    for r in rows
                    if r["action"] == "extension.finish"
                    and r["result"]["run_id"] == run_id
                ),
                None,
            )
            return w, w.get(
                end["result"]["record_ref"] if end else start["result"]["start_ref"]
            )

    def dataset_store(self, project, key, dataset):
        validate_dataset(dataset)
        w = self.workspace(project)

        def commit(rows):
            if dataset["kind"] == "collection":
                count = 0
                for ref in dataset["parts"]:
                    part = self.get_dataset(w, ref)
                    require(
                        part["kind"] == dataset["record_kind"]
                        and part["kind"] != "collection",
                        "DATASET_KIND_MISMATCH",
                    )
                    count += len(part["records"])
                require(count <= 2048, "BUDGET_EXCEEDED", "/dataset/parts")
            ref, refs = blobs.put(w, dataset)
            return {
                "dataset_ref": ref,
                "kind": dataset["kind"],
                "sha256": dataset["sha256"],
                "record_count": (
                    len(dataset.get("records", []))
                    if dataset["kind"] != "collection"
                    else count
                ),
                "execution_permission": False,
            }, refs

        return w.transact(
            "extension.dataset",
            "extension.dataset:" + digest(key),
            {"dataset": dataset},
            commit,
        )

    def get_dataset(self, w, ref):
        require(
            ref
            in {
                r["result"].get("dataset_ref")
                for r in w.history()
                if r["action"] == "extension.dataset"
            },
            "NOT_FOUND",
            "/dataset_ref",
        )
        return blobs.get(w, ref)

    def records(self, w, ref, kind):
        data = self.get_dataset(w, ref)
        if data["kind"] == "collection":
            require(data["record_kind"] == kind, "DATASET_KIND_MISMATCH")
            values = []
            for part in data["parts"]:
                item = self.get_dataset(w, part)
                require(item["kind"] == kind, "DATASET_KIND_MISMATCH")
                values += item["records"]
            return values
        require(data["kind"] == kind, "DATASET_KIND_MISMATCH")
        return data["records"]

    def resolve(self, project, engine, request):
        w = self.workspace(project)
        if engine == "observer_synthesis_v1":
            result = {
                "train": self.records(w, request["task"]["train_ref"], "train"),
                "queries": self.records(w, request["task"]["predict_ref"], "queries"),
            }
            if request.get("source_run_id"):
                _, r = SymbolicService(self.base.root, None).load(
                    project, request["source_run_id"]
                )
                require(r["status"] == "COMPLETED", "SOURCE_NOT_COMPLETED")
                result["source_result_digest"] = r["result_digest"]
            return result
        if request["complex_source"]["kind"] == "saved_symbolic_history":
            source = request["complex_source"]
            require(
                source["project"] == project,
                "PROJECT_ISOLATION",
                "/complex_source/project",
            )
            sw, r = SymbolicService(self.base.root, None).load(
                project, source["run_id"]
            )
            require(r["status"] == "COMPLETED", "SOURCE_NOT_COMPLETED")
            return {"source_artifact": blobs.get(sw, r["result_ref"])}
        return {}

    def reserve(self, project, key, engine, request):
        w = self.workspace(project)
        fresh = []
        resolved = self.resolve(project, engine, request)

        def commit(rows):
            packet = {
                "action": "extension_run",
                "engine": engine,
                "request": request,
                "resolved": resolved,
            }
            snapshot, refs = blobs.put(w, packet)
            run_id = digest(
                {
                    "project": project,
                    "request_key": key,
                    "packet_digest": digest(packet),
                    "kernel_binding": binding(),
                }
            )
            start = {
                "schema": "livingmath-symbolic-extension-run/1",
                "project": project,
                "run_id": run_id,
                "engine": engine,
                "status": "RUNNING",
                "snapshot_ref": snapshot,
                "kernel_binding": binding(),
                "execution_permission": False,
            }
            ref = w.put(start)
            fresh.append(True)
            return {"run_id": run_id, "start_ref": ref, "status": "RUNNING"}, [
                ref,
                *refs,
            ]

        value = w.transact(
            "extension.start",
            "extension.start:" + digest([engine, key]),
            {"engine": engine, "request": request},
            commit,
        )
        return w, w.get(value["start_ref"]), bool(fresh)

    def finish(self, w, start, data=None, error=None, metrics=None):
        def commit(rows):
            record = {
                **start,
                "status": "COMPLETED" if error is None else "FAILED",
                "error": error,
                "metrics": metrics or {},
            }
            refs = []
            if data is not None:
                ref, stored = blobs.put(w, data)
                refs += stored
                sections = {}
                for name in [
                    "vertices",
                    "edges",
                    "peaks",
                    "cells",
                    "homology",
                    "paths",
                    "observer_provenance",
                    "model",
                    "candidate_rules",
                    "pairwise_eval",
                    "diagnostics",
                    "checks",
                    "manifest",
                ]:
                    if name in data:
                        sr, srefs = blobs.put(w, data[name])
                        sections[name] = sr
                        refs += srefs
                record.update(
                    result_ref=ref,
                    result_digest=digest(data),
                    summary=data["summary"],
                    section_refs=sections,
                )
            ref = w.put(record)
            refs.append(ref)
            return {
                "run_id": start["run_id"],
                "record_ref": ref,
                "status": record["status"],
            }, refs

        return w.transact(
            "extension.finish",
            "extension.finish:" + start["run_id"],
            {"run_id": start["run_id"]},
            commit,
        )

    async def run(self, project, key, engine, request):
        w, start, fresh = await asyncio.to_thread(
            self.reserve, project, key, engine, request
        )
        if fresh:
            task = asyncio.create_task(self.compute(w, start))
            self.active.add(task)
            task.add_done_callback(self.active.discard)
            await asyncio.shield(task)
        return (await asyncio.to_thread(self.load, project, start["run_id"]))[1]

    async def compute(self, w, start):
        try:
            packet = await asyncio.to_thread(blobs.get, w, start["snapshot_ref"])
            reply = await asyncio.to_thread(self.executor.run, packet)
            await asyncio.to_thread(
                self.finish, w, start, reply["data"], None, reply.get("metrics")
            )
        except AssuranceError as exc:
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                None,
                {"code": exc.code, "field_path": exc.field or ""},
            )
        except Exception:
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                None,
                {"code": "INTERNAL_EXTENSION_ERROR", "field_path": ""},
            )

    def recover(self):
        for folder in sorted(self.base.root.iterdir()):
            if not folder.is_dir() or not (folder / "journal.jsonl").exists():
                continue
            w = self.workspace(folder.name)
            rows = w.history()
            finished = {
                r["result"]["run_id"] for r in rows if r["action"] == "extension.finish"
            }
            for row in rows:
                if (
                    row["action"] == "extension.start"
                    and row["result"]["run_id"] not in finished
                ):
                    self.finish(
                        w,
                        w.get(row["result"]["start_ref"]),
                        error={"code": "INTERRUPTED", "field_path": ""},
                    )

    def inspect(
        self, project, run_id, view="summary", offset=0, limit=32, artifact_ref=None
    ):
        w, record = self.load(project, run_id)
        require(0 <= offset and 1 <= limit <= 128, "INVALID_INPUT")
        if view == "summary":
            items = [record]
            ref = None
        elif view == "export":
            from .bundle import export

            # Freeze the first export prefix for this immutable run. Holding the
            # same workspace lock also prevents two first-page callers racing.
            with w.locked():
                cache = private_dir(w.path / ".extension-exports")
                index = cache / ("run-" + run_id + ".json")
                require(not index.is_symlink(), "SYMLINK_FORBIDDEN")
                if index.exists():
                    require(index.stat().st_size <= 1024, "EXPORT_INTEGRITY_FAILURE")
                    metadata = strict_json(index.read_text())
                    ref = metadata.get("bundle_ref", "")
                    require(
                        metadata.get("run_id") == run_id
                        and len(ref) == 64
                        and all(c in "0123456789abcdef" for c in ref),
                        "EXPORT_INTEGRITY_FAILURE",
                    )
                    target = cache / (ref + ".zip")
                    require(
                        not target.is_symlink()
                        and target.is_file()
                        and target.stat().st_size <= 64 * 1024 * 1024,
                        "EXPORT_INTEGRITY_FAILURE",
                    )
                    raw = target.read_bytes()
                    require(
                        __import__("hashlib").sha256(raw).hexdigest() == ref,
                        "EXPORT_INTEGRITY_FAILURE",
                    )
                else:
                    raw, _ = export(w, run_id, rows=w.history())
                    ref = __import__("hashlib").sha256(raw).hexdigest()
                    target = cache / (ref + ".zip")
                    require(not target.is_symlink(), "SYMLINK_FORBIDDEN")
                    if target.exists():
                        require(target.read_bytes() == raw, "EXPORT_INTEGRITY_FAILURE")
                    else:
                        atomic_write(target, raw)
                    atomic_write(
                        index,
                        canonical(
                            {
                                "schema": "livingmath-run-export-snapshot/1",
                                "run_id": run_id,
                                "bundle_ref": ref,
                            }
                        ).encode(),
                    )
            total = (len(raw) + 49151) // 49152
            values = (
                []
                if offset >= total
                else [
                    {
                        "bundle_ref": ref,
                        "index": offset,
                        "chunk_count": total,
                        "data_base64": base64.b64encode(
                            raw[offset * 49152 : (offset + 1) * 49152]
                        ).decode(),
                    }
                ]
            )
            return {
                "schema": "livingmath-symbolic-extension-page/1",
                "project": project,
                "run_id": run_id,
                "view": view,
                "items": values,
                "total": total,
                "offset": offset,
                "next_offset": (
                    offset + len(values) if offset + len(values) < total else None
                ),
                "requires_artifact": False,
                "artifact_ref": None,
                "execution_permission": False,
            }
        elif view == "artifact":
            require(
                artifact_ref == record.get("result_ref")
                or artifact_ref in record.get("section_refs", {}).values(),
                "NOT_FOUND",
                "/artifact_ref",
            )
            root = w.get(artifact_ref)
            total = len(root["chunks"])
            values = (
                []
                if offset >= total
                else [
                    {
                        "index": offset,
                        "data_base64": w.get(root["chunks"][offset])["data"],
                    }
                ]
            )
            return {
                "schema": "livingmath-symbolic-extension-page/1",
                "project": project,
                "run_id": run_id,
                "view": view,
                "items": values,
                "total": total,
                "offset": offset,
                "next_offset": (
                    offset + len(values) if offset + len(values) < total else None
                ),
                "requires_artifact": False,
                "artifact_ref": artifact_ref,
                "artifact_sha256": root["sha256"],
                "artifact_bytes": root["bytes"],
                "execution_permission": False,
            }
        else:
            require(record["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
            ref = record["section_refs"].get(view)
            require(ref is not None, "INVALID_VIEW", "/view")
            value = blobs.get(w, ref)
            items = value if isinstance(value, list) else [value]
        values = []
        size = 0
        for item in items[offset : offset + limit]:
            count = len(canonical(item).encode())
            if size + count > 112 * 1024:
                break
            values.append(item)
            size += count
        fallback = offset < len(items) and not values
        return {
            "schema": "livingmath-symbolic-extension-page/1",
            "project": project,
            "run_id": run_id,
            "view": view,
            "items": values,
            "total": len(items),
            "offset": offset,
            "next_offset": (
                offset + len(values)
                if offset + len(values) < len(items) and not fallback
                else None
            ),
            "requires_artifact": fallback,
            "artifact_ref": ref,
            "execution_permission": False,
        }

    async def verify(self, project, run_id, certificate_ref=None, certificate=None):
        w, record = self.load(project, run_id)
        require(
            record["engine"] == "symbolic_complex_v1"
            and record["status"] == "COMPLETED",
            "INVALID_COMPLEX_RUN",
        )
        data = await asyncio.to_thread(blobs.get, w, record["result_ref"])
        if certificate_ref is not None:
            require(
                certificate_ref in record["section_refs"].values(),
                "NOT_FOUND",
                "/certificate_ref",
            )
            field = next(
                k for k, v in record["section_refs"].items() if v == certificate_ref
            )
            require(
                field in ("paths", "homology"),
                "UNSUPPORTED_CERTIFICATE",
                "/certificate_ref",
            )
            data[field] = await asyncio.to_thread(blobs.get, w, certificate_ref)
        if certificate:
            for name, value in certificate.items():
                data[name] = value
        return (
            await asyncio.to_thread(
                self.executor.run, {"action": "complex_verify", "artifact": data}
            )
        )["data"]
