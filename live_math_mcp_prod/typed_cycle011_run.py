"""Whole011 QA CPU/wall/RSS through exit; report serialization is included."""
import hashlib
import json
from pathlib import Path
import sys
import time
from native_preview008_server import MeasuredProcess


def main():
    pointer=Path('/tmp/lm011_cohort');previous=pointer.read_text() if pointer.exists() else None;start=time.perf_counter_ns()
    process=MeasuredProcess([sys.executable,str(Path(__file__).with_name('typed_cycle011_qa.py')),*sys.argv[1:]])
    process.wait()
    if not pointer.exists() or pointer.read_text()==previous:raise SystemExit(process.returncode)
    base=Path(pointer.read_text().strip());out=Path(json.loads((base/'metadata.json').read_text())['report'])
    if not out.exists():raise SystemExit(process.returncode or 'No exported report')
    usage=process.child_usage;receipt={'method':'OS wait4 through whole QA process exit','wall_ns':time.perf_counter_ns()-start,
        'CPU_ns_inclusive_all_descendants':round((usage.ru_utime+usage.ru_stime)*1e9),'peak_RSS_KiB':usage.ru_maxrss,
        'includes':'interpreter/imports, source freeze, tests/regression, MCP/worker/executor/operator, report generation and teardown',
        'CPU_overlap':'per-worker costs are subsets; do not add them again','returncode':process.returncode}
    (out/'whole-QA-exit-usage.json').write_text(json.dumps(receipt,indent=2)+'\n')
    costs=json.loads((out/'costs.json').read_text());costs['whole_QA_exit_usage']=receipt
    (out/'costs.json').write_text(json.dumps(costs,ensure_ascii=False,indent=2)+'\n')
    with (out/'report.md').open('a') as f:f.write('\n## Whole QA through exit\n\n'+json.dumps(receipt)+'\n')
    files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}
    (out/'manifest-sha256.json').write_text(json.dumps(files,indent=2)+'\n')
    print(json.dumps({'report':str(out),'whole_QA_exit_usage':receipt}),flush=True)


if __name__=='__main__':main()
