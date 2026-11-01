"""Operator-only actual-source016 replay; immutable011/014 provide lifecycle storage."""
import argparse
import json
from pathlib import Path
import sys
from normalizer import canonical, digest, read_history, normalize_context, reconstruct_context
from frontier import ResearchMoveFingerprint
from research_store import ResearchStore
from typed_cycle011 import TypedCycle
from typed_cycle011_store import install, register_scope, connect, scope, assert_isolated
from typed_cycle011_operator import activate
from law_validation014_store import install as install_guards
from law_validation014_contract import Precommit014, Envelope014, ReceiptRequest014
from law_validation014_receipt import ReceiptValidator014
from research_cycle009 import operation, MECHANISM
from real_xi015_reproduce import sha
from real_xi015_source import load_native
from release016_worker import native_rows
from release016_math import ARCHIVE_SHA, T, identity, score

SOURCE = Path(__file__).resolve().parent
ADAPTER = 'actual-theta-n-h016/v1'
OBSERVER = {'projection': 'primary', 'mod': None}


def question_from(root):
    data = json.loads(Path(root['question_file']).read_text())
    if digest(data) != root['question_sha256']:
        raise ValueError('SOURCE_QUESTION_REBIND')
    return data


def observe(question, rows):
    if question['observer_code_sha256'] != sha(SOURCE / 'release016_math.py'):
        raise ValueError('OBSERVER_CODE_DRIFT')
    if [r['index'] for r in rows] != list(range(8)):
        raise ValueError('SOURCE_ADDRESS_MISMATCH')
    for row in rows:
        expected = identity(row['source_address']['n'], row['source_address']['branch'])
        if any(row[k] != v for k, v in expected.items()) or row['t'] != T or row['h'] != question['h']:
            raise ValueError('SOURCE_ADDRESS_MISMATCH')
    return sum(not score(p['C'], rows[p['index']]['value'])['containment_PASS']
               for p in question['predictions'])


class Validator016(ReceiptValidator014):
    def validate_in(self, c, project, move_id, event_id):
        result = super().validate_in(c, project, move_id, event_id)
        if result['status'] != 'VALID_BOUND_MEASUREMENT':
            return result
        pre = c.execute('SELECT p.payload_json FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=?', (move_id,)).fetchone()
        pc = json.loads(pre[0])
        root = c.execute('SELECT content FROM events WHERE id=? AND project=?',
            (pc['native_request']['question']['root_event_id'], project)).fetchone()
        question = question_from(json.loads(root[0]))
        local = c.execute('SELECT payload_json FROM typed011_executions WHERE move_id=?', (move_id,)).fetchone()
        artifact = json.loads(Path(json.loads(local[0])['artifact_path']).read_text())
        if pc['native_request']['source_adapter_id'] != ADAPTER or pc['native_definition_sha256'] != ARCHIVE_SHA:
            raise ValueError('SOURCE_DEFINITION_REBIND')
        if artifact['question_sha256'] != digest(question) or artifact['pre_registration_sha256'] != question['pre_registration_sha256']:
            raise ValueError('SOURCE_QUESTION_REBIND')
        count = observe(question, artifact['raw_rows'])
        if result['envelope']['observed_coordinate'] != [count] or result['envelope']['observed']['observation'] != count:
            raise ValueError('SOURCE_OBSERVER_MISMATCH')
        result.update(reason='Bound native theta calculation and containment observer checked; not mathematical verification.',
            measurement_authenticity='ORIGINAL_ARCHIVAL_THETA_EVALUATOR; trusted local operator/filesystem boundary')
        return result


def normalize_source(db, project, scope_name, obligation_id, events):
    ids = [e['id'] for e in events]
    query = {'id': 'real016', 'project': project, 'scope': scope_name, 'version': 1,
        'root_ref': 'event:' + str(ids[1]), 'move': {'active_frontier_id': obligation_id, 'parent_event_ids': ids}}
    history = read_history(db, project)
    normal = normalize_context(history, 'actual theta n/h source question', [query], 'C2')
    recovered = reconstruct_context(normal, history)
    complete = recovered['tables']['events'] == history['tables']['events']
    if not complete:
        raise ValueError('SOURCE_NORMALIZATION_LOSS')
    return {'status': normal['status'], 'exact_event_recovery': complete}


