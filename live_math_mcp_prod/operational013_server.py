"""Private 013 read-only MCP. Never registered with the production endpoint."""
import argparse
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from operational013_source import Request,bound_fit


def create_server(database):
    database=Path(database).resolve(strict=True)
    server=FastMCP('LivingMath013 isolated experiment',json_response=True)
    server._mcp_server.version='013.0'
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def operational_law_preview(request:Request)->dict:
        try:return bound_fit(database,request)
        except (ValueError,KeyError,TypeError) as error:
            return {'status':'INSUFFICIENT_CONTEXT','reason':str(error),'execution_permission':{'allowed':False},'proof_status':'unverified'}
    return server


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);args=parser.parse_args()
    create_server(args.db).run(transport='stdio')
