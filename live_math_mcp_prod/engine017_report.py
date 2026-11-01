"""Package reviewed staging evidence; never deploys, migrates or restarts production."""
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from normalizer import canonical
from qa_positive_acceptance import write_json
from native_preview008_qa import readonly_state
from engine017_contract import Query017, SourceEnvelope017
from law_validation014_contract import ReceiptRequest014

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_tree_public(source, target):
    for p in source.rglob('*'):
        if p.is_file() and '.sqlite3' not in p.name and p.suffix not in ('.db', '.env', '.ed25519'):
            destination = target / p.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, destination)


def main():
    base = Path(Path('/tmp/lm017_path').read_text().strip())
    meta = json.loads((base / 'metadata.json').read_text())
    current = json.loads((base / 'current.json').read_text())
    out = Path(current['output'])
    read = lambda name: json.loads((out / name).read_text())
    original_result = read('result.json')
    if original_result['status'] != 'STAGING_PASS_REGRESSION_PENDING':
        raise ValueError('RETAIN_UNSUCCESSFUL_COHORT')
    checks = read('checks.json')
    artifacts = read('artifact-negative-controls.json')
    private = read('private-integrity.json')
    legacy = read('legacy-integrity.json')
    assert all(c['result'] == 'PASS' for c in checks + artifacts)
    assert all(private['all_original_table_prefixes'].values()) and all(private['append_only'].values())
    assert private['chain']['hash_chain_ok'] and not private['chain']['foreign_key_errors'] and not private['own_active_permissions']
    assert not private['new_verified_events']
    assert all(legacy['all_original_table_prefixes'].values()) and legacy['chain']['hash_chain_ok']
    assert legacy['append_only']['events:UPDATE'] is False  # Do not silently green R4.
    tests = Path('/tmp/lm017-pytest-final.txt').read_text()
    historical = json.loads((base / 'historical86-final.json').read_text())
    assert '630 passed' in tests and historical['passed'] == 86 and historical['failed'] == 0
    before = json.loads((base / 'before.json').read_text())
    after = {n: readonly_state(Path(meta[n])) for n in ('canonical', 'deployed_typed')}
    protected = json.loads((base / 'protected.json').read_text())
    differences = [n for n, value in protected.items() if sha(ROOT / n) != value]
    assert before == after and not differences
    shutil.copy2(out / 'result.json', out / 'staging-original-result.json')
    (out / 'pytest.txt').write_text(tests)
    write_json(out / 'historical86.json', historical)
    shutil.copy2(base / 'protected.json', out / 'protected-file-hashes.json')
    for name in ('live-preflight.json', 'live-postflight.json'):
        shutil.copy2(base / name, out / name)
    copy_tree_public(base / 'historical86-final', out / 'historical86')
    for name in ('live-preflight', 'live-postflight'):
        copy_tree_public(base / name, out / name)
    write_json(out / 'integrity.json', {'live_before': before, 'live_after': after, 'live_exactly_unchanged': before == after,
        'protected_files': len(protected), 'protected_differences': differences, 'engine': private, 'legacy': legacy,
        'production_research_writes': 0, 'production_code_SQL_deployments': 0, 'production_restarts': 0,
        'auth_protocol_note': 'Read-only HTTPS checks used temporary owner-authorized OAuth QA registrations, cleaned by the existing helper; no research writes.'})
    source_rows, journal, projections = {}, [], []
    with sqlite3.connect(Path(current['database'])) as c:
        c.row_factory = sqlite3.Row
        for row in c.execute('SELECT * FROM engine017_sources ORDER BY project,version'):
            source_rows[row['project']] = json.loads(row['payload_json'])
        journal = [dict(r) for r in c.execute('SELECT * FROM typed011_journal ORDER BY id')]
        projections = [dict(r) for r in c.execute('SELECT * FROM engine017_projections ORDER BY id')]
        sql = [r['sql'] + ';' for r in c.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name")]
    for row in journal:
        with (out / 'novelty-journal.jsonl').open('a') as stream:
            stream.write(canonical(row) + '\n')
    write_json(out / 'feedback-projections.json', projections)
    (out / 'staging-schema.sql').write_text('-- Observed private staging schema only; NOT a production migration.\n' + '\n'.join(sql) + '\n')
    catalogues = [json.loads(s) for s in (out / 'catalogues.jsonl').read_text().splitlines()]
    enabled = next(r for r in catalogues if r['enabled'])
    write_json(out / 'schema.json', {'source017': SourceEnvelope017.model_json_schema(), 'query017': Query017.model_json_schema(),
        'receipt014_reused': ReceiptRequest014.model_json_schema(), 'MCP_tools': enabled['tools']})
    evidence = lambda name: {'path': name, 'sha256': sha(out / name)}
    gates = [
        ('R1', 'PASS', 'No mathematical changes; prior scientific NO_GO preserved. Bound finite-source/native/oracle/unknown semantics distinguished.', ['integrity.json', 'pre-registration.json']),
        ('R2', 'PASS', '017 known-source staging:18 complete cycles on3 native families, all4 outcomes, source-owned feedback/T, singleton validation, restart and rollback.', ['typed-receipts.jsonl', 'feedback-replay.jsonl', 'checks.json']),
        ('R3', 'PASS', '017 staging: typed generic completion/premise rejected, signed native semantic binding required; new legacy explicitly labelled, historical data not upgraded.', ['artifact-negative-controls.json', 'mcp-transcript.jsonl', 'historical86.json']),
        ('R4', 'FAIL', 'Engine staging guards pass; deployed and legacy compatibility events/operations guards remain absent. Schema owner is trusted.', ['integrity.json']),
        ('R5', 'FAIL', 'Production remains0.4.2/24 tools with temporary ingress; no stable named017 HTTPS/OAuth deployment or canary.', ['live-postflight.json']),
        ('R6', 'INCONCLUSIVE', '630 regression and private historical86 pass. Portable demo replay recorded separately; independent-machine/external-person installation not established.', ['pytest.txt', 'historical86.json']),
        ('R7', 'FAIL', 'Reviewed data-only envelope/operator registration for staging native sources; no independent real external-source registration acceptance.', ['source-envelopes.json', 'schema.json']),
        ('R8', 'FAIL', 'Nonblocking scientific NO_STRUCTURAL_ADVANTAGE/NO_GO_SOURCE_DISCOVERY from016 remains unchanged;017 is not a superiority benchmark.', ['integrity.json'])]
    readiness = {'release': 'LivingMath1.0 research-engine', 'ready': False, '017_status': 'PASS_R2_R3_STAGING',
        'deployment': 'NOT_PERFORMED', 'gates': [{'gate': g, 'status': s, 'blocking': g != 'R8' and s != 'PASS',
            'owner': 'LivingMath maintainer/operator' if g != 'R8' else 'mathematical research', 'reason': reason,
            'evidence': [evidence(p) for p in paths]} for g, s, reason, paths in gates]}
    write_json(out / 'release-readiness.json', readiness)
    negative = [c for c in checks if any(k in c['invariant'] for k in ('denied', 'refusal', 'fails_closed', 'no_fake', 'rollback', 'immutable', 'active:', 'cannot_', 'alias', 'concurrent', 'legacy_completion'))]
    write_json(out / 'negative-controls.json', {'MCP_and_authority_controls': negative, 'artifact_controls': artifacts,
        'active_before_environment_controls': read('active-negative-controls.json')})
    costs = read('costs.json')
    workers = costs['workers']
    costs['grouped_worker_CPU_ns'] = {name: sum(w['CPU_ns'] for w in workers if (w['module'], w['action']) == key)
        for name, key in {'source_executor': ('engine017_executor.py', None), 'owner_activation': ('engine017_operator.py', 'activate'),
                          'owner_commit_including_semantic_validation': ('engine017_operator.py', 'commit')}.items()}
    costs['source_I_T_meter'] = 'native-I-T.jsonl: native operation/stage counts; no hidden E during prediction.'
    costs['validation_accounting'] = 'MCP validation wall in raw calls; owner commit CPU includes validation. Server protocol/normalization/I-T CPU not separately attributed; total children measured through exit.'
    costs['artifact_controls'] = read('artifact-control-costs.json')
    costs['test_wall_s'] = 59.13
    costs['regression_CPU'] = 'Not separately measured; no invented per-phase or speedup claim.'
    write_json(out / 'costs.json', costs)
    failures = json.loads((base / 'retained-failures.json').read_text())
    for failure in failures:
        old = Path(failure['output'])
        target = out / 'retained-failures' / old.name
        target.mkdir(parents=True)
        for name in ('RCA.md', 'report.md', 'result.json', 'first-failure.json', 'implementation-lock.json'):
            if (old / name).exists():
                shutil.copy2(old / name, target / name)
        if (old / 'verification-helper-source').exists():
            copy_tree_public(old / 'verification-helper-source', target / 'verification-helper-source')
    write_json(out / 'retained-failures.json', failures)
    result = {**original_result, 'status': 'PASS_R2_R3_STAGING', 'R2': 'PASS', 'R3': 'PASS', 'MCP_tool_calls': original_result['MCP_tool_calls'] + len(artifacts),
        'MCP_initialize_requests': original_result['sessions'] + len(artifacts), 'MCP_tools_list_requests': original_result['sessions'],
        'server_processes': original_result['sessions'] + len(artifacts), 'invariants_PASS': len(checks) + len(artifacts),
        'pytest_PASS': 630, 'historical86_PASS': 86, 'false_typed_grants': 0, 'model_verified_claims': 0,
        'active_own_QA_permissions': [], 'protected_files_unchanged': len(protected),
        'operator_authority': 'Local-only typed audit/activation/commit; pinned separate signed executor. Legacy API remains explicitly legacy and cannot reach typed namespaces.',
        'production_research_writes': 0, 'production_deployment_or_restart': False,
        'retained_failed_cohorts': failures, 'release_ready': False,
        'remaining_gates': {'R4': 'FAIL', 'R5': 'FAIL', 'R6': 'INCONCLUSIVE', 'R7': 'FAIL', 'R8': 'FAIL_NONBLOCKING'},
        'distribution_gate': 'See ../distribution-validation.json for exact ZIP replay outcome/hash; not inferred from staging tests.'}
    write_json(out / 'result.json', result)
    (out / 'engine-contract.md').write_text('''# Engine017 contract

`engine017_server.py` is the staging entrypoint; `LIVE_MATH_ENGINE_017` defaults disabled. Disabled mode retains the existing24 API schemas. Enabled mode keeps the existing names, mounts the four typed adapters through one017 controller and adds `research_cycle_next`, `research_cycle_history`, `research_source_contract` (27 tools). Production `mcp_server.py`/HTTP entrypoint is untouched.

For an enrolled source, use `{"api_version":"engine017/v1","project":"<registered QA project>"}`. `research_cycle_preview`/`research_cycle_next` build source closure, latest committed feedback and novelty from SQLite. Caller known_fingerprints/latest_feedback/display_label do not create state or novelty. Exact raw NativeRequest compatibility still checks IDs, row hashes, observer, version and question. C4 is rejected. Source registration/provisioning is local owner only.

`research_cycle_precommit(request,request_key)` persists the exact014 purpose/guard/ordered suffix/alternatives and proposal, no grant. Exact intent keys are idempotent under a crash-safe cross-process proposal lock; changing semantic content conflicts. `research_cycle_validate(project,move_id,event_id)` checks every014 binding plus pinned signed source receipt and reviewed native calculation; premise events and byte/signature tampering fail. `research_cycle_history` exposes persisted precommits, full I/T preview, normalization/loss ledger, activation/event links, receipts and applicability versions. Phase routes are derived from durable records, not new truth assertions. Undefined/ERROR attempts are not labelled numeric measurements.

Definitive DISCRIMINATE outcomes narrow an append-only applicability projection and preserve the independent branch. This projection version is distinct from the immutable source/obligation version. Source version changes revoke grants through existing011 rules. VALIDATE_TRANSFER remains legal after singleton only for untested guarded probes. A failed validation law requires review, not a fabricated guard. INCONCLUSIVE retains hypotheses/open obligation and waits for evidence; ERROR records no numeric observation, revokes permission on owner commit and requires owner attention. No silent retry.

Atomic owner commit: BEGIN IMMEDIATE → semantic validation → terminal status → receipt → source-owned journal → feedback projection → audit. Journal failure rolls back the entire transaction; concurrent duplicate commits yield one receipt/projection. State lives in SQLite and survives new client/server processes. All outcomes remain unverified. Known-source staging acceptance is not external physical authenticity or deployment readiness.

Explicit errors include SOURCE_VERSION_SCOPE_OBSERVER(_HASH), SOURCE_ID_REBIND, SOURCE_QUESTION_REBIND, C4_IS_NOT_AUDIT_SUFFICIENT, PRECOMMIT_KEY_CONFLICT, TYPED_ROUTE_REQUIRED, INSUFFICIENT_MEASUREMENT_BINDING, ARTIFACT_DIGEST_MISMATCH, EXECUTOR_SIGNATURE_INVALID, STALE_OBLIGATION_VERSION. Read previews return explicit denial/status; malformed/mutating requests may be MCP errors. Neither response grants execution.
''')
    (out / 'source-contract.md').write_text('''# Registered source017

See schema.json/SourceEnvelope017. Required: source_id, project/scope/version, origin/content/native-operation hashes, ordinal operations and observer, rights, provenance, unknowns, inspection status; optional law receipt hash/display label. No Python/path/plugin/execute capability. Operator registration validates project-local source root, observed payload hash, operation order/definition, scope/version/observer and pinned executor identity.

Staging accepts the reviewed native014 affine, noncommuting permutation and push/pop erasure fixtures. Common mathematical operations and selector are unchanged. The source identity excludes display labels/version bookkeeping; source/observer/operation changes require binding. Public MCP cannot register a new adapter, generate a source environment or install a validator. DECLARED_UNINSPECTED context cannot grant an experiment. External-source R7 remains FAIL until independent registration acceptance.

Each actual attempt is made by a separately pinned CLI after current scoped activation checks and before reading the sealed environment/private key. The source receipt includes hash-bound environment, exact target/ordered suffix/observation or explicit no-observation mode and native trace. An Ed25519 signature is checked against an operator-registered public key. The server can replay the reviewed computable artifact; this establishes local computational provenance, NOT physical authentication or mathematical truth. ERROR has no native trace or numeric readout; a declared withheld sensor produces INCONCLUSIVE without eliminating hypotheses. The independent frozen oracle is postmeasurement evaluator-only, denied to the server by Landlock.
''')
    (out / 'permission-matrix.md').write_text('''# Authority matrix

| Principal | Allowed | Forbidden |
|---|---|---|
| Typed MCP/model | Preview, next, history, source/novelty view, precommit, read-only semantic validation | Register source/validator, activate, execute, sign, commit, verified |
| Local owner | Provision reviewed source/schema, audit, explicit scoped activation, atomic receipt/journal/projection commit | Retroactively rewrite source/history or label computation a proof |
| Pinned native executor | Read sealed environment/key after exact grant checks, append signed bound actual attempt | Select/activate its own proposal or substitute a source/observer/word |
| Evaluator | Independent frozen oracle after actual attempt; expected fault copies | Feed oracle/target truth into inference |
| Legacy API | Existing bounded legacy workflows, explicitly legacy/v1; historic views remain legacy/historical | Reach a typed namespace, use cycle_binding or fabricated measurement_binding to obtain a typed receipt |

Legacy activation/completion retains its old bounded contract. It is not typed operator authority: all generic writers/activation/completion refuse typed namespaces and typed routing markers. Typed/legacy SQLite storage is separate. No historical outcome is upgraded. The owner/schema owner and same-authority OS account are trusted; triggers do not defend against a DB owner who can drop schema. Landlock protects the model server's reads, not a malicious owner. Physical authenticity is not established by an executor name or signature alone.
''')
    (out / 'RCA.md').write_text('''#017 RCA

Two unsuccessful cohorts are retained and linked in retained-failures.json. First:18 cycles passed but history omitted persisted precommit/selection details; contract review at actual MCP call210 failed. Minimal correction exposes existing payload/preview and derives phase routes from durable rows, with no numeric-measurement label for undefined/error attempts. Second: verification assumed the separate legacy DB had typed tables. Minimal correction makes engine-required table checks strict and legacy assessment explicit; absent legacy events/operations guards remain false. No mathematical/source/authority rule or scientific gate was weakened.

The final fresh cohort reran all18 cycles, all4 outcomes on3 families, real MCP and artifact controls,630 tests and86 historical checks. Source-specific signatures/semantic bindings, duplicate keys, rollback and restart checks pass. ERROR/INCONCLUSIVE are actual registered instrument modes, not fabricated successes. Old012/013/015/016 scientific NO_GO remains byte-identical.

Remaining product limitations are release blockers, not masked by staging PASS: deployed events/operations guards absent, temporary ingress, reviewed HTTP mount/canary/backup-restore/recovery pending, independent-machine installation and real external-source acceptance unproven. No production deployment/SQL migration/restart occurred. No mathematical or physical verification claim.
''')
    blockers = ['Production append-only migration on both deployed DBs after checked backup/restore and explicit owner review; protect events/operations/typed/history and document schema-owner limits.',
        'Stable named HTTPS/OAuth ingress and reviewed017 HTTP mounting with versioned capabilities/errors; current production remains24 tools.',
        'Real HTTPS canary, repeated clients, cancellation/deadlines/load and crash reconciliation between measurement/event/receipt; restart/transaction checks here are bounded staging evidence.',
        'Production rollout/rollback/restore rehearsal and source/SQL artifact hashes; no service/environment changes are bundled as pre-approved deployment.',
        'Independent-machine/external-person clean install (R6) and actual external source contract registration/validator/authenticity acceptance (R7).']
    write_json(out / '018-handoff.json', {'blockers': blockers, 'production_approval': 'NOT_REQUESTED_OR_GIVEN_FOR_THIS_STAGE', 'Bridge_SUTI': 'OUT_OF_SCOPE'})
    (out / 'rollback.md').write_text('''# Rollback /018 handoff

017 only ran short-lived stdio staging servers on private BackupAPI copies. No production service, environment, endpoint or real SQL was changed. There is no production migration to roll back. Stop the staging client/server and leave LIVE_MATH_ENGINE_017 unset/0 to retain the accepted24 APIs. Retain snapshots/failed cohorts rather than deleting evidence.

deployment-review.patch is an additive review of staging runtime files, not an approved production mount. It intentionally does not modify http_server.py, mcp_server.py, service units or real DBs. staging-schema.sql is observed private DDL, not a deploy script.018 must review HTTP/auth settings, source scope promotion, exact SQL guards and rollback separately. Restore tests target new disposable paths before any owner-approved real migration. See018-handoff.json for exact blockers.
''')
    controls_cost = read('artifact-control-costs.json')
    wall = costs['protocol_and_driver_wall_ns'] / 1e9
    cpu = (costs['driver_CPU_ns'] + costs['children_CPU_ns_through_exit']) / 1e9
    (out / 'report.md').write_text(f'''# LM-RELEASE-017-ENGINE

## Decision

**STATUS=PASS_R2_R3_STAGING; R2=PASS; R3=PASS.** One source-owned server controller reuses004/006/007/011/013/014. It runs actual MCP preview/precommit/next/history and signed typed receipt/feedback on three native operation families. Production is unchanged and1.0 is **not ready**: R4/R5/R7 FAIL, R6 INCONCLUSIVE, R8 nonblocking FAIL.

## Frozen cases and actual execution

Preregistration and existing native/oracle hashes were frozen before017 implementation. Affine, noncommuting permutation and push/pop erasure each have SUCCESS/FAILURE/INCONCLUSIVE/ERROR cases. Hidden environments, sensor modes and expected outcomes were fixed in advance. Discovery and I/T/law mathematics are the unchanged014/013 source mechanisms; no DSL/SMT/new fundamental operation or RH work.

**18 complete typed cycles:**9SUCCESS,3FAILURE,3INCONCLUSIVE,3ERROR, including one real successful singleton validation followup after each definitive discriminator. **229 actual MCP tool calls**,9 initialized server/client processes and6 tools/list requests; raw request/response and wire are included.226 main calls cover all families/outcomes, aliases, current source/version/observer/C4 refusals, typed generic-path denial, concurrent duplicate precommit/commit, planned journal rollback, new client/restart and source-owned next. Three additional MCP calls validate a genuine restored historical measurement and reject artifact byte tampering and an invalid executor signature even after coherent local checksum rebinding. They are read-only fault controls, not new physical cycles.

The old24 schemas remain unchanged with default-disabled flag. Enabled staging has27 tools, no register/activate/execute/commit tool. Existing typed names are reused; minimal project queries obtain source closure/latest committed feedback/journal from SQLite. The test driver never constructs the next hypothesis or T decision: it supplies only explicitly authorized owner/executor actions and postmeasurement oracle evaluation. State/history includes exact ordered suffix, source/observer/version/hash, guard, normalization/loss ledger, alternatives, T scoring and bound result/activation/audit/journal links.

## Outcomes, authority and negative controls

SUCCESS updates committed memory and chooses an untested guarded continuation. FAILURE of a proposed discriminator excludes the rejected premise in a new applicability projection and retains the independent branch; it does not globally refute the law. Singleton permits VALIDATE_TRANSFER through the existing014 selector. Raw journal conflicts require review. INCONCLUSIVE keeps hypotheses/obligation open and waits for evidence. ERROR reports no numerical observation or native trace, consumes the permission on owner commit and waits for owner review; no silent retry. Source version changes are distinct from applicability versions and revoke stale grants before environment/key reads.

Typed precommit never activates. Owner CLI explicitly audits/activates; the separately pinned native CLI reads/signs an actual bound attempt; typed validation checks every014 linkage plus registered source/hash and Ed25519/calculation semantics. Atomic owner commit appends terminal outcome, receipt, journal and feedback projection under BEGIN IMMEDIATE. Planned journal failure leaves every table/status/operation unchanged; duplicate concurrent commits produce one receipt/projection. Changed result under the same key is rejected. Empty caller history/feedback cannot revive old novelty; phase/history survives new processes. A premise event or generic legacy completion cannot complete a typed claim. Legacy remains explicitly legacy, including its old bounded activation contract; no historical record is upgraded.

All{len(checks)} final main checks and3 artifact controls pass. 630 pytest tests and86 unchanged historical real MCP checks pass. The engine DB passes{len(private['append_only'])} UPDATE/DELETE rollback probes, original-prefix checks, SQLite/FK/hash-chain; no new verified event or own active grant. Deliberately corrupted fault copies are separately retired, not counted as healthy accepted ledgers. The compatibility legacy DB explicitly lacks events/operations SQL guards; this is not hidden and does not close R4.

## Preservation and cost

Both deployed research DBs are exactly unchanged by inode/file hash/schema/all rows/sequence/chain. All{len(protected)} protected preexisting files, including mathematical implementations and old NO_GO reports, match. Read-only live HTTPS/OAuth health/tools/contract still show0.4.2/schema5/24 tools,2056 events,4813 operations, chain head5171e4495e180ad15643f0941942dd27ba903064b89a7343ccf59d3d8c0e9c57. No production research/code/SQL deployment or restart. Temporary read-only QA OAuth registrations were cleaned; no credentials are packaged.

Final main acceptance: wall{wall:.6f}s, combined driver/children CPU{cpu:.6f}s, largest child RSS{costs['largest_child_peak_RSS_KiB']}KiB. Native/owner worker CPU/wall/RSS through exit and I/T operation meter are retained; MCP validation wall and commit-validation cost are distinguished from source executor cost. Fine-grained server CPU attribution is not invented. Artifact controls separately wall{controls_cost['wall_ns']/1e9:.6f}s/CPU{controls_cost['CPU_ns']/1e9:.6f}s. Full regression wall59.13s; no speedup claim. Limits per worker are CPU90s/wall120s/AS1GiB; native/owner CLI calls have15s wall deadlines, source code/guard words are bounded. Portable replay is the same acceptance, not independent scientific evidence.

## Retained failures, delivery and018

Two failed cohorts are preserved with original raw traces/source locks and STOP_WITH_RCA reports. The first exposed missing detailed history; the second exposed a verifier assuming typed tables in legacy storage. Narrow corrections and fresh full reruns are documented in RCA.md. No FAIL was rewritten into PASS in its old cohort.

The capsule includes runtime/test sources, JSON schemas, source/engine/authority contracts, signed raw receipts, wire, oracle-after-measurement results, journal/feedback, SQL/diff review artifacts and reproduction script. It excludes private keys, credentials, canonical SQLite and foreign archives. The unapplied additive deployment-review.patch passes a clean apply check but does not mount production or implement018. ../distribution-validation.json records the exact ZIP replay hash/result after execution. Independent-machine/external-source gates stay unclosed even if local replay passes.

018 blockers are exact in018-handoff.json: real guards/backup-restore, stable HTTPS/OAuth, reviewed HTTP mount and canary, cancellation/crash/recovery/load, rollout/rollback, independent installation/external registration. Bridge/SUTI and universal autonomous mathematics remain out of scope.
''')
    runtime_names = ['engine017_contract.py', 'engine017_store.py', 'engine017_controller.py', 'engine017_measurement.py',
        'engine017_receipt.py', 'engine017_executor.py', 'engine017_operator.py', 'engine017_server.py']
    patch = '# Review-only additive017 staging runtime; no production entrypoint, environment or SQL changes.\n'
    for name in runtime_names:
        content = (SOURCE / name).read_text().splitlines(keepends=True)
        patch += ''.join(difflib.unified_diff([], content, fromfile='/dev/null', tofile='b/live_math_mcp_prod/' + name))
    (out / 'deployment-review.patch').write_text(patch)
    checkdir = base / 'patch-review-check'
    checkdir.mkdir()
    check = subprocess.run(['git', 'apply', '--check', str(out / 'deployment-review.patch')], cwd=checkdir, capture_output=True, text=True)
    write_json(out / 'patch-validation.json', {'exit_code': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr, 'applied': False, 'scope': 'Empty isolated review tree; additive files only'})
    assert check.returncode == 0
    lock = '\n'.join(sorted(d.metadata['Name'] + '==' + d.version for d in importlib.metadata.distributions())) + '\n'
    (out / 'requirements.lock').write_text(lock)
    runtime = out / 'runtime'
    runtime.mkdir()
    for p in SOURCE.glob('*.py'):
        if not p.name.startswith('test_') or p.name == 'test_engine017.py':
            shutil.copy2(p, runtime / p.name)
    shutil.copy2(SOURCE / 'normalization-schema.json', runtime / 'normalization-schema.json')
    for name in ('LM_RELEASE_017_CODEX_PROMPT.md', 'LM_RELEASE_017_ENGINE_TZ.md'):
        shutil.copy2(ROOT / 'docs' / name, out / name)
    created = [str(p.relative_to(ROOT)) for p in sorted(SOURCE.glob('engine017*.py'))] + ['live_math_mcp_prod/test_engine017.py', 'docs/superpowers/plans/2026-10-28-engine-017.md']
    write_json(out / 'changed-files.json', {'created': created, 'preexisting_modified': [], 'production_mounted_or_deployed': False})
    (out / 'README.md').write_text('''# Reproduce017 staging acceptance

Linux/Landlock and Python3.13 required. In a venv run `python -m pip install -r requirements.lock`. Then `PYTHON=/absolute/venv/bin/python bash reproduce.sh /new/private/workdir`. The directory must not exist. No canonical DB, token, original RH archive or production access is needed. The script verifies hashes and creates disposable source/operator keys/SQLite only in that directory; all next decisions come from the actual MCP server.

It reruns18 cycles on3 frozen native families/all4 outcomes, real stdio clients/restarts/duplicate commits/journal rollback/legacy routing and signed artifact attacks, then checks prefixes/chain/guards and retires copied grants. It leaves nondefinitive research outcomes honest, never verified. This is a local repeat of acceptance, not new science or independent physical authenticity. Private original historical fixture22 is not bundled:630/86 original results and full traces are included, but historical86 re-execution requires a separately authorized private backup. Independent-machine/external-source gates remain unclosed.

Contract unit tests: `LM_ENGINE017_POLICY=/absolute/capsule/pre-registration.json python -m pytest -q runtime/test_engine017.py`. Default-off schema compatibility is checked there. Read report.md, RCA.md and permission-matrix.md. deployment-review.patch/staging-schema.sql are review artifacts, NOT production installation instructions. No Bridge/SUTI or production source migration.
''')
    script = '''#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-python3}"
if [[ $# -ne 1 ]]; then
    echo 'Usage: PYTHON=/venv/bin/python bash reproduce.sh /new/private/workdir' >&2
    exit 2
fi
"$python_bin" - "$package_dir" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
manifest=json.loads((root/'manifest.json').read_text())
for name,expected in manifest.items():
    p=(root/name).resolve()
    if not p.is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
        raise SystemExit('MANIFEST_MISMATCH:'+name)
print('MANIFEST_PASS',len(manifest))
PY
exec "$python_bin" "$package_dir/runtime/engine017_reproduce.py" --package "$package_dir" --work "$1"
'''
    (out / 'reproduce.sh').write_text(script)
    (out / 'reproduce.sh').chmod(0o755)
    for p in out.rglob('*'):
        if p.is_file() and ('.sqlite3' in p.name or p.suffix in ('.db', '.env', '.ed25519')):
            raise ValueError('PRIVATE_FILE_IN_CAPSULE:' + str(p))
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('manifest.json', 'manifest.sha256')}
    (out / 'manifest.sha256').write_text(''.join(value + '  ' + name + '\n' for name, value in files.items()))
    files['manifest.sha256'] = sha(out / 'manifest.sha256')
    write_json(out / 'manifest.json', files)
    package = out.parent / (out.name + '.zip')
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    print(json.dumps({'out': str(out), 'zip': str(package), 'zip_sha256': sha(package), 'files': len(files), 'R2': 'PASS', 'R3': 'PASS'}))


if __name__ == '__main__':
    main()
