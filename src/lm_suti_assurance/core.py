"""Load one byte-pinned core without global bare-module/path collisions.

The private import hook changes module resolution, never source bytes or semantics.
"""
import builtins
import hashlib
import json
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).parent
FROZEN = ROOT / '_frozen'
LOCK = json.loads((ROOT / 'BASELINE_LOCK.json').read_text())
_MODULES = {}
_MUTEX = threading.RLock()
_FILES = {name: FROZEN / 'checker001' / (name + '.py') for name in
          ('contracts', 'checks', 'finite_semantics', 'independent_vm', 'bounded_program', 'ledger')}
_FILES.update({name: FROZEN / (name + '.py') for name in
               ('common002', 'proposal_schema', 'proposal_binder')})


def verify_bytes():
    actual = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in LOCK['source_file_sha256']}
    if actual != LOCK['source_file_sha256']:
        raise RuntimeError('FROZEN_CORE_INTEGRITY_FAILURE')
    return actual


def module(name):
    with _MUTEX:
        if name in _MODULES:
            return _MODULES[name]
        path = _FILES[name]
        qualified = 'lm_suti_assurance._pinned_' + name
        mod = types.ModuleType(qualified)
        mod.__file__ = str(path)
        mod.__package__ = 'lm_suti_assurance'
        private_builtins = dict(vars(builtins))
        original_import = builtins.__import__

        def resolve(imported, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and imported in _FILES:
                return module(imported)
            if imported == 'sys' and name == 'common002':
                proxy = types.ModuleType('sys')
                proxy.__dict__.update(vars(sys))
                proxy.path = list(sys.path)
                return proxy
            return original_import(imported, globals, locals, fromlist, level)

        private_builtins['__import__'] = resolve
        mod.__dict__['__builtins__'] = private_builtins
        _MODULES[name] = mod
        sys.modules[qualified] = mod
        try:
            exec(compile(path.read_bytes(), str(path), 'exec'), mod.__dict__)
        except BaseException:
            _MODULES.pop(name, None)
            sys.modules.pop(qualified, None)
            raise
        return mod


verify_bytes()
contracts = module('contracts')
canonical = contracts.canonical
digest = contracts.digest
byte_digest = contracts.byte_digest
strict_json = contracts.strict_json


def check(candidate, task, sources, engine='direct'):
    verify_bytes()
    return module('checks').check(candidate, task, sources, engine=engine,
                                  expected_verifier_digest=LOCK['verifier_digest'])


def compile_delta(raw, task, sources, runtime):
    verify_bytes()
    return module('proposal_binder').compile_delta(raw, task, sources, runtime)


def identity():
    verify_bytes()
    actual = {'verifier_digest': contracts.verifier_digest(),
              'binder_digest': module('common002').binder_digest()}
    if any(actual[k] != LOCK[k] for k in actual):
        raise RuntimeError('FROZEN_CORE_IDENTITY_MISMATCH')
    return actual
