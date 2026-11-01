"""SELECT-only Phase-A gates. No fabricated binding, journal initialization or completion."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from pydantic import ValidationError
from normalizer import canonical, digest, read_history, strict_json
from native_preview008_contract import NativeRequest
from native_preview008_engine import check_sources, frontier, source_budget
from research_engine010_contract import MeasurementBinding, ReceiptValidationRequest, refusal


class PhaseAEngine:
    def __init__(self, database: Path):
        self.database = database.expanduser().resolve(strict=True)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION}
        conn.set_authorizer(lambda action, a, b, c, d: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        try:
            yield conn
        finally:
            conn.close()

    def validate_receipt(self, request: ReceiptValidationRequest) -> dict:
        started, cpu = time.perf_counter_ns(), time.process_time_ns()
        with self.connection() as conn:
            event = conn.execute('SELECT * FROM events WHERE id=?', (request.measurement_event_id,)).fetchone()
            move = conn.execute('SELECT * FROM research_moves WHERE id=?', (request.move_id,)).fetchone()
            if event is None or move is None or event['project'] != request.project or move['project'] != request.project:
                return refusal('REJECTED', 'MISSING_OR_FOREIGN_EVENT_OR_MOVE')
            data, quality = strict_json(event['content'])
            if quality != 'EXACT_JSON':
                return refusal('INSUFFICIENT_MEASUREMENT_BINDING', 'EVENT_HAS_NO_EXACT_MEASUREMENT_ENVELOPE')
            binding_data = data.get('measurement_binding')
            if not isinstance(binding_data, dict):
                return refusal('INSUFFICIENT_MEASUREMENT_BINDING', 'EVENT_HAS_NO_BOUND_MEASUREMENT_CONTRACT',
                    event_id=event['id'], event_sha256=digest(dict(event)),
                    missing_source_fields=['measurement_binding.' + k for k, f in MeasurementBinding.model_fields.items() if f.is_required()],
                    legacy_fields_present=sorted(data),
                    no_reconstruction_from_caller_or_harness_trace=True)
            try:
                binding = MeasurementBinding.model_validate(binding_data)
            except ValidationError as error:
                return refusal('INSUFFICIENT_MEASUREMENT_BINDING', 'MALFORMED_OR_INCOMPLETE_EVENT_BINDING',
                    errors=[{'location': list(e['loc']), 'type': e['type']} for e in error.errors()])
            if binding.project != event['project'] or binding.move_id != move['id']:
                return refusal('REJECTED', 'MEASUREMENT_BOUND_TO_ANOTHER_PROJECT_OR_MOVE')
            receipt = request.receipt
            if receipt is not None:
                if receipt.measurement_event_id != event['id'] or receipt.binding.model_dump() != binding.model_dump():
                    return refusal('REJECTED', 'CALLER_RECEIPT_DIFFERS_FROM_SOURCE_EVENT')
            payload = json.loads(move['payload_json'])
            if (payload['active_frontier_id'] != binding.obligation_id or payload['scope'] != binding.scope
                    or payload['fingerprint']['digest'] != binding.proposal_fingerprint):
                return refusal('REJECTED', 'MOVE_SCOPE_OR_FINGERPRINT_MISMATCH')
            current = conn.execute('SELECT current_version FROM research_obligations WHERE id=? AND project=?',
                                   (binding.obligation_id, binding.project)).fetchone()
            if current is None or current['current_version'] != binding.obligation_version:
                return refusal('REJECTED', 'STALE_OBLIGATION_VERSION')
            active = conn.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence DESC LIMIT 1', (move['id'],)).fetchone()
            if active is None or active['status'] != 'EXPERIMENT_ALLOWED' or active['audit_id'] != binding.audit_id:
                return refusal('REJECTED', 'NO_CURRENT_MATCHING_ACTIVATION')
            decision = json.loads(active['decision_json'])
            if (not decision.get('allowed') or decision.get('scope') != binding.scope
                    or decision.get('frontier_versions') != {str(binding.obligation_id): binding.obligation_version}):
                return refusal('REJECTED', 'ACTIVATION_SCOPE_OR_VERSION_MISMATCH')
            audit = conn.execute('SELECT * FROM research_move_audits WHERE id=? AND move_id=?', (binding.audit_id, move['id'])).fetchone()
            if audit is None:
                return refusal('REJECTED', 'AUDIT_NOT_BOUND_TO_MOVE')
            if payload.get('proposed_operation', {}).get('cycle_binding') is None:
                return refusal('INSUFFICIENT_MEASUREMENT_BINDING', 'PROPOSAL_DID_NOT_PRECOMMIT_TYPED_TEST_SOURCE_BINDING')
            activation = conn.execute('SELECT * FROM operations WHERE id=?', (binding.activation_operation_id,)).fetchone()
            if activation is None or activation['action'] != 'research_move_status_changed':
                return refusal('REJECTED', 'UNKNOWN_ACTIVATION_OPERATION')
            act = json.loads(activation['details_json'])
            if any(act.get(k) != v for k, v in {'move_id': move['id'], 'sequence': active['sequence'],
                    'status': 'EXPERIMENT_ALLOWED', 'audit_id': binding.audit_id}.items()):
                return refusal('REJECTED', 'ACTIVATION_OPERATION_MISMATCH')
            creation = [r['id'] for r in conn.execute("SELECT id,details_json FROM operations WHERE action='event_created'")
                        if json.loads(r['details_json']).get('id') == event['id']]
            if len(creation) != 1 or creation[0] <= activation['id']:
                return refusal('REJECTED', 'EVENT_NOT_CREATED_AFTER_BOUND_ACTIVATION')
            source_ids = binding.source_event_ids
            sources = {r['id']: dict(r) for r in conn.execute('SELECT * FROM events WHERE id IN (' + ','.join('?' for _ in source_ids) + ')', source_ids)}
            if any(i not in sources or sources[i]['project'] != request.project for i in source_ids):
                return refusal('REJECTED', 'MISSING_OR_FOREIGN_BOUND_SOURCE')
            if any(digest(sources[r.event_id]) != r.sha256 for r in binding.source_bindings):
                return refusal('REJECTED', 'SOURCE_HASH_DRIFT')
            # Phase A intentionally cannot authorize commit or assert authenticity.
            # No source-compatible010 envelope/proposal/executor has been supplied.
            return refusal('REQUIRES_REVIEW', 'OPERATOR_COMMIT_AND_AUTHORITATIVE_JOURNAL_NOT_IMPLEMENTED_UNTIL_SOURCE_GATE_PASSES',
                structural_fields_checked=True, actual_external_measurement_authenticity=False,
                observed_is_not_verified=True, artifact_inspection='NOT_PERFORMED',
                source_lookup_wall_ns=time.perf_counter_ns() - started, CPU_self_ns=time.process_time_ns() - cpu)

    def novelty_snapshot(self, request: NativeRequest) -> dict:
        if len(canonical(request.model_dump()).encode()) > request.budget.input_bytes:
            return refusal('INSUFFICIENT_CONTEXT', 'INPUT_BYTE_BOUND')
        if request.question.context_level == 'C4':
            return refusal('INSUFFICIENT_CONTEXT', 'C4_IS_NOT_AUDIT_SUFFICIENT')
        started = time.perf_counter_ns()
        try:
            history = read_history(self.database, request.project, source_budget(request.budget))
            hashes = check_sources(history, request.source_event_ids, request.source_bindings, exact=True)
            active = frontier(history, request.active_frontier_id, request.active_frontier_version)
        except (ValueError, sqlite3.Error) as error:
            return refusal('INSUFFICIENT_CONTEXT', str(error))
        return refusal('NOVELTY_CONTEXT_INCOMPLETE', 'NO_SERVER_AUTHORITATIVE_TYPED_NOVELTY_JOURNAL',
            project=request.project, scope=active['scope'], version=request.active_frontier_version,
            source_hashes=hashes, known_fingerprints=None, snapshot_complete=False,
            caller_known_fingerprints_authoritative=False, caller_known_ignored=True,
            source_lookup_wall_ns=time.perf_counter_ns() - started,
            limitation='An absent typed journal is not an authoritative empty history. Legacy008 caller-local novelty semantics are unchanged.')

    def cycle_preview(self, request: NativeRequest) -> dict:
        snapshot = self.novelty_snapshot(request)
        return {**snapshot, 'next_step': None, 'measurement_executed': False, 'move_created': False,
                'native_calls': {'extend': 0, 'observe': 0, 'admissible': 0},
                'I_T_executed': False, 'reason_for_no_proposal': 'Typed source/authority preconditions must pass before a research proposal.'}
