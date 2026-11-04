"""Local, single-owner CLI. All writes require explicit request keys."""
import argparse
import json
import os
from pathlib import Path
import sys
from . import RELEASE, __version__, core
from .core import canonical, digest
from .errors import AssuranceError
from .service import Service
from .validation import parse, validate
from .workspace import atomic_write


def default_root():
    return str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'lm-suti-assurance')


def read_json(path):
    p = Path(path)
    if p.stat().st_size > 2 * 1024 * 1024:
        raise AssuranceError('INPUT_TOO_LARGE')
    return parse(p.read_text(encoding='utf-8'))


def parser():
    p = argparse.ArgumentParser(description='LivingMath × SUTI finite assurance developer preview')
    p.add_argument('--state-dir', default=default_root())
    p.add_argument('--version', action='version', version=RELEASE + ' (' + __version__ + ')')
    sub = p.add_subparsers(dest='command', required=True)
    for noun, actions in [('project', ['new']), ('source', ['add']), ('task', ['import', 'draft', 'review']),
                          ('candidate', ['import'])]:
        q = sub.add_parser(noun); actions_parser = q.add_subparsers(dest='action', required=True)
        for action in actions:
            a = actions_parser.add_parser(action)
            a.add_argument('--project', required=True); a.add_argument('--request-key', required=True)
            if action in ('import','draft'):
                a.add_argument('--file', required=True)
            elif noun == 'source':
                a.add_argument('--snapshot', required=True); a.add_argument('--policy', required=True)
            elif action == 'review':
                a.add_argument('--task-ref', required=True); a.add_argument('--actor', required=True)
                a.add_argument('--reason', required=True)
    q = sub.add_parser('check');q.add_argument('--project', required=True);q.add_argument('--candidate-ref', required=True)
    q.add_argument('--engine', choices=['direct','compiled'], default='direct');q.add_argument('--request-key', required=True)
    q = sub.add_parser('report');q.add_argument('--project', required=True);q.add_argument('--format', choices=['json','text'], default='text')
    q = sub.add_parser('export');q.add_argument('--project', required=True);q.add_argument('--output', required=True)
    q.add_argument('--audience', choices=['private','reviewers','public'], required=True)
    q = sub.add_parser('replay');q.add_argument('bundle');q.add_argument('--offline', action='store_true', required=True)
    q.add_argument('--engine', choices=['direct','compiled'], default='direct')
    q = sub.add_parser('doctor');q.add_argument('--smoke', action='store_true')
    q = sub.add_parser('examples');q.add_argument('--output', required=True);q.add_argument('--project', default='pilot')
    q = sub.add_parser('smoke');q.add_argument('--output')
    return p


def examples(output, project):
    from .smoke import CASES, POLICY, TAG
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads((core.ROOT/'examples/FROZEN_CORPUS.json').read_text())
    sources = json.loads((core.ROOT/'examples/SOURCE_SNAPSHOTS.json').read_text())
    (output/'policy.json').write_text(canonical(POLICY)+'\n')
    for tid, delta, _ in CASES:
        task = {'schema':'lm-suti.assurance.task/0.1','project':project,'task':corpus[tid]}
        (output/(tid+'-task.json')).write_text(canonical(task)+'\n')
        (output/(tid+'-delta.json')).write_text(canonical({'schema':TAG,**delta})+'\n')
        for index, sid in enumerate(corpus[tid]['source_ids']):
            (output/(tid+'-source-'+str(index)+'.json')).write_text(canonical(sources[sid])+'\n')
    return {'status':'CREATED','directory':str(output), 'note':'Candidate envelope must reference the task_ref returned by task import.'}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        s = Service(args.state_dir); cmd = args.command
        if cmd == 'project':
            value = s.new(args.project, args.request_key)
        elif cmd == 'source':
            value = s.source(args.project, read_json(args.snapshot), read_json(args.policy), args.request_key)
        elif cmd == 'task':
            if args.action == 'review':
                value = s.review(args.project, args.task_ref, args.actor, args.reason, args.request_key)
            else:
                # Draft import is explicit structured input, never guessed NL semantics.
                value = s.task(args.project, read_json(args.file), args.request_key)
        elif cmd == 'candidate':
            value = s.candidate(args.project, read_json(args.file), args.request_key)
        elif cmd == 'check':
            value = s.check(args.project, args.candidate_ref, args.engine, args.request_key)
        elif cmd == 'report':
            from .report import report, text_report
            value = report(s.workspace(args.project))
            if args.format == 'text':
                print(text_report(value));return 0
        elif cmd == 'export':
            from .bundle import export_bundle
            raw, manifest = export_bundle(s.workspace(args.project), args.audience)
            target = Path(args.output)
            if target.exists() and target.read_bytes() != raw:
                raise AssuranceError('EXPORT_ALREADY_EXISTS')
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, raw)
            value = {'status':'EXPORTED','sha256':core.byte_digest(raw),'manifest':manifest}
        elif cmd == 'replay':
            from .bundle import replay, MAX_BUNDLE
            if Path(args.bundle).stat().st_size > MAX_BUNDLE:
                raise AssuranceError('BUNDLE_SIZE_LIMIT')
            value = replay(Path(args.bundle).read_bytes(), args.engine)
        elif cmd == 'doctor':
            import importlib.metadata, platform
            value = {'status':'PASS','release':RELEASE,'python':platform.python_version(),
                     'jsonschema':importlib.metadata.version('jsonschema'),**core.identity(),
                     'native_SUTI':'NOT_EXECUTED','formal_adapter':'UNAVAILABLE_NOT_REGISTERED',
                     'model':'OPTIONAL_NOT_REQUIRED','execution_permission':False}
            if args.smoke:
                from .smoke import run
                value['smoke'] = run();value['status'] = value['smoke']['status']
        elif cmd == 'examples':
            value = examples(args.output, args.project)
        elif cmd == 'smoke':
            from .smoke import populate
            import tempfile
            with tempfile.TemporaryDirectory() as temporary:
                value = populate(Service(Path(temporary)/'state'), output=args.output)
        print(canonical(value))
        return 1 if value.get('status') == 'FAIL' else 0
    except AssuranceError as exc:
        print(canonical(exc.as_dict()));return 2
    except (OSError, UnicodeError) as exc:
        print(canonical({'status':'HOLD','reason_code':'LOCAL_IO_ERROR','error_type':type(exc).__name__}));return 2


if __name__ == '__main__':
    sys.exit(main())
