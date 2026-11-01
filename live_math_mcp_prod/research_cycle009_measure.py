"""Privileged external QA instrument. Never imported or called by preview I/T."""
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time


def main():
    started = time.perf_counter_ns()
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    request = json.loads(sys.stdin.buffer.read(65537))
    from research_cycle009_worlds import checksum
    from live_constructive007_native import Port, Ledger, native_fingerprint
    registry = json.loads(Path(__file__).with_name('native_preview008-adapters.json').read_text())
    if native_fingerprint() != registry['livingmath.native007.reviewed.v1']['native_sha256']:
        raise ValueError('UNREVIEWED_INSTRUMENT_DEFINITIONS')
    world = json.loads(Path(request['world_file']).read_text())
    if checksum({k: v for k, v in world.items() if k not in {'fixture_sha256', 'scope'}}) != world['fixture_sha256']:
        raise ValueError('PUBLIC_FIXTURE_DEFINITION_DRIFT')
    environment_bytes = Path(request['environment_file']).read_bytes()
    if hashlib.sha256(environment_bytes).hexdigest() != request['environment_sha256']:
        raise ValueError('ENVIRONMENT_COMMITMENT_DRIFT')
    environment = json.loads(environment_bytes)
    if environment['fixture_sha256'] != world['fixture_sha256'] or environment['parameters'] != world['parameters']:
        raise ValueError('INSTRUMENT_FIXTURE_DRIFT')
    with sqlite3.connect(Path(request['database']).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        move = conn.execute('SELECT * FROM research_moves WHERE id=? AND project=?', (request['move_id'], world['project'])).fetchone()
        history = conn.execute('SELECT * FROM research_move_status_history WHERE move_id=? ORDER BY sequence DESC LIMIT 1', (request['move_id'],)).fetchone()
        if move is None or history is None:
            raise ValueError('NO_MEASUREMENT_GRANT')
        payload = json.loads(move['payload_json']); decision = json.loads(history['decision_json'])
        active = conn.execute('SELECT current_version FROM research_obligations WHERE id=?', (payload['active_frontier_id'],)).fetchone()
        version = conn.execute('SELECT payload_json FROM research_obligation_versions WHERE obligation_id=? AND version=?',
            (payload['active_frontier_id'], active['current_version'])).fetchone()
        current = json.loads(version['payload_json'])
        if (history['status'] != 'EXPERIMENT_ALLOWED' or decision.get('allowed') is not True
                or decision['scope'] != world['scope'] or current['scope'] != world['scope']
                or current['status'] not in {'OPEN', 'TESTING'} or current['version'] != request['version']
                or decision['frontier_versions'] != {str(payload['active_frontier_id']): request['version']}
                or payload['proposed_operation']['mechanism'] != 'qa_cycle_measurement'):
            raise ValueError('STALE_OR_WRONG_MEASUREMENT_GRANT')
    test = next(t for t in world['tests'] if t['id'] == request['test_id'])
    if 'Finite declared test ' + request['test_id'] not in payload['proposed_operation']['mathematical_properties']:
        raise ValueError('MEASUREMENT_NOT_BOUND_TO_GRANTED_TEST')
    ledger = Ledger(2048, 2); ledger.stage = 'external_measurement'
    port = Port(world['parameters'], ledger)
    state = port.load(environment['target_word']); flags = []
    for action in test['suffix']:
        allowed = port.admissible(state, action); flags.append(allowed)
        if not allowed:
            raise ValueError('EXTERNAL_MEASUREMENT_ADMISSIBILITY_DENIED')
        state = port.extend(state, action)
    readout = {'defined': True, 'observation': port.observe(state, world['observer']), 'admissibility': flags}
    out = {'test_id': test['id'], 'readout': readout, 'scope': world['scope'], 'version': request['version'],
           'observer': world['observer'], 'fixture_sha256': world['fixture_sha256'],
           'measurement_origin': 'external_bounded_native_executor', 'proof_status': 'unverified',
           'cost_ledger': ledger.summary(), 'private_native_trace': ledger.trace,
           'instrument_wall_ns': time.perf_counter_ns() - started}
    sys.stdout.write(json.dumps(out))


if __name__ == '__main__':
    main()