def prepare(db, canonical_db, project, public, policy, predictions, anchors, raw):
    install(db, canonical_db)
    install_guards(db)
    store = ResearchStore(db)
    scope_name = 'release016/' + project
    question = {'h': '0.0005', 't': T, 'archive_sha256': ARCHIVE_SHA,
        'pre_registration_sha256': digest(policy), 'observer_code_sha256': sha(SOURCE / 'release016_math.py'),
        'native_file_hashes': policy['native_file_hashes'],
        'predictions': [p for p in predictions if p['binding']['h'] == '0.0005'],
        'observer': 'number of failed n-target interval containments; zero is not Xi zero'}
    q_file = public / 'typed-question.json'
    q_file.write_text(canonical(question))
    q_sha = digest(question)
    def record(name, content):
        event = store.record(project, 'qa_source', name, canonical(content), 'hypothesis', request_key=project + ':' + name)
        with store._connect() as c:
            return dict(c.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone())
    fixture = record('source-manifest', {'claim_type': 'SOURCE_CLAIM', 'scope': scope_name, 'version': 1,
        'fixture_sha256': q_sha, 'environment_commitment': q_sha, 'archive_sha256': ARCHIVE_SHA})
    root = record('bound n-h question', {'claim_type': 'HYPOTHESIS', 'scope': scope_name, 'version': 1,
        'question_file': str(q_file), 'question_sha256': q_sha})
    imported = store.frontier.import_history({'import_key': project, 'project': project,
        'sources': [{'id': fixture['id'], 'sha256': digest(fixture)}],
        'obligations': [{'key': 'n-h', 'statement': 'Bounded genuine n-target measurement; no proof claim.',
            'scope': scope_name, 'source_event_ids': [fixture['id'], root['id']], 'evidence_refs': []}],
        'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'n-h', 'mechanisms': [MECHANISM],
            'scope': scope_name, 'source_event_ids': [fixture['id']], 'source_representations': ['fixture009:' + q_sha],
            'reason': 'Only this immutable theta question, typed binding and native executor.',
            'reopen_conditions': ['New source contract and explicit operator review.']}]}, 'User-authorized016 private QA operator')
    oid = imported['obligation_ids']['n-h']
    checks = normalize_source(db, project, scope_name, oid, [fixture, root])
    directory = public / 'typed-native-artifacts'
    directory.mkdir()
    op_sha = digest({'question': q_sha, 'observer': question['observer']})
    family = digest({'archive': ARCHIVE_SHA, 'addresses': list(range(8)), 't': T})
    register_scope(db, project, {'scope': scope_name, 'fixture_id': fixture['id'], 'fixture_sha256': digest(fixture),
        'fixture_content_sha256': q_sha, 'environment_sha256': q_sha, 'source_family_id': family,
        'operation_definition_sha256': op_sha, 'native_definition_sha256': ARCHIVE_SHA,
        'executor_code_sha256': sha(__file__), 'artifact_directory': str(directory)})
    bindings = [{'event_id': e['id'], 'sha256': digest(e)} for e in (fixture, root)]
    request = {'project': project, 'active_frontier_id': oid, 'active_frontier_version': 1,
        'source_event_ids': [fixture['id'], root['id']], 'source_adapter_id': ADAPTER, 'source_bindings': bindings,
        'observer': OBSERVER, 'question': {'root_event_id': root['id'], 'left_history_id': fixture['id'], 'right_history_id': root['id']}}
    expected = {'defined': True, 'observation': 0, 'admissibility': [True]}
    op = operation({'fixture_sha256': q_sha}, 'actual-n-h-containment', expected, 'actual theta source calculation')
    pc = Precommit014(project=project, obligation_id=oid, obligation_version=1, scope=scope_name,
        native_request=request, source_bindings=bindings, source_family_id=family, native_definition_sha256=ARCHIVE_SHA,
        operation_definition_sha256=op_sha, observer=OBSERVER, test_id='actual-n-h-containment',
        suffix=['native-t15-h.0005-n3,4'], suffix_ordinals=[0], admissibility_guard=[True],
        alternatives=[{'kind': 'ACTUAL_THETA_CONTAINMENT_FORECAST', 'question_sha256': q_sha, 'readout': expected}],
        tested_hypothesis='Source identity n/h cocycle, not autonomous discovery', expected_readout=expected,
        expected_coordinate=[0], proposal_fingerprint=ResearchMoveFingerprint.build(op).digest,
        claim_fingerprint=digest(question), raw_distinction_sha256=q_sha, preview_digest=q_sha,
        purpose='VALIDATE_TRANSFER', law_fingerprint=digest(policy['source_identity']), context_word=[2, 3, 4]).model_dump()
    with connect(db, True) as c:
        TypedCycle._sources_current(c, pc)
        cursor = c.execute('INSERT INTO typed011_precommits(project,request_key,request_sha,digest,payload_json,operation_json,preview_json) VALUES (?,?,?,?,?,?,?)',
            (project, '016:precommit', digest(request), digest(pc), canonical(pc), canonical(op),
             canonical({'preview_digest': q_sha, 'raw_distinction': {'source_question_sha256': q_sha, 'observer': question['observer']}})))
        row = dict(c.execute('SELECT * FROM typed011_precommits WHERE id=?', (cursor.lastrowid,)).fetchone())
        store._audit(c, 'typed011_precommitted', {'precommit_id': row['id'], 'digest': row['digest']})
    linked = TypedCycle(db)._link(row)
    return {'precommit': linked, 'normalization004': checks, 'project': project, 'move_id': linked['move_id'], 'question_sha256': q_sha}


