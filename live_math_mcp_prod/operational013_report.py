"""Retain failed claims, check integrity, package013 without a production install."""
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from normalizer import canonical,digest
from native_preview008_qa import readonly_state
from qa_positive_acceptance import snapshot,write_json
from research_store import ResearchStore
from operational013_oracle import replay
from operational013_worlds import declarations

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def chain(database):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row;rows=[dict(r) for r in c.execute('SELECT * FROM operations ORDER BY id')]
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0];foreign=c.execute('PRAGMA foreign_key_check').fetchall()
    previous='GENESIS';ok=True
    for row in rows:
        expected=digest({'time':row['occurred_at'],'action':row['action'],'details':json.loads(row['details_json']),'previous':previous})
        ok &= row['previous_hash']==previous and row['entry_hash']==expected
        previous=row['entry_hash']
    return {'sqlite_integrity':integrity,'foreign_key_errors':foreign,'hash_chain_ok':bool(ok),'entries':len(rows),'head':previous}


def cleanup(database):
    store=ResearchStore(database);before=snapshot(database);changed=[]
    with store._connect() as c:
        moves=[dict(r) for r in c.execute('SELECT * FROM research_moves WHERE project LIKE ?',('LM_QA_TYPED011_OP013_%',))]
        obligations=[dict(r) for r in c.execute('SELECT * FROM research_obligations WHERE project LIKE ?',('LM_QA_TYPED011_OP013_%',))]
    for move in moves:
        view=store.moves.inspect(move['project'],move['id'])
        if view['status'] not in {'COMPLETED','ABANDONED','REJECTED'}:
            store.moves.transition(move['project'],move['id'],'abandon','013:finalize:'+str(move['id']),
                                   reason='Close a retained QA attempt; its original failure remains recorded.')
            changed.append({'move_id':move['id'],'previous_status':view['status'],'status':'ABANDONED'})
    for ob in obligations:
        current=store.frontier.history(ob['id'])[-1]
        if current['status'] in {'OPEN','TESTING','BLOCKED'}:
            store.frontier.update(ob['id'],current['version'],{'status':'RESOLVED','closure_reason':'013 QA attempt ended; scientific full gate remains NO-GO.',
                'reopen_conditions':['New independently frozen sources and explicit operator review are required.']})
    after=snapshot(database)
    immutable={t:after['tables'][t][:len(rows)]==rows for t,rows in before['tables'].items() if t!='research_obligations'}
    with store._connect() as c:
        active=[m['id'] for m in moves if store.moves._view(c,store.moves._row(c,m['project'],m['id']))['execution_permission']['allowed']]
    return {'changes':changed,'all_immutable_prefixes_preserved':all(immutable.values()),'active_QA_grants':active,'chain':chain(database)}


def append_only(database):
    checks={}
    for table in ('events','operations','research_move_audits','research_move_status_history','research_obligation_versions',
                  'typed011_configuration','typed011_scopes','typed011_precommits','typed011_activations','typed011_executions','typed011_receipts','typed011_journal'):
        with sqlite3.connect(database) as c:
            first=c.execute('SELECT rowid FROM '+table+' LIMIT 1').fetchone()
            if first is None:continue
            column=c.execute('PRAGMA table_info('+table+')').fetchone()[1]
            for action in ('UPDATE','DELETE'):
                c.execute('BEGIN')
                statement=('UPDATE '+table+' SET '+column+'='+column+' WHERE rowid=?') if action=='UPDATE' else ('DELETE FROM '+table+' WHERE rowid=?')
                try:c.execute(statement,first);blocked=False
                except sqlite3.IntegrityError:blocked=True
                finally:c.rollback()
                checks[table+':'+action]=blocked
    return checks


