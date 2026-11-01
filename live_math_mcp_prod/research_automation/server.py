"""Automatic worker lifetime for stdio AND the entire stateless HTTP application."""
import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from davcore.mcp import Project, PositiveID, Key
from .contract import ResearchInput
from .artifact_contract import ArtifactInput


class Runner:
    def __init__(self, controller):
        self.controller = controller
        self.users = 0
        self.task = None

    @asynccontextmanager
    async def lifespan(self):
        self.users += 1
        if self.task is None:
            self.task = asyncio.create_task(self.controller.run(), name='LivingMath automatic research')
        try:
            yield
        finally:
            self.users -= 1
            if self.users == 0 and self.task is not None:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                self.task = None


def register_tools(mcp, controller) -> Runner:
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    @mcp.tool(annotations=write)
    def research_autonomy_ingest(project: Project, source: ResearchInput | ArtifactInput, request_key: Key) -> dict:
        """Supply scoped source/model inputs once; all computational research stages then run automatically.

        livingmath-artifact/1 accepts raw UTF-8 or pinned source snapshot, rights,
        typed008/1 reaction_network and bounded budgets; the server builds models.
        Optional interpretation="general011" enables addressed source relations,
        independent source critique and named observation projections. It uses
        an owner-configured model; availability is explicit in bridge_system_status.
        Declared facts are not independent empirical verification. A new relevant source
        automatically revalidates waiting/completed cases, preserving adverse history.
        Existing native/physical operator permissions remain separate.
        """
        return controller.ingest(project, source, request_key)

    @mcp.tool(annotations=read)
    def research_autonomy_status(project: Project, case_id: PositiveID | None = None,
                                  offset: Annotated[int, Field(ge=0)] = 0,
                                  limit: Annotated[int, Field(ge=1, le=20)] = 10) -> dict:
        """Observe automatically running/waiting cases; no advance, audit or activation calls are necessary."""
        result = controller.status(project)
        cases = result['cases']
        if case_id is not None:
            controller.journal.case(project, case_id)
            cases = [c for c in cases if c['case_id'] == case_id]
        result.update(cases=cases[offset:offset + limit], total_cases=len(cases),
                      next_offset=offset + limit if offset + limit < len(cases) else None)
        return result

    @mcp.tool(annotations=write)
    def research_autonomy_control(project: Project, case_id: PositiveID,
                                   action: Literal['pause', 'resume', 'cancel'], request_key: Key) -> dict:
        """Interrupt/resume a computational case. This is not a manual stage-advance or mathematical permission tool."""
        return controller.control(project, case_id, action, request_key)

    @mcp.tool(annotations=read)
    def research_autonomy_history(project: Project, case_id: PositiveID,
                                   after_sequence: Annotated[int, Field(ge=-1)] = -1,
                                   limit: Annotated[int, Field(ge=1, le=20)] = 10,
                                   view: Literal['steps','export','report']='steps',
                                   after_record_id: Annotated[int,Field(ge=0)]=0,
                                   byte_offset: Annotated[int,Field(ge=0)]=0,
                                   max_bytes: Annotated[int,Field(ge=4096,le=128000)]=60000) -> dict:
        """Page the complete immutable lifecycle, including failed proposals, RCA, input requests and checker record IDs."""
        controller.journal.case(project, case_id)
        if view!='steps':
            from .artifact import export,report
            if view=='report':return report(controller,project,case_id,max_bytes)
            return export(controller,project,case_id,after_record_id,byte_offset,limit,max_bytes)
        rows = [r for r in controller.journal.steps(project, case_id) if r['payload']['sequence'] > after_sequence]
        page = rows[:limit]
        return {'case_id': case_id, 'steps': page, 'more': len(rows) > limit,
                'next_after_sequence': page[-1]['payload']['sequence'] if len(rows) > limit else None,
                'proof_status': 'unverified', 'execution_permission': {'allowed': False}}

    for name in ['research_autonomy_ingest', 'research_autonomy_status', 'research_autonomy_control', 'research_autonomy_history']:
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid', strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()

    runner = Runner(controller)
    previous = mcp._mcp_server.lifespan

    @asynccontextmanager
    async def low_level_lifespan(server):
        async with previous(server) as context:
            async with runner.lifespan():
                yield context
    mcp._mcp_server.lifespan = low_level_lifespan

    # FastMCP starts a low-level server for EACH stateless HTTP request.
    # Keep a reference for the whole ASGI app so research continues with no client connected.
    previous_http_factory = mcp.streamable_http_app

    def streamable_http_app(*args, **kwargs):
        app = previous_http_factory(*args, **kwargs)
        previous_http_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def app_lifespan(application):
            async with runner.lifespan():
                async with previous_http_lifespan(application) as context:
                    yield context
        app.router.lifespan_context = app_lifespan
        return app
    mcp.streamable_http_app = streamable_http_app
    return runner
