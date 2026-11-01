"""Read-only projections over frozen004.1/006.2/007.2; never instantiate a store."""
import copy
import json
from pathlib import Path
import resource
import sqlite3
import time

from normalizer import Budget, canonical, digest, normalize_context, read_history
from live_constructive007 import interpret_constructive
from live_constructive007_laws import AUDITED_IMPLEMENTATION
from live_constructive007_native import Ledger, native_fingerprint
from live_constructive007_source import load_frame, payload, ref_id
from live_transfer006 import attend, interpret
from native_preview008_contract import ADAPTER_ID, VERSION, NativeRequest, NormalizeRequest, refusal


def install_readonly_sqlite(path: Path) -> None:
    """All connections in this worker are pinned, SELECT-only and authorizer guarded."""
    original = sqlite3.connect
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_RECURSIVE}
    uri = path.resolve(strict=True).as_uri() + '?mode=ro'

    def authorize(action, arg1, arg2, database, trigger):
        if action in allowed:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and arg1 in {'user_version', 'query_only'}:
            if arg1 == 'user_version' and arg2 is not None:
                return sqlite3.SQLITE_DENY
            if arg1 == 'query_only' and arg2 not in {None, 'ON', '1'}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def connect(database, *args, **kwargs):
        if str(database) != uri:
            raise ValueError('Worker database binding is fixed by the server')
        conn = original(uri, *args, **{**kwargs, 'uri': True})
        conn.execute('PRAGMA query_only=ON')
        conn.set_authorizer(authorize)
        return conn

    sqlite3.connect = connect


def source_budget(budget) -> Budget:
    return Budget(max_source_bytes=budget.source_bytes, max_output_bytes=budget.output_bytes,
                  max_tokens=budget.max_tokens, max_events=budget.max_events,
                  max_milliseconds=budget.deadline_ms)


def check_sources(history: dict, ids: list[int], bindings: list, exact: bool = False) -> list:
    events = {e['id']: e for e in history['tables']['events']}
    if len(set(ids)) != len(ids) or any(i not in events for i in ids):
        raise ValueError('MISSING_OR_FOREIGN_SOURCE')
    supplied = {x.event_id: x.sha256 for x in bindings}
    if len(supplied) != len(bindings) or not set(supplied) <= set(ids):
        raise ValueError('DUPLICATE_OR_UNDECLARED_BINDING')
    if exact and set(supplied) != set(ids):
        raise ValueError('EXACT_SOURCE_BINDINGS_REQUIRED')
    if any(digest(events[i]) != h for i, h in supplied.items()):
        raise ValueError('SOURCE_HASH_DRIFT')
    return [{'ref': 'event:' + str(i), 'project': history['project'], 'sha256': digest(events[i])}
            for i in sorted(ids)]


def frontier(history: dict, oid: int, version: int, scope=None) -> dict:
    row = next((o for o in history['tables']['research_obligations'] if o['id'] == oid), None)
    if row is None or row['project'] != history['project'] or row['current_version'] != version:
        raise ValueError('STALE_OR_FOREIGN_FRONTIER')
    versions = [json.loads(v['payload_json']) for v in history['tables']['research_obligation_versions']
                if v['obligation_id'] == oid]
    current = next((v for v in versions if v['version'] == version), None)
    if current is None or current['status'] not in {'OPEN', 'TESTING'}:
        raise ValueError('CLOSED_FRONTIER')
    if scope is not None and scope != current['scope']:
        raise ValueError('FRONTIER_SCOPE_MISMATCH')
    return current


def validate_parameters(spec: dict) -> None:
    """Finite reviewed data schemas, not a solver or arbitrary Python verifier."""
    p = spec['parameters']
    common = {'family', 'initial', 'actions'}
    additions = {'affine': {'coefficients', 'modulus'}, 'permutation': {'permutations'},
                 'erasure': {'cuts'}, 'opaque': set(), 'boundary': set()}
    family = p['family']
    if family not in additions or set(p) != common | additions[family]:
        raise ValueError('UNREVIEWED_PARAMETER_FIELDS')
    actions, initial = p['actions'], p['initial']
    if not isinstance(actions, list) or not 2 <= len(actions) <= 10 or len(set(actions)) != len(actions):
        raise ValueError('ACTION_BOUND')
    if any(not isinstance(a, str) or not 1 <= len(a) <= 80 for a in actions):
        raise ValueError('ACTION_LABEL')
    if not isinstance(initial, list) or not 1 <= len(initial) <= 32:
        raise ValueError('INITIAL_STATE_BOUND')
    integer = lambda n: type(n) is int and abs(n) <= 2**31
    if family == 'affine':
        if (not integer(p['modulus']) or p['modulus'] < 2 or len(initial) != 2
                or any(not integer(n) or not 0 <= n < p['modulus'] for n in initial)
                or len(p['coefficients']) != len(actions) or not all(map(integer, p['coefficients']))):
            raise ValueError('AFFINE_PARAMETER_BOUND')
    elif family == 'permutation':
        n = len(initial)
        if n > 16 or sorted(initial) != list(range(n)) or any(type(x) is not int for x in initial):
            raise ValueError('PERMUTATION_INITIAL_BOUND')
        if len(p['permutations']) != len(actions) or any(
                not isinstance(g, list) or any(type(x) is not int for x in g) or sorted(g) != list(range(n))
                for g in p['permutations']):
            raise ValueError('PERMUTATION_PARAMETER_BOUND')
    elif family == 'erasure':
        if (any(not isinstance(x, str) or not 1 <= len(x) <= 16 or x == 'EMPTY' for x in initial)
                or len(p['cuts']) != len(actions)
                or any(type(x) is not int or not 0 <= x <= len(initial) for x in p['cuts'])):
            raise ValueError('ERASURE_PARAMETER_BOUND')
    elif initial != [0]:
        raise ValueError('OPAQUE_INITIAL_BOUND')


