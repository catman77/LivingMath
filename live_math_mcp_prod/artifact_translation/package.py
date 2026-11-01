"""Source/evidence bundle builder: never copies SQLite, OAuth responses or sealed data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def build(repo: Path, artifact: Path, output: Path) -> dict:
    if output.exists():raise FileExistsError('Refusing to overwrite an existing release or trial ZIP: '+str(output))
    with tempfile.TemporaryDirectory(prefix='lm-at001-bundle-') as scratch:
        stage=Path(scratch);base=stage/'ARTIFACT_TRANSLATION_001';base.mkdir()
        code=repo/'live_math_mcp_prod'
        packages={'artifact_translation','davcore','research_automation','unified_system'}
        sources=[p for p in code.glob('*.py')]
        sources += [p for name in packages for p in (code/name).glob('*.py')]
        sources += list(code.glob('requirements*.txt'))+list(code.glob('requirements*.in'))
        for src in sources:
            dest=base/src.relative_to(repo);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        for src in artifact.rglob('*'):
            if not src.is_file() or any(part.startswith('.') for part in src.relative_to(artifact).parts):continue
            if (src.suffix in {'.sqlite3','.db','.key','.pem'} or 'private-oauth' in src.name
                    or src.name in {'final-replay-receipt.json','final-manifest.json'}):
                continue
            dest=base/'artifact_translation001'/src.relative_to(artifact)
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        shutil.copyfile(artifact/'reproduce.sh',base/'reproduce.sh')
        shutil.copyfile(artifact/'requirements.txt',base/'requirements.txt')
        manifest={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(base.rglob('*')) if p.is_file()}
        (base/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(base.rglob('*')):
                if p.is_file():
                    info=ZipInfo(str(p.relative_to(stage)),date_time=(2026,10,30,0,0,0))
                    info.compress_type=ZIP_DEFLATED;info.external_attr=0o100644<<16
                    z.writestr(info,p.read_bytes())
        return {'zip':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                'bytes':output.stat().st_size,'files':len(manifest)+1,
                'bundle_manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True)
    p.add_argument('--zip',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.repo.resolve(),a.artifact.resolve(),a.zip.resolve())))
