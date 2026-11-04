"""Deterministic data-only ZIPs. Bundle code is compared, never imported/executed."""
import io
import json
import zipfile
from . import core, RELEASE
from .core import canonical, digest, byte_digest
from .errors import AssuranceError
from .offline import isolated
from .policy import can_publish, export_guard
from .validation import parse, validate, safe_source_schema
from .workspace import validate_history, ZERO, SHA
from .service import Service, evaluate_record, require

MAX_BUNDLE = 24 * 1024 * 1024


def export_bundle(workspace, audience='private'):
    require(audience in ('private', 'reviewers', 'public'), 'INVALID_AUDIENCE')
    with workspace.locked():
        rows = workspace.history()
        require(bool(rows), 'PROJECT_NOT_FOUND')
        excluded = set()
        for row in rows:
            if row['action'] == 'source.add':
                ref = row['result']['source_ref']
                a = workspace.get(ref)
                if not can_publish(a['snapshot'], a['publication_policy'], audience):
                    excluded.add(ref)
        refs = {ref for row in rows for ref in row['object_refs']}
        files = {'journal.jsonl': b''.join((canonical(row) + '\n').encode() for row in rows)}
        for ref in sorted(refs - excluded):
            files['objects/' + ref + '.json'] = canonical(workspace.get(ref)).encode()
        for path in core.LOCK['source_file_sha256']:
            files['core/' + path] = (core.ROOT / path).read_bytes()
        manifest = {'schema': 'lm-suti.assurance.package-manifest/0.1', 'release': RELEASE,
                    'project': workspace.project, 'audience': audience, **core.identity(),
                    'journal_head': rows[-1]['hash'], 'source_dependencies': sorted(excluded),
                    'files': {name: byte_digest(raw) for name, raw in sorted(files.items())},
                    'execution_permission': False}
        validate('package-manifest', manifest)
        files['package_manifest.json'] = canonical(manifest).encode()
        for name, raw in files.items():
            if not name.startswith('core/'):
                export_guard(raw.decode('utf-8'))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, raw in sorted(files.items()):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100600 << 16
                z.writestr(info, raw)
        require(len(output.getvalue()) <= MAX_BUNDLE, 'BUNDLE_SIZE_LIMIT')
        return output.getvalue(), manifest


class MemoryWorkspace:
    def __init__(self, objects):
        self.objects = objects

    def get(self, ref):
        if ref not in self.objects:
            raise AssuranceError('MISSING_SOURCE_DEPENDENCY', details={'ref': ref})
        return self.objects[ref]


