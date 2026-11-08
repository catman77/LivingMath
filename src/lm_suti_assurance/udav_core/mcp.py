"""Four additive opt-in tools; historical94 schemas remain byte-identical."""
import asyncio,copy
from mcp.types import ToolAnnotations
from ..symbolic.contracts import obj,integer,PROJECT,KEY,REF
from ..symbolic.mcp import result
from ..white_star.mcp import RawMetadata
from ..white_star.contracts import TOOLS as NUMERIC_TOOLS,check_schema
from ..errors import AssuranceError
from .contracts import SYMBOLIC_REQUEST,NUMERIC_POLICY
from .service import UDAVService


def register_tools(server,root,executor,numeric=False,recover=False):
    service=UDAVService(root,executor)
    if recover:service.recover()
    schemas={
      'udav_symbolic_explore':obj({'project':PROJECT,'request_key':KEY,'request':SYMBOLIC_REQUEST},['project','request_key','request']),
      'udav_inspect':obj({'project':PROJECT,'run_id':REF,'view':{'enum':['summary','result','diagnostics','bundle']},'offset':integer(0,64*1024*1024),'limit':integer(1,48),'expected_result_sha256':REF},['project','run_id']),
      'udav_replay':obj({'project':PROJECT,'run_id':REF,'expected_result_sha256':REF},['project','run_id'])}
    if numeric:schemas['white_star_explore_v2']=obj({'project':PROJECT,'request_key':KEY,'selection_policy':{'const':NUMERIC_POLICY},'request':copy.deepcopy(NUMERIC_TOOLS['white_star_explore']['inputSchema']['properties']['request'])},['project','request_key','selection_policy','request'])
    for name,schema in schemas.items():
        def make(tool):
            async def invoke(**args):
                try:
                    check_schema(args,schemas[tool]);q=dict(args);project=q.pop('project')
                    if tool in ('udav_symbolic_explore','white_star_explore_v2'):
                        value=await service.explore(project,q['request_key'],'symbolic' if tool=='udav_symbolic_explore' else 'numeric',q['request'])
                    elif tool=='udav_replay':value=await service.replay(project,**q)
                    else:value=await asyncio.to_thread(service.inspect,project,**q)
                    return result(data=value)
                except (AssuranceError,ValueError,KeyError,TypeError) as e:
                    return result(error={'code':e.code if isinstance(e,AssuranceError) else 'UDAV_INVALID_INPUT','message':str(e),'field_path':getattr(e,'field',None) or '', 'run_id':args.get('run_id')})
            return invoke
        server.add_tool(make(name),name=name,description={'udav_symbolic_explore':'Opt-in frontier_argument_coverage_v1 on actual stored SymbolicState/History. Lazy finite argument coverage and raw/structural diagnostics, no grammar induction, LLM or execution permission.','white_star_explore_v2':'Explicit CAT-distinction tie-break after primary topology novelty, genuine dynamic memory. All atlas aliases preserved. Legacy white_star_explore unchanged.','udav_inspect':'Read owned immutable UDAV summaries, full byte-paged result/diagnostics and data-only bundle.','udav_replay':'Recompute one project-owned UDAV request through the exact installed isolated worker; zero LLM/network; fail closed on SHA/profile mismatch.'}[name],structured_output=False,annotations=ToolAnnotations(readOnlyHint=name in ('udav_inspect','udav_replay'),destructiveHint=False,idempotentHint=True,openWorldHint=False))
        t=server._tool_manager.get_tool(name);t.parameters=schema
        from ..symbolic.mcp import RESPONSE
        m=t.fn_metadata.model_dump();m['output_schema']=RESPONSE;t.fn_metadata=RawMetadata(**m)
    return service
