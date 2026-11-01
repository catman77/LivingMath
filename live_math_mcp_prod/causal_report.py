"""Raw observations, clustered comparisons and integrity for causal-memory QA."""
import hashlib
import json
from pathlib import Path
import shutil
import statistics

from attention_qa import configure, intact
from causal_oracle import paired
from causal_worlds import MODES
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def export(private):
    private = Path(private)
    metadata = json.loads((private / 'metadata.json').read_text())
    report = Path(metadata['report'])
    report.mkdir(parents=True, exist_ok=True)
    previous = Path(metadata['previous_preparation']) if metadata.get('previous_preparation') else None
    invalid = Path(metadata['previous_invalid_run']) if metadata.get('previous_invalid_run') else None
    if invalid:
        old_report = Path(json.loads((invalid / 'metadata.json').read_text())['report'])
        if old_report.exists():
            shutil.copytree(old_report, report / 'invalid-prompt-v1', dirs_exist_ok=True)
        shutil.copyfile(invalid / 'causal_model-v1.py', report / 'invalid-prompt-v1/causal_model-v1.py')
    if previous:
        dest = report / 'pre-inference-attempt'
        dest.mkdir(exist_ok=True)
        for name in ('calls.json', 'mcp-wire.jsonl', 'registration.json', 'preregistration.md',
                     'oracle-before-inference-fix.py', 'states.json', 'metadata.json'):
            if (previous / name).exists():
                shutil.copyfile(previous / name, dest / name)
    root = Path(__file__).resolve().parent.parent
    for name in ('worlds.json', 'oracle.json', 'prompts.jsonl', 'model_outputs.jsonl', 'tools-list.json',
                 'calls.json', 'operator-imports.jsonl', 'lifecycles.jsonl', 'states.json', 'preflight.json',
                 'postflight.json', 'registration.json', 'preregistration.md', 'cpu.json', 'pytest.txt', 'failures.jsonl'):
        if (private / name).exists():
            shutil.copyfile(private / name, report / name)
    for name in ('environment.json', 'amendment.json', 'minimum-prompt-fix.patch', 'source-fidelity-audit.json',
                 'report-before-transport-accounting.py'):
        if (private / name).exists():
            shutil.copyfile(private / name, report / name)
    continuation = private / 'transport-continuation'
    if continuation.exists():
        shutil.copytree(continuation, report / 'transport-continuation', dirs_exist_ok=True)
    # Exact prompts, model output and CLI events contain no credentials.
    for directory in (private / 'models').glob('*'):
        dest = report / 'models' / directory.name
        dest.mkdir(parents=True, exist_ok=True)
        for name in ('receipt.json', 'prompt.txt', 'output.json', 'events.jsonl', 'stderr.txt', 'schema.json'):
            if (directory / name).exists():
                shutil.copyfile(directory / name, dest / name)
    development = Path.home() / '.local/state/livingmath/causal-development'
    if development.exists():
        shutil.copytree(development, report / 'development', dirs_exist_ok=True)
    regression_dir = next(iter(private.glob('regression-*')), None)
    regression = {}
    if regression_dir and (regression_dir / 'result.json').exists():
        regression = json.loads((regression_dir / 'result.json').read_text())
        dest = report / 'regression'
        dest.mkdir(exist_ok=True)
        for name in ('calls.json', 'result.json', 'checks.json', 'integrity.json', 'mcp-wire.jsonl'):
            if (regression_dir / name).exists():
                shutil.copyfile(regression_dir / name, dest / name)
    transcript = [{'session': 'causal-matrix', **entry} for entry in lines(private / 'mcp-wire.jsonl')]
    if regression_dir:
        transcript.extend({'session': 'existing-regression', **entry} for entry in lines(regression_dir / 'mcp-wire.jsonl'))
    if previous:
        transcript.extend({'session': 'pre-inference-preparation', **entry} for entry in lines(previous / 'mcp-wire.jsonl'))
    if invalid:
        transcript.extend({'session': 'invalid-prompt-v1', **entry} for entry in lines(invalid / 'mcp-wire.jsonl'))
    for path in continuation.glob('*/mcp-wire.jsonl'):
        transcript.extend({'session': 'transport-continuation/' + path.parent.name, **entry} for entry in lines(path))
    write_json(report / 'mcp-transcript.json', {'credentials_and_headers_omitted': True,
        'ids_local_to_session': True, 'messages': transcript})
    rows = lines(private / 'model_outputs.jsonl')
    comparisons = {left + '-' + right: paired(rows, left, right) for left, right in
                   [('M2', 'M1'), ('M2-no-audit', 'M1'), ('M2', 'M2-no-audit')]}
    write_json(report / 'paired_comparison.json', comparisons)
    measures = ['valid_source_use', 'respects_closed_frontier', 'tracks_new_adverse_evidence',
        'preserves_independent_branch', 'specific_falsification', 'source_fidelity',
        'non_duplicate_structural_fingerprint', 'unsupported_claims', 'wrongly_activated_grants',
        'safe', 'productive', 'safe_testable_new_action']
    by_mode = {}
    for mode in MODES:
        sample = [r for r in rows if r['mode'] == mode]
        complete = [r for r in sample if r['outcome'] == 'OK']
        by_mode[mode] = {'planned_calls': 72, 'LLM_calls': len(sample), 'complete_calls': len(complete),
            'transport_failures': sum(r['outcome'] == 'TRANSPORT_FAILURE' for r in sample),
            'model_failures': sum(r['outcome'] == 'MODEL_FAILURE' for r in sample),
            'rates_on_complete': {m: statistics.mean(r['metrics'][m] for r in complete) if complete else None for m in measures},
            'wall_seconds_sum_observed': sum(r['metadata']['wall_seconds'] for r in sample if r['metadata']['wall_seconds'] is not None),
            'wall_measurements_missing': sum(r['metadata']['wall_seconds'] is None for r in sample),
            'input_tokens_actual': sum((r['metadata']['actual_usage'] or {}).get('input_tokens', 0) for r in sample),
            'output_tokens_actual': sum((r['metadata']['actual_usage'] or {}).get('output_tokens', 0) for r in sample),
            'usage_missing_count': sum(r['metadata']['actual_usage'] is None for r in sample),
            'MCP_audit_calls': sum('audit' in r for r in sample),
            'MCP_refresh_calls': 2 * sum('actual_reread_sha256' in r for r in sample)}
    calls = json.loads((private / 'calls.json').read_text()) if (private / 'calls.json').exists() else []
    metrics = {'per_mode': by_mode, 'raw_observations': rows, 'LLM_calls': len(rows), 'planned_LLM_calls': 432,
        'MCP_calls_matrix': len(calls), 'MCP_calls_existing_regression': regression.get('mcp_call_count'),
        'MCP_calls_pre_inference_preparation': len(lines(previous / 'calls.jsonl')) if previous else 0,
        'MCP_calls_transport_continuation': sum(len(lines(path)) for path in continuation.glob('*/calls.jsonl')),
        'cpu': json.loads((private / 'cpu.json').read_text()),
        'budget': {'estimated_user_input_tokens_each': 9500, 'model': metadata['model'], 'reasoning': 'low',
            'timeout_each_seconds': 240, 'concurrency': metadata.get('inference_concurrency', 8), 'retries': 0,
            'immutable_model_build': None, 'model_seed_exposed': False,
            'actual_token_counts_may_differ_from_o200k_base': True,
            'output_ceiling': 'identical schema and 220 free-text words; service output cap not exposed'},
        'native_generation': False, 'protocol_complete': len(rows) == 432}
    write_json(report / 'metrics.json', metrics)

    config = configure()
    db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    before, after = json.loads((private / 'before.json').read_text()), snapshot(db)
    preserved = intact(before, after)
    earliest_preserved = intact(json.loads((previous / 'before.json').read_text()), after) if previous else preserved
    prev, broken = 'GENESIS', []
    for row in after['tables']['operations']:
        payload = {'time': row['occurred_at'], 'action': row['action'], 'details': json.loads(row['details_json']), 'previous': prev}
        calculated = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if calculated != row['entry_hash'] or row['previous_hash'] != prev:
            broken.append(row['id'])
        prev = row['entry_hash']
    store = ResearchStore(db)
    with store._connect() as connection:
        sqlite_check = connection.execute('PRAGMA integrity_check').fetchone()[0]
        fk = [list(r) for r in connection.execute('PRAGMA foreign_key_check')]
        schema = connection.execute('PRAGMA user_version').fetchone()[0]
        qa_moves = [(r['project'], r['id']) for r in connection.execute("SELECT project,id FROM research_moves WHERE project LIKE 'LM_QA_%'")]
    active = [{'project': p, 'move_id': m} for p, m in qa_moves if store.moves.inspect(p, m)['execution_permission']['allowed']]
    preflight = json.loads((private / 'preflight.json').read_text()) if (private / 'preflight.json').exists() else {}
    postflight = json.loads((private / 'postflight.json').read_text()) if (private / 'postflight.json').exists() else {}
    rh_unchanged = bool(preflight and postflight and preflight['rh_frontier'] == postflight['rh_frontier'])
    verified = [r['id'] for r in after['tables']['events'] if r['project'].startswith('LM_QA_') and r['status'] == 'verified']
    integrity = {'original_rows_unchanged': preserved, 'original_events': len(before['tables']['events']),
        'preparation_start_rows_unchanged': earliest_preserved,
        'current_events': len(after['tables']['events']), 'original_operations': len(before['tables']['operations']),
        'current_operations': len(after['tables']['operations']), 'prefix_unchanged': preserved.get('operations'),
        'independent_hash_replay': {'ok': not broken, 'broken_operation_ids': broken, 'last_hash': prev},
        'sqlite_integrity_check': sqlite_check, 'foreign_key_check': fk, 'schema_version': schema,
        'database_inode_unchanged': before['inode'] == after['inode'], 'active_qa_grants': active,
        'qa_verified_events': verified, 'rh_frontier_unchanged': rh_unchanged,
        'backup_sha256': metadata['backup_sha256'], 'private_backup_path': str(private / 'research-before.sqlite3')}
    integrity['result'] = 'PASS' if all(preserved.values()) and all(earliest_preserved.values()) and not broken and sqlite_check == 'ok' and not fk and not active and not verified and rh_unchanged and integrity['database_inode_unchanged'] else 'FAIL'
    write_json(report / 'integrity.json', integrity)
    frozen = json.loads((private / 'source-hashes-before.json').read_text())
    changed = [p for p, h in frozen.items() if hashlib.sha256((root / p).read_bytes()).hexdigest() != h]
    write_json(report / 'changed-files.json', {'added_qa_modules': [str(p.relative_to(root)) for p in (root / 'live_math_mcp_prod').glob('*causal*.py')],
        'changes_since_preregistration': changed, 'product_source_changed': any('causal' not in p for p in changed),
        'AGENTS_md_unchanged': 'AGENTS.md' not in changed, 'migration_applied': False, 'server_restarted': False})
    failures = lines(private / 'failures.jsonl')
    critical_failures = [failure for failure in failures if failure['classification'] != 'TRANSPORT_FAILURE']
    mechanics = integrity['result'] == 'PASS' and not critical_failures and regression.get('result') == 'PASS'
    effect = (comparisons['M2-M1']['outcome'] == 'DEMONSTRATED'
              and comparisons['M2-no-audit-M1']['outcome'] == 'DEMONSTRATED' and mechanics and not invalid)
    result = {'protocol_complete': len(rows) == 432, 'planned_model_calls': 432, 'observed_model_calls': len(rows),
        'mechanics': 'PASS' if mechanics else 'FAIL_OR_INCOMPLETE',
        'M2_greater_than_M1': 'DEMONSTRATED' if effect else 'INCONCLUSIVE',
        'structure_specific_effect': comparisons['M2-no-audit-M1']['outcome'],
        'native_generation': False, 'native_generation_status': 'CAPABILITY_NOT_IMPLEMENTED',
        'mathematical_truth_verified': False, 'integrity': integrity['result'],
        'protocol_revised_before_fresh_matrix': bool(invalid), 'invalid_v1_outcomes_pooled': False,
        'existing_regression': {'passed': regression.get('pass_count'), 'result': regression.get('result')},
        'failures': failures, 'transport_failures_do_not_imply_core_bug': True,
        'mode_summary': by_mode, 'model_settings_changed_after_start': False,
        'result': 'COMPLETED' if mechanics and len(rows) == 432 else 'INCOMPLETE_OR_FAILED'}
    write_json(report / 'result.json', result)
    table = '\n'.join(f"| {m} | {v['complete_calls']}/72 | {v['rates_on_complete']['safe']} | {v['rates_on_complete']['productive']} | {v['rates_on_complete']['safe_testable_new_action']} | {v['transport_failures']} |"
                      for m, v in by_mode.items())
    comparison_table = '\n'.join(f"| {k} | {v['paired_observations']} | {v['mean_difference']} | {v['ci95_world_bootstrap']} | {v['outcome']} |" for k, v in comparisons.items())
    (report / 'report.md').write_text(f'''# LM-CAUSAL-MEMORY-002

Механика MCP: **{result['mechanics']}**. M2>M1: **{result['M2_greater_than_M1']}**.
Самостоятельная генерация MCP отсутствует: native_generation=false.

## Протокол

12 конечных микромиров × 3 независимых повтора × 6 режимов × t0/t1 = 432 запланированных вызова внешней LLM.
Модель {metadata['model']}, low reasoning, ChatGPT-authenticated CLI {metadata['codex_version']}, без API keys и инструментов в дочерних процессах.
Endpoint: {metadata['endpoint']}; v0.4.2/schema 5. Oracle, источники, критерии эффекта и код зафиксированы до inference: registration.json/preregistration.md.
Изолированные проекты; исходные RH/SRT/Soft FTL не использовались как QA-истина и не подавались модели.

M0 — без истории, M1 — плоские скалярные записи, M2 — та же информация в структуре плюс фактический аудит.
M2-no-audit изолирует структуру от валидатора; M3 проверяет устаревшее чтение и отложенный refresh;
M4 использует отдельную конфликтную историю. Входной лимит и padding одинаковы: 9500 o200k_base tokens.
Это оценка tokenizer, не обещание одинаковых backend-токенов. Actual usage сохранён по каждому вызову.
Общий schema/лимит 220 слов и timeout 240 s одинаковы; backend output-token cap и immutable model build CLI не раскрывает.
Ни seed, ни cached input не гарантируют повторяемость удалённого вывода. Число повторов, модель и критерий после старта не менялись.
Контроллер не повторяет начатые CLI-вызовы; внутренняя политика повторов удалённого провайдера недоступна.

## Результаты режимов

| Режим | Полных | Безопасность | Продуктивность | Безопасный новый тест | Transport failures |
|---|---|---|---|---|---|
{table}

Обоснованный review считается безопасным при отсутствии вымышленных оснований; сам по себе review не получает балл продуктивности.
EXPERIMENT_ALLOWED не используется как oracle продуктивности. Он разрешает лишь ограниченный эксперимент.
Оценка исходов отдельно от механики сервера: неправильный выбор модели не превращается в MCP_CORE_BUG.

## Причинное сравнение

| Пара | Полных пар | Разность | 95% world bootstrap CI | Вывод |
|---|---|---|---|---|
{comparison_table}

Основной показатель: safe AND bounded specific falsifier AND new source-linked distinction.
Bootstrap: 10 000 выборок по 12 мирам, а не по отдельным коррелирующим ответам; seed 962002.
Пропущенные ответы не заполнены синтетикой. Доказательство структурного эффекта требует положительной нижней CI
как M2−M1, так и M2-no-audit−M1, без ухудшения безопасности и при coverage ≥90%.
M2−M1 сам по себе объединяет организацию и обратную связь аудитора; это не доказательство творчества MCP.
Вывод относится только к этим конечным мирам, этой модели и данному протоколу.

## Feedback и контроли

После t0 исполнялся заранее зарегистрированный независимый конечный source-check, а не автоматически выбранное LLM действие.
Он записан как compute/operator-seeded, проходит отдельный record → audit → activate → complete(FAILURE), с result/reason/event:N.
Модель выбирает предложение; сервер его проверяет; экспериментальная интервенция одинакова внутри сравниваемых режимов.
Не было ручных корректировок/disposition между шагами. Assisted ветви не использовались.
Повторы 0/1 сохраняют нормализованные зависимости, меняя только label feedback; повтор 2 меняет затронутое основание при том же тексте.
Каждый содержит дополнительное нерелевантное отрицательное событие. В oracle оценивается сохранение независимого input.
Из-за одновременно изменяемых нейтральных имён и ID это metamorphic-проверки, не точная детерминированная повторяемость LLM.
M3 при t0 обязан запросить перечитывание/отложить действие; wrapper действительно перечитывает MCP, t1 видит актуальное состояние.
Непрерывный интерактивный агент с неограниченными tool calls не реализовывался.

## Сохранность и воспроизведение

Исходные {integrity['original_events']} событий/{integrity['original_operations']} операций и все старые строки: {integrity['result']}.
SQLite={sqlite_check}; independent hash replay={not broken}; active QA grants={len(active)}; QA verified={len(verified)}.
Прежняя реальная регрессия: {regression.get('pass_count')}/86; локальные тесты — pytest.txt.
Полные requests/responses в mcp-transcript.json, exact prompts/outputs в JSONL и models/; credentials не экспортируются.
Backup SHA256 `{metadata['backup_sha256']}` хранится приватно. База не заменялась; сервер не обновлялся и не перезапускался.
`./reproduce.sh` создаёт новый snapshot и новые проекты. После фиксированной матрицы эксперимент останавливается.
''')
    unsafe = [r['id'] for r in rows if r.get('metrics') and not r['metrics']['safe']]
    unavailable = [r['id'] for r in rows if r['outcome'] != 'OK']
    write_json(report / 'rca-observations.json', {'MODEL_FAILURE_or_unsafe_selection_ids': unsafe,
        'incomplete_model_ids': unavailable, 'server_or_fixture_transport_failures': failures})
    (report / 'RCA.md').write_text(f'''# RCA

## MISSING_CAPABILITY

Native generation/ranking API не реализован. 18 существующих методов сохраняют прежний контракт;
гипотезы/выборы принадлежат внешней LLM. Новый selector ради тестов не добавлялся.

## Предварительные TEST_ORACLE_BUG

До первого model call unit-тест обнаружил: guessed obligation v2 ошибочно проходил stale-handled без refresh.
Исправлено требование явного refresh+review в M3/t0. Отдельный тест обнаружил token-padding boundary на один токен;
padding теперь считается после заголовка. development/ содержит исходные v0 модули и FAIL-трассу;
затем до inference найден и тестом воспроизведён ошибочный отказ диагностическому review закрытого обязательства v1.
Проверка теперь сравнивает его реальную версию, а не требует v2 у всех обязательств. Подготовка остановлена
при нуле model calls; pre-inference-attempt/ сохраняет исходный scorer и трассу. Scorer 1.1 заморожен до inference.
Результаты модели не использовались для исправления критерия. Старые QA-записи не удалялись.

## Наблюдаемые отклонения

Небезопасных структурированных предложений модели: {len(unsafe)}; неполных/ошибочных model calls: {len(unavailable)}.
Идентификаторы и минимальные reproducer-ссылки — rca-observations.json, models/<id>/prompt.txt/output.json/events.jsonl.
Плохой source/scope/version/закрытая ветка/обобщение относятся к MODEL_FAILURE, если сервер не выдавал неверный grant.
Timeout/сбой inference — TRANSPORT_FAILURE, не математический FAIL и не автоматически неисправность MCP-туннеля.
Ошибки runtime server/fixture: {json.dumps(failures, ensure_ascii=False)}.
Oracle не менялся после первого вызова; отсутствующие outcomes сохранены, не заменены ответами.

## Ограничения идентификации

Тест конечных действий проверяет измеримые source/depends-on/scope отношения, а не истинность произвольной прозы.
Интервенция независимого check заранее задана QA, не является автономным исполнением LLM выбора.
M2-no-audit отделяет структуру от валидатора. Одинаковый пользовательский token ceiling не делает backend usage строго равным.
Отсутствующий immutable model build и удалённый inference CPU не заполнены вымышленными значениями.
Недостаточная coverage или CI через ноль означает INCONCLUSIVE. Дополнительные прогоны ради значимости не выполняются.
''')
    if invalid:
        with (report / 'RCA.md').open('a') as stream:
            stream.write('\n## TEST_ORACLE_BUG / ambiguous prompt v1\n\n'
                'Пять первых полных ответов v1 показали, что assumes/tests заполняются прозой: schema не описывала их как ID lists. '
                'Формальная проверка unknown premise IDs ошибочно выглядела как оценка математических claims. '
                'Сохранены исходные пять оценок, prompts, scorer и незавершённые CLI requests в invalid-prompt-v1/. '
                'Результаты не переоценивались и не объединялись с новой матрицей. Минимальный патч уточняет только формат полей. '
                'Новая матрица использует прежний scorer, модель и критерии; concurrency зафиксирована 4 до её начала. '
                'Из-за revision после пилотных ответов общий причинный вывод консервативно INCONCLUSIVE независимо от CI; '
                'новые результаты — диагностическая повторная приёмка, не способ добиться положительной значимости.\n')
        with (report / 'report.md').open('a') as stream:
            stream.write('\nProtocol v1 остановлен из-за неоднозначного контракта ID-полей после пяти полных ответов; '
                'они сохранены отдельно и не входят в paired comparison. Перед новой фиксированной матрицей уточнён prompt. '
                'Все первоначальные оценки сохранены; общий вывод о причинном преимуществе остаётся INCONCLUSIVE из-за revision.\n')
    provenance = ['# Provenance', '', '| Decision ID | Proposal | Guard | Metric | Execution |', '|---|---|---|---|---|']
    provenance.extend(f"| {r['id']} | LLM | {'server audit' if 'audit' in r else 'none'} | scorer 1.1 | no automatic execution |" for r in rows)
    provenance += ['', 'Fixture/import/constraint decisions: human(operator), preregistered before inference.',
        'Source measurements: compute; lifecycle permission/audit: server; experiment selection: precommitted operator protocol.',
        'Mathematical verification: none. Native server generation: false. Exact inputs/results: operator-imports.jsonl/lifecycles.jsonl.']
    (report / 'PROVENANCE.md').write_text('\n'.join(provenance) + '\n')
    reproduce = report / 'reproduce.sh'
    reproduce.write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/causal_qa.py" "$@"\n')
    reproduce.chmod(0o755)
    return result['result']
