"""Private read-only012 experiment. No production registration or operator tools."""
import argparse
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from concept_genesis012_source import Request
from concept_genesis012 import evaluate


def create_server(database: Path) -> FastMCP:
    database=database.resolve(strict=True)
    mcp=FastMCP('LivingMath012 source concept experiment',json_response=True);mcp._mcp_server.version='012.1'
    annotation=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    @mcp.tool(annotations=annotation)
    def concept_genesis_preview(request:Request)->dict:
        return evaluate(database,request)
    @mcp.tool(annotations=annotation)
    def source_counterexample_preview(request:Request)->dict:
        return evaluate(database,request,'negative')
    @mcp.tool(annotations=annotation)
    def source_probing_baseline(request:Request)->dict:
        return evaluate(database,request,'baseline')
    for name in ('concept_genesis_preview','source_counterexample_preview','source_probing_baseline'):
        tool=mcp._tool_manager.get_tool(name);tool.fn_metadata.arg_model.model_config.update(extra='forbid',strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True);tool.parameters=tool.fn_metadata.arg_model.model_json_schema()
    return mcp


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);args=p.parse_args()
    create_server(args.db).run(transport='stdio')
