"""A reviewable study capsule; reuse immutable 003 source, no new runtime framework."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def include_artifact(name: str) -> bool:
    p = Path(name)
    return (name not in {'final-replay-receipt.json', 'final-manifest.json'}
            and p.suffix not in {'.sqlite3', '.db', '.key', '.pem'} and 'private-oauth' not in p.name
            and not any(x.startswith('.') for x in p.parts))


def build(repo: Path, root: Path, output: Path, *, observer005: bool = False, source006: bool = False, pipeline007: bool = False, typed008: bool = False) -> dict:
    if output.exists(): raise FileExistsError('DO_NOT_OVERWRITE_ARCHIVE')
    label = 'OBSERVER_CLOSURE_005' if observer005 else 'SEMANTIC_REPAIR_004'
    data_name = 'observer_closure005' if observer005 else 'semantic_repair004'
    baseline = 'baseline004.zip' if observer005 else 'baseline003.zip'
    old_label = 'SEMANTIC_REPAIR_004' if observer005 else 'SEMANTIC_GROUNDING_003'
    if source006:
        label,data_name,baseline,old_label='SOURCE_ALIGNMENT_006','source_alignment006','baseline005.zip','OBSERVER_CLOSURE_005'
    if pipeline007:
        label,data_name,baseline,old_label='PIPELINE_REPAIR_007','pipeline_repair007','baseline006.zip','SOURCE_ALIGNMENT_006'
    if typed008:
        label,data_name,baseline,old_label='TYPED_REALIZATION_008','typed_realization008','baseline007.zip','PIPELINE_REPAIR_007'
    with tempfile.TemporaryDirectory(prefix='lm-repair004-') as temp:
        stage = Path(temp)/label; stage.mkdir()
        with ZipFile(root/'frozen'/baseline) as z:
            for member in z.namelist():
                name = member.removeprefix(old_label+'/')
                if not (name.startswith('live_math_mcp_prod/') or ((observer005 or source006 or pipeline007 or typed008) and name.startswith('semantic_repair004/'))) or member.endswith('/'): continue
                p = (stage/name).resolve()
                if not p.is_relative_to(stage): raise ValueError('UNSAFE_OLD_SOURCE')
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(z.read(member))
        for p in (repo/'live_math_mcp_prod/semantic_repair').glob('*.py'):
            dest = stage/'live_math_mcp_prod/semantic_repair'/p.name; dest.parent.mkdir(exist_ok=True, parents=True); shutil.copyfile(p, dest)
        tests=['test_semantic_repair004.py','test_semantic_repair004_boundary.py']
        if observer005 or source006 or pipeline007 or typed008: tests+=['test_observer_closure005.py']
        if source006 or pipeline007 or typed008: tests+=['test_source_alignment006.py']
        if pipeline007 or typed008: tests+=['test_soundness007.py','test_pipeline_repair007.py']
        if typed008: tests+=['test_typed_realization008.py']
        for name in tests:
            shutil.copyfile(repo/'live_math_mcp_prod'/name, stage/'live_math_mcp_prod'/name)
        for p in root.rglob('*'):
            if p.is_file() and include_artifact(str(p.relative_to(root))):
                dest = stage/data_name/p.relative_to(root); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dest)
        for name, h in json.loads((root/'protocol-freeze.json').read_text())['freeze_files'].items():
            p = stage/data_name/name
            if hashlib.sha256(p.read_bytes()).hexdigest() != h: raise ValueError('FROZEN_BUNDLE_DRIFT:'+name)
        for name in ['reproduce.sh','requirements.txt']: shutil.copyfile(root/name, stage/name)
        manifest = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(stage.rglob('*')):
                if not p.is_file(): continue
                info = ZipInfo(label+'/'+str(p.relative_to(stage)), date_time=(2026,10,31,0,0,0)); info.compress_type=ZIP_DEFLATED; info.external_attr=0o100644<<16
                z.writestr(info,p.read_bytes())
        return {'zip': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'bytes': output.stat().st_size,
                'files': len(manifest)+1, 'manifest_sha256': hashlib.sha256((stage/'manifest.json').read_bytes()).hexdigest()}
