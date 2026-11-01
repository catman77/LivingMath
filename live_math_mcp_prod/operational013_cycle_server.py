"""Isolated typed013 MCP: precommit allowed, activation/commit/execution absent."""
import argparse
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from native_preview008_contract import NativeRequest
from operational013_cycle import OperationalCycle


def create_server(database):
    mcp=FastMCP('LivingMath013 private typed cycle',json_response=True)
    mcp._mcp_server.version='013.0'
    engine=OperationalCycle(database)
    ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    @mcp.tool(annotations=ro)
    def operational_cycle_preview(request:NativeRequest)->dict:
        return engine.preview(request.model_dump())
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def operational_cycle_precommit(request:NativeRequest,request_key:str)->dict:
        return engine.precommit(request.model_dump(),request_key)
    @mcp.tool(annotations=ro)
    def operational_cycle_validate(project:str,move_id:int,event_id:int)->dict:
        return engine.validate(project,move_id,event_id)
    return mcp


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);args=p.parse_args()
    create_server(args.db).run(transport='stdio')
