"""Default-off staging mounting of017. Production entrypoints are unchanged."""
import argparse
import copy
import functools
import json
import os
from pathlib import Path
import resource
from typing import Union
from mcp.types import ToolAnnotations
from research_store import ResearchStore
from mcp_server import create_server as base_server
from native_preview008_contract import NativeRequest
from law_validation014_contract import Request014
from typed_cycle011 import TypedCycle
from typed_cycle011_store import assert_isolated, connect
from engine017_contract import Query017, SourceEnvelope017, FLAG
from engine017_controller import EngineController017
from law_validation014_isolation import restrict_reads

Request = Union[Query017, Request014, NativeRequest]


def create_server(canonical_database, engine_database, enabled=None):
    canonical_database = Path(canonical_database).resolve(strict=True)
    engine_database = Path(engine_database).resolve(strict=True)
    if enabled is None:
        enabled = os.environ.get(FLAG) == '1'
    if not enabled:
        return base_server(ResearchStore(canonical_database))
    assert_isolated(engine_database)
    # Keep the old18/20 tools, then replace only the four typed adapters.
    old = os.environ.pop('LIVE_MATH_TYPED_CYCLE_DB', None)
    try:
        mcp = base_server(ResearchStore(canonical_database))
    finally:
        if old is not None:
            os.environ['LIVE_MATH_TYPED_CYCLE_DB'] = old
    engine = EngineController017(engine_database)
    legacy = TypedCycle(engine_database)
    store = ResearchStore(canonical_database)
    with store._connect() as c:
        historical_max = c.execute('SELECT COALESCE(max(id),0) FROM research_moves').fetchone()[0]
    ro = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    def managed(project):
        return project.startswith('LM_QA_TYPED011_ENGINE017_')

    def typed_namespace(project):
        return project.startswith('LM_QA_TYPED011_')

    def replace(name, wrapper):
        tool = mcp._tool_manager.get_tool(name)
        original = tool.fn
        replacement = functools.wraps(original)(wrapper(original))
        annotations = tool.annotations
        mcp.remove_tool(name)
        mcp.add_tool(replacement, name=name, description=tool.description, annotations=annotations)

    def guard_writer(name):
        def factory(original):
            def wrapped(*args, **kwargs):
                import inspect
                bound = inspect.signature(original).bind(*args, **kwargs)
                bound.apply_defaults()
                data = dict(bound.arguments)
                project = data.get('project', '')
                if typed_namespace(project):
                    raise ValueError('TYPED_ROUTE_REQUIRED: model cannot activate/complete/measure engine claims through legacy tools')
                if project and not project.startswith('LM_QA_'):
                    raise ValueError('STAGING_QA_NAMESPACE_REQUIRED')
                if name == 'record_result':
                    try:
                        body = json.loads(data.get('result', ''))
                    except (ValueError, TypeError):
                        body = {}
                    if isinstance(body, dict) and ('measurement_binding' in body or str(body.get('claim_protocol', '')).startswith('typed')):
                        raise ValueError('TYPED_MEASUREMENT_REQUIRES_PINNED_EXECUTOR')
                if name == 'record_research_move':
                    move = copy.deepcopy(data['move'])
                    operation = move.get('proposed_operation', {})
                    if 'cycle_binding' in operation or operation.get('claim_protocol', 'legacy/v1') != 'legacy/v1':
                        raise ValueError('TYPED_ROUTE_REQUIRED')
                    operation['claim_protocol'] = 'legacy/v1'
                    move['proposed_operation'] = operation
                    data['move'] = move
                if name == 'transition_research_move':
                    view = store.moves.inspect(project, data['move_id'])
                    protocol = view.get('proposed_operation', {}).get('claim_protocol')
                    if protocol != 'legacy/v1' and data['move_id'] > historical_max:
                        raise ValueError('EXPLICIT_LEGACY_PROTOCOL_REQUIRED')
                result = original(**data)
                if name in ('record_research_move', 'transition_research_move'):
                    result['claim_protocol'] = 'legacy/v1' if result.get('proposed_operation', {}).get('claim_protocol') == 'legacy/v1' else 'legacy/historical'
                return result
            return wrapped
        return factory

    for name in ('record_result', 'record_research_move', 'transition_research_move', 'audit_research_move',
                 'research_obligation_create', 'research_obligation_update', 'record_transformation_contract', 'attend', 'interpret'):
        if mcp._tool_manager.get_tool(name):
            replace(name, guard_writer(name))

    @mcp.tool(annotations=ro)
    def research_cycle_preview(request: Request) -> dict:
        """017 source-owned004/I/T preview; legacy011 adapter remains compatible. No grants."""
        data = request.model_dump()
        return engine.preview(data) if managed(data['project']) else legacy.preview(data)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def research_cycle_precommit(request: Request, request_key: str) -> dict:
        """Persist a source-bound proposal only. Local owner must audit/activate separately."""
        data = request.model_dump()
        return engine.precommit(data, request_key) if managed(data['project']) else legacy.precommit(data, request_key)

    @mcp.tool(annotations=ro)
    def research_cycle_validate(project: str, move_id: int, event_id: int) -> dict:
        """Read-only typed semantic validator. A premise event never completes an engine claim."""
        return (engine if managed(project) else legacy).validate(project, move_id, event_id)

    @mcp.tool(annotations=ro)
    def research_novelty_snapshot(request: Request) -> dict:
        """Use server journal/latest committed feedback; caller memory does not grant novelty."""
        data = request.model_dump()
        if managed(data['project']):
            return engine.novelty(data)
        # Delegate the accepted011 implementation rather than invent a second legacy controller.
        from typed_cycle011_server import create_typed_server
        accepted = create_typed_server(engine_database)
        return accepted._tool_manager.get_tool('research_novelty_snapshot').fn(request)

    @mcp.tool(annotations=ro)
    def research_cycle_next(query: Query017) -> dict:
        """Server-owned next proposal or explicit stop/wait. Never activates, measures or commits."""
        return engine.preview(query.model_dump())

    @mcp.tool(annotations=ro)
    def research_cycle_history(project: str) -> dict:
        """Persistent source, status, receipts and applicability versions across clients/restarts."""
        return engine.history(project)

    @mcp.tool(annotations=ro)
    def research_source_contract(project: str) -> dict:
        """Registered immutable data envelope, inspection limits and no executable capabilities."""
        manifest, _ = engine.registered(project)
        return {'status': 'SOURCE_BOUND', 'source': manifest, 'schema': SourceEnvelope017.model_json_schema(),
            'proof_status': 'unverified', 'execution_permission': {'allowed': False}}

    def contract_wrapper(original):
        def wrapped(*args, **kwargs):
            out = original(*args, **kwargs)
            out['engine017'] = {'version': '017.1', 'feature_flag': FLAG, 'default_enabled': False,
                'authority': {'model': ['preview', 'precommit', 'next', 'history'], 'owner': ['register', 'audit', 'activate', 'commit'],
                    'executor': ['fresh signed bound source attempt']}, 'legacy': 'Explicit legacy/v1 only; never typed receipt promotion',
                'scope': 'staging registered QA sources; R4/R5/R6/R7 not established', 'physical_authenticity': 'NOT_CLAIMED'}
            return out
        return wrapped
    replace('research_contract', contract_wrapper)
    for name in ('research_cycle_preview', 'research_cycle_precommit', 'research_cycle_validate', 'research_novelty_snapshot',
                 'research_cycle_next', 'research_cycle_history', 'research_source_contract'):
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid', strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()
    return mcp


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--canonical', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--forbidden', type=Path, action='append', default=[])
    args = parser.parse_args()
    os.environ['LIVE_MATH_TYPED_CYCLE_DB'] = str(args.db)
    os.environ['LIVE_MATH_NATIVE_PREVIEW'] = '1'
    server = create_server(args.canonical, args.db)
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    if os.environ.get(FLAG) == '1':
        for name in ('engine017_operator', 'engine017_executor', 'law_validation014_oracle'):
            if name in __import__('sys').modules:
                raise RuntimeError('AUTHORITY_MODULE_PRELOADED:' + name)
        evidence = restrict_reads(args.db.parent, args.forbidden)
        (args.db.parent / 'engine017-isolation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    server.run(transport='stdio')
