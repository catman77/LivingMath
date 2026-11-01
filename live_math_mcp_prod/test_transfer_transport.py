import asyncio
import json

import pytest

from transfer_model import ENCODING, INPUT_TOKENS, infer, prompt, schema
from transfer_worlds import world


def test_every_frozen_prompt_fits_the_same_input_budget_without_expected_decisions():
    for i in range(9):
        for repeat in (0, 1):
            for time in (0, 1):
                for mode in ('F', 'S'):
                    text = prompt(world(i, repeat), time, mode)
                    assert len(ENCODING.encode(text)) == INPUT_TOKENS
                    assert 'best_action' not in text and 'best_loss' not in text
    assert schema()['additionalProperties'] is False


def test_started_attempt_is_never_overwritten_or_retried(tmp_path):
    path = tmp_path / 'started'
    path.mkdir()
    (path / 'attempt-start.json').write_text('{}')
    with pytest.raises(FileExistsError):
        asyncio.run(infer(path, 'unused', asyncio.Semaphore(1)))
    assert (path / 'attempt-start.json').read_text() == '{}'
