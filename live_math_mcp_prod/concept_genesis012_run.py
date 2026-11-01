"""Meter complete012 QA through process exit and package immutable evidence."""
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile
from native_preview008_server import MeasuredProcess


def main():
    pointer=Path('/tmp/lm012_cohort');previous=pointer.read_text() if pointer.exists() else None;started=time.perf_counter_ns()
    process=MeasuredProcess([sys.executable,str(Path(__file__).with_name('concept_genesis012_qa.py')),*sys.argv[1:]])
    try:process.wait(timeout=240)
    except __import__('subprocess').TimeoutExpired:process.kill();process.wait();raise SystemExit('WHOLE_QA_WALL_BOUND; preserve partial cohort')
    if not pointer.exists() or pointer.read_text()==previous:raise SystemExit(process.returncode)
    base=Path(pointer.read_text().strip());out=Path(json.loads((base/'metadata.json').read_text())['report'])
    if not out.exists():raise SystemExit(process.returncode or 'Report unavailable; partial evidence retained')
    usage=process.child_usage;measured={'method':'OS wait4 through whole QA exit','wall_ns':time.perf_counter_ns()-started,
        'CPU_ns_inclusive_all_descendants':round((usage.ru_utime+usage.ru_stime)*1e9),'peak_RSS_KiB':usage.ru_maxrss,
        'scope':'Cold interpreter/imports, source freeze, complete mathematical P0, mathematical validation, regressions, export and teardown.',
        'overlap':'Per-stage/worker costs are subsets. P0 scientific budget is recorded separately before G6 regressions.'}
    (out/'whole-QA-costs.json').write_text(json.dumps(measured,indent=2)+'\n')
    costs=json.loads((out/'costs.json').read_text());costs['whole_QA_through_exit']=measured
    (out/'costs.json').write_text(json.dumps(costs,ensure_ascii=False,indent=2)+'\n')
    with (out/'report.md').open('a') as f:f.write('\nWhole-QA resource evidence (including G6): '+json.dumps(measured)+'\n')
    # Keep the required scientific interpretation as the final report section.
    text=(out/'report.md').read_text();tail='\nWhole-QA resource evidence (including G6): '+json.dumps(measured)+'\n'
    text=text.removesuffix(tail);text=text.replace('## Что именно ядро научилось создавать самостоятельно',tail+'\n## Что именно ядро научилось создавать самостоятельно')
    (out/'report.md').write_text(text)
    hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}
    (out/'manifest-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,arcname=str(Path(out.name)/p.relative_to(out)))
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(json.dumps({'report':str(out/'report.md'),'ZIP':str(archive),'whole_QA':measured}),flush=True)


if __name__=='__main__':main()
