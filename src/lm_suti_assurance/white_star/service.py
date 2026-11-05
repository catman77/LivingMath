"""Durable run lifecycle on the existing Workspace, not a parallel database."""

import asyncio
import base64
import time
from pathlib import Path
from ..core import canonical, digest
from ..errors import AssuranceError
from ..service import Service, require
from . import blobs
from .contracts import (
    common_snapshot,
    preflight,
    source_evidence,
    check_schema,
    TOOLS,
    RESPONSE,
)


class WhiteStar:
    def __init__(self, root: str | Path, pool=None):
        self.base = Service(Path(root))
        self.pool = pool
        self.active = set()

    def workspace(self, project):
        return self.base.workspace(project)

    def recover(self):
        if not self.base.root.exists():
            return []
        recovered = []
        for path in sorted(self.base.root.iterdir()):
            if not path.is_dir() or not (path / "journal.jsonl").exists():
                continue
            w = self.workspace(path.name)
            with w.locked():
                rows = w.history()
            ended = {
                r["result"]["run_id"] for r in rows if r["action"] == "white.finish"
            }
            for row in rows:
                if (
                    row["action"] == "white.start"
                    and row["result"]["run_id"] not in ended
                ):
                    record = w.get(row["result"]["start_ref"])
                    self.finish(
                        w,
                        record,
                        None,
                        {
                            "code": "INTERRUPTED",
                            "message": "Server restarted before a committed result",
                            "field_path": "",
                        },
                    )
                    recovered.append(record["run_id"])
        return recovered

    def load(self, project, run_id):
        w = self.workspace(project)
        with w.locked():
            rows = w.history()
            starts = [
                r
                for r in rows
                if r["action"] == "white.start" and r["result"]["run_id"] == run_id
            ]
            require(bool(starts), "NOT_FOUND")
            end = next(
                (
                    r
                    for r in rows
                    if r["action"] == "white.finish" and r["result"]["run_id"] == run_id
                ),
                None,
            )
            return w, (
                w.get(end["result"]["record_ref"])
                if end
                else w.get(starts[0]["result"]["start_ref"])
            )

    def reserve(self, project, key, request, engine):
        w = self.workspace(project)
        payload = {"engine": engine, "request": request}
        ident = digest({"project": project, "request_key": key, "payload": payload})
        fresh = []

        def start(rows):
            # Freeze common bytes before either branch is executed; source validity
            # is checked before native computation, with any failure retained.
            common = (
                common_snapshot(request["encoding"])
                if engine == "white_star"
                else request["common_snapshot"]
            )
            cref = w.put(common)
            iref = w.put(request)
            record = {
                "schema": "levinmas-white-star-run/1",
                "run_id": ident,
                "project": project,
                "engine": engine,
                "status": "RUNNING",
                "request_key": key,
                "input_ref": iref,
                "input_digest": digest(request),
                "common_snapshot_ref": cref,
                "common_snapshot_sha256": digest(common),
                "source_sha256": common["source"]["sha256"],
                "execution_permission": False,
            }
            ref = w.put(record)
            fresh.append(True)
            return {
                "run_id": ident,
                "start_ref": ref,
                "status": "RUNNING",
                "execution_permission": False,
            }, [ref, iref, cref]

        try:
            r = w.transact("white.start", "ws-request:" + digest(key), payload, start)
        except AssuranceError as e:
            if e.code == "REQUEST_KEY_CONFLICT":
                raise AssuranceError("REQUEST_CONFLICT", "/request_key")
            raise
        return w, w.get(r["start_ref"]), bool(fresh)

    def finish(self, w, start, result, error=None, metrics=None):
        def save(rows):
            refs = []
            record = {
                **start,
                "status": (
                    "COMPLETED"
                    if error is None
                    else "INTERRUPTED" if error["code"] == "INTERRUPTED" else "FAILED"
                ),
                "error": error,
                "metrics": metrics or {},
                "result_ref": None,
                "result_digest": None,
            }
            if result is not None:
                ref, rr = blobs.put(w, result)
                refs += rr
                record["result_ref"] = ref
                record["result_digest"] = digest(result)
            ref = w.put(record)
            refs.append(ref)
            return {
                "run_id": start["run_id"],
                "record_ref": ref,
                "status": record["status"],
                "execution_permission": False,
            }, refs

        return w.transact(
            "white.finish",
            "ws-finish:" + start["run_id"],
            {"run_id": start["run_id"]},
            save,
        )

    def compact(self, project, run_id):
        w, record = self.load(project, run_id)
        value = {
            k: record[k]
            for k in (
                "schema",
                "project",
                "run_id",
                "engine",
                "status",
                "common_snapshot_sha256",
                "common_snapshot_ref",
                "source_sha256",
                "execution_permission",
            )
        }
        if record.get("error"):
            e = record["error"]
            raise AssuranceError(
                e["code"], e.get("field_path"), {**e, "run_id": run_id}
            )
        if record["status"] == "COMPLETED":
            result = blobs.get(w, record["result_ref"])
            value.update(
                summary=result["summary"],
                result_ref=record["result_ref"],
                result_digest=record["result_digest"],
                metrics=record["metrics"],
                decoder={
                    "inspect_view": "decoder",
                    "available_slots": len(result["selected_frames"]),
                },
                selected_frame_ids=[f["id"] for f in result["selected_frames"]],
            )
        return value

    async def explore(self, project: str, key: str, request: dict) -> dict:
        # Schema validation must precede even common_snapshot indexing.
        check_schema(
            request, TOOLS["white_star_explore"]["inputSchema"]["properties"]["request"]
        )
        if len(canonical(request).encode()) > 262144:
            raise AssuranceError("INPUT_TOO_LARGE")
        w, start, fresh = await asyncio.to_thread(
            self.reserve, project, key, request, "white_star"
        )
        if fresh:
            task = asyncio.create_task(self.compute(w, start, request))
            self.active.add(task)
            task.add_done_callback(self.active.discard)
            # Client/session cancellation must not abandon an accepted durable run.
            await asyncio.shield(task)
        return await asyncio.to_thread(self.compact, project, start["run_id"])

    async def compute(self, w, start, request):
        began = time.perf_counter()
        try:
            preflight(request)
            if self.pool is None:
                raise AssuranceError("ENGINE_UNAVAILABLE")
            response = await asyncio.to_thread(
                self.pool.run, {"action": "explore", "request": request}
            )
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                response["data"],
                None,
                {
                    **response.get("metrics", {}),
                    "worker_wall_s": response.get("worker_wall_s"),
                    "server_elapsed_s": time.perf_counter() - began,
                    "LLM_calls": 0,
                    "tokens": None,
                    "cost_USD": None,
                },
            )
        except AssuranceError as e:
            await asyncio.to_thread(
                self.finish,
                w,
                start,
                None,
                {
                    "code": e.code,
                    "field_path": e.field or "",
                    "message": (e.details or {}).get("message", e.code),
                },
            )

    def frozen(self, project: str, key: str, common_ref: str, slots: int = 6) -> dict:
        w = self.workspace(project)
        with w.locked():
            rows = w.history()
            require(
                any(
                    r["action"] == "white.start"
                    and w.get(r["result"]["start_ref"])["common_snapshot_ref"]
                    == common_ref
                    for r in rows
                ),
                "NOT_FOUND",
            )
            common = w.get(common_ref)
        from hashlib import sha256

        require(
            sha256(common["source"]["text"].encode()).hexdigest()
            == common["source"]["sha256"],
            "SOURCE_MISMATCH",
        )
        for c in common["concepts"]:
            for e in c["evidence"]:
                source_evidence(
                    common["source"], e, "/common_snapshot/concepts/evidence"
                )
        request = {
            "common_snapshot": common,
            "decoder_slots": slots,
            "ingress": "FROZEN_NO_EXTRACTION",
        }
        w, start, fresh = self.reserve(project, key, request, "suti")
        if fresh:
            began = time.perf_counter()
            try:
                from .suti import run

                result = run(self.base, project, common, common_ref, slots)
                self.finish(
                    w,
                    start,
                    result,
                    None,
                    {
                        "bridge_assurance_s": time.perf_counter() - began,
                        "LLM_calls": 0,
                        "tokens": None,
                        "cost_USD": None,
                    },
                )
            except AssuranceError as e:
                self.finish(
                    w,
                    start,
                    None,
                    {"code": e.code, "field_path": e.field or "", "message": e.code},
                )
        return self.compact(project, start["run_id"])

    def result(self, project, run_id):
        w, r = self.load(project, run_id)
        require(r["status"] == "COMPLETED", "RUN_NOT_COMPLETED")
        return w, r, blobs.get(w, r["result_ref"])

    def readings(
        self,
        project: str,
        run_id: str,
        key: str,
        readings: list[dict],
        provenance: dict | None = None,
    ) -> dict:
        w, r, result = self.result(project, run_id)
        source = result["common_snapshot"]["source"]
        ids = {f["id"] for f in result["selected_frames"]}
        seen = set()
        for i, reading in enumerate(readings):
            require(reading["frame_id"] in ids, "NOT_FOUND")
            require(reading["frame_id"] not in seen, "INVALID_INPUT")
            seen.add(reading["frame_id"])
            require(bool(reading["evidence"]), "EVIDENCE_MISMATCH")
            for j, e in enumerate(reading["evidence"]):
                source_evidence(source, e, f"/readings/{i}/evidence/{j}")
            require(
                len({c["local_id"] for c in reading["claim_atoms"]})
                == len(reading["claim_atoms"]),
                "INVALID_INPUT",
            )

        def save(rows):
            rr = []
            cr = []
            for reading in readings:
                value = {
                    "schema": "levinmas-white-star-reading/1",
                    "project": project,
                    "run_id": run_id,
                    "source_sha256": source["sha256"],
                    "reading": reading,
                    "provenance": {
                        "producer": "CALLING_MCP_CLIENT_LLM_OR_MANUAL; no server model call",
                        "input_run_digest": r["result_digest"],
                        "declaration": provenance,
                        "independently_certified": False,
                    },
                    "status": "INTERPRETATION",
                    "execution_permission": False,
                }
                ref = w.put(value)
                rr.append(ref)
                for claim in reading["claim_atoms"]:
                    cr.append(
                        w.put(
                            {
                                "schema": "levinmas-white-star-claim/1",
                                "project": project,
                                "run_id": run_id,
                                "reading_ref": ref,
                                "frame_id": reading["frame_id"],
                                "atom": claim,
                                "status": "INTERPRETATION",
                                "execution_permission": False,
                            }
                        )
                    )
            return {
                "run_id": run_id,
                "status": "INTERPRETATION",
                "reading_refs": rr,
                "claim_refs": cr,
                "execution_permission": False,
            }, rr + cr

        try:
            return w.transact(
                "white.reading",
                "ws-reading:" + digest({"run": run_id, "key": key}),
                {"run_id": run_id, "readings": readings, "provenance": provenance},
                save,
            )
        except AssuranceError as e:
            if e.code == "REQUEST_KEY_CONFLICT":
                raise AssuranceError("REQUEST_CONFLICT")
            raise

    async def model(self, project: str, run_id: str, proposal: dict) -> dict:
        w, r, result = self.result(project, run_id)
        with w.locked():
            rows = w.history()
            known = {
                ref
                for row in rows
                if row["action"] == "white.reading"
                and row["result"]["run_id"] == run_id
                for ref in row["result"]["claim_refs"]
            }
            require(proposal["claim_ref"] in known, "NOT_FOUND")
            claim = w.get(proposal["claim_ref"])
            require(
                claim["frame_id"] in proposal["frame_refs"]
                and set(proposal["frame_refs"])
                <= {f["id"] for f in result["selected_frames"]},
                "NOT_FOUND",
            )
            key = "ws-model:" + digest({"run_id": run_id, "proposal": proposal})
            prior = next((row for row in rows if row["request_key"] == key), None)
            if prior:
                return prior["result"]
        if self.pool is None:
            raise AssuranceError("ENGINE_UNAVAILABLE")
        response = await asyncio.to_thread(
            self.pool.run, {"action": "model", "proposal": proposal}
        )

        def save(rows):
            p = w.put(proposal)
            value = {
                "schema": "levinmas-white-star-check/1",
                "project": project,
                "run_id": run_id,
                "proposal_ref": p,
                "claim_ref": proposal["claim_ref"],
                "result": response["data"],
                "status": response["data"]["status"],
                "execution_permission": False,
            }
            ref = w.put(value)
            return {"run_id": run_id, "check_ref": ref, **response["data"]}, [p, ref]

        return w.transact(
            "white.model", key, {"run_id": run_id, "proposal": proposal}, save
        )
