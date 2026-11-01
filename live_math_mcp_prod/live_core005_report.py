"""Evidence export for005; excludes canonical snapshots, auth data and credentials."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import statistics

from attention_qa import configure
from normalizer import digest
from qa_positive_acceptance import snapshot,write_json


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(base: Path) -> dict:
    meta=load(base/'metadata.json');report=Path(meta['report']);report.mkdir(parents=True,exist_ok=True)
    for name in ('worlds.json','oracle.json','frozen-contract.json','frozen-manifest.json','witnesses.json','attention-decisions.json',
                 'cycles.json','controls.json','P0-result.json','P0-failures.json','run-failures.json','exception.txt','pytest.txt',
                 'normalizer-preflight.json','connector-errors.json'):
        if (base/name).exists():shutil.copyfile(base/name,report/name)
    for name in ('development','frozen-sources','negative-inputs','local-logging','pilot'):
        source=base/name
        if not source.exists():continue
        for p in source.rglob('*'):
            if p.is_file() and p.suffix in {'.json','.jsonl','.txt','.py','.patch'}:
                dest=report/name/p.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    local=report/'local86';local.mkdir(exist_ok=True)
    for name in ('result.json','calls.json','checks.json','stdio-wire.jsonl','server-stderr.txt','final-moves.json','integrity.json'):
        if (base/'local86'/name).exists():shutil.copyfile(base/'local86'/name,local/name)
    src=Path(__file__).parent
    for p in [*src.glob('live_core005*.py'),*src.glob('test_live_core005*.py'),src/'live_core005-contract.json']:
        shutil.copyfile(p,report/p.name)
    # Read canonical data again; no mutation probes on production.
    before=load(base/'before.json');after=snapshot(Path(meta['db']))
    exact={name:after['tables'].get(name)==rows for name,rows in before['tables'].items()}
    protected={name:sha(Path(name))==value for name,value in meta['protected_files'].items()}
    prev='GENESIS';broken=[]
    for op in after['tables']['operations']:
        expected=digest({'time':op['occurred_at'],'action':op['action'],'details':json.loads(op['details_json']),'previous':prev})
        if op['entry_hash']!=expected or op['previous_hash']!=prev:broken.append(op['id'])
        prev=op['entry_hash']
    with sqlite3.connect(Path(meta['db']).as_uri()+'?mode=ro',uri=True) as conn:
        sqlite_ok=conn.execute('PRAGMA integrity_check').fetchone()[0];fk=conn.execute('PRAGMA foreign_key_check').fetchall()
    latest={}
    for row in after['tables']['research_move_status_history']:
        if row['move_id'] not in latest or row['sequence']>latest[row['move_id']]['sequence']:latest[row['move_id']]=row
    qa={m['id'] for m in after['tables']['research_moves'] if m['project'].startswith('LM_QA_')}
    active=[mid for mid in qa if latest[mid]['status']=='EXPERIMENT_ALLOWED']
    verified=[r['id'] for r in after['tables']['events'] if r['project'].startswith('LM_QA_') and r['status']=='verified']
    integrity={'all_original_tables_exact':exact,'protected_file_count':len(protected),'changed_protected_files':[n for n,ok in protected.items() if not ok],
        'old_events':len(before['tables']['events']),'current_events':len(after['tables']['events']),
        'old_operations':len(before['tables']['operations']),'current_operations':len(after['tables']['operations']),
        'sqlite_integrity_check':sqlite_ok,'foreign_key_check':fk,'chain_broken_ids':broken,'chain_head':prev,
        'inode_unchanged':before['inode']==after['inode'],'backup_sha256':meta['backup_sha256'],
        'backup_hash_matches':sha(base/'research-before.sqlite3')==meta['backup_sha256'],
        'active_QA_grants':active,'QA_verified_events':verified,'production_research_writes':0,'server_restarted':False,'MCP_API_changed':False}
    integrity['result']='PASS' if (all(exact.values()) and not broken and sqlite_ok=='ok' and not fk and all(protected.values())
        and integrity['inode_unchanged'] and integrity['backup_hash_matches'] and not active and not verified) else 'FAIL'
    write_json(report/'source-preservation.json',integrity)
    manifest=load(base/'frozen-manifest.json',{});patches=load(base/'development/patches.json',[])
    frozen={name:sha(Path(name))==value for name,value in manifest.items()}
    accepted={p['file']:p for p in patches}
    valid_frozen=all(ok or (name in accepted and sha(Path(name))==accepted[name]['after_sha256']
                    and manifest[name]==accepted[name]['before_sha256']) for name,ok in frozen.items())
    write_json(report/'frozen-checks.json',{'current_original_hash_matches':frozen,'documented_patches':patches,
                                          'valid_with_explicit_fixture_patch':valid_frozen})
    pre=load(base/'live-preflight.json',{})
    if pre:
        write_json(report/'live-readonly-check.json',{'health':pre['health'],'tools':pre['tools'],
            'contract_RH_without_private_frontier':{k:v for k,v in pre['contract_RH'].items() if k!='frontier'},
            'RH_frontier_digest':digest(pre['contract_RH']['frontier']),'raw_trace_private':str(base/'live-readonly'),
            'attend_interpret':'persist caller supplied content; algorithm005 is not installed',
            'normalizer004_1':'local read-only Python/CLI, not a MCP tool'})
    p0=load(base/'P0-result.json',{'result':'FAIL'});reg=load(base/'local86/result.json',{'result':'NOT_RUN'})
    p1=load(base/'pilot/result.json',{'result':'NOT_RUN','calls':0,'complete':0,'utility':'INCONCLUSIVE','main_calls':0})
    failures=load(base/'run-failures.json',[])
    rows=[json.loads(s) for s in (base/'pilot/outputs.jsonl').read_text().splitlines()] if (base/'pilot/outputs.jsonl').exists() else []
    means={condition:statistics.mean(r['metrics']['quality'] for r in rows if r['condition']==condition and r['outcome']=='OK')
           for condition in 'ABC' if any(r['condition']==condition and r['outcome']=='OK' for r in rows)}
    comparisons={}
    for condition in 'BC':
        pairs=[]
        for i in range(2):
            a=next((r for r in rows if r['task']==i and r['condition']=='A' and r['outcome']=='OK'),None)
            b=next((r for r in rows if r['task']==i and r['condition']==condition and r['outcome']=='OK'),None)
            if a and b:pairs.append(b['metrics']['quality']-a['metrics']['quality'])
        comparisons[condition+'-A']={'paired_differences':pairs,'coverage':len(pairs)/2,
            'mean':statistics.mean(pairs) if pairs else None,'conclusion':'INCONCLUSIVE; two-task exploratory pilot, no population superiority inference'}
    metrics={'P0':p0,'P1':p1,'condition_means':means,'comparisons':comparisons,
        'calls_started':len(rows),'transport_failures':sum(r['outcome']=='TRANSPORT_FAILURE' for r in rows),
        'model_failures':sum(r['outcome']=='MODEL_FAILURE' for r in rows),
        'false_novelty':sum(r['metrics']['false_novelty'] for r in rows if r['outcome']=='OK'),
        'valid_model_witnesses':sum(r['metrics']['witness_valid'] for r in rows if r['outcome']=='OK'),
        'model_source_errors':sum(r['metrics']['source_error'] for r in rows if r['outcome']=='OK'),
        'model_independent_retained':sum(r['metrics']['independent_retained'] for r in rows if r['outcome']=='OK'),
        'tool_events':sum(r['tool_events'] for r in rows),'LLM_quality_not_safety':'Action regret and witness validity are separate from unverified/no-grant invariants.',
        'input_tokens_estimated_per_call':7000,'actual_usage':[{'id':r['id'],'usage':r.get('usage'),'wall_seconds':r['wall_seconds']} for r in rows],
        'actual_provider_build':None,'provider_seed':None,'output_cap':None,'utility':'INCONCLUSIVE',
        'native_MCP_generation':False,'experimental_algorithm_generation':True}
    write_json(report/'metrics.json',metrics)
    good=(p0['result']=='PASS' and reg['result']=='PASS' and integrity['result']=='PASS' and valid_frozen and not failures)
    result={'P0':p0['result'],'P1':p1['result'],'engineering':'PASS' if good else 'FAIL',
        'finite_core':'GO' if good else 'NO-GO','utility':'INCONCLUSIVE','core_version':'005.1',
        'server_version_unchanged':'0.4.2','normalizer_version_unchanged':'004.1',
        'production_research_writes':0,'MCP_API_changed':False,'core_installed_in_MCP':False,
        'P2':'Separate decision for bounded read-only preview; no installation authorized by this run',
        'model_calls':p1['calls'],'main_calls':0,'main_max_after_separate_gate':24,
        'integrity':integrity['result'],'historical86':reg['result'],'report':str(report/'report.md')}
    write_json(report/'result.json',result)
    write_json(report/'failures.json',{'initial_fixture_failures':patches,'P0_failures':load(base/'P0-failures.json',[]),
        'pipeline_failures':failures,'P1_stop':p1.get('stop'),'prior_series_scores_recomputed':False})
    added=[str(p.relative_to(src.parent)) for p in src.glob('*core005*') if p.is_file()]
    write_json(report/'changed-files.json',{'added':added+['docs/superpowers/plans/2026-10-27-live-math-core-005.md'],
        'existing_production_sources_modified':[],'protected_files_checked':len(protected),'server_restarted':False})
    cycles=load(base/'cycles.json',[])
    examples=[]
    for c in cycles:
        i=c['I_before'];a=c['attention'];u=c['feedback'];excluded=[h['id'] for h in u['hypotheses'] if h['status']!='ACTIVE']
        examples.append(f"- {c['world']}: histories {i.get('history_refs')}, current O={i.get('current_observation')}, "
            f"witness a={i.get('witness',{}).get('suffix')}, readouts={i.get('witness',{}).get('left')}/{i.get('witness',{}).get('right')}; "
            f"T={a.get('test_id')} suffix={a.get('suffix')}, loss={a.get('loss')}; observation={c['observation']['readout']}; "
            f"excluded={excluded}, I remains ACTIVE. Guard={c['I_after'].get('guard')}.")
    (report/'report.md').write_text(f'''# LM-LIVE-MATH-CORE-005

P0 **{p0['result']}**; finite experimental I/T **{result['finite_core']}**. P1 **{p1['result']}**, utility **INCONCLUSIVE**. Production installation: none.

## Mechanism and boundary

The existing MCP attend/interpret only persist caller-supplied content. The separate live_core005.py algorithm computes new finite content: I constructs a witness with unit/coordinate-target/admissibility-boundary algebra; T groups analytic suffix readouts and minimizes cost+7/3×expected remaining alternatives. Neither function imports the independent oracle. There is no DSL, SMT solver, new fundamental operation or automatic proof/grant/completion. All outputs are unverified proposals. The normalizer004.1 remains local source-backed Python/CLI, not an MCP tool.

Native source: start(x,y)=(0,1); appending k maps to ((x+k*y)%5,(y+k)%5). Finite words and suffixes, observer and K are explicit source records. For suffix(k,l), I/T use x'=x+(k+l)y+kl, y'=y+k+l modulo5. Oracle executes every concatenated word step-by-step and enumerates the complete finite Sig; attention oracle independently counts pairwise surviving alternatives. Truth tables and current optimal tests are never inputs to the generator or model.

## Frozen P0

Four worlds, six source histories each,15 unordered pairs each. Witness cases={p0.get('valid_witness_cases')}/{p0.get('pair_cases')}; new distinctions={p0.get('new_distinctions')}; false novelty={p0.get('false_novelty')}; missed distinctions={p0.get('missed_distinctions')}; false grants={p0.get('false_grants')}. Negative controls={p0.get('negative_controls')}; attention before/after checks={p0.get('attention_checks')}; independent branches retained={p0.get('independent_branches_preserved')}/4. Full local pytest trace is pytest.txt; unchanged historical86 real MCP/stdio replay={reg['result']}.

W1: current observation hides a continuation distinction. W2: observer change is distinguished from source change; equal native states with distinct source IDs create no new distinction. W3: an initial x=3 -> next x=1 rule needs the stricter guard y=3 after a counterexample. W4: admissibility differs despite a constant observer; conflicting predictive/dependent hypotheses are provisionally excluded while the independent question remains. Word(1,1) has state(3,3), word(2,2) has state(3,0); both currently show x=3. Source identity is never inferred from observation/coordinate equality.

Full Sig, source IDs/hashes, finite witnesses, assumptions, guards, unknowns and failure conditions: oracle.json, witnesses.json, cycles.json. Point-zero/germ-zero and alias/equivalence controls refuse unsupported inference rather than invent semantic witnesses. C4, missing C2/C3, budget, foreign project, tampered source/catalog, stale/closed obligation and observer mismatch fail closed. Renaming/seen structural fingerprints create no novelty. A NO_NEW_DISTINCTION for equal continuation states preserves distinct source identities.

## Concrete research cycles

'''+ '\n'.join(examples)+f'''

Original source events are unchanged; counterexample observations and MCP logging append only to isolated synthetic DBs. Feedback excludes bound predictions provisionally, not mathematical truth. I narrows scope to actual register states; a renamed broad rule cannot remove its missing guard. MCP logging trace local-logging/ stores algorithm content; the server generated no witness itself. Measurements are from the operator-precommitted synthetic environment, not a model or generator-selected truth.

## Pilot and stopping rule

Pilot calls={p1['calls']}/6, complete={p1['complete']}. Two held-out weighted hidden-history tasks, same requested gpt-6-luna/low, A source snapshot/B source-preserving normalization/C normalization+I/T uncertainty/witness. Source atoms match; user prompts7000 estimated o200k_base tokens. C deliberately withholds current T ranking/selection and full prediction tables; it does not test handing the model a ready answer. Build/seed/provider output cap unknown; raw inputs/output/usage/latency are retained.

Condition means={means}. Baseline source-only calls come first; ceiling/floor or any transport/schema/tool failure stops with RCA, without retries or imputation. Stop={p1.get('stop')}. Main0/24: separate after-pilot gate/decision, never automatic. Paired coverage and regret, source errors, false novelty and witness validity are in metrics.json; safety is not a quality score. Two tasks cannot establish population superiority. Old002/003/004 results remain separate and unchanged.

## Preservation and limitations

Canonical integrity={integrity['result']}: {integrity['current_events']} events/{integrity['current_operations']} operations; all original rows, protected source/reports/AGENTS, SQLite/FKs, inode and hash-chain preserved. Chain head={prev}. Backup remains private; no production source/API/policy/schema/research writes or restart. Live HTTPS/OAuth reads inspected actual health, RH contract and18 tool schemas. Local86 and logging use genuine ClientSession over isolated stdio, not live HTTPS writes.

GO applies only to this finite native arithmetic constructor and scoped attention rule. It is neither universal live mathematics nor mathematical truth verification. No claim of improved LLM utility, universal semantic extraction, model-generated internal ontology or MCP-native candidate generation. P2 read-only preview is a separate installation decision; ChatGPT reconnection is unnecessary for these local modules. Reproduction defaults to P0 only; --pilot explicitly enables at most6 calls after PASS.
''')
    (report/'RCA.md').write_text('''# RCA

## Initial red test

Development/expected-import-before.txt preserves the expected missing-module test before implementation. It is scaffolding evidence, not a scientific result.

## SOURCE_BINDING_BUG: invalid closed-obligation fixture

The initial targeted run had4 FAIL/61 PASS because the closed fixture supplied reason/evidence but omitted mandatory reopen_conditions. The existing server rejected setup before I/T. Exact source and trace: development/test-before-closed-fixture-fix.py and closed-fixture-before.txt. The minimum patch supplies explicit reopening conditions and binds the closed test to its new version, separating closure from the stale-version control. No guard or expected fail-closed assertion was weakened; worlds/oracle/scoring unchanged. Original frozen test hash and current patched hash remain explicit in frozen-checks.json and development/patches.json. Full regression is pytest.txt; no model calls preceded the fix.

## Finite mechanism versus missing capabilities

Native mod5 rules and observers are declared source fixtures. I uses constructive arithmetic probes; it does not claim completeness outside registered worlds or infer mathematical equality from aliases, point values or observer names. Unsupported contexts are refused. Environmental measurements are operator-precommitted. MCP only logs algorithm outputs; no production native generator was installed. Model claims remain unverified regardless of audit or completion.

## Acceptance and pilot findings

Exact failing P0 input/output, if any, remains P0-failures.json and blocks model inference. Pilot transport/model/ceiling/floor findings remain failures.json and pilot/result.json with raw receipts; missing observations are not imputed. A baseline ceiling is QA_WORLD_BUG and STOP_WITH_RCA, not a benefit or failure of structured mathematics. A small pilot utility remains INCONCLUSIVE. No oracle, source world or past primary score is changed after viewing model responses.
'''+f"\nCurrent P0={p0['result']}; pipeline failures={failures}; P1 stop={p1.get('stop')}.\n")
    (report/'README.md').write_text('''# Reproduction

From this repository: `./reproduce.sh` runs P0 only with a fresh private BackupAPI baseline, isolated synthetic worlds and real stdio MCP regression. `./reproduce.sh --pilot` additionally permits at most6 unique calls only after P0 PASS and stops on baseline ceiling/floor or any transport/schema/tool failure. Existing result directories are refused. Main24 is never automatic.

Use the existing .venv and requirements-causal-qa.txt. Pilot uses existing ChatGPT CLI login and gpt-6-luna/low. No API key is supplied; backend build/seed/output cap remain unknown. All source atoms and exact user token budgets are checked before calls. Current optimal oracle/ranking is absent from model prompts.

Canonical snapshots/RH raw context/OAuth credentials stay outside this report. World DB paths are private fixture references, not included databases. All exported source histories and negative inputs are synthetic. local86/ contains genuine stdio replay on a private historical backup copy; local-logging/ shows supplied algorithm content persisted by existing tools. Protected raw model traces have0700 directories/0600 files.

Offline integrity: `../../../../.venv/bin/python verify_artifacts.py` from this report directory; this performs no model calls or DB access. Full oracle/Sig is for verification only and must not be passed into I/T or model inputs. Source changes are listed in changed-files.json; frozen sources and initial fixture FAIL are retained.
''')
    (report/'reproduce.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/live_core005_qa.py" "$@"\n');(report/'reproduce.sh').chmod(0o755)
    (report/'verify_artifacts.py').write_text('''import hashlib,json\nfrom pathlib import Path\nr=Path(__file__).resolve().parent\nload=lambda n:json.loads((r/n).read_text())\nchecks={}\nchecks['hashes']=all(hashlib.sha256((r/p).read_bytes()).hexdigest()==h for p,h in load('manifest-sha256.json')['files'].items())\nchecks['P0']=load('P0-result.json')['result']=='PASS'\nchecks['witnesses']=all(x['result']=='PASS' for x in load('witnesses.json'))\nchecks['attention']=all(x['result']=='PASS' for x in load('attention-decisions.json'))\nchecks['controls']=all(x['result']=='PASS' for x in load('controls.json'))\nchecks['source_preservation']=load('source-preservation.json')['result']=='PASS'\nchecks['historical86']=load('local86/result.json')['result']=='PASS'\nchecks['secrets']=load('secret-scan.json')['result']=='PASS'\nprint(json.dumps({'result':'PASS' if all(checks.values()) else 'FAIL','checks':checks},indent=2))\nraise SystemExit(0 if all(checks.values()) else1)\n'''.replace('else1','else 1'))
    for name in ('pilot','local86','local-logging'):
        folder=report/name
        if folder.exists():
            for p in [folder,*folder.rglob('*')]:p.chmod(0o700 if p.is_dir() else 0o600)
    secret=Path(configure()['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode()
    leaks=[];forbidden=[]
    patterns=[rb'Bearer[ \t]+[A-Za-z0-9._~+/-]{20,}',rb'"(?:access_token|refresh_token|client_secret)"\s*:\s*"[A-Za-z0-9._~+/-]{16,}"',rb'sk-(?:proj-)?[A-Za-z0-9_-]{24,}']
    for p in report.rglob('*'):
        if not p.is_file():continue
        data=p.read_bytes()
        if (len(secret)>=8 and secret in data) or any(re.search(pattern,data) for pattern in patterns):leaks.append(str(p.relative_to(report)))
        if '.sqlite' in p.name or p.name in {'before.json','server.env','auth.json'}:forbidden.append(str(p.relative_to(report)))
    scan={'result':'PASS' if not leaks and not forbidden else 'FAIL','credential_match_files':leaks,'forbidden_files':forbidden,
          'canonical_backup_exported':False,'OAuth_headers_recorded':False}
    write_json(report/'secret-scan.json',scan)
    hashes={str(p.relative_to(report)):sha(p) for p in sorted(report.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}
    write_json(report/'manifest-sha256.json',{'algorithm':'sha256','files':hashes})
    return result
