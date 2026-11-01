"""Isolated read-only Phase-A contract prototype. No public registration or commit."""
import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from native_preview008_contract import NativeRequest
from research_engine010_contract import VERSION, ReceiptValidationRequest
from research_engine010 import PhaseAEngine


def create_phase_a_server(database: Path) -> FastMCP:
    engine = PhaseAEngine(database)
    mcp = FastMCP('LivingMath010 source-contract preflight', json_response=True)
    mcp._mcp_server.version = VERSION
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @mcp.tool(annotations=annotation)
    def research_cycle_validate_receipt(request: ReceiptValidationRequest) -> dict:
        """Prevalidate actual event metadata only; never synthesize missing binding or commit completion."""
        return engine.validate_receipt(request)

    @mcp.tool(annotations=annotation)
    def research_novelty_snapshot(request: NativeRequest) -> dict:
        """Missing server history returns INCOMPLETE, never a complete empty caller-supplied history."""
        return engine.novelty_snapshot(request)

    @mcp.tool(annotations=annotation)
    def research_cycle_preview(request: NativeRequest) -> dict:
        """Fail-closed Phase-A next-step guard. No I/T/measurement/activation before typed authority exists."""
        return engine.cycle_preview(request)

    for name in ('research_cycle_validate_receipt', 'research_novelty_snapshot', 'research_cycle_preview'):
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid', strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()
    return mcp


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    create_phase_a_server(args.db).run(transport='stdio')
