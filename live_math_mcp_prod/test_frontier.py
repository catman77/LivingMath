"""v0.4 T1–T7 regressions replay actual, hash-identified historical RH records."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sqlite3

import pytest

from frontier import PRESERVATION_PROPERTIES, ResearchMoveFingerprint
from research_store import ResearchStore


DATA = Path(__file__).parent / 'testdata'
HISTORY = json.loads((DATA / 'rh_history_v031.json').read_text())
BLUEPRINT = json.loads((DATA / 'rh_frontier_seed.json').read_text())


def historical_database(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(';\n'.join(HISTORY['schema_sql']) + ';')
        for table, rows in HISTORY['tables'].items():
            for row in rows:
                columns = ','.join('"' + key + '"' for key in row)
                placeholders = ','.join('?' for _ in row)
                connection.execute('INSERT INTO "' + table + '" (' + columns + ') VALUES (' + placeholders + ')',
                                   tuple(row.values()))
        connection.execute('PRAGMA user_version=2')


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'historical.sqlite3'
    historical_database(path)
    store = ResearchStore(path)
    store.frontier.import_history(BLUEPRINT, 'regression replay')
    return store


def move(store, mechanism='theta_edge_address_match', parent=15, intent='experiment'):
    frontier = store.frontier.inspect('RH', include_closed=True)
    active = next(item for item in frontier['obligations'] if item['source_event_ids'] == [15])
    return {'active_frontier_id': active['id'], 'parent_event_ids': [parent],
            'proposed_operation': {'mechanism': mechanism, 'intent': intent,
                'premises': ['actual T49/T54 theta edges'],
                'mathematical_properties': ['source_address and origin_id matching'],
                'testable_consequence': 'detect unmatched edges before comparing contributions',
                'required_evidence': ['source-address matching report']},
            'source_representation': 'actual_theta_source_edges',
            'target_representation': 'actual_theta_source_edges',
            'verification_plan': {'method': 'compare source_address and origin_id',
                                  'failure_condition': 'any unmatched source edge'}}


def test_t1_archival_x4_reentry_is_obsolete(store):
    request = move(store, mechanism='X4', parent=9)
    report = store.audit('RH', 'Return to the X4 branch', **request)
    assert report['classification'] == 'OBSOLETE_FRONTIER'
    assert report['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'
    finding = next(row for row in report['findings'] if row['code'] == 'OBSOLETE_FRONTIER')
    assert finding['source_event_ids'] == [9]
    assert finding['reopen_conditions']


def test_t2_cosmetic_route_length_rename_does_not_add_a_distinction(store):
    request = move(store, parent=14)
    request['proposed_operation'] = copy.deepcopy(BLUEPRINT['moves'][0]['proposed_operation'])
    request['proposed_operation']['display_name'] = 'A revolutionary route extent'
    request['proposed_operation']['mechanism'] = 'renamed_extent'
    request['proposed_operation']['mathematical_properties'][0] = 'path length'
    report = store.audit('RH', 'Rename the length', **request)
    assert report['classification'] == 'NO_NEW_DISTINCTION'
    assert any(item['source_event_ids'] == [14] for item in report['findings'])


def test_t3_case_c_point_erasure_does_not_establish_germ_preservation(store):
    request = move(store, mechanism='erase_point_loop', parent=13, intent='transformation')
    request['target_representation'] = 'theta_edges_after_pointwise_loop_erasure'
    request['preserved_properties'] = {'point_value': {'claim': 'preserved', 'evidence_refs': ['event:13']}}
    report = store.audit('RH', 'Erase the CASE-C point loop', **request)
    assert report['classification'] == 'UNPROVEN_SEMANTIC_PRESERVATION'
    assert any(item['code'] == 'UNPROVEN_SEMANTIC_PRESERVATION' and item['source_event_ids'] == [13]
               for item in report['findings'])
    assert not any(item['established'] for item in report['preservation_checks'])


def test_t4_source_matching_is_an_experiment_and_never_a_proof(store):
    request = move(store)
    report = store.audit('RH', 'Match the theta source edges', **request)
    assert report['classification'] == 'ACTIVE_CONTINUATION'
    assert report['verdict'] == 'EXPERIMENT_ALLOWED'
    assert report['proof_status'] == 'unverified'
    request['proposed_operation']['intent'] = 'proof'
    assert store.audit('RH', 'Claim a proof', **request)['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'


def test_t5_identical_records_are_idempotent_without_a_request_key(store):
    before = store.health()
    arguments = ('RH', 'experiment', 'idempotence check', 'same exact record')
    with ThreadPoolExecutor(max_workers=6) as executor:
        records = list(executor.map(lambda _: store.record(*arguments), range(12)))
    assert len({row['id'] for row in records}) == 1
    assert store.health()['event_count'] == before['event_count'] + 1
    event = HISTORY['events'][0]
    duplicate = store.record(**{key: event[key] for key in
        ('project', 'kind', 'focus', 'content', 'status', 'evidence', 'parent_id')})
    assert duplicate['id'] == event['id'] and duplicate['idempotent']


def test_t6_migration_preserves_every_legacy_row_and_hash(tmp_path):
    path = tmp_path / 'real-history.sqlite3'
    historical_database(path)
    store = ResearchStore(path)
    with store._connect() as connection:
        for table, rows in HISTORY['tables'].items():
            actual = [dict(row) for row in connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]
            assert actual == rows
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 5
    assert store.verify_audit()['ok']
    last_hash = store.verify_audit()['last_hash']
    store.frontier.import_history(BLUEPRINT, 'regression replay')
    assert store.verify_audit()['ok']
    with store._connect() as connection:
        prefix = [dict(row) for row in connection.execute('SELECT * FROM operations ORDER BY id LIMIT 16')]
        assert prefix == HISTORY['operations']
        assert connection.execute('SELECT previous_hash FROM operations WHERE id=17').fetchone()[0] == last_hash
        assert connection.execute('SELECT count(*) FROM events').fetchone()[0] == 16


def test_t7_insufficient_evidence_has_no_invented_conclusion(store):
    report = store.audit('RH', 'Some promising idea', proposed_operation={})
    assert report['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'
    assert report['proof_status'] == 'unverified'
    assert any(item['missing_data'] for item in report['findings'])
    assert not report['formal_checks']['mathematical_equivalence_decided']


def test_obligation_versions_are_immutable_and_reopening_is_explicit(store):
    obligation = store.frontier.create('RH', 'Check a scoped statement', 'finite source', [15])
    closed = store.frontier.update(obligation['id'], 1, {'status': 'RESOLVED',
        'closure_reason': 'Recorded scoped test outcome, not a mathematical proof.',
        'evidence_refs': ['event:15'], 'reopen_conditions': ['New source-linked evidence.']})
    assert closed['version'] == 2
    with pytest.raises(ValueError):
        store.frontier.update(obligation['id'], 2, {'status': 'OPEN'})
    with pytest.raises(ValueError):
        store.frontier.update(obligation['id'], 1, {'status': 'TESTING'})
    reopened = store.frontier.update(obligation['id'], 2, {'status': 'OPEN', 'source_event_ids': [15, 16]},
                                     reopen_reason='Event #16 supplies a new adversarial test.')
    assert reopened['version'] == 3 and reopened['status'] == 'OPEN'
    assert [item['status'] for item in store.frontier.history(obligation['id'])] == ['OPEN', 'RESOLVED', 'OPEN']
    with store._connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE research_obligation_versions SET status='OPEN' WHERE obligation_id=?", (obligation['id'],))


def test_project_boundaries_and_closure_requirements(store):
    with pytest.raises(ValueError):
        store.frontier.create('OTHER', 'Claim', 'scope', [15])
    with pytest.raises(ValueError):
        store.frontier.create('RH', 'Claim', 'scope', [15], status='RESOLVED')
    request = move(store)
    request['parent_event_ids'] = [2]
    with pytest.raises(ValueError):
        store.audit('RH', 'Foreign input', **request)


def test_transformation_contract_creates_five_separate_open_obligations(store):
    preservation = {prop: {'statement': 'Check ' + prop, 'evidence_refs': ['event:13']}
                    for prop in PRESERVATION_PROPERTIES}
    contract = store.frontier.transformation_contract('RH', 'original edges', {'mechanism': 'candidate transform'},
                                                      'candidate edges', preservation, [13])
    assert len(contract['obligation_ids']) == 5 and contract['verification_status'] == 'UNVERIFIED'
    for obligation_id in contract['obligation_ids']:
        assert store.frontier.history(obligation_id)[0]['status'] == 'OPEN'


def test_fingerprint_does_not_solve_formula_equivalence_or_erase_case():
    left = copy.deepcopy(BLUEPRINT['moves'][0]['proposed_operation'])
    right = copy.deepcopy(left)
    left['premises'] = ['X = 1']
    right['premises'] = ['x = 1']
    assert ResearchMoveFingerprint.build(left).digest != ResearchMoveFingerprint.build(right).digest


def test_seed_is_idempotent_and_guards_original_source_content(store):
    before = store.verify_audit()
    store.frontier.import_history(BLUEPRINT, 'another replay')
    assert store.verify_audit() == before
    changed = copy.deepcopy(BLUEPRINT)
    changed['import_key'] += '-altered'
    changed['sources'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        store.frontier.import_history(changed, 'regression replay')


def test_known_experiment_name_does_not_bypass_source_scope(store):
    request = move(store, parent=9)
    request['source_representation'] = request['target_representation'] = 'archival_x4_toy'
    result = store.audit('RH', 'Borrow a permitted experiment name', **request)
    assert result['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'
    assert 'EXPERIMENT_SCOPE_REQUIRES_REVIEW' in result['warnings']


def test_new_testable_hypothesis_is_distinguished_without_approving_novelty(store):
    request = move(store, mechanism='unreviewed_source_operation')
    report = store.audit('RH', 'A newly specified hypothesis', **request)
    assert report['classification'] == 'NEW_TESTABLE_HYPOTHESIS'
    assert report['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'


def test_a_closed_obligation_cannot_be_reopened_by_editing_its_old_version(store):
    original = next(item for item in store.frontier.inspect('RH', True)['obligations']
                    if item['source_event_ids'] == [9])
    opened = store.frontier.update(original['id'], 1,
        {'status': 'OPEN', 'source_event_ids': [9, 15], 'evidence_refs': ['event:9', 'event:15']},
        reopen_reason='Review whether the current source provides a genuine new bridge.')
    request = move(store, mechanism='X4', parent=15)
    request['active_frontier_id'] = opened['id']
    report = store.audit('RH', 'Reopened research request', **request)
    assert 'REOPEN_REQUIRES_SEMANTIC_REVIEW' in report['warnings']
    assert 'OBSOLETE_FRONTIER' not in report['warnings']
    assert store.frontier.history(opened['id'])[0]['status'] == 'SUPERSEDED'


def test_blocked_frontier_and_declared_preservation_are_not_approved(store):
    active = next(item for item in store.frontier.inspect('RH')['obligations'] if item['source_event_ids'] == [15])
    store.frontier.update(active['id'], 1, {'status': 'BLOCKED', 'closure_reason': 'The source dataset is unavailable.'})
    report = store.audit('RH', 'A blocked experiment', **move(store))
    assert report['verdict'] == 'REQUIRES_SEMANTIC_REVIEW'
    assert 'BLOCKED_FRONTIER' in report['warnings']


def test_recorded_move_keeps_its_history_based_audit(store):
    request = move(store, mechanism='X4', parent=9)
    active = store.frontier.history(request['active_frontier_id'])[-1]
    request.update(scope=active['scope'], active_frontier_version=active['version'])
    record = store.frontier.record_move('RH', request, 'historical-audit')
    assert record['audit']['classification'] == 'OBSOLETE_FRONTIER'
    assert record['audit']['proof_status'] == 'unverified'
    with store._connect() as connection:
        payload = json.loads(connection.execute('SELECT payload_json FROM research_moves WHERE id=?', (record['id'],)).fetchone()[0])
        assert 'audit' not in payload
        audit = json.loads(connection.execute('SELECT report_json FROM research_move_audits WHERE move_id=?', (record['id'],)).fetchone()[0])
        assert audit == record['audit']