def execute(db, project, move_id, raw):
    assert_isolated(db)
    with connect(db) as c:
        registered = scope(c, project)
        row = c.execute('SELECT p.* FROM typed011_precommits p JOIN typed011_moves m ON m.precommit_id=p.id WHERE m.move_id=? AND p.project=?', (move_id, project)).fetchone()
        activation = c.execute('SELECT * FROM typed011_activations WHERE move_id=?', (move_id,)).fetchone()
        if not row or not activation:
            raise ValueError('NO_BOUND_ACTIVATION')
        pc = json.loads(row['payload_json'])
        TypedCycle._sources_current(c, pc)
        reader = ResearchStore.__new__(ResearchStore)
        reader.path = Path(db)
        if not reader.moves._view(c, reader.moves._row(c, project, move_id))['execution_permission']['allowed']:
            raise ValueError('NO_CURRENT_GRANT')
        if c.execute('SELECT 1 FROM typed011_executions WHERE move_id=?', (move_id,)).fetchone():
            raise ValueError('ALREADY_MEASURED')
        if sha(__file__) != registered['executor_code_sha256']:
            raise ValueError('EXECUTOR_CODE_DRIFT')
        root = json.loads(c.execute('SELECT content FROM events WHERE id=?', (pc['native_request']['question']['root_event_id'],)).fetchone()[0])
        question = question_from(root)
    for name, expected in question['native_file_hashes'].items():
        if sha(Path(raw) / name) != expected:
            raise ValueError('ORIGINAL_SOURCE_DRIFT')
    native = load_native(raw)
    rows = native_rows(native, raw, question['h'], 4)
    count = observe(question, rows)
    observed = {'defined': True, 'observation': count, 'admissibility': [True]}
    outcome = 'SUCCESS' if count == 0 else 'FAILURE'
    artifact = {'precommit_sha256': row['digest'], 'move_id': move_id, 'observed': observed,
        'observed_coordinate': [count], 'outcome': outcome, 'raw_rows': rows,
        'question_sha256': digest(question), 'pre_registration_sha256': question['pre_registration_sha256']}
    path = Path(registered['artifact_directory']) / ('move-' + str(move_id) + '.json')
    with path.open('x') as stream:
        stream.write(canonical(artifact))
    env = {k: pc[k] for k in ('project', 'proposal_fingerprint', 'obligation_id', 'obligation_version', 'scope',
        'source_family_id', 'source_bindings', 'native_definition_sha256', 'operation_definition_sha256', 'observer',
        'test_id', 'suffix', 'suffix_ordinals', 'purpose', 'law_fingerprint', 'context_word')}
    env.update(precommit_id=row['id'], precommit_sha256=row['digest'], move_id=move_id, audit_id=activation['audit_id'],
        activation_operation_id=activation['operation_id'], predictions=pc['alternatives'], observed=observed,
        observed_coordinate=[count], outcome=outcome, executor_id='qa.external.native011/v1',
        executor_code_sha256=sha(__file__), artifact_sha256=sha(path),
        summary='Fresh postactivation original theta n-target containment measurement; not a theorem.',
        reason='Original source calculation at t15 after exact explicit operator activation.')
    envelope = Envelope014.model_validate(env).model_dump()
    content = {'claim_type': 'EXPERIMENT_RESULT', 'statement': env['summary'], 'scope': pc['scope'], 'version': 1,
        'outcome': outcome, 'proof_status': 'unverified', 'measurement_binding': envelope,
        'observation': {'test_id': pc['test_id'], 'readout': observed, 'scope': pc['scope'], 'version': 1, 'observer': OBSERVER}}
    store = ResearchStore(db)
    event = store.record(project, 'experiment' if outcome == 'SUCCESS' else 'counterexample', 'Actual theta n-h measurement',
        canonical(content), 'experiment', parent_id=pc['native_request']['question']['root_event_id'], request_key=project + ':native')
    local = {'artifact_path': str(path), 'artifact_sha256': sha(path), 'envelope_sha256': digest(envelope)}
    with connect(db, True) as c:
        c.execute('INSERT INTO typed011_executions VALUES (?,?,?)', (move_id, event['id'], canonical(local)))
        store._audit(c, 'typed011_executor_receipt', {'move_id': move_id, 'event_id': event['id'], 'digest': digest(local)})
    return {'event_id': event['id'], 'envelope': envelope, 'artifact_path': str(path)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    print(canonical(execute(args.db, **json.loads(sys.stdin.read()))))
