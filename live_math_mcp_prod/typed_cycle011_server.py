"""Separate isolated endpoint. Operator activation/commit are never model tools."""
import argparse
from pathlib import Path
from mcp.types import ToolAnnotations
from mcp.server.fastmcp import FastMCP
from research_store import ResearchStore
from native_preview008_contract import NativeRequest, Project, EventID
from typed_cycle011 import TypedCycle
from typed_cycle011_contract import VERSION
from typed_cycle011_store import connect, scope, assert_isolated


def create_typed_server(database):
    database=Path(database).resolve(strict=True)
    assert_isolated(database)
    engine=TypedCycle(database);store=ResearchStore(database)
    mcp=FastMCP('LivingMath typed011 isolated QA',json_response=True);mcp._mcp_server.version=VERSION
    readonly=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)

    def qa(project):
        if not project.startswith('LM_QA_TYPED011_'):raise ValueError('UNAUTHORIZED_PROJECT_WRITE')

    @mcp.tool()
    def record_result(project:str,kind:str,focus:str,result:str,status:str='experiment',evidence:str='',parent_id:int|None=None,request_key:str|None=None)->dict:
        """Append QA source data only; never verifies or grants an experiment."""
        qa(project)
        return store.record(project,kind,focus,result,status,evidence,parent_id,request_key)

    @mcp.tool()
    def research_obligation_update(project:str,obligation_id:int,expected_version:int,changes:dict,reopen_reason:str='')->dict:
        """Append an isolated QA frontier version, revoking obsolete grants."""
        qa(project)
        if store.frontier.history(obligation_id)[-1]['project']!=project:raise ValueError('FOREIGN_OBLIGATION')
        return store.frontier.update(obligation_id,expected_version,changes,reopen_reason)

    @mcp.tool(annotations=readonly)
    def research_move_history(project:str,move_id:int)->dict:
        return store.moves.inspect(project,move_id)

    @mcp.tool(annotations=readonly)
    def research_cycle_preview(request:NativeRequest)->dict:
        """004→007 I→006 T; authoritative novelty, no writes, measurements or grants."""
        return engine.preview(request.model_dump())

    @mcp.tool(annotations=readonly)
    def research_cycle_validate(project:Project,move_id:EventID,event_id:EventID)->dict:
        """Independent SELECT-only binding check; local receipt integrity is not physical truth."""
        return engine.validate(project,move_id,event_id)

    @mcp.tool(annotations=readonly)
    def research_novelty_snapshot(request:NativeRequest)->dict:
        """Server-owned scope-local history; ignores caller known_fingerprints."""
        try:
            _,current,_,registered,claim,_=engine.context(request)
            with connect(database) as c:
                rows=[dict(r) for r in c.execute('SELECT id,claim_fingerprint,raw_sha256,receipt_id FROM typed011_journal WHERE project=? AND scope=? AND source_family_id=? ORDER BY id',(request.project,current['scope'],registered['source_family_id']))]
            return {'status':'AUTHORITATIVE_SNAPSHOT','snapshot_complete':True,'caller_known_ignored':True,'claim_fingerprint':claim,
                'journal':rows,'proof_status':'unverified','execution_permission':{'allowed':False}}
        except (ValueError,KeyError) as error:
            return {'status':'NOVELTY_CONTEXT_INCOMPLETE','reason':str(error),'snapshot_complete':False,
                'proof_status':'unverified','execution_permission':{'allowed':False}}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def research_cycle_precommit(request:NativeRequest,request_key:str)->dict:
        """Persist exact source/test precommit before audit; this never authorizes execution."""
        return engine.precommit(request.model_dump(),request_key)

    for name in ('research_cycle_preview','research_cycle_validate','research_novelty_snapshot','research_cycle_precommit'):
        tool=mcp._tool_manager.get_tool(name);tool.fn_metadata.arg_model.model_config.update(extra='forbid',strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True);tool.parameters=tool.fn_metadata.arg_model.model_json_schema()
    return mcp


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);a=p.parse_args()
    create_typed_server(a.db).run(transport='stdio')