def replay(raw, engine='direct'):
    require(engine in ('direct', 'compiled'), 'UNKNOWN_EVALUATOR')
    require(isinstance(raw, bytes) and len(raw) <= MAX_BUNDLE, 'BUNDLE_SIZE_LIMIT')
    # Load only installed, SHA-pinned code before entering the offline boundary.
    identity = core.identity()
    core.module('checks')
    try:
        with isolated():
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos = z.infolist()
                require(len(infos) <= 4096 and sum(i.file_size for i in infos) <= MAX_BUNDLE,
                        'BUNDLE_EXPANSION_LIMIT')
                names = [i.filename for i in infos]
                require(len(names) == len(set(names)), 'DUPLICATE_ZIP_MEMBER')
                for i in infos:
                    parts = i.filename.split('/')
                    require(not i.filename.startswith('/') and '\\' not in i.filename and
                            not any(p in ('', '.', '..') for p in parts) and
                            (i.external_attr >> 16) & 0o170000 != 0o120000,
                            'UNSAFE_ZIP_MEMBER')
                files = {i.filename: z.read(i) for i in infos}
            require('package_manifest.json' in files, 'MANIFEST_MISSING')
            manifest = validate('package-manifest', parse(files.pop('package_manifest.json').decode()))
            require(set(files) == set(manifest['files']), 'MANIFEST_FILE_SET_MISMATCH')
            require(all(byte_digest(raw) == manifest['files'][name] for name, raw in files.items()),
                    'MANIFEST_SHA_MISMATCH')
            require(all(manifest[k] == identity[k] for k in identity), 'MIGRATION_REQUIRED')
            expected_core = {'core/' + path for path in core.LOCK['source_file_sha256']}
            require({p for p in files if p.startswith('core/')} == expected_core, 'CORE_FILE_SET_MISMATCH')
            for path, sha in core.LOCK['source_file_sha256'].items():
                require(byte_digest(files['core/' + path]) == sha, 'FROZEN_CORE_INTEGRITY_FAILURE')
            rows = [parse(line) for line in files['journal.jsonl'].decode().splitlines()]
            require(validate_history(rows) == manifest['journal_head'], 'JOURNAL_HEAD_MISMATCH')
            require(not manifest['source_dependencies'], 'MISSING_SOURCE_DEPENDENCY')
            objects = {}
            for name, data in files.items():
                if name.startswith('objects/'):
                    ref = name.removeprefix('objects/').removesuffix('.json')
                    require(bool(SHA.fullmatch(ref)) and byte_digest(data) == ref, 'OBJECT_INTEGRITY_FAILURE')
                    objects[ref] = parse(data.decode())
                else:
                    require(name == 'journal.jsonl' or name in expected_core, 'UNKNOWN_BUNDLE_MEMBER')
            refs = {ref for row in rows for ref in row['object_refs']}
            require(refs == set(objects), 'OBJECT_SET_MISMATCH')
            workspace = MemoryWorkspace(objects)
            results = []
            for index, row in enumerate(rows):
                for ref in row['object_refs']:
                    require(ref in objects, 'MISSING_OBJECT')
                result = row['result']; prior = rows[:index]; action = row['action']
                if action == 'source.add':
                    a = workspace.get(result['source_ref'])
                    require(a['project'] == manifest['project'], 'CROSS_PROJECT_REFERENCE')
                    s = a['snapshot']
                    safe_source_schema(s)
                    require(can_publish(s, a['publication_policy'], manifest['audience']), 'PUBLICATION_POLICY_VIOLATION')
                    require(core.byte_digest(s['content_utf8'].encode()) == s['sha256'] and
                            digest(s) == result['snapshot_digest'], 'SOURCE_SHA_MISMATCH')
                elif action == 'task.import':
                    a = validate('task', workspace.get(result['task_ref']))
                    require(a['project'] == manifest['project'], 'CROSS_PROJECT_REFERENCE')
                    Service._sources(workspace, prior, a['task'])
                elif action == 'task.review':
                    Service._known(prior, 'task.import', 'task_ref', result['task_ref'])
                elif action == 'candidate.import':
                    a = validate('candidate', workspace.get(result['candidate_ref']))
                    require(a['project'] == manifest['project'], 'CROSS_PROJECT_REFERENCE')
                    Service._known(prior, 'task.import', 'task_ref', a['task_ref'])
                    if a.get('supersedes'):
                        Service._known(prior, 'candidate.import', 'candidate_ref', a['supersedes'])
                elif action == 'check':
                    stored = workspace.get(result['check_ref'])
                    Service._known(prior, 'candidate.import', 'candidate_ref', stored['candidate_ref'])
                    record = workspace.get(stored['candidate_ref'])
                    require(any(r['action'] == 'task.review' and r['result']['task_ref'] == record['task_ref']
                                for r in prior), 'TASK_REVIEW_REQUIRED')
                    task = workspace.get(record['task_ref'])['task']
                    sources = Service._sources(workspace, prior, task)
                    actual = evaluate_record(record, task, sources, engine)
                    expected = {k: stored[k] for k in actual}
                    require(canonical(actual) == canonical(expected), 'REPLAY_LOGICAL_MISMATCH')
                    require(result['status'] == actual['status'] and result['reason_code'] == actual['reason_code'],
                            'JOURNAL_RESULT_MISMATCH')
                    results.append({'check_ref': result['check_ref'], 'status': actual['status'],
                                    'logical_digest': digest(actual),
                                    'witness_digest': digest(actual['witnesses'])})
                else:
                    require(action == 'project.new' and index == 0, 'UNKNOWN_JOURNAL_ACTION')
            return {'status': 'PASS', 'project': manifest['project'], 'engine': engine,
                    'checks': results, 'logical_digest': digest(results), **identity,
                    'journal_entries': len(rows), 'journal_head': manifest['journal_head'],
                    'network': 'DISABLED', 'model': 'NOT_USED', 'execution_permission': False}
    except AssuranceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, UnicodeError):
        raise AssuranceError('INVALID_BUNDLE') from None
