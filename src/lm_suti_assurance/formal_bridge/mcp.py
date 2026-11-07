"""Eight additive tools on the existing HTTPS/OAuth MCP server and worker pool."""

import asyncio
from mcp.types import CallToolResult,TextContent,ToolAnnotations
from ..core import canonical
from ..errors import AssuranceError
from ..symbolic_complex.contracts import validate
from ..white_star.mcp import RawMetadata
from .contracts import TOOLS
from .service import FormalService


RESPONSE={'type':'object','properties':{'schema':{'const':'formal-response/1'},'ok':{'type':'boolean'},'data':{'type':'object'},'error':{'type':'object'},'execution_permission':{'const':False}},'required':['schema','ok','execution_permission'],'additionalProperties':False}


def capabilities(executor):
    return {'version':'formal-bridge/1','status':'READY' if executor and executor.status()['ready'] else 'ENGINE_UNAVAILABLE','formats':['formal-grammar-ir/1','formal-dfa-ir/1','formal-candidate/1','formal-contrast/1'],'candidate_classes':'bounded primitive sequence/alternative grammars and canonical finite transition tables; not all CFG','semantic_proposer':'EXPLICIT_HUMAN_OR_IMPORTED_PROPOSALS; no general NL decoder','limits':{'max_tokens':12,'max_NT':2,'max_rules':6,'max_ast_nodes':32,'max_states':4,'worker_CPU_s':5,'worker_wall_s':6,'worker_RAM_MiB':512,'shared_active':2,'shared_queue':16},'execution_permission':False}


def register_tools(server,root,executor,recover=False):
    service=FormalService(root,executor)
    if recover:service.recover()
    descriptions={
        'formal_store':'Store same-project data-only source/model/query record or explicit imported grammar/DFA. SHA/rights/types checked; imported AST is never called induced.',
        'formal_synthesize':'Induce a declared bounded CFG/DFA catalog from owned train data only; seal model before query-only predictions; retain rivals/counterexamples. Create project and datasets first. No universal/unique grammar claim.',
        'formal_inspect':'Read immutable formal run, candidates, full packed forests, objects or data-only replay bundle. Lists are paginated; large objects use explicit byte/base64 chunks, not silent truncation.',
        'formal_verify':'Independently check a source-bound packed CFG forest or DFA transition trace using the frozen AST. Optional proof_ref is untrusted data. Complete negative DP versus explicit UNKNOWN, never an execution grant.',
        'formal_contrast':'Find bounded distinguishing word/prediction vector without true label, or finite FOL countermodel. Retain provenance. No difference within bound never means equivalent.',
        'formal_interpret':'Store multiple explicitly provided source-aligned typed FOL proposals from human/imported/external provenance. Provider does not establish meaning. Every candidate stays PROPOSED; no automatic Russian NLP claim.',
        'formal_model_check':'Check typed FOL and assumptions in an explicitly closed finite model; TRUE/FALSE belongs to that model, not author intent. Open-world input gives UNKNOWN.',
        'formal_replay':'Recompute owned immutable formal packet through exact installed kernel binding, append replay receipt and compare result SHA. No code from uploaded archives.'}
    for name,schema in TOOLS.items():
        def make(tool):
            async def invoke(**arguments):
                try:
                    validate(arguments,TOOLS[tool]);args=dict(arguments);project=args.pop('project')
                    if tool=='formal_inspect':value=await asyncio.to_thread(service.inspect,project,**args)
                    else:value=await service.operation(project,args.pop('request_key'),tool.removeprefix('formal_'),args)
                    if value.get('status')=='FAILED':raise AssuranceError('FORMAL_OPERATION_FAILED',details=value)
                    result={'schema':'formal-response/1','ok':True,'data':value,'execution_permission':False};error=False
                except (AssuranceError,ValueError,KeyError,TypeError) as exc:
                    result={'schema':'formal-response/1','ok':False,'error':{'code':exc.code if isinstance(exc,AssuranceError) else 'FORMAL_INVALID_INPUT','message':str(exc),'details':exc.details if isinstance(exc,AssuranceError) else None},'execution_permission':False};error=True
                return CallToolResult(structuredContent=result,content=[TextContent(type='text',text=canonical(result))],isError=error)
            return invoke
        server.add_tool(make(name),name=name,description=descriptions[name],structured_output=False,annotations=ToolAnnotations(readOnlyHint=name=='formal_inspect',destructiveHint=False,idempotentHint=True,openWorldHint=False))
        tool=server._tool_manager.get_tool(name);tool.parameters=schema;metadata=tool.fn_metadata.model_dump();metadata['output_schema']=RESPONSE;tool.fn_metadata=RawMetadata(**metadata)
    return service
