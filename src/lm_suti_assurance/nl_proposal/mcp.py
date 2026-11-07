"""Opt-in proposer and immutable private inspector on the current FastMCP."""
import asyncio
from mcp.types import CallToolResult,TextContent,ToolAnnotations
from ..core import canonical
from ..errors import AssuranceError
from ..symbolic_complex.contracts import validate
from ..white_star.mcp import RawMetadata
from .contracts import TOOLS
from .service import NLService

def capabilities(provider):
    return {'version':'NLProposalBridge/1','status':'READY_OPT_IN' if provider else 'PROVIDER_UNAVAILABLE','tools':list(TOOLS),'origin':'SOURCE_BOUND_CHECKED or TRACE_LINK_CHECKED; neither establishes meaning','semantic_alignment_status':'PROPOSED','legacy_formal_interpret_origin':'DECLARED_UNVERIFIED; provider.kind is an unchecked declaration','human_adjudication':'NOT_EXECUTED','execution_permission':False,'limits':{'active_jobs':4,'provider_concurrency':1,'max_batch':6,'max_frames_per_source':4,'max_candidates_per_source':8,'model_calls_per_job':1,'CPU_ms_decoder':4000,'tokens':'post-call checked usage; CLI has no hard generation token ceiling','sampling':'model revision, seed, temperature not controlled by CLI'}}

def register_tools(server,root,executor,provider=None,recover=False):
    service=NLService(root,executor,provider)
    if recover:service.recover()
    for name,schema in TOOLS.items():
        def make(tool):
            async def invoke(**arguments):
                try:
                    validate(arguments,TOOLS[tool]);args=dict(arguments);project=args.pop('project')
                    if tool=='formal_nl_propose':value=await service.propose(project,args.pop('request_key'),args)
                    else:value=await asyncio.to_thread(service.inspect,project,**args)
                    result={'schema':'nl-proposal-response/1','ok':True,'data':value,'execution_permission':False};error=False
                except (AssuranceError,ValueError,KeyError,TypeError) as e:
                    result={'schema':'nl-proposal-response/1','ok':False,'error':{'code':e.code if isinstance(e,AssuranceError) else 'NL_INVALID_INPUT','message':str(e),'details':e.details if isinstance(e,AssuranceError) else None},'execution_permission':False};error=True
                return CallToolResult(structuredContent=result,content=[TextContent(type='text',text=canonical(result))],isError=error)
            return invoke
        server.add_tool(make(name),name=name,description=('Opt-in literal-source FOL alternatives. Same-project checked White Star trace optional. Returns RUNNING: poll formal_nl_inspect. Provider/typing/origin/finite truth never establishes source meaning or grants execution. Up to six items share one real model call.' if name=='formal_nl_propose' else 'Read a project-owned immutable NL proposal, full private provenance or offline replay. Large objects use explicit base64 byte pages; no model call on replay.'),structured_output=False,annotations=ToolAnnotations(readOnlyHint=name=='formal_nl_inspect',destructiveHint=False,idempotentHint=True,openWorldHint=name=='formal_nl_propose'))
        tool=server._tool_manager.get_tool(name);tool.parameters=schema;metadata=tool.fn_metadata.model_dump();metadata['output_schema']={'type':'object','properties':{'schema':{'const':'nl-proposal-response/1'},'ok':{'type':'boolean'},'data':{'type':'object'},'error':{'type':'object'},'execution_permission':{'const':False}},'required':['schema','ok','execution_permission'],'additionalProperties':False};tool.fn_metadata=RawMetadata(**metadata)
    return service
