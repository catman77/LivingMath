"""Additive owner-only semantic tools. Imported frames are never model certificates."""
import base64
from typing import Annotated,Literal
from pydantic import Field
from mcp.types import ToolAnnotations
from ..mcp import Project,Key,Ref,Json
from ..errors import AssuranceError
from ..workspace import private_dir,atomic_write
from ..bundle import replay,MAX_BUNDLE
from ..core import canonical,digest
from ..validation import parse
from .records import SCHEMAS,schema
from .service import SemanticService
from .report import dossier
from .bundle import export


def register_tools(server,root,provider=None):
    s=SemanticService(root);ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    rw=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    model_rw=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=True)
    def call(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except AssuranceError as exc:return exc.as_dict()

    @server.tool(annotations=ro)
    def semantic_contract()->dict:
        """Exact semantic schemas, source scope, workflow and epistemic boundaries. Existing assurance tools stay unchanged."""
        return {'version':'semantic-bridge/1','release':'v0.2.0-developer-preview',
                'schemas':{p.name.removesuffix('.schema.json'):schema(p.name.removesuffix('.schema.json')) for p in sorted(SCHEMAS.glob('*.json'))},
                'hosted_backend':'OWNER_PIPE_CODEX_CHATGPT' if provider else 'MODEL_UNAVAILABLE',
                'model':'gpt-6.1-sol','R3':'PENDING','native_SUTI':'NOT_EXECUTED','execution_permission':False,
                'workflow':['assurance_project_new','assurance_source_add','semantic_source','semantic_draft','semantic_revise','semantic_compare','semantic_report','semantic_export','semantic_replay'],
                'boundary':'Interpretations UNKNOWN; SOURCE_ATTESTED applies only to exact independently bound quote bytes; structural loss only declared finite annotations/Q.'}

    @server.tool(annotations=rw)
    def semantic_source(project:Project,source_ref:Ref,metadata_json:Json,actor:Annotated[str,Field(min_length=1,max_length=160)],
                        reason:Annotated[str,Field(min_length=1,max_length=2000)],request_key:Key)->dict:
        """Pin author/title/edition/editorial_source_url/edition_status over an existing source_ref and confirm limited task scope."""
        try:return call(s.edition,project,source_ref,parse(metadata_json),actor,reason,request_key)
        except AssuranceError as exc:return exc.as_dict()

    async def read(project,edition_ref,parent,challenge,proposal_json,request_key):
        if proposal_json != '':
            return call(s.import_proposal,project,edition_ref,proposal_json,request_key,parents=[parent] if parent else [])
        if provider is None:return {'status':'MODEL_UNAVAILABLE','reason_code':'OWNER_PROPOSER_NOT_CONFIGURED','execution_permission':False}
        w=s.workspace(project)
        try:
            with w.locked():
                rows=w.history();s.known(rows,'semantic.edition','edition_ref',edition_ref);ed=w.get(edition_ref)
                initial=None
                if parent:s.known(rows,'semantic.bind','frame_ref',parent);initial=w.get(parent)
                existing=next((r for r in rows if r['action']=='semantic.propose' and r['request_key']=='sb-proposal:'+digest(request_key)),None)
                if existing:
                    record=w.get(existing['result']['proposal_ref'])
                    if record['edition_ref']!=edition_ref or record['parent_frames']!=([parent] if parent else []) or record['receipt'].get('request',{}).get('diagnostic_question')!=challenge:
                        raise AssuranceError('REQUEST_KEY_CONFLICT')
                source=w.get(ed['source_ref'])['snapshot']
            if existing:return {**s.finish(project,existing['result']['proposal_ref']),'model_status':record['receipt'].get('status','UNKNOWN'),'model_attempt_created':False}
            delivered=await provider.generate(project,source,ed,'revise' if parent else 'initial',initial,challenge,request_key)
            receipt=delivered.get('receipt',delivered)
            if 'raw_output' not in receipt:return {**receipt,'execution_permission':False}
            result=s._register(project,edition_ref,receipt['raw_output'],request_key,parents=[parent] if parent else [],mode='HOSTED_MODEL',receipt=receipt)
            return {**result,'model_status':receipt['status'],'model_attempt_created':delivered.get('model_attempt_created')}
        except AssuranceError as exc:return exc.as_dict()

    @server.tool(annotations=model_rw)
    async def semantic_draft(project:Project,edition_ref:Ref,request_key:Key,proposal_json:Json='')->dict:
        """Generate a real hosted initial reading, or import an explicitly untrusted client proposal. No truth/execution grant."""
        return await read(project,edition_ref,None,None,proposal_json,request_key)

    @server.tool(annotations=model_rw)
    async def semantic_revise(project:Project,frame_ref:Ref,challenge:Annotated[str,Field(min_length=1,max_length=4000)],
                              request_key:Key,proposal_json:Json='')->dict:
        """Retain the frozen parent and add a revised reading with rationale, competing interpretations and exact lineage."""
        w=s.workspace(project)
        try:
            with w.locked():s.known(w.history(),'semantic.bind','frame_ref',frame_ref);frame=w.get(frame_ref)
        except AssuranceError as exc:return exc.as_dict()
        return await read(project,frame['poem_ref'],frame_ref,challenge,proposal_json,request_key)

    @server.tool(annotations=rw)
    def semantic_compare(project:Project,left_ref:Ref,right_ref:Ref,projection_json:Json,request_key:Key)->dict:
        """Finite declared-field/Q comparison with a source-bound counter-witness; semantic world questions remain conjectures."""
        try:
            spec=parse(projection_json)
            if not isinstance(spec,dict) or not {'fields','declared_Q'}<=set(spec):raise AssuranceError('PROJECTION_CONTRACT_REQUIRED')
            if set(spec)-{'fields','declared_Q','complete','expectation','loss_origin'}:raise AssuranceError('UNKNOWN_PROJECTION_FIELD')
            return call(s.compare,project,left_ref,right_ref,spec['fields'],spec['declared_Q'],request_key,
                        complete=spec.get('complete',True),expectation=spec.get('expectation','REPORT'),loss_origin=spec.get('loss_origin','DECLARED_ANNOTATION'))
        except AssuranceError as exc:return exc.as_dict()

    @server.tool(annotations=ro)
    def semantic_report(project:Project)->dict:
        """All reading versions, exact anchors, alternatives, revision edges, failed raw proposals and actual model receipts."""
        return call(dossier,s.workspace(project))

    @server.tool(annotations=rw)
    def semantic_withdraw(project:Project,frame_ref:Ref,reason:Annotated[str,Field(min_length=1,max_length=2000)],request_key:Key)->dict:
        """Append withdrawal status and reason while retaining the original reading and every negative result."""
        return call(s.withdraw,project,frame_ref,reason,request_key)

    @server.tool(annotations=ro)
    def semantic_export(project:Project,audience:Literal['private','reviewers','public']='private',include_source_bytes:bool=True)->dict:
        """Data-only research ZIP; publication rights apply to source bytes, prompts, quote envelopes and anchors alike."""
        try:
            workspace=s.workspace(project)
            raw,manifest=export(workspace,audience,include_source_bytes)
            sha=__import__('hashlib').sha256(raw).hexdigest()
            cache=private_dir(workspace.path/'.semantic-exports');target=cache/(sha+'.zip')
            if target.exists():
                if target.is_symlink() or __import__('hashlib').sha256(target.read_bytes()).hexdigest()!=sha:
                    raise AssuranceError('EXPORT_CACHE_INTEGRITY_FAILURE')
            else:atomic_write(target,raw)
            return {'status':'EXPORTED','bundle_base64':base64.b64encode(raw).decode(),'sha256':sha,'bundle_ref':sha,
                    'manifest':manifest,'execution_permission':False}
        except AssuranceError as exc:return exc.as_dict()
    @server.tool(annotations=ro)
    def semantic_replay(project:Project,bundle_ref:Ref,engine:Literal['direct','compiled']='direct')->dict:
        """Replay an immutable export by SHA within its project; keeps large ZIP bytes outside bounded HTTP requests."""
        try:
            target=s.workspace(project).path/'.semantic-exports'/(bundle_ref+'.zip')
            if target.is_symlink() or not target.is_file():raise AssuranceError('EXPORT_NOT_IN_PROJECT')
            if target.stat().st_size>MAX_BUNDLE:raise AssuranceError('BUNDLE_SIZE_LIMIT')
            raw=target.read_bytes()
            if __import__('hashlib').sha256(raw).hexdigest()!=bundle_ref:raise AssuranceError('EXPORT_CACHE_INTEGRITY_FAILURE')
            return replay(raw,engine)
        except AssuranceError as exc:return exc.as_dict()
    return s
