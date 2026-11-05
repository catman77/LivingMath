"""Seven real additive tools over the existing authenticated MCP and worker pool."""

import asyncio, base64, copy, hashlib
from pathlib import Path
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from ..core import canonical
from ..errors import AssuranceError
from ..symbolic.contracts import obj, arr, PROJECT, KEY, REF, integer
from ..white_star.mcp import RawMetadata
from ..white_star.contracts import RESPONSE as OLD_RESPONSE
from ..symbolic.state import require
from ..observer_synthesis.contracts import REQUEST as OBSERVER_REQUEST, DATASET
from .contracts import REQUEST, validate, VERSION, WORKER_LIMITS
from .service import ExtensionService
from .app import binding

VIEWS = [
    "summary",
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
    "export",
    "artifact",
]
INSPECT = obj(
    {
        "project": PROJECT,
        "run_id": REF,
        "view": {"enum": VIEWS},
        "offset": integer(0, 1000000),
        "limit": integer(1, 128),
        "artifact_ref": REF,
    },
    ["project", "run_id"],
)
CERTIFICATE = obj(
    {
        "vertices": arr({"type": "object"}, 8192),
        "edges": arr({"type": "object"}, 16384),
        "cells": arr({"type": "object"}, 5000),
        "peaks": arr({"type": "object"}, 20000),
        "paths": {"type": ["object", "null"]},
        "homology": {"type": "object"},
    }
)
TOOLS = {
    "white_star_symbolic_complex_analyze": obj(
        {"project": PROJECT, "request_key": KEY, "request": REQUEST},
        ["project", "request_key", "request"],
    ),
    "white_star_symbolic_complex_inspect": INSPECT,
    "white_star_symbolic_complex_verify": obj(
        {
            "project": PROJECT,
            "run_id": REF,
            "certificate_ref": REF,
            "certificate": CERTIFICATE,
        },
        ["project", "run_id"],
    ),
    "white_star_symbolic_dataset_store": obj(
        {"project": PROJECT, "request_key": KEY, "dataset": DATASET},
        ["project", "request_key", "dataset"],
    ),
    "white_star_symbolic_observer_synthesize": obj(
        {"project": PROJECT, "request_key": KEY, "request": OBSERVER_REQUEST},
        ["project", "request_key", "request"],
    ),
    "white_star_symbolic_observer_inspect": INSPECT,
    "white_star_symbolic_extension_replay": obj(
        {"project": PROJECT, "bundle_ref": REF}, ["project", "bundle_ref"]
    ),
}
RESPONSE = copy.deepcopy(OLD_RESPONSE)
RESPONSE["properties"]["schema"] = {"const": "livingmath-symbolic-extension-response/1"}


def capabilities(executor):
    ready = bool(executor and executor.status()["ready"])
    return {
        "symbolic_complex_v1": {
            "version": VERSION,
            "status": "READY" if ready else "ENGINE_UNAVAILABLE",
            "kernel_binding": binding(),
            "max_fixture_length": 10,
            "proof_boundary": "Only explicitly defined finite SP 2-complex with independently checked local peak/strict-length proof; H1 alone proves no pi1 claim.",
            "request_schema": REQUEST,
            "limits": WORKER_LIMITS,
            "execution_permission": False,
        },
        "observer_synthesis_v1": {
            "version": "observer_synthesis_v1/1-patch003",
            "status": "READY" if ready else "ENGINE_UNAVAILABLE",
            "kernel_binding": binding(),
            "request_schema": OBSERVER_REQUEST,
            "limits": {
                "train_records": 2048,
                "query_records": 1024,
                "dataset_parts": 64,
                "max_total_tokens": 131072,
                "worker": WORKER_LIMITS,
            },
            "proof_boundary": "Train-only empirical candidates and builtin origin audit; sealed queries contain no labels; UNDERDETERMINED is not a theorem.",
            "execution_permission": False,
        },
        "pairwise_context_v1": {
            "status": "READY" if ready else "ENGINE_UNAVAILABLE",
            "version": "pairwise_context_v1/1",
            "statuses": ["PREFERENCE", "TIE", "NOT_IDENTIFIABLE", "UNDERDETERMINED"],
            "semantic_truth_claimed": False,
        },
    }


