"""Exactly four additive opt-in contextual tools; no server-side LLM."""
import asyncio,copy
from mcp.types import ToolAnnotations,CallToolResult,TextContent
from ...errors import AssuranceError
from ...formal_bridge.mcp import RESPONSE as FORMAL_RESPONSE
from ...core import canonical
from ...white_star.mcp import RawMetadata
from .contracts import TOOLS,validate
from .service import ContextualService


RESPONSE=copy.deepcopy(FORMAL_RESPONSE);RESPONSE['properties']['schema']={'const':'semantic-bridge-response/1'}

def result(data=None,error=None):
    value={'schema':'semantic-bridge-response/1','ok':error is None,'execution_permission':False}
    value['error' if error is not None else 'data']=error if error is not None else data
    return CallToolResult(structuredContent=value,content=[TextContent(type='text',text=canonical(value))],isError=error is not None)


def capabilities(executor):
    return {'version':'semantic-bridge-patch001/1','status':'READY_OPT_IN' if executor and executor.status()['ready'] else 'UNAVAILABLE','tools':list(TOOLS),'LLM_calls':0,'semantic_adjudication':'NOT_EVALUATED','limits':{'pairs':10,'scenarios':8,'hypotheses':6,'obligations_per_hypothesis':8,'source_links_per_hypothesis':16,'formula_nodes':128,'formula_depth':16,'boolean_atoms':10,'worker_CPU_s':5,'worker_wall_s':6,'worker_RAM_MiB':512,'shared_active':2,'shared_queue':16},'execution_permission':False}


def register_tools(server,root,executor,recover=False):
    service=ContextualService(root,executor)
    if recover:service.recover()
    for name,schema in TOOLS.items():
        def make(tool):
            async def invoke(**args):
                try:
                    validate(tool,args);q=dict(args);project=q.pop('project')
                    if tool in ('semantic_bridge_register','semantic_bridge_analyze'):
                        key=q.pop('request_key');data=await service.operation(project,key,'register' if tool.endswith('register') else 'analyze',q)
                    elif tool=='semantic_bridge_replay':data=await service.replay(project,**q)
                    else:data=await asyncio.to_thread(service.inspect,project,**q)
                    return result(data=data)
                except (AssuranceError,ValueError,TypeError,KeyError,UnicodeError,RecursionError) as e:
                    return result(error={'code':e.code if isinstance(e,AssuranceError) else 'INVALID_INPUT','field_path':getattr(e,'field',None) or '', 'message':e.code if isinstance(e,AssuranceError) else str(e)[:256]})
            return invoke
        server.add_tool(make(name),name=name,description={'semantic_bridge_register':'Register immutable source-bound external/human contextual FOL hypotheses, assumptions and OPEN obligations. Unsupported/ill-typed candidates remain explicit. Source bytes and same-project issuance required; no LLM or semantic licensing.','semantic_bridge_analyze':'Exact alpha certificates first, conservative forall-boolean entailment next, then bounded existing directional finite countermodels. Keep formula truth, assumptions, context applicability, both incomparable candidates and OPEN obligations separate.','semantic_bridge_inspect':'Read own contextual summary, graph, obligations, checks or data-only replay bundle; exact base64 byte pages with full hash, no silent truncation.','semantic_bridge_replay':'Actually recompute one owned contextual register/analyze with exact installed binding and expected immutable result SHA; no model/network calls, fail closed.'}[name],structured_output=False,annotations=ToolAnnotations(readOnlyHint=name in ('semantic_bridge_inspect','semantic_bridge_replay'),destructiveHint=False,idempotentHint=True,openWorldHint=False))
        tool=server._tool_manager.get_tool(name);tool.parameters=schema;m=tool.fn_metadata.model_dump();m['output_schema']=RESPONSE;tool.fn_metadata=RawMetadata(**m)
    return service
