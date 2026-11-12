"""Opt-in local acceptance server over real existing tool registrations."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(1, str(ROOT/'live_math_mcp_prod'))


def build(root, executor=None, coverage=True):
    import mcp_server
    from research_store import ResearchStore
    # The same legacy tools, with a QA-only temporary database/configuration.
    from lm_suti_assurance.mcp import register_tools
    from lm_suti_assurance.white_star.mcp import register_tools as white
    from lm_suti_assurance.symbolic.mcp import register_tools as symbolic
    from lm_suti_assurance.symbolic_complex.mcp import register_tools as complex_tools
    from lm_suti_assurance.semantic_bridge.mcp import register_tools as semantic
    from lm_suti_assurance.semantic_bridge.contextual.mcp import register_tools as contextual
    from lm_suti_assurance.nl_proposal.mcp import register_tools as nl
    from lm_suti_assurance.nl_proposal.causal_mcp import register_tools as causal
    from lm_suti_assurance.udav_core.mcp import register_tools as udav
    server = mcp_server.create_server(ResearchStore(Path(root).parent/'legacy-qa.sqlite3'), stateless_http=True)
    register_tools(server, root)
    white(server, root)
    symbolic(server, root)
    complex_tools(server, root, None)
    semantic(server, root)
    contextual(server, root, None)
    nl(server, root, None)
    causal(server, root, None)
    udav(server, root, None, numeric=True)
    if coverage:
        from lm_suti_assurance.completeness.mcp import register_tools as register_coverage
        register_coverage(server, root, executor)
    return server


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--port', type=int, default=18765)
    p.add_argument('--without-coverage', action='store_true')
    a = p.parse_args()
    from lm_suti_assurance.completeness.executor import Executor
    from lm_suti_assurance.symbolic.executor import SharedBudget
    executor = Executor(SharedBudget())
    try:
        if not executor.status()['ready']:
            raise RuntimeError(executor.status())
        server = build(a.state, executor, coverage=not a.without_coverage)
        server.settings.host = '127.0.0.1'
        server.settings.port = a.port
        server.run(transport='streamable-http')
    finally:
        executor.close()


if __name__ == '__main__':
    main()
