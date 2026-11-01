"""Export immutable010 Phase-A evidence. STOP is never relabeled as typed-cycle PASS."""
import json
from pathlib import Path
import re
import shutil
import sqlite3

from native_preview008_qa import readonly_state
from normalizer import digest
from qa_positive_acceptance import snapshot, write_json
from research_cycle009_report import integrity as canonical_integrity
from research_engine010_contract import BoundMeasurementReceipt, MeasurementBinding, VERSION
from research_engine010_qa import PRIOR009, SOURCE, sha


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def private_integrity(db):
    if not db.exists(): return {'result': 'INCONCLUSIVE', 'reason': 'Reproducer database not created'}
    state = snapshot(db); last = 'GENESIS'; broken = []
    for op in state['tables']['operations']:
        expected = digest({'time': op['occurred_at'], 'action': op['action'],
            'details': json.loads(op['details_json']), 'previous': last})
        if expected != op['entry_hash'] or op['previous_hash'] != last: broken.append(op['id'])
        last = op['entry_hash']
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        sql = conn.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = conn.execute('PRAGMA foreign_key_check').fetchall()
        active = conn.execute("SELECT count(*) FROM research_move_status_history h WHERE status='EXPERIMENT_ALLOWED' AND sequence=(SELECT max(sequence) FROM research_move_status_history s WHERE s.move_id=h.move_id)").fetchone()[0]
    return {'result': 'PASS' if sql == 'ok' and not foreign and not broken and not active else 'FAIL',
        'SQLite': sql, 'foreign_keys': foreign, 'chain_head': last, 'broken_hash_ids': broken,
        'active_grants': active, 'origin': 'exact scoped009 snapshot materialized into a new isolated database; not canonical chain'}


