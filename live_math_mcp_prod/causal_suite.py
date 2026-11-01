"""One-command fresh experiment with OAuth transport continuation, no resampling."""
import json
from pathlib import Path
import subprocess
import sys

from causal_finalize import finalize


def main():
    source = Path(__file__).resolve().parent
    process = subprocess.Popen([sys.executable, str(source / 'causal_qa.py'), *sys.argv[1:]],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    private = None
    for line in process.stdout:
        print(line, end='', flush=True)
        try:
            item = json.loads(line)
            if 'private' in item:
                private = Path(item['private'])
        except ValueError:
            pass
    code = process.wait()
    if private is None:
        raise SystemExit(code)
    outcomes = [json.loads(line) for line in (private / 'model_outputs.jsonl').read_text().splitlines()] if (private / 'model_outputs.jsonl').exists() else []
    if len(outcomes) < 432:
        # Resume only a confirmed expired-token transport failure, never a core failure.
        wire = [json.loads(line) for line in (private / 'mcp-wire.jsonl').read_text().splitlines()]
        failures = [json.loads(line) for line in (private / 'failures.jsonl').read_text().splitlines()] if (private / 'failures.jsonl').exists() else []
        report = Path(json.loads((private / 'metadata.json').read_text())['report'])
        integrity = json.loads((report / 'integrity.json').read_text()) if (report / 'integrity.json').exists() else {}
        if integrity and (not all(integrity['original_rows_unchanged'].values()) or not integrity['independent_hash_replay']['ok']
                          or integrity['sqlite_integrity_check'] != 'ok' or integrity['foreign_key_check']):
            raise SystemExit('Critical data integrity failure; no continuation: ' + str(private))
        if not any(message.get('http_status') == 401 for message in wire) or any(f['classification'] != 'TRANSPORT_FAILURE' for f in failures):
            raise SystemExit('Incomplete experiment preserved. No automatic sampling after an unclassified/core failure: ' + str(private))
        subprocess.run([sys.executable, str(source / 'causal_recover.py'), '--private-dir', str(private)], check=True)
    print(finalize(private))


if __name__ == '__main__':
    main()
