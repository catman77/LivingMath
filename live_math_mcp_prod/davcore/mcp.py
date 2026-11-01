"""Strict optional FastMCP adapter tools, sharing the server's existing auth boundary."""
import logging
from typing import Annotated, Literal
from pathlib import Path

from mcp.types import ToolAnnotations
from pydantic import Field

from .adapters import AdapterSpec
from .ast import Formula
from .models import Budget
from .service import Service

Project = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[\w][\w.-]*$')]
PositiveID = Annotated[int, Field(ge=1)]
Binding = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
States = Annotated[list[Annotated[int, Field(ge=0, le=1023)]], Field(max_length=1024)]
Key = Annotated[str, Field(min_length=1, max_length=200)]
TOOLS = ('dav_register_adapter', 'dav_observe', 'dav_check_law', 'dav_generate_candidates',
         'dav_reduce_library', 'dav_find_counterexample', 'dav_audit_adapter', 'dav_export_evidence')
LOG = logging.getLogger('livingmath.dav')


def register_tools(mcp, database: Path, forbidden: tuple[Path, ...]) -> Service:
    service = Service(database, forbidden)
    # Check/observe/reduce may explicitly persist; never advertise them as unconditionally read-only.
    optional_write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    async def compute(project, registration_id, adapter_binding, action, **kwargs):
        try:
            out = await service.compute(project, registration_id, action, expected_binding=adapter_binding, **kwargs)
        except (ValueError, TypeError):
            LOG.warning('DAV_REQUEST_REJECTED action=%s project=%s registration=%s', action, project, registration_id)
            raise
        LOG.info('DAV_REQUEST action=%s project=%s registration=%s status=%s', action, project, registration_id,
                 out.get('status', out.get('payload', {}).get('status')))
        return out

    @mcp.tool(annotations=optional_write)
    async def dav_register_adapter(project: Project, spec: AdapterSpec, request_key: Key) -> dict:
        """Register allowlisted CA/GraphBits/conditional-Gate6 or capacity-one reaction_network. No code/path input.

        Writes only the isolated DAV store. Registration/audit never grants research execution.
        A projected descriptor retains raw full states; audit may forbid a quotient interpretation.
        """
        out = await service.register(project, spec, request_key)
        LOG.info('DAV_REGISTER project=%s id=%s', project, out.get('id'))
        return out

    @mcp.tool(annotations=optional_write)
    async def dav_observe(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                          states: States, budget: Budget = Budget(), persist: bool = False,
                          request_key: Key | None = None) -> dict:
        """Observe bounded original states and all operation outputs. Observations never imply a full-world proof."""
        return await compute(project, registration_id, adapter_binding, 'observe', states=states, budget=budget,
                             persist=persist, request_key=request_key)

    @mcp.tool(annotations=optional_write)
    async def dav_check_law(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                            formula: Formula, states: States | None = None,
                            backend: Literal['finite', 'smt'] = 'finite', budget: Budget = Budget(),
                            persist: bool = False, request_key: Key | None = None) -> dict:
        """Check a bound typed formula. proved is only adapter-relative finite/encoded semantics; never scientific verified.

        Explicit states ALWAYS mean sampled evidence. Complete enumeration is determined internally.
        Equality scope full_state/observation is explicit. Default computation writes no certificate.
        """
        return await compute(project, registration_id, adapter_binding, 'check', formula=formula, states=states,
                             backend=backend, budget=budget, persist=persist, request_key=request_key)

    @mcp.tool(annotations=read)
    async def dav_generate_candidates(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                                      offset: Annotated[int, Field(ge=0, le=40000)] = 0,
                                      budget: Budget = Budget(max_candidates=64)) -> dict:
        """Deterministic paged symbolic equation-implication proposals; no proof or neural policy implied."""
        return await compute(project, registration_id, adapter_binding, 'generate', offset=offset, budget=budget)

    @mcp.tool(annotations=optional_write)
    async def dav_reduce_library(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                                 states: States | None = None, budget: Budget = Budget(),
                                 persist: bool = False, request_key: Key | None = None) -> dict:
        """Reduce checked laws by exact premise/conclusion vectors and subsumption; not a minimal axiom basis.

        Partial candidate search is marked search_complete=false. Sample relations remain empirical.
        Explicit persist saves one append-only library with its scope and evidence vectors.
        """
        return await compute(project, registration_id, adapter_binding, 'reduce', states=states, budget=budget,
                             persist=persist, request_key=request_key)

    @mcp.tool(annotations=optional_write)
    async def dav_find_counterexample(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                                      formula: Formula, states: States | None = None,
                                      backend: Literal['finite', 'smt'] = 'finite', budget: Budget = Budget(),
                                      persist: bool = False, request_key: Key | None = None) -> dict:
        """Return a concrete raw-state violation and full replay steps, or an explicitly scoped undecided/proved result."""
        return await compute(project, registration_id, adapter_binding, 'find_counterexample', formula=formula,
                             states=states, backend=backend, budget=budget, persist=persist, request_key=request_key)

    @mcp.tool(annotations=read)
    async def dav_audit_adapter(project: Project, registration_id: PositiveID, adapter_binding: Binding,
                                budget: Budget = Budget()) -> dict:
        """Audit total deterministic builtin semantics and projected observational congruence; return actual paired witness."""
        return await compute(project, registration_id, adapter_binding, 'audit', budget=budget)

    @mcp.tool(annotations=read)
    def dav_export_evidence(project: Project, evidence_id: PositiveID) -> dict:
        """Read project-local immutable evidence and effective binding validity; no grant, verification or raw DB exposure."""
        return service.export(project, evidence_id)

    for name in TOOLS:
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid', strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()
    return service
