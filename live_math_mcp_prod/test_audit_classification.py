"""Failure classification must use either kind or status without changing evidence."""
import pytest

from research_store import ResearchStore


@pytest.mark.parametrize('kind,status,is_failure', [
    ('failure', 'experiment', True),
    ('failed_check', 'experiment', True),
    ('counterexample', 'experiment', True),
    ('rca', 'experiment', True),
    ('interpretation', 'refuted', True),
    ('interpretation', 'counterexample', True),
    ('counterexample', 'counterexample', True),
    ('interpretation', 'hypothesis', False),
    ('experiment', 'experiment', False),
    ('attention', 'observation', False),
])
def test_failure_classification_preserves_ledger(tmp_path, kind, status, is_failure):
    store = ResearchStore(tmp_path / 'research.sqlite3')
    event = store.record('CLASSIFICATION', kind, 'specific check', 'recorded result',
                         status=status, evidence='test witness')
    store.record('CLASSIFICATION', 'attention', 'next check', 'recorded reason',
                 status='observation', parent_id=event['id'])
    before_events = store.events('CLASSIFICATION')
    before_audit = store.verify_audit()

    report = store.audit('CLASSIFICATION', 'a proposed next check', 'test witness')
    failures = [candidate for candidate in store.focus_candidates('CLASSIFICATION')
                if candidate['target'] == 'failure']

    assert ('No RCA/counterexample in recorded history' not in report['warnings']) is is_failure
    assert [candidate['event_id'] for candidate in failures] == ([event['id']] if is_failure else [])
    assert report['verdict'] == 'needs_independent_check'
    assert store.events('CLASSIFICATION') == before_events
    assert store.verify_audit() == before_audit
