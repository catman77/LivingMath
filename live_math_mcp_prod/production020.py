"""Owner-authorized deployment adapter for the immutable RC020 payload.

Default release/private guards stay unchanged on disk. This entrypoint needs
an owner-only local authorization; it never registers operator MCP tools.
"""
import argparse
import ctypes
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sqlite3
import stat
import sys
import types

RELEASE = '1.0.0rc1'
CAPSULE_SHA = '5c1e639701758f942908a1e24a5104ad65b206d11726045e294de35d7790fabb'
CORE_MANIFEST_SHA = 'b5b92f6b4f60e7996b1e877fb52323d9528c6da95135954878cde888f1983081'
INSTRUCTION = 'Так накати релиз на работающий сервер'
QA_GATE = "                if project and not project.startswith('LM_QA_'):\n                    raise ValueError('STAGING_QA_NAMESPACE_REQUIRED')\n"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_authorization(path):
    path = Path(path)
    info = path.stat()
    if path.is_symlink() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('DEPLOYMENT_AUTHORIZATION_MUST_BE_OWNER_ONLY')
    plan = json.loads(path.read_text())
    if plan.get('instruction') != INSTRUCTION or plan.get('capsule_sha256') != CAPSULE_SHA:
        raise ValueError('EXPLICIT_PRODUCTION_DEPLOYMENT_AUTHORIZATION_REQUIRED')
    if plan.get('mode') not in ('production', 'rehearsal'):
        raise ValueError('INVALID_DEPLOYMENT_MODE')
    if sha(plan['adapter_path']) != plan['adapter_sha256']:
        raise ValueError('DEPLOYMENT_ADAPTER_DRIFT')
    if sha(plan['core_manifest']) != CORE_MANIFEST_SHA:
        raise ValueError('RELEASE_CORE_MANIFEST_DRIFT')
    code = Path(plan['code']).resolve(strict=True)
    manifest = json.loads(Path(plan['core_manifest']).read_text())
    for name, digest in manifest['files'].items():
        if name.startswith('source/') and sha(code / name[7:]) != digest:
            raise ValueError('RELEASE_CODE_DRIFT:' + name)
    paths = {}
    for role in ('canonical', 'typed', 'oauth'):
        entry = plan['databases'][role]
        actual = Path(entry['path']).resolve(strict=True)
        if actual.stat().st_ino != entry['inode']:
            raise ValueError('DEPLOYMENT_DATABASE_INODE_CHANGED:' + role)
        paths[role] = actual
    if paths['canonical'].samefile(paths['typed']):
        raise ValueError('CANONICAL_TYPED_ISOLATION_REQUIRED')
    if paths['canonical'].parent != paths['oauth'].parent:
        raise ValueError('EXISTING_OAUTH_WORKSPACE_REQUIRED')
    plan['_paths'], plan['_code'] = paths, code
    return plan


def authorize_storage(plan):
    code = str(plan['_code'])
    if code not in sys.path:
        sys.path.insert(0, code)
    import deploy018_storage as storage
    original = getattr(storage, '_production020_original_guard', storage.private_path)
    storage._production020_original_guard = original
    allowed = {plan['_paths']['canonical'], plan['_paths']['typed']}

    def guarded(path):
        candidate = Path(path).resolve()
        live = any(candidate == p.resolve() or candidate.exists() and p.exists() and candidate.samefile(p) for p in storage.LIVE)
        if live:
            if plan['mode'] != 'production' or candidate not in allowed:
                raise ValueError('EXPLICIT_PRODUCTION_PATH_NOT_AUTHORIZED')
            for role in ('canonical', 'typed'):
                if candidate == plan['_paths'][role] and candidate.stat().st_ino != plan['databases'][role]['inode']:
                    raise ValueError('DEPLOYMENT_DATABASE_INODE_CHANGED:' + role)
            return candidate
        return original(candidate)

    storage.private_path = guarded
    return storage


def migrate(plan):
    storage = authorize_storage(plan)
    from engine017_store import install as install017
    from deploy018_authority import install as install018
    install017(plan['_paths']['typed'])
    result = {role: storage.migrate(plan['_paths'][role]) for role in ('canonical', 'typed')}
    install018(plan['_paths']['typed'])
    return result


