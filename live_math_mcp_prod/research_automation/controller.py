"""One persistent autonomous coordinator over existing registered finite capabilities."""
import asyncio
import copy
import logging
import sqlite3
import time

from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Formula, canonical, digest
from davcore.models import Budget
from .checker import analyze_inputs
from .contract import Problem, ResearchInput
from .journal import Journal
from .planner import initial_observer_state, next_candidate, refine_from_counterexample
from .versioning import policy_binding

LOG = logging.getLogger('livingmath.autoresearch')
ACTIVE = {'QUEUED', 'DIAGNOSING', 'PROPOSING', 'AUDITING', 'EXPERIMENTING', 'CHECKING'}


class Controller:
    def __init__(self, service, *, budget: Budget | None = None, canonical=None, inbox=None, semantic_provider=None):
        self.service = service
        self.journal = Journal(service)
        self.budget = budget or Budget()
        self.binding = digest({'policy': policy_binding(), 'budget': self.budget.model_dump()})
        self.semantic_provider = semantic_provider
        if semantic_provider is not None:
            self.binding = digest({'coordinator': self.binding, 'semantic_provider': semantic_provider.fingerprint})
        self.service.automation = self
        self.canonical = canonical
        self.inbox = inbox
        self._stopping = False
        self.last_error: dict | None = None
        self._source_cursor = 0

    def _validate_references(self, project: str, references: list[str]) -> None:
        for ref in references:
            if ref.startswith('dav:'):
                try:
                    ident = int(ref.removeprefix('dav:'))
                except ValueError:
                    raise ValueError('INVALID_DAV_SOURCE_REFERENCE') from None
                self.service.store.get(project, ident)
            elif ref.startswith('event:'):
                if self.canonical is None:
                    raise ValueError('CANONICAL_EVENT_REFERENCE_NEEDS_BOUND_SOURCE_STORE')
                try:
                    ident = int(ref.removeprefix('event:'))
                except ValueError:
                    raise ValueError('INVALID_EVENT_SOURCE_REFERENCE') from None
                with sqlite3.connect(self.canonical.resolve(strict=True).as_uri() + '?mode=ro', uri=True) as c:
                    row = c.execute('SELECT id FROM events WHERE id=? AND project=?', (ident, project)).fetchone()
                if row is None:
                    raise ValueError('MISSING_OR_FOREIGN_SOURCE_EVENT')

    def submit(self, project: str, problem: Problem, sources: list[int]) -> dict:
        self.service.project(project)
        if problem.kind=='artifact_reconstruction':
            from semantic_repair.context009 import resolve
            assert problem.artifact_snapshot_id is not None
            resolve(self.service.store,project,problem.artifact_snapshot_id)
        self._validate_references(project, problem.source_refs)
        for ident in sources:
            self.service.store.get(project, ident)
        if problem.registration_id is not None:
            p = self.service.registration(project, problem.registration_id)
            if p['binding'] != problem.adapter_binding:
                raise ValueError('STALE_OR_FOREIGN_AUTOMATION_ADAPTER')
        return self.journal.create(project, problem, sources, self.binding)

    def on_registration(self, project: str, row: dict) -> None:
        meta = row['payload']['metadata']
        if meta['spec']['mask'] is not None:
            self.submit(project, Problem(kind='observer_refinement', scope='adapter/' + meta['snapshot_id'],
                registration_id=row['id'], adapter_binding=row['payload']['binding'],
                source_refs=['dav:' + str(row['id'])]), [row['id']])

    def ingest(self, project: str, packet: ResearchInput, request_key: str, *, provenance: dict | None = None) -> dict:
        from .artifact_contract import ArtifactInput
        if isinstance(packet,ArtifactInput):
            from .artifact import ingest
            return ingest(self,project,packet,request_key,provenance)
        self.service.project(project)
        self._validate_references(project, packet.source_refs + [r for f in packet.facts for r in f.source_refs])
        for problem in packet.problems:
            self._validate_references(project, problem.source_refs)
            if problem.registration_id is not None:
                p = self.service.registration(project, problem.registration_id)
                if p['binding'] != problem.adapter_binding:
                    raise ValueError('STALE_OR_FOREIGN_AUTOMATION_ADAPTER')
        data = packet.model_dump()
        if len(canonical(data).encode()) > 256000:
            raise ValueError('AUTOMATION_INPUT_BYTE_BOUND')
        identity = {'input': data, 'provenance': provenance or {'kind': 'DECLARED_MCP_INPUT'}}
        row = self.journal.append(project, 'automation_input', 'auto-input:' + digest(request_key), identity, identity)
        cases = [self.submit(project, problem, [row['id']])['id'] for problem in packet.problems]
        return {'input_id': row['id'], 'case_ids': cases, 'status': 'ACCEPTED_FOR_AUTOMATIC_PROCESSING',
                'input_assurance': 'DECLARED_NOT_INDEPENDENTLY_VERIFIED', 'proof_status': 'unverified',
                'execution_permission': {'allowed': False}}

    def bootstrap(self) -> None:
        """Recover after any interruption between intake and enqueue; proposals deduplicate structurally."""
        for row in self.journal.rows(('adapter', 'automation_input', 'evidence','automation_artifact_input'), after_id=self._source_cursor):
            self._source_cursor = row['id']
            p = row['payload']
            if row['kind'] == 'adapter' and p.get('created_by') != 'AUTOMATION':
                try:
                    self.service.registration(row['project'], row['id'])
                    self.on_registration(row['project'], row)
                except ValueError:
                    continue
            elif row['kind']=='automation_artifact_input':
                problem=Problem.model_validate(p['problem'])
                self.submit(row['project'],problem,[row['id'],p['source_id']])
            elif row['kind'] == 'automation_input':
                packet = ResearchInput.model_validate(p['input'])
                for problem in packet.problems:
                    self.submit(row['project'], problem, [row['id']])
            elif p.get('evidence_provenance', {}).get('created_by') != 'AUTOMATION' and p.get('status') in {'unknown', 'timeout', 'refuted', 'consistent_with_observations'} and p.get('formula'):
                origin = p['evidence_provenance']
                try:
                    self.submit(row['project'], Problem(kind='law_check', scope='law/' + p['law_fingerprint'],
                        registration_id=origin['registration_id'], adapter_binding=origin['binding'],
                        formula=Formula.model_validate(p['formula']), source_refs=['dav:' + str(row['id'])]), [row['id']])
                except ValueError:
                    continue

    def _inputs(self, case: dict) -> list[dict]:
        problem = case['payload']['problem']
        if problem['kind'] not in {'identify_model', 'input_gap'}:
            return []
        relevant = set(problem['required_features']) | {p['feature'] for h in problem['hypotheses'] for p in h['predictions']}
        relevant.update('model_target/' + h['model_id'] for h in problem['hypotheses'] if h['target'] is None)
        return [r for r in self.journal.inputs(case['project'], problem['scope'])
                if any(f['feature'] in relevant and f['value'] is not None for f in r['payload']['input']['facts'])]

    def _basis(self, case: dict) -> str:
        if case['payload']['problem']['kind']=='artifact_reconstruction':
            from .artifact import current_source
            from semantic_repair.context009 import resolve
            ctx=resolve(self.service.store,case['project'],case['payload']['problem']['artifact_snapshot_id'])
            return digest({'source':ctx.public(),'current':current_source(self,ctx)})
        return digest([r['id'] for r in self._inputs(case)])

    def _control(self, case: dict) -> dict | None:
        rows = self.journal.controls(case['project'], case['id'])
        return rows[-1] if rows else None

    def _runnable(self, case: dict, last: dict) -> bool:
        control = self._control(case)
        if control and control['payload']['action'] in {'pause', 'cancel'}:
            return False
        p = last['payload']
        if p['state'].get('coordinator_binding') != self.binding or p['state'].get('basis') != self._basis(case):
            return True
        return p['status'] in ACTIVE or p['status'] == 'RETRY_WAIT' and time.time() >= p['state']['retry_at']

    async def tick(self) -> bool:
        with self.journal.leader() as leader:
            if not leader:
                return False
            self.bootstrap()
            candidates = []
            for case in self.journal.rows(('automation_case',)):
                steps = self.journal.steps(case['project'], case['id'])
                if steps and self._runnable(case, steps[-1]):
                    candidates.append((steps[-1]['id'], case, steps[-1]))
            if not candidates:
                return False
            _, case, last = min(candidates, key=lambda row: row[0])
            await self._advance(case, last)
            return True

    def _retry(self, case: dict, last: dict, state: dict, reason: str) -> None:
        count = state.get('resource_retries', 0) + 1
        status = 'RETRY_WAIT' if count <= 3 else 'RESOURCE_EXHAUSTED'
        self.journal.step(case, last, status, {**state, 'resource_retries': count,
            'resume_status': last['payload']['status'], 'retry_at': time.time() + min(60, 2**count)},
            {'outcome': 'RESOURCE_OR_BACKEND_UNDECIDED', 'reason': reason,
             'automatic_retry': status == 'RETRY_WAIT', 'retry_count': count})

    async def _compute(self, case: dict, last: dict, problem: Problem, action: str, **kwargs) -> dict:
        row = await self.service.compute(case['project'], problem.registration_id, action,
            budget=self.budget, persist=True, request_key=f"auto-work:{case['id']}:{last['payload']['sequence']}:{action}",
            expected_binding=problem.adapter_binding, _automation_origin=True, **kwargs)
        return row

    async def _audit_mask(self, case: dict, last: dict, problem: Problem, state: dict, check: bool = False) -> dict:
        p = self.service.registration(case['project'], problem.registration_id)
        spec = {**p['metadata']['spec'], 'mask': state['current_mask']}
        a = Adapter(AdapterSpec.model_validate(spec))
        req = {'action': 'check_refinement' if check else 'audit', 'spec': spec, 'metadata': a.metadata,
               'budget': self.budget.model_dump()}
        if check:
            req['base_spec'] = p['metadata']['spec']
        key = f"auto-work:{case['id']}:{last['payload']['sequence']}:{req['action']}"
        identity = {'request': req, 'coordinator_binding': self.binding}
        old = self.service.store.repeated(case['project'], key, identity)
        if old:
            return old
        result = await self.service.boundary.run(req)
        return self.journal.append(case['project'], 'automation_probe', key, identity,
            {'request': req, 'result': result, 'coordinator_binding': self.binding, 'case_id': case['id']})

    async def _advance(self, case: dict, last: dict) -> None:
        p = last['payload']
        state = copy.deepcopy(p['state'])
        problem = Problem.model_validate(case['payload']['problem'])
        basis = self._basis(case)
        if state.get('coordinator_binding') != self.binding or state.get('basis') != basis:
            generation = state.get('generation', 0) + (0 if p['status'] == 'QUEUED' and 'basis' not in state else 1)
            self.journal.step(case, last, 'DIAGNOSING', {'generation': generation, 'coordinator_binding': self.binding,
                'basis': basis, 'resource_retries': 0}, {'outcome': 'SOURCE_OR_POLICY_REVALIDATION', 'previous_result_retained': True})
            return
        status = p['status']
        control = self._control(case)
        control_id = control['id'] if control else None
        if status == 'QUEUED':
            self.journal.step(case, last, 'DIAGNOSING', state)
            return
        if status == 'RETRY_WAIT':
            self.journal.step(case, last, state['resume_status'], state)
            return
        try:
            if problem.kind=='artifact_reconstruction':
                from .artifact import advance
                assert problem.artifact_budget is not None
                try:
                    await advance(self,case,last,state,problem,control_id)
                except (TimeoutError,ValueError) as exc:
                    reason=str(exc)
                    if isinstance(exc,TimeoutError) or any(k in reason for k in ('WORKER_','BUDGET_EXHAUSTED')):
                        if state.get('resource_retries',0)<problem.artifact_budget.retries:
                            self._retry(case,last,state,reason or 'WORKER_TIMEOUT')
                        else:
                            self.journal.step(case,last,'RESOURCE_EXHAUSTED',state,{'outcome':'BOUNDED_COMPUTATION_STOPPED','reason':reason or 'WORKER_TIMEOUT','historical_results_retained':True})
                    else:raise
                return
            if problem.kind in {'observer_refinement', 'law_check'}:
                self.service.registration(case['project'], problem.registration_id)
            if status == 'DIAGNOSING':
                if problem.kind == 'observer_refinement':
                    metadata = self.service.registration(case['project'], problem.registration_id)['metadata']
                    state.update(initial_observer_state(metadata))
                self.journal.step(case, last, 'PROPOSING', state)
            elif status == 'PROPOSING':
                if problem.kind == 'observer_refinement':
                    candidate = next_candidate(state)
                    if candidate is None:
                        self.journal.step(case, last, 'REQUIRES_REVIEW', state, {'outcome': 'FINITE_REPRESENTATION_FAMILY_EXHAUSTED'})
                        return
                    state['current_mask'] = candidate
                self.journal.step(case, last, 'AUDITING', state, {'outcome': 'SCOPED_COMPUTATIONAL_PROPOSAL', 'external_execution_grant': False})
            elif status == 'AUDITING':
                # No external transformation is authorized. The proposal only selects a finite checker action.
                if problem.kind == 'observer_refinement' and state['current_mask'] & state['original_mask'] != state['original_mask']:
                    self.journal.step(case, last, 'REQUIRES_REVIEW', state, {'outcome': 'LOSSY_REPRESENTATION_REJECTED'})
                    return
                self.journal.step(case, last, 'EXPERIMENTING', state)
            elif status == 'EXPERIMENTING':
                if problem.kind == 'observer_refinement':
                    probe = await self._audit_mask(case, last, problem, state)
                    result = probe['payload']['result']
                elif problem.kind == 'law_check':
                    probe = await self._compute(case, last, problem, 'check', formula=problem.formula)
                    result = probe['payload']
                else:
                    analysis = analyze_inputs(problem, self._inputs(case))
                    probe = self.journal.append(case['project'], 'automation_probe', f"auto-work:{case['id']}:{p['sequence']}:input-analysis",
                        {'case_id': case['id'], 'basis': basis, 'sequence': p['sequence']},
                        {'case_id': case['id'], 'input_ids': [r['id'] for r in self._inputs(case)],
                         'result': {'status': analysis.outcome, **analysis.result}})
                    result = probe['payload']['result']
                if not self._can_publish(case, last, basis, control_id):
                    return
                if result.get('status') in {'timeout', 'unknown'}:
                    self._retry(case, last, state, result.get('reason', 'UNDECIDED_BACKEND'))
                    return
                self.journal.step(case, last, 'CHECKING', {**state, 'probe_id': probe['id']})
            elif status == 'CHECKING':
                await self._accept(case, last, problem, state, control_id)
        except (ValueError, KeyError, TypeError) as exc:
            self.journal.step(case, last, 'REQUIRES_REVIEW', state,
                              {'outcome': 'AUTOMATIC_AUDIT_REJECTED', 'reason': str(exc), 'no_execution_grant': True})

    def _can_publish(self, case: dict, last: dict, basis: str, control_id: int | None) -> bool:
        control = self._control(case)
        steps = self.journal.steps(case['project'], case['id'])
        return (self._basis(case) == basis and (control['id'] if control else None) == control_id
                and steps[-1]['id'] == last['id'])

    async def _accept(self, case: dict, last: dict, problem: Problem, state: dict, control_id: int | None) -> None:
        probe = self.service.store.get(case['project'], state['probe_id'])
        result = probe['payload'].get('result', probe['payload'])
        if problem.kind == 'observer_refinement':
            if result.get('congruent') is False:
                a = Adapter(AdapterSpec.model_validate(self.service.registration(case['project'], problem.registration_id)['metadata']['spec']))
                state = refine_from_counterexample(state, result['congruence_witness'], a.width)
                self.journal.step(case, last, 'PROPOSING', state, {'outcome': 'COUNTEREXAMPLE_RETAINED_RCA_DRIVES_NEXT_PROPOSAL', 'probe_id': probe['id']})
                return
            if result.get('congruent') is not True:
                raise ValueError('NO_DEFINITIVE_CONGRUENCE_RESULT')
            independent = await self._audit_mask(case, last, problem, state, check=True)
            if not self._can_publish(case, last, state['basis'], control_id):
                return
            verdict = independent['payload']['result']
            if verdict['status'] == 'timeout':
                self._retry(case, last, state, verdict.get('reason', 'INDEPENDENT_CHECK_TIMEOUT'))
                return
            if verdict['status'] != 'accepted':
                self.journal.step(case, last, 'REQUIRES_REVIEW', state,
                    {'outcome': 'INDEPENDENT_CHECK_REJECTED', 'checker_evidence_id': independent['id'], 'verdict': verdict})
                return
            spec = self.service.registration(case['project'], problem.registration_id)['metadata']['spec']
            registration = await self.service.register(case['project'], AdapterSpec.model_validate({**spec, 'mask': state['current_mask']}),
                f"auto-work:{case['id']}:g{state['generation']}:accepted-observer", _automation_origin=True)
            if not self._can_publish(case, last, state['basis'], control_id):
                return
            self.journal.step(case, last, 'COMPLETED', state, {
                'outcome': 'FORMAL_REPRESENTATION_REPAIRED' if state['current_mask'] != state['original_mask'] else 'OBSERVER_ALREADY_SUFFICIENT',
                'observer_mask': state['current_mask'], 'base_registration_id': problem.registration_id,
                'new_registration_id': registration['id'], 'checker_evidence_id': independent['id'],
                'new_adapter_binding': registration['payload']['binding'], 'independent_check': verdict,
                'counterexamples_preserved': len(state['counterexamples']), 'domain_or_assumptions_changed': False,
                'external_unknowns_resolved': False})
        elif problem.kind == 'law_check':
            other = await self._compute(case, last, problem, 'check', formula=problem.formula, backend='smt')
            if not self._can_publish(case, last, state['basis'], control_id):
                return
            independent = other['payload']
            if independent['status'] in {'timeout', 'unknown'}:
                metadata = self.service.registration(case['project'], problem.registration_id)['metadata']
                if problem.formula is None:
                    raise ValueError('LAW_FORMULA_REQUIRED')
                req = {'action': 'check_law_independent', 'spec': metadata['spec'], 'metadata': metadata,
                    'formula': problem.formula.model_dump(), 'claimed': {'status': result['status'], 'counterexample': result.get('counterexample')},
                    'budget': self.budget.model_dump()}
                verdict = await self.service.boundary.run(req)
                if not self._can_publish(case, last, state['basis'], control_id):
                    return
                checked = self.journal.append(case['project'], 'automation_probe', f"auto-work:{case['id']}:{last['payload']['sequence']}:finite-checker",
                    {'request': req, 'policy': self.binding}, {'case_id': case['id'], 'request': req, 'result': verdict})
                if verdict['status'] == 'timeout':
                    self._retry(case, last, state, verdict.get('reason', 'INDEPENDENT_FINITE_CHECK_TIMEOUT'))
                    return
                if verdict['status'] != 'accepted':
                    self.journal.step(case, last, 'REQUIRES_REVIEW', state, {'outcome': 'INDEPENDENT_CHECK_REJECTED', 'evidence_id': checked['id']})
                    return
                independent = {'status': result['status'], 'fallback_evidence_id': checked['id']}
            if independent['status'] != result['status']:
                self.journal.step(case, last, 'REQUIRES_REVIEW', state, {'outcome': 'INDEPENDENT_BACKENDS_DISAGREE',
                    'finite_evidence_id': probe['id'], 'SMT_evidence_id': other['id']})
                return
            self.journal.step(case, last, 'COMPLETED', state, {'outcome': 'LAW_REFUTED' if result['status'] == 'refuted' else 'FINITE_LAW_CHECKED',
                'finite_evidence_id': probe['id'], 'SMT_evidence_id': other['id'], 'adapter_relative_status': result['status'],
                'independent_finite_fallback_evidence_id': independent.get('fallback_evidence_id'),
                'counterexample': result.get('counterexample'), 'formula_unchanged': True, 'scientific_truth_established': False})
        else:
            replay = analyze_inputs(problem, self._inputs(case))
            if replay.result != {k: v for k, v in result.items() if k != 'status'}:
                raise ValueError('INPUT_ANALYSIS_REPLAY_CHANGED')
            self.journal.step(case, last, replay.outcome, state, replay.result)
            if replay.outcome == 'WAITING_FOR_INPUT':
                self.journal.append(case['project'], 'automation_input_request',
                    f"auto-request:{case['id']}:g{state['generation']}", {'case_id': case['id'], 'basis': state['basis']},
                    {'case_id': case['id'], 'scope': problem.scope, 'requirements': replay.result,
                     'source_refs': problem.source_refs, 'automatic_resume_when_inputs_change': True})

    def status(self, project: str) -> dict:
        self.service.project(project)
        cases = []
        runnable = 0
        for case in self.journal.rows(('automation_case',), project):
            steps = self.journal.steps(project, case['id'])
            if not steps:
                continue
            p = steps[-1]['payload']
            control = self._control(case)
            status = {'pause': 'PAUSED', 'cancel': 'CANCELLED'}.get(control['payload']['action'], p['status']) if control else p['status']
            runnable += int(self._runnable(case, steps[-1]))
            cases.append({'case_id': case['id'], 'scope': case['payload']['problem']['scope'],
                'kind': case['payload']['problem']['kind'], 'status': status, 'generation': p['state'].get('generation', 1),
                'result': p['result'], 'state': p['state'], 'history': [
                    {'record_id': s['id'], 'sequence': s['payload']['sequence'], 'status': s['payload']['status'],
                     'generation': s['payload']['state'].get('generation', 1)} for s in steps[-100:]],
                'history_complete': len(steps) <= 100, 'proof_status': 'unverified', 'execution_permission': {'allowed': False}})
        return {'mode': 'AUTOMATIC', 'coordinator_binding': self.binding, 'cases': cases, 'runnable': runnable,
                'last_error': self.last_error, 'physical_execution': 'EXISTING_OPERATOR_AND_TYPED_RECEIPT_BOUNDARY',
                'proof_status': 'unverified', 'execution_permission': {'allowed': False}}

    def control(self, project: str, case_id: int, action: str, request_key: str) -> dict:
        self.service.project(project)
        self.journal.case(project, case_id)
        controls=self.journal.controls(project,case_id)
        if controls and controls[-1]['payload']['action']=='cancel' and action!='cancel':
            raise ValueError('CANCELLED_CASE_IS_TERMINAL')
        if action not in {'pause', 'resume', 'cancel'}:
            raise ValueError('INVALID_AUTOMATION_CONTROL')
        return self.journal.append(project, 'automation_control', 'auto-control:' + digest(request_key),
            {'case_id': case_id, 'action': action}, {'case_id': case_id, 'action': action})

    def artifact_certificate_current(self, project: str, row: dict) -> bool:
        from .artifact import certificate_current
        return certificate_current(self,project,row)

    async def run(self) -> None:
        from .intake import Intake
        intake = Intake(self)
        while not self._stopping:
            try:
                intake.poll()
                progressed = await self.tick()
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = {'type': type(exc).__name__, 'reason': str(exc)}
                LOG.error('AUTOMATION_CYCLE_ERROR %s', self.last_error)
                progressed = False
            await asyncio.sleep(0.01 if progressed else 0.5)
