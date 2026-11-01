"""One-command, fresh-project reproduction of the finite attention QA protocol."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

from attention_qa import configure
from qa_positive_acceptance import snapshot, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-root', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parent.parent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    private = Path.home() / '.local/state/livingmath/attention' / stamp
    private.mkdir(parents=True, exist_ok=False)
    report = (args.report_root or root / 'docs/qa') / ('LM-ATTENTION-001-' + stamp)
    config = configure()
    db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    backup = private / 'research-before.sqlite3'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
        if source.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise SystemExit('Expected schema 5; this QA runner never migrates the server.')
        source.backup(target)
    before = snapshot(backup)
    before['inode'] = db.stat().st_ino
    write_json(private / 'before.json', before)
    write_json(private / 'metadata.json', {
        'private': str(private), 'report': str(report),
        'backup_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
        'original_events': len(before['tables']['events']),
        'original_operations': len(before['tables']['operations']),
        'hard_limits_waived_by_user': True, 'seeds': [17011, 27013],
        'oracle_version': '1.1', 'model_reasoning_effort': 'low',
    })
    with zipfile.ZipFile(private / 'source-before.zip', 'w') as archive:
        for source in (root / 'live_math_mcp_prod').glob('*.py'):
            archive.write(source, source.relative_to(root))
        archive.write(root / 'AGENTS.md', 'AGENTS.md')
    status = 0
    for script, arguments, output in [
        (None, ['-m', 'pytest', '-q'], 'pytest.txt'),
        ('qa_positive_acceptance.py', ['--out', str(private / ('regression-v042-' + stamp))], 'regression-output.txt'),
    ]:
        with (private / output).open('w') as stream:
            process = subprocess.run([sys.executable] + ([script] if script else []) + arguments,
                                     cwd=root / 'live_math_mcp_prod', stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            status = process.returncode
            break
    if not status:
        import shutil
        shutil.copytree(private / ('regression-v042-' + stamp), private / 'regression-v042')
        process = subprocess.run([sys.executable, 'attention_qa.py', '--private-dir', str(private)],
                                 cwd=root / 'live_math_mcp_prod')
        status = process.returncode
    # Export preserved failures as well as successful runs. Never reuse an old project.
    from attention_report import export
    result = export(private, report)
    print(json.dumps({'report': str(report), 'result': result['result']}, ensure_ascii=False))
    raise SystemExit(status or (0 if result['result'] == 'PASS' else 1))


if __name__ == '__main__':
    main()
