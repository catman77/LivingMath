"""018 denied authority remains a machine-readable MCP error."""
import asyncio
from pathlib import Path
from deploy018_http import create_app
from deploy018_transport import serving, client
from research_store import ResearchStore
from typed_cycle011_store import install as install011
from engine017_store import install as install017
from deploy018_storage import migrate
from deploy018_authority import install
from qa_positive_acceptance import snapshot


def test_real_tls_model_denial_has_structured_code_and_no_db_delta(tmp_path):
    async def run():
        workspace = tmp_path / 'workspace'
        workspace.mkdir()
        legacy, db = workspace / 'research.sqlite3', workspace / 'engine.sqlite3'
        ResearchStore(legacy); ResearchStore(db)
        install011(db, legacy); install017(db); migrate(legacy); migrate(db); install(db)
        out = tmp_path / 'output'; out.mkdir()
        before = snapshot(legacy), snapshot(db)
        async with serving(workspace, db, out, 'structured-error', []) as (origin, context, tokens, process):
            async with client(origin, context, tokens['access_token'], out / 'wire.jsonl') as connection:
                await connection.initialize()
                tools = await connection.list_tools()
                assert len(tools.tools) == 27
                for action in ('activate_experiment', 'complete'):
                    reply = await connection.call_tool('transition_research_move', {'project': 'LM_QA_018_ERRORS', 'move_id': 1,
                        'action': action, 'reason': 'HTTP authority control', 'request_key': '018-error-' + action})
                    assert reply.isError and reply.structuredContent['error']['code'] == '018_OPERATOR_AUTHORITY_REQUIRED'
                    assert not reply.structuredContent['execution_permission']['allowed']
        assert (snapshot(legacy), snapshot(db)) == before
    asyncio.run(run())
