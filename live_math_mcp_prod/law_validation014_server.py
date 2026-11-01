"""Private014 MCP, confined reads, no model grant/commit/execution authority."""
import argparse
import json
from pathlib import Path
import time
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from law_validation014_engine import LawCycle014
from law_validation014_contract import Request014
from law_validation014_isolation import restrict_reads


def create_server(database):
    engine=LawCycle014(database);mcp=FastMCP('LivingMath014 isolated law validation',json_response=True)
    mcp._mcp_server.version='014.P0.1'
    ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    @mcp.tool(annotations=ro)
    def source_law_preview(request:Request014)->dict:
        return engine.source_preview(request.model_dump())
    @mcp.tool(annotations=ro)
    def law_research_preview(request:Request014)->dict:
        return engine.preview(request.model_dump())
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def law_research_precommit(request:Request014,request_key:str)->dict:
        return engine.precommit(request.model_dump(),request_key)
    @mcp.tool(annotations=ro)
    def law_research_validate(project:str,move_id:int,event_id:int)->dict:
        return engine.validate(project,move_id,event_id)
    for name in ('source_law_preview','law_research_preview','law_research_precommit','law_research_validate'):
        tool=mcp._tool_manager.get_tool(name);tool.fn_metadata.arg_model.model_config.update(extra='forbid',strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True);tool.parameters=tool.fn_metadata.arg_model.model_json_schema()
    return mcp


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--forbidden',type=Path,action='append',required=True);args=parser.parse_args()
    server=create_server(args.db)
    # All required imports/schema generation precede confinement; later oracle/seal reads must fail.
    evidence=restrict_reads(args.db.parent,args.forbidden)
    (args.db.parent/'isolation.json').write_text(json.dumps(evidence,indent=2)+'\n')
    server.run(transport='stdio')
