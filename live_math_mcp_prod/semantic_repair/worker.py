"""Isolated query-free compiler or raw observer, using the inherited finite bounds."""
import argparse
import asyncio
import json
import os
import resource
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def call(mode: str, payload: dict, *, context=None) -> dict:
    if mode not in {'observe', 'compile', 'alignment','artifact_compile','artifact_check'}:
        raise ValueError('INSTALLED_MODE_REQUIRED')
    if mode.startswith('artifact_'):
        if context is None:raise ValueError('SERVER_SOURCE_CONTEXT_REQUIRED')
        context.require(payload['binding']['project'],payload['premises'])
        payload={**payload,'server_source_context':context.transport(payload['premises'])}
        if mode == 'artifact_check' and payload['model']['observer']['kind'] == 'SOURCE_SEMANTICS012':
            from davcore.ast import digest
            # The full source descriptors already occur in premises. Rebuild M
            # inside the worker and compare its exact fingerprint, instead of
            # transmitting every annotation twice through the fixed64K pipe.
            payload['model'] = {'transport': 'frozen-model012/1',
                'compiled_hash': payload['model']['compiled_hash'], 'model_sha256': digest(payload['model'])}
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    if len(raw) > 64000:
        raise ValueError('WORKER_INPUT_BOUND')
    p = await asyncio.create_subprocess_exec(sys.executable, '-I', '-B', str(Path(__file__)), mode,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd='/tmp', env={'PATH': os.defpath, 'LANG': 'C.UTF-8'})
    try:
        data, error = await asyncio.wait_for(p.communicate(raw), timeout=6)
        if p.returncode or len(data) > 256000:
            raise ValueError('WORKER_FAILED:' + error.decode(errors='replace')[-500:])
        result = json.loads(data)
        if result['isolation']['query_modules_loaded']:
            raise ValueError('QUERY_COMPILER_FIREWALL_BREACH')
        return result
    finally:
        if p.returncode is None:
            p.kill(); await p.wait()


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['observe', 'compile', 'alignment','artifact_compile','artifact_check']); args = p.parse_args()
    data = sys.stdin.buffer.read(64001)
    if len(data) > 64000:
        raise ValueError('WORKER_INPUT_BOUND')
    invoke: Callable[[], dict[str, Any]]
    if args.mode.startswith('artifact_'):
        from semantic_repair import (
            realization,  # preload before IO denial
            realization011,  # preload before IO denial
            realization012,  # noqa: F401 - preload before IO denial
        )
        from semantic_repair.compiler import compile_model
        from semantic_repair.context009 import from_private_channel
        from semantic_repair.contract import CompilerRequest
        value=json.loads(data)
        required={'premises','binding','profile','server_source_context'}
        if args.mode=='artifact_check':required.add('model')
        if set(value)!=required:raise ValueError('STRICT_SERVER_WORKER_ENVELOPE_REQUIRED')
        context=from_private_channel(value['server_source_context'])
        request=CompilerRequest.model_validate({k:value[k] for k in ('premises','binding','profile')})
        if args.mode=='artifact_compile':
            invoke=lambda:compile_model(value['premises'],request.binding.model_dump(),profile=request.profile,context=context)
        else:
            from davcore import adapters

            from semantic_repair import (
                check011,  # noqa: F401 - preload before IO denial
                check012,  # noqa: F401 - preload before IO denial
                inference013,  # noqa: F401 - preload fixed observer checker before IO denial
            )
            from semantic_repair.check009 import check_model
            # Freeze the actual checksum before denying file IO. Metadata still
            # binds the installed bytes; the isolated checker cannot read files.
            checksum=adapters.implementation_sha()
            adapters.implementation_sha=lambda:checksum
            def bounded_check():
                model = value['model']
                if model.get('transport') == 'frozen-model012/1':
                    from davcore.ast import digest
                    actual = compile_model(value['premises'], request.binding.model_dump(), profile=request.profile, context=context)
                    expected = {'transport': 'frozen-model012/1', 'compiled_hash': actual['compiled_hash'], 'model_sha256': digest(actual)}
                    if model != expected: raise ValueError('STALE_ARTIFACT_MODEL_CONTRACT')
                    model = actual
                return check_model(value['premises'], request.binding.model_dump(), model, context)
            invoke=bounded_check
    elif args.mode == 'alignment':
        from artifact_genesis.contract import RawPacket

        from semantic_repair.alignment import observe as observe_alignment
        value = json.loads(data)
        if set(value) != {'packet', 'strategy'}:
            raise ValueError('QUERY_FREE_ALIGNMENT_OBSERVER_REQUIRED')
        packet = RawPacket.model_validate(value['packet'])
        strategy = value['strategy']
        invoke = lambda: observe_alignment(packet, strategy=strategy)
    elif args.mode == 'observe':
        from artifact_genesis.contract import RawPacket

        from semantic_repair.observe import observe
        value = json.loads(data)
        if 'packet' in value:
            if set(value) != {'packet', 'strategy'}:
                raise ValueError('UNEXPECTED_OBSERVER_INPUT')
            raw = RawPacket.model_validate(value['packet'])
            strategy = value['strategy']
            if strategy in {'artifact009/1','artifact009-middle/1'}:
                from semantic_repair.observe009 import observe as observe_scoped
            elif strategy in {'typed008/1', 'typed008-middle/1'}:
                from semantic_repair.observe008 import observe as observe_scoped
            else:
                from semantic_repair.observe005 import observe as observe_scoped
            invoke = lambda: observe_scoped(raw, strategy=strategy)
        else:
            raw = RawPacket.model_validate(value)
            invoke = lambda: observe(raw)
    else:
        from semantic_repair import (
            realization,  # noqa: F401 - preload before isolated IO denial
            realization011,  # noqa: F401 - no lazy IO in compiler
        )
        from semantic_repair.compiler import compile_model
        from semantic_repair.contract import CompilerRequest
        request = CompilerRequest.model_validate_json(data)
        invoke = lambda: compile_model([x.model_dump(exclude_unset=True) for x in request.premises], request.binding.model_dump(), profile=request.profile)
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def deny(event, args):
        if event in {'open', 'os.listdir', 'os.scandir', 'subprocess.Popen', 'os.system',
                     'ctypes.dlopen', 'os.fork', 'os.exec', 'os.posix_spawn'} or event.startswith('socket.'):
            raise PermissionError('ISOLATED_IO_DENIED:' + event)
    sys.addaudithook(deny)
    probes = {}
    def probe_file():
        with open('/etc/hostname') as stream:
            return stream.read(1)
    attempts: list[tuple[str, Callable[[], Any]]] = [('file', probe_file), ('socket', socket.socket)]
    for name, fn in attempts:
        try: fn()
        except PermissionError: probes[name] = 'DENIED'
        else: raise RuntimeError('UNENFORCED_IO_BOUNDARY')
    result = invoke()
    result['isolation'] = {'probes': probes, 'mode': args.mode,
        'query_modules_loaded': [m for m in ['semantic_repair.search', 'semantic_repair.query', 'semantic_repair.experiment'] if m in sys.modules]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
