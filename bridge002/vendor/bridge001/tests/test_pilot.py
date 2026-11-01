import json

from bridge.journal import verify
from bridge.pilot import frozen_inputs, run_local
from bridge.canonical import read_json
from bridge.intake import ROOT


def test_frozen_ten_tasks_and_no_fabricated_baseline():
    frozen_inputs()
    tasks = read_json(ROOT / 'eval/tasks.json')
    assert len(tasks) == 10
    assert [sum(t['group'] == g for t in tasks) for g in ('mathematical','linguistic','image_practical')] == [4,3,3]
    assert all(t['author_confirmation'] == 'AUTHOR_REVIEW_NOT_AVAILABLE' for t in tasks)
    assert all(all('NOT_TESTED' in s for s in t['arms'].values()) for t in tasks)


def test_whole_local_cycle_reproducible(tmp_path):
    first = run_local(tmp_path / 'first');second = run_local(tmp_path / 'second')
    assert first['oracles'] == second['oracles']
    assert first['REAL_SUTI_INTEGRATION'] == 'NOT_TESTED'
    assert first['BASELINE_ADVANTAGE'] == 'NOT_ESTABLISHED'
    assert first['cost']['LLM_calls'] == 0
    for name in ['branches.json','negative-controls.json','tasks-local.json','journal.jsonl']:
        assert (tmp_path/'first'/name).read_bytes() == (tmp_path/'second'/name).read_bytes()
    rows = [json.loads(l) for l in (tmp_path/'first/journal.jsonl').read_text().splitlines()]
    assert verify(rows)
