"""Lifecycle authorization regressions using the actual RH history fixture."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from frontier import PRESERVATION_PROPERTIES, SCHEMA_SQL as FRONTIER_SCHEMA
from research_store import ResearchStore
from test_frontier import store, move, HISTORY


def proposal(store, **kwargs):
    request = move(store, **kwargs)
    active = store.frontier.history(request['active_frontier_id'])[-1]
    return {**request, 'scope': active['scope'], 'active_frontier_version': active['version']}


def statuses(record):
    return [entry['status'] for entry in record['history']]


def mismatch(store):
    request = proposal(store)
    contract = store.frontier.transformation_contract('RH', 'other source', request['proposed_operation'],
        request['target_representation'], {prop: {'statement': 'Check ' + prop} for prop in PRESERVATION_PROPERTIES}, [15])
    request['transformation_contract_id'] = contract['id']
    return request


def test_complete_cycle_requires_separate_activation(store):
    request = proposal(store)
    record = store.frontier.record_move('RH', request, 'cycle-propose')
    assert statuses(record) == ['PROPOSED', 'AUDITED']
    assert record['status'] == 'AUDITED'
    assert record['audit']['verdict'] == 'EXPERIMENT_ALLOWED'
    assert not record['execution_permission']['allowed']
    allowed = store.moves.transition('RH', record['id'], 'activate_experiment', 'cycle-activate')
    assert allowed['execution_permission']['allowed']
    assert allowed['execution_permission']['scope'] == request['scope']
    assert not allowed['execution_permission']['transformation_allowed']
    assert not allowed['execution_permission']['proof_allowed']
    completed = store.moves.transition('RH', record['id'], 'complete', 'cycle-complete',
        evidence_refs=['event:15','artifact:protocol-test'], reason='The protocol regression finished; no scientific claim.',
        result={'outcome':'SUCCESS','summary':'Protocol regression finished; no mathematical verification.'})
    assert statuses(completed) == ['PROPOSED', 'AUDITED', 'EXPERIMENT_ALLOWED', 'COMPLETED']
    assert not completed['execution_permission']['allowed']
    assert completed['proof_status'] == 'unverified'


def test_contract_mismatch_is_recorded_rejected_and_never_activated(store):
    record = store.frontier.record_move('RH', mismatch(store), 'mismatch-propose')
    assert statuses(record) == ['PROPOSED', 'AUDITED', 'REJECTED']
    assert 'TRANSFORMATION_CONTRACT_MISMATCH' in record['audit']['warnings']
    assert not record['execution_permission']['allowed']
    assert all(not item['decision'].get('allowed', False) for item in record['history'])
    with pytest.raises(ValueError, match='audit|REJECTED'):
        store.moves.transition('RH', record['id'], 'activate_experiment', 'mismatch-activate')


@pytest.mark.parametrize('mechanism,parent,intent', [('X4',9,'experiment'), ('erase_point_loop',13,'transformation')])
def test_hard_audit_failures_never_issue_permissions(store, mechanism, parent, intent):
    record = store.frontier.record_move('RH', proposal(store, mechanism=mechanism, parent=parent, intent=intent), 'blocked-propose')
    assert record['status'] == 'REJECTED'
    assert not record['execution_permission']['allowed']


def test_structural_replay_and_cosmetic_rename_are_idempotent_under_concurrency(store):
    request = mismatch(store)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: store.frontier.record_move('RH', request, 'same-request'), range(8)))
    assert len({item['id'] for item in results}) == 1
    renamed = copy.deepcopy(request)
    renamed['proposal'] = 'New marketing name'
    renamed['proposed_operation']['display_name'] = 'Completely new experiment'
    renamed['proposed_operation']['mechanism'] = 'renamed_mechanism'
    repeated = store.frontier.record_move('RH', renamed, 'renamed-request')
    assert repeated['id'] == results[0]['id'] and repeated['idempotent']
    assert repeated['status'] == 'REJECTED'
    assert statuses(repeated) == ['PROPOSED', 'AUDITED', 'REJECTED']


def test_request_key_and_identity_conflicts_fail_closed(store):
    request = proposal(store)
    store.frontier.record_move('RH', request, 'binding')
    changed = copy.deepcopy(request)
    changed['target_representation'] = 'other source'
    with pytest.raises(ValueError, match='key|identity'):
        store.frontier.record_move('RH', changed, 'binding')
    with pytest.raises(ValueError, match='identity'):
        store.frontier.record_move('RH', changed, 'different-key')
    with pytest.raises(ValueError, match='request_key'):
        store.frontier.record_move('RH', request, '')


def test_frontier_change_revokes_and_requires_new_audit(store):
    request = proposal(store)
    record = store.frontier.record_move('RH', request, 'initial')
    store.moves.transition('RH', record['id'], 'activate_experiment', 'activate')
    store.frontier.update(request['active_frontier_id'], 1, {'status':'TESTING'})
    stale = store.moves.inspect('RH', record['id'])
    assert stale['status'] == 'REQUIRES_REVIEW'
    assert not stale['execution_permission']['allowed']
    with pytest.raises(ValueError):
        store.moves.transition('RH', record['id'], 'activate_experiment', 'stale-activate')
    with pytest.raises(ValueError):
        store.moves.transition('RH', record['id'], 'complete', 'stale-complete', ['event:15'], 'Done')
    audited = store.moves.audit('RH', record['id'], 'new-audit')
    assert audited['status'] == 'AUDITED'
    assert not audited['execution_permission']['allowed']
    allowed = store.moves.transition('RH', record['id'], 'activate_experiment', 'new-activate')
    assert allowed['execution_permission']['allowed']
    assert allowed['execution_permission']['frontier_versions'][str(request['active_frontier_id'])] == 2


def test_closed_frontier_requires_a_new_reopened_version(store):
    request = proposal(store)
    record = store.frontier.record_move('RH', request, 'closed-proposal')
    store.moves.transition('RH', record['id'], 'activate_experiment', 'before-close')
    store.frontier.update(request['active_frontier_id'], 1, {'status':'RESOLVED',
        'closure_reason':'Protocol closure, no proof.', 'evidence_refs':['event:15'], 'reopen_conditions':['New evidence.']})
    assert not store.moves.inspect('RH', record['id'])['execution_permission']['allowed']
    assert store.moves.audit('RH', record['id'], 'closed-audit')['status'] == 'REJECTED'
    with pytest.raises(ValueError):
        store.moves.transition('RH', record['id'], 'activate_experiment', 'closed-activate')
    store.frontier.update(request['active_frontier_id'], 2, {'status':'OPEN', 'source_event_ids':[15,16]}, 'New evidence in event #16.')
    assert store.moves.audit('RH', record['id'], 'reopen-audit')['status'] == 'REQUIRES_REVIEW'


def test_project_references_and_lifecycle_calls_are_isolated(store):
    request = proposal(store)
    record = store.frontier.record_move('RH', request, 'own')
    for operation in [lambda: store.moves.inspect('OTHER', record['id']),
                      lambda: store.moves.audit('OTHER', record['id'], 'foreign-audit'),
                      lambda: store.moves.transition('OTHER', record['id'], 'abandon', 'foreign-update')]:
        with pytest.raises(ValueError): operation()
    for field,value in [('active_frontier_id',store.frontier.create('OTHER','Other','Other',[])['id']),
                        ('parent_event_ids',[2]), ('evidence_refs',['event:2'])]:
        changed = {**request, field:value}
        with pytest.raises(ValueError): store.frontier.record_move('RH', changed, 'foreign-'+field)
    with pytest.raises(ValueError):
        store.moves.transition('RH',record['id'],'verified','illegal-verify')
    assert store.moves.inspect('RH',record['id'])['proof_status']=='unverified'


def test_completion_and_abandonment_do_not_verify_or_reactivate(store):
    record = store.frontier.record_move('RH',proposal(store),'abandon-proposal')
    abandoned=store.moves.transition('RH',record['id'],'abandon','abandon-key',reason='Withdrawn')
    assert abandoned['status']=='ABANDONED' and not abandoned['execution_permission']['allowed']
    with pytest.raises(ValueError): store.moves.audit('RH',record['id'],'abandoned-audit')
    with pytest.raises(ValueError): store.moves.transition('RH',record['id'],'complete','bad-complete')
    with pytest.raises(ValueError): store.frontier.record_move('RH',{**proposal(store),'status':'verified'},'bad-status')


def test_status_and_audit_history_are_append_only(store):
    record=store.frontier.record_move('RH',proposal(store),'immutable')
    with store._connect() as connection:
        assert connection.execute('SELECT count(*) FROM research_move_audits WHERE move_id=?',(record['id'],)).fetchone()[0]==1
        for table in ('research_move_audits','research_move_status_history'):
            for sql in ('UPDATE '+table+' SET move_id=move_id','DELETE FROM '+table):
                with pytest.raises(sqlite3.IntegrityError): connection.execute(sql)
    assert store.verify_audit()['ok']


def test_v3_migration_preserves_all_original_rows_and_never_infers_a_grant(store, tmp_path):
    path = tmp_path / 'v04.sqlite3'
    with store._connect() as connection:
        names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                 if not r[0].startswith('research_move_') and r[0]!='adverse_evidence_reviews']
        snapshot = {name: [dict(row) for row in connection.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in names}
    with sqlite3.connect(path) as connection:
        connection.executescript(';\n'.join(HISTORY['schema_sql'])+';'+FRONTIER_SCHEMA)
        for table, rows in snapshot.items():
            for row in rows:
                connection.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')', tuple(row.values()))
        payload = {**proposal(store), 'audit':{'warnings':['TRANSFORMATION_CONTRACT_MISMATCH'],
            'findings':[], 'verdict':'REQUIRES_SEMANTIC_REVIEW','proof_status':'unverified'}}
        connection.execute('INSERT INTO research_moves(project,fingerprint,payload_json,created_at) VALUES (?,?,?,0)',
            ('RH','legacy-fingerprint',json.dumps(payload)))
        connection.execute('PRAGMA user_version=3')
        connection.row_factory=sqlite3.Row
        before={name:[dict(row) for row in connection.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in names}
    migrated=ResearchStore(path)
    with migrated._connect() as connection:
        for table,rows in before.items():
            actual=[dict(row) for row in connection.execute('SELECT * FROM '+table+' ORDER BY rowid')]
            assert (actual[:len(rows)] if table=='operations' else actual)==rows
        assert connection.execute('PRAGMA user_version').fetchone()[0]==5
    records=[migrated.moves.inspect('RH',row['id']) for row in before['research_moves']]
    assert all(not record['execution_permission']['allowed'] for record in records)
    assert records[-1]['status']=='REJECTED'
    assert migrated.verify_audit()['ok']
    before_repeat=migrated.verify_audit()
    ResearchStore(path)
    assert migrated.verify_audit()==before_repeat


def test_changed_scope_cannot_borrow_a_known_experiment_permission(store):
    request=proposal(store)
    request['scope']='A broader universal claim'
    record=store.frontier.record_move('RH',request,'expanded-scope')
    assert record['status']=='REQUIRES_REVIEW'
    assert not record['execution_permission']['allowed']
    with pytest.raises(ValueError): store.moves.transition('RH',record['id'],'activate_experiment','expanded-activate')


def test_replayed_grant_request_returns_current_revoked_permission(store):
    request=proposal(store)
    record=store.frontier.record_move('RH',request,'replayed-propose')
    store.moves.transition('RH',record['id'],'activate_experiment','replayed-activate')
    store.frontier.update(request['active_frontier_id'],1,{'status':'TESTING'})
    repeat=store.moves.transition('RH',record['id'],'activate_experiment','replayed-activate')
    assert repeat['idempotent'] and not repeat['execution_permission']['allowed']
    assert repeat['status']=='REQUIRES_REVIEW'


def test_related_preservation_obligation_change_also_invalidates_permission(store):
    request=proposal(store)
    contract=store.frontier.transformation_contract('RH',request['source_representation'],request['proposed_operation'],
        request['target_representation'],{prop:{'statement':'Check '+prop} for prop in PRESERVATION_PROPERTIES},[15])
    request['transformation_contract_id']=contract['id']
    record=store.frontier.record_move('RH',request,'related-propose')
    allowed=store.moves.transition('RH',record['id'],'activate_experiment','related-activate')
    assert allowed['execution_permission']['allowed']
    store.frontier.update(contract['obligation_ids'][0],1,{'status':'TESTING'})
    current=store.moves.inspect('RH',record['id'])
    assert current['status']=='REQUIRES_REVIEW' and not current['execution_permission']['allowed']


def test_admin_backup_preserves_old_schema_without_implicit_migration(tmp_path):
    source=tmp_path/'before.sqlite3'
    backup=tmp_path/'backup.sqlite3'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE marker(value TEXT)')
        connection.execute("INSERT INTO marker VALUES ('original')")
        connection.execute('PRAGMA user_version=3')
    subprocess.run([sys.executable,str(Path(__file__).with_name('admin.py')),'--db',str(source),'backup',str(backup)],check=True,capture_output=True)
    for path in (source,backup):
        with sqlite3.connect(path) as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0]==3
            assert connection.execute('SELECT value FROM marker').fetchone()[0]=='original'
            assert not connection.execute("SELECT name FROM sqlite_master WHERE name='research_move_audits'").fetchone()
