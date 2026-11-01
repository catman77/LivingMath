"""Publish accepted typed011 tools against a separate operator-provisioned sandbox."""
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from typed_cycle011_server import create_typed_server
from typed_cycle011_store import assert_isolated, connect

PUBLIC_TOOLS = ('research_cycle_preview', 'research_cycle_precommit',
                'research_cycle_validate', 'research_novelty_snapshot')


def register_typed_tools(mcp: FastMCP, canonical_database: Path, sandbox_database: Path) -> None:
    canonical = Path(canonical_database).expanduser().resolve(strict=True)
    sandbox = Path(sandbox_database).expanduser().resolve(strict=True)
    if sandbox.samefile(canonical):
        raise ValueError('TYPED_SANDBOX_MUST_NOT_BE_CANONICAL')
    assert_isolated(sandbox)
    with connect(sandbox) as connection:
        configuration = json.loads(connection.execute(
            'SELECT payload_json FROM typed011_configuration WHERE id=1').fetchone()[0])
    if not Path(configuration['canonical_database']).resolve(strict=True).samefile(canonical):
        raise ValueError('TYPED_SANDBOX_CANONICAL_BINDING_MISMATCH')
    if any(mcp._tool_manager.get_tool(name) is not None for name in PUBLIC_TOOLS):
        raise ValueError('TYPED_TOOL_NAME_COLLISION')
    accepted = create_typed_server(sandbox)
    for name in PUBLIC_TOOLS:
        original = accepted._tool_manager.get_tool(name)
        mcp.add_tool(original.fn, name=name, description=original.description,
                     annotations=original.annotations)
        mounted = mcp._tool_manager.get_tool(name)
        # Retain the accepted strict argument model, including outer extra-field rejection.
        mounted.fn_metadata = original.fn_metadata
        mounted.parameters = original.parameters


def public_contract() -> dict:
    return {'version': '011.1', 'tools': list(PUBLIC_TOOLS), 'storage': 'isolated operator-provisioned sandbox',
            'project_scope': 'Registered LM_QA_TYPED011_* scopes only; no RH/SRT/FTL execution.',
            'source_management': 'Local operator provisions sandbox sources/scopes; record_result uses the canonical ledger.',
            'lifecycle': 'Precommit and read-only checks do not grant execution. Activation, execution, review and commit remain local operator actions.',
            'generic_tools': 'Canonical record_research_move/transition_research_move do not activate or complete typed sandbox moves.',
            'proof_status': 'unverified'}
