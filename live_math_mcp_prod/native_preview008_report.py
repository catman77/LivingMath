"""Evidence export and an unapplied deployment candidate; no production mutation."""
import ast
import asyncio
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys

from normalizer import digest
from qa_positive_acceptance import snapshot, write_json
from native_preview008_contract import VERSION

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_patch(base, acceptance, baseline):
    """Apply solely to a new private staging source tree and exercise both flags."""
    original = (SOURCE / 'mcp_server.py').read_text()
    needle = '    return mcp\n'
    replacement = '''    # Optional read-only preview: requires separate owner-approved deployment.
    if os.environ.get('LIVE_MATH_NATIVE_PREVIEW') == '1':
        from native_preview008_server import register_preview_tools
        register_preview_tools(mcp, store.path)
    return mcp
'''
    assert original.count(needle) == 1
    candidate = original.replace(needle, replacement)
    patch = ''.join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                       fromfile='a/live_math_mcp_prod/mcp_server.py', tofile='b/live_math_mcp_prod/mcp_server.py'))
    (base / 'deployment.patch').write_text(patch)
    stage = base / 'staging-source'; stage.mkdir()
    for p in SOURCE.iterdir():
        if p.is_file() and p.suffix in {'.py', '.json', '.txt'}:
            shutil.copyfile(p, stage / p.name)
    (stage / 'mcp_server.py').write_text(candidate)
    # Full unmodified historical86 with the opt-in flag disabled, on private backup.
    spec = importlib.util.spec_from_file_location('preview008_staged_regression', stage / 'normalization_regression.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    prior = os.environ.pop('LIVE_MATH_NATIVE_PREVIEW', None)
    try:
        reg = module.run_regression(base / 'staged-historical86', baseline / 'research-before.sqlite3')
    finally:
        if prior is not None:
            os.environ['LIVE_MATH_NATIVE_PREVIEW'] = prior
    acceptance.check('staged_disabled_historical86', reg['result'] == 'PASS')
    from native_preview008_fixtures import native_request, normalize_request
    world = load(base / 'worlds.json')[0]; db = Path(world['database'])
    async def exercise(client, tools):
        names = {t['name'] for t in tools['tools']}
        acceptance.check('staged_enabled20', len(names) == 20 and {'service_health', 'research_native_preview', 'research_normalize_preview'} <= names)
        out, _ = await acceptance.call(client, db, 'service_health', {}, 'staged:legacy_health')
        acceptance.check('staged_legacy_schema5', out['version'] == '0.4.2' and out['schema_version'] == 5)
        for name, args in [('research_native_preview', native_request(world)), ('research_normalize_preview', normalize_request(world))]:
            out, _ = await acceptance.call(client, db, name, args, 'staged:' + name)
            acceptance.check('staged:' + name + ':callable', out['status'] in {'NEW_DISTINCTION', 'COMPLETE'})
    asyncio.run(acceptance.session(db, exercise, 'staged-enabled', stage / 'mcp_server.py',
                                  {'LIVE_MATH_DB': str(db), 'LIVE_MATH_NATIVE_PREVIEW': '1'}))
    write_json(base / 'staging-review.json', {'patch_applied_only_to': str(stage), 'enabled_tools': 20,
        'disabled_legacy_invariants': reg['passed'], 'production_patch_applied': False, 'migration': 'NONE',
        'policies_changed': False, 'result': 'PASS'})


def integrity(baseline):
    meta = load(baseline / 'metadata.json')
    db = Path(meta['db']); before = load(baseline / 'before.json'); after = snapshot(db)
    old = load(baseline / 'protected-hashes.json')
    changed = [p for p, h in old.items() if sha(Path(p)) != h]
    tables = {k: after['tables'].get(k) == v for k, v in before['tables'].items()}
    previous, broken = 'GENESIS', []
    for op in after['tables']['operations']:
        expected = digest({'time': op['occurred_at'], 'action': op['action'], 'details': json.loads(op['details_json']), 'previous': previous})
        if op['previous_hash'] != previous or op['entry_hash'] != expected:
            broken.append(op['id'])
        previous = op['entry_hash']
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        sqlite_ok = conn.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = conn.execute('PRAGMA foreign_key_check').fetchall()
    good = all(tables.values()) and not changed and not broken and sqlite_ok == 'ok' and not foreign and before['inode'] == after['inode']
    good = good and sha(baseline / 'research-before.sqlite3') == meta['backup_sha256']
    return {'result': 'PASS' if good else 'FAIL', 'tables_exact': tables, 'changed_original_files': changed,
            'protected_files': len(old), 'events_before': len(before['tables']['events']), 'events_after': len(after['tables']['events']),
            'operations_before': len(before['tables']['operations']), 'operations_after': len(after['tables']['operations']),
            'inode_unchanged': before['inode'] == after['inode'], 'SQLite': sqlite_ok, 'foreign_key_errors': foreign,
            'chain_broken_ids': broken, 'chain_head': previous, 'production_writes': 0,
            'backup_sha256': meta['backup_sha256'], 'backup_exported': False, 'MCP_restarted': False}


def export(base, failure):
    meta = load(base / 'metadata.json'); baseline = Path(meta['baseline']); report = Path(meta['report'])
    report.mkdir(parents=True, exist_ok=False)
    copied = ('worlds.json', 'oracle.json', 'frozen-manifest.json', 'preregistration.json', 'pytest.txt', 'checks.json',
              'first-failure.json', 'run-failure.json', 'calls.jsonl', 'mcp-wire.jsonl', 'tools-list.jsonl',
              'read-only-before-after.jsonl', 'cost-ledger.jsonl', 'cache-secondary.json', 'deployment.patch', 'staging-review.json', 'corpus-replay-check.json')
    for name in copied:
        if (base / name).exists(): shutil.copyfile(base / name, report / name)
    for folder in ('historical86', 'staged-historical86'):
        (report / folder).mkdir()
        for name in ('result.json', 'checks.json', 'calls.json', 'stdio-wire.jsonl', 'integrity.json', 'server-stderr.txt', 'tools-list.json'):
            if (base / folder / name).exists(): shutil.copyfile(base / folder / name, report / folder / name)
    for folder, names in [('normalization004', ['P0-result.json', 'P0-failures.json', 'P0-manifest.json', 'audit-equivalence.json']),
                          ('baseline007', ['P0-result.json', 'metamorphic.json', 'attention.json', 'feedback.json'])]:
        (report / folder).mkdir()
        for name in names:
            if (base / folder / name).exists(): shutil.copyfile(base / folder / name, report / folder / name)
    if (baseline / 'development').exists(): shutil.copytree(baseline / 'development', report / 'development',
        ignore=shutil.ignore_patterns('*.sqlite3*', 'reproduction'))
    for p in SOURCE.glob('native_preview008*'):
        if p.is_file(): shutil.copyfile(p, report / p.name)
    shutil.copyfile(SOURCE / 'test_native_preview008.py', report / 'test_native_preview008.py')
    checks = load(base / 'checks.json', [])
    calls = [json.loads(line) for line in (base / 'calls.jsonl').read_text().splitlines()] if (base / 'calls.jsonl').exists() else []
    readonly = [json.loads(line) for line in (base / 'read-only-before-after.jsonl').read_text().splitlines()] if (base / 'read-only-before-after.jsonl').exists() else []
    costs = [json.loads(line) for line in (base / 'cost-ledger.jsonl').read_text().splitlines()] if (base / 'cost-ledger.jsonl').exists() else []
    write_json(report / 'mcp-transcript.json', {'transport': 'actual MCP ClientSession stdio; synthetic BackupAPI copies', 'calls': calls})
    write_json(report / 'read-only-before-after.json', {'calls': readonly, 'unchanged': all(x['all_tables_schema_sequence_chain_and_bytes_unchanged'] for x in readonly)})
    write_json(report / 'cost-ledger.json', costs)
    intact = integrity(baseline); write_json(report / 'integrity.json', intact)
    frozen = {p: sha(Path(p)) == h for p, h in load(base / 'frozen-manifest.json', {}).items()}
    write_json(report / 'frozen-checks.json', frozen)
    groups = {}
    for label, selected in [('original120', [x for x in costs if not x['fresh_heldout']]),
                            ('fresh45', [x for x in costs if x['fresh_heldout']])]:
        values = {}
        for mode in ('bounded', 'constructive'):
            rows = [x for x in selected if x['mode'] == mode]
            values[mode] = {'cases': len(rows),
                'all_native_I_T': sum(sum(x['primitive_calls'].values()) for x in rows),
                'I_native_on_successful_hidden': sum(x['cost_ledger']['interpretation']['total_native_calls'] for x in rows if x['hidden'] and x['status'] == 'NEW_DISTINCTION'),
                'cold_server_wall_ns': sum(x['cold_wall_ns'] for x in rows),
                'cold_client_roundtrip_ns': sum(x['client_roundtrip_wall_ns'] for x in rows),
                'worker_cpu_ns': sum(x['child_cpu_ns'] for x in rows),
                'parent_cpu_ns': sum(x['parent_cpu_ns'] for x in rows),
                'source_serialization_bytes': sum(x['source_serialization']['bytes'] for x in rows),
                'source_serialization_ns': sum(x['source_serialization']['wall_ns'] for x in rows),
                'max_worker_rss_KiB': max([x['child_peak_rss_KiB'] for x in rows], default=0)}
            values[mode]['compute_CPU_ns'] = values[mode]['worker_cpu_ns'] + values[mode]['parent_cpu_ns']
        ratios = {k: values['constructive'][k] / values['bounded'][k] if values['bounded'][k] else None
                  for k in ('I_native_on_successful_hidden', 'all_native_I_T', 'cold_server_wall_ns', 'cold_client_roundtrip_ns', 'worker_cpu_ns', 'compute_CPU_ns')}
        groups[label] = {'methods': values, 'C_B1_ratios': ratios}
    write_json(report / 'cost-summary.json', groups)
    good = failure is None and all(x['result'] == 'PASS' for x in checks) and intact['result'] == 'PASS' and all(frozen.values())
    result = {'P0': 'PASS' if good else 'FAIL', 'P1': 'MEASURED' if len(costs) == 330 and good else 'INCOMPLETE',
        'P2_READY': 'READY_FOR_DEPLOYMENT_REVIEW' if good else 'NO', 'integration_ready': good,
        'PRODUCTION_DEPLOYED': False, 'WITNESS_CORRECTNESS': 'PASS' if good else 'NOT_ESTABLISHED',
        'COLD_WALL_SPEEDUP': 'NO' if groups['original120']['C_B1_ratios']['cold_server_wall_ns'] is not None and
                          groups['original120']['C_B1_ratios']['cold_server_wall_ns'] >= 1 else 'INCONCLUSIVE',
        'NATIVE_CALL_REDUCTION': 'YES_BOUNDED' if good and groups['original120']['C_B1_ratios']['I_native_on_successful_hidden'] < 1 else 'NOT_ESTABLISHED',
        'UNIVERSALITY': 'NO', 'LLM_UTILITY': 'NOT_TESTED_NO_LLM_NEEDED', 'LLM_calls': 0,
        'preview_version': VERSION, 'deployed_MCP': '0.4.2', 'deployed_schema': 5, 'deployed_tools': 18,
        'normalizer': '004.1', 'I_T': '006.2 unchanged', 'constructor': '007.2 unchanged',
        'checks_PASS': sum(x['result'] == 'PASS' for x in checks), 'checks_FAIL': sum(x['result'] == 'FAIL' for x in checks),
        'MCP_calls': len(calls), 'cost_cases': len(costs), 'integrity': intact['result'], 'report': str(report / 'report.md')}
    write_json(report / 'result.json', result)
    pre = load(baseline / 'preflight.json', {})
    write_json(report / 'live-inventory.json', {'health': pre.get('health'), 'tools': [t['name'] for t in pre.get('tools', {}).get('tools', [])],
        'RH_frontier_sha256': digest(pre.get('RH_frontier')), 'RH_frontier_raw_exported': False, 'connector': 'Unknown tool; real HTTPS/OAuth read-only fallback used'})
    (report / 'report.md').write_text(f'''# LM-NATIVE-PREVIEW-008

P0={result['P0']}; P1={result['P1']}; P2={result['P2_READY']}; PRODUCTION_DEPLOYED=false. WITNESS_CORRECTNESS={result['WITNESS_CORRECTNESS']}; COLD_WALL_SPEEDUP={result['COLD_WALL_SPEEDUP']}; NATIVE_CALL_REDUCTION={result['NATIVE_CALL_REDUCTION']}; UNIVERSALITY=NO; LLM_UTILITY=NOT_TESTED,0 calls.

## Implemented boundary

Two actual MCP tools: `research_normalize_preview(project,focus,source_event_ids,query_scope,budget)` and `research_native_preview(project,active_frontier_id,active_frontier_version,source_event_ids,source_adapter_id,source_bindings,observer,question,budget)`. Strict data-only models reject extra fields; stable server-owned registry pins the reviewed native implementation. No caller code/path/plugin/verified authority is accepted. Standalone stdio is trusted local transport. The staged patch inherits existing owner OAuth; no extra access is inferred from IDs.

Each evaluation starts a new process with hard parent wall timeout, CPU/address-space/file-descriptor limits. SQLite is opened mode=ro, query_only and an authorizer rejecting writes/DDL/attach/unsafe PRAGMA. The preview never constructs ResearchStore, calls the writing auditor, inserts research rows, audits or request keys. Every successful and error call has before/after all-table/schema/sequence/inode/database-byte/hash-chain receipts. Generated results are unverified; execution_permission.allowed=false always. Only bounded exact local replay runs; no external experiment or move activation.

004.1 is unchanged. C0–C3 preserve the registered finite Dq; C4 is explanatory and audit_sufficient=false. All excluded project sources appear in the loss ledger/recovery catalog. Source identity, observer, frontier status/scope/version and exact supplied SHA-256 are checked. Source laws permit only the reviewed finite schemas; they do not prove arbitrary Python semantics. Wrong/partial/stale/guard-false or missing laws fall back to unchanged006.2. Closed/foreign/hash-drift/unsupported-adapter/C4/invalid-source inputs refuse. Source equality, lexical alias, point/germ and operation order remain distinct.

## Acceptance

{result['checks_PASS']} invariants PASS, {result['checks_FAIL']} FAIL; {len(calls)} actual MCP calls, {len(costs)} cold method measurements. See pytest.txt, historical86/result.json, normalization004/P0-result.json and baseline007/P0-result.json. The original007120 pairs are retained;45 fresh frozen held-out pairs vary the source parameters. Every witness is checked against independent raw signatures; T is compared against exact rational cost/survivor enumeration and across I strategies, including a nonoptimal-first-witness case. Native-call accounting includes I, independent T, replay, fallback and adapter leaf calls; per-stage work is retained. No oracle imported by preview/constructor.

Original120 cold costs: `{json.dumps(groups['original120'], ensure_ascii=False)}`.

Fresh45 cold costs: `{json.dumps(groups['fresh45'], ensure_ascii=False)}`.

All native-query, wall, CPU, memory and serialization measures are separate. Authoritative per-child CPU and peak RSS use OS wait4 through exit, including final JSON serialization and interpreter teardown; self-reported worker timings are diagnostic. Parent boundary thread CPU is separate; MCP event-loop/transport CPU outside the boundary is not measured. Cold MCP latency includes new process/import/source/normalization/I/T/serialization; client roundtrip additionally includes protocol/trace overhead. Fixed B1-then-C order and a finite deterministic cohort do not establish statistical speedup. The existing bounded8 normalization cache is measured only in cache-secondary.json inside one process. Fresh public MCP requests have no persistent cache, so those secondary timings are not public cached-preview speedup.

## Production gate

Canonical integrity={intact['result']}: {intact['events_after']} events/{intact['operations_after']} operations, old files and full hash-chain retained. No schema/policy/RH/SRT/FTL/SUTI changes or production restart. Deployed endpoint remains0.4.2/schema5/18 methods. New tools exist only in isolated preview and private staging. deployment.patch is unapplied to repository/production. Staging validates enabled20 tools and disabled historical86. Follow deployment-rollback.md only after separate owner authorization; no migration is required.

Known initial008 client-harness FAIL, incomplete child-CPU measurement in the prior008.1 cohort and007 binding/logging incidents are retained in RCA.md. Failure of this cohort, if any: `{failure['exception'] if failure else 'NONE'}`.
''')
    (report / 'RCA.md').write_text('''# RCA — Native Preview008

## Preserved first008 failure

Development attempt001:1 FAIL/22 PASS. The test client assumed structuredContent was present, but installed FastMCP legitimately returned the JSON result in a text content block. The server response was NEW_DISTINCTION with no grant and no DB delta. The original test, full failing pytest traceback, exact MCP request/response/wire and first-failure.json are retained under development/attempt-001. This is CLIENT_HARNESS_BUG, not a mathematical counterexample. The minimal client-decode patch accepts structuredContent or text JSON, as the legacy client already does. Attempt002 is a separate folder with23 PASS. No old FAIL is recolored; no mathematical/source/oracle guard was relaxed.

## Earlier007 incidents remain historical

007.1 initially failed PRIMITIVE_BINDING before its first pair: marshal code serialization depended on reference-sharing flags.007.2 replaced it with the stable canonical descriptor; native E/O/A AST and oracle bytes were unchanged. A retry initialization NameError and stale shell path overwrote part of the generated pytest/summary logs. Frozen source/input/oracle and worker failure survived, but the first raw pytest transcript did not. See the prior007 final RCA and corpus-replay-check.json;008 does not rewrite that history or claim lost logs were recovered.005 negative and006 prior failure packages also remain unchanged.

##008.1 cold CPU measurement gap and fresh008.2 cohort

The first full008.1 cohort `20261027T043501395880Z` passed all3261 functional checks and330 cold method calls, but its worker CPU was self-reported before final JSON serialization and interpreter teardown. OS diagnosis measured393064000ns through exit against328643401ns reported, a64420599ns gap. This invalidates the claim of a complete cold CPU ledger. It does not change witness/read-only correctness. Original raw calls/costs and preliminary result are retained; post-run review marks P1 INVALID_COST_MEASUREMENT and P2 not ready. The diagnostic, request/response and failing test are in development/cost-review.

Minimal patch: collect per-child CPU/RSS using wait4 at both Popen reap paths, including termination, without global RUSAGE_CHILDREN subtraction or cross-worker contamination; parent thread CPU is separate. Worker self-timings remain diagnostics. Added complete-exit and concurrent-worker regressions. Preview version008.2/protocol008.P0.P1.2 denotes this engineering correction; frozen004/006/007 mathematics, source laws, D, oracle and correctness/cost gates are unchanged. The fresh cohort reruns all checks/calls and asserts identical worlds (except private DB paths) and exact oracle bytes before testing. Old timing rows are never rescored or pooled. No LLM calls or production changes occurred.

## Limits

The source-local law receipt trusts finite reviewed code schemas and guarded parameters, not arbitrary program semantics. Read-only finite witnesses do not verify mathematics or grant execution. Cold worker startup/normalization and independent T can dominate query savings; no universal search, RH result, statistical wall speedup or LLM utility follows. Expected negative controls and intentional resource faults are not repaired mathematical defects.
''')
    if failure:
        with (report / 'RCA.md').open('a') as out: out.write('\n## Current cohort FAIL\n\n```text\n' + failure['traceback'] + '\n```\n')
    (report / 'deployment-rollback.md').write_text('''# Deployment and rollback — owner review required

Status: unapplied candidate. No migration; schema5 and all policies/data remain unchanged.

1. Review deployment.patch, code.diff, adapter registry/hash/Python runtime binding, resource limits and all P0/P1 evidence. The two names do not conflict with existing18 tools. Existing owner OAuth must protect the added tools; stdio is trusted local access only.
2. Obtain separate explicit owner deployment approval. Record target source/service configuration and original18-tool schema; create a private SQLite BackupAPI snapshot and full tables/hash-chain manifest before touching deployed files. Save old source/env/service files for rollback.
3. Copy native_preview008_contract/engine/server/worker.py and native_preview008-adapters.json into the deployed source directory. Existing004.1/006.2/007.2 dependencies and causal-QA requirements must be installed in the serving environment. Do not copy QA fixtures, oracle, traces or databases into public paths.
4. Apply deployment.patch only after review (`git apply --check` first). Leave LIVE_MATH_NATIVE_PREVIEW unset for disabled legacy18-tool smoke; verify historical86 on an isolated copy. Enable LIVE_MATH_NATIVE_PREVIEW=1 only in the intended service environment, then restart that service and verify authenticated tools/list20. Health stays0.4.2/schema5; preview_version distinguishes008.2. No DB migration or policy alteration is part of this patch.
5. Live smoke is read only: service_health/research_frontier and authorized normalization/native calls with valid source IDs/hashes, plus denial controls. Existing RH sources without the reviewed native007 representation must refuse native preview; never manufacture their witnesses. Recheck all rows, inode/schema/chain before/after. Reconnect/refresh the ChatGPT app to reload tools/list only after a successful approved rollout; until then production still has18 tools.
6. Rollback: unset LIVE_MATH_NATIVE_PREVIEW, restore original mcp_server.py/source/env and restart the target service. Verify18 tools and unchanged canonical data/hash-chain. No research DB restoration should be necessary because preview has no writes; preserve any unexpected delta and stop for RCA rather than overwriting data. Never restore a backup over newer unrelated user events.
''')
    (report / 'README.md').write_text('''# Reproduction and review

No production deployment has occurred. Use repository .venv and existing requirements-causal-qa.txt. Run `./reproduce.sh --help` safely. A full `./reproduce.sh` makes a new private BackupAPI baseline/cohort, runs local tests, historical86,0042304 comparisons,007 regression, real two-tool MCP/P1 and private staged-patch checks. It makes no LLM calls or production research writes. Live inventory uses existing local owner OAuth; raw auth/canonical snapshots are never exported. Each cohort is unique and retained after failure.

Standalone: `.venv/bin/python live_math_mcp_prod/native_preview008_server.py --db /absolute/authorized/existing-schema5.sqlite3`. Public arguments are specified by tools/list; bind every requested event ID to the canonical normalizer digest. Use source_adapter_id=livingmath.native007.reviewed.v1 only for its reviewed native_007/v1 source representation. No general Python code or arbitrary source adapter can be passed. Requests are computation previews and always deny execution permission.

Offline verification: run `verify_artifacts.py` from the repository environment. Frozen manifests refer to source paths; manifest-sha256.json covers exported bytes. Deployment/rollback instructions are review material, not authorization to deploy.
''')
    (report / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/native_preview008_qa.py" "$@"
'''); (report / 'reproduce.sh').chmod(0o755)
    (report / 'verify_artifacts.py').write_text('''import hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parent
load=lambda n:json.loads((r/n).read_text())
c={'hashes':all(hashlib.sha256((r/p).read_bytes()).hexdigest()==h for p,h in load('manifest-sha256.json')['files'].items()),'readonly':load('read-only-before-after.json')['unchanged'],'integrity':load('integrity.json')['result']=='PASS','secrets':load('secret-scan.json')['result']=='PASS','checks':all(x['result']=='PASS' for x in load('checks.json')),'P0':load('result.json')['P0']=='PASS','frozen':all(load('frozen-checks.json').values())}
print(json.dumps({'result':'PASS' if all(c.values()) else 'FAIL','checks':c},indent=2))
raise SystemExit(0 if all(c.values()) else 1)
''')
    newfiles = [p for p in SOURCE.glob('native_preview008*') if p.is_file()] + [SOURCE / 'test_native_preview008.py']
    diff = ''.join(''.join(difflib.unified_diff([], p.read_text().splitlines(True), fromfile='/dev/null', tofile='b/' + str(p.relative_to(ROOT)))) for p in newfiles)
    (report / 'code.diff').write_text(diff)
    write_json(report / 'changed-files.json', {'added': [str(p.relative_to(ROOT)) for p in newfiles], 'modified_existing_files': [], 'production_patch': 'deployment.patch (unapplied)', 'production_deployed': False})
    from attention_qa import configure
    cfg = configure(); password = Path(cfg['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode()
    matches, forbidden = [], []
    for p in report.rglob('*'):
        if not p.is_file(): continue
        content = p.read_bytes()
        if len(password) >= 8 and password in content or re.search(rb'Bearer[ \t]+[A-Za-z0-9._~+/-]{20,}', content): matches.append(str(p.relative_to(report)))
        if '.sqlite' in p.name or p.name in {'before.json', 'server.env', 'auth.json'}: forbidden.append(str(p.relative_to(report)))
    write_json(report / 'secret-scan.json', {'result': 'PASS' if not matches and not forbidden else 'FAIL', 'matches': matches, 'forbidden_files': forbidden, 'canonical_backup_exported': False})
    for folder in (report / 'historical86', report / 'staged-historical86'):
        folder.chmod(0o700)
        for p in folder.iterdir(): p.chmod(0o600)
    write_json(report / 'manifest-sha256.json', {'algorithm': 'sha256', 'files': {str(p.relative_to(report)): sha(p) for p in sorted(report.rglob('*')) if p.is_file() and p.name != 'manifest-sha256.json'}})
    write_json(base / 'run-state.json', {'stage': 'COMPLETE' if good else 'FAILED', 'result': result})
    return result
