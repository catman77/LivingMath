"""OS-metered acceptance entry point; full QA/validation CPU includes all descendants."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from native_preview008_server import MeasuredProcess


def main():
    pointer = Path('/tmp/lm009_cohort')
    previous = pointer.read_text() if pointer.exists() else None
    started = time.perf_counter_ns()
    process = MeasuredProcess([sys.executable, str(Path(__file__).with_name('research_cycle009_qa.py')), *sys.argv[1:]])
    process.wait()
    if any(flag in sys.argv for flag in ('-h', '--help')):
        raise SystemExit(process.returncode)
    if process.returncode != 0 or not pointer.exists() or pointer.read_text() == previous:
        raise SystemExit(process.returncode or 'QA child produced no fresh cohort')
    base = Path(pointer.read_text().strip())
    report = Path(json.loads((base / 'metadata.json').read_text())['report'])
    usage = process.child_usage
    receipt = {'method': 'OS wait4 through QA process exit', 'pid': process.pid, 'returncode': process.returncode,
        'wall_ns': time.perf_counter_ns() - started,
        'CPU_ns_inclusive_all_descendants': round((usage.ru_utime + usage.ru_stime) * 1e9),
        'peak_rss_KiB': usage.ru_maxrss,
        'scope': 'Entire QA interpreter launch/imports/source freeze/tests/historical86/operator fixture actions/client logging/cycles/report generation and waited-for children, including serialization and teardown.',
        'overlap': 'All MCP-server/preview/measurement CPU receipts are subsets of this inclusive total. Do not add them again or treat validation CPU as the scientific-cycle CPU.'}
    for folder in (base, report):
        (folder / 'whole-QA-exit-usage.json').write_text(json.dumps(receipt, indent=2) + '\n')
    costs = json.loads((report / 'costs.json').read_text()); costs['whole_QA_through_exit'] = receipt
    (report / 'costs.json').write_text(json.dumps(costs, indent=2, ensure_ascii=False) + '\n')
    result = json.loads((report / 'result.json').read_text()); result['whole_QA_CPU_accounted_through_exit'] = True
    (report / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    with (report / 'report.md').open('a') as out:
        out.write('\n## Whole QA process cost\n\nThe outer OS wait4 receipt includes orchestration/operator fixture work, all validation processes and final serialization/teardown: '
                  + str(receipt['CPU_ns_inclusive_all_descendants']) + ' CPU ns, ' + str(receipt['wall_ns']) + ' wall ns, peak RSS '
                  + str(receipt['peak_rss_KiB']) + ' KiB. Subprocess-specific costs are subsets; these totals are not a pure scientific-cycle benchmark.\n')
    files = {str(p.relative_to(report)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(report.rglob('*'))
             if p.is_file() and p.name != 'manifest-sha256.json'}
    (report / 'manifest-sha256.json').write_text(json.dumps({'algorithm': 'sha256', 'files': files}, indent=2) + '\n')
    print(json.dumps({'whole_QA_exit_usage': receipt, 'report': str(report), 'decision': result['decision']}), flush=True)


if __name__ == '__main__':
    main()
