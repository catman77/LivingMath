import json

from causal_recover import prior_attempt, recorded_attempt


def test_queued_prompt_can_run_but_started_inference_cannot_be_retried(tmp_path):
    (tmp_path / 'prompt.txt').write_text('fixed prompt')
    assert prior_attempt(tmp_path) is None
    (tmp_path / 'events.jsonl').write_text('{"type":"thread.started"}\n')
    receipt = prior_attempt(tmp_path)
    assert receipt['outcome'] == 'TRANSPORT_FAILURE'
    assert receipt['metadata']['wall_seconds'] is None


def test_completed_receipt_is_preserved_byte_semantics(tmp_path):
    receipt = {'outcome': 'OK', 'metadata': {'wall_seconds': 3}, 'output': {'action': 'unchanged'}}
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    assert prior_attempt(tmp_path) == receipt


def test_continuation_cannot_repeat_an_attempt_from_an_earlier_transport_session(tmp_path):
    old = tmp_path / 'transport-continuation' / 'w01-r0' / 'models' / 'w01-r0-M2-t1'
    old.mkdir(parents=True)
    (old / 'events.jsonl').write_text('{"type":"turn.started"}\n')
    assert recorded_attempt(tmp_path, 'w01-r0-M2-t1')['outcome'] == 'TRANSPORT_FAILURE'
