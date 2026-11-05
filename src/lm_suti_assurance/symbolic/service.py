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
    "diagnostics": "search_diagnostics",
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
        self,
        project,
        run_id,
        view="summary",
        offset=0,
        limit=32,
        artifact_ref=None,
        compare_run_id=None,
    ):
        w, record = self.load(project, run_id)
        require(0 <= offset and 1 <= limit <= 128)
        if view == "comparison":
            require(
                compare_run_id is not None, "COMPARE_RUN_ID_REQUIRED", "/compare_run_id"
            )
            compared = self.compare(project, run_id, compare_run_id)
            require(
                len(canonical(compared).encode()) <= 112 * 1024, "COMPARISON_TOO_LARGE"
            )
            items = [compared]
        elif view == "summary":
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
                v = value.get(
                    VIEWS[view],
                    [
                        {
                            "status": "NOT_RECORDED_IN_HISTORICAL_PROFILE",
                            "kind": "observed",
                        }
                    ],
                )
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

    def compare(self, project: str, left_id: str, right_id: str) -> dict:
        """Compare actual saved roots/paths, never their aggregate summary counts."""
        from .state import alpha_corpus, reduce_sp

        lw, lr = self.load(project, left_id)
        rw, rr = self.load(project, right_id)
        require(lr["status"] == rr["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
        left = blobs.get(lw, lr["result_ref"])
        right = blobs.get(rw, rr["result_ref"])
        ls = next(s for s in left["states"] if s["node_id"] == left["root_node_id"])
        rs = next(s for s in right["states"] if s["node_id"] == right["root_node_id"])
        a, b = ls["tokens"], rs["tokens"]

        def topology(s):
            return sorted({(p, k) for p, k, _ in s["boundaries"]})

        scope = left["input"]["segmentation"]["renaming_scope"]
        require(
            scope == right["input"]["segmentation"]["renaming_scope"],
            "COMPARISON_SCOPE_MISMATCH",
        )

        def pattern(s):
            cuts = sorted(
                {0, len(s["tokens"])}
                | {p for p, k, _ in s["boundaries"] if k == "record_start"}
            )
            words = (
                [s["tokens"][x:y] for x, y in zip(cuts, cuts[1:])]
                if scope == "local"
                else [s["tokens"]]
            )
            return {"pattern": alpha_corpus(words, scope), "boundaries": topology(s)}

        changed = next(
            (
                i
                for i in range(max(len(a), len(b)))
                if i >= len(a) or i >= len(b) or a[i] != b[i]
            ),
            None,
        )

        def at(s, i):
            return {
                "position": i,
                "token": (
                    s["tokens"][i] if i is not None and i < len(s["tokens"]) else None
                ),
                "original_byte_spans": (
                    s["source_spans"][i]
                    if i is not None and i < len(s["tokens"])
                    else []
                ),
            }

        sp = None
        sp_witness = {
            "applicable": False,
            "reason": "SP algebra must be declared in both runs",
        }
        if (
            left["input"]["algebra"]["kind"]
            == right["input"]["algebra"]["kind"]
            == "SP"
        ):
            an, ae = reduce_sp(a)
            bn, be = reduce_sp(b)
            aq = a.count("S") - a.count("P")
            bq = b.count("S") - b.count("P")
            sp = an == bn
            sp_witness = {
                "applicable": True,
                "q_left": aq,
                "q_right": bq,
                "same_zero_status": (aq == 0) == (bq == 0),
                "left_normal_form": list(an),
                "right_normal_form": list(bn),
                "left_reduction_route": ae,
                "right_reduction_route": be,
                "sign_duality_holds": bq == -aq,
                "scope": "SP/PS cancellation; zero status and q-sign are distinct properties",
            }
        same_index = left["input"]["observers"] == right["input"]["observers"]
        lo = [o["observers"] for o in left["structural_observations"]]
        ro = [o["observers"] for o in right["structural_observations"]]
        compared = {
            "schema": "livingmath-symbolic-comparison/1",
            "project": project,
            "left_run_id": left_id,
            "right_run_id": right_id,
            "same_literal": a == b and topology(ls) == topology(rs),
            "same_alpha": pattern(ls) == pattern(rs),
            "same_sp_normal_form": sp,
            "same_history": left["history"] == right["history"],
            "same_op_trace": left["ops_trace"] == right["ops_trace"],
            "same_observer_signature": lo == ro if same_index else None,
            "source_sha256_equal": lr["source_sha256"] == rr["source_sha256"],
            "literal_witness": {
                "first_different_token": changed,
                "left": at(ls, changed),
                "right": at(rs, changed),
                "left_word_hash": ls["word_hash"],
                "right_word_hash": rs["word_hash"],
                "left_boundaries": topology(ls),
                "right_boundaries": topology(rs),
            },
            "alpha_witness": {
                "scope": scope,
                "left": pattern(ls),
                "right": pattern(rs),
            },
            "composition_witness": {
                "left_declared_segments": left["source_map"]["declared_hierarchy"],
                "right_declared_segments": right["source_map"]["declared_hierarchy"],
                "left_concat_nodes": [
                    n["node_id"] for n in left["history"] if n["op"] == "CONCAT"
                ],
                "right_concat_nodes": [
                    n["node_id"] for n in right["history"] if n["op"] == "CONCAT"
                ],
                "boundary": "Only supplied segments and actually saved operations; no inferred semantic syntax",
            },
            "sp_witness": sp_witness,
            "history_witness": {
                "left_digest": digest(left["history"]),
                "right_digest": digest(right["history"]),
                "left_trace_digest": digest(left["ops_trace"]),
                "right_trace_digest": digest(right["ops_trace"]),
            },
            "observer_witness": {
                "same_index": same_index,
                "left_index": left["input"]["observers"],
                "right_index": right["input"]["observers"],
                "left_digest": digest(lo),
                "right_digest": digest(ro),
                "scope": "finite saved observations, not universal indistinguishability",
            },
            "kind": "observed",
            "non_claims": [
                "semantic_equivalence",
                "universal_invariant",
                "verified_truth",
            ],
            "execution_permission": False,
        }

        from ..core import strict_json

        return strict_json(canonical(compared))