def template_hooks(plan):
    import deploy018_authority as authority
    original = getattr(authority, '_production020_original_template', authority.template)
    authority._production020_original_template = original
    code = plan['_code']
    raw = (code / 'engine017_server.py').read_text()
    if raw.count(QA_GATE) != 1:
        raise ValueError('PINNED_STAGING_GATE_NOT_RECOGNIZED')
    production_source = raw.replace(QA_GATE, '', 1)
    provenance = {'original_engine017_sha256': sha(code / 'engine017_server.py'),
        'executed_engine017_sha256': hashlib.sha256(production_source.encode()).hexdigest(),
        'change': 'Remove only staging LM_QA_ restriction for ordinary legacy ledger writes; retain typed namespace, measurement/protocol and operator-only checks.',
        'adapter_sha256': plan['adapter_sha256']}

    def release_metadata():
        return {'version': RELEASE, 'runtime_version': '1.0.0b1', 'protocol': 'livingmath-research019/v1',
            'capsule_sha256': CAPSULE_SHA, 'deployment_id': plan['deployment_id'],
            'mode': plan['mode'], 'tool_count': 27, 'owner_authorized': True}

    def http_template():
        module = original('http_server')
        create = module.create_app

        def app(*args, **kwargs):
            factory = module.create_server

            def mounted(*fargs, **fkwargs):
                server = factory(*fargs, **fkwargs)
                server._mcp_server.version = RELEASE
                for name in ('research_contract', 'service_health'):
                    tool = server._tool_manager.get_tool(name)
                    old = tool.fn

                    def wrap(fn, kind):
                        @functools.wraps(fn)
                        def decorated(*a, **kw):
                            result = fn(*a, **kw)
                            result['installed_release'] = release_metadata()
                            if kind == 'research_contract':
                                result['http018']['deployment'] = 'OWNER_AUTHORIZED_EXISTING_SERVER'
                                result['http018']['release_version'] = RELEASE
                                result['engine017']['scope'] = 'Reviewed registered typed sources; legacy research projects retained; operator activation/execution/commit remain local.'
                                result['workflow'] = [
                                    'Read project frontier, source contract and history.',
                                    'Preview/precommit never grant execution.',
                                    'Local owner audits and explicitly activates the bounded experiment.',
                                    'A separate native executor measures; local owner atomically commits signed evidence.',
                                    'Results stay unverified; changed scope/version requires a fresh audit.']
                            else:
                                counts = {}
                                for role in ('canonical', 'typed'):
                                    with sqlite3.connect(plan['_paths'][role].as_uri() + '?mode=ro', uri=True) as c:
                                        counts[role] = {'immutable_018_triggers': c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'lm018_%'").fetchone()[0],
                                            'events': c.execute('SELECT count(*) FROM events').fetchone()[0]}
                                result['deployed_storage'] = counts
                            return result
                        return decorated
                    tool.fn = wrap(old, name)
                return server
            module.create_server = mounted
            return create(*args, **kwargs)
        module.create_app = app
        return module

    def template(name):
        if name == 'engine017_server':
            module = types.ModuleType('_production020_engine017')
            module.__file__ = str(code / 'engine017_server.py')
            exec(compile(production_source, module.__file__, 'exec'), module.__dict__)
            return module
        if name == 'http_server':
            return http_template()
        return original(name)
    authority.template = template
    return provenance


def restrict_service_reads(plan):
    """Same Landlock boundary as014, allowing public worker dependencies too.

    Private old source directories retain owner paths via symlinks whose
    targets are outside the read-allowed HTTP workspace.
    """
    code = plan['_code']
    denied_names = {'admin.py', 'beta019_seed.py'}
    paths = {plan['_paths']['canonical'].parent, code, Path(sys.base_prefix) / 'lib', Path(sys.prefix) / 'lib',
        Path(sys.executable).resolve(), Path(sys.prefix) / 'pyvenv.cfg',
        Path('/usr/lib'), Path('/usr/share'), Path('/etc'), Path('/dev/null'), Path('/dev/urandom')}
    for path in code.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        name = path.name
        if (name in denied_names or 'oracle' in name or 'worlds' in name or '_executor' in name
                or '_operator' in name or name.endswith('_qa.py') or name.startswith(('test_', 'qa_'))):
            continue
        if path.suffix in ('.py', '.json', '.md', '.txt'):
            paths.add(path)
    forbidden = [Path(p) for p in plan.get('forbidden_files', [])]
    forbidden += [code / name for name in ('beta019_seed.py', 'beta019_executor.py', 'beta019_operator.py', 'law_validation014_oracle.py')]
    forbidden = [p for p in forbidden if p.exists()]
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 1:
        raise RuntimeError('MISSING_CAPABILITY_LANDLOCK')
    class Ruleset(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]
    class PathBeneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int)]
    rules = Ruleset(12)
    descriptor = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if descriptor < 0:
        raise RuntimeError('LANDLOCK_CREATE')
    try:
        for path in paths:
            if not path.exists():
                continue
            opened = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                # FileFinder needs directory listing in a fresh child. Listing
                # the code directory must not grant reads of excluded files.
                access = 8 if path == code else 12 if path.is_dir() else 4
                rule = PathBeneath(access, opened)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0) < 0:
                    raise RuntimeError('LANDLOCK_ADD:' + str(path))
            finally:
                os.close(opened)
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.syscall(446, descriptor, 0) < 0:
            raise RuntimeError('LANDLOCK_RESTRICT')
    finally:
        os.close(descriptor)
    denied = []
    for path in forbidden:
        try:
            with path.open('rb') as stream:
                stream.read(1)
        except PermissionError:
            denied.append(str(path))
        else:
            raise RuntimeError('PRIVATE_SOURCE_ISOLATION_FAILED:' + str(path))
    return {'Landlock_ABI': abi, 'forbidden_reads_denied': denied,
        'scope': 'HTTP workspace plus signed public source/dependency files; no executor/owner/sealed-source reads'}


