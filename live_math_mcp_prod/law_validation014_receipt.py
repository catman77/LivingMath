"""014 receipt validator: exact011 checks, explicit singleton/coordinate/purpose extension.

The original011 implementation is unchanged. See receipt-protocol.diff in QA.
"""
import json
from pathlib import Path
from normalizer import digest
from research_store import ResearchStore
from typed_cycle011 import TypedCycle,journal_state,require_ledger_order
from typed_cycle011_store import scope
from typed_cycle011_contract import denied
from law_validation014_contract import Envelope014,Precommit014


class ReceiptValidator014(TypedCycle):
    def validate_in(self, c, project, move_id, event_id):
        event = c.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
        if not event or event['project'] != project: raise ValueError('MISSING_OR_FOREIGN_EVENT')
        data = json.loads(event['content'])
        if not isinstance(data, dict) or 'measurement_binding' not in data:
            return denied('INSUFFICIENT_MEASUREMENT_BINDING', 'LEGACY_EVENT_WITHOUT_BINDING')
        env = Envelope014.model_validate(data['measurement_binding']).model_dump()
        row = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?', (move_id, project)).fetchone()
        if row is None: raise ValueError('MISSING_OR_FOREIGN_PRECOMMIT')
        pc = Precommit014.model_validate(json.loads(row['payload_json'])).model_dump(); self._sources_current(c, pc)
        move = c.execute('SELECT * FROM research_moves WHERE id=? AND project=?', (move_id, project)).fetchone()
        if move is None or move['fingerprint'] != pc['proposal_fingerprint']: raise ValueError('MOVE_FINGERPRINT_MISMATCH')
        mp = json.loads(move['payload_json'])
        if mp['proposed_operation']['cycle_binding'] != {'precommit_id': row['id'], 'sha256': row['digest']}: raise ValueError('MOVE_PRECOMMIT_DRIFT')
        activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
        latest = c.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence DESC LIMIT 1', (move_id,)).fetchone()
        if not activation or not latest or latest['status'] != 'EXPERIMENT_ALLOWED' or latest['audit_id'] != activation['audit_id']:
            raise ValueError('NO_CURRENT_BOUND_GRANT')
        # Reuse the existing read-only permission projection without running migrations.
        reader = ResearchStore.__new__(ResearchStore); reader.path = self.database
        if not reader.moves._view(c, move)['execution_permission']['allowed']: raise ValueError('CURRENT_LEGACY_PERMISSION_DENIED')
        decision = json.loads(latest['decision_json'])
        if not decision.get('allowed') or decision['scope'] != pc['scope'] or decision['frontier_versions'] != {str(pc['obligation_id']): pc['obligation_version']}:
            raise ValueError('STALE_OR_WRONG_GRANT')
        audit = c.execute('SELECT * FROM research_move_audits WHERE id=? AND move_id=? ORDER BY id', (activation['audit_id'], move_id)).fetchone()
        newest = c.execute('SELECT max(id) FROM research_move_audits WHERE move_id=?', (move_id,)).fetchone()[0]
        if audit is None or newest != audit['id'] or json.loads(audit['report_json'])['verdict'] != 'EXPERIMENT_ALLOWED': raise ValueError('STALE_OR_UNSUCCESSFUL_AUDIT')
        activation_op = c.execute('SELECT * FROM operations WHERE id=?', (activation['operation_id'],)).fetchone()
        act = json.loads(activation_op['details_json']) if activation_op else {}
        if not activation_op or activation_op['action'] != 'research_move_status_changed' or any(act.get(k) != v for k,v in
                {'move_id': move_id, 'status': 'EXPERIMENT_ALLOWED', 'audit_id': audit['id'], 'sequence': latest['sequence']}.items()):
            raise ValueError('FORGED_ACTIVATION_OPERATION')
        if act.get('decision_sha256') != digest(decision): raise ValueError('ACTIVATION_DECISION_DIGEST_MISMATCH')
        expected = {k: pc[k] for k in ('project', 'proposal_fingerprint', 'obligation_id', 'obligation_version', 'scope',
            'source_family_id', 'source_bindings', 'native_definition_sha256', 'operation_definition_sha256', 'observer', 'test_id', 'suffix', 'suffix_ordinals', 'purpose', 'law_fingerprint', 'context_word')}
        expected.update(precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id,
            audit_id=audit['id'], activation_operation_id=activation_op['id'], predictions=pc['alternatives'])
        if any(env[k] != v for k,v in expected.items()): raise ValueError('MEASUREMENT_BINDING_MISMATCH')
        if (data.get('observation') != {'test_id': pc['test_id'], 'readout': env['observed'], 'scope': pc['scope'],
                'version': pc['obligation_version'], 'observer': pc['observer']}
                or data.get('outcome') != env['outcome'] or data.get('proof_status') != 'unverified'):
            raise ValueError('RESULT_EVENT_CONFLICT')
        order = {'precommit': [], 'audit': [], 'event': []}
        for op in c.execute('SELECT * FROM operations WHERE id<=? ORDER BY id', (c.execute('SELECT max(id) FROM operations').fetchone()[0],)):
            d = json.loads(op['details_json'])
            if op['action'] == 'typed011_precommitted' and d.get('precommit_id') == row['id'] and d.get('digest') == row['digest']: order['precommit'].append(op['id'])
            if op['action'] == 'research_move_audited' and d.get('audit_id') == audit['id']: order['audit'].append(op['id'])
            event_digest = digest({k:event[k] for k in ('project','kind','focus','content','status','evidence','parent_id')})
            if op['action'] == 'event_created' and d.get('id') == event_id and d.get('digest') == event_digest:
                order['event'].append(op['id'])
        if any(len(v) != 1 for v in order.values()):
            raise ValueError('PRECOMMIT_AUDIT_ACTIVATION_EVENT_ORDER')
        require_ledger_order(order['precommit'][0], order['audit'][0], activation_op['id'], order['event'][0])
        execution = c.execute('SELECT * FROM typed011_executions WHERE move_id=? AND event_id=?', (move_id, event_id)).fetchone()
        if execution is None: raise ValueError('NO_OPERATOR_LOCAL_EXECUTOR_RECEIPT')
        local = json.loads(execution['payload_json']); registered = scope(c, project)
        if env['executor_code_sha256'] != registered['executor_code_sha256'] or local['envelope_sha256'] != digest(env): raise ValueError('EXECUTOR_IDENTITY_OR_PAYLOAD_CONFLICT')
        artifact = Path(local['artifact_path']).resolve(strict=True)
        if not artifact.is_relative_to(Path(registered['artifact_directory']).resolve(strict=True)) or artifact.stat().st_size > 1_000_000:
            raise ValueError('ARTIFACT_OUTSIDE_INSPECTABLE_LOCAL_BOUNDARY')
        import hashlib
        artifact_data = artifact.read_bytes()
        if hashlib.sha256(artifact_data).hexdigest() != env['artifact_sha256']: raise ValueError('ARTIFACT_DIGEST_MISMATCH')
        artifact_value = json.loads(artifact_data)
        if artifact_value['precommit_sha256'] != row['digest'] or artifact_value['move_id'] != move_id or artifact_value['observed'] != env['observed']:
            raise ValueError('ARTIFACT_MEASUREMENT_MISMATCH')
        if artifact_value.get('observed_coordinate') != env['observed_coordinate']: raise ValueError('ARTIFACT_COORDINATE_MISMATCH')
        matches = env['observed'] == pc['expected_readout']
        if pc['purpose'] == 'VALIDATE_TRANSFER': matches = matches and env['observed_coordinate'] == pc['expected_coordinate']
        calculated = 'SUCCESS' if matches else 'FAILURE'
        if env['outcome'] not in {calculated, 'INCONCLUSIVE', 'ERROR'}: raise ValueError('OUTCOME_PREDICTION_CONFLICT')
        if artifact_value['outcome'] != env['outcome']: raise ValueError('ARTIFACT_OUTCOME_MISMATCH')
        raw = json.loads(row['preview_json'])
        journal = journal_state(c, project, pc['scope'], pc['source_family_id'], pc['claim_fingerprint'], pc['raw_distinction_sha256'])
        if journal == 'REQUIRES_REVIEW': return denied('REQUIRES_REVIEW', 'JOURNAL_RAW_DISTINCTION_CONFLICT')
        return denied('VALID_BOUND_MEASUREMENT', 'Structural binding and local synthetic executor artifact checked; not physical authenticity or mathematical truth.',
            precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id, event_id=event_id,
            event_sha256=digest(dict(event)), audit_id=audit['id'], activation_operation_id=activation_op['id'],
            event_operation_id=order['event'][0], envelope=env, artifact_inspection='LOCAL_EXECUTOR_ARTIFACT_HASH_CHECKED',
            measurement_authenticity='LOCAL_SYNTHETIC_TRUST_BOUNDARY_ONLY', novelty=journal,
            preview_replay_digest=raw['preview_digest'])
