import asyncio
import signal

import pytest

import causal_model


@pytest.mark.parametrize('missing_on', [signal.SIGTERM, signal.SIGKILL])
def test_deadline_remains_transport_failure_if_process_group_already_exited(tmp_path, monkeypatch, missing_on):
    class Input:
        def close(self):
            pass

    class Process:
        pid = 999999
        returncode = 0
        stdin = Input()
        waits = 0

        async def communicate(self, data):
            raise asyncio.TimeoutError()

        async def wait(self):
            self.waits += 1
            if missing_on == signal.SIGKILL and self.waits == 1:
                raise asyncio.TimeoutError()
            return 0

    async def spawn(*args, **kwargs):
        return Process()

    def kill_group(pid, sig):
        if sig == missing_on:
            raise ProcessLookupError('Already exited between timeout and signalling')

    monkeypatch.setattr(causal_model.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(causal_model.os, 'killpg', kill_group)
    result = asyncio.run(causal_model.infer(tmp_path / 'case', 'fixed test prompt', asyncio.Semaphore(1)))
    assert result['outcome'] == 'TRANSPORT_FAILURE'
    assert result['metadata']['timed_out'] is True
