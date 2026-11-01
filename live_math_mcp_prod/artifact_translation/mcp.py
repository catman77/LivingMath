"""Optional tools for private BackupAPI clones; never auto-mounted in production."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field
from davcore.mcp import Project, Key, PositiveID, Binding
from davcore.adapters import AdapterSpec
from davcore.ast import digest
from .contract import ProposalRequest, SourceGraph
from .checker import check_translation, evaluate_laws, repair
from .network import Network


def private_clone_guard(root: Path, canonical: Path, dav: Path) -> None:
    root=root.resolve(strict=True)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077:
        raise ValueError('OWNER_ONLY_PRIVATE_QA_ROOT_REQUIRED')
    receipt=root/'clone-receipt.json'
    if receipt.is_symlink() or receipt.stat().st_mode&0o077:
        raise ValueError('PRIVATE_CLONE_RECEIPT_REQUIRED')
    proof=json.loads(receipt.read_text())
    if proof.get('purpose')!='ARTIFACT_TRANSLATION001_PRIVATE_BACKUP_CLONES':
        raise ValueError('PRIVATE_CLONE_RECEIPT_REQUIRED')
    for role,path in [('canonical',canonical),('dav',dav)]:
        path=path.resolve(strict=True)
        if not path.is_relative_to(root) or path.is_symlink():raise ValueError('WRITES_OUTSIDE_PRIVATE_CLONE')
        if path.stat().st_ino!=proof[role]['inode']:raise ValueError('PRIVATE_CLONE_IDENTITY_CHANGED')
        original=Path(proof[role]['source'])
        if original.exists() and path.samefile(original):raise ValueError('PRODUCTION_DATABASE_FORBIDDEN')


_GENERATOR_SLOTS=asyncio.Semaphore(2)


async def generate(request: ProposalRequest) -> dict:
    async with asyncio.timeout(8):
        async with _GENERATOR_SLOTS:
            return await _generate(request)


async def _generate(request: ProposalRequest) -> dict:
    raw=json.dumps(request.model_dump()).encode()
    process=await asyncio.create_subprocess_exec(sys.executable,'-I','-B',str(Path(__file__).with_name('worker.py')),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        cwd='/tmp',env={'PATH':os.defpath,'LANG':'C.UTF-8'},start_new_session=True)
    try:
        data,error=await asyncio.wait_for(process.communicate(raw),timeout=7)
        if process.returncode!=0 or len(data)>1000000:
            raise ValueError('BOUNDED_GENERATOR_FAILURE:'+error.decode(errors='replace')[-300:])
        return json.loads(data)
    finally:
        if process.returncode is None:process.kill();await process.wait()


def binding() -> str:
    return digest({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})


def register_tools(mcp, dav, private_root: Path, canonical: Path, source_bindings: dict[str,str]) -> None:
    private_clone_guard(private_root,canonical,dav.store.path)
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    def guard(project):
        if not project.startswith(('BRIDGE_QA_','LM_QA_')):raise ValueError('DEDICATED_QA_PROJECT_REQUIRED')
        private_clone_guard(private_root,canonical,dav.store.path)

    @mcp.tool(annotations=write)
    async def artifact_translation_propose(project: Project, request: ProposalRequest, request_key: Key) -> dict:
        """Propose competing source-bound symbolic networks in private QA. No empirical verification or execution grant.

        Input is relation data only; no code, raw artifact path, checker or hidden answer is accepted.
        SEARCH_EXHAUSTED describes this bounded edit family, not scientific success.
        """
        guard(project)
        source_sha=digest(request.graph.model_dump())
        if source_bindings.get(request.graph.id)!=source_sha:
            raise ValueError('SOURCE_GRAPH_NOT_IN_OWNER_FROZEN_SOURCE_CATALOG')
        identity={'action':'artifact_propose','request':request.model_dump(),'binding':binding(),
                  'frozen_source_graph_sha256':source_sha}
        old=dav.store.repeated(project,request_key,identity)
        if old:return old
        proposals=await generate(request)
        return dav.store.append(project,'artifact_translation',request_key,identity,
            {'source_graph':request.graph.model_dump(),'proposals':proposals,'status':'PROPOSED',
             'scope':'PRIVATE_CLONE_STAGING_ONLY','proof_status':'unverified','execution_permission':{'allowed':False}})

    @mcp.tool(annotations=write)
    async def artifact_translation_check(project: Project, proposal_id: PositiveID, candidate_id: Binding,
        request_key: Key, repair_on_conflict: bool = False,
        max_laws: Annotated[int,Field(ge=1,le=24)] = 24) -> dict:
        """Independently check source reverse traces; register valid descriptors in DAV and check scoped laws.

        Optional local role repair retains the original conflict and adds a revision. Validity is
        relative to declared textual B-relations, not verification of meaning or physical chemistry.
        """
        guard(project);identity={'action':'artifact_check','proposal_id':proposal_id,'candidate_id':candidate_id,
            'repair_on_conflict':repair_on_conflict,'max_laws':max_laws,'binding':binding()}
        old=dav.store.repeated(project,request_key,identity)
        if old:return old
        proposal=dav.store.get(project,proposal_id)
        if proposal['kind']!='artifact_translation':raise ValueError('EXPECTED_TRANSLATION_PROPOSAL')
        graph=SourceGraph.model_validate(proposal['payload']['source_graph'])
        candidate=next((c for c in proposal['payload']['proposals']['candidates'] if c['candidate_id']==candidate_id),None)
        if candidate is None:raise ValueError('CANDIDATE_NOT_IN_BOUND_PROPOSAL')
        original=check_translation(graph,candidate);revision=None
        if original['conflicts'] and repair_on_conflict:
            revision=repair(graph,candidate);candidate=revision['candidate']
        checked=check_translation(graph,candidate);registration=None;laws=[]
        if checked['status']=='FORMAL_TRANSLATION_VALID':
            registration=await dav.register(project,AdapterSpec(kind='reaction_network',
                reaction_network=Network.model_validate(candidate['network'])),'at-reg:'+digest(identity))
            if 'id' not in registration:raise ValueError('DAV_REGISTRATION_DID_NOT_PASS_OPERATION_AUDIT')
            laws=evaluate_laws(candidate,max_laws=max_laws)
        return dav.store.append(project,'artifact_translation_check',request_key,identity,
            {'proposal_id':proposal_id,'candidate_id':candidate_id,'original_check':original,'repair':revision,
             'effective_check':checked,'registration':registration,'laws':laws,
             'status':checked['status'],'new_structural_source_law':'UNESTABLISHED',
             'proof_status':'unverified','execution_permission':{'allowed':False}})

    @mcp.tool(annotations=read)
    def artifact_translation_history(project: Project, offset: Annotated[int,Field(ge=0)]=0,
                                     limit: Annotated[int,Field(ge=1,le=20)]=10) -> dict:
        """Read project-local append-only proposal/check summaries and integrity, including original failures."""
        guard(project)
        with dav.store.connect() as connection:
            rows=connection.execute("SELECT * FROM dav_records WHERE project=? AND kind LIKE 'artifact_translation%' ORDER BY id",(project,)).fetchall()
        decoded=[dav.store.decode(row) for row in rows[offset:offset+limit]]
        return {'records':[{'id':r['id'],'kind':r['kind'],'entry_hash':r['entry_hash'],
            'status':r['payload']['status'],'candidate_id':r['payload'].get('candidate_id')} for r in decoded],
            'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,
            'integrity':dav.store.integrity(),'proof_status':'unverified','execution_permission':{'allowed':False}}

    for name in ['artifact_translation_propose','artifact_translation_check','artifact_translation_history']:
        tool=mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid',strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True);tool.parameters=tool.fn_metadata.arg_model.model_json_schema()