def reject_executable_fields(value) -> None:
    if isinstance(value, dict):
        if any(k.startswith('__') or k in {'code', 'python', 'exec', 'eval', 'callable', 'verified'} for k in value):
            raise ValueError('EXECUTABLE_OR_AUTHORITY_FIELD')
        for v in value.values():
            reject_executable_fields(v)
    elif isinstance(value, list):
        for v in value:
            reject_executable_fields(v)


def normalize(request: NormalizeRequest, history: dict) -> dict:
    q = request.query_scope
    hashes = check_sources(history, request.source_event_ids, q.expected_hashes)
    active = frontier(history, q.obligation_id, q.version, q.scope) if q.obligation_id else None
    # Preserve the registered Dq exactly;004 records every excluded source in its loss ledger.
    candidates = copy.deepcopy(q.candidates)
    view = normalize_context(history, request.focus, candidates, q.level, source_budget(request.budget))
    sufficient = view['status'] == 'COMPLETE' and q.level != 'C4'
    return {'status': view['status'], 'source_hashes': hashes, 'obligation_id': q.obligation_id,
            'version': active['version'] if active else None, 'normalizer_version': '004.1',
            'claims': view['concepts'], 'unknowns': view['unresolved'] + [u for c in view['concepts'] for u in c['unknowns']],
            'counter_readings': [c['counter_reading'] for c in view['concepts'] if c['counter_reading'] is not None],
            'declared_relations': [rel for c in view['concepts'] for rel in c['relations']] + view['interpretations'],
            'loss_ledger': view['loss_ledger'],
            'recovery_refs': [{'ref': k, 'sha256': v, 'project': request.project} for k, v in view['source_catalog'].items()],
            'audit_sufficient': sufficient, 'epistemic_status': 'unverified', 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}, 'preview_version': VERSION, 'view': view,
            'limitations': ['Completeness only for this registered finite Dq and bound auditor version.',
                            'Lexical aliases do not establish source identity or mathematical equivalence.']}


