"""Default-off019 beta factory; production018/legacy entrypoints unchanged."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import uvicorn
from beta019_controller import Controller019
from deploy018_http import Controller018
from deploy018_authority import reconcile
from deploy018_storage import private_path

VERSION = '1.0.0b1'


class ReviewedRouter:
    """Fixed source-family dispatch, preserving accepted017 native profiles."""
    def __init__(self, database):
        self.external, self.accepted = Controller019(database), Controller018(database)
        self.database = database

    def registered(self, project):
        return self.external.registered(project)

    def route(self, project):
        from typed_cycle011_store import connect
        _, binding = self.registered(project)
        with connect(self.database) as c:
            row = c.execute('SELECT content FROM events WHERE id=? AND project=?', (binding['root_event_id'], project)).fetchone()
        family = json.loads(row[0])['source_spec']['parameters']['algebra']
        if family == 'automata-nfa019/v1':
            return self.external
        if family in ('affine', 'permutation', 'stack'):
            return self.accepted
        raise ValueError('019_UNSUPPORTED_REVIEWED_ADAPTER')

    def preview(self, request):
        return self.route(request['project']).preview(request)

    def precommit(self, request, request_key):
        return self.route(request['project']).precommit(request, request_key)

    def validate(self, project, move_id, event_id):
        return self.route(project).validate(project, move_id, event_id)

    def novelty(self, request):
        return self.route(request['project']).novelty(request)

    def history(self, project):
        return self.route(project).history(project)


def create_app(origin, data, database, password, enabled=False, bounds=None):
    private_path(data / 'research.sqlite3'); private_path(database)
    path = Path(__file__).with_name('deploy018_http.py')
    spec = importlib.util.spec_from_file_location('_beta019_http018', path)
    transport = importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
    transport.Controller018 = ReviewedRouter
    transport.CONTRACT = {**transport.CONTRACT, 'version': VERSION, 'protocol': 'livingmath-research019/v1',
        'deployment': 'ISOLATED_PRIVATE_BETA', 'source_adapter': 'automata-nfa019/v1',
        'accepted017_native_profiles': ['affine', 'permutation', 'stack'],
        'R5a': 'private protocol/security gate', 'R5b': 'DEFERRED_BY_OWNER',
        'registration': 'Local reviewed owner only; data-only source envelope, no remote code/path/plugin',
        'engine': 'unchanged004/006/013 mathematics, typed011–018 protocol with019 native adapter'}
    return transport.create_app(origin, data, database, password, enabled, bounds)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for flag in ('data', 'typed', 'cert', 'key', 'password'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--origin', required=True); parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--enable019', action='store_true')
    parser.add_argument('--forbidden', type=Path, action='append', default=[])
    parser.add_argument('--rate', type=int, default=1000); parser.add_argument('--window', type=float, default=60)
    args = parser.parse_args(); os.umask(0o077)
    os.environ['LIVE_MATH_NATIVE_PREVIEW'] = '1'; os.environ['LIVE_MATH_TYPED_CYCLE_DB'] = str(args.typed)
    if not 1 <= args.rate <= 1000 or not 0.1 <= args.window <= 60:
        parser.error('bounded rate1..1000/window0.1..60 required')
    if args.enable019:
        reconcile(args.typed, '019 owner pre-start reconciliation; no automatic execution recovery')
    app = create_app(args.origin, args.data, args.typed, args.password.read_text().strip(), args.enable019,
        {'rate': args.rate, 'window': args.window})
    if args.enable019:
        import typed_cycle011_public
        import beta019_receipt
        from law_validation014_isolation import restrict_reads
        for name in ('beta019_executor', 'beta019_seed', 'beta019_operator', 'law_validation014_oracle', 'engine017_executor'):
            if name in sys.modules:
                raise RuntimeError('019_AUTHORITY_OR_ORACLE_PRELOADED:' + name)
        evidence = restrict_reads(args.data, args.forbidden)
        (args.data / 'beta019-isolation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824)); resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    uvicorn.run(app, host='127.0.0.1', port=args.port, ssl_certfile=str(args.cert), ssl_keyfile=str(args.key),
        access_log=False, proxy_headers=False, limit_concurrency=32, timeout_keep_alive=2)
