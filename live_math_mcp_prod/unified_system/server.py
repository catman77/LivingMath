"""Source-bound Bridge tools composed with the accepted ledger/native/DAV/autonomy tools."""
import asyncio
import functools
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

from davcore.ast import digest, implication
from davcore.mcp import Key, Project
from mcp.types import ToolAnnotations
from pydantic import Field
from research_automation.source_bridge import public_model_inputs

from . import VERSION
from .assets import Assets


def mount(server, assets: Assets, dav, controller, deployment_id: str) -> None:
    ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    rw=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    server._mcp_server.name='SUTI-Bridge-LivingMath'
    server._mcp_server.instructions=(
        'Unified SUTI-Bridge-LivingMath. Start with bridge_system_status and bridge_catalog. '
        'Use bridge_inspect for exact source-bound records, bridge_validate_records for actual SUTI schema/projection checks. '
        'Use bridge_run_alchemy once in a BRIDGE_QA_ project, then research_autonomy_status to watch automatic research. '
        'For raw texts use research_autonomy_ingest with livingmath-artifact/1 and typed008/1; the server constructs models. '
        'For scoped observer/quote semantics and META_ONLY reports use source.interpretation="observer012"; '
        'the older source.interpretation="general011" is also available; '
        'its owner-selected LLM backend and availability are disclosed in artifact_research.general_interpretation. '
        'Read research_autonomy_history(view="report" or "export") for scoped models, source bytes and evidence. '
        'Finite model proofs do not verify historical or physical claims; execution permissions remain separate.')

    def metadata():
        from research_automation.artifact_capabilities import capabilities
        return {'name':'SUTI-Bridge-LivingMath','version':VERSION,'deployment_id':deployment_id,
            'components':{'legacy':'RC020/27 tools and original operator boundaries','SUTI_bridge':'source-bound004 schemas/references',
                          'alchemical_model':'ALCH006 public snapshot','DAV':'dav001.1 + reaction_network','automation':'research-automation/1 + artifact009/1'},
            'artifact_research':capabilities(controller.semantic_provider),
            'SUTI_native_runtime':'NOT_EXECUTED','source_manifest':assets.manifest,
            'tool_count':len(server._tool_manager.list_tools()),'proof_status':'unverified',
            'execution_permission':{'allowed':False}}

    @server.tool(annotations=ro)
    def bridge_system_status()->dict:
        """Read unified version/components and the exact capabilities actually installed on this endpoint."""
        return {**metadata(),'automation_running':'automatic server lifespan; inspect research_autonomy_status(project)',
            'start_checks':['bridge_catalog','bridge_inspect(source_id="ALCH006")',
                            'bridge_validate_records(source_id="P1-001")',
                            'bridge_run_alchemy(project="BRIDGE_QA_CHATGPT_ALCH",request_key="alchemy-first")']}

    @server.tool(annotations=ro)
    def bridge_catalog(query:Annotated[str,Field(max_length=200)]='',offset:Annotated[int,Field(ge=0)]=0,
                       limit:Annotated[int,Field(ge=1,le=20)]=10,project:Project|None=None)->dict:
        """List registered source snapshots. Source IDs select allowlisted data, never a path/module or arbitrary archive."""
        rows=[{'source_id':p['id'],'kind':'SUTI_SOURCE_SCHEMA','archive':p['archive_name'],'member':p['member'],
               'source_sha256':p['source_sha256'],'observer':p['observer'],'hidden_distinction':p['distinguished_field']} for p in assets.bridge['pairs']]
        rows.append({'source_id':'ALCH006','kind':'PUBLIC_ALCHEMICAL_RESEARCH_MODEL','source_sha256':assets.manifest['alch006.json'],
            'title':assets.model['source_identity']['title'],'source_fragments':len(assets.model['source_claims']),
            'unknown_records':len(assets.model['uncertainty'])})
        if project is not None:
            dav.project(project)
            rows.extend({'source_id':f"artifact:{r['id']}:v{r['payload']['version']}",'kind':'PROJECT_ARTIFACT_SNAPSHOT',
                'source_sha256':r['payload']['sha256'],'project':project,'title':r['payload']['source_name']}
                for r in controller.journal.rows(('artifact_source',),project))
        rows=[r for r in rows if query.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
        return {'sources':rows[offset:offset+limit],'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,
                'proof_status':'unverified','execution_permission':{'allowed':False}}

    @server.tool(annotations=ro)
    def bridge_inspect(source_id:Annotated[str,Field(pattern=r'^(P1-001|P1-002|ALCH006|artifact:[1-9][0-9]*:v[1-9][0-9]*)$')],
                       view:Literal['summary','schema','pair','references','source_claims','models','states','transitions','uncertainty','open_obligations','alternatives']='summary',
                       offset:Annotated[int,Field(ge=0)]=0,limit:Annotated[int,Field(ge=1,le=10)]=5,project:Project|None=None)->dict:
        """Inspect real source addresses, original schema-valid witness pairs or the preserved public ALCH006 model.

        Archived numeric event IDs in model provenance are historical only, not current execution grounds.
        Text/document references do not become executable invariants. All model claims remain unverified.
        """
        value: object
        if source_id.startswith('artifact:'):
            if project is None:raise ValueError('PROJECT_REQUIRED_FOR_ARTIFACT_SOURCE')
            from semantic_repair.context009 import packets, resolve
            _,ident,version=source_id.split(':');ctx=resolve(dav.store,project,int(ident))
            if ctx.public()['version']!=int(version[1:]):raise ValueError('SOURCE_VERSION_MISMATCH')
            if view=='summary':value={**ctx.public(),'rights':ctx.record['payload']['rights'],
                'source_name':ctx.record['payload']['source_name'],'raw_UTF8_bytes':len(ctx.record['payload']['raw_text'].encode())}
            elif view in {'source_claims','references'}:value=[s for w in packets(ctx)[0] for s in w['spans']]
            else:raise ValueError('ARTIFACT_EXPORT_USES_RESEARCH_AUTONOMY_HISTORY')
        elif source_id=='ALCH006':
            if view=='summary':
                value={'model_version':assets.model['model_version'],'source':assets.model['source_identity'],
                       'scope':assets.model['scope'],'evaluation':assets.model['evaluation_status']}
            elif view in {'source_claims','models','states','transitions','uncertainty','open_obligations','alternatives'}:
                value=assets.model[view]
            else:raise ValueError('VIEW_NOT_APPLICABLE_TO_ALCHEMICAL_MODEL')
        else:
            pair=next(p for p in assets.bridge['pairs'] if p['id']==source_id)
            if view=='schema':value={'source':{k:pair[k] for k in ['member','archive_name','archive_sha256','source_sha256']},
                                     'schema':json.loads(assets.bridge['schema_members'][pair['member']]['text'])}
            elif view in {'summary','pair'}:value=pair
            elif view=='references':value=[r for r in assets.bridge['relations']+assets.bridge['reviewed_contexts'] if r['pair_id']==source_id]
            else:raise ValueError('VIEW_NOT_APPLICABLE_TO_SUTI_SCHEMA')
        total=len(value) if isinstance(value,list) else 1
        page=value[offset:offset+limit] if isinstance(value,list) else value
        return {'source_id':source_id,'view':view,'data':page,'total':total,
                'next_offset':offset+limit if isinstance(value,list) and offset+limit<total else None,
                'archived_event_ids_are_execution_grounds':False,'proof_status':'unverified','execution_permission':{'allowed':False}}

    @server.tool(annotations=ro)
    async def bridge_validate_records(source_id:Literal['P1-001','P1-002'],
                        records:Annotated[list[dict],Field(min_length=1,max_length=4)]|None=None,
                        projection_fields:Annotated[list[Annotated[str,Field(min_length=1,max_length=80)]],Field(max_length=20)]|None=None)->dict:
        """Validate full records against the actual reviewed SUTI schema and return witnesses of information lost by projection.

        Omit records to replay the original003/004 source-bound pair. Schema admission, observed equality
        and full source equality remain distinct; no runtime permission or global field-independence claim.
        """
        raw=json.dumps({'source_id':source_id,'records':records,'projection_fields':projection_fields}).encode()
        if len(raw)>128000:raise ValueError('BRIDGE_INPUT_BYTE_BOUND')
        process=await asyncio.create_subprocess_exec(sys.executable,'-I','-B',str(Path(__file__).with_name('worker.py')),str(assets.root),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            data,_error=await asyncio.wait_for(process.communicate(raw),timeout=7)
            if process.returncode!=0 or len(data)>256000:
                return {'status':'RESOURCE_OR_WORKER_FAILURE','proof_status':'unverified','execution_permission':{'allowed':False}}
            return json.loads(data)
        except TimeoutError:
            return {'status':'TIMEOUT','proof_status':'unverified','execution_permission':{'allowed':False}}
        finally:
            if process.returncode is None:
                process.kill();await process.wait()

    @server.tool(annotations=rw)
    async def bridge_run_alchemy(project:Project='BRIDGE_QA_CHATGPT_ALCH',request_key:Key='alchemy-first')->dict:
        """Start the real public alchemy case in its own QA project with one call; research continues automatically.

        Imports source-bound requirements, repairs the insufficient P observer, and rechecks the original
        Gate6 implication without adding P⇒Q. Original RH/FTL/canonical events and ALCH006 files are not modified.
        Repeated same request_key does not create another run. Inspect research_autonomy_status(project).
        """
        if not project.startswith(('BRIDGE_QA_','LM_QA_')):
            raise ValueError('CANNED_DEMO_REQUIRES_DEDICATED_QA_PROJECT')
        request_key=digest({'project':project,'request_key':request_key})
        from davcore.adapters import AdapterSpec
        observer=await dav.register(project,AdapterSpec(kind='gate6',mask=1),'unified-alch:'+request_key+':observer')
        if 'id' not in observer:return observer
        packets=public_model_inputs(assets.model,assets.manifest['alch006.json'])
        ids=[]
        for i,packet in enumerate(packets):
            result=controller.ingest(project,packet,'unified-alch:'+request_key+':source:'+str(i))
            ids.extend(result['case_ids'])
        original=await dav.register(project,AdapterSpec(kind='gate6'),'unified-alch:'+request_key+':original')
        if 'id' not in original:return original
        evidence=await dav.compute(project,original['id'],'check',formula=implication('P','One','Joint','One'),
            persist=True,request_key='unified-alch:'+request_key+':original-law',expected_binding=original['payload']['binding'])
        return {'status':'AUTOMATIC_RESEARCH_STARTED','project':project,'source_case_ids':ids,
            'observer_registration_id':observer['id'],'original_law_evidence_id':evidence['id'],
            'source_model_sha256':assets.manifest['alch006.json'],'original_law_status':evidence['payload']['status'],
            'next_action':'research_autonomy_status(project); no manual stage transitions required',
            'proof_status':'unverified','execution_permission':{'allowed':False}}

    for name in ['bridge_system_status','bridge_catalog','bridge_inspect','bridge_validate_records','bridge_run_alchemy']:
        tool=server._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid',strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters=tool.fn_metadata.arg_model.model_json_schema()
    for name in ['research_contract','service_health']:
        tool=server._tool_manager.get_tool(name);original=tool.fn
        def wrapper(fn):
            @functools.wraps(fn)
            def call(*args,**kwargs):
                return {**fn(*args,**kwargs),'unified_system':metadata(),
                        'automatic_research':{'mode':'AUTOMATIC','last_error':controller.last_error}}
            return call
        tool.fn=wrapper(original)