def native(request: NativeRequest, history: dict) -> dict:
    hashes = check_sources(history, request.source_event_ids, request.source_bindings, exact=True)
    registry = json.loads(Path(__file__).with_name('native_preview008-adapters.json').read_text())
    adapter = registry.get(request.source_adapter_id)
    if request.source_adapter_id != ADAPTER_ID or adapter is None:
        raise ValueError('UNSUPPORTED_ADAPTER')
    if adapter['native_sha256'] != native_fingerprint() or adapter['native_sha256'] != AUDITED_IMPLEMENTATION:
        raise ValueError('UNREVIEWED_ADAPTER_DIGEST')
    active = frontier(history, request.active_frontier_id, request.active_frontier_version)
    question = request.question
    ids = {question.root_event_id, question.left_history_id, question.right_history_id}
    ids |= {x for x in (question.certificate_event_id, question.feedback_event_id) if x is not None}
    if not ids <= set(request.source_event_ids):
        raise ValueError('QUESTION_SOURCE_NOT_BOUND')
    query = {'id': 'native-preview008', 'project': request.project,
             'root_ref': f'event:{question.root_event_id}', 'scope': active['scope'],
             'version': request.active_frontier_version,
             'move': {'active_frontier_id': request.active_frontier_id,
                      'parent_event_ids': request.source_event_ids,
                      'proposed_operation': {'mechanism': 'readonly_source_law_interpretation', 'intent': 'advisory'}}}
    view = normalize_context(history, 'source-certified interpretation', [query],
                             question.context_level, source_budget(request.budget))
    if view['status'] != 'COMPLETE' or question.context_level == 'C4':
        raise ValueError('INCOMPLETE_OR_C4_CONTEXT')
    frame = load_frame(view, history, query)
    validate_parameters(frame.spec)
    required = {ref_id(x) for x in frame.spec['histories'] + [frame.spec['independent_ref']]}
    required |= {i for i, e in frame.events.items() if e['kind'] in {'failure', 'failed_check', 'counterexample', 'rca'}
                 or e['status'] in {'refuted', 'counterexample'}}
    if not required <= set(request.source_event_ids):
        raise ValueError('DEPENDENCY_SOURCE_NOT_BOUND')
    if request.observer.model_dump() != frame.spec['observer']:
        raise ValueError('OBSERVER_MISMATCH')
    ledger = Ledger(request.budget.native_calls, request.budget.deadline_ms / 1000)
    left, right = f'event:{question.left_history_id}', f'event:{question.right_history_id}'
    start = time.perf_counter_ns()
    if question.mode == 'constructive':
        out = interpret_constructive(frame.fork(ledger), left, right,
                                    f'event:{question.certificate_event_id}' if question.certificate_event_id else None,
                                    known=question.known_fingerprints, max_calls=request.budget.native_calls)
    else:
        ledger.stage = 'baseline_B1'
        out = interpret(frame.fork(ledger), left, right, known=question.known_fingerprints,
                        max_calls=request.budget.native_calls)
    interpretation_ns = time.perf_counter_ns() - start
    out = copy.deepcopy(out)
    interpretation_ledger = ledger.summary()
    start = time.perf_counter_ns()
    ledger.stage = 'independent_T'
    attention = attend(frame.fork(ledger),
                       f'event:{question.feedback_event_id}' if question.feedback_event_id else None,
                       max_calls=request.budget.native_calls)
    attention_ns = time.perf_counter_ns() - start
    witness = None
    if out.get('witness'):
        witness = {**out['witness'], 'histories': [left, right], 'readouts': out['predictions'],
                   'admissibility': out['admissibility_trace'], 'provenance': out['source_hashes'],
                   'guard': out['guard'], 'proof_status': 'unverified'}
    status = out['status']
    if status == 'NO_NEW_DISTINCTION':
        status = 'NO_NEW_DISTINCTION_BOUNDED'
    return {'status': status, 'witness': witness, 'attention': attention,
            'interpretation': out, 'fallback_reason': out.get('fallback_reason'),
            'law_receipt': out.get('law', {'status': 'NOT_USED_B1'}), 'primitive_calls': dict(ledger.native),
            'cost_ledger': {'total': ledger.summary(), 'interpretation': interpretation_ledger,
                            'interpretation_ns': interpretation_ns, 'attention_ns': attention_ns,
                            'attention_native_calls': sum(ledger.native.values()) - interpretation_ledger['total_native_calls']},
            'source_hashes': hashes, 'source_adapter_id': request.source_adapter_id,
            'active_frontier_id': request.active_frontier_id, 'active_frontier_version': request.active_frontier_version,
            'observer': request.observer.model_dump(), 'proof_status': 'unverified', 'asserts_equivalence': False,
            'execution_permission': {'allowed': False}, 'preview_version': VERSION,
            'limitations': ['Finite registered D only; UNKNOWN is not equivalence.',
                            'Law receipt trusts reviewed finite source schemas, not arbitrary Python semantics.',
                            'T recommends a finite experiment; no external experiment or research move is executed.',
                            'Native-query reduction does not imply cold CPU or wall-time reduction.']}


def evaluate(path: Path, kind: str, arguments: dict) -> dict:
    start, cpu = time.perf_counter_ns(), time.process_time_ns()
    model = NativeRequest if kind == 'native' else NormalizeRequest
    request = model.model_validate(arguments)
    reject_executable_fields(arguments)
    history_start = time.perf_counter_ns()
    history = read_history(path, request.project, source_budget(request.budget))
    history_ns = time.perf_counter_ns() - history_start
    serialization_start = time.perf_counter_ns()
    source_bytes = len(canonical(history).encode())
    serialization_ns = time.perf_counter_ns() - serialization_start
    try:
        out = native(request, history) if kind == 'native' else normalize(request, history)
    except (ValueError, KeyError, TypeError, StopIteration) as error:
        out = refusal('INSUFFICIENT_CONTEXT', str(error))
    out.update(cold_wall_ns=time.perf_counter_ns() - start, cold_cpu_ns=time.process_time_ns() - cpu,
               source_serialization={'bytes': source_bytes, 'wall_ns': serialization_ns},
               source_snapshot_wall_ns=history_ns,
               memory={'worker_max_rss_KiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
               resource_limits={'native_calls': request.budget.native_calls, 'suffix_length': 2,
                                'address_space_MiB': request.budget.memory_mb, 'hard_deadline_ms': request.budget.deadline_ms})
    if len(canonical(out).encode()) > request.budget.output_bytes:
        return refusal('RESOURCE_LIMIT', 'OUTPUT_BYTE_BOUND')
    return out
