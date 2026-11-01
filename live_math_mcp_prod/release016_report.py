"""Static017 audit and016 delivery. Never installs code/SQL or calls an executor."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import zipfile

from qa_positive_acceptance import write_json, snapshot
from native_preview008_qa import readonly_state
from operational013_report import chain
from normalizer import digest

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    base = Path(Path('/tmp/lm016_path').read_text().strip())
    meta = json.loads((base / 'metadata.json').read_text())
    out = Path(meta['out'])
    read = lambda name: json.loads((out / name).read_text())
    experiment = read('experiment-result.json')
    if experiment['status'] != 'PASS_SOURCE_BOUND_N_H_TRANSFER':
        raise ValueError('STOP: retain original experiment failure; do not package a success')
    before = json.loads((base / 'before.json').read_text())
    after = {n: readonly_state(Path(meta[n])) for n in ('canonical', 'deployed_typed')}
    protected = json.loads((base / 'protected.json').read_text())
    differences = [p for p, h in protected.items() if sha(ROOT / p) != h]
    historical = json.loads((base / 'historical86.json').read_text())
    pytest = Path('/tmp/lm016-pytest.txt').read_text()
    assert '618 passed' in pytest and historical['passed'] == 86 and historical['failed'] == 0
    assert before == after and not differences
    db = base / 'private-QA.sqlite3'
    old, new = snapshot(base / 'canonical.sqlite3'), snapshot(db)
    prefixes = {t: new['tables'][t][:len(rows)] == rows for t, rows in old['tables'].items()}
    assert all(prefixes.values())
    integrity = {'live_before': before, 'live_after': after, 'live_exactly_unchanged': before == after,
        'protected_files': len(protected), 'protected_differences': differences,
        'all_original_private_prefixes': prefixes, 'private_chain': chain(db),
        'private_append_only': read('private-integrity.json')['append_only'],
        'active_own_QA_permissions': read('private-integrity.json')['active_permissions']}
    assert not integrity['active_own_QA_permissions'] and all(integrity['private_append_only'].values())
    write_json(out / 'integrity.json', integrity)
    for name in ('historical86.json', 'live-preflight.json', 'clean-install-result.json'):
        shutil.copy2(base / name, out / name)
    shutil.copy2(base / 'clean-install.log', out / 'clean-install.log')
    (out / 'pytest.txt').write_text(pytest)
    # Full MCP request/response, excluding the private BackupAPI database itself.
    for folder in ('historical86', 'live-preflight'):
        for p in (base / folder).rglob('*'):
            if p.is_file() and '.sqlite3' not in p.name and p.suffix != '.db':
                target = out / folder / p.relative_to(base / folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
    live = json.loads((base / 'live-preflight.json').read_text())
    summary = read('comparison.json')['summary']
    costs = read('costs.json')
    source = read('source-audit.json')
    costs['source_regeneration'] = source['regeneration_cost']
    costs['streaming_source_audit'] = source['streaming_audit_cost']
    costs['source_call_ledger'] = {'known_original_export_native_evaluate_calls': 6,
        'known_export_count_basis': 'Unchanged reproducer:3 CASEs, each main and reflected evaluation; source hash pinned.',
        'new_t15_anchor_native_calls': 2, 'postseal_t15_target_native_calls': 4,
        'fresh_postactivation_t15_native_calls': 1, 'total_native_evaluate_calls': 13,
        'learners_native_evaluate_calls': 0, 'B2_source_formula_forecasts': 16,
        'C_R_step_applications_including_two_routes': 48, 'C_H_applications_including_two_routes': 32,
        'unique_h_at_t15': 4, 'LLM_calls': 0}
    costs['accounting'] = {'P0_P3_total': 'Includes archive extraction, BackupAPI private copy, original source reproduction/audit, anchors, all models,4 target reads, typed native/receipt, closure/integrity. Does not include later pytest/historical86/OAuth/packaging/dependency install.',
        'all_models_preseal': 'C, B2–B5 share one confined process; only their combined CPU/wall is measured. No per-model timing or speed advantage is inferred.',
        'clean_replay': 'Companion distribution-validation.json records actual fresh-venv replay and exact ZIP hash.',
        'historical_regression': 'Full MCP trace and86 outcomes provided; full-suite wall65.74s. Regression CPU and dependency-install CPU not measured.',
        'source_regeneration_is_shared': 'Do not add its cost twice to P0_P3_total.'}
    write_json(out / 'costs.json', costs)
    # Derived baseline diagnostic: retain first concrete miss without calling it
    # a falsification of the successful guarded source identity.
    predictions = [json.loads(s) for s in (out / 'sealed-predictions.jsonl').read_text().splitlines()]
    reveals = [json.loads(s)['native'] for s in (out / 'target-reveal.jsonl').read_text().splitlines()]
    failures = []
    for method in ('B3_geometric', 'B4_linear_n_Hermite_h'):
        row = next(r for r in read('comparison.json')['per_address'] if not r['scores'][method]['containment_PASS'])
        p = next(p for p in predictions if p['index'] == row['index'] and p['binding']['h'] == row['h'])
        actual = next(a for a in reveals if a['index'] == row['index'] and a['h'] == row['h'])
        failures.append({'method': method, 'h': row['h'], 'address': actual['source_address'],
            'origin_id': actual['origin_id'], 'prediction': p[method], 'native': actual['value'], 'score': row['scores'][method]})
    write_json(out / 'baseline-counterexamples.json', failures)
    evidence = lambda name: {'path': name, 'sha256': sha(out / name)}
    gates = [
        ('R1', 'PASS', 'Source, scope-specific blind targets, containment/cocycle and honest identity/discovery taxonomy checked.', ['source-audit.json', 'pre-registration.json', 'comparison.json', 'blind-history-audit.json']),
        ('R2', 'FAIL', '016 is an owner-run private QA lifecycle. No complete engine-owned014/016 cycle/feedback/new move over staging MCP with all outcomes.', ['typed-ledger.jsonl', 'live-preflight.json']),
        ('R3', 'INCONCLUSIVE', 'Isolated typed receipt strict; universal versioned claim routing and legacy-only generic completion for external sources not established.', ['typed-ledger.jsonl', 'historical86.json']),
        ('R4', 'FAIL', 'Deployed events/operations have no append-only triggers. Private014 guards pass; owner/schema-owner remains trusted.', ['deployed-schema-readonly.json', 'integrity.json']),
        ('R5', 'FAIL', 'OAuth/24 tools work, but current ingress remains temporary Quick Tunnel; stable named endpoint/capability/version/error contract incomplete.', ['live-preflight.json']),
        ('R6', 'INCONCLUSIVE', 'Fresh venv installed from lock; capsule replay checked separately on this host. Separate-machine install and redistribution rights for original RH ZIP not demonstrated.', ['requirements.lock', 'clean-install-result.json']),
        ('R7', 'FAIL', 'Public tools accept registered QA sandbox adapters; arbitrary external versioned source registration/authenticity boundary unavailable.', ['live-preflight.json']),
        ('R8', 'FAIL', 'NO_STRUCTURAL_ADVANTAGE: preregistered B2 source formula matches16/16. Nonblocking for research-engine1.0.', ['comparison.json'])]
    readiness = {'release': 'LivingMath1.0 research-engine', 'ready': False, '016_math_gate': 'PASS_SOURCE_BOUND_N_H_TRANSFER',
        'deployment': 'NOT_PERFORMED', 'autonomous_discovery_required_for_1_0': False,
        'gates': [{'gate': g, 'status': s, 'blocking': g != 'R8' and s != 'PASS',
            'owner': 'LivingMath maintainer/operator' if g != 'R8' else 'mathematical research',
            'reason': reason, 'evidence': [evidence(n) for n in names]} for g, s, reason, names in gates],
        'next_stage': '017 productization review; no017 code/SQL patch in this task'}
    write_json(out / 'release-readiness.json', readiness)
    result = {'status': 'PASS_SOURCE_BOUND_N_H_TRANSFER', 'source_binding': {'status': 'PASS', 'evidence': evidence('source-audit.json')},
        'blind_n_targets': {'status': 'PASS', 'scope': 't15 n3/4 entirely absent from permitted inputs; public formula allowed for all models', 'target_count': 16},
        'n_transfer': {'status': 'PASS', 'contained': 16, 'total': 16},
        'h_n_cocycle': {'status': 'PASS', 'classification': 'SOURCE_IDENTITY_REPLAY', 'squares': 16, 'nontrivial_h_squares': 12},
        'strong_baseline': {'status': 'NO_STRUCTURAL_ADVANTAGE', 'B2_contained': 16, 'total': 16, 'not_posthoc': True},
        'typed_lifecycle': {'status': 'PASS', 'outcome': 'SUCCESS', 'completion': 'COMPLETED',
            'fresh_after_activation': True, 'active_own_QA_permissions': []},
        'integrity': {'status': 'PASS', 'live_exactly_unchanged': True, 'old_files_unchanged': len(protected),
            'original_private_prefixes_preserved': True, 'hash_chain': 'PASS'},
        'deployment': {'status': 'NOT_DEPLOYED', 'server_version': live['health']['version'], 'schema_version': live['health']['schema_version'],
            'tool_count': len(live['tools']['tools']), 'canonical_events': live['health']['event_count']},
        'autonomous_discovery': {'status': 'NO_GO_SOURCE_DISCOVERY', 'claim': False, 'required_for_1_0': False},
        'release_readiness': {'status': 'NOT_READY', 'evidence': evidence('release-readiness.json')},
        'regression': {'pytest_PASS': 618, 'historical86_PASS': 86, 'failed': 0},
        'proof_status': 'unverified', 'scientific_corrections_used': 0,
        'distribution_replay': 'See ../distribution-validation.json, bound to exact ZIP hash; no replay PASS inferred before actual run.'}
    # Obtain IDs from the actual receipt rather than a fixture-dependent fallback.
    receipt = next(json.loads(s)['data'] for s in (out / 'typed-ledger.jsonl').read_text().splitlines() if json.loads(s)['stage'] == 'receipt')
    result['typed_lifecycle'].update(move_id=receipt['move_id'], measurement_event=receipt['event_id'], receipt_id=receipt['receipt_id'])
    write_json(out / 'result.json', result)
    (out / 'law-derivation.md').write_text('''# Source-level n/h derivation

Source bytes and intervals are pinned in pre-registration/source-audit. The original generator has `a_n=pi*n²*exp(2u)`, `P(a)=4a²-6a`, `A_n=q*P(a_n)*exp(u/2-a_n)`, `f_(n,eps)=A_n*exp(eps*u*(h+i*t))`.

At the SAME original Gauss node and branch, q,u,h,t,eps cancel in `f_(n+1)/f_n`; the remaining ratio is `P(a_(n+1))/P(a_n)*exp(-(a_(n+1)-a_n))`. Independent algebraic factorization `P(a)=2a*(2a-3)` checks the denominator: certified u>0, q>0 and pi>3 imply a_n>3 for n>=1, hence P(a_n)>0. Interval implementation additionally requires strictly positive denominator lower bound at each used step. No near-zero subtraction or floating-point conversion certifies this guard.

The actual source uses node gid0 and origin n-1; a step in n changes origin by1 and edge index by2, preserving the branch. The original evaluator receives exactly the original prefix, with no row/index remapping. Only n1/2 atoms appear before seal in native anchor calls. Source equality is not inferred from shared scalar phase, coordinate or endpoint.

`H_delta=exp(eps*u*delta)` does not change n/u/eps/q. `R_n` changes n/origin but does not change h/u/eps. Thus both source-bound compositions produce `R_(n-1)...R_2*H_delta*f_2`, with identical exact factors in a commutative complex scalar field. Interval paths are computed in different orders, retain dependency overestimation, and are compared with native intervals. This is SOURCE_IDENTITY_REPLAY, NOT an independently discovered law. Sixteen squares include four trivial h0 squares and twelve nonzero h shifts.

C/B2 raw interval arithmetic encloses the same source expression; a preregistered1e-45 relative widening produces the prediction enclosure. Native-reference containment and max1e-40 relative width are checked separately from overlap. Heuristic B3/B4 have no proved remainder and cannot establish enclosure by assertion. CASE-C point-zero pairs retain nonzero derivatives/germs and are never erased. No full-Xi/RH conclusion is made.
''')
    (out / 'LM_RELEASE_017_ENGINE_GAP_AUDIT.md').write_text('''# LM-RELEASE-017 — static engine gap audit

## Observed boundary

Live HTTPS/OAuth client reports0.4.2/schema5,24 tools,2056 canonical events and typed_cycle011.1 isolated sandbox. `live-preflight.json` contains exact schemas/contract and full MCP wire trace. No production deployment/restart, new feature flag, migration or SQL patch occurred in016. 012–016 source-law engines and operator harnesses are QA/review-only. The source-specific016 validator is a local operator component, not a newly published MCP capability.

## Exact proposed change map — no implementation

| Existing path/interface | Required017 delta | Acceptance evidence missing |
|---|---|---|
| `mcp_server.py:create_server`, `typed_cycle011_public.py:register_typed_tools` | Mount a versioned engine-owned controller behind a default-off feature flag; publish capability/schema versions and error contract. Preserve separate owner authority and registered adapter/source versions. | Real staging MCP roundtrip and disabled-flag compatibility |
| `typed_cycle011.py:TypedCycle`, `law_validation014_contract.py` | Promote explicit purpose, context, coordinate and singleton validation semantics out of QA harness. Engine loads journal/feedback itself; caller cannot erase known distinctions with empty memory. | Three genuine operational families, all outcomes, second move from source-owned feedback |
| `release016_run.py:training_frame/typed_cycle`, `release016_typed.py:prepare` | Replace operator-side direct precommit insertion with validated engine-owned source registration/read-only preview/proposal. Preserve byte/source/observer/scope/version commitments and authority separation. Do not copy the finite QA fixture label as the external source ontology. | External client registers its own immutable versioned source and sees provenance/failure/UNKNOWN |
| `release016_typed.py:Validator016/execute`, `law_validation014_receipt.py` | Introduce reviewed source-validator registry, exact artifact/manifest binding and declared authenticity levels. Keep execution outside model-facing server. Local executor identity alone never authenticates physical measurement. | Rebind/stale/foreign-project/adverse evidence attacks; DECLARED_UNINSPECTED for unsupported sources |
| `law_validation014_operator.py:commit`, `move_lifecycle.py:transition` | Keep atomic receipt/journal/result digest; route typed claims only through their typed validator. Generic completion stays explicitly legacy-only; never upgrade historic rows. | Mixed legacy/typed routing, result substitution, race/rollback fault injection |
| `typed_cycle011_store.py`, `law_validation014_store.py` | Review a SEPARATE protected SQL migration for events/operations/typed/history append-only guarantees, exact trigger definitions and restore/rollback. No migration generated/applied here. Current deployed events/operations have zero such triggers. | Owner-approved staging migration, restored backup, all invariants preserved |
| `http_server.py`, OAuth/service/tunnel configuration | Stable named HTTPS ingress, auth/capability versioning, cancellation/recovery/limits and sanitized diagnostics. No endpoint alteration here. | Real repeated-client canary, disconnect/restart/rollback; Quick Tunnel no longer sole ingress |

## Authority and threat model

Remote MCP/model has no activate/execute/commit tools.016 uses the user's explicitly authorized local QA operator and a separate measured executor process. Landlock denies learner raw/archive/oracle files; it does not protect against the schema-owning or same-authority local operator. SQLite triggers are not protection against a DB owner who can drop schema objects. Source-file hashes and computable artifacts are inspectable computational provenance, not physical authenticity or mathematical verification.

R1 passes the bounded scientific integrity gate. R2/R4/R5/R7 fail release readiness; R3/R6 remain inconclusive at the full external-release boundary. R8 fails utility-superiority but is nonblocking for research-engine1.0. See release-readiness.json for per-gate hashes, owners and blockers. No Bridge/SUTI/X4/Weil/DAG implementation, no017 code/SQL patch.
''')
    (out / 'RCA.md').write_text('''# 016 RCA and limitations

No guarded C counterexample occurred: all16 native intervals are contained, and both interval cocycle paths pass. No corrected fresh cohort was needed. A counterfeit first-failure witness would misstate the result; baseline-counterexamples.json instead preserves the first genuine B3/B4 misses with exact address and error.

B3 assumes geometric evolution across n based on n1/2. The true source contains exp(-pi*n²*exp(2u)) and a polynomial in that quadratic argument; a fixed geometric n-ratio does not model it. B4 linear n extrapolation with legitimate Hermite h values likewise fails. Neither miss demonstrates a new discovered mechanism: preregistered B2 explicitly computes the same public source formula and passes16/16. Therefore NO_STRUCTURAL_ADVANTAGE and NO_GO_SOURCE_DISCOVERY are preserved. B5 UNKNOWN is an interface/mathematical representation limit, not a false mathematical forecast.

Blindness concerns computed native t15 n3/4 inputs, not secrecy of the public formula. Published015 anchors at another t and all per-target cached amplitudes are unavailable to the confined learner. The same original interval implementation is shared, so independent reference path is not independent mathematical axiomatization or proof kernel. Padding was fixed before reveal; containment is not silently replaced by overlap. Source IDs are original prefix IDs; no labels or RH zeros select the sample.

The isolated typed cycle is real and source-bound but owner-orchestrated. It does not prove the production engine can own the full loop. Deployed events/operations lack SQL append-only guards; stable ingress/external source registration/independent-machine release acceptance remain open. Static017 audit lists exact pending boundaries; no deployment occurred. Original RH source ZIP has no declared redistribution licence and is intentionally omitted; replay requires the operator-provided immutable original. A fresh-venv replay on this host is separate from acceptance by an external person on another machine.
''')
    total = costs['P0_P3_total']
    report = f'''# LM-RELEASE-016-MATH — n/h source-bound holdout

## Result

**PASS_SOURCE_BOUND_N_H_TRANSFER; NO_STRUCTURAL_ADVANTAGE; NO_GO_SOURCE_DISCOVERY.** The real T49/T54 source predicts all16 target n3/4 complex intervals at t15 without target anchors; the preregistered explicit-formula baseline also passes16/16. This is a source-identity demonstration, not an autonomous discovery or a proof of RH. Release1.0 is **not ready**; mathematical superiority is nonblocking, but production/security/API gaps remain.

## Frozen experiment and source

Original ZIP SHA256 `19e3112882242fd8f686bfaf12b888bd7a8abe930e07b542fe298720044b14dd`. All18 manifest entries checked. Native source regeneration reproduces cases/routes/loops bytes exactly, with16384 addresses per A/B/C and ordered-address SHA `2fa469f8873e8f7150e749182f33c20f366563ab49b38f488b58680ea7962ecb`. M256/N4/U2/Gauss8, outward Decimal58 digits. DIAG008 is archival provenance, not a newly run RH kernel; no Git commit fabricated.

One genuine prefix node cell0/node0, both branches, original origins0..3/edges0..7. This is a new `(t,h,address)` combination at **t15**, not a claim that its source-address names were never published. Train h0/.001 and n1/2 only; targets n3/4 at h0/.001/.0005/.002. Original015 used t14.134725141734694. Addresses are never renumbered: preseal native anchor calls contain only origins0/1, postseal native calls use original origins0..3.

`pre-registration.json` and its byte/canonical hash freeze before anchors/learner. `permitted-learner-input.json` contains only n1/2 values/derivatives and allowed common node/formula/provenance. No cached n3/4 amplitude, value, derivative or interval anchor at any h enters the learner. Native evaluate is explicitly disabled there; Landlock denies raw cases, archive and oracle directory. All16 forecasts were fsync-sealed before any native t15 target call. Public source formula is equally available to all models. Blindness is scoped to the supplied archive/prior015/workspace, not a global assertion about the internet.

## Source law and intervals

`a_n=pi*n²*exp(2u)`, `R_n=P(a_(n+1))/P(a_n)*exp(-(a_(n+1)-a_n))`, `P(a)=2a(2a-3)`. Positive certified u and pi>3 prove nonzero denominators; implementation also checks lower bounds. `H_h=exp(epsilon*u*h)` preserves n/u/branch, while R changes n/origin preserving h/u/branch. Law derivation and guards are in law-derivation.md.

C computes both orders on real complex interval source values. Primary: native Re/Im intervals fully **contained** in presealed prediction enclosures, width<=1e-40 relative predicted complex magnitude. A fixed1e-45 relative widening of raw sound C/B2 intervals is frozen in advance. Overlap is a separate weaker diagnostic.16 cocycle squares pass both route/reference containments and raw route overlap;12 involve nonzero h. This is SOURCE_IDENTITY_REPLAY, not mathematical independence. Shared interval arithmetic is an explicit trust boundary.

## Baselines and retained failures

| Model | Target results | Interpretation |
|---|---|---|
| C, n ratio plus h shift | 16/16 containment | Explicit source identity |
| B1 original evaluator | 16 reference intervals | Separate postseal native path, not predictive competitor |
| B2 explicit source formula | 16/16 containment | Same permitted information; defeats structural-superiority claim |
| B3 preregistered geometric h/n | 0/16 enclosure/overlap | Wrong n dependence; exact first miss retained |
| B4 linear n / Hermite h | 0/16 enclosure/overlap | Heuristic without proved remainder; first miss retained |
| B5 unchanged006/007/013 | UNKNOWN | I006 already observed, T006 no informative test,007 missing schema,013 complex interval representation unsupported |

No posthoc baseline substitution or gate change. Weak-baseline failures are not evidence of a new law. Coordinates/origin identity, source equality and scalar cancellation remain distinct. CASE-C point-zero/germ controls reproduced, no loop deletion, zero-label filtering or RH/full-Xi conclusion.

## Typed cycle and preservation

Move{receipt['move_id']}, measurement event{receipt['event_id']}, receipt{receipt['receipt_id']}: PROPOSED → AUDITED → EXPERIMENT_ALLOWED → COMPLETED/SUCCESS/**unverified**; repeated AUDITED is retained in full trace. Source normalization, explicit private precommit and owner activation precede a **fresh** native h.0005,t15 read. The diagnostic observer counts failed n-target containments;0 is not a Xi zero. Full raw8-edge artifact checked by source-specific validator before atomic receipt/journal. Measurement is a protocol replay of an already checked h, not another independent blind claim.

Receipt repeat is idempotent; changed outcome under the same key rejected without operations. Question hash rebind rejected. Closed obligation version invalidates old execution (`STALE_OBLIGATION_VERSION`), no native call. Source-owned journal reports NO_NEW_DISTINCTION_BOUNDED after receipt; feedback event2063 preserves outcome and baseline limitation. All own QA grants closed. This fixed owner CLI does not constitute an engine-owned public MCP cycle.

Both deployed DBs unchanged by inode/file hash/schema/all rows/sequence/chain; canonical2056 events and4813 operations unchanged. All{len(protected)} preexisting files unchanged. Private original table prefixes retained, SQLite/FK/hash-chain and rollback append-only probes pass. Full regression **618 PASS**, historical real MCP stdio **86 PASS**; current HTTPS/OAuth health separately0.4.2/schema5/24 tools. No production/017/SQL/endpoint changes, no verified status.

## Full measured cost and reproducibility

P0–P3 CPU **{total['CPU_ns']/1e9:.6f}s**, wall **{total['wall_ns']/1e9:.6f}s**, largest-process peak RSS{total['largest_process_peak_RSS_KiB']}KiB. Includes source regeneration/audit/private backup, anchors, combined model process, four targets, fresh typed measurement/receipt and cleanup. Shared source generator:6 known-case native calls; new t15:2 anchors+4 targets+1 typed=7, total13. Learner0 native calls, B2 has16 explicit formula forecasts, no LLM calls. All-model CPU is combined, not a fictitious per-model speed comparison. Source CPU90s/wall120s/AS1GiB and total CPU120s budgets respected. Regression wall65.74s, regression/install CPU not measured; later packaging/OAuth/feedback are outside the frozen math total. See costs.json for complete call/scope ledger.

Pinned requirements installed in a new venv. Exact ZIP replay log/hash/outcome and fresh-environment cost appear in the companion `../distribution-validation.json` **after actual execution**, not inferred from unit tests. Original source ZIP is deliberately not rebundled without a redistribution licence; supply your locally authorized original with the exact hash. No private DB or OAuth credential is included. Clean replay is local-host evidence; separate-machine/external-person acceptance remains inconclusive.

## Release decision

R1 PASS. R2/R4/R5/R7 FAIL; R3/R6 INCONCLUSIVE. R8 FAIL, nonblocking for research-engine1.0. release-readiness.json gives owners and evidence hashes; LM_RELEASE_017_ENGINE_GAP_AUDIT.md maps precise pending interfaces, storage and authority boundaries.017 is static audit only. The next product step is a reviewed engine-owned typed controller; no new mathematical ontology, DSL, Bridge or production migration is smuggled into016.
'''
    (out / 'report.md').write_text(report)
    (out / 'README.md').write_text('''# Reproduce LM-RELEASE-016

This is a bounded real-source calculation, not autonomous discovery or a production release. Read report.md/result.json/RCA.md and the static017 readiness audit.

1. Obtain the original operator-authorized RH_XI_ROUTES_EXPORT_001.zip (supplied separately in repository docs). Required SHA256:19e3112882242fd8f686bfaf12b888bd7a8abe930e07b542fe298720044b14dd. It is not rebundled because no redistribution licence is declared. No synthetic fallback.
2. On Linux with Landlock and Python3.13, create a venv and run `python -m pip install -r requirements.lock`.
3. Run `PYTHON=/absolute/venv/bin/python bash reproduce.sh /absolute/RH_XI_ROUTES_EXPORT_001.zip /new/private/workdir`. The destination must not exist. This regenerates known source files, replays the frozen hidden-n experiment and fresh typed cycle, and closes its QA grants. It creates only disposable QA ledgers inside that directory and never opens production.
4. Run contract tests with `LM_RELEASE016_ARCHIVE=/absolute/RH_XI_ROUTES_EXPORT_001.zip /absolute/venv/bin/python -m pytest -q runtime/test_release016.py`. The archived full618 regression and historical86 traces are original-run evidence. Historical86 references private historical fixtures and is not advertised as reproducible from an empty public ledger.

All mathematical CODE hashes and the preregistered split/criteria are preserved; the replay is the same experiment, not a second independent scientific observation. Source CPU90s/wall120s/AS1GiB, P0–P3 CPU120s. Other-machine release acceptance is not implied by this host's clean-venv replay. Model/MCP has no activate/execute/commit authority; the local owner-run CLI is the explicitly authorized bounded QA operator. Known results remain unverified.
''')
    script = '''#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-python3}"
if [[ $# -ne 2 ]]; then
    echo 'Usage: PYTHON=/venv/bin/python bash reproduce.sh /original/source.zip /new/private/workdir' >&2
    exit 2
fi
"$python_bin" - "$package_dir" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
manifest=json.loads((root/'MANIFEST_SHA256.json').read_text())
for name,expected in manifest.items():
    p=(root/name).resolve()
    if not p.is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
        raise SystemExit('MANIFEST_MISMATCH:'+name)
print('MANIFEST_PASS',len(manifest))
PY
exec "$python_bin" "$package_dir/runtime/release016_reproduce.py" --work "$2" --source "$1" --package "$package_dir"
'''
    (out / 'reproduce.sh').write_text(script)
    (out / 'reproduce.sh').chmod(0o755)
    runtime = out / 'runtime'
    runtime.mkdir(exist_ok=True)
    for p in SOURCE.glob('*.py'):
        if not p.name.startswith('test_') or p.name == 'test_release016.py':
            shutil.copy2(p, runtime / p.name)
    shutil.copy2(SOURCE / 'normalization-schema.json', runtime / 'normalization-schema.json')
    write_json(out / 'environment.json', {'Python': sys.version, 'platform': platform.platform(),
        'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
        'clean_venv_install': 'PASS', 'other_machine': 'NOT_TESTED'})
    for name in ('LM_RELEASE_016_TZ.md', 'LM_RELEASE_016_CODEX_PROMPT.md', 'LivingMath_Release_Roadmap_v1.md'):
        shutil.copy2(ROOT / 'docs' / name, out / name)
    created = [str(p.relative_to(ROOT)) for p in sorted(SOURCE.glob('release016*.py'))]
    created += ['live_math_mcp_prod/test_release016.py', 'docs/superpowers/plans/2026-10-28-release-016.md']
    write_json(out / 'changed-files.json', {'created': created, 'old_source_modified': [], 'deployed_code_modified': [],
        'deployed_sql_modified': [], 'public_endpoint_changed': False, 'delivery': str(out.relative_to(ROOT))})
    for p in out.rglob('*'):
        if p.is_file() and ('.sqlite3' in p.name or p.suffix in ('.db', '.env') or p.name == 'RH_XI_ROUTES_EXPORT_001.zip'):
            raise ValueError('PRIVATE_OR_UNLICENSED_INPUT_IN_CAPSULE:' + str(p))
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'MANIFEST_SHA256.json'}
    write_json(out / 'MANIFEST_SHA256.json', manifest)
    package = out.parent / (out.name + '.zip')
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    print(json.dumps({'out': str(out), 'zip': str(package), 'sha256': sha(package), 'files': len(manifest)}))


if __name__ == '__main__':
    main()
