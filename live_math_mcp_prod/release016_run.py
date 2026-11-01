"""One bounded016 source experiment; no production server or schema mutations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile

from normalizer import canonical, digest, read_history, normalize_context, reconstruct_context
from qa_positive_acceptance import write_json, snapshot
from research_store import ResearchStore
from real_xi015_run import measured, append
from real_xi015_source import audit_export
from real_xi015_reproduce import sha
from release016_math import ARCHIVE_SHA, HS, T, identity, score, binding_sha

SOURCE = Path(__file__).resolve().parent
CODE = ['release016_math.py', 'release016_worker.py', 'release016_typed.py', 'release016_operator.py', 'release016_run.py']


def freeze(path, value):
    with path.open('x') as stream:
        stream.write(canonical(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def training_frame(db, project, anchors):
    store = ResearchStore(db)
    events = []
    for name, data in [('native-h0-n2', next(r for r in anchors if r['h'] == '0' and r['source_address']['n'] == 2)),
                       ('native-h1-n2', next(r for r in anchors if r['h'] == '0.001' and r['source_address']['n'] == 2)),
                       ('independent', {'statement': 'Source-address provenance distinct from value transport.'})]:
        e = store.record(project, 'qa_source', name, canonical(data), 'hypothesis', request_key=project + ':' + name)
        with store._connect() as c:
            events.append(dict(c.execute('SELECT * FROM events WHERE id=?', (e['id'],)).fetchone()))
    scope = 'release016/anchors'
    ob = store.frontier.create(project, 'Read only genuine allowed n1/2 source anchors.', scope, [e['id'] for e in events])
    refs = ['event:' + str(e['id']) for e in events]
    spec = {'parameters': {'actions': []}, 'histories': refs[:2], 'independent_ref': refs[2],
        'hypotheses': [{'id': r, 'ref': r, 'weight': 1, 'predictive': True, 'question': 'current', 'depends_on': []} for r in refs[:2]] +
                      [{'id': 'IND', 'ref': refs[2], 'weight': 1, 'predictive': False, 'question': 'independent', 'depends_on': []}],
        'tests': [], 'observer': {'projection': 'primary', 'mod': None}, 'current_observation': canonical(json.loads(events[0]['content'])['value']),
        'known_failures': [], 'unknowns': ['No native complex interval proof-schema in007.'], 'primitive_sha256': ARCHIVE_SHA}
    query = {'id': 'actual016-anchors', 'project': project, 'scope': scope, 'version': 1, 'root_ref': refs[0],
             'move': {'active_frontier_id': ob['id'], 'parent_event_ids': [e['id'] for e in events]}}
    history = read_history(db, project)
    normal = normalize_context(history, 'permitted theta anchors', [query], 'C2')
    recovered = reconstruct_context(normal, history)
    if recovered['tables']['events'] != history['tables']['events']:
        raise ValueError('NORMALIZATION_LOSS')
    return {'spec': spec, 'query': query, 'events': {e['id']: e for e in events},
        'words': {refs[0]: ['A'], refs[1]: ['B'], refs[2]: ['A']},
        'data': {'A': json.loads(events[0]['content']), 'B': json.loads(events[1]['content'])}}, {'status': normal['status'], 'exact_recovery': True}


def source_audit(base, out, archive):
    if not archive.exists() or sha(archive) != ARCHIVE_SHA:
        raise ValueError('STOP_SOURCE_MISSING: expected RH_XI_ROUTES_EXPORT_001.zip sha256=' + ARCHIVE_SHA)
    raw = base / 'raw/RH_XI_ROUTES_EXPORT_001'
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (base / 'raw' / name).resolve().is_relative_to(base / 'raw'):
                raise ValueError('UNSAFE_ARCHIVE')
        z.extractall(base / 'raw')
    manifest = json.loads((raw / 'MANIFEST_SHA256.json').read_text())
    if not all(sha(raw / name) == expected for name, expected in manifest.items()):
        raise ValueError('SOURCE_MANIFEST_MISMATCH')
    launcher = ('import resource,runpy,sys;resource.setrlimit(resource.RLIMIT_CPU,(90,90));'
        'resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824));'
        'p=sys.argv.pop(1);sys.path.insert(0,str(__import__("pathlib").Path(p).parent));runpy.run_path(p,run_name="__main__")')
    cost = measured([sys.executable, '-c', launcher, str(raw / 'reproduce.py'), '--out', str(base / 'source-reproduced')],
        out / 'source-reproduction.log', timeout=120)
    start, cpu = time.perf_counter_ns(), time.process_time_ns()
    audit = audit_export(raw / 'cases.json')
    regenerated = audit_export(base / 'source-reproduced/cases.json')
    exact = {n: sha(raw / n) == sha(base / 'source-reproduced' / n) for n in ('cases.json', 'routes.json', 'loops.json')}
    if not all(exact.values()) or audit != regenerated:
        raise ValueError('SOURCE_ADDRESS_MISMATCH')
    if audit['join']['ordered_address_sha256'] != '2fa469f8873e8f7150e749182f33c20f366563ab49b38f488b58680ea7962ecb':
        raise ValueError('SOURCE_ORDER_DRIFT')
    result = {'archive_sha256': ARCHIVE_SHA, 'full_manifest': manifest, 'exact_bytes': exact,
        'join': audit['join'], 'metadata': audit['header'], 'manifest_files_checked': len(manifest),
        'CASE_C_control': json.loads((raw / 'loops.json').read_text())['cases'][2]['loops'],
        'commit': None, 'source_status': 'T54 uses unchanged T49 formula; DIAG008 archival provenance only',
        'regeneration_cost': cost, 'streaming_audit_cost': {'CPU_ns': time.process_time_ns() - cpu, 'wall_ns': time.perf_counter_ns() - start},
        'rights': 'No redistribution licence found; original input ZIP excluded from capsule; supply operator-owned original with exact hash.'}
    write_json(out / 'source-audit.json', result)
    return raw, audit['nodes'][0]


def make_policy(raw, node):
    return {'experiment': 'LM-RELEASE-016-MATH', 'frozen_UTC': datetime.now(timezone.utc).isoformat(),
        'archive_sha256': ARCHIVE_SHA, 'native_file_hashes': {n: sha(raw / n) for n in ('reproduce.py', 'vendor/source.py', 'vendor/intervals.py', 'vendor/ALGEBRAIC_NODES.json')},
        'code_hashes': {n: sha(SOURCE / n) for n in CODE}, 't': T, 'h_train': HS[:2], 'h_grid': HS,
        'anchor_n': [1, 2], 'target_n': [3, 4], 'node': node,
        'address_table': [identity(n, b) for n in range(1, 5) for b in ('+', '-')],
        'selection': 'First genuine source node/prefix; t15 is new versus archived015 t14.134725141734694. No zero-label/accuracy selection.',
        'blind_scope': 'No n3/4 values/derivatives/amplitudes at t15 supplied to learner. Published015 values at other t are denied. Global public-source formula is explicitly allowed for every model.',
        'permitted': ['n1/2 native values/derivatives only at h0/.001,t15', 'u/quadrature weight/pi and exact source formula', 'source addresses/origin/branch/code hashes', 'source-owned n1/2 ledger frame'],
        'forbidden': ['all n3/4 per-address amplitude/value/derivative tables, at any h', 'raw cases/routes/015 traces/target artifacts', 'hidden evaluator calls in learner'],
        'baselines': {'B1': 'Original evaluate, independent postseal reference path, not predictive competitor',
            'B2': 'Public source formula q*(4a_n²-6a_n)*exp(u/2-a_n)*exp(eps*u*h)*exp(i*eps*u*t), same permitted data',
            'B3': 'Geometric h half/double; geometric integer n extrapolation from n1/2; principal-root positive-real guard, no complex logarithm needed',
            'B4': 'Linear extrapolation in n, Hermite in h using only n1/2 permitted derivatives; heuristic, no rigorous remainder',
            'B5': 'Unchanged006/007/013 bounded I/T; UNKNOWN on unsupported complex images is not mathematical FAIL'},
        'source_identity': {'n': 'f_(n+1)=R_n(u)*f_n; R_n=(4b²-6b)/(4a²-6a)*exp(-(b-a)); a=pi*n²*exp(2u), b=pi*(n+1)²*exp(2u)',
            'h': 'H_h=exp(epsilon*u*h)', 'cocycle': 'R_n H_h = H_h R_n at same u/epsilon; n changes original origin/address, not source equality'},
        'guards': ['same actual cell/node/branch and source definition', 'n in1..4, ratio step1..3, denominator lower bound>0', '|h|<=.5, |h+15i|<=27', 'no erasure or conflation of coordinate/source/scalar equality'],
        'metrics': {'primary': 'Native reference interval fully contained in prediction enclosure for both complex components; width<=1e-40 times predicted complex max magnitude',
            'padding': 'Source-identity C and B2 raw sound intervals widened by1e-45 times own pre-reveal max magnitude, same rule',
            'secondary': 'Overlap reported separately, never substituted for containment; heuristic B3/B4 scored midpoint error at same1e-40 scale with no proof claim',
            'cocycle': 'Both raw route enclosures overlap within1e-40 relative width; widened routes each contain native reference. SOURCE_IDENTITY_REPLAY, not independent discovery'},
        'budget': {'source_CPU_s': 90, 'source_wall_s': 120, 'source_AS_bytes': 1073741824,
            'P0_P3_CPU_s': 120, 'P0_P3_wall_s': 180, 'learner_AS_bytes': 536870912,
            'native_anchor_calls': 2, 'native_target_calls': 4, 'postactivation_calls': 1, 'LLM_calls': 0, 'corrected_fresh_cohorts_max': 1},
        'decisions': {'PASS_SOURCE_BOUND_N_H_TRANSFER': 'Source/blind/containment/cocycle/typed gates pass',
            'NO_STRUCTURAL_ADVANTAGE': 'B2 equally explains/predicts target values from same public formula; no autonomous superiority claim',
            'INCONCLUSIVE_BLIND': 'Preexisting target at t15 or leakage; no blind PASS',
            'NO_GO_SOURCE_DISCOVERY': 'Source formula instantiated, not inferred by unchanged013',
            'FAIL_OPERATIONAL_LAW': 'First false guarded C forecast/cocycle', 'STOP_RESOURCE': 'Frozen limit exceeded'}}


def close_qa(db, projects):
    from operational013_report import append_only, chain
    store = ResearchStore(db)
    for project in projects:
        with store._connect() as c:
            moves = [dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project=?', (project,))]
            obs = [dict(r) for r in c.execute('SELECT * FROM research_obligations WHERE project=?', (project,))]
        for move in moves:
            view = store.moves.inspect(project, move['id'])
            if view['status'] not in ('COMPLETED', 'ABANDONED', 'REJECTED'):
                store.moves.transition(project, move['id'], 'abandon', '016:close:' + str(move['id']), reason='Bounded016 QA ended; retain original outcome.')
        for ob in obs:
            current = store.frontier.history(ob['id'])[-1]
            if current['status'] in ('OPEN', 'TESTING', 'BLOCKED'):
                store.frontier.update(ob['id'], current['version'], {'status': 'RESOLVED',
                    'closure_reason': '016 finite source experiment ended; no proof claim.',
                    'evidence_refs': current['evidence_refs'] or ['event:' + str(i) for i in current['source_event_ids']],
                    'reopen_conditions': ['New immutable source question and explicit operator review.']})
    with store._connect() as c:
        moves = [dict(r) for r in c.execute('SELECT * FROM research_moves') if r['project'] in projects]
    views = [store.moves.inspect(m['project'], m['id']) for m in moves]
    return {'moves': views, 'active_permissions': [v['id'] for v in views if v['execution_permission']['allowed']],
            'append_only': append_only(db), 'chain': chain(db)}


def typed_cycle(db, canonical_db, out, public, policy, predictions, anchors, raw, project):
    from release016_typed import prepare, activate, Validator016, question_from
    from release016_operator import commit
    from law_validation014_contract import ReceiptRequest014
    from native_preview008_server import MeasuredProcess
    from typed_cycle011 import TypedCycle
    from typed_cycle011_store import connect
    pc = prepare(db, canonical_db, project, public, policy, predictions, anchors, raw)
    if pc['precommit']['execution_permission']['allowed']:
        raise ValueError('FALSE_PRECOMMIT_PERMISSION')
    denied = False
    try:
        question_from({'question_file': str(public / 'typed-question.json'), 'question_sha256': '0' * 64})
    except ValueError:
        denied = True
    activation = activate(db, project, pc['move_id'], 'release016-exact-question')
    started = time.perf_counter_ns()
    with (out / 'typed-executor.log').open('w') as log:
        proc = MeasuredProcess([sys.executable, str(SOURCE / 'release016_typed.py'), '--db', str(db)], stdin=subprocess.PIPE, stdout=log, stderr=log, text=True)
        try:
            proc.communicate(canonical({'project': project, 'move_id': pc['move_id'], 'raw': str(raw)}), timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(); raise ValueError('STOP_RESOURCE: typed wall')
    usage = proc.child_usage
    cost = {'CPU_ns': round((usage.ru_utime + usage.ru_stime) * 1e9), 'wall_ns': time.perf_counter_ns() - started, 'peak_RSS_KiB': usage.ru_maxrss}
    if proc.returncode:
        raise ValueError('TYPED_EXECUTION_FAILED:' + (out / 'typed-executor.log').read_text()[-1600:])
    execution = json.loads((out / 'typed-executor.log').read_text())
    validation = Validator016(db).validate(project, pc['move_id'], execution['event_id'])
    if validation['status'] != 'VALID_BOUND_MEASUREMENT':
        raise ValueError('TYPED_VALIDATION:' + canonical(validation))
    env = execution['envelope']
    req = ReceiptRequest014(project=project, move_id=pc['move_id'], event_id=execution['event_id'], request_key='016:receipt',
        **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}).model_dump()
    receipt = commit(db, req)
    stable = snapshot(db)
    repeat = commit(db, req)
    conflict = False
    try:
        commit(db, {**req, 'outcome': 'FAILURE' if req['outcome'] == 'SUCCESS' else 'SUCCESS'})
    except ValueError as error:
        conflict = str(error) == 'RECEIPT_REQUEST_KEY_CONFLICT'
    controls = {'source_rebind_denied': denied, 'duplicate_idempotent': repeat['idempotent'],
                'result_substitution_denied': conflict, 'no_duplicate_operations': stable == snapshot(db)}
    for stage, value in [('precommit', pc), ('activation', activation), ('native_measurement', execution), ('validation', validation), ('receipt', receipt), ('controls', controls)]:
        append(out / 'typed-ledger.jsonl', {'stage': stage, 'data': value})
    shutil.copy2(execution['artifact_path'], out / 'typed-native-raw.json')
    if not all(controls.values()):
        raise ValueError('TYPED_CONTROLS_FAILED')
    return receipt, cost


def run(base, out, archive, canonical_db, policy_input=None):
    start, own0, child0 = time.perf_counter_ns(), resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    out.mkdir(parents=True, exist_ok=False)
    private = base / 'evaluation'
    private.mkdir()
    public = base / 'learner'
    public.mkdir()
    costs = {}
    db = base / 'private-QA.sqlite3'
    with sqlite3.connect(canonical_db.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(db) as dst:
        src.backup(dst)
    original = snapshot(db)
    stamp = out.name
    projects = ['LM_QA_RELEASE016_TRAIN_' + stamp, 'LM_QA_TYPED011_RELEASE016_' + stamp]
    try:
        raw, node = source_audit(base, out, archive)
        policy = json.loads(policy_input.read_text()) if policy_input else make_policy(raw, node)
        if policy['archive_sha256'] != ARCHIVE_SHA or any(sha(SOURCE / n) != h for n, h in policy['code_hashes'].items()):
            raise ValueError('PRE_REGISTRATION_CODE_DRIFT')
        freeze(out / 'pre-registration.json', policy)
        freeze(out / 'pre-registration-seal.json', {'bytes_sha256': sha(out / 'pre-registration.json'), 'canonical_sha256': digest(policy), 'UTC': datetime.now(timezone.utc).isoformat()})
        write_json(out / 'anchors-allowlist.json', {'allow': policy['permitted'], 'deny': policy['forbidden'],
            'node': node, 'source_addresses': policy['address_table'], 'blind_history_audit': 'Original015 h forecasts fixed t14.134725141734694; no observed t15 targets in015. Native target output files do not yet exist.'})
        anchors = []
        for h in HS[:2]:
            request, answer = private / ('anchor-request-' + h + '.json'), private / ('anchor-' + h + '.json')
            write_json(request, {'h': h, 't': T})
            costs['anchors-' + h] = measured([sys.executable, str(SOURCE / 'release016_worker.py'), 'anchors', '--native', str(raw), '--input', str(request), '--output', str(answer)], out / ('anchor-' + h + '.log'))
            data = json.loads(answer.read_text())
            if data['n_in_native_input'] != [1, 2]:
                raise ValueError('INCONCLUSIVE_BLIND: target anchor computed')
            anchors.extend(data['rows'])
        frame, norm = training_frame(db, projects[0], anchors)
        write_json(out / 'normalization004.json', norm)
        inputs = {'t': T, 'archive_sha256': ARCHIVE_SHA, 'node': node, 'anchors': anchors,
                  'pre_registration_sha256': digest(policy), 'legacy_frame': frame}
        write_json(public / 'inputs.json', inputs)
        shutil.copy2(public / 'inputs.json', out / 'permitted-learner-input.json')
        command = [sys.executable, str(SOURCE / 'release016_worker.py'), 'predict', '--native', str(raw), '--input', str(public / 'inputs.json'),
            '--output', str(public / 'forecasts.json'), '--deny', str(raw / 'cases.json'), '--deny', str(archive), '--deny', str(private)]
        costs['all-models-preseal'] = measured(command, out / 'learner.log')
        forecast = json.loads((public / 'forecasts.json').read_text())
        write_json(out / 'learner-isolation.json', forecast['isolation'])
        write_json(out / 'B5-unchanged-core.json', forecast['B5'])
        predictions = forecast['predictions']
        if len(predictions) != 16:
            raise ValueError('PREDICTION_COMPLETENESS')
        for row in predictions:
            append(out / 'sealed-predictions.jsonl', {**row, 'sealed_UTC': datetime.now(timezone.utc).isoformat()})
        freeze(out / 'prediction-seal.json', {'sha256': sha(out / 'sealed-predictions.jsonl'), 'rows': len(predictions), 'UTC': datetime.now(timezone.utc).isoformat(),
            'native_evaluate_calls_in_learner': forecast['native_evaluate_calls'], 'input_sha256': sha(public / 'inputs.json'), 'pre_registration_sha256': digest(policy)})
        comparison, squares = [], []
        for h in HS:
            request, answer = private / ('target-request-' + h + '.json'), private / ('target-' + h + '.json')
            write_json(request, {'h': h, 't': T})
            costs['B1-target-' + h] = measured([sys.executable, str(SOURCE / 'release016_worker.py'), 'target', '--native', str(raw), '--input', str(request), '--output', str(answer)], out / ('B1-' + h + '.log'))
            targets = json.loads(answer.read_text())
            write_json(out / ('B1-native-receipt-' + h + '.json'), targets)
            for actual in targets['rows']:
                if actual['source_address']['n'] not in (3, 4):
                    continue
                append(out / 'target-reveal.jsonl', {'native': actual, 'after_prediction_seal': True, 'seal_sha256': sha(out / 'sealed-predictions.jsonl')})
                pred = next(p for p in predictions if p['index'] == actual['index'] and p['binding']['h'] == h)
                if any(pred[k] != actual[k] for k in ('index', 'origin_id', 'source_address')):
                    raise ValueError('SOURCE_ADDRESS_MISMATCH')
                scores = {m: score(pred[m], actual['value']) for m in ('C', 'B2_source_formula', 'B3_geometric', 'B4_linear_n_Hermite_h')}
                comparison.append({'h': h, 'index': actual['index'], 'source_address': actual['source_address'], 'scores': scores})
                from real_xi015_source import load_native
                from release016_math import enclosure
                native = load_native(raw)
                paths = pred['cocycle']
                route_scores = {k: score(enclosure(native, v), actual['value']) for k, v in paths.items() if isinstance(v, dict)}
                route_overlap = score(paths['n_then_h'], paths['h_then_n'])['overlap_PASS']
                square = {'h': h, 'index': actual['index'], 'routes_vs_reference': route_scores,
                          'raw_route_overlap': route_overlap, 'classification': 'SOURCE_IDENTITY_REPLAY'}
                squares.append(square)
                if not scores['C']['containment_PASS'] or not route_overlap or not all(s['containment_PASS'] for s in route_scores.values()):
                    write_json(out / 'first-failure.json', {'status': 'FAIL_OPERATIONAL_LAW', 'prediction': pred, 'native': actual, 'scores': scores, 'square': square})
                    raise ValueError('FAIL_OPERATIONAL_LAW')
        write_json(out / 'comparison.json', {'per_address': comparison, 'summary': {m: {'containment_PASS': sum(r['scores'][m]['containment_PASS'] for r in comparison),
            'overlap_PASS': sum(r['scores'][m]['overlap_PASS'] for r in comparison)} for m in comparison[0]['scores']},
            'B3_B4': 'Heuristic point forecasts have no claimed proven enclosure; numeric midpoint tolerance is separately reported in component errors.'})
        write_json(out / 'n-h-cocycle.json', {'classification': 'SOURCE_IDENTITY_REPLAY', 'squares': squares})
        receipt, costs['typed-fresh-native'] = typed_cycle(db, canonical_db, out, public, policy, predictions, anchors, raw, projects[1])
        status = 'PASS_SOURCE_BOUND_N_H_TRANSFER'
    except Exception as error:
        status = str(error).split(':')[0] if str(error).startswith(('STOP_', 'FAIL_', 'INCONCLUSIVE_')) else 'STOP_WITH_RCA'
        write_json(out / 'exception.json', {'status': status, 'error': str(error), 'traceback': __import__('traceback').format_exc()})
    finally:
        cleanup = close_qa(db, projects)
        after = snapshot(db)
        prefixes = {t: after['tables'][t][:len(rows)] == rows for t, rows in original['tables'].items()}
        write_json(out / 'private-integrity.json', {**cleanup, 'all_original_table_prefixes': prefixes})
        appended = {t: rows[len(original['tables'].get(t, [])):] for t, rows in after['tables'].items()}
        write_json(out / 'private-QA-append-trace.json', appended)
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    costs['P0_P3_total'] = {'wall_ns': time.perf_counter_ns() - start,
        'CPU_ns': round((own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime
            - own0.ru_utime - own0.ru_stime - child0.ru_utime - child0.ru_stime) * 1e9),
        'largest_process_peak_RSS_KiB': max(own.ru_maxrss, children.ru_maxrss)}
    if costs['P0_P3_total']['CPU_ns'] > 120e9 or costs['P0_P3_total']['wall_ns'] > 180e9:
        status = 'STOP_RESOURCE'
    write_json(out / 'costs.json', costs)
    write_json(out / 'experiment-result.json', {'status': status, 'proof_status': 'unverified', 'production_writes': False,
        'structural_advantage': 'NO_STRUCTURAL_ADVANTAGE' if status == 'PASS_SOURCE_BOUND_N_H_TRANSFER' else 'INCONCLUSIVE',
        'autonomous_discovery': 'NO_GO_SOURCE_DISCOVERY', 'private_database': str(db)})
    print(canonical({'status': status, 'out': str(out)}))
    if status != 'PASS_SOURCE_BOUND_N_H_TRANSFER':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--canonical', type=Path)
    parser.add_argument('--policy', type=Path)
    args = parser.parse_args()
    if args.base:
        base = args.base.resolve()
        base.mkdir(parents=True, exist_ok=False)
        canonical_db = base / 'disposable-origin.sqlite3'
        ResearchStore(canonical_db)
        run(base, args.out.resolve(), args.archive.resolve(), canonical_db, args.policy)
    else:
        base = Path(Path('/tmp/lm016_path').read_text().strip())
        meta = json.loads((base / 'metadata.json').read_text())
        run(base, Path(meta['out']), Path(meta['archive']), base / 'canonical.sqlite3')
