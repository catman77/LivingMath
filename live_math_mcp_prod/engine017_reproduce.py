"""Fresh private017 MCP acceptance, without canonical DB, credentials or production."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import resource
import shutil
import time
from qa_positive_acceptance import write_json
from research_store import ResearchStore
from engine017_qa import Acceptance017
from engine017_controls import verify
from engine017_integrity import verify_private, cleanup_fault_copies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    base = args.work.resolve()
    base.mkdir(parents=True, mode=0o700, exist_ok=False)
    frozen = base / 'frozen'
    frozen.mkdir()
    shutil.copy2(args.package / 'pre-registration.json', frozen / 'pre-registration.json')
    shutil.copy2(args.package / 'pre-registration-seal.json', frozen / 'seal.json')
    shutil.copy2(args.package / 'frozen-oracle.py', frozen / 'oracle.py')
    policy = json.loads((frozen / 'pre-registration.json').read_text())
    if hashlib.sha256((frozen / 'oracle.py').read_bytes()).hexdigest() != policy['oracle_sha256']:
        raise ValueError('FROZEN_ORACLE_DRIFT')
    canonical_db = base / 'canonical.sqlite3'
    ResearchStore(canonical_db)
    runner = Acceptance017(base, base / 'acceptance')
    current = {'output': str(runner.out), 'private': str(runner.private), 'database': str(runner.db), 'legacy': str(runner.legacy)}
    write_json(base / 'current.json', current)
    counts = asyncio.run(runner.run())
    controls = asyncio.run(verify(current, runner.out))
    integrity = verify_private(canonical_db, runner.db)
    retired = cleanup_fault_copies(runner.private)
    checks = {'frozen_cycles': counts == policy['expected_cycles'],
        'MCP_invariants': all(r['result'] == 'PASS' for r in runner.checks),
        'artifact_controls': all(r['result'] == 'PASS' for r in controls),
        'original_prefix': all(integrity['all_original_table_prefixes'].values()),
        'append_only': all(integrity['append_only'].values()),
        'chain': integrity['chain']['hash_chain_ok'] and integrity['chain']['sqlite_integrity'] == 'ok' and not integrity['chain']['foreign_key_errors'],
        'no_verified': not integrity['new_verified_events'], 'no_grants': not integrity['own_active_permissions']}
    result = {'result': 'PASS_STAGING_REPLAY' if all(checks.values()) else 'STOP_WITH_RCA', 'checks': checks,
        'complete_cycles': counts, 'MCP_tool_calls': len(runner.calls) + len(controls), 'server_processes': runner.session_count + len(controls),
        'R2': 'PASS' if all(checks.values()) else 'FAIL', 'R3': 'PASS' if all(checks.values()) else 'FAIL',
        'production_used': False, 'proof_status': 'unverified', 'remaining_gates': {'R4': 'FAIL', 'R5': 'FAIL', 'R6': 'INCONCLUSIVE', 'R7': 'FAIL', 'R8': 'FAIL_NONBLOCKING'},
        'integrity': integrity, 'retired_fault_copy_grants': retired,
        'historical86': 'Original transcript provided. Re-running historical fixture22 requires a separately authorized private backup; it is not bundled.'}
    write_json(base / 'replay-result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('integrity', 'retired_fault_copy_grants')}, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
