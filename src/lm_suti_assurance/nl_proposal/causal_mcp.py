"""One additive frozen-redecode tool; preserve all historical tool schemas."""
import asyncio
from functools import wraps
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from ..core import canonical
from ..errors import AssuranceError
from ..symbolic.contracts import obj, arr, integer, PROJECT, KEY, REF
from ..symbolic_complex.contracts import validate
from ..white_star.mcp import RawMetadata
from .contracts import TRACE
from .causal import ARMS
from .causal_service import CausalService

MODEL_CLASS = obj({'domain_sizes': {**arr(integer(1, 3), 3, 1), 'uniqueItems': True},
                   'max_models': integer(1, 530), 'max_relation_cells': integer(1, 9)},
                  ['domain_sizes', 'max_models', 'max_relation_cells'])
POLICY = obj({'max_candidates_per_source': integer(1, 8), 'max_ast_nodes': integer(1, 32),
              'max_cpu_ms': integer(1, 4000), 'sham_seed': integer(0, 2147483647),
              'max_primitive_depth': integer(0, 4), 'model_class': MODEL_CLASS},
             ['max_candidates_per_source', 'max_ast_nodes', 'max_cpu_ms', 'sham_seed', 'max_primitive_depth'])
SCHEMA = obj({'project': PROJECT, 'request_key': KEY, 'source_nl_run_ref': REF,
              'source_item_indices': {**arr(integer(0, 5), 6, 1), 'uniqueItems': True},
              'structural_run_refs': arr(TRACE, 24), 'arms': {**arr({'enum': list(ARMS)}, 4, 1), 'uniqueItems': True},
              'policy': POLICY}, ['project', 'request_key', 'source_nl_run_ref', 'source_item_indices', 'arms', 'policy'])


def response(value=None, error=None, schema='nl-causal-response/1'):
    result = {'schema': schema, 'ok': error is None, 'execution_permission': False}
    if error:
        result['error'] = {'code': error.code if isinstance(error, AssuranceError) else 'NL_INVALID_INPUT',
                           'message': str(error), 'details': error.details if isinstance(error, AssuranceError) else None}
    else:
        result['data'] = value
    return CallToolResult(structuredContent=result, content=[TextContent(type='text', text=canonical(result))], isError=error is not None)


def register_tools(server, root, executor):
    service = CausalService(root, executor)
    async def invoke(**arguments):
        try:
            validate(arguments, SCHEMA)
            args = dict(arguments)
            project = args.pop('project')
            key = args.pop('request_key')
            return response(await asyncio.to_thread(service.execute, project, key, args))
        except (AssuranceError, ValueError, KeyError, TypeError) as exc:
            return response(error=exc)
    server.add_tool(invoke, name='formal_nl_redecode', description='Frozen counterfactual over one owned finished NL provider receipt. NO_MOVE / REAL_TRACE / SHAM_ORDER / PRIMITIVE_CLOSURE share identical source, response, AST and ceilings. No provider calls, no semantic licensing, no execution grant. Inspect result or offline replay with formal_nl_inspect.',
                    structured_output=False, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    tool = server._tool_manager.get_tool('formal_nl_redecode')
    tool.parameters = SCHEMA
    metadata = tool.fn_metadata.model_dump()
    metadata['output_schema'] = obj({'schema': {'const': 'nl-causal-response/1'}, 'ok': {'type': 'boolean'},
                                      'data': {'type': 'object'}, 'error': {'type': 'object'},
                                      'execution_permission': {'const': False}}, ['schema', 'ok', 'execution_permission'])
    tool.fn_metadata = RawMetadata(**metadata)
    # The inspector contract already describes private immutable provenance and
    # offline replay. Extend dispatch only; its published metadata stays exact.
    inspector = server._tool_manager.get_tool('formal_nl_inspect')
    original = inspector.fn
    @wraps(original)
    async def inspect(**arguments):
        try:
            from .contracts import TOOLS
            validate(arguments, TOOLS['formal_nl_inspect'])
            if await asyncio.to_thread(service.owns, arguments['project'], arguments['run_ref']):
                return response(await asyncio.to_thread(service.inspect, **arguments), schema='nl-proposal-response/1')
            return await original(**arguments)
        except (AssuranceError, ValueError, KeyError, TypeError) as exc:
            return response(error=exc, schema='nl-proposal-response/1')
    inspector.fn = inspect
    return service
