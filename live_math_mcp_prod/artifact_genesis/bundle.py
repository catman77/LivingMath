"""Additive bundle on immutable 001 source; never includes private SQLite or tokens."""
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import shutil


def build(repo: Path,root: Path,output: Path) -> dict:
    if output.exists():raise FileExistsError('REFUSE_TO_OVERWRITE_EXISTING_ARCHIVE')
    with tempfile.TemporaryDirectory(prefix='lm-genesis002-') as tmp:
        stage=Path(tmp)/'ARTIFACT_GENESIS_002';stage.mkdir()
        # Every reused source file is copied from the immutable accepted ZIP, not patched.
        with ZipFile(root/'frozen/baseline001.zip') as z:
            for member in z.namelist():
                prefix='ARTIFACT_TRANSLATION_001/'
                name=member.removeprefix(prefix)
                if not name.startswith('live_math_mcp_prod/') or member.endswith('/'):continue
                dest=(stage/name).resolve()
                if not dest.is_relative_to(stage):raise ValueError('UNSAFE_BUNDLE_MEMBER')
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(member))
        for p in (repo/'live_math_mcp_prod/artifact_genesis').glob('*.py'):
            dest=stage/'live_math_mcp_prod/artifact_genesis'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        for name in ['test_artifact_genesis002.py','test_artifact_genesis002_boundary.py']:
            shutil.copyfile(repo/'live_math_mcp_prod'/name,stage/'live_math_mcp_prod'/name)
        for p in root.rglob('*'):
            if not p.is_file() or any(x.startswith('.') for x in p.relative_to(root).parts):continue
            if p.suffix in {'.sqlite3','.db','.key','.pem'} or 'private-oauth' in p.name or p.name in {'final-manifest.json','final-replay-receipt.json'}:continue
            dest=stage/'artifact_genesis002'/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        shutil.copyfile(root/'reproduce.sh',stage/'reproduce.sh');shutil.copyfile(root/'requirements.txt',stage/'requirements.txt')
        manifest={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    info=ZipInfo('ARTIFACT_GENESIS_002/'+str(p.relative_to(stage)),date_time=(2026,10,31,0,0,0))
                    info.compress_type=ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes())
        return {'zip':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,
                'files':len(manifest)+1,'bundle_manifest_sha256':hashlib.sha256((stage/'manifest.json').read_bytes()).hexdigest()}