def serve(plan):
    storage = authorize_storage(plan)
    for role in ('canonical', 'typed'):
        if not storage.migrate(plan['_paths'][role], dry_run=True)['idempotent']:
            raise ValueError('OWNER_MIGRATION_REQUIRED_BEFORE_SERVE')
    provenance = template_hooks(plan)
    from deploy018_authority import reconcile
    retired = reconcile(plan['_paths']['typed'], 'Owner-authorized RC020 service restart: revoke unfinished typed grants, preserve evidence.')
    os.environ['LIVE_MATH_NATIVE_PREVIEW'] = '1'
    os.environ['LIVE_MATH_TYPED_CYCLE_DB'] = str(plan['_paths']['typed'])
    os.environ.pop('LM018_FAULT', None)
    import beta019_http
    import typed_cycle011_public
    import beta019_receipt
    import native_preview008_worker
    import native_preview008_engine
    import uvicorn
    for name in ('beta019_executor', 'beta019_seed', 'beta019_operator',
                 'engine017_executor', 'engine017_operator', 'law_validation014_oracle'):
        if name in sys.modules:
            raise RuntimeError('OPERATOR_OR_ORACLE_PRELOADED_IN_HTTP:' + name)
    origin = os.environ.get('LIVE_MATH_PUBLIC_URL', plan['origin']) if plan['mode'] == 'production' else plan['origin']
    app = beta019_http.create_app(origin, plan['_paths']['canonical'].parent, plan['_paths']['typed'],
        Path(plan['password_file']).read_text().strip(), enabled=True)
    log = Path(plan['startup_record'])
    record = {'release': RELEASE, 'capsule_sha256': CAPSULE_SHA, 'deployment_id': plan['deployment_id'],
        'template': provenance, 'retired_move_ids': retired, 'mode': plan['mode']}
    # Open log before the allowlist closes access to the private supervisor dir.
    with log.open('w') as stream:
        record['isolation'] = restrict_service_reads(plan)
        stream.write(json.dumps(record, indent=2) + '\n')
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    # Executor CLI retains CPU90s. A long-running service has no cumulative
    # lifetime CPU kill; HTTP/preview/worker deadlines remain unchanged.
    uvicorn.run(app, host='127.0.0.1', port=plan['port'], access_log=False, proxy_headers=False,
        limit_concurrency=32, timeout_keep_alive=2, ssl_certfile=plan.get('tls_cert'), ssl_keyfile=plan.get('tls_key'))


def owner(plan, action):
    authorize_storage(plan)
    payload = json.loads(sys.stdin.read(65537))
    database = plan['_paths']['typed']
    if action == 'seed':
        from beta019_seed import seed
        return seed(database, database.parent, Path(plan['operator_seals']), payload.get('case', 0), payload['request_key'])
    if action == 'execute':
        from beta019_executor import execute
        return execute(database, **payload)
    if action == 'activate':
        from beta019_operator import activate
        return activate(database, **payload)
    if action == 'commit':
        from beta019_operator import commit
        return commit(database, payload)
    raise ValueError('UNKNOWN_OWNER_ACTION')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorization', type=Path, required=True)
    parser.add_argument('action', choices=['migrate', 'serve', 'seed', 'activate', 'execute', 'commit'])
    args = parser.parse_args()
    os.umask(0o077)
    try:
        plan = load_authorization(args.authorization)
        if args.action == 'serve':
            serve(plan)
        else:
            if args.action != 'migrate':
                resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
                resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
            result = migrate(plan) if args.action == 'migrate' else owner(plan, args.action)
            print(json.dumps({'ok': True, 'result': result}))
    except (ValueError, OSError, KeyError, sqlite3.Error) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        raise SystemExit(2)
