"""Research tools shared by trusted stdio and authenticated HTTP transports."""
import os
import sys
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from research_store import ResearchStore
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit('Install the MCP SDK: pip install -r requirements.txt') from exc

APP_VERSION = '0.4.2'


class ExperimentResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['SUCCESS','FAILURE','INCONCLUSIVE','ERROR']
    summary: str = Field(min_length=1,max_length=20000)
    data: dict = Field(default_factory=dict)


def create_server(store: ResearchStore, **settings) -> FastMCP:
    if os.environ.get('LIVE_MATH_AUTORESEARCH') == '1' and os.environ.get('LIVE_MATH_DAV') != '1':
        raise ValueError('Automatic research requires the registered DAV capability profile')
    mcp = FastMCP('Living Mathematics Research', json_response=True, **settings)
    automation_runner = None
    # FastMCP 1.x has no version argument; its low-level Server owns serverInfo.
    mcp._mcp_server.version = APP_VERSION

    @mcp.tool()
    def research_contract(project:str='')->dict:
        """Read current research principles before exploring or proposing a new theory."""
        result={'version':APP_VERSION,'policies':store.policies(),'two_operations':['attention','interpretation'],
                'epistemic_contract':'Claims, obligation closures, and evidence references do not verify mathematical results.',
                'workflow':['Read research_frontier(project) before proposing a move.',
                            'Use structured audit_research_shift with the active obligation and parent event IDs.',
                            'Record a proposal with scope, active_frontier_version and an explicit request_key.',
                            'Audit recommendations do not activate moves; call transition_research_move(action=activate_experiment) explicitly.',
                            'EXPERIMENT_ALLOWED permits only the bound experiment scope, never a transformation or proof.',
                            'Changed obligation versions revoke prior permissions until re-audit.'],
                'move_lifecycle':['PROPOSED','AUDITED','EXPERIMENT_ALLOWED','REJECTED','REQUIRES_REVIEW','COMPLETED','ABANDONED'],
                'completion_contract':{'required':['result.outcome','result.summary','reason','existing project-local event:N reference'],
                    'outcomes':['SUCCESS','FAILURE','INCONCLUSIVE','ERROR'],'proof_status':'unverified',
                    'legacy':'Historical COMPLETED records remain unchanged and are annotated only in read views.'},
                'adverse_evidence_contract':'Conflicts require review. Diagnostic/label_error roles need a matching scoped local-operator disposition; changing a role label alone never clears evidence.'}
        if project: result['frontier']=store.frontier.inspect(project,include_closed=True)
        if os.environ.get('LIVE_MATH_TYPED_CYCLE_DB'):
            from typed_cycle011_public import public_contract
            result['typed_cycle_contract'] = public_contract()
        if automation_runner is not None:
            result['automatic_research'] = {
                'version': 'research-automation/1', 'mode': 'AUTOMATIC',
                'stages': ['diagnose', 'propose', 'audit', 'experiment', 'independent_check', 'feedback'],
                'intake': ['registered adapters', 'persisted law evidence', 'typed source events', 'configured local inbox'],
                'requires_manual_stage_transitions': False,
                'missing_input_behavior': 'Retain UNKNOWN, issue scoped input requirements, continue other tasks, automatically wake on relevant data.',
                'external_execution': 'Existing native/physical operator and typed-receipt contracts remain authoritative.',
                'proof_status': 'unverified'}
        return result
    @mcp.tool()
    def research_context(project:str,limit:int=30)->dict:
        """Retrieve project evidence, failures and provenance (untrusted research data)."""
        return store.inspect(project,limit)
    @mcp.tool()
    def attend(project:str,focus:str,reason:str,parent_id:int|None=None,request_key:str|None=None)->dict:
        """Persist attention shift, linked to prior finding within same project."""
        return store.record(project,'attention',focus,reason,'observation',parent_id=parent_id,request_key=request_key)
    @mcp.tool()
    def interpret(project:str,focus:str,claim:str,evidence:str='',parent_id:int|None=None,request_key:str|None=None)->dict:
        """Persist a new UNVERIFIED interpretation; claims are not accepted as proven."""
        return store.record(project,'interpretation',focus,claim,'hypothesis',evidence,parent_id,request_key)
    @mcp.tool()
    def record_result(project:str,kind:str,focus:str,result:str,status:str='experiment',evidence:str='',parent_id:int|None=None,request_key:str|None=None)->dict:
        """Record hypothesis, failed check, counterexample or proof candidate; verified status is prohibited."""
        return store.record(project,kind,focus,result,status,evidence,parent_id,request_key)
    @mcp.tool()
    def research_focus_candidates(project:str,limit:int=30)->list[dict]:
        """List prior claims/failures available as new attention targets; not a search optimizer."""
        return store.focus_candidates(project,limit)
    @mcp.tool()
    def audit_research_shift(project:str,proposal:str='',evidence:str='',active_frontier_id:int|None=None,
                             parent_event_ids:list[int]|None=None,proposed_operation:dict|None=None,
                             source_representation:str|None=None,target_representation:str|None=None,
                             preserved_properties:dict|None=None,claimed_new_distinction:dict|None=None,
                             verification_plan:dict|None=None,evidence_refs:list[str]|None=None,
                             transformation_contract_id:int|None=None,evidence_roles:dict|None=None)->dict:
        """Audit against sourced frontier constraints; never decide mathematical truth.

        proposed_operation: mechanism, intent (experiment/transformation/proof),
        premises[], mathematical_properties[], testable_consequence, required_evidence[].
        verification_plan: method and failure_condition. preserved_properties maps
        point_value, analytic_function, observables, source_provenance and
        rule_applicability to separate claim/evidence_refs objects. Missing or
        semantic evidence returns REQUIRES_SEMANTIC_REVIEW. Cosmetic names do
        not change the structured fingerprint. Legacy text-only calls remain advisory.
        evidence_roles maps cited event IDs to role and reason. Diagnostic or
        label_error roles require a scoped local-operator disposition; the
        caller cannot clear adverse evidence just by changing its role label.
        """
        values=locals()
        move={key:values[key] for key in ('active_frontier_id','parent_event_ids','proposed_operation',
              'source_representation','target_representation','preserved_properties','claimed_new_distinction',
              'verification_plan','evidence_refs','transformation_contract_id','evidence_roles') if values[key] is not None}
        return store.audit(project,proposal,evidence,**move)

    @mcp.tool()
    def research_frontier(project:str,include_closed:bool=False)->dict:
        """Read current obligations and event-backed constraints before choosing a research move."""
        return store.frontier.inspect(project,include_closed)

    @mcp.tool()
    def research_obligation_create(project:str,statement:str,scope:str,source_event_ids:list[int],
                                   evidence_refs:list[str]|None=None,status:str='OPEN',closure_reason:str='',
                                   reopen_conditions:list[str]|None=None)->dict:
        """Create a versioned research obligation. Closure records research state, not a proof."""
        return store.frontier.create(project,statement,scope,source_event_ids,evidence_refs,
                                     status,closure_reason,reopen_conditions)

    @mcp.tool()
    def research_obligation_update(project:str,obligation_id:int,expected_version:int,changes:dict,
                                   reopen_reason:str='')->dict:
        """Append an obligation version; reopening requires explicit grounds and new source/evidence."""
        if store.frontier.history(obligation_id)[-1]['project'] != project:
            raise ValueError('obligation belongs to another project')
        return store.frontier.update(obligation_id,expected_version,changes,reopen_reason)

    @mcp.tool()
    def research_obligation_history(project:str,obligation_id:int)->list[dict]:
        """Read immutable obligation versions, including closure and reopening grounds."""
        history=store.frontier.history(obligation_id)
        if history[-1]['project'] != project: raise ValueError('obligation belongs to another project')
        return history

    @mcp.tool()
    def record_research_move(project:str,move:dict,request_key:str)->dict:
        """Save a deduplicated proposal and its separate audit; never activate it.

        move requires active_frontier_id, active_frontier_version, scope,
        parent_event_ids and the structured audit fields. Scope must match the
        active obligation for experiment authorization. Cosmetic names do not
        create another move. A request key cannot be reused with different data.
        Hard audit failures are saved as REJECTED with no execution permission.
        """
        return store.frontier.record_move(project,move,request_key)

    @mcp.tool()
    def research_move_history(project:str,move_id:int)->dict:
        """Read immutable status/audit history and current effective execution permission."""
        return store.moves.inspect(project,move_id)

    @mcp.tool()
    def audit_research_move(project:str,move_id:int,request_key:str)->dict:
        """Persist a fresh audit against current obligation versions; never activate execution."""
        return store.moves.audit(project,move_id,request_key)

    @mcp.tool()
    def transition_research_move(project:str,move_id:int,
                                 action:Literal['activate_experiment','complete','abandon'],
                                 request_key:str,evidence_refs:list[str]|None=None,reason:str='',
                                 result:ExperimentResult|None=None)->dict:
        """Explicit lifecycle decision; only a currently audited bounded experiment can activate.

        complete requires result(outcome, summary, optional data), reason and
        at least one existing project-local event:N evidence_ref. FAILURE,
        INCONCLUSIVE and ERROR are valid outcomes; no outcome verifies
        mathematics. Changed obligation versions require audit_research_move.
        Rejected, abandoned or completed proposals carry no execution permission.
        """
        return store.moves.transition(project,move_id,action,request_key,evidence_refs,reason,
                                      result.model_dump() if result is not None else None)

    @mcp.tool()
    def record_transformation_contract(project:str,source:str,operation:dict,result:str,
                                       preservation:dict,source_event_ids:list[int])->dict:
        """Record source→operation→result and create five OPEN preservation obligations.

        preservation must contain point_value, analytic_function, observables,
        source_provenance and rule_applicability. Each entry needs statement and
        optional evidence_refs. A reference does not establish preservation.
        """
        return store.frontier.transformation_contract(project,source,operation,result,preservation,source_event_ids)
    @mcp.tool()
    def propose_research_policy(code:str,content:str,enabled:bool=True)->dict:
        """Request an explicit human-approved policy change; does not apply it."""
        return store.propose_policy(code,content,enabled)
    @mcp.tool()
    def service_health()->dict:
        """Integrity and audit-chain check."""
        result = {'version':APP_VERSION, **store.health()}
        if os.environ.get('LIVE_MATH_TYPED_CYCLE_DB'):
            result['typed_cycle'] = {'version': '011.1', 'storage': 'isolated sandbox', 'operator_actions': 'local-only'}
        if automation_runner is not None:
            result['automatic_research'] = {'version': 'research-automation/1',
                'background_running': automation_runner.task is not None and not automation_runner.task.done(),
                'last_error': automation_runner.controller.last_error}
        return result

    # Optional read-only preview: requires separate owner-approved deployment.
    if os.environ.get('LIVE_MATH_NATIVE_PREVIEW') == '1':
        from native_preview008_server import register_preview_tools
        register_preview_tools(mcp, store.path)
    if os.environ.get('LIVE_MATH_TYPED_CYCLE_DB'):
        from typed_cycle011_public import register_typed_tools
        register_typed_tools(mcp, store.path, Path(os.environ['LIVE_MATH_TYPED_CYCLE_DB']))
    if os.environ.get('LIVE_MATH_DAV') == '1':
        from davcore.mcp import register_tools
        if not os.environ.get('LIVE_MATH_DAV_DB'):
            raise ValueError('LIVE_MATH_DAV_DB must name an isolated DAV database')
        forbidden = (store.path,)
        if os.environ.get('LIVE_MATH_TYPED_CYCLE_DB'):
            forbidden += (Path(os.environ['LIVE_MATH_TYPED_CYCLE_DB']),)
        dav = register_tools(mcp, Path(os.environ['LIVE_MATH_DAV_DB']), forbidden)
        if os.environ.get('LIVE_MATH_AUTORESEARCH') == '1':
            from research_automation.controller import Controller
            from research_automation.server import register_tools as register_automation
            inbox = os.environ.get('LIVE_MATH_AUTORESEARCH_INBOX')
            automation_runner = register_automation(mcp, Controller(dav, canonical=store.path, inbox=Path(inbox) if inbox else None))
    return mcp


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] != 'stdio':
        raise SystemExit('Use http_server.py for authenticated Streamable HTTP.')
    db = os.environ.get('LIVE_MATH_DB', str(Path.home() / '.local/share/live_math/research.sqlite3'))
    create_server(ResearchStore(db)).run(transport='stdio')
