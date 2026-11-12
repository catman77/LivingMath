"""Four explicit opt-in tools; existing tool schemas stay unchanged."""
import asyncio
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from ..core import canonical
from ..errors import AssuranceError
from ..white_star.contracts import check_schema
from ..white_star.mcp import RawMetadata, RESPONSE
from .contracts import TOOLS, OBSERVER
from .service import CoverageService


def result(data: dict | None = None, error: dict | None = None) -> CallToolResult:
    """Full structured pages once, plus a short text preview (not duplicate pages)."""
    value = {'schema': 'levinmas-white-star-response/1', 'ok': error is None,
             'status': data.get('status', 'OK') if error is None else 'ERROR', 'execution_permission': False}
    value['data' if error is None else 'error'] = data if error is None else error
    check_schema(value, RESPONSE)
    preview = value if error else {**value, 'data': {k: v for k, v in data.items() if k != 'records'}}
    reply = CallToolResult(structuredContent=value, content=[TextContent(type='text', text=canonical(preview))], isError=error is not None)
    if len(reply.model_dump_json().encode()) > 262144:
        raise AssuranceError('COVERAGE_PAGE_TRANSPORT_LIMIT')
    return reply


def capabilities(executor=None) -> dict:
    return {'version': 'certified-cj-coverage/1', 'observer': OBSERVER, 'mode': 'completeness_only',
            'profiles': ['cj_v1'], 'source_truth': 'NOT_VERIFIED', 'execution_permission': False,
            'tools': list(TOOLS), 'worker': executor.status() if executor else {'ready': False}}


def register_tools(server, root, executor=None) -> CoverageService:
    service = CoverageService(root, executor)
    methods = {'coverage_plan': service.plan, 'coverage_advance': service.advance, 'coverage_inspect': service.inspect, 'coverage_replay': service.replay}
    descriptions = {
        'coverage_plan': 'Opt-in cj_v1 finite qualitative coverage. Freeze source-bound atlas, complete target domain, analytic witnesses and kernel bindings. Does not execute targets or verify source meaning. Requires assurance_project_new first.',
        'coverage_advance': 'Execute a bounded prefix of mandatory target projections via supplied CAD, no CAT veto. Commit checked receipts/checkpoint atomically. PARTIAL on budget boundary; ERROR leaves obligation open. Retry with the identical request key.',
        'coverage_inspect': 'Full stable plan/receipt pagination (default64), or summary. compute_complete, export_available and delivery_acked are distinct. Explicit digest/count/client acknowledgement uses view=delivery and request_key; no claim of semantic reading.',
        'coverage_replay': 'Read-only bounded replay through pinned isolated CAD worker with independent exact-cell verification. Repeat next_cursor until null; compares exact saved receipts, never verifies semantic truth.'}
    for name, schema in TOOLS.items():
        def make(tool):
            async def invoke(**args):
                try:
                    check_schema(args, TOOLS[tool])
                    value = await asyncio.to_thread(methods[tool], **args)
                    return result(data=value)
                except (AssuranceError, ValueError, KeyError, TypeError, OSError) as e:
                    return result(error={'code': e.code if isinstance(e, AssuranceError) else 'COVERAGE_INVALID_INPUT', 'message': str(e)[:512], 'field_path': getattr(e, 'field', None) or '', 'run_id': None})
            return invoke
        server.add_tool(make(name), name=name, description=descriptions[name], structured_output=False,
                        annotations=ToolAnnotations(readOnlyHint=name == 'coverage_replay', destructiveHint=False, idempotentHint=True, openWorldHint=False))
        tool = server._tool_manager.get_tool(name)
        tool.parameters = schema
        metadata = tool.fn_metadata.model_dump()
        metadata['output_schema'] = RESPONSE
        tool.fn_metadata = RawMetadata(**metadata)
    return service
