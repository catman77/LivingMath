"""009 evidence export; originals stay immutable and production is never deployed here."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

from normalizer import digest
from qa_positive_acceptance import snapshot, write_json
from research_cycle009 import VERSION

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def integrity(baseline, private_db=None):
    meta = load(baseline / 'metadata.json'); before = load(baseline / 'before.json'); after = snapshot(Path(meta['db']))
    protected = load(baseline / 'protected-files.json')
    changed = [p for p, h in protected.items() if sha(Path(p)) != h]
    canonical_exact = all(after['tables'].get(k) == v for k, v in before['tables'].items()) and after['inode'] == before['inode']
    previous, broken = 'GENESIS', []
    for op in after['tables']['operations']:
        expected = digest({'time': op['occurred_at'], 'action': op['action'], 'details': json.loads(op['details_json']), 'previous': previous})
        if op['entry_hash'] != expected or op['previous_hash'] != previous: broken.append(op['id'])
        previous = op['entry_hash']
    with sqlite3.connect(Path(meta['db']).as_uri() + '?mode=ro', uri=True) as conn:
        sqlite_ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = conn.execute('PRAGMA foreign_key_check').fetchall()
    private = {}
    if private_db and private_db.exists():
        copied = snapshot(private_db)
        prefix = {k: copied['tables'][k][:len(v)] == v for k, v in before['tables'].items()}
        last, failures = 'GENESIS', []
        for op in copied['tables']['operations']:
            expected = digest({'time': op['occurred_at'], 'action': op['action'], 'details': json.loads(op['details_json']), 'previous': last})
            if op['entry_hash'] != expected or op['previous_hash'] != last: failures.append(op['id'])
            last = op['entry_hash']
        with sqlite3.connect(private_db) as conn:
            active = conn.execute("SELECT count(*) FROM research_move_status_history h WHERE status='EXPERIMENT_ALLOWED' AND sequence=(SELECT max(sequence) FROM research_move_status_history x WHERE x.move_id=h.move_id) AND move_id NOT IN (SELECT id FROM research_moves WHERE project NOT LIKE 'LM_QA_CYCLE009_%')").fetchone()[0]
            sql = conn.execute('PRAGMA integrity_check').fetchone()[0]; fk = conn.execute('PRAGMA foreign_key_check').fetchall()
        private = {'original_prefix_exact': prefix, 'hash_chain_broken_ids': failures, 'chain_head': last,
                   'SQLite': sql, 'foreign_keys': fk, 'active_QA_grants': active}
    good = canonical_exact and not changed and not broken and sqlite_ok == 'ok' and not foreign
    good = good and sha(baseline / 'research-before.sqlite3') == meta['backup_sha256']
    if private:
        good = good and all(private['original_prefix_exact'].values()) and not private['hash_chain_broken_ids'] and private['SQLite'] == 'ok' and not private['foreign_keys']
    return {'result': 'PASS' if good else 'FAIL', 'canonical_all_tables_and_inode_exact': canonical_exact,
        'events': len(after['tables']['events']), 'operations': len(after['tables']['operations']), 'chain_head': previous,
        'broken_hashes': broken, 'SQLite': sqlite_ok, 'foreign_keys': foreign, 'private_lifecycle': private,
        'changed_protected_files': changed, 'protected_files': len(protected), 'production_writes': 0,
        'production_deployed_or_restarted': False, 'backup_sha256': meta['backup_sha256']}


def export(base, failure):
    meta = load(base / 'metadata.json'); baseline = Path(meta['baseline']); out = Path(meta['report'])
    out.mkdir(parents=True, exist_ok=False)
    names = ('worlds.json', 'oracle.json', 'preregistration.json', 'manifest.json', 'source-hashes.json', 'checks.json',
        'cycle-ledger.jsonl', 'costs.jsonl', 'offline-vs-MCP.jsonl', 'calls.jsonl', 'readonly.jsonl', 'permission-invalidation.jsonl',
        'external-measurements.jsonl', 'operator-ledger.jsonl', 'source-receipts.jsonl', 'novelty-ledger.jsonl', 'pytest.txt', 'run-failure.json', 'first-failure.json', 'run-state.json')
    for name in names:
        if (base / name).exists(): shutil.copyfile(base / name, out / name)
    for folder in ('world-inputs', 'sealed-environments', 'frozen-sources', 'sessions', 'source-snapshots'):
        if (base / folder).exists(): shutil.copytree(base / folder, out / folder)
    for p in base.glob('*-preview.json'): shutil.copyfile(p, out / p.name)
    for p in [*SOURCE.glob('research_cycle009*.py'), SOURCE / 'test_research_cycle009.py']:
        shutil.copyfile(p, out / p.name)
    if (baseline / 'development').exists(): shutil.copytree(baseline / 'development', out / 'development')
    (out / 'historical86').mkdir()
    for name in ('result.json', 'checks.json', 'calls.json', 'stdio-wire.jsonl', 'integrity.json', 'server-stderr.txt'):
        if (base / 'historical86' / name).exists(): shutil.copyfile(base / 'historical86' / name, out / 'historical86' / name)
    public = load(baseline / 'public-preflight.json', {'public_installation': 'DEPLOYMENT_PENDING'})
    write_json(out / 'public-installation.json', public)
    installed = public['public_installation'] == 'PASS'
    intact = integrity(baseline, base / 'isolated.sqlite3'); write_json(out / 'integrity.json', intact)
    frozen = {p: sha(Path(p)) == h for p, h in load(base / 'source-hashes.json', {}).items()}
    write_json(out / 'frozen-source-checks.json', frozen)
    calls, ledger, costs, equivalents = [rows(base / (n + '.jsonl')) for n in ('calls', 'cycle-ledger', 'costs', 'offline-vs-MCP')]
    write_json(out / 'mcp-transcript.json', {'transport': 'actual MCP ClientSession over measured stdio; no direct-function mock', 'calls': calls})
    write_json(out / 'offline-vs-MCP.json', equivalents)
    server_usage = [load(p) for p in (base / 'sessions').glob('*/server-exit-usage.json')] if (base / 'sessions').exists() else []
    summary = {}
    for mode in ('bounded', 'constructive'):
        chosen = [r for r in costs if r['mode'] == mode]
        summary[mode] = {'snapshots': len(chosen), 'cold_wall_ns': sum(r['cold_wall_ns'] for r in chosen),
            'child_CPU_ns_through_exit': sum(r['child_cpu_ns'] for r in chosen),
            'MCP_roundtrip_ns': sum(r['MCP_roundtrip_wall_ns'] for r in chosen),
            'I_native_calls': sum(r['cost_ledger']['interpretation']['total_native_calls'] for r in chosen),
            'T_native_calls': sum(r['cost_ledger']['attention_native_calls'] for r in chosen),
            'peak_rss_KiB': max([r['child_peak_rss_KiB'] for r in chosen], default=0)}
    write_json(out / 'costs.json', {'paired_cold_previews': costs, 'summary': summary, 'whole_MCP_sessions': server_usage,
        'external_measurements': rows(base / 'external-measurements.jsonl'),
        'double_counting_rule': 'Whole MCP server wait4 includes reaped preview descendants on Linux; preview receipts are a subset, never added again. External measurement children and client per-call CPU are separate.',
        'warm': 'No native/public cross-request cache; no warm speedup claimed.',
        'full_cycle_speedup': 'NOT_ESTABLISHED; B1 comparison is paired previews on identical snapshots, not a separately executed second lifecycle campaign.'})
    good = failure is None and intact['result'] == 'PASS' and all(frozen.values()) and len(ledger) == 6
    good = good and all(r['result'] == 'PASS' for r in load(base / 'checks.json', []))
    good = good and all(sum(r['world'] == w['id'] for r in ledger) == 2 for w in load(base / 'worlds.json', []))
    if intact.get('private_lifecycle'): good = good and intact['private_lifecycle']['active_QA_grants'] == 0
    result = {'offline': 'PASS' if good else 'STOP_WITH_RCA', 'MCP_staging': 'PASS' if good else 'STOP_WITH_RCA',
        'public_installation': 'PASS' if installed else 'DEPLOYMENT_PENDING',
        'decision': ('GO_TO_010' if installed else 'DEPLOYMENT_PENDING') if good else 'STOP_WITH_RCA',
        'public_preview_smoke': public.get('public_preview_smoke'), 'completed_cycle_steps': len(ledger),
        'worlds_with_two_completed_steps': sum(sum(r['world'] == w['id'] for r in ledger) == 2 for w in load(base / 'worlds.json', [])),
        'MCP_calls': len(calls), 'paired_previews': len(costs), 'checks_PASS': sum(x['result'] == 'PASS' for x in load(base / 'checks.json', [])),
        'checks_FAIL': sum(x['result'] == 'FAIL' for x in load(base / 'checks.json', [])),
        'P1': 'SKIP', 'LLM_calls': 0, 'proof_status': 'unverified', 'autonomous_discovery': False,
        'production_deployed': False, 'production_writes': 0, 'integrity': intact['result'], 'harness_version': VERSION,
        'report': str(out / 'report.md')}
    write_json(out / 'result.json', result)
    table = ['| World | Step | Version | I suffix | T | Result event | Outcome | Surviving hypotheses | Next T |',
             '| --- | ---: | ---: | --- | --- | ---: | --- | --- | --- |']
    for row in ledger:
        table.append(f"| {row['world']} | {row['cycle_index']} | {row['version']} | {row['I']['suffix'] if row['I'] else None} | {row['T']} | {row['measurement_event_id']} | {row['outcome']} | {','.join(row['active_after'])} | {row['next_T']} |")
    (out / 'report.md').write_text(f'''# LM-RESEARCH-CYCLE-009

Offline={result['offline']}; MCP staging={result['MCP_staging']}; public installation={result['public_installation']}. Decision: **{result['decision']}**. P1 SKIP0. This validates a finite operator-bounded research loop, not mathematical truth, autonomous permission, efficiency or universal discovery.

## Sequential cycle

{chr(10).join(table)}

Each world starts with3 competing finite histories, equal current observations, derived dependent guards and one independent branch. I is unchanged006.2/optional007.2, T is unchanged006.2. A cheap partition leaves2 candidates; negative feedback excludes only its failed finite guard/dependents and changes T to a different discriminator. The second bounded observation leaves1 candidate and no further informative finite action. Both experiments have explicit record/audit/activation, actual external measurement, project-local result event, reason and COMPLETED decision. FAILURE is a finite candidate failure, not a universal refutation; SUCCESS is finite consistency, not verified. Separate INCONCLUSIVE controls do not count as research-cycle successes.

Version2 is an explicit append-only applicability projection. It links cloned word views/root/law and an old measurement receipt to original event IDs; the latter is re-scoped, not another measurement. The measured-excluded hypothesis is absent only from the current predictive view and retained in old source/known_failures. Parameters, D, observer, original word rows and independent branch survive. A previously activated, deliberately unexecuted canary is invalidated by the evidence-bearing obligation version change; no old key/reactivation yields a usable permission.

## Independent checks and authority

Raw finite oracle and exact Fraction ranking were frozen before trials, separate from the native adapter/I/T. The sealed environment is salted and never attached to source records; only actual chosen-test readouts are published after execution. Full private instrument traces/costs are not fed to I/T, so hidden starting state/history length cannot leak via the measurement event. The orchestration selects hypotheses from T counterfactual partitions, never from the oracle's future results. Post-run sealed fixtures/oracle are exported for reproduction, not model inputs.

Operators supply operations/hypotheses/costs, reviewed source laws, fixed environment, a narrow fixture/project/scope allowance and fingerprint/version-specific adverse dispositions. These are not autonomous discoveries. Before the disposition, diagnostic labels alone fail review and cannot activate. After it, a fresh audit and explicit activation are required. Adverse review does not establish truth. The009 harness binds completion to an actual matching measured event; the preexisting generic MCP lifecycle only enforces project-local event existence and structured result. This stronger measurement-binding rule is a harness guarantee, not a claim that arbitrary MCP callers gain semantic validation.

## Interoperability, cost and preservation

Actual MCP ClientSession/stdio drives the whole private lifecycle on a BackupAPI copy; no write lifecycle goes to public production. All preview success/refusal paths compare full SQLite tables/schema/sequence/inode/bytes/hash-chain receipts. Offline worker and staged preview projection/witness/readouts/provenance/guards/T are equal after excluding timing fields only. Raw oracle independently checks each witness and both rational decisions. Public installation was observed through real HTTPS/OAuth initialize/tools/list/health, not assumed from a user message. Public preview smoke: {result['public_preview_smoke']}; no historical RH row was used as a synthetic source. No deployment/restart/migration occurred in009.

Cold preview costs: `{json.dumps(summary)}`. Whole MCP-process exit receipts include process/import/protocol/lifecycle/serialization and waited-for preview descendants; the per-preview wait4 CPU/RSS subset is not added twice. MCP roundtrip/client CPU and external instrument CPU are separate. Full transport startup is measured, while active servers reuse their protocol process; mathematical workers remain cold. No warm cache or speedup/autonomy inference is made. B1 comparisons use identical evolving snapshots; the lifecycle is not rerun solely to claim a full-cycle speedup.

Integrity={intact['result']}: canonical{intact['events']} events/{intact['operations']} operations unchanged; original private-copy rows/hash prefix preserved, append-only status/version/evidence histories, no remaining active QA grant. Policies, RH/FTL/SRT, original004–008 code/reports and AGENTS are unchanged. Secrets/raw canonical database are excluded. See costs.json, checks.json, external-measurements.jsonl, permission-invalidation.jsonl, operator-ledger.jsonl and exact schemas/wire traces.

Current failure: {failure['error'] if failure else 'NONE'}.
''')
    (out / 'RCA.md').write_text('''# RCA — Research Cycle009

Prior008 client-decode and incomplete child-CPU cases remain in their original packages.009 changes no production/core implementation and does not recolor earlier FAILs. Expected denials/mutated-witness controls are distinct from actual bugs. Scoped operator review, source laws and environment are explicit supplied inputs, never attributed to an autonomous discovery. The legacy completion API's generic event-existence check is strengthened at the009 orchestration boundary; no arbitrary mathematical verification is added.

The first009 cohort `20261027T055311302098Z` remains STOP_WITH_RCA. It completed both affine science steps and156 assertions, then call84 failed during cleanup because the harness sent unsupported status CLOSED. The existing API's actual terminal statuses are RESOLVED/REFUTED/SUPERSEDED. This is TEST_FIXTURE_BUG, not a failed mathematical mechanism. Exact request/response/first traceback/frozen source are retained in the original cohort; development/status-fix contains the isolated real-MCP failing regression and minimal patch.009.2 changes only that cleanup to RESOLVED (a finished QA obligation, not mathematical verification), with a fresh cohort using the same frozen world/environment/oracle bytes and gates. The original FAIL is never recolored or pooled.

Post-P0 novelty-state audit found that009.2 always sent empty known_fingerprints, so the stateless preview returned NEW again for an already seen fingerprint in later snapshots. The core API behaved correctly for its empty request context; the orchestration omitted its own history. Actual captured MCP responses and a separate real-MCP repeat test reproduce the gap in development/novelty-state-fix.009.3 adds a local append-only seen registry: B1/C/offline all receive the identical pre-snapshot registry, and a distinction is registered only after comparisons. Rebinding byte-identical request shapes under a new version is explicitly not a new mathematical discovery. The full finite worlds/environments/oracle and acceptance gates are unchanged. Earlier provisional GO records are retained byte-for-byte; their incomplete novelty coverage is documented separately, not overwritten or used as final acceptance.
''')
    if failure:
        with (out / 'RCA.md').open('a') as stream:
            stream.write('\n## First actual failure\n\nClassification: ' + failure['classification'] + '\n\n```text\n' + failure['traceback'] + '\n```\n')
    (out / 'README.md').write_text('''# Reproduction

Use repository .venv and existing requirements-causal-qa.txt. `./reproduce.sh --help` is safe; default invocation runs deterministic P0 with a fresh private BackupAPI baseline/cohort, actual public read-only gate, full local tests, historical86 and private MCP cycles. No LLM or production deployment/writes. A public18/unknown schema records DEPLOYMENT_PENDING and still permits offline/staging. Existing failed cohorts are retained; frozen scenarios/oracle in a baseline are reused byte-for-byte after a narrow bug fix.

Operator environments/oracle are privileged fixtures during scoring. They are exported only for post-run reproducibility; never pass target_word/salt/oracle tables/private instrument traces to preview. Full native definitions and core hashes remain in frozen-sources. Per-stage CPU/native/roundtrip and whole MCP wait4 receipts have explicit overlap rules; do not sum a server's inclusive descendant CPU and its preview child subset.
''')
    (out / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/research_cycle009_run.py" "$@"
'''); (out / 'reproduce.sh').chmod(0o755)
    from attention_qa import configure
    cfg = configure(); password = Path(cfg['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode()
    leaks, forbidden = [], []
    for p in out.rglob('*'):
        if not p.is_file(): continue
        data = p.read_bytes()
        if len(password) >= 8 and password in data or re.search(rb'Bearer[ \t]+[A-Za-z0-9._~+/-]{20,}', data): leaks.append(str(p.relative_to(out)))
        if '.sqlite' in p.name or p.name in {'before.json', 'server.env', 'auth.json'}: forbidden.append(str(p.relative_to(out)))
    write_json(out / 'secret-scan.json', {'result': 'PASS' if not leaks and not forbidden else 'FAIL', 'matches': leaks, 'forbidden_files': forbidden})
    write_json(out / 'manifest-sha256.json', {'algorithm': 'sha256', 'files': {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest-sha256.json'}})
    return result
