"""Original015 native test source, portable without the large local experiment ZIP."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def native_source(target: Path, archive: Path, *, snapshot: Path | None = None) -> None:
    """Copy exact original bytes; reject drift in either distribution format."""
    snapshot = snapshot or Path(__file__).parent / 'testdata/xi015_source'
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    target.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['source_archive_sha256']:
            raise ValueError('PINNED_SOURCE_ARCHIVE_DRIFT')
        with ZipFile(archive) as container:
            files = {name: container.read('RH_XI_ROUTES_EXPORT_001/' + name) for name in manifest['files']}
    else:
        files = {name: (snapshot / name).read_bytes() for name in manifest['files']}
    for name, raw in files.items():
        if hashlib.sha256(raw).hexdigest() != manifest['files'][name]:
            raise ValueError('PINNED_SOURCE_DRIFT:' + name)
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
