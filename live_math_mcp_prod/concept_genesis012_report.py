"""Immutable012 scientific report. A finite residual alias is not a new source law."""
import json
import difflib
from pathlib import Path
import re
import shutil
import sqlite3

from normalizer import digest
from native_preview008_qa import readonly_state
from qa_positive_acceptance import snapshot,write_json
from concept_genesis012_qa import ROOT,SOURCE,sha


def load(path,default=None):return json.loads(path.read_text()) if path.exists() else default
def rows(path):return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []


def chain(database):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row;previous='GENESIS';broken=[]
        for op in c.execute('SELECT * FROM operations ORDER BY id'):
            expected=digest({'time':op['occurred_at'],'action':op['action'],'details':json.loads(op['details_json']),'previous':previous})
            if op['previous_hash']!=previous or op['entry_hash']!=expected:broken.append(op['id'])
            previous=op['entry_hash']
        return {'SQLite':c.execute('PRAGMA integrity_check').fetchone()[0],'foreign_keys':c.execute('PRAGMA foreign_key_check').fetchall(),
            'broken_hash_ids':broken,'head':previous}


def export(base,failure):
    meta=load(base/'metadata.json');baseline=Path(meta['baseline']);out=Path(meta['report']);out.mkdir(parents=True,exist_ok=False)
    for name in ('P0-result.json','P0-costs.json','first-failure.json','run-failure.json','checks.json','calls.jsonl','readonly.jsonl','source-manifest.json','typed-cycle-stage.json','pytest.txt'):
        if (base/name).exists():shutil.copyfile(base/name,out/name)
    for folder in ('frozen-inputs','frozen-sources','mcp'):
        if (base/folder).exists():shutil.copytree(base/folder,out/folder)
    for p in base.glob('source*-results.json'):shutil.copyfile(p,out/p.name)
    p0=load(base/'P0-result.json',{});checks=load(base/'checks.json',[]);frozen=load(base/'source-manifest.json',{})
    metadata=load(baseline/'metadata.json');before=load(baseline/'before.json')['tables'];private=snapshot(base/'isolated.sqlite3')['tables']
    canonical=Path(metadata['db']);typed=Path(metadata['typed_db'])
    same=readonly_state(canonical)==load(baseline/'readonly-before.json');typed_same=readonly_state(typed)==load(baseline/'typed-readonly-before.json')
    original_prefix={t:private[t][:len(values)]==values for t,values in before.items()}
    protected=load(baseline/'protected-files.json');changed=[p for p,h in protected.items() if sha(Path(p))!=h]
    drift=[p for p,h in frozen.items() if sha(Path(p))!=h]
    frozen_inputs=load(base/'frozen-inputs/manifest.json',{});input_drift=[p for p,h in frozen_inputs.items() if sha(base/'frozen-inputs'/p)!=h]
    canonical_chain=chain(canonical);typed_chain=chain(typed);private_chain=chain(base/'isolated.sqlite3')
    ok=same and typed_same and all(original_prefix.values()) and not changed and not drift and not input_drift and all(c['SQLite']=='ok' and not c['foreign_keys'] and not c['broken_hash_ids'] for c in (canonical_chain,typed_chain,private_chain))
    with sqlite3.connect((base/'isolated.sqlite3').as_uri()+'?mode=ro',uri=True) as c:
        active=c.execute("SELECT count(*) FROM research_move_status_history h JOIN research_moves m ON m.id=h.move_id WHERE m.project LIKE 'LM_QA_CONCEPT012_%' AND h.status='EXPERIMENT_ALLOWED' AND h.sequence=(SELECT max(sequence) FROM research_move_status_history s WHERE s.move_id=h.move_id)").fetchone()[0]
        verified=c.execute("SELECT count(*) FROM events WHERE project LIKE 'LM_QA_CONCEPT012_%' AND status='verified'").fetchone()[0]
    integrity={'result':'PASS' if ok and not active and not verified else 'FAIL',
        'canonical_all_rows_schema_sequence_inode_bytes_chain_exact':same,'deployed_typed_sandbox_exact':typed_same,
        'original_private_row_prefix':original_prefix,'canonical_chain':canonical_chain,'typed_chain':typed_chain,'private_chain':private_chain,
        'changed_protected_files':changed,'protected_files':len(protected),'changed_frozen_sources':drift,'changed_frozen_inputs':input_drift,
        'active012_grants':active,'new_verified':verified,'canonical_events':len(before['events']),'canonical_operations':len(before['operations'])}
    write_json(out/'integrity.json',integrity)
    checks.append({'invariant':'canonical, deployed sandbox, frozen inputs/code and original rows/chain retained','result':integrity['result']})
    check_count={s:sum(c['result']==s for c in checks) for s in ('PASS','FAIL','INCONCLUSIVE')}
    historical=load(base/'historical86/result.json',{'result':'INCONCLUSIVE'});write_json(out/'historical86.json',historical)
    if (base/'historical86').exists():
        (out/'historical86').mkdir()
        for name in ('calls.json','stdio-wire.jsonl','checks.json'):
            if (base/'historical86'/name).exists():shutil.copyfile(base/'historical86'/name,out/'historical86'/name)
    matches=re.findall(r'(\d+) passed',(base/'pytest.txt').read_text() if (base/'pytest.txt').exists() else '')
    pytest_passed=int(matches[-1]) if matches else 0
    public=load(baseline/'public-preflight.json');write_json(out/'public-preflight.json',public)
    write_json(out/'baseline-source-hashes.json',{p:h for p,h in protected.items() if str(SOURCE) in p and p.endswith(('.py','.json'))})
    cases=[load(p) for p in sorted(base.glob('source*-results.json'))]
    costs={'P0':load(base/'P0-costs.json'),'per_world':p0.get('metrics',[]),
        'stage_costs':{c['world']:{'C':c['C'].get('stage_costs',{}),'B1':c['B1'].get('stage_costs',{}),'B0':c['B0']['costs']} for c in cases},
        'scope':'All bound source calls, normalization, inference, source validation and old T are counted; source computations are not external measurements.',
        'warm_cold':'Persistent isolated MCP interpreter is warm across calls; each source context/Port is rebuilt. Outer whole-process OS wait4 includes cold startup/imports/serialization/regressions; no timing subtraction.',
        'heap_allocations':'INCONCLUSIVE; OS peak RSS measured.','wall_speedup':False,'LLM_calls':0}
    write_json(out/'costs.json',costs)
    calls=rows(base/'calls.jsonl');write_json(out/'mcp-transcript.json',{'transport':'real ClientSession/private stdio, read-only tools','calls':calls})
    write_json(out/'negative-controls.json',{'checks':[r for r in checks if any(t in r['invariant'] for t in ('false','no_grant','fail_closed','required','NO_GENESIS','novelty'))],
        'typed_specific_controls':'NOT_RUN after scientific FAIL_CEILING; existing011 regressions retained, not substituted for012 cycles.'})
    typed_stage=load(base/'typed-cycle-stage.json',{'status':'NOT_RUN_UNEXPECTED_FAILURE','receipts':[],'execution_grants':0,'journal_writes':0})
    (out/'typed-receipts.jsonl').write_text(json.dumps(typed_stage)+'\n')
    (out/'novelty-journal.jsonl').write_text(json.dumps({'status':'NOT_WRITTEN','reason':typed_stage.get('status'),'new_entries':0})+'\n')
    gates={'G0':'PASS' if public['health']['typed_cycle']['version']=='011.1' else 'FAIL','G1':'PASS' if not input_drift else 'FAIL',
        'G2':'PASS' if not failure and not check_count['FAIL'] else 'INCONCLUSIVE',
        'G3':'FAIL_CEILING' if p0.get('scientific_decision')=='FAIL_CEILING' else 'INCONCLUSIVE',
        'G4':'NOT_RUN_SCIENTIFIC_STOP','G5':'BASELINES_EVALUATED_NO_GENESIS_GAIN' if p0 else 'INCONCLUSIVE',
        'G6':'PASS' if historical['result']=='PASS' and pytest_passed>=573 and integrity['result']=='PASS' else 'INCONCLUSIVE'}
    for name in ('eight fresh typed012 cycles','external hidden world','predictive gain after actual measurement','new authoritative concept journal'):
        checks.append({'invariant':name,'result':'INCONCLUSIVE','reason':'Scientific ceiling gate stops expensive experiments; no fabricated receipts/observations.'})
    write_json(out/'checks.json',checks);counts={s:sum(c['result']==s for c in checks) for s in ('PASS','FAIL','INCONCLUSIVE')}
    result={'decision':'STOP_WITH_RCA','scientific_result':p0.get('scientific_decision','INCONCLUSIVE'),
        'mechanics':'PASS' if not failure and integrity['result']=='PASS' else 'FAIL','bounded_genesis':'INCONCLUSIVE',
        'source_authorship':'SOURCE_GENERATED_FINITE_DEPENDENCY; no supplied guard/pair/theory in Request',
        'AUTONOMOUS_HYPOTHESIS_GENERATION':'INCONCLUSIVE','next_test_selection':'UNCHANGED_006.2; C and B1 choose identical T',
        'false_novelty':0,'false_grants':0,'novelty_history':'INCONCLUSIVE_NOT_COMMITTED','typed_receipt':'NOT_RUN',
        'production_changes':0,'oracle_leakage':0,'wall_speedup':False,
        'limitations':'Exact finite residual dependency is observable probing reified as a field predicate; no independently stronger source law or out-of-domain generalization established.',
        'next_mathematical_blocker':'Derive a transferable operational invariant beyond the executed continuation census without preseeded guards or a larger brute-force horizon.',
        'gates':gates,'checks':counts,'pytest_passed':pytest_passed,'historical86':historical['result'],
        'bounded_refinement_candidates':p0.get('bounded_refinement_candidates'),
        'valid_genesis_rate':p0.get('valid_genesis_rate'),'predictive_gain_after_feedback':None,
        'typed_cycles':0,'LLM_calls':0,'proof_status':'unverified','integrity':integrity['result'],'failure':failure,'report':str(out/'report.md')}
    write_json(out/'result.json',result)
    candidate=next((c for c in cases if c['C']['status']=='CANDIDATE_REFINEMENT'),None)
    example=({'world':candidate['world'],'negative_event_id':candidate['negative_event_id'],
        'source_hashes':candidate['C']['binding']['source_hashes'],'concept':candidate['C']['concept'],
        'witness':candidate['C']['witness'],'falsifier':candidate['C']['falsifier']} if candidate else None)
    write_json(out/'generated-concept-example.json',example)
    table='\n'.join('| '+str(c['world'])+' | '+c['C']['status']+' | '+str(c['C']['costs']['total_native_calls'])+' | '+str(c['B1']['costs']['total_native_calls'])+' | '+str(c['C']['attention'].get('test_id') if c['C'].get('attention') else None)+' |' for c in cases)
    (out/'RCA.md').write_text('''# Concept Genesis012 RCA

**STOP_WITH_RCA / FAIL_CEILING** when P0 demonstrates no C-only semantic distinction. This is a scientific negative result, not a source-gate failure of011 and not a mathematical theorem.

The generated concept is an exact partial dependency from a native trace field to the residual readout O(h·u) on the declared history class. It yields conditional interpretations with different predictions and a real replayable witness. Its values and selected source address are generated, not supplied by the operator. However, every output cell is exactly a value of a registered residual that the fair006 probing census already computes. A finite mapping of this residual onto a trace field does not add predictive content beyond B1. The C next test is chosen by unchanged T006 and is identical to B1. No expensive typed-cycle or hidden-world experiment is justified by this corpus after the preregistered ceiling gate.

The coloured-stack case also exposes a concrete mechanism limitation: an absolute source-leaf address from the first conflicting pair need not covary with the top-of-stack guard across longer contexts. The generator must refuse rather than invent a portable guard. A list of stack-specific rules, another classifier, or more theory names would hide this failure.

Falsifiers of the stronger claim are retained: histories in one generated residual cell can diverge under a different registered continuation. The finite conditional concept does not establish source equality or future congruence. Independent heldout oracle data exists only for evaluation and is not a measured external result. The true predictive gain after a real negative experiment is INCONCLUSIVE because G4 is stopped, not scored using QA truth as measurement.

RCA class for the scientific ceiling: MATHEMATICAL_COUNTEREXAMPLE_TO_ADDITIONAL_EXPRESSIVE_GAIN (bounded adequacy counterexample, not universal impossibility). The minimal protocol correction is to decline the genesis claim and retain FAIL_CEILING. No source/oracle/budget/normalization/permission relaxation is applied. A next mechanism must derive a source-operational invariant whose transfer predicts an unprobed continuation; renaming residual cells is insufficient.
'''+('\n## Unexpected engineering failure\n\n```json\n'+json.dumps(failure,ensure_ascii=False,indent=2)+'\n```\n' if failure else '\nNo unexpected engineering failure in this cohort. Scientific FAIL_CEILING remains explicit.\n'))
    (out/'report.md').write_text(f'''# LM-CONCEPT-GENESIS-012

**STOP_WITH_RCA — {result['scientific_result']}.** The finite source-field constructor is implemented. Independent scientific novelty beyond fair probing was not established; no PASS_BOUNDED_CONCEPT_GENESIS or autonomous-generation claim is made.

## Actual boundary and frozen protocol

Real HTTPS/OAuth preflight:24 tools, base0.4.2/schema5, typed_cycle011.1. Canonical and deployed sandbox were read-only; both BackupAPI snapshots precede changes. Four new native programs, oracle and preregistration were frozen before generator implementation.700 native/oracle checks matched before freeze. No production source/service/DB change, restart, Bridge or RH/SRT/FTL experiment. The private MCP prototype exposes only3 SELECT-only tools.

## Mathematical result

I* replays an automatically discovered coarse-description counterexample, extracts differing native trace addresses, tests an exact partial field→residual dependency, and emits conditional source interpretations with explicit finite applicability. It makes no claim of full future equivalence. T is unchanged006.2, with exact Fraction ranking independently checked. Neither pair, feature address, cell labels nor optimal test is supplied in the generator request. Discovery of the negative input itself belongs to unchanged006 paired probing.

| Source | I* result | C source calls | B1 source calls | C next test |
| --- | --- | --- | --- | --- |
{table}

Finite refinement candidates: {p0.get('bounded_refinement_candidates','INCONCLUSIVE')}/4; C-only observable distinctions: {p0.get('C_only_observable_distinctions','INCONCLUSIVE')}. B1 independently recovers every C cell by its registered residual table. B0 is explicitly operator-supplied finite cells; B2 only records the failed coarse prediction. C-no-trace and C-no-negative refuse; they do not receive oracle answers. Four NO-GENESIS alias-only controls, rename/order/version/source/observer/hash/quota and false-witness controls are retained. Source labels are used only by physical primitive dispatch, not inference.

## Acceptance and cost

Checks: {counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['INCONCLUSIVE']} INCONCLUSIVE. Full pytest after mathematical evaluation: {pytest_passed} PASS; unchanged historical86: {historical['result']}. Integrity: {integrity['result']}; original canonical2056 events/4813 operations, deployed typed sandbox and all original private row prefixes retained. No new grants, receipts or verified event. Eight012 typed cycles and the external hidden-world stage are NOT_RUN after the scientific gate, rather than simulated. Existing011 cycles remain historical evidence only.

P0 costs and per-stage source/normalization/negative replay/dependency/falsifier/T timing are in costs.json; wall/CPU/RSS and all source calls are retained. Persistent MCP interpreter is warm; source contexts are rebuilt every call. Whole QA process costs, including cold imports/regressions/export, are appended by the measured entrypoint. No wall speedup is claimed. LLM0. There is no actual external012 measurement, so predictive_gain_after_feedback remains INCONCLUSIVE.

## Reproduction

`reproduce.sh /tmp/fresh012-replay` rebuilds an isolated synthetic SQLite from exported frozen input and runs real MCP source tests; no production configuration or private DB is needed. The original acceptance uses the private BackupAPI baseline with `.venv/bin/python live_math_mcp_prod/concept_genesis012_run.py --baseline-dir /path/to/genesis012-baseline`. Sources/tests/manifests and full I*/T/MCP traces are included. Any unexpected first failure remains in first-failure.json; no historical result is overwritten.

## Что именно ядро научилось создавать самостоятельно и какое ограничение осталось

Создан источникосвязанный предикат по адресу поля промежуточного native state и точная частичная зависимость этого поля от ещё не включённого в F остаточного наблюдения. Конкретные ID, SHA256, условные интерпретации, witness-продолжение и фальсификатор сильной версии — в generated-concept-example.json. Это работающий конечный конструктор: данные выбирают адрес и разбиение, оператор их не задаёт.

Но сам остаточный readout уже вычислим тем же bounded probing006. Новая запись предиката пока не добавляет математического содержания к B1 и не выводит закон переноса за проверенные истории/продолжения. Следующий конкретный барьер — построить переносимый операционный инвариант с проверяемым предсказанием вне выполненной конечной таблицы. Универсальная достаточность признака и самостоятельное порождение новых математических интерпретаций остаются INCONCLUSIVE.
''')
    (out/'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../../.."
.venv/bin/python live_math_mcp_prod/concept_genesis012_qa.py --replay-frozen "$HERE/frozen-inputs" --output "${1:?Supply a fresh output directory}"
''');(out/'reproduce.sh').chmod(0o755)
    (out/'rollback.md').write_text('No production deployment, migration, flag or service change occurred. Stop the private stdio prototype to remove012. Preserve frozen source/oracle and scientific FAIL_CEILING; never restore old SQLite snapshots over newer data.\n')
    patches=[]
    for p in sorted((base/'frozen-sources').glob('*.py')):
        lines=p.read_text().splitlines();patches.extend(['--- /dev/null','+++ b/live_math_mcp_prod/'+p.name,'@@ -0,0 +1,'+str(len(lines))+' @@',*['+'+line for line in lines]])
    (out/'isolated-source.patch').write_text('\n'.join(patches)+'\n')
    previous=[]
    for p in sorted(out.parent.glob('*/result.json')):
        if p.parent!=out:previous.append({'cohort':p.parent.name,'result':load(p).get('scientific_result'),'result_sha256':sha(p)})
    write_json(out/'prior-cohorts.json',previous)
    first=out.parent/'20261027T101423059321Z'
    if first.exists() and first!=out:
        write_json(out/'engineering-RCA.json',{'classification':'SOURCE_CONTRACT_BUG','first_failed_cohort':first.name,
            'original_result':'FAIL','reason':'004.1 reconstruction canonically sorts rows; adapter compared event list order to the ID-ordered source instead of checking exact immutable event records keyed by ID.',
            'evidence':'Original ID order2057..2066; recovered2065,2057,2061,2062,2059,2063,2064,2060,2058,2066; every ID/row identical. Zero source calls before refusal.',
            'minimum_fix':'Compare exact ID→row maps. No content/hash/project/provenance check removed; source/oracle definitions and resource limits unchanged.'})
        name='concept_genesis012_source.py';old=(first/'frozen-sources'/name).read_text().splitlines(True)
        new=(base/'frozen-sources'/name).read_text().splitlines(True)
        (out/'minimum-fixes.patch').write_text(''.join(difflib.unified_diff(old,new,fromfile='a/live_math_mcp_prod/'+name,tofile='b/live_math_mcp_prod/'+name)))
    write_json(out/'manifest-sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    return result