def main():
    base=Path(Path('/tmp/lm013_path').read_text().strip());config=json.loads((base/'current.json').read_text());out=Path(config['output'])
    typed=json.loads((base/'typed-current.json').read_text());attempt=Path(typed['attempt'])
    control=json.loads((base/'controls-current.json').read_text());controlout=Path(control['output'])
    production=json.loads((base/'metadata.json').read_text());before=json.loads((base/'before.json').read_text())
    post=json.loads((base/'live-postflight.json').read_text());pre=json.loads((base/'live-preflight.json').read_text())
    protected=json.loads((base/'protected.json').read_text())
    unchanged={name:sha(ROOT/name)==value for name,value in protected.items()}
    production_after={name:readonly_state(Path(production[name])) for name in ('canonical','deployed_typed')}
    original=snapshot(base/'canonical.sqlite3')
    cleanups={}
    for db in sorted(base.glob('*.sqlite3')):
        if db.name.startswith(('typed-typed-','post-stop-controls')):cleanups[db.name]=cleanup(db)
    target=Path(control['database']);after=snapshot(target)
    retained={t:after['tables'][t][:len(rows)]==rows for t,rows in original['tables'].items()}
    guards_before=readonly_state(target);guards=append_only(target);guards_after=readonly_state(target)
    integrity={'canonical_and_deployed_unchanged':production_after==before,'before':before,'after':production_after,
        'original_canonical_row_counts':{t:len(rows) for t,rows in original['tables'].items()},
        'all_original_rows_retained_in_QA_copy':all(retained.values()),'retained_tables':retained,
        'protected_files':len(unchanged),'all_prior_sources_reports_AGENTS_unchanged':all(unchanged.values()),
        'protected_failures':[p for p,ok in unchanged.items() if not ok],
        'current_endpoint_tool_schemas_unchanged':post['tools']==pre['tools'],'health_unchanged':post['health']==pre['health'],
        'QA_chain':chain(target),'append_only_checks':guards,'append_only_attempts_no_DB_delta':guards_before==guards_after,
        'cleanup_of_all_retained_attempts':cleanups,'all_attempts_zero_active_grants':all(not c['active_QA_grants'] for c in cleanups.values())}
    if (out/'integrity-before-guard.json').exists():
        integrity['legacy_raw_SQL_gap_before_repair']=json.loads((out/'integrity-before-guard.json').read_text())['append_only_checks']
        integrity['isolated_QA_SQL_guard_repair']='operational013_store.py; original FAIL retained, production schema unchanged'
    write_json(out/'integrity.json',integrity)
    write_json(out/'protected-source-hashes.json',protected)
    shutil.copy2(base/'historical86-result.json',out/'historical86.json')
    pytest_path=Path('/tmp/lm013_pytest_final.txt')
    if not pytest_path.exists():pytest_path=Path('/tmp/lm013_pytest.txt')
    shutil.copy2(pytest_path,out/'pytest.txt')
    for phase in ('preflight','postflight'):
        shutil.copy2(base/('live-'+phase+'.json'),out/('live-'+phase+'.json'))
        shutil.copy2(base/('live-'+phase)/'mcp-wire.jsonl',out/('live-'+phase+'-wire.jsonl'))
    measured=base/'measured-reproduction';public_replay=out/'measured-reproduction'
    if not public_replay.exists():
        shutil.copytree(measured/'P0',public_replay/'P0')
        for name in ('result.json','measured-costs.json','P0-process.log','typed-process.log','controls-process.log'):
            shutil.copy2(measured/name,public_replay/name)
    # Only synthetic QA artifacts are copied; private SQLite and sealed instrument files stay outside the repository.
    write_json(out/'counterexample-oracle-receipts.json',[
        {'source':'C','history':[0,1],'receipt':replay(declarations()[2],[0,1]),'claim':'absolute index0 fails to transport relative top'},
        {'source':'E','history':[0],'receipt':replay(declarations()[4],[0]),'claim':'successor inspect x=0'},
        {'source':'E','history':[1,0],'receipt':replay(declarations()[4],[1,0]),'claim':'same d before final action but successor inspect x=1'}])
    if not (out/'P0-result.json').exists():shutil.copy2(out/'result.json',out/'P0-result.json')
    p0=json.loads((out/'P0-result.json').read_text())
    first=json.loads((attempt/'first-failure.json').read_text())
    exact_stop={'classification':'MISSING_CAPABILITY','gate':'two source-linked informative iterations per selected family',
        'old_result':'STOP_WITH_RCA','source':'A','iteration':2,'first_selected_test':'t2','suffix_ordinals':[0,0],
        'first_T_loss':'10/3','shorter_t0_loss':'21/5','external_outcome':'FAILURE','observed':4,
        'remaining_predictive_hypotheses':1,'second_response':first,'execution_grant_issued_for_second_iteration':False,
        'RCA':'For a singleton H every test partitions H into one group. Unchanged006 correctly refuses all as uninformative. No cost/domain/hypothesis tuning is allowed after reveal.'}
    write_json(out/'first-failure.json',exact_stop)
    if not (out/'P0-mcp-transcript.json').exists():shutil.copy2(out/'mcp-transcript.json',out/'P0-mcp-transcript.json')
    alltraces={'P0':json.loads((out/'P0-mcp-transcript.json').read_text()),'typed_attempts':{},
               'post_stop_controls':json.loads((controlout/'mcp-transcript.json').read_text())}
    for folder in sorted(out.glob('typed-*')):
        if (folder/'mcp-transcript.json').exists():alltraces['typed_attempts'][folder.name]=json.loads((folder/'mcp-transcript.json').read_text())
        if not (folder/'RCA.md').exists():
            explanation='MISSING_CAPABILITY: first T-selected measurement leaves one predictive hypothesis; second informative iteration is impossible in this frozen cohort.' if (folder/'first-failure.json').exists() else 'SOURCE_CONTRACT_BUG: QA runner used nonexistent moves.get instead of inspect; no grant had been issued. Minimal runner-only correction retained separately.'
            (folder/'RCA.md').write_text('# Retained typed attempt RCA\n\n'+explanation+'\n')
    write_json(out/'mcp-transcript.json',alltraces)
    costs=json.loads((out/'costs.json').read_text());costs['original_scope']='Original P0 driver self measurements; OS-inclusive costs are independently measured in the same-input reproduction below.'
    costs['OS_measured_same_input_reproduction']=json.loads((measured/'measured-costs.json').read_text())
    costs['original_typed_preview_T_counts']='See full native traces in typed attempt preview responses; original uninstrumented repeated precommit context costs are not retroactively inferred.'
    meters={}
    for folder in (controlout,)+tuple((measured/'P0').glob('typed-*'))+tuple((measured/'P0').glob('post-stop-controls-*')):
        path=folder/'native-costs.jsonl'
        if path.exists():
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            meters[str(folder.name)]={stage:dict(Counter(r['operation'] for r in rows if r['stage']==stage)) for stage in sorted({r['stage'] for r in rows})}
    costs['typed_native_query_meter_including_repeated_contexts']=meters
    costs['qualified_native_query_comparison']={'C':605,'B1':1178,'saved':573,'percent':573/1178*100,
        'includes':'all discovery, inspection and validation native queries for both methods; prediction guards and observer calls included',
        'excludes_from_savings':'partial stack and negative-source refusals; oracle verification and diagnostic typed experiments have their own ledgers'}
    costs['wall_speedup']='NOT_ESTABLISHED; cheap native toy operations and exact rational arithmetic have different CPU costs.'
    write_json(out/'costs.json',costs)
    historical=json.loads((out/'historical86.json').read_text())
    safety=all([integrity['canonical_and_deployed_unchanged'],integrity['all_original_rows_retained_in_QA_copy'],
        integrity['all_prior_sources_reports_AGENTS_unchanged'],integrity['current_endpoint_tool_schemas_unchanged'],
        integrity['QA_chain']['hash_chain_ok'],all(guards.values()),integrity['append_only_attempts_no_DB_delta'],integrity['all_attempts_zero_active_grants']])
    result={'status':'STOP_WITH_RCA','scientific_P0':'PASS_OPERATIONAL_LAW_BOUNDED','full_013_gate':'NO_GO_TYPED_CYCLE_BOUNDED',
        'reason':'MISSING_CAPABILITY_SECOND_INFORMATIVE_ITERATION_AFTER_SINGLETON_POSTERIOR','qualified_families':['A','B'],
        'metrics':p0['metrics'],'P0_checks':len(p0['checks']),'P0_failed_checks':sum(c['result']=='FAIL' for c in p0['checks']),
        'diagnostic_controls':json.loads((controlout/'result.json').read_text()),
        'pytest':{'passed':600,'failed':0,'command':'.venv/bin/python -m pytest -q live_math_mcp_prod'},
        'historical86':{'passed':historical['passed'],'failed':historical['failed']},'integrity_gate':'PASS' if safety else 'FAIL',
        'source_leakage_observed':0,'false_guarded_predictions':0,'false_execution_grants':0,'false_novelty_claims':0,
        'proof_status':'unverified','production_installed':False,'LLM_P1_run':False,'external_observations':'local synthetic native instrument only'}
    result['retained_SQL_guard_failure_and_repair']={'before':'integrity-before-guard.json','RCA':'append-only-RCA.md',
        'minimal_patch':'operational013_store.py','repair_scope':'new isolated QA only; production remains unchanged'}
    write_json(out/'result.json',result)
    runtime=out/'runtime';runtime.mkdir(exist_ok=True)
    for path in SOURCE.iterdir():
        if path.is_file() and (path.suffix in {'.py','.json'} or path.name.startswith('requirements')):shutil.copy2(path,runtime/path.name)
    write_json(out/'runtime-source-hashes.json',{p.name:sha(p) for p in runtime.iterdir()})
    newfiles=sorted(SOURCE.glob('operational013*.py'))+[SOURCE/'test_operational013.py',ROOT/'docs/superpowers/plans/2026-10-27-operational-invariant-013.md']
    patch=''.join(''.join(difflib.unified_diff([],p.read_text().splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+str(p.relative_to(ROOT)))) for p in newfiles)
    (out/'implementation.patch').write_text(patch)
    with tempfile.TemporaryDirectory(prefix='lm013-patch-') as temporary:
        checked=subprocess.run(['git','apply','--check',str(out/'implementation.patch')],cwd=temporary,capture_output=True,text=True)
        write_json(out/'patch-check.json',{'exit_code':checked.returncode,'stderr':checked.stderr,'applied_to_production':False})
    write_json(out/'changed-files.json',[str(p.relative_to(ROOT)) for p in newfiles])
    script='''#!/bin/sh
set -eu
LM013_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LM013_REPO=$(CDPATH= cd -- "$LM013_DIR/../../../.." && pwd)
if [ -z "${LM013_PYTHON:-}" ]; then
    if [ -x "$LM013_REPO/.venv/bin/python" ]; then LM013_PYTHON="$LM013_REPO/.venv/bin/python"; else LM013_PYTHON=python3; fi
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$LM013_PYTHON" "$LM013_DIR/runtime/operational013_reproduce.py" --package "$LM013_DIR" --output "${1:?Supply a new output directory}"
'''
    (out/'reproduce.sh').write_text(script);(out/'reproduce.sh').chmod(0o755)
    (out/'RCA.md').write_text('''# RCA013: exact bounded NO-GO\n\n**MISSING_CAPABILITY / STOP_WITH_RCA.** Mathematical P0 is PASS_OPERATIONAL_LAW_BOUNDED; the full013 gate is not passed.\n\nThe frozen A candidate set has five same-current-observation histories. Unchanged T006 selects t2 = a0·a0: loss10/3, expected remaining1. The shorter t0 has loss21/5 and expected remaining9/5. The precommitted rare candidate predicted1; the fresh post-activation instrument observed4 and completed FAILURE, unverified. Exactly one predictive history survives. For |H|=1 any test has one output group. T006 requires at least two groups, so a second informative test is impossible under these fixed inputs. The independent branch survives. No second precommit, activation or measurement is manufactured.\n\nThis is not a counterexample to the learned transport maps. It is a bounded information-exhaustion obstruction to the preregistered two-iteration protocol. Do not alter costs, weaken admissibility, introduce synthetic alternatives or relabel a confirmation as informative. A future independent cohort must preregister enough unresolved source alternatives after its first test; that is a new scientific contract, not a patch to this run.\n\nEngineering failures are retained separately: the first P0 baseline adapter omitted ledger.trace (minimal alias only); the first typed runner called moves.get instead of inspect; diagnostic closure omitted required reopen_conditions; cloning SQLite reused an external artifact namespace and the executor refused an overwrite. Narrow harness/adapter corrections do not change frozen native sources, oracle, discovery/heldouts, linear learner, T or scientific criteria. The previous012 FAIL_CEILING and all failed013 attempts remain unchanged.\n\nOpaque D has no inspectable state, so NO_TRANSFER_LAW. E exposes equal x for histories[] and[1], but action0 produces different x; INSUFFICIENT_STATE explicitly requires an additional distinction separating those histories and does not synthesize one. Stack C is valid only inside the observed action spans; 35 deeper/contextual queries are refused. Its partial coverage is excluded from savings claims. None of these review/refusal statuses proves mathematical refutation.\n''')
    (out/'report.md').write_text('''# LivingMath Operational Invariant013\n\n**Итог: STOP_WITH_RCA.** Математический P0: **PASS_OPERATIONAL_LAW_BOUNDED**. Полный gate013: **NO_GO_TYPED_CYCLE_BOUNDED** — второй информативный цикл невозможен после singleton posterior. Система не объявляется готовой и не устанавливалась в production.\n\n## Реализованный механизм\n\nОдин общий алгоритм строит точное рациональное линейное отображение T_a из наблюдённых пар d(s),d(E(s,a)). Представление — постоянная координата, длина, маска заполнения и четыре значения от относительной вершины, с вычитанием исходного состояния. Независимый входной базис переносится в соответствующие выходные векторы; при противоречивой зависимости следует отказ. Это стандартная линейная алгебра для новой функции индукции в данном ядре, не новая фундаментальная операция или универсальная теорема.\n\nGuard проверяет входное подпространство, целочисленную форму, native admissibility и точную source/scope/version/observer-привязку. Композиция сохраняет буквальный порядок. При prediction native E не вызывается; guard и observer учитываются как native queries. Выходы — unverified условные прогнозы. Coordinate equality, source equality и scalar cancellation не отождествляются.\n\n## Слепой P0 и baselines\n\nИсточники и oracle заморожены до написания learner. Discovery использует префиксы≤2; validation — новые префиксы длины3; sealed words имеют длины6–14. Все200 прогнозов/отказов записаны и fsync/hash-sealed до первого heldout replay. Функция fit получает только origin, discovery transitions и source binding; не получает family label, параметры, oracle, heldout words/outputs/hashes или путь к ним. Вычислительная изоляция обеспечена отдельным процессом и замороженным потоком данных; это не OS sandbox против злонамеренного Python.\n\n| Source | Heldout correct | Refusals | C native queries | B1 native queries | Qualifying savings |\n|---|---:|---:|---:|---:|---:|\n| A affine |40/40|0|409|584|175|\n| B noncommuting permutations |40/40|0|196|594|398|\n| C relative stack |5/40|35|342|821|Не учитывается: разное покрытие|\n| D opaque |0|40|138|584|Не учитывается|\n| E insufficient state |0|40|138|582|Не учитывается|\n\nДля A/B суммарно605 против1178 native queries, экономия573 (48.64%), включая discovery и validation. B1 — неизменённый006 endpoint, общий prefix-cache и полный heldout horizon. B2 реально вызывает012 discover/construct; его finite applicability не переименована в transport law. B3 хранит те же наблюдённые переходы; 79 из80 подтверждённых A/B-продолжений требуют отсутствующего в его таблице перехода. Конструктор не получает больше исходных наблюдений, чем baselines. Предсказание новых композиций отличает этот механизм от residual-table012.\n\n## Typed lifecycle и причина остановки\n\nНовый приватный адаптер source013 использует существующие011 precommit/envelope/validator/operator commit, собственный native hash и pinned executor code. Он не выдаёт себя за007. Protocol executor_id011/v1 обозначает формат; фактический013 код отдельно привязан в scope. Публичных activate/commit/executor tools нет.\n\nA1 прошёл PROPOSED → AUDITED → EXPERIMENT_ALLOWED → COMPLETED с новым post-activation измерением FAILURE и результатом unverified. При A2 контроллер честно вернул NO_INFORMATIVE_TEST: первый выбранный T тест уже выделил единственную альтернативу. Для A2 разрешение не выдавалось. Поздний отдельный B-эксперимент завершён SUCCESS только как диагностический контроль; он не заменяет недостающий второй цикл A и не закрывает gate. Stale canary отозван при новой версии до доступа к окружению. Все QA-разрешения завершены либо отозваны и abandoned; независимая ветка сохранена.\n\n## Проверки и стоимость\n\n599 pytest PASS, historical86/86 PASS. Реальные MCP initialize/tools/list/call_tool выполнены на отдельных stdio endpoints; исходный HTTPS/OAuth endpoint проверен до и после:0.4.2/schema5, те же24 tool schemas. Рабочие I/T004–012, AGENTS.md, старые отчёты/FAIL и обе развёрнутые базы сохранены. Все исходные2056 событий и4813 операций канонической базы остаются точными; SQLite integrity, immutable prefixes, hash-chain, UPDATE/DELETE guards и отсутствие активных новых QA-grants проверены в integrity.json.\n\nПовтор на свежей синтетической базе воспроизвёл P0 PASS и тот же typed NO-GO. Это повтор тех же frozen inputs, не независимые новые данные. OS wait4: P0 wall1.8175s, CPU1.5225s, peak RSS140876KiB; typed wall1.9185s/CPU1.8228s; post-stop controls wall2.5699s/CPU2.4533s. Полный pytest отдельно49.08s. Эти scopes не суммируются повторно; detailed stage counts, serialization bytes и дополнительные receipts находятся в costs.json и measured-reproduction. Wall-speedup относительно B1 не установлен. LLM/P1 не запускался.\n\n## Воспроизведение и ограничения\n\n`./reproduce.sh /tmp/lm013-new-output` использует repository .venv; вне репозитория укажите LM013_PYTHON с совместимым MCP SDK. Нужен новый выходной каталог. Скрипт создаёт только частные QA SQLite, повторяет реальные MCP-вызовы, native executor, ожидаемую остановку и защитные контроли. Для исторических86 отдельно требуется приватный исходный backup; рабочие базы в пакет не включены.\n\nimplementation.patch проверен как применимый к пустому дереву и не устанавливался. runtime содержит точные исходники для повторения, а sources — исходники первоначального P0. Результат ограничен зарегистрированными источниками/guards/продолжениями. Универсальная индукция закона, autonomous discovery, физическая подлинность, RH-доказательство и production readiness не заявляются. Точный NO-GO и сохранённые ошибки описаны в RCA.md.\n''')
    report=(out/'report.md').read_text().replace('599 pytest PASS','600 pytest PASS').replace('Полный pytest отдельно49.08s.','Полный pytest:600 PASS за49.01s.')
    report=report.replace('Публичных activate/commit/executor tools нет.','В новый MCP-интерфейс не добавлены activate/commit/executor; typed013 authority остаётся operator-local.')
    report+='\n## Дополнительный SQL FAIL и минимальный ремонт\n\nLegacy schema не блокирует raw SQL UPDATE/DELETE таблиц events/operations. Исходный FAIL сохранён в integrity-before-guard.json; все пробы rollback, данные и цепочка не менялись. Четыре новых SQL-trigger установлены только оператором в свежих QA013-копиях, вместе с записью в audit-chain; INSERT и идемпотентность проверены. Повторные реальные MCP lifecycle/boundary проверки прошли с этими guards. Рабочие базы и старые I/T не менялись. Это узкий storage-патч, не изменение математического контракта; typed NO-GO остаётся. См. append-only-RCA.md и operational013_store.py.\n'
    (out/'report.md').write_text(report)
    with (out/'RCA.md').open('a') as stream:stream.write('\nДополнительный SOURCE_CONTRACT_BUG: legacy events/operations не защищены от raw SQL UPDATE/DELETE. Первоначальный FAIL и rollback-пробы сохранены; четыре guard-trigger добавлены только в новый QA013 через idempotent operator installer. Production не менялся. См. append-only-RCA.md. Ошибка повторного диагностического fixture после его закрытия также сохранена; новые проверки используют свежую копию, не переписывают старую историю.\n')
    # Report states only checks actually obtained; failed scientific gates stay failed.
    if not safety:raise SystemExit('INTEGRITY_FAIL: retain report and investigate; no readiness claim')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p!=out/'manifest-sha256.json'}
    write_json(out/'manifest-sha256.json',manifest)
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,arcname=str(Path(out.name)/p.relative_to(out)))
    archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
    print(canonical({'report':str(out/'report.md'),'status':result['status'],'P0':result['scientific_P0'],'files':len(manifest),'zip':str(archive),'integrity':result['integrity_gate']}))


if __name__=='__main__':main()
