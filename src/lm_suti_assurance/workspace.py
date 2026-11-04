"""Single-owner atomic journal. Objects precede commit; failed commits are invisible."""
import fcntl
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from .core import canonical, digest, byte_digest
from .errors import AssuranceError
from .validation import parse, inspect

ZERO = '0' * 64
SLUG = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


def private_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise AssuranceError('SYMLINK_FORBIDDEN')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    stat = path.stat()
    if not path.is_dir() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise AssuranceError('PRIVATE_OWNER_DIRECTORY_REQUIRED')
    return path


def atomic_write(path, raw):
    if path.is_symlink():
        raise AssuranceError('SYMLINK_FORBIDDEN')
    fd, temporary = tempfile.mkstemp(prefix='.commit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_history(rows):
    previous = ZERO
    keys = set()
    for i, row in enumerate(rows, 1):
        unhashed = {k: v for k, v in row.items() if k != 'hash'}
        if (row.get('seq') != i or row.get('previous_hash') != previous
                or row.get('hash') != digest(unhashed) or row.get('request_key') in keys):
            raise AssuranceError('JOURNAL_INTEGRITY_FAILURE')
        keys.add(row['request_key'])
        previous = row['hash']
    return previous


class Workspace:
    def __init__(self, root, project):
        if not isinstance(project, str) or not SLUG.fullmatch(project):
            raise AssuranceError('INVALID_PROJECT_ID', '/project')
        self.root = private_dir(Path(root).absolute())
        self.path = self.root / project
        self.project = project

    @contextmanager
    def locked(self):
        private_dir(self.path)
        private_dir(self.path / 'objects')
        lock = self.path / '.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def history(self):
        path = self.path / 'journal.jsonl'
        if path.is_symlink():
            raise AssuranceError('SYMLINK_FORBIDDEN')
        if not path.exists():
            return []
        if path.stat().st_size > 32 * 1024 * 1024:
            raise AssuranceError('JOURNAL_SIZE_LIMIT')
        try:
            rows = [parse(line) for line in path.read_text().splitlines()]
            validate_history(rows)
            return rows
        except AssuranceError:
            raise
        except (OSError, ValueError, KeyError):
            raise AssuranceError('JOURNAL_INTEGRITY_FAILURE') from None

    def get(self, ref):
        if not isinstance(ref, str) or not SHA.fullmatch(ref):
            raise AssuranceError('INVALID_OBJECT_REFERENCE')
        path = self.path / 'objects' / (ref + '.json')
        if path.is_symlink() or not path.is_file():
            raise AssuranceError('MISSING_OBJECT', details={'ref': ref})
        raw = path.read_bytes()
        if byte_digest(raw) != ref:
            raise AssuranceError('OBJECT_INTEGRITY_FAILURE', details={'ref': ref})
        return parse(raw.decode('utf-8'))

    def put(self, value):
        inspect(value)
        raw = canonical(value).encode()
        ref = byte_digest(raw)
        path = self.path / 'objects' / (ref + '.json')
        if path.exists():
            self.get(ref)
        else:
            atomic_write(path, raw)
        return ref

    def transact(self, action, request_key, payload, operation):
        inspect(payload)
        if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_key):
            raise AssuranceError('REQUEST_KEY_REQUIRED', '/request_key')
        request_digest = digest({'action': action, 'payload': payload})
        with self.locked():
            rows = self.history()
            for row in rows:
                if row['request_key'] == request_key:
                    if row['payload_digest'] != request_digest or row['action'] != action:
                        raise AssuranceError('REQUEST_KEY_CONFLICT', '/request_key')
                    return row['result']
            if action != 'project.new' and not rows:
                raise AssuranceError('PROJECT_NOT_FOUND')
            result, refs = operation(rows)
            row = {'seq': len(rows) + 1, 'previous_hash': rows[-1]['hash'] if rows else ZERO,
                   'action': action, 'request_key': request_key, 'payload_digest': request_digest,
                   'result': result, 'object_refs': sorted(set(refs))}
            row['hash'] = digest(row)
            raw = b''.join((canonical(r) + '\n').encode() for r in [*rows, row])
            atomic_write(self.path / 'journal.jsonl', raw)
            return result
