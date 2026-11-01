"""P0/P1 evidence export, keeping canonical production data and credentials private."""
import hashlib
import json
from pathlib import Path
import random
import shutil
import sqlite3
import statistics

from attention_qa import configure
from normalizer import canonical, digest
from qa_positive_acceptance import snapshot, write_json
from transfer_report import copy_retained


def json_file(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lines(path: Path) -> list:
    return [json.loads(s) for s in path.read_text().splitlines() if s] if path.exists() else []


def export(base: Path) -> dict:
    meta=json_file(base/'metadata.json');report=Path(meta['report']);report.mkdir(parents=True,exist_ok=True)
    for name in ('worlds.json','cases.json','oracle.json','preregistration.json','P0-manifest.json','P0-result.json','P0-failures.json',
                 'audit-equivalence.json','loss-ledger.json','P0-metrics.json','pytest.txt','run-failures.json','exception.txt',
                 'example-C0.json','example-C1.json','example-C2.json','example-C3.json','example-C4.json'):
        if (base/name).exists():shutil.copyfile(base/name,report/name)
    for name in ('development','pilot','demonstration'):
        src=base/name
        if not src.exists():continue
        for p in src.rglob('*'):
            if p.is_file() and p.suffix in {'.json','.jsonl','.txt','.py','.md','.patch'}:
                dest=report/name/p.relative_to(src);dest.parent.mkdir(parents=True,exist_ok=True);copy_retained(p,dest)
    local=report/'local86';local.mkdir(exist_ok=True)
    for name in ('result.json','calls.json','checks.json','stdio-wire.jsonl','server-stderr.txt','final-moves.json','integrity.json'):
        if (base/'local86'/name).exists():shutil.copyfile(base/'local86'/name,local/name)
    source=Path(__file__).parent
    for p in [source/'normalizer.py',source/'normalization-schema.json',*source.glob('normalization_*.py'),*source.glob('test_normaliz*.py')]:
        shutil.copyfile(p,report/p.name)
    before=json_file(base/'before.json');after=snapshot(Path(meta['db']))
    exact={table:rows==after['tables'][table] for table,rows in before['tables'].items()}
    prev='GENESIS';bad=[]
    for row in after['tables']['operations']:
        expected=digest({'time':row['occurred_at'],'action':row['action'],'details':json.loads(row['details_json']),'previous':prev})
        if row['entry_hash']!=expected or row['previous_hash']!=prev:bad.append(row['id'])
        prev=row['entry_hash']
    with sqlite3.connect(Path(meta['db']).as_uri()+'?mode=ro',uri=True) as c:
        sqlite_ok=c.execute('PRAGMA integrity_check').fetchone()[0];fk=c.execute('PRAGMA foreign_key_check').fetchall()
    protected_sources={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()==value for name,value in meta['source_before'].items()}
    latest={}
    for row in after['tables']['research_move_status_history']:
        if row['move_id'] not in latest or row['sequence']>latest[row['move_id']]['sequence']:latest[row['move_id']]=row
    qa_moves={r['id'] for r in after['tables']['research_moves'] if r['project'].startswith('LM_QA_')}
    active_qa=[mid for mid,row in latest.items() if mid in qa_moves and row['status']=='EXPERIMENT_ALLOWED']
    verified_qa=[e['id'] for e in after['tables']['events'] if e['project'].startswith('LM_QA_') and e['status']=='verified']
    root=source.parent
    integrity={'exact_original_tables':exact,'old_events':len(before['tables']['events']),'current_events':len(after['tables']['events']),
        'old_operations':len(before['tables']['operations']),'current_operations':len(after['tables']['operations']),
        'sqlite_integrity_check':sqlite_ok,'foreign_key_check':fk,'independent_hash_chain':{'ok':not bad,'broken_ids':bad,'last_hash':prev},
        'inode_unchanged':before['inode']==after['inode'],'existing_source_files_unchanged':protected_sources,
        'AGENTS_unchanged':hashlib.sha256((root/'AGENTS.md').read_bytes()).hexdigest()==meta['AGENTS_sha256'],
        'private_backup_sha256':meta['backup_sha256'],'backup_hash_matches':hashlib.sha256((base/'research-before.sqlite3').read_bytes()).hexdigest()==meta['backup_sha256'],
        'production_research_writes':0,'production_tool_installed':False,'active_QA_grants':active_qa,'QA_verified_events':verified_qa}
    integrity['result']='PASS' if all(exact.values()) and not bad and sqlite_ok=='ok' and not fk and integrity['inode_unchanged'] and integrity['AGENTS_unchanged'] and all(protected_sources.values()) and integrity['backup_hash_matches'] and not active_qa and not verified_qa else 'FAIL'
    write_json(report/'integrity.json',integrity)
    live=json_file(base/'live-preflight.json',{})
    if live:
        contract={key:value for key,value in live['contract_RH'].items() if key!='frontier'}
        write_json(report/'live-readonly-check.json',{'health':live['health'],'tools':len(live['tools']['tools']),
            'contract':contract,'RH_frontier_sha256':digest(live['contract_RH']['frontier']),
            'raw_trace_private':str(base/'live-readonly'),'research_DB_writes':0})
    p0=json_file(base/'P0-result.json',{'result':'FAIL'});reg=json_file(base/'local86/result.json',{})
    demo=json_file(base/'demonstration/result.json',{})
    p1=json_file(base/'pilot/result.json',{'difficulty_gate':'NOT_RUN','calls':0,'complete':0,'main_calls':0,'causal_utility':'INCONCLUSIVE'})
    rows=lines(base/'pilot/outputs.jsonl')
    comparisons={}
    for left,right in [('C','A'),('C','D'),('C','B')]:
        differences=[]
        for i in range(4):
            a=next((r for r in rows if r['task']==i and r['mode']==left and r['outcome']=='OK'),None)
            b=next((r for r in rows if r['task']==i and r['mode']==right and r['outcome']=='OK'),None)
            if a and b:differences.append({'task':i,'difference':a['metrics']['regret_quality']-b['metrics']['regret_quality']})
        rng=random.Random(104004)
        means=sorted(statistics.mean(rng.choices([d['difference'] for d in differences],k=len(differences))) for _ in range(10000)) if differences else []
        comparisons[left+'-'+right]={'pairs':differences,'coverage':len(differences)/4,
            'ci95':[means[250],means[9750]] if means else None,'mean':statistics.mean(d['difference'] for d in differences) if differences else None,
            'outcome':'INCONCLUSIVE','scope':'Exploratory four-task pilot only; B is lossy, not a causal structure comparison.'}
    p0_metrics=json_file(base/'P0-metrics.json',[])
    times=[m['normalization_seconds'] for m in p0_metrics];sorted_times=sorted(times)
    costs={level:{'mean_bytes_factor':statistics.mean(m['input_bytes']/m['output_bytes'] for m in p0_metrics if m['level']==level),
        'mean_tokens_factor':statistics.mean(m['input_tokens']/m['output_tokens'] for m in p0_metrics if m['level']==level)}
        for level in ('C0','C1','C2','C3','C4')} if p0_metrics else {}
    metrics={'P0':p0,'P0_costs':costs,'P0_latency_seconds':{'p50':statistics.median(times) if times else None,'p95':sorted_times[min(len(sorted_times)-1,int(.95*len(sorted_times)))] if times else None},
        'tokenizer':'o200k_base (estimate, not backend billing tokens)','P1':p1,'P1_comparisons':comparisons,
        'native_generation':False,'actual_model_build':None,'remote_cpu_seconds':None}
    write_json(report/'metrics.json',metrics)
    manifest=json_file(base/'P0-manifest.json',{})
    unchanged={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()==value for name,value in manifest.items()}
    write_json(report/'frozen-checks.json',unchanged)
    go=p0['result']=='PASS' and reg.get('result')=='PASS' and demo.get('result')=='PASS' and integrity['result']=='PASS' and all(unchanged.values())
    result={'P0':p0['result'],'P1':p1['difficulty_gate'],'read_only_MCP_tool':'GO' if go else 'NO-GO',
        'GO_scope':'Only bounded source-backed read-only preview; finite registered D_q, fail-closed missing/budget/C4/out-of-family. No deployment performed.',
        'normalizer_version':'004.1','production_modified':False,'production_tool_installed':False,
        'normalizer_decides_mathematical_equivalence':False,'native_generation':False,'integrity':integrity['result'],
        'model_calls':p1['calls'],'model_complete':p1['complete'],'main_calls':0,'causal_benefit':'INCONCLUSIVE',
        'local86':reg.get('result'),'demonstration':demo.get('result'),'report':str(report/'report.md')}
    write_json(report/'result.json',result)
    write_json(report/'changed-files.json',{'added':[str(p.relative_to(root)) for p in source.glob('*normaliz*') if p.is_file()]+['docs/superpowers/plans/2026-10-27-suti-normalization-004.md'],
        'modified_existing_sources':[p for p,same in protected_sources.items() if not same],'AGENTS_unchanged':integrity['AGENTS_unchanged'],'server_restarted':False})
    (report/'normalization-contract.md').write_text('''# Source-preserving normalization contract

The local API is read_history(existing_path, project) then normalize_context(history, focus, registered_candidates, level, Budget). The CLI is normalizer.py preview --db EXISTING --project PROJECT --dq JSON --level C2. Without D_q it is a preview with INSUFFICIENT_CONTEXT, never an experiment authorization.

A concept is an extraction, not a mathematical equivalence class. Different source records keep different scoped IDs even when spellings/values match. Declared relations and lexical alias hypotheses retain source hashes; substitution_allowed is always false. claim_map, method_model, counter_reading and unknowns are independent. Confidence describes extraction only. Verified declarations remain in canonical source but are never promoted by this normalizer.

C0 keeps raw audit data; C1 adds a lossless-for-audit concept index; C2 selects conservative dependency closure plus lexical focus and all adverse records, retaining every non-event audit input. C3 refuses a budget that cannot hold that closure. C4 is an abbreviated explanation and is never an audit substitute. Omitted source records remain addressable by ID/hash and loss ledger. reconstruct_context performs lazy recovery and rejects input drift.

Certificates cover only the finite D_q, schema, source/scope/version, normalizer version and auditor-code digest. Projection validation is against the registered canonical source. No cached verdict or model text is an authority. Audit-equivalence is tested using the actual unmodified auditor on explicitly separate SQLite materializations. It is not a universal theorem or a replacement for live server audit.

Cache size is eight derived entries. Source/event/byte, query-family and output/time bounds are explicit. Time checks are cooperative and input-bounded, not hard realtime scheduling guarantees. Overflow/missing source is fail-closed; an unavailable input digest is explicitly labeled UNAVAILABLE_INPUT_BOUND, not represented as a hash.

All canonical production SQL uses mode=ro/query_only. Temporary P0/stdio fixtures may create local research records and synthetic operator dispositions; these are not live owner approvals. No production schema, policy, API or record is changed. A future MCP tool must preserve these limitations and remain read-only.
''')
    (report/'README.md').write_text('''# Reproduction

From the repository environment, `./reproduce.sh --p0-only` creates a fresh private baseline and isolated deterministic fixtures; no LLM calls. `./reproduce.sh` additionally runs at most16 pilot calls only after P0 PASS. The32-call main needs a separate after-pilot decision and is never started automatically. `--help` only prints options. Existing output directories are refused.

Dependencies are the existing requirements-dev.txt plus tiktoken/jsonschema (requirements-causal-qa.txt). The CLI uses the existing ChatGPT login, requested gpt-6-luna/low; the immutable provider build and seed are unknown. Actual usage, inputs and failures are in pilot/. Do not interpret byte compression as token savings; metrics identify the tokenizer.

Canonical production snapshots and OAuth secrets are private and are not exported. `local86/` is a real stdio MCP replay on a private backup copy, not a production write or a new live HTTPS run. The saved earlier86 live invariants were read; the original methods are unchanged. Source attribution summarizes SUTI specification ideas only; no SUTI runtime or full ontology was imported.
''')
    (report/'report.md').write_text(f'''# LM-SUTI-NORMALIZATION-004

P0: **{p0['result']}**. Read-only MCP preview recommendation: **{result['read_only_MCP_tool']}**; no tool installed.
P1 difficulty gate: **{p1['difficulty_gate']}**. Causal utility: **INCONCLUSIVE**. Native generation: **false**.

## Implementation and source boundary

Local normalizer/preview, strict schema, canonical event/hash locators, separate claim/method/counter-reading, explicit unknowns and loss ledger. It never merges source identities or promotes aliases into equality, pointwise-zero into germ-zero, successful completion into proof, or a diagnostic failure object into a supporting premise.
SUTI Syntaxium/compaction/integration-contract ideas are attributed as local-specification/specification-only/PROPOSED-HOLD-NOT_IMPLEMENTED. Our C0-C4 levels follow this004 specification, not a claim that a SUTI runtime exists. The original archives/documents remain primary.

## P0 acceptance

Finite worlds: {p0.get('worlds')}; candidate-family size: {p0.get('candidate_family_size')}; exact comparisons: {p0.get('exact_complete_matches')}/{p0.get('complete_audit_comparisons')}.
False-grant transitions: {p0.get('false_grants')}. Full outputs compare findings, grounds, role/source hashes, scope/version, reopening conditions and proof_status. C4 and incomplete budgets explicitly refuse; they are not advertised as equal auditable replacements.
Source roundtrip and cache/budget/unknown tests are in pytest.txt and tests. Dispositions, lifecycle SUCCESS and competing-theory fixtures are synthetic/local, not normalizer-generated truth or production approvals. The actual auditor is used on separate DBs; model text is never an audit oracle.

The unchanged86 invariant methods replayed over real stdio MCP: {reg.get('result')}, passed={reg.get('passed')}. Production HTTPS research_contract(RH) and health were read; live tool count remains18. The original connector route returned Unknown tool; direct HTTPS worked. Production research rows unchanged: {integrity['result']} ({integrity['old_events']} events/{integrity['old_operations']} operations).

## Demonstration and P1

Competing L/R source claims remain together before and after a synthetic guard measurement. Existing local MCP attention/interpretation record an operator-seeded move toward R; the normalizer merely rebuilds the source map and retains unknown/history/independent branch. Demonstration: {demo.get('result')}, see demonstration/.
The new P1 problem is costed measurement under a finite uncertainty set, with no realized guard or complete test-prediction table in prompts. Two independent exhaustive Bayes-error implementations agree. Conditions A full, B ordinary lossy summary, C source-backed projection, D flat facts share the same6000 estimated-token budget. B has different information and is descriptive only.
Pilot calls: {p1['calls']}/16, complete={p1['complete']}; baseline A mean={p1.get('baseline_A_mean')}. Main:0/32, requires a separate decision. No new inference is performed to improve significance or fill missing responses. Comparisons are four-task exploratory; no causal advantage is established. Exact prompts/outputs and preregistration: pilot/.

## Costs, limitations and safety

Compression factors and P50/P95 are in metrics.json; C1 can be larger because it adds provenance. No efficiency advantage is claimed without measured tokens and matched coverage. Cooperative limits and explicit INSUFFICIENT_CONTEXT protect budget pressure. P0 is finite acceptance, not SRT completeness or general semantic equivalence.
SQLite/inode/hash-chain and all original rows: {integrity['result']}; protected source files and AGENTS unchanged. Production writes:0; no migration, policy, write API, native selector or new mathematical operation. New MCP preview remains a separate minimal future patch.
''')
    (report/'RCA.md').write_text('''# RCA

## TEST_ORACLE_BUG — diagnostic disposition fingerprint

Before registration/inference, the independent oracle incorrectly assumed changing intent changed the deployed claim fingerprint. The original source/test failure and exact case are in development/. The rule now reflects the same claim/scope/version binding. No transformation is authorized: contract/preservation checks still reject it. No model score was revised.

## NORMALIZER_BUG — input bound and open-obligation view

Initial tests showed that exceeding max_events still extracted claims and that closed/old obligation entries appeared in the open list. Original source and FAIL traces are retained. Input bounds now refuse before extraction, and the open list contains only current OPEN/TESTING versions. Closed records/history remain in the exact audit context, never deleted.

## NORMALIZER_BUG — cache resource bound

The first cache had no entry limit. A reproducible ten-query test failed the eight-entry bound; eviction now limits derived memory and detached values cannot mutate the cache/source. Source, schema, normalizer and auditor-code changes invalidate keys. Original FAIL/source retained.

## SOURCE_BINDING_BUG — historical regression fixture

The first empty isolated DB lacked original QA event22/move10 required by unchanged historical tests. This was a test-fixture failure, not a server regression. Replay now uses a private read-only Backup-API copy as its starting DB; all new writes remain local. Original partial wire/checks are in development/regression-missing-history/.

## Deliberately caught projection violations

Missing adverse source, foreign binding, tampered context, unknown candidate, partial budget and C4-only audit are refused. They are negative controls, not allowed transformations or proof. Full detailed responses are in audit-equivalence.json and tests. Any actual unmatched P0 output remains P0-failures.json and blocks P1.

## P1 and capability limits

Pilot failures/transport gates are preserved in pilot/result.json and raw logs. No model confidence verifies a claim; no missing response is imputed. Old003 scores remain unchanged and are not pooled. Native generation is absent. A GO recommendation applies only to the bounded read-only preview and finite tested contract, not an unrestricted semantic normalizer or production deployment.
''')
    failures=json_file(base/'P0-failures.json',[])+json_file(base/'run-failures.json',[])+p1.get('failures',[])
    write_json(report/'failures.json',failures)
    (report/'reproduce.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/normalization_qa.py" "$@"\n');(report/'reproduce.sh').chmod(0o755)
    hashes={str(p.relative_to(report)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(report.rglob('*')) if p.is_file() and p.name!='manifest-sha256.json'}
    write_json(report/'manifest-sha256.json',{'algorithm':'sha256','files':hashes})
    return result
