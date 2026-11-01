"""Export synthetic QA receipts, never the private research database or credentials."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import zipfile

from attention_fixture import SEEDS
from attention_qa import configure, intact
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def copy_receipts(source, target):
    """Allowlist excludes database files, whole-DB manifests and auth/environment."""
    target.mkdir(parents=True, exist_ok=True)
    for name in ('calls.json', 'mcp-wire.jsonl', 'checks.json', 'tools-list.json', 'result.json',
                 'metrics.json', 'fixtures.json', 'expected_relations.json', 'operator-import.json',
                 'operator-dispositions.json', 'finite-outcome.json', 'final-moves.json',
                 'initial-snapshot.json', 'before-snapshot.json', 'after-snapshot.json',
                 'M1-main-guarded.json', 'M1-no-history-guarded.json', 'M1-text-guarded.json',
                 'M2-after-guarded.json', 'integrity.json', 'measurements.json'):
        if (source / name).is_file():
            shutil.copyfile(source / name, target / name)
    for model in (source / 'models').glob('*'):
        dest = target / 'models' / model.name
        dest.mkdir(parents=True, exist_ok=True)
        for name in ('prompt.txt', 'schema.json', 'output.json', 'events.jsonl', 'metadata.json', 'stderr.txt'):
            if (model / name).is_file():
                shutil.copyfile(model / name, dest / name)


def export(private, report):
    private, report = Path(private), Path(report)
    report.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent.parent
    metadata = read(private / 'metadata.json')
    previous = Path(metadata['previous_attempt']) if metadata.get('previous_attempt') else None
    initial = previous or private
    baseline = read(private / 'regression-v042/result.json', {})
    pytest_output = (private / 'pytest.txt').read_text() if (private / 'pytest.txt').exists() else ''
    local_match = re.search(r'(\d+) passed', pytest_output)
    local_passed = int(local_match.group(1)) if local_match else 0
    results = {str(seed): read(private / ('seed-' + str(seed)) / 'result.json', {}) for seed in SEEDS}
    for seed in SEEDS:
        copy_receipts(private / ('seed-' + str(seed)), report / ('seed-' + str(seed)))
    copy_receipts(private / 'regression-v042', report / 'regression-v042')
    if previous:
        for name in ('seed-17011', 'seed-27013', 'regression-v042'):
            copy_receipts(previous / name, report / 'initial-attempt' / name)
        oracle = previous / 'oracle-v1-source'
        if oracle.exists():
            shutil.copytree(oracle, report / 'initial-attempt/oracle-v1-source', dirs_exist_ok=True)
    if (private / 'pytest.txt').exists():
        shutil.copyfile(private / 'pytest.txt', report / 'pytest.txt')

    fixtures = {str(seed): read(private / ('seed-' + str(seed)) / 'fixtures.json', {}) for seed in SEEDS}
    relations = {str(seed): read(private / ('seed-' + str(seed)) / 'expected_relations.json', {}) for seed in SEEDS}
    write_json(report / 'fixtures.json', fixtures)
    write_json(report / 'expected_relations.json', relations)
    write_json(report / 'seeds.json', {'fixed_seeds': list(SEEDS), 'per_seed': {
        seed: {'event_order': f.get('definition', {}).get('event_order'),
               'obligation_order': f.get('definition', {}).get('obligation_order'),
               'event_ids': f.get('event_ids'), 'obligation_ids': f.get('obligation_ids')}
        for seed, f in fixtures.items()}})
    calls, wire, sessions = [], [], []
    attempts = [('accepted-repeat', private)] + ([('initial-attempt', previous)] if previous else [])
    for attempt, base in attempts:
        for label in ('regression-v042', 'seed-17011', 'seed-27013'):
            source = base / label
            session = attempt + '/' + label
            local = read(source / 'calls.json', [])
            calls.extend({'session': session, **call} for call in local)
            if (source / 'mcp-wire.jsonl').exists():
                wire.extend({'session': session, **json.loads(line)} for line in
                            (source / 'mcp-wire.jsonl').read_text().splitlines() if line.strip())
            sessions.append({'session': session, 'tool_calls': len(local)})
    write_json(report / 'calls.json', calls)
    write_json(report / 'mcp-transcript.json', {'headers_omitted': True,
               'jsonrpc_ids_are_local_to_session': True, 'messages': wire})
    tools = read(private / 'seed-17011/tools-list.json', {})
    write_json(report / 'tools-list.json', tools)

    per_at = {}
    for number in range(1, 19):
        name = 'AT' + str(number).zfill(2)
        if name == 'AT15':
            continue
        observations = []
        for seed, result in results.items():
            observations.extend({'seed': seed, **check} for check in result.get('checks', [])
                                if check['invariant'] == name or check['invariant'].startswith(name + '-'))
        ok = all(result.get('completed') for result in results.values()) and all(
            any(c['invariant'] == name for c in r.get('checks', [])) for r in results.values())
        per_at[name] = {'result': 'PASS' if ok and all(c['result'] == 'PASS' for c in observations) else 'FAIL',
                        'observations': observations}
    signatures = [r.get('modes', {}).get('M0', {}).get('fixture_guard_signature') for r in results.values()]
    semantic = [r.get('modes', {}).get('M2', {}).get('semantic_before_after', {}).get('after', {}) for r in results.values()]
    semantic_keys = ('considers_new_outcome', 'unsafe_selected', 'independent_observation_retained', 'consistent')
    profiles = [{k: s.get(k) for k in semantic_keys} for s in semantic]
    order_ok = (len(signatures) == 2 and bool(signatures[0]) and signatures[0] == signatures[1]
                and profiles[0] == profiles[1] and all(s.get('consistent') for s in semantic))
    per_at['AT15'] = {'result': 'PASS' if order_ok else 'FAIL', 'guard_signatures': signatures,
        'feedback_semantic_profiles': profiles,
        'scope': 'Same branch eligibility/identity/version decisions and post-outcome safety relations; no claim of identical LLM ranking or wording.'}

    config = configure()
    db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    before, after = read(initial / 'before.json'), snapshot(db)
    preserved = intact(before, after)
    repeated = intact(read(private / 'before.json'), after)
    store = ResearchStore(db)
    with store._connect() as connection:
        sqlite_ok = connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys = [list(row) for row in connection.execute('PRAGMA foreign_key_check')]
        schema_version = connection.execute('PRAGMA user_version').fetchone()[0]
        qa_moves = [(row['id'], row['project']) for row in connection.execute(
            "SELECT id,project FROM research_moves WHERE project LIKE 'LM_QA_%'")]
    states = [store.moves.inspect(project, move_id) for move_id, project in qa_moves]
    active = [{'project': state['project'], 'move_id': state['id']} for state in states
              if state['execution_permission']['allowed']]
    integrity = {'original_rows_unchanged_by_table': preserved,
        'repeat_start_rows_unchanged_by_table': repeated,
        'repeat_start_events': len(read(private / 'before.json')['tables']['events']),
        'repeat_start_operations': len(read(private / 'before.json')['tables']['operations']),
        'original_events': len(before['tables']['events']), 'current_events': len(after['tables']['events']),
        'original_operations': len(before['tables']['operations']), 'current_operations': len(after['tables']['operations']),
        'original_hash_prefix_unchanged': preserved.get('operations'),
        'original_last_hash': before['tables']['operations'][-1]['entry_hash'],
        'current_last_hash': after['tables']['operations'][-1]['entry_hash'],
        'database_inode_unchanged': before['inode'] == after['inode'],
        'sqlite_integrity_check': sqlite_ok, 'foreign_key_check': foreign_keys,
        'audit': store.verify_audit(), 'qa_moves_checked': len(states), 'active_qa_grants': active,
        'qa_verified_event_count': sum(row['status'] == 'verified' and row['project'].startswith('LM_QA_')
                                       for row in after['tables']['events']),
        'backup_sha256': hashlib.sha256((initial / 'research-before.sqlite3').read_bytes()).hexdigest(),
        'repeat_backup_sha256': hashlib.sha256((private / 'research-before.sqlite3').read_bytes()).hexdigest(),
        'private_backup_path': str(initial / 'research-before.sqlite3'),
        'backups_exported': False}
    integrity['result'] = 'PASS' if (all(preserved.values()) and all(repeated.values())
        and integrity['database_inode_unchanged'] and sqlite_ok == 'ok' and not foreign_keys
        and integrity['audit']['ok'] and not active and not integrity['qa_verified_event_count']) else 'FAIL'
    write_json(report / 'integrity.json', integrity)
    if integrity['result'] != 'PASS':
        per_at['AT18']['result'] = 'FAIL'
    write_json(report / 'migration.json', {'applied': False, 'schema_version_before': 5,
        'schema_version_after': schema_version, 'server_version': '0.4.2', 'server_restarted': False,
        'new_database_created': False, 'historical_records_rewritten': False})
    if local_passed < 106 or re.search(r'\d+ failed', pytest_output):
        per_at['AT17']['result'] = 'FAIL'

    receipt_metrics = {seed: result.get('metrics', {}) for seed, result in results.items()}
    models = []
    for attempt, base in attempts:
        for directory in base.glob('seed-*/models/*'):
            path = directory / 'metadata.json'
            receipt = read(path, {'receipt_incomplete': True, 'exit_code': None,
                'limitation': 'Initial timeout occurred before the old runner wrote metadata; raw events/stderr retained.'})
            models.append({'attempt': attempt, 'path': str(directory.relative_to(base)), **receipt})
    metrics = {'seeds': receipt_metrics, 'sessions': sessions, 'mcp_tool_calls_all_attempts': len(calls),
        'external_model_receipts': models, 'original_numeric_limits_waived_by_user': True,
        'external_model_invocations_all_attempts': len(models),
        'protocol_iterations_per_seed': 1, 'seeds_executed': list(SEEDS),
        'cpu_accounting': 'Final per-seed client + MCP server + all local children measured. Remote inference CPU is not observable. Initial attempt local CPU accounting was incomplete.',
        'no_cost_or_mathematical_novelty_claim': True,
        'structural_novelty_limitation': 'Different structured formulations are not independent mathematical mechanisms; no mathematical novelty established.'}
    metrics['per_mode'] = {
        'M0': {'server_generated_candidates': 0, 'generation': 'CAPABILITY_NOT_IMPLEMENTED',
               'selection': 'CAPABILITY_NOT_IMPLEMENTED'},
        'M1': {'external_candidates': sum(len(r.get('modes', {}).get('M1', {}).get(condition, []))
               for r in results.values() for condition in ('main', 'no_history', 'identical_text'))},
        'M2': {'external_candidates': sum(len(r.get('modes', {}).get('M2', {}).get('after_candidates', []))
               for r in results.values()), 'operator_seeded_experiments': sum(r.get('completed', False) for r in results.values())},
    }
    write_json(report / 'metrics.json', metrics)
    passed = (all(r.get('result') == 'PASS' for r in results.values())
        and all(v['result'] == 'PASS' for v in per_at.values())
        and baseline.get('result') == 'PASS' and baseline.get('pass_count') == 86
        and integrity['result'] == 'PASS')
    result = {'result': 'PASS' if passed else 'FAIL', 'at_checks': dict(sorted(per_at.items())),
        'server_version': '0.4.2', 'schema_version': schema_version, 'tools': len(tools.get('tools', [])),
        'existing_live_regression': {'result': baseline.get('result'), 'passed': baseline.get('pass_count'), 'required': 86},
        'local_tests': {'passed': local_passed, 'original_required': 101, 'qa_tests_added': 5},
        'seed_results': {seed: {'project': r.get('project'), 'result': r.get('result'),
                              'events': r.get('events'), 'obligations': r.get('obligations')} for seed, r in results.items()},
        'modes': {'M0': {'result': 'CAPABILITY_NOT_IMPLEMENTED', 'memory_and_guards_result': 'PASS' if passed else 'FAIL',
                          'generation': 'CAPABILITY_NOT_IMPLEMENTED', 'selection': 'CAPABILITY_NOT_IMPLEMENTED',
                          'server_generated_candidates': 0},
                  'M1': {'result': 'PASS' if all(len(r.get('modes', {}).get('M1', {}).get(c, [])) == 3
                           for r in results.values() for c in ('main', 'no_history', 'identical_text')) else 'FAIL',
                         'formulator': 'external_llm_generated', 'conditions': ['MCP snapshot', 'no history', 'same snapshot as text'],
                         'identical_text_is_not_live_tool_access': True},
                  'M2': {'result': 'PASS' if all(per_at[k]['result'] == 'PASS' for k in ('AT05', 'AT08', 'AT14', 'AT15')) else 'FAIL',
                         'attention_formulator': 'external_llm_generated', 'executed_move_origin': 'operator_seeded',
                         'experimental_outcome': 'FAILURE', 'selection_is_not_execution': True}},
        'native_autonomous_attention_implemented': False, 'autonomous_discovery_claimed': False,
        'scope': 'Finite controlled-feedback workflow; external proposals + MCP guards. Not an autonomous selection/execution loop.',
        'prior_attempt_failures_preserved': bool(previous), 'integrity_result': integrity['result']}

    changed = []
    patches = []
    with zipfile.ZipFile(initial / 'source-before.zip') as archive:
        names = set(archive.namelist())
        for path in sorted((root / 'live_math_mcp_prod').glob('*.py')):
            relative = str(path.relative_to(root))
            old = archive.read(relative).decode() if relative in names else ''
            new = path.read_text()
            if old != new:
                changed.append({'path': relative, 'role': 'QA-only', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                patches.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                    fromfile='a/' + relative if old else '/dev/null', tofile='b/' + relative))
        agents_preserved = ('AGENTS.md' not in names or archive.read('AGENTS.md') == (root / 'AGENTS.md').read_bytes())
        product_unchanged = all(archive.read(name) == (root / name).read_bytes() for name in names
            if name.startswith('live_math_mcp_prod/') and (root / name).is_file()
            and not Path(name).name.startswith(('attention_', 'test_attention')))
    write_json(report / 'changed-files.json', {'files': changed, 'product_source_unchanged': product_unchanged,
        'AGENTS_md_unchanged': agents_preserved, 'documentation': ['docs/superpowers/plans/2026-10-26-attention-001.md', str(report)]})
    (report / 'changes.patch').write_text(''.join(patches))
    result['product_source_unchanged'] = product_unchanged
    if not product_unchanged or not agents_preserved:
        result['result'] = 'FAIL'
    write_json(report / 'result.json', result)
    endpoint = config['LIVE_MATH_PUBLIC_URL'].rstrip('/') + '/mcp'
    total_current = sum(m.get('mcp_tool_calls', 0) for m in receipt_metrics.values())
    table = '\n'.join('| ' + key + ' | ' + value['result'] + ' |' for key, value in sorted(per_at.items()))
    modes = []
    for seed, r in results.items():
        m1 = r.get('modes', {}).get('M1', {})
        for condition in ('main', 'no_history', 'identical_text'):
            decisions = [entry['decision'] for entry in m1.get(condition, [])]
            modes.append(f'| {seed} | {condition} | ' + ', '.join(decisions) + ' |')
    comparisons = '\n'.join(modes)
    shifts = []
    lifecycles = []
    for seed in results:
        chosen = []
        for phase in ('M1-main', 'M2-after'):
            output = read(private / ('seed-' + seed) / 'models' / phase / 'output.json', {})
            selected = output.get('attention', {}).get('selected_candidate_id')
            candidate = next((c for c in output.get('candidates', []) if c['candidate_id'] == selected), {})
            chosen.append(candidate.get('mechanism', 'NO_SAFE_NEXT_MOVE'))
        shifts.append('| ' + seed + ' | ' + ' | '.join(chosen) + ' | ' + str(results[seed].get('events', {}).get('feedback')) + ' |')
        for state in read(private / ('seed-' + seed) / 'final-moves.json', []):
            history = ' → '.join(entry['status'] for entry in state['history'])
            lifecycles.append(f"| {seed} | {state['id']} | {state['status']} | {history} | {state['execution_permission']['allowed']} |")
    shift_table = '\n'.join(shifts)
    lifecycle_table = '\n'.join(lifecycles)
    post_decisions = {seed: [entry['decision'] for entry in r.get('modes', {}).get('M2', {}).get('after_candidates', [])]
                      for seed, r in results.items()}
    post_decision_text = '; '.join(seed + ': ' + ', '.join(decisions) for seed, decisions in post_decisions.items())
    (report / 'README.md').write_text(f'''# LM-ATTENTION-001

Finite integration acceptance on LivingMath v0.4.2/schema 5, 18 tools. Endpoint: {endpoint}.
Result: **{result['result']}** for the controlled external-model workflow. Native generation/ranking: **CAPABILITY_NOT_IMPLEMENTED**.

Read [report.md](report.md), [result.json](result.json), [RCA.md](RCA.md) and [integrity.json](integrity.json).
Two shuffled seeds, one controlled negative feedback step each. Numeric limits were explicitly waived by the user.
Synthetic QA projects only. History is retained; no model verification, product migration or new mathematical operation.

`calls.json` contains full tool request/response receipts; `mcp-transcript.json` includes initialize and tools/list, with session-local IDs.
`seed-*/models/*` contains exact prompts, structured outputs, CLI events and model metadata.
No OAuth credentials, private database or original research manifests are exported.

Reproduce with `./reproduce.sh`. This creates a fresh private Backup API snapshot and new QA projects,
uses the local owner OAuth configuration and existing ChatGPT-authenticated Codex CLI, and retains all new history.
Inference is nondeterministic; seeds fix fixture order, not model weights/sampling. The endpoint must still be live.
''')
    (report / 'report.md').write_text(f'''# LM-ATTENTION-001 — отчёт

**Итог: {result['result']}** для ограниченного контура с внешней моделью. Проверки AT01–AT18 приведены ниже.
Сервер v0.4.2, SQLite schema 5, 18 MCP-инструментов; реальный HTTPS/OAuth endpoint: {endpoint}.
Продуктовый код, математическая онтология, исходные RH/Soft-FTL данные и AGENTS.md сохранены.

## Кто выполнял работу

M0: сервер возвращал память/фронтир и проверял переданные предложения. Порождение и выбор кандидата отсутствуют: CAPABILITY_NOT_IMPLEMENTED, 0 server-generated candidates.
Тестовые A–H и выполненный G были operator_seeded; это входы проверки, а не найденные MCP идеи.
M1/M2: предложения и выбор внимания формулировал внешний gpt-6.1-sol через ChatGPT-authenticated Codex CLI без API key, инструментов, приложений, документов проекта и пользовательского AGENTS в дочернем namespace.
Точный immutable build модели сервисом не раскрывается. Все prompts, outputs, CLI version, reasoning=low и usage сохранены.

## Сравнение режимов

| Seed | Условие | Решения MCP для трёх предложений |
|---|---|---|
{comparisons}

Без истории модель не имела действительных project-local оснований/обязательств. Одинаковая история в текстовом ablation несла те же сведения, что MCP snapshot; различие ответов модели не доказывает преимущество MCP в творчестве.
Наблюдаемая функция MCP — адресная память, независимый аудит, scope/version и жизненный цикл разрешения.

## Отрицательная обратная связь

В каждом seed операторский G прошёл record → audit → explicit activate → complete(FAILURE).
Единственное вычисление на seed: длины четырёх слов [2,2,3,4]; слово w3 даёт конечный контрпример p_even.
До/после модель получала одну задачу. Новый event учтён, зависимая предпосылка не используется для активного хода, независимое наблюдение сохранено.
Изменение предлагаемого внимания — ответ внешней модели на обновлённую память. Выполненный эксперимент задан QA, поэтому автономный цикл выбора/исполнения не заявляется.
Ни COMPLETED, ни EXPERIMENT_ALLOWED не означает verified. Полные состояния и append-only трассы в seed-каталогах.

| Seed | Выбор до | Выбор после | Новый event |
|---|---|---|---|
{shift_table}

Это смена предложения, не автоматическая выдача grant. Новая диагностическая формулировка повторно проверяется;
scoped disposition для операторского F не переносится автоматически на иной fingerprint модели.
Решения для M2: {post_decision_text}. Аудит предложений не выдавал разрешение на исполнение.
Независимый операторский A при этом остаётся EXPERIMENT_ALLOWED: это адресный review, а не глобальный запрет.
В text-ablation scope/representation отличались от зарегистрированного контракта; диагностике также требовался собственный scoped review.

| Seed | Move ID | Итоговый статус | Append-only статусы | Grant в конце |
|---|---|---|---|---|
{lifecycle_table}

## Проверки

| ID | Результат |
|---|---|
{table}

AT15 сравнивает решения о допустимости всех fixture-ветвей и отношения безопасности/сохранения независимой ветви после нового исхода при перестановке ID.
Равенство ранжирования и текста LLM не заявляется. Семантический oracle использует depends_on/contradicts/scope; expected choice не передавался модели.
Прежняя реальная регрессия: {baseline.get('pass_count')}/86 PASS. Локальные тесты: см. pytest.txt (101 прежний + 5 QA-тестов).

## Измерения и сохранность

Текущий attention-прогон: {total_current} MCP tool calls; с регрессиями и сохранёнными неудачными попытками: {len(calls)}.
Внешние модельные предложения, CPU клиента/сервера/локальных дочерних процессов и wall time перечислены в metrics.json; удалённый inference CPU неизвестен.
Лимиты сняты пользователем; протокол завершён после двух seeds, по одному feedback, без лестницы новых обязательств.
Исходные {integrity['original_events']} событий и {integrity['original_operations']} операций, все старые строки и hash prefix сохранены.
SQLite={sqlite_ok}; hash-chain={integrity['audit']['ok']}; активных QA grants={len(active)}; QA verified={integrity['qa_verified_event_count']}.
Backup SHA256: `{integrity['backup_sha256']}`. Backup хранится приватно, база не заменялась.
Обновление/перезапуск MCP и переподключение ChatGPT для этих QA-изменений не требуются.

## Границы вывода

Подтверждается механика контролируемого переноса внимания с внешними предложениями. Самостоятельный ранжировщик/генератор MCP отсутствует.
Структурно отличающиеся формулировки не засчитываются как новые математические механизмы. Автономное открытие и математическая истинность не заявляются.
Ранние FAIL сохранены отдельно и разобраны в RCA.md; они не переписаны в PASS.
''')
    (report / 'RCA.md').write_text('''# RCA

## TEST_ORACLE_BUG — первоначальная проверка идемпотентности

Сохранено в initial-attempt/seed-*/checks.json: idempotency:call_17:no_new_operations FAIL.
Минимальный reproducer: записать refuted C ключом K1, затем структурно тот же C с другим названием и ключом K2.
Сервер возвращает тот же move_id/fingerprint, но добавляет append-only research_move_request_bound для нового K2.
Это допустимая привязка нового ключа, а не второй ход. Нулевой прирост операций требуется при повторении K1/K2, а не при первой привязке K2.
Исправлен только QA oracle: отдельный учёт виденных (project, request_key), тест на новую привязку и точный replay. Старые traces и oracle-v1-source сохранены.

## TRANSPORT_FAILURE — внешняя модель, первоначальный seed 27013

M1-no-history не завершился за 300 секунд: CLI events содержат thread.started/turn.started, но нет результата.
Точная причина на стороне сервиса не установлена. Это не ошибка MCP/математики и не доказательство неисправности Cloudflare.
Первоначальный seed помечен FAIL/неполным. Повтор выполнен в новых проектах с явным одинаковым reasoning=low,
тайм-аутом 600 секунд и завершением всей группы процессов при timeout. Результаты разных конфигураций не смешиваются.

## MISSING_CAPABILITY — native attention

tools/list подтверждает 18 текущих методов: память/перечисление/аудит/lifecycle, без API порождения или ранжирования.
M0 generation/selection = CAPABILITY_NOT_IMPLEMENTED. research_focus_candidates соблюдает прежний контракт;
добавлять скрытый selector, RH-эвристику или новые фундаментальные операции не требовалось.

## Границы oracle и модели

AT08 проверяет явные structured depends_on, references и сохранение независимого наблюдения; не доказывает корректность произвольного естественного текста.
AT15 сравнивает ограничения и семантическую безопасность, а не равенство творческих формулировок.
Контролируемое отрицательное вмешательство operator_seeded; автоматическое исполнение выбора модели не тестировалось.
Различия модели между MCP snapshot и идентичным текстом сами по себе не дают причинной оценки творческого эффекта LivingMath.
Immutable model build и удалённый inference CPU недоступны. Все известные ограничения сохранены, а не заполнены синтетикой.

Конечные статусы каждой проверки находятся в result.json; любой новый FAIL отменяет готовность соответствующего контура.
''')
    if not previous:
        rca = report / 'RCA.md'
        rca.write_text(rca.read_text() + '\nИсторические сбои выше относятся к разработке QA. В этом новом воспроизведении initial-attempt не запускался; '
            'исходные receipts сохранены в docs/qa/LM-ATTENTION-001-20261026T091249Z/initial-attempt/.\n')
    reproduce = report / 'reproduce.sh'
    reproduce.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'
        + 'ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"\n'
        + 'exec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/attention_suite.py" "$@"\n')
    reproduce.chmod(0o755)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.private_dir, args.report_dir), ensure_ascii=False))