def register_tools(server, root, executor, recover=False):
    service = ExtensionService(root, executor)
    if recover:
        service.recover()

    def result(data=None, error=None):
        value = {
            "schema": "livingmath-symbolic-extension-response/1",
            "ok": error is None,
            "status": data.get("status", "OK") if error is None else "ERROR",
            "execution_permission": False,
        }
        value["data" if error is None else "error"] = data if error is None else error
        from ..white_star.contracts import check_schema

        check_schema(value, RESPONSE)
        return CallToolResult(
            structuredContent=value,
            content=[TextContent(type="text", text=canonical(value))],
            isError=error is not None,
        )

    async def dispatch(name, args):
        try:
            validate(args, TOOLS[name])
            if name == "white_star_symbolic_dataset_store":
                data = await asyncio.to_thread(
                    service.dataset_store,
                    args["project"],
                    args["request_key"],
                    args["dataset"],
                )
            elif name in (
                "white_star_symbolic_complex_analyze",
                "white_star_symbolic_observer_synthesize",
            ):
                engine = (
                    "symbolic_complex_v1"
                    if name.endswith("analyze")
                    else "observer_synthesis_v1"
                )
                data = await service.run(
                    args["project"], args["request_key"], engine, args["request"]
                )
                if data["status"] == "FAILED":
                    raise AssuranceError(
                        data["error"]["code"],
                        data["error"].get("field_path"),
                        {"run_id": data["run_id"]},
                    )
            elif name.endswith("_inspect"):
                data = await asyncio.to_thread(service.inspect, **args)
            elif name.endswith("_verify"):
                data = await service.verify(**args)
            else:
                w = service.workspace(args["project"])
                target = w.path / ".extension-exports" / (args["bundle_ref"] + ".zip")
                require(not target.is_symlink() and target.is_file(), "NOT_FOUND")
                raw = target.read_bytes()
                require(
                    hashlib.sha256(raw).hexdigest() == args["bundle_ref"],
                    "EXPORT_INTEGRITY_FAILURE",
                )
                data = (
                    await asyncio.to_thread(
                        executor.run,
                        {
                            "action": "extension_replay",
                            "bundle_base64": base64.b64encode(raw).decode(),
                        },
                    )
                )["data"]
            return result(data=data)
        except AssuranceError as exc:
            return result(
                error={
                    "code": exc.code,
                    "message": (exc.details or {}).get("message", exc.code),
                    "field_path": exc.field or "",
                    "run_id": (exc.details or {}).get("run_id", args.get("run_id")),
                }
            )

    descriptions = {
        "white_star_symbolic_complex_analyze": "Construct/check finite positional SP rewrite 2-complex N=2..10, exact F2 boundaries and independent path-coherence certificate. Or import only actual saved same-project operations. No pi1 claim from H1 alone. Create project first with assurance_project_new.",
        "white_star_symbolic_complex_verify": "Independently check stored finite complex and optional owned certificate_ref/typed replacement. Returns CHECKED_INSTANCE, REJECTED or NOT_PROVED with failed obligations; no execution grant.",
        "white_star_symbolic_dataset_store": "Store a private typed train/query dataset or bounded parts collection with SHA, rights and exact source spans. Queries MUST NOT contain labels; collection parts are same-project issued refs.",
        "white_star_symbolic_observer_synthesize": "Fit on private train_ref, seal, then predict queries-only predict_ref. Audit BUILTIN versus executed operator-derived features, effective ablation, contradictions, context UNKNOWN and pairwise abstentions. No unique grammar/semantic verification.",
        "white_star_symbolic_extension_replay": "Recompute an owned data-only complex/observer export with installed exact binding, source hashes, independent checker and journal chain. No ZIP code, network or arbitrary paths.",
    }
    for name, schema in TOOLS.items():

        def make(tool):
            async def invoke(**arguments):
                return await dispatch(tool, arguments)

            return invoke

        description = descriptions.get(
            name,
            "Read immutable extension summary/sections with bounded pagination, source spans, exact references and private data-only export. Oversized records require artifact chunks; nothing is silently truncated.",
        )
        server.add_tool(
            make(name),
            name=name,
            description=description,
            structured_output=False,
            annotations=ToolAnnotations(
                readOnlyHint=name
                not in (
                    "white_star_symbolic_complex_analyze",
                    "white_star_symbolic_observer_synthesize",
                    "white_star_symbolic_dataset_store",
                ),
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        tool = server._tool_manager.get_tool(name)
        tool.parameters = schema
        metadata = tool.fn_metadata.model_dump()
        metadata["output_schema"] = RESPONSE
        tool.fn_metadata = RawMetadata(**metadata)
    return service
