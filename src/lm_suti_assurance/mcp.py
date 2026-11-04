"""Additive FastMCP adapter; HTTP auth is inherited from the owner-only host.

No caller-controlled host paths, model command, module name or execution grant.
"""
import base64
import binascii
from pathlib import Path
from typing import Annotated, Literal
from mcp.types import ToolAnnotations
from pydantic import Field
from . import RELEASE, core
from .errors import AssuranceError
from .service import Service
from .validation import parse
from .bundle import export_bundle, replay, MAX_BUNDLE
from .report import report

Project = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
Key = Annotated[str, Field(pattern=r'^[A-Za-z0-9_.:-]{1,128}$')]
Ref = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Json = Annotated[str, Field(max_length=2*1024*1024)]


def register_tools(server, root):
    service = Service(Path(root))
    ro = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    rw = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    def call(fn, *args):
        try:
            return fn(*args)
        except AssuranceError as exc:
            return exc.as_dict()

    @server.tool(annotations=ro)
    def assurance_contract() -> dict:
        """Get exact v0.1 schemas, a valid manual proposal and finite assurance boundaries."""
        import json
        from .smoke import POLICY, TAG
        return {'release': RELEASE, **core.identity(),
                'schemas': {p.stem.removesuffix('.schema'): json.loads(p.read_text()) for p in sorted((core.ROOT/'schemas').glob('*.json'))},
                'source_snapshot_schema': json.loads((core.FROZEN/'checker001/SOURCE_SNAPSHOT_V1.schema.json').read_text()),
                'manual_delta_example': {'schema':TAG,'intent':'PROPOSE','kind':'BOUNDED_PROPERTY','property':'PRESERVES_POPCOUNT'},
                'publication_policy_example': POLICY, 'native_SUTI':'NOT_EXECUTED',
                'formal_adapter':'UNAVAILABLE_NOT_REGISTERED', 'execution_permission':False,
                'boundary': 'Owner-only finite/source assurance. Review confirms scope, never mathematical truth. No external execution.'}

    @server.tool(annotations=rw)
    def assurance_project_new(project: Project, request_key: Key) -> dict:
        """Create a separate private assurance workspace; no changes to legacy SQLite events."""
        return call(service.new, project, request_key)

    @server.tool(annotations=rw)
    def assurance_source_add(project: Project, snapshot_json: Json, publication_policy_json: Json, request_key: Key) -> dict:
        """Import exact SourceSnapshot JSON bytes and explicit publication policy; see assurance_contract."""
        try:
            return call(service.source, project, parse(snapshot_json), parse(publication_policy_json), request_key)
        except AssuranceError as exc:
            return exc.as_dict()

    @server.tool(annotations=rw)
    def assurance_task_import(project: Project, artifact_json: Json, request_key: Key) -> dict:
        """Import a typed task as DRAFT. Explicit exact scope/assumptions review is required before check."""
        try:
            return call(service.task, project, parse(artifact_json), request_key)
        except AssuranceError as exc:
            return exc.as_dict()

    @server.tool(annotations=rw)
    def assurance_task_review(project: Project, task_ref: Ref, actor: Annotated[str, Field(min_length=1,max_length=160)],
                              reason: Annotated[str, Field(min_length=1,max_length=2000)], request_key: Key) -> dict:
        """Explicitly confirm the exact imported task scope and assumptions. Does not verify the claim."""
        return call(service.review, project, task_ref, actor, reason, request_key)

    @server.tool(annotations=rw)
    def assurance_candidate_import(project: Project, artifact_json: Json, request_key: Key) -> dict:
        """Retain an untrusted manual/model proposal, including malformed or false raw claims. No checking or grant."""
        try:
            return call(service.candidate, project, parse(artifact_json), request_key)
        except AssuranceError as exc:
            return exc.as_dict()

    @server.tool(annotations=rw)
    def assurance_check(project: Project, candidate_ref: Ref, request_key: Key,
                        engine: Literal['direct','compiled']='direct') -> dict:
        """Append a deterministic scoped decision and actual witnesses using the unchanged pinned core."""
        return call(service.check, project, candidate_ref, engine, request_key)

    @server.tool(annotations=ro)
    def assurance_report(project: Project) -> dict:
        """Read all checked claims, exact assumptions/scope, source SHA/spans, witnesses and negative results."""
        return call(report, service.workspace(project))

    @server.tool(annotations=ro)
    def assurance_export(project: Project, audience: Literal['private','reviewers','public']) -> dict:
        """Return a data-only immutable bundle as base64. Source bytes require both rights and audience permission."""
        try:
            raw, manifest = export_bundle(service.workspace(project), audience)
            return {'status':'EXPORTED','bundle_base64':base64.b64encode(raw).decode(),
                    'sha256':core.byte_digest(raw),'manifest':manifest,'execution_permission':False}
        except AssuranceError as exc:
            return exc.as_dict()

    @server.tool(annotations=ro)
    def assurance_replay(bundle_base64: Annotated[str, Field(max_length=MAX_BUNDLE*4//3+8)],
                         engine: Literal['direct','compiled']='direct') -> dict:
        """Offline replay of a data-only bundle; no network, OAuth refresh, model or subprocess inside replay."""
        try:
            raw = base64.b64decode(bundle_base64, validate=True)
        except (ValueError, binascii.Error):
            return AssuranceError('INVALID_BASE64').as_dict()
        return call(replay, raw, engine)

    @server.tool(annotations=ro)
    def assurance_doctor() -> dict:
        """Read the actual installed core identities and scope of this developer preview."""
        return {'status':'PASS','release':RELEASE,**core.identity(),'native_SUTI':'NOT_EXECUTED',
                'formal_adapter':'UNAVAILABLE_NOT_REGISTERED','execution_permission':False}

    return service
