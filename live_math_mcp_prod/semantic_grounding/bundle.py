"""Bundle unchanged old sources plus additive study; exclude databases and credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def build(repo: Path, root: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError('REFUSE_TO_OVERWRITE_PREVIOUS_ARCHIVE')
    with tempfile.TemporaryDirectory(prefix='lm-grounding003-') as tmp:
        stage = Path(tmp) / 'SEMANTIC_GROUNDING_003'; stage.mkdir()
        with ZipFile(root / 'frozen/baseline002.zip') as z:
            for member in z.namelist():
                name = member.removeprefix('ARTIFACT_GENESIS_002/')
                if not name.startswith('live_math_mcp_prod/') or member.endswith('/'):
                    continue
                dest = (stage / name).resolve()
                if not dest.is_relative_to(stage):
                    raise ValueError('UNSAFE_BASELINE_SOURCE_MEMBER')
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(z.read(member))
        for p in (repo / 'live_math_mcp_prod/semantic_grounding').glob('*.py'):
            dest = stage / 'live_math_mcp_prod/semantic_grounding' / p.name
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
        for name in ['test_semantic_grounding003.py', 'test_semantic_grounding003_boundary.py']:
            shutil.copyfile(repo / 'live_math_mcp_prod' / name, stage / 'live_math_mcp_prod' / name)
        for p in root.rglob('*'):
            if not p.is_file() or any(x.startswith('.') for x in p.relative_to(root).parts):
                continue
            if p.suffix in {'.sqlite3', '.db', '.key', '.pem'} or 'private-oauth' in p.name or str(p.relative_to(root)) in {'final-manifest.json', 'final-replay-receipt.json'}:
                continue
            dest = stage / 'semantic_grounding003' / p.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
        shutil.copyfile(root / 'reproduce.sh', stage / 'reproduce.sh')
        shutil.copyfile(root / 'requirements.txt', stage / 'requirements.txt')
        for name, expected in json.loads((root / 'source-freeze.json').read_text())['frozen_files'].items():
            p = (stage / 'semantic_grounding003' / name).resolve(strict=True)
            if not p.is_relative_to(stage / 'semantic_grounding003') or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                raise ValueError('INCOMPLETE_FROZEN_BUNDLE:' + name)
        manifest = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    info = ZipInfo('SEMANTIC_GROUNDING_003/' + str(p.relative_to(stage)), date_time=(2026, 10, 31, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED; info.external_attr = 0o100644 << 16
                    z.writestr(info, p.read_bytes())
        return {'zip': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'bytes': output.stat().st_size, 'files': len(manifest) + 1,
                'bundle_manifest_sha256': hashlib.sha256((stage / 'manifest.json').read_bytes()).hexdigest()}
