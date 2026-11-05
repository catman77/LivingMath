"""Additive SDK1.30 tools with strict raw validation and typed domain errors."""

import asyncio
import base64
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata
from ..core import canonical
from ..errors import AssuranceError
from .contracts import TOOLS, RESPONSE, LIMITS, check_schema, integrity
from .service import WhiteStar
from . import views


class RawMetadata(FuncMetadata):
    """Preserve bool/float and unknown keys for our strict JSON Schema validator.

    FastMCP's convenience coercion/JSON-string preparse is intentionally bypassed
    only for these tools; their published schemas perform the full validation.
    """

    async def call_fn_with_arg_validation(
        self, fn, fn_is_async, arguments_to_validate, arguments_to_pass_directly=None
    ):
        return await fn(**arguments_to_validate)

    def convert_result(self, result):
        return result


def result(data=None, error=None):
    value = {
        "schema": "levinmas-white-star-response/1",
        "ok": error is None,
        "status": data.get("status", "OK") if error is None else "ERROR",
        "execution_permission": False,
    }
    if error is None:
        value["data"] = data
    else:
        value["error"] = error
    check_schema(value, RESPONSE)
    reply = CallToolResult(
        structuredContent=value,
        content=[TextContent(type="text", text=canonical(value))],
        isError=error is not None,
    )
    if len(reply.model_dump_json().encode()) > LIMITS["MCP_response_bytes"]:
        return result(
            error={
                "code": "INPUT_TOO_LARGE",
                "message": "Use white_star_inspect whole-record pages or artifact chunks",
                "field_path": "/response",
                "run_id": (data or {}).get("run_id"),
            }
        )
    return reply


