"""011 isolated evidence export; no canonical DB or OAuth credential publication."""
import json
from pathlib import Path
import re
import shutil
import sqlite3

from normalizer import digest
from qa_positive_acceptance import snapshot,write_json
from native_preview008_qa import readonly_state
from research_cycle009_report import integrity as canonical_integrity
from typed_cycle011_contract import MeasurementEnvelope,ReceiptRequest,CyclePrecommit
from typed_cycle011_qa import SOURCE,ROOT,sha


def load(p,default=None):return json.loads(p.read_text()) if p.exists() else default
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []


def export(base,failure):
    meta=load(base/'metadata.json');baseline=Path(meta['baseline']);out=Path(meta['report']);out.mkdir(parents=True,exist_ok=False)
    for name in ('checks.json','gates.json','negative-controls.json','first-failure.json','run-failure.json','calls.jsonl','lifecycle-ledger.jsonl','costs.jsonl',
                 'operator-ledger.jsonl','database-routing.jsonl','frozen-source-manifest.json','oracle.json','worlds.json','manifest.json','pytest.txt','feedback-RCA-reproducer.json'):
        if (base/name).exists():shutil.copyfile(base/name,out/name)
    for folder in ('frozen-sources','world-inputs','sealed-environments','sessions','measurement-artifacts'):
        if (base/folder).exists():shutil.copytree(base/folder,out/folder)
    for p in base.glob('*-preview.json'):shutil.copyfile(p,out/p.name)
    if (baseline/'development').exists():shutil.copytree(baseline/'development',out/'development')
    historical=load(base/'historical86/result.json',{'result':'INCONCLUSIVE'})
    write_json(out/'historical86.json',historical)
    if (base/'historical86').exists():
        (out/'historical86').mkdir()
        for n in ('checks.json','calls.json','stdio-wire.jsonl','server-stderr.txt'):
            if (base/'historical86'/n).exists():shutil.copyfile(base/'historical86'/n,out/'historical86'/n)
    public=load(baseline/'public-preflight.json');write_json(out/'public-preflight.json',public)
    intact=canonical_integrity(baseline)
    db=base/'isolated.sqlite3';before=load(baseline/'before.json')['tables'];after=snapshot(db)['tables']
    prefix={t:after[t][:len(values)]==values for t,values in before.items()}
    prior='GENESIS';broken=[]
    for op in after['operations']:
        expected=digest({'time':op['occurred_at'],'action':op['action'],'details':json.loads(op['details_json']),'previous':prior})
        if op['entry_hash']!=expected or op['previous_hash']!=prior:broken.append(op['id'])
        prior=op['entry_hash']
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
        sql=c.execute('PRAGMA integrity_check').fetchone()[0];fk=c.execute('PRAGMA foreign_key_check').fetchall()
        active=c.execute("SELECT count(*) FROM research_move_status_history h JOIN research_moves m ON m.id=h.move_id WHERE m.project LIKE 'LM_QA_TYPED011_%' AND h.status='EXPERIMENT_ALLOWED' AND h.sequence=(SELECT max(sequence) FROM research_move_status_history s WHERE s.move_id=h.move_id)").fetchone()[0]
        schema=c.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'typed011_%' ORDER BY name").fetchall()
    auxiliary=[]
    for auxiliary_db in base.glob('*.sqlite3'):
        if auxiliary_db==db:continue
        with sqlite3.connect(auxiliary_db.as_uri()+'?mode=ro',uri=True) as c:
            count=c.execute("SELECT count(*) FROM research_move_status_history h JOIN research_moves m ON m.id=h.move_id WHERE m.project LIKE 'LM_QA_TYPED011_%' AND h.status='EXPERIMENT_ALLOWED' AND h.sequence=(SELECT max(sequence) FROM research_move_status_history s WHERE s.move_id=h.move_id)").fetchone()[0]
            auxiliary.append({'database':auxiliary_db.name,'active_QA_grants':count,'SQLite':c.execute('PRAGMA integrity_check').fetchone()[0]})
    verified=[e['id'] for e in after['events'] if e['project'].startswith('LM_QA_TYPED011_') and e['status']=='verified']
    canonical_after=readonly_state(Path(load(baseline/'metadata.json')['db']))
    canonical_bytes=canonical_after==load(baseline/'readonly-before.json')
    frozen=load(base/'frozen-source-manifest.json');drift=[n for n,h in frozen.items() if sha(Path(n))!=h]
    good=intact['result']=='PASS' and canonical_bytes and all(prefix.values()) and not broken and sql=='ok' and not fk and not active and not verified and not drift and all(not r['active_QA_grants'] and r['SQLite']=='ok' for r in auxiliary)
    intact.update(result='PASS' if good else 'FAIL',canonical_rows_schema_sequence_inode_bytes_chain_exact=canonical_bytes,
        private_original_row_prefix=prefix,private_hash_chain_broken=broken,private_chain_head=prior,private_SQLite=sql,private_FK=fk,
        active_QA_grants=active,new_verified=verified,frozen_source_drift=drift,
        baseline_counts={t:len(v) for t,v in before.items()},final_counts={t:len(v) for t,v in after.items()},
        new_rows={t:len(v)-len(before.get(t,[])) for t,v in after.items()},typed_schema_sql=schema,auxiliary_fixture_databases=auxiliary)
    write_json(out/'integrity.json',intact)
    checks=load(base/'checks.json',[]);checks.append({'invariant':'canonical/private retention, hash-chain, SQL/FK, no grants/no verified, source freeze','result':'PASS' if good else 'FAIL'})
    gates=load(base/'gates.json',{});pytest_text=(base/'pytest.txt').read_text() if (base/'pytest.txt').exists() else ''
    matches=re.findall(r'(\d+) passed',pytest_text);passed=int(matches[-1]) if matches else 0
    if gates.get('G5')=='PASS' and (not good or historical['result']!='PASS' or passed<555):gates['G5']='FAIL'
    for key in ('G0','G1','G2','G3','G4','G5'):
        checks.append({'invariant':key,'result':gates.get(key,'INCONCLUSIVE')})
    for name in ('physical external measurement authenticity','per-allocation heap profile','isolated novelty-lookup timing'):
        checks.append({'invariant':name,'result':'INCONCLUSIVE','reason':'Outside the measured bounded local structural acceptance; no positive scientific/performance claim.'})
    write_json(out/'checks.json',checks);write_json(out/'gates.json',gates)
    ledger=rows(base/'lifecycle-ledger.jsonl');calls=rows(base/'calls.jsonl');operator=rows(base/'operator-ledger.jsonl')
    write_json(out/'mcp-transcript.json',{'transport':'actual ClientSession/stdio on one private BackupAPI clone; local operator requests captured separately',
        'calls':calls,'database_routing':rows(base/'database-routing.jsonl'),'operator_requests_responses':operator,'wire_files':[str(p.relative_to(out)) for p in out.glob('sessions/*/wire.jsonl')]})
    measurements=[e for e in after['events'] if e['project'].startswith('LM_QA_TYPED011_') and 'measurement_binding' in e['content']]
    (out/'measurement-events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in measurements))
    (out/'novelty-journal.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in after.get('typed011_journal',[])))
    (out/'typed-receipts.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in after.get('typed011_receipts',[])))
    (out/'precommits.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in after.get('typed011_precommits',[])))
    write_json(out/'source-envelope.schema.json',MeasurementEnvelope.model_json_schema())
    write_json(out/'receipt.schema.json',ReceiptRequest.model_json_schema());write_json(out/'precommit.schema.json',CyclePrecommit.model_json_schema())
    costs={'preview_measurements':rows(base/'costs.jsonl'),'operator_executor_measured_processes':operator,
        'CPU_overlap':'Worker/executor CPU are subsets of whole QA usage; never add twice.',
        'source_lookup':'source_lookup_wall_ns in preview; authoritative journal SELECT included in controller wall, not independently timed.',
        'worker_startup':'008 cold wall/child CPU includes launch/imports through exit; no warm cache or speedup claim.',
        'heap_allocation':'INCONCLUSIVE: RSS measured, individual heap allocations not separately instrumented',
        'baseline009':load(ROOT/'docs/qa/LM-RESEARCH-CYCLE-009/20261027T061232007705Z/result.json').get('whole_QA_exit_usage'),
        'comparison':'011 includes new validation/commit/journal. Different work from009; no throughput acceleration established.',
        'speedup_claim':False,'LLM_calls':0}
    write_json(out/'costs.json',costs)
    count={status:sum(c['result']==status for c in checks) for status in ('PASS','FAIL','INCONCLUSIVE')}
    complete=not failure and good and all(gates.get(g)=='PASS' for g in ('G0','G1','G2','G3','G4','G5')) and count['FAIL']==0
    result={'decision':'PASS_TYPED_CYCLE_BOUNDED' if complete else 'STOP_WITH_RCA','gates':gates,
        'source_contract':'PASS' if gates.get('G2')=='PASS' else 'FAIL','typed_cycle':'PASS' if complete else 'INCONCLUSIVE',
        'journal':'PASS' if gates.get('G3')=='PASS' else 'INCONCLUSIVE','deployment':'NOT_REQUESTED',
        'isolated_engine_deployment_review_ready':complete,'checks':count,'pytest_passed':passed,'historical86':historical['result'],
        'six_cycle_steps':len([r for r in ledger if r['world'] in {'affine','permutation','erasure'}]),
        'completed_typed_receipts':len(after.get('typed011_receipts',[])),'lifecycle_ids':ledger,
        'MCP_calls':len(calls),'LLM_calls':0,'proof_status':'unverified','no_active_QA_grants':not active,
        'production_writes':0,'production_deployed':False,'production_version':public['health']['version'],
        'baseline_events':len(before['events']),'final_private_events':len(after['events']),
        'new_private_events':len(after['events'])-len(before['events']),'failure':failure,'report':str(out/'report.md')}
    write_json(out/'result.json',result)
    table='\n'.join('| {world} | {version} | {move_id} | {audit_id} | {activation_operation_id} | {event_id} | {receipt_id} | {outcome} |'.format(**r) for r in ledger)
    (out/'report.md').write_text(f'''# LM-TYPED-SOURCE-CYCLE-011

**{result['decision']}**. source_contract={result['source_contract']}; typed_cycle={result['typed_cycle']}; journal={result['journal']}; deployment=NOT_REQUESTED.

## Gates and acceptance

{json.dumps(gates,ensure_ascii=False)}

Final checks: {count['PASS']} PASS, {count['FAIL']} FAIL, {count['INCONCLUSIVE']} INCONCLUSIVE. Full pytest: {passed} PASS. Unchanged historical MCP regression: {historical['result']} (86 expected). Real MCP calls: {len(calls)}; LLM:0. Main three worlds: {result['six_cycle_steps']}/6 steps; total typed receipts including INCONCLUSIVE/ERROR controls: {result['completed_typed_receipts']}.

| World | Version | Move | Audit | Activation op | Fresh event | Receipt | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
{table}

Exact event/precommit hashes, scope and binding provenance are in lifecycle-ledger.jsonl, measurement-events.jsonl and typed-receipts.jsonl. IDs are qualified by this isolated cohort/database/project; no historical009 row is upgraded. Raw full MCP schemas/requests/responses and operator command requests/responses are retained.

## Authority and implementation

The private011 MCP exposes proposal/precommit and SELECT-only preview/validation/history. It exposes no generic activation, completion, audit or operator disposition tool. Source writes are restricted to LM_QA_TYPED011_ namespaces. Local operator CLI owns scoped adverse dispositions, explicit activation and atomic commit. Independent external executor opens the sealed source only after checking current exact precommit/audit/grant; event creation uses the existing event API. Read-only validator checks actual immutable event, source hashes, precommit fingerprint, current frontier, audit/activation operation, event ordering, observer/test/ordered suffix, expected readout/outcome and local artifact receipt. Commit repeats this check in BEGIN IMMEDIATE and appends terminal status/receipt/journal/idempotency decision together. Injected journal failure verifies rollback in unit tests.

Server journal is scope/source-family local. Claim identity uses native definition, ordinal operations/histories, observer and finite domain; version and display labels are provenance. Action identity and canonical source addresses remain distinct. Caller known_fingerprints is ignored. Preview inserts nothing; raw conflicts return REVIEW. Existing004.1 normalization,006.2 I/T and007.2 constructor run unchanged inside the008 bounded worker. Oracle and sealed target are never imported by the decision engine.

This is bounded synthetic research with operator source/projection/review input. It is not an autonomous researcher. Local executor receipt/artifact hashing establishes local software integrity; JSON Schema and executor_id do not authenticate physical measurements. Other external artifacts remain DECLARED_UNINSPECTED and cannot be promoted into this trusted local path. All mathematical proof statuses remain unverified, including SUCCESS and COMPLETED.

## Integrity, regressions and limitations

Canonical SQLite: {intact['result']}; {intact['events']} original events/{intact['operations']} operations; byte/schema/sequence/inode/all-row/chain match={canonical_bytes}. Private copy retains all original row prefixes={all(prefix.values())}, SQL={sql}, broken chain entries={len(broken)}, active QA grants={active}, new verified={len(verified)}. Schema5 unchanged; only private typed011 tables/triggers added. Baseline vs final/new row counts and full typed schema are in integrity.json. Historical009/010 source/events/reports/FAILs remain unchanged.

CPU/wall/RSS/native I-versus-T/normalization costs are retained in costs.json and raw preview receipts; whole-process wait4 is appended by typed_cycle011_run.py after exit. Heap allocations and physical authenticity remain INCONCLUSIVE. No acceleration is claimed against009 because011 performs additional work. Exact journal lookup time is included in controller latency, not isolated as a separate timing.

## Reproduction and deployment boundary

From repository root: `.venv/bin/python live_math_mcp_prod/typed_cycle011_run.py --baseline-dir /path/to/private/typed011-baseline`. The private baseline contains a BackupAPI snapshot and read-only public preflight; it is intentionally not exported. Reproduce contract/integration checks without any private data: `.venv/bin/python -m pytest -q live_math_mcp_prod/test_typed_cycle011.py`. The report package contains frozen public fixtures/oracle after trial, schemas, source diff and hashes. New cohorts preserve prior failures. Deployment010/011 has not occurred; no restart/reconnection is required. Review readiness of the isolated engine: {complete}.
''')
    (out/'RCA.md').write_text('''# RCA and trust boundary

010 MISSING_SOURCE_CONTRACT_METADATA is addressed only by new typed011 events. The six legacy009 events are still rejected without binding in independent regression tests. No adjacent harness JSONL is treated as historical event metadata.

SOURCE_CONTRACT_BUG means missing precommit/envelope; MEASUREMENT_BINDING_BUG means accepting a wrong/stale event; JOURNAL_IDENTITY_BUG means false rename/version novelty or duplicate/conflicting raw identity; MCP_LIFECYCLE_BUG means unauthorized activation/commit. TEST_ORACLE_BUG, TEST_FIXTURE_BUG, TRANSPORT_FAILURE, MISSING_CAPABILITY and MATHEMATICAL_COUNTEREXAMPLE remain distinct categories. Expected adversarial denials are not discovered defects.

Stage A creates precommit before audit/measurement, independently validates current ledger linkage and a fresh event. Stage B adds operator-only transactional receipt/journal. File/database access of the local Linux operator is trusted; remote model tools never receive that authority. A local executor identifier alone is not authenticity. The validator additionally checks the operator-local execution row and actual artifact bytes; this establishes only synthetic local receipt integrity. Sealed finite QA is not autonomous scientific truth.

The earlier development cohort lacked server-owned latest-feedback selection when the caller omitted feedback. SOURCE_CONTRACT_BUG: novelty history was authoritative, but T could remain stale until the harness supplied feedback. The current controller resolves a committed negative event itself, and requires a hash-bound, provenance-linked version projection for other current observations. `feedback-RCA-reproducer.json` (when present) captures real old/new MCP responses on the same fresh source, preserving old_result=FAIL. The earlier STOP cohort, sources and trace remain unchanged. This is a controller contract repair, not an I/T or oracle change.

Operator source applicability projections and scoped diagnostic dispositions are explicit inputs. FAILURE excludes only the applicable predictive guard; the independent branch survives. Review is not refutation. Every receipt terminal outcome is unverified. Any failing gate below stops readiness, and old traces/results are retained rather than rewritten.
'''+('\n## Current failure\n\n```json\n'+json.dumps(failure,ensure_ascii=False,indent=2)+'\n```\n' if failure else '\nNo unexpected failure recorded in this cohort. Missing gates (if any) remain INCONCLUSIVE.\n'))
    (out/'rollback.md').write_text('''# Rollback and compatibility

Production0.4.2/schema5/20 tools are unchanged. No production SQL migration, service change or MCP reconnection is needed. Isolated011 adds eight append-only typed tables and triggers without changing user_version5 or existing tables/API. A configuration marker binds the forbidden canonical file; server startup and every local writer reject an unmarked DB or canonical file/hardlink. Stop its stdio process to remove the experimental endpoint. Preserve the private clone and evidence; never restore an old backup over live newer research.

Production deployment requires a separate owner decision after review of all gates. The optional deployment.patch contains only new isolated source files, not a change to public OAuth routes/policies. It must not be applied automatically. Generic legacy completion semantics remain unchanged; only the new isolated typed path claims stronger binding. Trusted local operator/file/database authority cannot be obtained through its MCP tools.
''')
    (out/'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../.."
.venv/bin/python -m pytest -q live_math_mcp_prod/test_typed_cycle011.py
if [ "$#" -gt 0 ]; then .venv/bin/python live_math_mcp_prod/typed_cycle011_run.py "$@"; fi
''');(out/'reproduce.sh').chmod(0o755)
    patches=[]
    for p in sorted((base/'frozen-sources').glob('*.py')):
        lines=p.read_text().splitlines();patches.extend(['diff --git a/live_math_mcp_prod/'+p.name+' b/live_math_mcp_prod/'+p.name,
            'new file mode 100644','--- /dev/null','+++ b/live_math_mcp_prod/'+p.name,'@@ -0,0 +1,'+str(len(lines))+' @@',*['+'+line for line in lines]])
    (out/('deployment.patch' if complete else 'minimum-isolated.patch')).write_text('\n'.join(patches)+'\n')
    write_json(out/'changed-files.json',{'new_files':[str(Path('live_math_mcp_prod')/p.name) for p in (base/'frozen-sources').glob('*.py')],
        'existing_source_files_modified':[],'production_modified':False,'schema_migration':'Private typed011 tables/triggers only; original schema5 unchanged'})
    previous=[]
    for p in sorted(out.parent.glob('*/result.json')):
        if p.parent==out:continue
        d=load(p);previous.append({'cohort':p.parent.name,'decision':d['decision'],'result_sha256':sha(p),'failure':d.get('failure')})
    write_json(out/'prior-cohorts.json',previous)
    write_json(out/'prior-failure-RCA.json',{'cohort':'20261027T081801566413Z','classification':'TEST_FIXTURE_BUG',
        'original_result':'FAIL','invariant':'affine:version_rebind_not_new',
        'actual_refusal':'INSUFFICIENT_CONTEXT / NORMALIZATION_INCOMPLETE: Output/time budget cannot preserve the registered audit closure',
        'cause':'Malformed-envelope fault injection accumulated in the main research source closure until normalizer audit-token cap refused the version3 view.',
        'minimum_fix':'Run the identical fault injection on a BackupAPI clone, preserve all raw cases there, close copied permissions and keep the scientific source/journal on the main clone. No budget increase, source truncation, I/T or oracle change.',
        'preservation':'Original FAIL, first-failure, source hashes and MCP wire remain unchanged; this is a new cohort.'})
    write_json(out/'manifest-sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    return result
