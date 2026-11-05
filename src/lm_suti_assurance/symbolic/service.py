"""Append-only symbolic runs in the existing private Workspace, never a new database."""

from pathlib import Path
import asyncio, base64, time
from ..core import digest, canonical
from ..errors import AssuranceError
from ..service import Service
from ..white_star import blobs
from .contracts import validate
from .kernel import binding
from .state import require

VIEWS = {
    "input": "input",
    "operations": "ops_trace",
    "observations": "structural_observations",
    "claims": "equivalence_claims",
    "grammar": "grammar_hypotheses",
    "evaluation": "heldout_eval",
    "history": "history",
    "states": "states",
    "manifest": "manifest",
    "source": "source_map",
    "checks": "checks",
}


class SymbolicService:
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
                    if r["action"] == "symbolic.start"
                    and r["result"]["run_id"] == run_id
                ),
                None,
            )
            require(start is not None, "NOT_FOUND")
            end = next(
                (
                    r
                    for r in rows
                    if r["action"] == "symbolic.finish"
                    and r["result"]["run_id"] == run_id
                ),
                None,
            )
            return w, w.get(
                end["result"]["record_ref"] if end else start["result"]["start_ref"]
            )

    def reserve(self, project, key, request):
        w = self.workspace(project)
        fresh = []

        def commit(rows):
            run_id = digest(
                {
                    "project": project,
                    "request_key": key,
                    "request": request,
                    "kernel_binding": binding(),
                }
            )
            ref = w.put(request)
            start = {
                "schema": "levinmas-white-star-symbolic-run/1",
                "engine": "symbolic_v1",
                "project": project,
                "run_id": run_id,
                "status": "RUNNING",
                "source_sha256": request["source"]["sha256"],
                "input_ref": ref,
                "kernel_binding": binding(),
                "execution_permission": False,
            }
            start_ref = w.put(start)
            fresh.append(True)
            return {
                "run_id": run_id,
                "start_ref": start_ref,
                "status": "RUNNING",
                "execution_permission": False,
            }, [ref, start_ref]

        try:
            value = w.transact(
                "symbolic.start",
                "symbolic-request:" + digest(key),
                {"request": request},
                commit,
            )
        except AssuranceError as exc:
            if exc.code == "REQUEST_KEY_CONFLICT":
                raise AssuranceError("REQUEST_CONFLICT", "/request_key")
            raise
        return w, w.get(value["start_ref"]), bool(fresh)

    def finish(self, w, start, result=None, error=None, metrics=None):
        def commit(rows):
            refs = []
            record = {
                **start,
                "status": (
                    "COMPLETED"
                    if error is None
                    else "INTERRUPTED" if error["code"] == "INTERRUPTED" else "FAILED"
                ),
                "error": error,
                "result_ref": None,
                "result_digest": None,
                "metrics": metrics or {},
            }
            if result is not None:
                ref, stored = blobs.put(w, result)
                refs += stored
                record.update(
                    result_ref=ref,
                    result_digest=digest(result),
                    summary=result["summary"],
                    numeric_kernel_binding=result["manifest"]["numeric_kernel_binding"],
                )
            ref = w.put(record)
            refs.append(ref)
            return {
                "run_id": start["run_id"],
                "record_ref": ref,
                "status": record["status"],
                "execution_permission": False,
            }, refs

        return w.transact(
            "symbolic.finish",
            "symbolic-finish:" + start["run_id"],
            {"run_id": start["run_id"]},
            commit,
        )

    def compact(self, project, run_id):
        _, record = self.load(project, run_id)
        if record.get("error"):
            raise AssuranceError(
                record["error"]["code"],
                record["error"].get("field_path"),
                {**record["error"], "run_id": run_id},
            )
        return {k: v for k, v in record.items() if k not in ("input_ref", "error")}

    async def explore(self, project, key, request):
        validate(request)
        w, start, fresh = await asyncio.to_thread(self.reserve, project, key, request)
        if fresh:
            task = asyncio.create_task(self.compute(w, start, request))
            self.active.add(task)
            task.add_done_callback(self.active.discard)
            await asyncio.shield(task)
        return await asyncio.to_thread(self.compact, project, start["run_id"])

    async def compute(self, w, start, request):
        began = time.perf_counter()
        try:
            require(self.executor is not None, "ENGINE_UNAVAILABLE")
            reply = await asyncio.to_thread(
                self.executor.run, {"action": "explore", "request": request}
            )
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                reply["data"],
                None,
                {
                    **reply.get("metrics", {}),
                    "worker_wall_s": reply.get("worker_wall_s"),
                    "server_elapsed_s": time.perf_counter() - began,
                },
            )
        except AssuranceError as exc:
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                None,
                {
                    "code": exc.code,
                    "field_path": exc.field or "",
                    "message": (exc.details or {}).get("message", exc.code),
                },
            )

    def recover(self):
        recovered = []
        if not self.base.root.exists():
            return recovered
        for d in sorted(self.base.root.iterdir()):
            if not d.is_dir() or not (d / "journal.jsonl").exists():
                continue
            w = self.workspace(d.name)
            with w.locked():
                rows = w.history()
            ended = {
                r["result"]["run_id"] for r in rows if r["action"] == "symbolic.finish"
            }
            for row in rows:
                if (
                    row["action"] == "symbolic.start"
                    and row["result"]["run_id"] not in ended
                ):
                    start = w.get(row["result"]["start_ref"])
                    self.finish(
                        w,
                        start,
                        error={
                            "code": "INTERRUPTED",
                            "message": "Restart before committed result",
                            "field_path": "",
                        },
                    )
                    recovered.append(start["run_id"])
        return recovered

    def inspect(
        self, project, run_id, view="summary", offset=0, limit=32, artifact_ref=None
    ):
        w, record = self.load(project, run_id)
        require(0 <= offset and 1 <= limit <= 128)
        if view == "summary":
            items = [record]
        elif view == "export":
            from .bundle import export
            from ..workspace import private_dir, atomic_write

            raw, manifest = export(w, run_id)
            cache = private_dir(w.path / ".symbolic-exports")
            ref = __import__("hashlib").sha256(raw).hexdigest()
            target = cache / (ref + ".zip")
            if not target.exists():
                atomic_write(target, raw)
            else:
                require(target.read_bytes() == raw, "ARTIFACT_INTEGRITY_FAILURE")
            chunks = [raw[i : i + 49152] for i in range(0, len(raw), 49152)]
            items = [
                {
                    "bundle_ref": ref,
                    "index": i,
                    "chunk_count": len(chunks),
                    "data_base64": base64.b64encode(chunk).decode(),
                }
                for i, chunk in enumerate(chunks)
            ]
        elif view == "artifact":
            require(artifact_ref == record.get("result_ref"), "NOT_FOUND")
            root = w.get(artifact_ref)
            items = [
                {"index": i, "data_base64": w.get(ref)["data"]}
                for i, ref in enumerate(root["chunks"])
            ]
        else:
            require(record["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
            value = blobs.get(w, record["result_ref"])
            if view == "report":
                items = [
                    {
                        "summary": value["summary"],
                        "checks": value["checks"],
                        "grammar_status": [
                            g["status"] for g in value["grammar_hypotheses"]
                        ],
                        "boundary": "Finite exact word identities and empirical grammar hypotheses; no semantic or physical verification.",
                    }
                ]
            else:
                require(view in VIEWS, "INVALID_VIEW")
                v = value[VIEWS[view]]
                items = v if isinstance(v, list) else [v]
        out = []
        size = 0
        for item in items[offset : offset + limit]:
            n = len(canonical(item).encode())
            if size + n > 112 * 1024:
                break
            out.append(item)
            size += n
        fallback = offset < len(items) and not out
        return {
            "schema": "levinmas-white-star-symbolic-page/1",
            "project": project,
            "run_id": run_id,
            "view": view,
            "items": out,
            "offset": offset,
            "total": len(items),
            "next_offset": (
                offset + len(out)
                if offset + len(out) < len(items) and not fallback
                else None
            ),
            "requires_artifact": fallback,
            "artifact_ref": record.get("result_ref") if fallback else None,
            "artifact_hint": (
                "Read artifact chunks, concatenate base64, decode complete JSON"
                if fallback
                else None
            ),
            "execution_permission": False,
        }
