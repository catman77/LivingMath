"""Three additive strict tools, registered independently of numerical White Star."""

import asyncio, base64, copy, hashlib
from pathlib import Path
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from ..core import canonical
from ..errors import AssuranceError
from ..white_star.mcp import RawMetadata
from ..white_star.contracts import RESPONSE as OLD_RESPONSE, check_schema
from .contracts import REQUEST, PROJECT, KEY, REF, LIMITS, obj, integer
from .service import SymbolicService
from .kernel import binding

RESPONSE = copy.deepcopy(OLD_RESPONSE)
RESPONSE["properties"]["schema"] = {"const": "levinmas-white-star-symbolic-response/1"}
TOOLS = {
    "white_star_symbolic_explore": obj(
        {"project": PROJECT, "request_key": KEY, "request": REQUEST},
        ["project", "request_key", "request"],
    ),
    "white_star_symbolic_inspect": obj(
        {
            "project": PROJECT,
            "run_id": REF,
            "view": {
                "enum": [
                    "summary",
                    "input",
                    "operations",
                    "observations",
                    "claims",
                    "grammar",
                    "evaluation",
                    "history",
                    "states",
                    "source",
                    "manifest",
                    "checks",
                    "report",
                    "export",
                    "artifact",
                    "comparison",
                    "diagnostics",
                ]
            },
            "offset": integer(0, 1000000),
            "limit": integer(1, 128),
            "artifact_ref": REF,
            "compare_run_id": REF,
        },
        ["project", "run_id"],
    ),
    "white_star_symbolic_replay": obj(
        {"project": PROJECT, "bundle_ref": REF}, ["project", "bundle_ref"]
    ),
}


def capabilities(executor=None, replay_profiles=None):
    return {
        "version": "symbolic_v1/1-patch001",
        "historical_replay_bindings": sorted(replay_profiles or {}),
        "engine": "symbolic_v1",
        "status": (
            "READY" if executor and executor.status()["ready"] else "ENGINE_UNAVAILABLE"
        ),
        "kernel_binding": binding(),
        "limits": LIMITS,
        "request_schema": REQUEST,
        "response_schema": RESPONSE,
        "tools": list(TOOLS),
        "worker": executor.status() if executor else None,
        "execution_permission": False,
        "boundary": "Full symbolic histories; exact finite identities and empirical train-only grammars. No semantic verification.",
    }


def result(data=None, error=None):
    value = {
        "schema": "levinmas-white-star-symbolic-response/1",
        "ok": error is None,
        "status": data.get("status", "OK") if error is None else "ERROR",
        "execution_permission": False,
    }
    value["data" if error is None else "error"] = data if error is None else error
    check_schema(value, RESPONSE)
    if len(canonical(value).encode()) > 250000:
        return result(
            error={
                "code": "RESULT_TOO_LARGE",
                "message": "Use whole-record inspect pages or artifact chunks",
                "field_path": "/response",
                "run_id": (data or {}).get("run_id"),
            }
        )
    return CallToolResult(
        structuredContent=value,
        content=[TextContent(type="text", text=canonical(value))],
        isError=error is not None,
    )


def register_tools(server, root, executor=None, recover=False, replay_profiles=None):
    service = SymbolicService(Path(root), executor)
    if recover:
        service.recover()

    async def dispatch(name, args):
        try:
            check_schema(args, TOOLS[name])
            if name == "white_star_symbolic_explore":
                data = await service.explore(
                    args["project"], args["request_key"], args["request"]
                )
            elif name == "white_star_symbolic_inspect":
                data = await asyncio.to_thread(service.inspect, **args)
            else:
                w = service.workspace(args["project"])
                target = w.path / ".symbolic-exports" / (args["bundle_ref"] + ".zip")
                if target.is_symlink() or not target.is_file():
                    raise AssuranceError("NOT_FOUND")
                raw = target.read_bytes()
                if hashlib.sha256(raw).hexdigest() != args["bundle_ref"]:
                    raise AssuranceError("EXPORT_INTEGRITY_FAILURE")
                from .bundle import bundle_binding

                requested_binding = bundle_binding(raw)
                selected_executor = (
                    executor
                    if requested_binding == binding()
                    else (replay_profiles or {}).get(requested_binding)
                )
                if selected_executor is None:
                    raise AssuranceError(
                        "KERNEL_BINDING_UNAVAILABLE",
                        details={
                            "message": "No approved installed profile for this exact binding"
                        },
                    )
                reply = await asyncio.to_thread(
                    selected_executor.run,
                    {
                        "action": "replay",
                        "bundle_base64": base64.b64encode(raw).decode(),
                    },
                )
                data = reply["data"]
            return result(data=data)
        except AssuranceError as exc:
            details = exc.details or {}
            message = details.get("message", exc.code)
            field = exc.field or ""
            if exc.code == "PROJECT_NOT_FOUND":
                field = "/project"
                message = (
                    "First call assurance_project_new with "
                    + canonical(
                        {"project": args["project"], "request_key": "project-init-v1"}
                    )
                    + "; then retry the same symbolic request_key/request."
                )
            return result(
                error={
                    "code": exc.code,
                    "message": message,
                    "field_path": field,
                    "run_id": details.get("run_id", args.get("run_id")),
                }
            )

    descriptions = {
        "white_star_symbolic_explore": "Register project with assurance_project_new first. Execute symbolic_v1 full token histories, exact SP/alpha witnesses, bounded local UDAV/CAD search. No 2D encoder, server LLM or verification. See bridge_system_status.symbolic_v1 for exact schema and limits.",
        "white_star_symbolic_inspect": "Read immutable symbolic run pages and exact source spans. comparison requires compare_run_id in the same project; diagnostics exposes bounded local saturation. Views: operations, observations, claims, grammar, evaluation, history, states, source, report, manifest, checks, input, summary. Private export returns ordered base64 chunks. Large records explicitly require artifact chunks.",
        "white_star_symbolic_replay": "Recompute one private symbolic data-only bundle by SHA in its own project. Exact installed operation binding, complete source/DAG audit, bounded isolated worker. No LLM/network or code execution from ZIP.",
    }
    for name, schema in TOOLS.items():

        def make(tool_name):
            async def invoke(**arguments):
                return await dispatch(tool_name, arguments)

            return invoke

        server.add_tool(
            make(name),
            name=name,
            description=descriptions[name],
            structured_output=False,
            annotations=ToolAnnotations(
                readOnlyHint=name != "white_star_symbolic_explore",
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
