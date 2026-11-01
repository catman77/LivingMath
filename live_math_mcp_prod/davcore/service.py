"""Project-bound adapter registration and optional immutable evidence retention."""
import re
from pathlib import Path
from typing import Any, Protocol

from .adapters import Adapter, AdapterSpec
from .ast import Formula, digest
from .boundary import Boundary
from .models import Budget
from .storage import Store
from .versioning import backend_binding


class AutomationHook(Protocol):
    def on_registration(self, project: str, row: dict) -> None: ...


class Service:
    def __init__(self, path: Path, forbidden: tuple[Path, ...] = ()):
        path = Path(path).expanduser().resolve()
        for other in forbidden:
            other = Path(other).expanduser().resolve()
            if path == other or path.exists() and other.exists() and path.samefile(other):
                raise ValueError('DAV_DATABASE_MUST_BE_ISOLATED')
        self.store = Store(path)
        self.boundary = Boundary()
        self.automation: AutomationHook | None = None

    @staticmethod
    def project(project):
        if not isinstance(project, str) or not re.fullmatch(r'[\w][\w.-]{0,79}', project):
            raise ValueError('INVALID_PROJECT')

    def registration(self, project, ident):
        self.project(project)
        row = self.store.get(project, ident)
        if row['kind'] != 'adapter':
            raise ValueError('EXPECTED_ADAPTER_REGISTRATION')
        p = row['payload']
        a = Adapter(AdapterSpec.model_validate(p['metadata']['spec']))
        if a.metadata != p['metadata']:
            raise ValueError('STALE_ADAPTER_REQUIRES_REREGISTRATION_AND_REVALIDATION')
        return p

    async def register(self, project, spec: AdapterSpec, key: str, *, _automation_origin: bool = False):
        self.project(project)
        a = Adapter(spec)
        req: dict[str, Any] = {'action': 'register', 'metadata': a.metadata}
        if _automation_origin:
            req['automation_origin'] = True
        old = self.store.repeated(project, key, req)
        if old:
            if self.automation is not None and not _automation_origin:
                self.automation.on_registration(project, old)
            return old
        out = await self.boundary.run({'action': 'audit', 'spec': spec.model_dump(),
                                      'metadata': a.metadata, 'budget': Budget().model_dump()})
        if out['status'] not in {'proved', 'invalid_adapter'} or out['status'] == 'invalid_adapter' and not out.get('full_semantics_valid'):
            return out
        row = self.store.append(project, 'adapter', key, req,
                                 {'metadata': a.metadata, 'binding': digest(a.metadata), 'audit': out,
                                  'permission': False, 'provenance_assurance': 'BUILTIN_CODE_NOT_EXTERNAL_WORLD_VALIDATION',
                                  **({'created_by': 'AUTOMATION'} if _automation_origin else {})})
        if self.automation is not None and not _automation_origin:
            self.automation.on_registration(project, row)
        return row

    async def compute(self, project, registration_id, action, budget: Budget | None = None,
                      formula: Formula | None = None, states=None, backend='finite', offset=0,
                      persist=False, request_key=None, expected_binding=None, _automation_origin: bool = False):
        p = self.registration(project, registration_id)
        if expected_binding != p['binding']:
            raise ValueError('EXPECTED_ADAPTER_BINDING_REQUIRED_OR_STALE')
        if backend == 'smt' and states is not None:
            raise ValueError('SMT_SAMPLE_SCOPE_NOT_SUPPORTED_USE_FINITE')
        req = {'action': action, 'spec': p['metadata']['spec'], 'metadata': p['metadata'],
               'budget': (budget or Budget()).model_dump(), 'backend': backend}
        if formula is not None:
            req['formula'] = formula.model_dump()
        if states is not None:
            req['states'] = states
        if action == 'generate':
            req['offset'] = offset
        identity = {'registration_id': registration_id, 'backend_binding': backend_binding(), **req}
        if _automation_origin:
            identity['automation_origin'] = True
        if persist:
            if not request_key:
                raise ValueError('EXPLICIT_REQUEST_KEY_REQUIRED')
            old = self.store.repeated(project, request_key, identity)
            if old:
                return old
        out = await self.boundary.run(req)
        if formula is not None:
            out['law_fingerprint'] = digest(formula.canonical_ast())
        if action == 'reduce':
            out['counterexample_links'] = self.store.counterexample_links(project, registration_id)
        out.update(proof_status='unverified', execution_permission={'allowed': False},
                   backend_binding=identity['backend_binding'],
                   evidence_provenance={'project': project, 'registration_id': registration_id,
                                        'binding': p['binding'], **({'created_by': 'AUTOMATION'} if _automation_origin else {})},
                   request_fingerprint=digest(identity))
        if persist:
            return self.store.append(project, 'law_library' if action == 'reduce' else 'evidence', request_key, identity, out)
        return out

    def export(self, project, evidence_id):
        self.project(project)
        row = self.store.get(project, evidence_id)
        payload = row['payload']
        if row['kind'].startswith('artifact_') or row['kind']=='automation_artifact_input':
            validator=getattr(self.automation,'artifact_certificate_current',None)
            try:valid=bool(validator is not None and validator(project,row))
            except (ValueError,KeyError,TypeError):valid=False
            if payload.get('model', {}).get('target_model') == 'NOT_APPLICABLE':
                return {'record': row, 'certificate_current': False, 'meta_contract_current': valid,
                    'effective_status': 'SCOPED_META_TRANSPORT_CHECKED' if valid else 'unknown',
                    'reason': 'SOURCE_META_TRANSPORT_NOT_WORLD_VERIFICATION',
                    'certificate_scope': 'SOURCE_ANNOTATION_ONLY; TARGET_NOT_APPLICABLE',
                    'source_claim_verified': False, 'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
            return {'record':row,'certificate_current':valid,
                'effective_status':'CONDITIONAL_MODEL_CHECKED' if valid else 'unknown',
                'reason':'CURRENT_SCOPED_TARGET_CHECK_NOT_SOURCE_VERIFICATION' if valid else 'ARTIFACT_TASK_EXPORT_OR_REVALIDATION_REQUIRED',
                'certificate_scope':'CONDITIONAL_MODEL_AND_EXECUTED_TARGET_CHECK_ONLY',
                'source_claim_verified':False,'proof_status':'unverified','execution_permission':{'allowed':False}}
        provenance = payload.get('evidence_provenance')
        valid = True
        if provenance:
            try:
                current = self.registration(project, provenance['registration_id'])
                valid = provenance['binding'] == current['binding'] and payload.get('backend_binding') == backend_binding()
            except ValueError:
                valid = False
        return {'record': row, 'certificate_current': valid,
                'effective_status': payload.get('status') if valid else 'unknown',
                'reason': 'PINNED_ORIGINAL_CERTIFICATE' if valid else 'ADAPTER_CHANGED_REVALIDATION_REQUIRED',
                'proof_status': 'unverified', 'execution_permission': {'allowed': False}}
