import asyncio

from mcp_server import create_server
from research_store import ResearchStore
from transfer_qa import Experiment


def test_all_ten_deterministic_controls_before_any_live_write(tmp_path):
    store = ResearchStore(tmp_path / 'qa.sqlite3')
    server = create_server(store)
    experiment = Experiment.__new__(Experiment)
    experiment.base = tmp_path
    experiment.db = store.path
    experiment.stamp = 'local_only'
    experiment.bindings, experiment.controls = {}, []

    class Client:
        async def call(self, name, arguments, allow_error=False):
            try:
                return await server._tool_manager.call_tool(name, arguments)
            except Exception:
                if allow_error:
                    return None
                raise

    asyncio.run(experiment.deterministic_controls(Client()))
    assert len(experiment.controls) == 10
    assert all(c['result'] == 'PASS' for c in experiment.controls)
    with store._connect() as connection:
        moves = [(r['project'], r['id']) for r in connection.execute('SELECT project,id FROM research_moves')]
    assert all(not store.moves.inspect(project, mid)['execution_permission']['allowed'] for project, mid in moves)
    assert store.verify_audit()['ok']