def export(base, failure):
    meta = load(base / 'metadata.json'); baseline = Path(meta['baseline']); out = Path(meta['report'])
    out.mkdir(parents=True, exist_ok=False)
    names = ('source-binding.json', 'first-failure.json', 'run-failure.json', 'checks.json', 'calls.jsonl',
        'source-hashes.json', 'reproducer-inputs.json', 'legacy-red-summary.json', 'pytest.txt', 'process-costs.json', 'environment.json')
    for name in names:
        if (base / name).exists(): shutil.copyfile(base / name, out / name)
    for folder in ('frozen-sources',):
        shutil.copytree(base / folder, out / folder)
    for folder in base.iterdir():
        if folder.is_dir() and (folder / 'schemas.json').exists(): shutil.copytree(folder, out / folder.name)
    if (baseline / 'development').exists(): shutil.copytree(baseline / 'development', out / 'development')
    (out / 'historical86').mkdir()
    for name in ('result.json', 'checks.json', 'calls.json', 'stdio-wire.jsonl', 'integrity.json', 'server-stderr.txt'):
        src = base / 'historical86' / name
        if src.exists(): shutil.copyfile(src, out / 'historical86' / name)
    public = load(baseline / 'public-preflight.json', {})
    write_json(out / 'public-preflight.json', public)
    intact = canonical_integrity(baseline)
    before = load(baseline / 'readonly-before.json')
    current = readonly_state(Path(load(baseline / 'metadata.json')['db']))
    intact['all_rows_schema_sequence_inode_bytes_chain_exact'] = current == before
    intact['canonical_readonly_before'] = before; intact['canonical_readonly_after'] = current
    intact['isolated_reproducer'] = private_integrity(base / 'isolated.sqlite3')
    if current != before or intact['isolated_reproducer']['result'] == 'FAIL': intact['result'] = 'FAIL'
    write_json(out / 'integrity.json', intact)
    frozen = {p: Path(p).is_file() and sha(Path(p)) == h for p, h in load(base / 'source-hashes.json', {}).items()}
    write_json(out / 'frozen-source-checks.json', frozen)
    calls = rows(base / 'calls.jsonl'); checks = load(base / 'checks.json', [])
    def check(name, ok, evidence=None):
        checks.append({'invariant': name, 'result': 'PASS' if ok else 'FAIL', 'evidence': evidence})
    check('canonical_and_private_integrity', intact['result'] == 'PASS')
    check('frozen_sources_unchanged_after_observations', all(frozen.values()))
    tools = public.get('tools', {}).get('tools', [])
    check('actual_public_preflight_20_readonly', len(tools) == 20 and
        public.get('health', {}).get('audit', {}).get('ok') is True and
        public.get('readonly_before') == public.get('readonly_after'))
    pytest_text = (base / 'pytest.txt').read_text() if (base / 'pytest.txt').exists() else ''
    matches = re.findall(r'(\d+) passed', pytest_text)
    pytest_passed = int(matches[-1]) if matches else 0
    check('full_pytest_superset_of506', pytest_passed >= 506 and not re.search(r'\d+ failed|ERRORS', pytest_text), pytest_passed)
    findings = load(base / 'source-binding.json', [])
    check('six009_events_examined_without_backfill', len(findings) == 6 and all(not f['binding_envelope_present'] for f in findings))
    check('readonly_MCP_errors_and_success_no_delta', all(c['readonly_unchanged'] for c in calls if
        c['tool'].startswith('research_cycle_') or c['tool'] == 'research_novelty_snapshot' or c['response'].get('isError')))
    blocked = [
        'source-backed typed six-step lifecycle and oracle equality',
        'typed positive FAILURE/SUCCESS/INCONCLUSIVE/ERROR commits',
        'typed measurement cross-binding rejection with authentic complete metadata',
        'typed receipt request-key atomic commit and changed-result rejection',
        'typed grant revision invalidation and fresh-audit recovery',
        'authoritative journal append/raw-replay/conflict review and version rebinding',
        'full read-only normalization→I→T next-step proposal',
        'new typed adverse diagnostic dispositions and independent branch evolution',
        'independent external artifact authenticity',
        'full010 cycle startup/CPU/allocation/RSS comparison to009',
        'Phase-C deployment patch and staging deployment dry-run',
    ]
    for name in blocked:
        checks.append({'invariant': name, 'result': 'INCONCLUSIVE',
            'reason': 'STOP gate: original009 events lack source-bound measurement metadata; do not fabricate it or claim a completed typed controller.'})
    write_json(out / 'checks.json', checks)
    wire = {str(p.relative_to(out)): rows(p) for p in out.glob('*/wire.jsonl')}
    write_json(out / 'mcp-transcript.json', {'transport': 'real MCP ClientSession over stdio on isolated databases',
        'calls': calls, 'wire': wire, 'production': 'initialize/list/health/contract via actual HTTPS/OAuth only; no research writes'})
    receipts = [{'world': f['world'], 'cycle_index': f['cycle_index'], 'move_id': f['move_id'],
        'measurement_event_id': f['measurement_event_id'], 'source_event_sha256': f['event_sha256'],
        'status': 'INSUFFICIENT_MEASUREMENT_BINDING', 'receipt': None, 'committed': False,
        'proof_status': 'unverified', 'execution_permission': {'allowed': False}} for f in findings]
    (out / 'measurement-receipts.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in receipts))
    novelty = {'status': 'NOVELTY_CONTEXT_INCOMPLETE', 'authoritative_journal_installed': False,
        'snapshot_complete': False, 'known_fingerprints': None, 'registered_fingerprints': [],
        'registered_count': 0, 'journal_writes': 0, 'warning': 'No journal exists; [] registered here is a count of writes, never authoritative empty novelty history.',
        'legacy009_registry': str(PRIOR009.relative_to(SOURCE.parent) / 'novelty-ledger.jsonl'),
        'legacy009_registry_sha256': sha(PRIOR009 / 'novelty-ledger.jsonl')}
    write_json(out / 'novelty-history.json', novelty)
    baseline009 = load(PRIOR009 / 'result.json')
    legacy_previews = []
    guards = []
    for call in calls:
        response = call.get('decoded_response') or {}
        if call['tool'] == 'research_native_preview':
            legacy_previews.append({'label': call['label'], 'MCP_roundtrip_wall_ns': call['MCP_roundtrip_wall_ns'],
                'response_costs': {k: response[k] for k in ('costs', 'cost_ledger', 'cold_wall_ns', 'child_cpu_ns', 'child_peak_rss_KiB', 'source_serialization', 'source_snapshot_wall_ns') if k in response}})
        if call['tool'].startswith('research_cycle_') or call['tool'] == 'research_novelty_snapshot':
            guards.append({'label': call['label'], 'MCP_roundtrip_wall_ns': call['MCP_roundtrip_wall_ns'],
                'source_lookup_wall_ns': response.get('source_lookup_wall_ns'), 'status': response.get('status'),
                'I_T_executed': False, 'math_worker_starts': 0})
    costs = {'measurement_scope': 'Phase-A refusal guards and legacy boundary reproduction only',
        'process': load(base / 'process-costs.json'), 'guards': guards, 'legacy008_preview_costs': legacy_previews,
        'source_serialization_timing': 'INCONCLUSIVE for010; no completed typed pipeline',
        'novelty_lookup': 'No authoritative journal lookup implementation; journal absent, never complete-empty.',
        'allocation': 'INCONCLUSIVE; OS peak RSS measured, heap allocation not separately instrumented',
        'full010_cycle': 'INCONCLUSIVE; blocked at measurement source contract',
        'speedup_claim': False, 'LLM_calls': 0,
        'baseline009': {'provenance': str(PRIOR009.relative_to(SOURCE.parent)),
            'result_json_sha256': sha(PRIOR009 / 'result.json'),
            'whole_QA_exit_usage': baseline009.get('whole_QA_exit_usage'),
            'note': '009 full harness and010 refusal costs perform different work and cannot establish acceleration.'}}
    write_json(out / 'costs.json', costs)
    write_json(out / 'source-contract-extension.schema.json', MeasurementBinding.model_json_schema())
    write_json(out / 'receipt.schema.json', BoundMeasurementReceipt.model_json_schema())
    count = {name: sum(c['result'] == name for c in checks) for name in ('PASS', 'FAIL', 'INCONCLUSIVE')}
    result = {'decision': 'STOP_WITH_RCA', 'engine_version': VERSION,
        'phase_A_guard_checks': 'PASS' if not failure and not count['FAIL'] else 'FAIL',
        'typed_cycle': 'INCONCLUSIVE', 'phase_B': 'BLOCKED_SOURCE_CONTRACT', 'phase_C': 'NOT_REACHED',
        'checks': count, 'pytest_passed': pytest_passed, 'historical86': load(base / 'historical86/result.json', {}).get('result', 'INCONCLUSIVE'),
        'typed_completed_moves': 0, 'typed_committed_receipts': 0, 'new_journal_entries': 0,
        'measurement_events_inspected': [f['measurement_event_id'] for f in findings],
        'MCP_calls': len(calls), 'LLM_calls': 0, 'proof_status': 'unverified',
        'production_version': public.get('health', {}).get('version'), 'production_tools': len(tools),
        'canonical_events': intact['events'], 'canonical_operations': intact['operations'],
        'production_deployed': False, 'production_writes': 0, 'production_restarted': False,
        'integrity': intact['result'], 'failure': failure, 'report': str(out / 'report.md')}
    write_json(out / 'result.json', result)
    table = '\n'.join('| {world} | {cycle_index} | {move_id} | {measurement_event_id} |'.format(**f) for f in findings)
    (out / 'report.md').write_text(f'''# LM-RESEARCH-ENGINE-010 — Phase A

**STOP_WITH_RCA.** Исторические измерения009 не содержат привязку, необходимую новому typed workflow. Phase-A проверки: {count['PASS']} PASS, {count['FAIL']} FAIL; {count['INCONCLUSIVE']} INCONCLUSIVE. Это не `PASS_TYPED_CYCLE` и не `PASS_ISOLATED_LIBRARY_ONLY`.

## Проверенный источник

Реальный HTTPS/OAuth MCP: версия {result['production_version']}, {len(tools)} tools, schema5, {intact['events']} событий, {intact['operations']} операций. BackupAPI-копия сделана до изменений. Полное сравнение строк, схемы, sequence, inode, байтов и цепочки: **{intact['result']}**. Production не изменялся, не перезапускался;010 не устанавливался.

| Мир009 | Шаг | Move ID | Measurement event ID |
| --- | --- | --- | --- |
{table}

У всех шести исходных событий нет `measurement_binding`. Внешний009 harness знает больше, чем записано в событии; его трасса не является источником отсутствующих фактов. Исторические `COMPLETED`, результаты и hash-chain не переписаны.

## Реализовано и проверено

Отдельный экспериментальный FastMCP010.1-phase-a публикует три read-only инструмента: `research_cycle_validate_receipt`, `research_novelty_snapshot`, `research_cycle_preview`. Это прототип входных проверок, не полный controller. Он отвергает подмену caller-контекстом, не создаёт журнал, receipt, ход, grant или измерение. Проверка неполного события возвращает `INSUFFICIENT_MEASUREMENT_BINDING`; отсутствие authoritative history — `NOVELTY_CONTEXT_INCOMPLETE`, а не NEW.

Три реальные MCP репродукции на изолированном снимке: generic complete принимает исходное premise-событие как project-local evidence; повтор preview с пустой caller-history снова NEW относительно этой истории; переименование сохраняет structural fingerprint. Это точные границы старых API, не доказательство эксплуатации. Полные request/response и DB before/after находятся в `mcp-transcript.json` и каталогах wire.

Полный pytest: **{pytest_passed} PASS**; историческая MCP регрессия: **{result['historical86']} (86)**. Новые проверки охватывают schema, отсутствие binding/backfill, source hash/project/version, C4/quota, повтор read-only вызова, отказ добавить verified и нулевые SQLite delta на успехе/ошибке. Старые тесты и модули004–009 сохранены. Оригинальная009 приёмка остаётся прежним результатом; новый typed3×2 replay не выполнен и отмечен INCONCLUSIVE.

## Граница результата

Серверному прототипу принадлежат только строгие входные модели, SELECT-only предварительные проверки и явные отказы. Полный semantic/test binding, commit idempotency, authoritative novelty journal, raw replay, typed revocation и normalization→I→T controller **не реализованы до source gate**. Оператору/executor по-прежнему принадлежат независимое измерение и подтверждение его происхождения. Проверка ссылок не подтверждает физическую подлинность или математическую истину. Всё unverified; активных разрешений изолированного репродуктора: {intact['isolated_reproducer'].get('active_grants', 'INCONCLUSIVE')}.

Полный010 цикл и ускорение: INCONCLUSIVE. `costs.json` содержит измеренные расходы QA/отказов и честный009 baseline; эти разные объёмы работы не сравниваются как speedup. LLM calls:0.

## Следующий необходимый шаг

Сначала внешний executor должен записывать согласованный versioned envelope в новое событие после явной активации; typed proposal должен предварительно фиксировать источник/test/suffix. См. `source-contract-extension.md`, JSON Schema и `RCA.md`. Затем можно реализовать operator-only commit/journal и провести Phase B. `deployment.patch` не подготовлен: Phase B не PASS; разрешения на deployment010 нет. План совместимости и отката — `rollback.md`.

## Воспроизведение

Из корня репозитория: `.venv/bin/python live_math_mcp_prod/research_engine010_qa.py`. Команда создаёт новую приватную BackupAPI-копию, читает public health/schema, запускает pytest, historical86 и изолированные MCP сценарии; production research writes отсутствуют. Для повторного использования существующего приватного снимка: `--baseline-dir /path/to/private/engine010-baseline`. Новый cohort создаётся при каждом запуске. `reproduce.sh` также запускает отдельные contract-тесты. Требуются проектное окружение `.venv` с совместимым MCP SDK и настроенный локальный OAuth для нового preflight.
''')
    (out / 'RCA.md').write_text('''# Source / Authority RCA

**STOP_WITH_RCA — MISSING_SOURCE_CONTRACT_METADATA.** ТЗ010 §7 прямо требует остановиться, если исходные0.4.2 events не содержат настоящей привязки измерения. Это ожидаемый source gate, не регрессия исторического009 PASS.

## Причина и минимальное исправление

JSON payloads шести measurement events содержат claim_type, fixture_sha256, measurement_origin, observation, outcome, proof_status, scope, statement, test_id, version. Нет move_id, audit_id, activation_operation_id, obligation_id, proposal_fingerprint, source_bindings, ordered suffix, executor_id. Предсказания, измеряемый native source и artifact hash также не записаны в bound envelope. Полные фактические события и SHA256 — `source-binding.json`.

`event:N` подтверждает существование project-local записи. Parent — source root, не immutable связь с move/audit/activation. Отдельный measurement JSONL009 с move_id не связан хешем с event; поздняя передача receipt не добавляет отсутствовавшие факты. Coarse timestamps не заменяют порядок ledger operations. Поэтому нельзя достроить «успешный» typed цикл из старых результатов.

Минимальное расширение — versioned JSON envelope во **вновь полученных** external measurement events, плюс явная source/test precommit в новом proposal. SQLite JSON уже способен хранить его; migration не нужна на Phase A. Существующие события не обновлять. Внешний исполнитель должен измерить заново после activation; его identity — декларация до независимого доверенного интерфейса. Schema/authority детали — `source-contract-extension.md`.

## Владелец каждой гарантии

| Слой | Что установлено | Чего нет |
| --- | --- | --- |
| Source events009 | immutable raw QA observation + finite fixture/version/test | bound move/audit/activation/executor envelope |
| I/T006–008 | bounded predictions, native raw witness replay, rational T в старых тестах | независимого измерения; глобальной новизны |
| Audit / activation | contract/adverse/version review и явный scoped grant | доказательства измеренного числа |
| Generic complete | result/reason/existing project-local evidence и grant checks | семантической классификации каждого evidence_ref как измерения |
| Novelty008 / harness009 | caller-local fingerprints / внешний append-only registry009.3 | общего server-authoritative typed journal |
| Новый010 Phase A | schema + fail-closed отсутствие привязки/history, SELECT-only | полной receipt acceptance, controller commit, novelty registration |
| Independent oracle | замороженный009 QA baseline | доступа в runtime010, научной истины |

## Красные границы

1. Legacy isolated complete с заранее существующим premise evidence получает COMPLETED/unverified. Сам по себе этот ответ не удостоверяет измерение. Новый validator не принимает его как bound measurement.
2. Legacy preview с отсутствующей/пустой caller-history повторяет NEW относительно локального контекста. Новый endpoint возвращает NOVELTY_CONTEXT_INCOMPLETE и не выполняет I/T.
3. Новые display labels дают тот же structural fingerprint. Исходные операции и oracle не менялись; записи labels добавлены только в staging. Это не новое математическое различие.

## Блокированные проверки

Нельзя заявить прохождение typed3×2 lifecycle, полного receipt cross-binding, changed-key commit, journal conflict, raw replay registration или typed revocation без совместимых исходных событий. Они INCONCLUSIVE, а не пропущенные PASS. Изолированные проверки generic lifecycle и исторические86 сохраняют отдельный смысл. Review не означает refutation; SUCCESS/COMPLETED не означает verified.

Исторические FAIL009 и все прежние отчёты сохранены без изменений. `first-failure.json` фиксирует первичный source gate. Любая неожиданная ошибка этого прогона сохраняется отдельно в `run-failure.json`; наличие такой ошибки не позволяет объявить готовность.
''')
    (out / 'source-contract-extension.md').write_text('''# Proposed source contract — review required

Это проект узкого расширения, **не установленный протокол**. `source-contract-extension.schema.json` описывает обязательный `measurement_binding` в новом event.content; `receipt.schema.json` — декларацию receipt. Schema validation сама по себе не означает принятие, измерение или grant.

## Порядок и источник авторитета

1. Typed proposal до аудита фиксирует cycle_binding: exact source IDs/canonical row hashes, native adapter/definition hash, obligation/version/scope, observer/question/test_id/ordered suffix, predictions, optional preview_digest. Fingerprint фиксируется сервером; caller не может подменить его.
2. После корректного аудита оператор явно активирует только эту область. Activation_operation_id берётся из append-only ledger и должен соответствовать текущему move/audit/grant.
3. Отдельный внешний executor выполняет ограниченное измерение и записывает НОВОЕ source событие с `measurement_binding` по JSON Schema. Outer project, outcome/observation/scope/version/test и envelope должны согласовываться; predictions отделены от observed. Порядок event_created должен быть после bound activation operation. Никакой backfill из будущего receipt.
4. Read-only validator обязан сопоставить envelope с precommit/audit/current grant/source hashes и проверить observer/test/suffix, source identity, outcome/summary/result. Ни receipt, ни schema не подтверждают физическую подлинность: доверенный executor/artefact inspection — отдельная ответственность. Artifact declaration помечена DECLARED_UNINSPECTED.
5. Только после отдельного review возможно operator-only atomic commit: terminal unverified receipt, no active permission, request-key+digest conflict rejection и append-only decision/history. Этот commit НЕ реализован в010 Phase A и не опубликован в production.

## Authoritative novelty

Будущий immutable scope-local journal должен связывать project/scope/source-family/native operation ordinals+definition hashes, observer, source identities, guards/version provenance и raw witness replay. Label rename/version rebinding не дают математической новизны. Разные raw результаты под одним fingerprint требуют REVIEW. Preview никогда не вставляет запись. До появления такого журнала единственный корректный ответ — NOVELTY_CONTEXT_INCOMPLETE, не пустой полный snapshot.

## Совместимость

| Интерфейс / состояние | Изменение010 Phase A |
| --- | --- |
| production20 tools / schema5 / generic completion | отсутствует |
|004 normalization,006/007 I/T,008preview | исходники и контракты сохранены |
|009 harness/registry и старые COMPLETED | сохраняются, не повышаются до typed receipts |
| measurement_binding | только проект нового source envelope; нет записи исторических полей |
| private010 MCP | три отдельные SELECT-only guard tools; не production API |
| новая таблица/commit policy/allowance | отсутствует; отдельный будущий review после source gate |
''')
    (out / 'rollback.md').write_text('''# Compatibility and rollback

010 не установлен в production; service units, endpoint,20 tools, schema5 и canonical DB не изменялись. Переключать ChatGPT или перезапускать службу не требуется. Откатывать production нечего.

Прототип запускается отдельным stdio процессом с `--db` на существующем изолированном снимке. Для прекращения достаточно завершить этот процесс; SQLite migrations и фонового writer нет. Новые010 файлы можно исключить из будущей сборки, сохранив отчёты и исходные трассы. Приватный BackupAPI snapshot сохранён вне git. Не восстанавливать старый snapshot поверх живой базы: это уничтожило бы более новые события.

`phase-a.patch` содержит только новые экспериментальные файлы и не является deployment.patch. Phase C возможна после совместимых source events и PASS isolated typed acceptance, отдельного API/schema diff и решения владельца. До этого никаких новых public grants, journal inserts или новых обязательных полей старого complete.
''')
    (out / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../.."
.venv/bin/python -m pytest -q live_math_mcp_prod/test_research_engine010.py
.venv/bin/python live_math_mcp_prod/research_engine010_qa.py "$@"
''')
    (out / 'reproduce.sh').chmod(0o755)
    sources = [p for p in (base / 'frozen-sources').glob('*.py') if '010' in p.name]
    patch = []
    for path in sorted(sources):
        lines = path.read_text().splitlines()
        patch.extend(['diff --git a/live_math_mcp_prod/' + path.name + ' b/live_math_mcp_prod/' + path.name,
            'new file mode 100644', '--- /dev/null', '+++ b/live_math_mcp_prod/' + path.name,
            '@@ -0,0 +1,' + str(len(lines)) + ' @@', *['+' + line for line in lines]])
    (out / 'phase-a.patch').write_text('\n'.join(patch) + '\n')
    write_json(out / 'changed-files.json', {'new_source_files': [str(Path('live_math_mcp_prod') / p.name) for p in sources],
        'existing_source_files_modified': [], 'new_plan': 'docs/superpowers/plans/2026-10-27-research-engine-010.md',
        'production_files_modified': [], 'source_contract_extension': 'proposal only; not emitted or backfilled'})
    prior = []
    for path in sorted(out.parent.glob('*/result.json')):
        if path.parent == out: continue
        previous = load(path)
        prior.append({'cohort': path.parent.name, 'result_sha256': sha(path),
            'decision': previous.get('decision'), 'checks': previous.get('checks'),
            'report': '../' + path.parent.name + '/report.md',
            'failure': previous.get('failure')})
    write_json(out / 'prior-cohorts.json', {'preserved_without_rewrite': prior,
        'environment_RCA': 'First full run used system Python with an incompatible MCP SDK (RequestBodyLimitMiddleware missing). Retained FAIL; rerun uses repository .venv, no server changes or dependency installs.',
        'cost_report_correction': 'SDK responses can be text-encoded JSON; this cohort decodes the captured response before exporting cost fields. Earlier cost reports and raw traces are preserved.'})
    # Exported sources and prior QA worlds contain no canonical SQLite or OAuth credentials.
    forbidden = [p for p in out.rglob('*') if p.suffix in ('.sqlite3', '.sqlite', '.db')]
    if forbidden: raise RuntimeError('Private database leaked into export')
    write_json(out / 'manifest-sha256.json', {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    return result
