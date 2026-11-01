"""Seal014 evidence, integrity, source diff and an unapplied storage review patch."""
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from normalizer import canonical,digest
from qa_positive_acceptance import snapshot,write_json
from native_preview008_qa import readonly_state
from research_store import ResearchStore
from operational013_report import chain
from law_validation014_operator import commit

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def lines(path):return [json.loads(s) for s in path.read_text().splitlines()]


def cleanup(database):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        obligations=[dict(r) for r in c.execute('SELECT * FROM research_obligations WHERE project LIKE ?',('LM_QA_TYPED011_LV014_%',))]
    if not obligations:return None
    store=ResearchStore(database);before=snapshot(database)
    with store._connect() as c:moves=[dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project LIKE ?',('LM_QA_TYPED011_LV014_%',))]
    abandoned=[]
    for row in moves:
        view=store.moves.inspect(row['project'],row['id'])
        if view['status'] not in {'COMPLETED','ABANDONED','REJECTED'}:
            store.moves.transition(row['project'],row['id'],'abandon','014:cleanup:'+str(row['id']),reason='Retained QA run finished; original result remains immutable.')
            abandoned.append(row['id'])
    for ob in obligations:
        current=store.frontier.history(ob['id'])[-1]
        if current['status'] in {'OPEN','TESTING'}:
            blocked=ob['project'].endswith('_B')
            store.frontier.update(ob['id'],current['version'],{'status':'BLOCKED' if blocked else 'RESOLVED',
                'closure_reason':'Candidate law counterexample requires independent review.' if blocked else 'Finite QA obligation finished; not mathematical verification.',
                'reopen_conditions':['New source-backed applicability evidence and explicit operator review required.']})
    after=snapshot(database)
    preserved={t:after['tables'][t][:len(rows)]==rows for t,rows in before['tables'].items() if t!='research_obligations'}
    active=[m['id'] for m in moves if store.moves.inspect(m['project'],m['id'])['execution_permission']['allowed']]
    return {'abandoned':abandoned,'active_grants':active,'all_immutable_prefixes_preserved':all(preserved.values()),'chain':chain(database)}


def main():
    base=Path(Path('/tmp/lm014_path').read_text().strip());current=json.loads((base/'current.json').read_text());out=Path(current['output']);db=Path(current['database'])
    p0=json.loads((out/'result.json').read_text())
    if p0['status']!='P0_PASS_REGRESSIONS_PENDING':raise SystemExit('P0_GATE_NOT_PASSED')
    write_json(out/'P0-result.json',p0)
    receipts=lines(out/'typed-receipts.jsonl');trace=json.loads((out/'mcp-transcript.json').read_text())
    # Repeated key cannot replace a real terminal result, even for the operator path.
    r=receipts[0]['receipt'];changed={k:r[k] for k in ('project','move_id','event_id','request_key','outcome','observed','summary','reason','proof_status')}
    changed['reason']+=' Changed result attempt.';before=readonly_state(db)
    try:commit(db,changed);key_conflict=False
    except ValueError as error:key_conflict=str(error)=='RECEIPT_REQUEST_KEY_CONFLICT'
    key_conflict &= readonly_state(db)==before
    lifecycle=[]
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        lifecycle=[dict(r) for r in c.execute('SELECT h.* FROM research_move_status_history h JOIN research_moves m ON m.id=h.move_id WHERE m.project LIKE ? ORDER BY h.id',('LM_QA_TYPED011_LV014_%',))]
        journal=[dict(r) for r in c.execute('SELECT * FROM typed011_journal WHERE project LIKE ?',('LM_QA_TYPED011_LV014_%',))]
    write_json(out/'lifecycle-traces.json',lifecycle);write_json(out/'novelty-journal.json',journal)
    cleanup_results={}
    for path in sorted(base.rglob('*.sqlite3')):
        result=cleanup(path)
        if result:cleanup_results[str(path.relative_to(base))]=result
    source=snapshot(base/'canonical.sqlite3');actual=snapshot(db)
    retained={t:actual['tables'][t][:len(rows)]==rows for t,rows in source['tables'].items()}
    meta=json.loads((base/'metadata.json').read_text());old=json.loads((base/'before.json').read_text())
    now={name:readonly_state(Path(meta[name])) for name in ('canonical','deployed_typed')}
    protected=json.loads((base/'protected.json').read_text());bad=[p for p,h in protected.items() if sha(ROOT/p)!=h]
    pre=json.loads((base/'live-preflight.json').read_text());post=json.loads((base/'live-postflight.json').read_text())
    integrity={'canonical_and_deployed_exactly_unchanged':now==old,'before':old,'after':now,'all_original_rows_retained':all(retained.values()),
        'retained_tables':retained,'protected_files':len(protected),'all_prior_sources_reports_AGENTS_unchanged':not bad,'changed_protected_files':bad,
        'public_tool_schemas_unchanged':pre['tools']==post['tools'],'public_health_unchanged':pre['health']==post['health'],
        'primary_QA_chain':chain(db),'retained_attempt_cleanup':cleanup_results,
        'zero_all_QA_grants':all(not r['active_grants'] for r in cleanup_results.values()),
        'all_retained_immutable_prefixes_preserved':all(r['all_immutable_prefixes_preserved'] for r in cleanup_results.values()),
        'result_substitution_under_request_key_refused':key_conflict}
    write_json(out/'integrity.json',integrity);write_json(out/'protected-sha256.json',protected)
    security=json.loads((base/'security-before-after.json').read_text());write_json(out/'security-before-after.json',security)
    historical=json.loads((base/'historical86.json').read_text());write_json(out/'historical86.json',historical)
    shutil.copy2('/tmp/lm014-pytest.txt',out/'pytest.txt')
    pytest_text=(out/'pytest.txt').read_text();match=re.search(r'(\d+) passed.*?in ([\d.]+)s',pytest_text)
    if not match:raise ValueError('PYTEST_RESULT_MISSING')
    for phase in ('preflight','postflight'):
        shutil.copy2(base/('live-'+phase+'.json'),out/('live-'+phase+'.json'))
        shutil.copy2(base/('live-'+phase)/'mcp-wire.jsonl',out/('live-'+phase+'-wire.jsonl'))
    reproduced=json.loads((base/'reproduced013/result.json').read_text())
    write_json(out/'013-reproduced-NO-GO.json',reproduced)
    oracle=lines(out/'oracle.jsonl');write_json(out/'oracle.json',oracle)
    counterexamples=[{'source':r['source'],'step':r['step'],'receipt':r,'oracle':next(o for o in oracle if o['source']==r['source'] and o['step']==r['step']),
        'effect':'Stop the candidate law; no source-backed safe complement was derived, so REQUIRES_REVIEW.'}
        for r in receipts if r['purpose']=='VALIDATE_TRANSFER' and r['receipt']['outcome']=='FAILURE']
    write_json(out/'counterexamples.json',counterexamples)
    engine=lines(out/'native-meter.jsonl');counts={'engine':dict(Counter(r['operation'] for r in engine))};stages={}
    for row in engine:stages.setdefault(row['stage'],Counter())[row['operation']]+=1
    counts['engine_by_stage']={k:dict(v) for k,v in stages.items()}
    counts['discovery_and_separate_validation']={key:json.loads((out/('discovery-'+key+'.json')).read_text())['costs'] for key in 'ABCD'}
    counts['external_instruments']={path.stem:json.loads(path.read_text())['costs'] for path in sorted(out.glob('instrument-*.json'))}
    discovery_total=sum(len(json.loads((out/('discovery-'+k+'.json')).read_text())['native_trace']) for k in 'ABCD')
    instrument_total=sum(sum(phase.values()) for c in counts['external_instruments'].values() for phase in c.values())
    total=len(engine)+discovery_total+instrument_total
    os_costs=json.loads((base/'P0-final-costs.json').read_text());limits=json.loads((out/'source-freeze.json').read_text())['policy']['budgets']
    budget=total<=limits['native_queries_per_world'] and os_costs['wall_ns']<=limits['P0_wall_s']*1e9 and os_costs['CPU_ns_including_reaped_descendants']<=limits['P0_CPU_s']*1e9 and os_costs['peak_RSS_KiB']<=limits['RSS_KiB']
    costs={'native_queries':counts,'actual_all_native_API_queries':total,'engine_queries':len(engine),'discovery_validation_queries':discovery_total,
        'external_instrument_queries':instrument_total,'P0_process_tree':os_costs,'registered_resource_gate':'PASS' if budget else 'FAIL',
        'oracle_receipt_raw_E_steps':sum(len(o['steps']) for o in oracle),
        'random_control':'Same frozen admissible domain, eligibility-forecast budget and execution cost. Post-execution counterfactual evaluator; not extra committed measurements.',
        'CPU_by_native_primitive':'NOT_SEPARATELY_CAPTURED; exact process-tree CPU includes all preparation, normalization, prediction, execution, validation and fault-control costs.',
        'serialization_bytes_before_runtime_export':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),
        'regressions':{'pytest_wall_s':float(match.group(2)),'historical86_wall_ns':historical['wall_ns'],'separate_from_P0':True},
        'wall_speedup':'NOT_CLAIMED','LLM_calls':0}
    write_json(out/'native-costs.json',costs)
    good=all([now==old,all(retained.values()),not bad,pre['tools']==post['tools'],pre['health']==post['health'],
        integrity['primary_QA_chain']['hash_chain_ok'],integrity['zero_all_QA_grants'],integrity['all_retained_immutable_prefixes_preserved'],
        key_conflict,security['status']=='PASS',historical['passed']==86,historical['failed']==0,int(match.group(1))==607,budget])
    gates=json.loads((out/'gates.json').read_text());gates['G6 REGRESSION']='PASS' if good else 'FAIL';gates['G7 SECURITY']=security['status']
    write_json(out/'gates.json',gates)
    result={'status':'PASS_LAW_VALIDATION_BOUNDED' if good else 'STOP_WITH_RCA','gates':gates,
        'stable_laws_predicting_unexecuted_continuations':1,'successful_unexecuted_transfer_probes':2,'refuted_candidate_laws':1,
        'partial_guard_sources_refused':1,'insufficient_or_opaque_source_families':1,'actual_atomic_typed_receipts':len(receipts),
        'receipt_outcomes':[{'source':r['source'],'step':r['step'],'purpose':r['purpose'],'outcome':r['receipt']['outcome']} for r in receipts],
        'pytest_passed':int(match.group(1)),'historical86_passed':historical['passed'],'native_queries':total,'P0_costs':os_costs,
        'scientific_scope':'finite synthetic source laws and observed applicability only','proof_status':'unverified','LLM_P1':False,'production_deployed':False,
        'INCONCLUSIVE':['Universal law outside tested domain','physical interpretation','autonomous concept discovery','statistical superiority to random attention','per-primitive CPU attribution'],
        'retained_prior_failures':['20261027T144841775698Z nested schema limit','20261027T145326078417Z consumed stale fixture'],
        'engine_authority':['source-bound induction/forecast/attention','proposal/precommit only'],
        'operator_authority':['explicit scoped activation','atomic receipt/journal commit','QA closure'],
        'oracle_authority':['post-measurement independent evaluation only; no grants or truth verification']}
    write_json(out/'result.json',result)
    (out/'source-audit.md').write_text('''# Source audit014\n\n| Component | Retained capability |014 boundary |\n|---|---|---|\n|006.2|Finite discrimination and exact attention loss|Singleton correctly gives NO_INFORMATIVE_TEST|\n|011.1|Bound precommit/audit/activation/event/artifact/atomic receipt|Legacy min2 alternatives/suffix2 unchanged; explicit014 singleton/suffix4 schema extension|\n|012|Finite residual dependency, FAIL_CEILING|Unchanged, no residual rebranding|\n|013|Exact empirical linear transport with guarded input span|Unchanged source-of-truth NO-GO; original frozen reproducer repeated successfully|\n|014|Finite validation-attention after a unique context|No third fundamental operation, no synthetic hypothesis, no universal-law claim|\n\nUser-named report(20261027-124214).md/RCA(20261027-124215).md/result(20261027-124215).json correspond to docs/qa/LM-OPERATIONAL-INVARIANT-013/20261027T110832991953Z.014 preserves those files and all7502 preexisting protected files.\n''')
    (out/'RCA.md').write_text('''# RCA014\n\nOriginal013 NO-GO remains correct: after a singleton every test partitions the current candidate set into one group, so T006 refuses another discrimination.014 introduces a different attention purpose, VALIDATE_TRANSFER: choose an unexecuted guarded source consequence of the existing empirical law. It does not invent another interpretation.\n\nB is the preregistered negative candidate. Its native action1 depends on source-history position modulo4; the learned coordinate omits this clock. Local transitions and the first discrimination agree, but the delayed0101 probe produces a different coordinate and scalar readout. The external receipt is FAILURE, independently replayed. The system marks REQUIRES_REVIEW and blocks new proposals. No safe complement of the failed path was derived, and no clock coordinate or universal guard repair is synthesized. Independent research remains active. This is an expected THEORETICAL_LAW_FAILURE, not a failed acceptance gate.\n\nTwo unexpected engineering failures remain immutable in prior cohorts. SOURCE_CONTRACT_BUG: extending suffix to4 initially missed the inherited Readout admissibility max2; the narrow014 nested readout/receipt extension repaired only that schema. TEST_FIXTURE_BUG: stale-order testing initially reused an already-consumed execution snapshot; a separate pre-execution activated snapshot tests actual stale-version refusal. Neither repair changed frozen source operations, oracle, probes, scoring,006/011/013 or mathematical criteria.\n\nStorage is separate: four raw SQL probes on a fresh private production snapshot initially permit UPDATE/DELETE with SQLite's default FK setting; every probe rolls back. Four explicit immutable triggers block them independently afterward, while INSERT and historical86 still pass. Production is unchanged. An actor able to rewrite schema or the database file can remove these guards; that threat is outside this contract.\n''')
    cpu=os_costs['CPU_ns_including_reaped_descendants']/1e9;wall=os_costs['wall_ns']/1e9
    (out/'report.md').write_text(f'''# LivingMath Law Validation014\n\n**{result['status']}**. Все G0–G7: {', '.join(gates.values())}. Эксперимент новый; NO-GO013 сохранён и воспроизведён без изменения его I/T.\n\n## Что построено и проверено\n\nОтдельный конечный selector attention различает DISCRIMINATE и VALIDATE_TRANSFER. T006 по-прежнему отказывается различать singleton. При единственном текущем источниковом контексте014 выбирает ещё не исполненный допустимый probe существующего закона. Прогноз фиксируется до внешнего исполнения; истиной или новым различением он не объявляется.013 LinearTransport не менялся.\n\nОдин закон A успешно предсказал два новых четырёхшаговых продолжения. Кандидат B прошёл первую локальную проверку, затем опровергнут отложенным probe0101; дальнейший ход требует review. Стек C отказывает за зарегистрированным guard длины2. Источник D демонстрирует одинаковую координату с разными преемниками; отдельная opaque-инспекция не даёт данных для закона. Никакое недостающее различение не добавлено автоматически.\n\n## Реальные typed receipts\n\n| Source | Step | Purpose | Result |\n|---|---:|---|---|\n|A|1|DISCRIMINATE|FAILURE выбранного контекстного кандидата; posterior singleton|\n|A|2|VALIDATE_TRANSFER|SUCCESS|\n|A|3|VALIDATE_TRANSFER|SUCCESS|\n|B|1|DISCRIMINATE|SUCCESS|\n|B|2|VALIDATE_TRANSFER|FAILURE закона, REQUIRES_REVIEW|\n\nВсего5 atomic receipts. После A домен probes исчерпан: NO_UNTESTED_GUARDED_PROBE. После B новый precommit отклонён. Независимая ветвь сохранена. В новых QA-проектах нет активных разрешений. Все результаты unverified. SUCCESS не означает математическое доказательство; FAILURE интерпретации не равен опровержению самого закона.\n\nСтарый011 требует≥2 alternatives и suffix≤2. Новый явно версионированный014 envelope допускает одну настоящую prediction и suffix≤4, связывает purpose/law/context/coordinate. Остальные проверки011 source hash, project, ordered suffix, observer, move/audit/activation/event order, artifact, executor и transactional journal сохранены. Старые схемы011 остаются строгими. Model tools доступны только для preview/precommit/validate; активация и commit выполняются отдельным оператором, измерение — отдельным pinned executor.\n\n## Стоимость и контроли\n\nФактических native API queries: **{total}** = discovery/validation {discovery_total} + engine {len(engine)} + инструменты {instrument_total}. Учтены E/O/A, inspect/load и guard, включая вложенные вызовы. Engine не выполняет native E при прогнозах. Сводка по примитивам и этапам в native-costs.json. Oracle выполняет только последующую независимую проверку; random-control — отдельная counterfactual оценка с тем же доменом/бюджетом, без дополнительных receipts. В этом малом наборе превосходство над random не заявлено.\n\nOS wait4 полного P0 с дочерними процессами: CPU **{cpu:.4f}s**, wall **{wall:.4f}s**, peak RSS **{os_costs['peak_RSS_KiB']}KiB**; зарегистрированные лимиты соблюдены. CPU по каждому примитиву отдельно не измерялся; общие затраты включают подготовку, нормализацию и проверку. Регрессии измерены отдельно: pytest {match.group(2)}s, historical86 {historical['wall_ns']/1e9:.4f}s. Wall-speedup не заявлен; LLM/P1 не запускался.\n\n## Сохранность и безопасность\n\n**607 pytest PASS; historical86/86 PASS** на копии с четырьмя SQL-триггерами. Raw SQL изменяемость legacy events/operations независимо воспроизведена с rollback, исправлена только на копии. production-review.patch подготовлен отдельно и не устанавливался. Все исходные строки, audit-chain и7502 прежних файлов сохранены. Рабочие canonical/deployed базы, inode/байты, публичные24 tool schemas и версия0.4.2/schema5 неизменны.\n\nLandlock ABI9 реально запрещает engine чтение oracle и sealed-файла; доступ остаётся к публичному runtime и частному workspace с измерениями. Learner/selector не получают hidden targets, ответы или oracle. Строгие проверки чужого проекта, подмены purpose/law/context/порядка/observer/hash/activation/version, stale grant до чтения seal, backfill, пустого journal, caller grant и повторного request key пройдены. Это не защита от владельца SQLite-файла/схемы.\n\n## Воспроизведение и пределы\n\n`./reproduce.sh /tmp/lm014-new-output` создаёт свежую частную QA-базу, повторяет замороженные источники и реальные MCP/instrument/receipt проверки под Landlock. Нужен Linux с Landlock и совместимый MCP SDK; LM014_PYTHON задаёт Python явно. Рабочая SQLite и credentials в пакет не входят. Historical86 требует приватный исходный snapshot и отдельно не пересоздаётся из пустой базы.\n\nИсследование после singleton корректно остаётся нативным, когда открыто обязательство проверить перенос и остался неисполненный guarded probe. Конечные подтверждения не устанавливают универсальность. До полного научного engine остаются построение новых исходных различений при отказе, независимое обоснование расширяемых guards, открытые домены задач и внешние измерения. Здесь математически построен конечный механизм внимания, экспериментально проверены синтетические native следствия; физическая интерпретация и autonomous discovery не проверялись.\n''')
    runtime=out/'runtime';runtime.mkdir()
    for path in SOURCE.iterdir():
        if path.is_file() and (path.suffix in {'.py','.json'} or path.name.startswith('requirements')):shutil.copy2(path,runtime/path.name)
    write_json(out/'runtime-hashes.json',{p.name:sha(p) for p in runtime.iterdir()})
    newfiles=sorted(SOURCE.glob('law_validation014*.py'))+[SOURCE/'test_law_validation014.py',ROOT/'docs/superpowers/plans/2026-10-27-law-validation-014.md']
    diff=''.join(''.join(difflib.unified_diff([],p.read_text().splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+str(p.relative_to(ROOT)))) for p in newfiles)
    (out/'source.diff').write_text(diff)
    sql=(base/'production-review.sql').read_text();(out/'production-review.sql').write_text(sql)
    review=''.join(difflib.unified_diff([],sql.splitlines(keepends=True),fromfile='/dev/null',tofile='b/live_math_mcp_prod/migrations/014_append_only.sql'))
    (out/'production-review.patch').write_text(review)
    with tempfile.TemporaryDirectory(prefix='lm014-review-') as temporary:
        check=subprocess.run(['git','apply','--check',str(out/'production-review.patch')],cwd=temporary,capture_output=True,text=True)
        write_json(out/'patch-review.json',{'exit_code':check.returncode,'stderr':check.stderr,'deployed':False})
    legacy=(SOURCE/'typed_cycle011.py').read_text();extended=(SOURCE/'law_validation014_receipt.py').read_text()
    (out/'receipt-protocol.diff').write_text(''.join(difflib.unified_diff(legacy[legacy.index('    def validate_in('):].splitlines(keepends=True),extended[extended.index('    def validate_in('):].splitlines(keepends=True),fromfile='011 validate_in',tofile='014 validate_in')))
    write_json(out/'changed-files.json',[str(p.relative_to(ROOT)) for p in newfiles])
    script='''#!/bin/sh
set -eu
LM014_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LM014_ROOT=$(CDPATH= cd -- "$LM014_DIR/../../../.." && pwd)
if [ -z "${LM014_PYTHON:-}" ]; then
    if [ -x "$LM014_ROOT/.venv/bin/python" ]; then LM014_PYTHON="$LM014_ROOT/.venv/bin/python"; else LM014_PYTHON=python3; fi
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$LM014_PYTHON" "$LM014_DIR/runtime/law_validation014_reproduce.py" --package "$LM014_DIR" --output "${1:?Supply a new output directory}"
'''
    (out/'reproduce.sh').write_text(script);(out/'reproduce.sh').chmod(0o755)
    if not good:raise SystemExit('FINAL_GATE_FAIL: report retained; not ready')
    write_json(out/'sha256-manifest.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'sha256-manifest.json'})
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for p in sorted(out.rglob('*')):
            if p.is_file():zipped.write(p,arcname=str(Path(out.name)/p.relative_to(out)))
    archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
    print(canonical({'status':result['status'],'report':str(out/'report.md'),'native_queries':total,'receipts':len(receipts),'ZIP':str(archive)}))


if __name__=='__main__':main()