def register_tools(server, root, pool=None, recover=False):
    service = WhiteStar(root, pool)
    recovered = service.recover() if recover else []

    async def dispatch(name, args):
        try:
            check_schema(args, TOOLS[name]["inputSchema"])
            if name == "white_star_status":
                data = {
                    "schema": "levinmas-white-star-status/1",
                    "status": (
                        "READY"
                        if pool and pool.status()["ready"]
                        else "ENGINE_UNAVAILABLE"
                    ),
                    "release": "v0.3.0-developer-preview",
                    "worker": pool.status() if pool else {"ready": False},
                    "limits": LIMITS,
                    "profiles": ["base_v1", "cj_v1"],
                    "kernel_hashes": integrity(),
                    "tools": TOOLS,
                    "outputSchema": RESPONSE,
                    "workflow": {
                        "project_registration": {
                            "tool": "assurance_project_new",
                            "arguments": {
                                "project": "my-white-star-project",
                                "request_key": "project-init-v1",
                            },
                        },
                        "sequence": [
                            "assurance_project_new",
                            "white_star_explore",
                            "white_star_inspect (frames and decoder)",
                            "white_star_record_interpretation",
                        ],
                        "missing_project_retry": (
                            "Register the same project explicitly, then retry explore "
                            "with the same request_key and request. PROJECT_NOT_FOUND "
                            "creates no run and does not consume the request key."
                        ),
                    },
                    "modes": {
                        "white_star": "UNCHANGED_NATIVE_WHITE_STAR_CAD_UDAV",
                        "suti": "SemanticBridge001/source-assurance-frozen-ingress/1",
                    },
                    "SUTI_native_runtime": "NOT_EXECUTED",
                    "R3": "PENDING",
                    "recovered_runs": recovered,
                    "execution_permission": False,
                }
            elif name == "white_star_explore":
                data = await service.explore(
                    args["project"], args["request_key"], args["request"]
                )
            elif name == "semantic_run_frozen":
                data = await asyncio.to_thread(
                    service.frozen,
                    args["project"],
                    args["request_key"],
                    args["common_snapshot_ref"],
                    args.get("decoder_slots", 6),
                )
            elif name == "white_star_inspect":
                data = await asyncio.to_thread(views.inspect, service, **args)
            elif name == "white_star_record_interpretation":
                data = await asyncio.to_thread(
                    service.readings,
                    args["project"],
                    args["run_id"],
                    args["request_key"],
                    args["readings"],
                    args.get("provenance"),
                )
            elif name == "white_star_validate_model":
                data = await service.model(
                    args["project"], args["run_id"], args["proposal"]
                )
            elif name == "semantic_compare_runs":
                data = await asyncio.to_thread(views.compare, service, **args)
            elif name == "white_star_replay":
                from ..service import require

                w = service.workspace(args["project"])
                target = w.path / ".white-star-exports" / (args["bundle_ref"] + ".zip")
                require(not target.is_symlink() and target.is_file(), "NOT_FOUND")
                raw = target.read_bytes()
                require(
                    __import__("hashlib").sha256(raw).hexdigest() == args["bundle_ref"],
                    "EXPORT_INTEGRITY_FAILURE",
                )
                if pool is None:
                    raise AssuranceError("ENGINE_UNAVAILABLE")
                response = await asyncio.to_thread(
                    pool.run,
                    {
                        "action": "replay",
                        "bundle_base64": base64.b64encode(raw).decode(),
                    },
                )
                data = response["data"]
            else:
                raise AssuranceError("INVALID_INPUT")
            return result(data=data)
        except AssuranceError as e:
            details = e.details or {}
            code = {
                "REFERENCE_NOT_IN_PROJECT": "NOT_FOUND",
            }.get(e.code, e.code)
            field = e.field or ""
            message = details.get("message", code)
            if e.code == "PROJECT_NOT_FOUND":
                field = "/project"
                registration = canonical(
                    {"project": args["project"], "request_key": "project-init-v1"}
                )
                message = (
                    f"Project {args['project']!r} is not registered. First call "
                    f"assurance_project_new with {registration}, then retry the "
                    "original call with the same request_key and payload. "
                    "No run was created; the request key was not consumed."
                )
            return result(
                error={
                    "code": code,
                    "message": message,
                    "field_path": field,
                    "run_id": details.get("run_id", args.get("run_id")),
                }
            )

    descriptions = {
        "white_star_status": "Read exact schemas, project-registration workflow, readiness/limits, frozen kernel hashes and actual Bridge backend. Native SUTI is NOT_EXECUTED.",
        "white_star_explore": "Сначала зарегистрируйте project через assurance_project_new(project, request_key). Белая звезда: сохраните UTF-8 текст и явную LLM-разметку concepts/coordinates/evidence; выполните один bounded поиск. Затем inspect decoder и record_interpretation. При PROJECT_NOT_FOUND зарегистрируйте тот же project и повторите исходный request_key/request. Исходный алгоритм, без reranking.",
        "white_star_inspect": "Read immutable run pages (default64,max128). decoder may require artifact chunks. export returns private ZIP base64 chunks; concatenate in order. No new search.",
        "white_star_record_interpretation": "Save the calling LLM’s readings with actual frame IDs, exact source evidence, added assumptions, alternatives and INTERPRETATION claim atoms. No server LLM or verification.",
        "white_star_validate_model": "Check one registered reading/claim mapping within3 supported exact rational matrix families. CHECKED_INSTANCE certifies only the concrete algebra; counterexamples return REJECTED. Other families UNSUPPORTED_MODEL.",
        "semantic_compare_runs": "Read two actual saved runs. MATCHED_INPUT requires identical whole frozen common snapshot, not just source SHA. Report costs/projection boundaries; never call a model or declare a winner.",
        "semantic_run_frozen": "Execute actual existing SemanticBridge/source assurance on a saved common_snapshot_ref from White Star. No new extraction, no coordinates, no native SUTI or invented relations. Select decoder slots explicitly.",
        "white_star_replay": "Recompute one private data-only export by SHA in its own project. Fixed isolated worker, unchanged numerical kernel, existing assurance checks, no LLM/network/OAuth.",
    }
    for name, spec in TOOLS.items():

        def make(tool_name):
            async def invoke(**arguments):
                return await dispatch(tool_name, arguments)

            return invoke

        server.add_tool(
            make(name),
            name=name,
            description=descriptions[name],
            annotations=ToolAnnotations(**spec["annotations"]),
            structured_output=False,
        )
        tool = server._tool_manager.get_tool(name)
        tool.parameters = spec["inputSchema"]
        metadata = tool.fn_metadata.model_dump()
        metadata["output_schema"] = RESPONSE
        tool.fn_metadata = RawMetadata(**metadata)
    return service
