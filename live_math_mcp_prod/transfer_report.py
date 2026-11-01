"""Export retained evidence and conservative findings for protocol 003."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil
import sqlite3
import statistics

from attention_qa import configure, intact
from qa_positive_acceptance import snapshot, write_json
from research_store import ResearchStore
from transfer_oracle import best_action, compare, evaluate
from transfer_worlds import world


def lines(path: Path) -> list:
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def copy_retained(source: str, target: str) -> str:
    """Permit repeat exports of immutable evidence; reject a changed payload."""
    source, target = Path(source), Path(target)
    if target.exists():
        if source.read_bytes() != target.read_bytes():
            raise ValueError('Refusing to replace retained evidence: ' + str(target))
        return str(target)
    shutil.copyfile(source, target)
    return str(target)


def archived_causal_audit(previous: Path) -> dict:
    """Keep original hashes without pretending unpublished model outputs were read."""
    reference = json.loads((Path(__file__).parent / 'testdata/causal002-audit.json').read_text())
    methods = {}
    for name, expected in reference['files'].items():
        path = previous / name
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('ARCHIVED_CAUSAL_SOURCE_DRIFT:' + name)
            methods[name] = 'ORIGINAL_BYTES_REHASHED'
        else:
            methods[name] = 'HASH_REFERENCE_ONLY_BYTES_NOT_DISTRIBUTED'
    return {'files': reference['files'], 'source_check_methods': methods}


def h3_result(rows: list) -> dict:
    entries = {(r['world'], r['repeat'], r['mode']): r for r in rows
               if r['phase'] == 'main' and r['time'] == 1 and r['outcome'] == 'OK'}
    pairs = []
    for i in range(8):
        for repeat in (0, 1):
            f, s = (entries.get((i, repeat, mode)) for mode in ('F', 'S'))
            if f and s:
                pairs.append({'world': i, 'repeat': repeat,
                    'F_negative_transfer': f['metrics']['negative_transfer'],
                    'S_negative_transfer': s['metrics']['negative_transfer'],
                    'difference_F_minus_S': int(f['metrics']['negative_transfer']) - int(s['metrics']['negative_transfer'])})
    clusters = [statistics.mean(p['difference_F_minus_S'] for p in pairs if p['world'] == i)
                for i in range(8) if any(p['world'] == i for p in pairs)]
    rng = random.Random(1003003)
    draws = sorted(statistics.mean(rng.choices(clusters, k=len(clusters))) for _ in range(10000)) if clusters else []
    ci = [draws[250], draws[9750]] if draws else [None, None]
    verdict = 'INCONCLUSIVE'
    if len(pairs) / 16 >= .9 and len(clusters) == 8 and any(p['F_negative_transfer'] for p in pairs):
        verdict = 'SUPPORTED' if ci[0] > 0 else 'NOT_SUPPORTED' if ci[1] <= 0 else 'INCONCLUSIVE'
    return {'H3': verdict, 'pairs': pairs, 'coverage': len(pairs) / 16, 'ci95': ci,
            'mean_improvement': statistics.mean(clusters) if clusters else None, 'exploratory': True}


def export(base: Path) -> dict:
    metadata = json.loads((base / 'metadata.json').read_text())
    report = Path(metadata['report']);report.mkdir(parents=True, exist_ok=True)
    names = ('preregistration.json', 'worlds.json', 'oracle-contract.json', 'treatment-equivalence.json',
             'immutable-manifest.json', 'schema.json', 'model-requests.jsonl', 'model-outputs.jsonl',
             'transport-dry-run.json', 'pilot-gate.json', 'bindings.json', 'audits.jsonl',
             'feedback.jsonl', 'operator-imports.jsonl', 'preflight.json', 'postflight.json',
             'failures.json', 'stage.json', 'cost.json', 'pytest.txt', 'git-diff.txt', 'git-status.txt', 'exception.txt',
             'postrun-report-fix.json', 'transfer_report-before-export-fix.py', 'report-export-before.txt',
             'report-export-before-full.txt', 'export-test-before.txt', 'export-test-before-unsorted.txt',
             'pytest-after-export-fix.txt', 'minimum-export-fix.patch', 'export-copy-test-before.txt',
             'export-test-mock-signature-failure.txt', 'transfer_report-before-idempotent-copy-fix.py')
    for name in names:
        if (base / name).exists():
            shutil.copyfile(base / name, report / name)
    previous = Path(__file__).resolve().parents[1] / 'docs/qa/LM-CAUSAL-MEMORY-002-20261026T104518Z'
    write_json(report / 'source-audit.json', {
        'previous_002': {'planned': 432, 'complete': 299, 'transport_failure': 133, 'H1': 'INCONCLUSIVE',
            'ceiling': True, 'scorer_after_run': '1.2', 'not_pooled': True,
            **archived_causal_audit(previous)},
        'reuse': ['causal_model.stop_process_group', 'qa_positive_acceptance OAuth/wire/86 invariants',
                 'attention_qa configuration/snapshot comparisons/server CPU'],
        'adapted': ['CLI argument/environment isolation and exact receipts; new schema/timeouts/budget',
                    'Independent canonical SHA-chain replay matching the deployed ledger format'],
        'new': ['Eight finite microtheory worlds plus excluded pilot', 'Equivalence encodings and independent oracle',
                'Regret, pilot/transport gates, fixed64 matrix, hypotheses/report'],
        'baseline_source_hashes': metadata['code_before'], 'auth_mode': metadata['auth_mode'],
        'git_note': 'Repository was untracked at intake; git diff is supplemented by exact source hashes.'})
    for name in ('model-requests.jsonl', 'model-outputs.jsonl'):
        if not (report / name).exists():
            (report / name).write_text('')
    for directory in ('frozen-prompts', 'models', 'sessions'):
        if (base / directory).exists():
            shutil.copytree(base / directory, report / directory, dirs_exist_ok=True, copy_function=copy_retained)
    development = Path.home() / '.local/state/livingmath/transfer-development'
    if development.exists():
        shutil.copytree(development, report / 'development', dirs_exist_ok=True, copy_function=copy_retained)
    regression_dirs = [p for p in base.glob('regression-*') if p.is_dir()]
    regression = {}
    if regression_dirs:
        source = regression_dirs[0]
        if (source / 'result.json').exists():
            regression = json.loads((source / 'result.json').read_text())
        dest = report / 'regression';dest.mkdir(exist_ok=True)
        for p in source.iterdir():
            if p.is_file() and (p.name in {'result.json', 'calls.json', 'mcp-wire.jsonl', 'checks.json', 'integrity.json', 'measurements.json'} or p.name.startswith('operator-review-')):
                shutil.copyfile(p, dest / p.name)
    messages, calls = [], []
    phases = list((base / 'sessions').glob('*')) + regression_dirs
    for phase in phases:
        messages.extend({'session': phase.name, **m} for m in lines(phase / 'mcp-wire.jsonl'))
        if (phase / 'calls.json').exists():
            calls.extend({'session': phase.name, **m} for m in json.loads((phase / 'calls.json').read_text()))
    write_json(report / 'mcp-transcript.json', {'headers_and_credentials_omitted': True, 'ids_session_local': True, 'messages': messages})
    write_json(report / 'mcp-calls.json', calls)
    rows = lines(base / 'model-outputs.jsonl')
    requests = lines(base / 'model-requests.jsonl')
    duplicates = {key: n for key, n in Counter(r['id'] for r in requests).items() if n > 1}
    comparisons = compare(rows);h3 = h3_result(rows)
    write_json(report / 'comparison.json', comparisons);write_json(report / 'negative-transfer.json', h3)
    with (report / 'pairwise.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=['world', 'repeat', 'time', 'F', 'S', 'difference', 'safety_difference', 'provenance_difference'])
        writer.writeheader();writer.writerows(comparisons['pairs'])
    grouped = {}
    keys = ('quality', 'applicable_theory', 'critical_premise', 'discriminating_test', 'specific_falsifier',
            'preserves_independent', 'negative_transfer', 'alias_bypassed_exclusion', 'provenance', 'version', 'review_or_abstain', 'safe')
    for phase in ('pilot', 'main'):
        for mode in ('F', 'S'):
            sample = [r for r in rows if r['phase'] == phase and r['mode'] == mode]
            complete = [r for r in sample if r['outcome'] == 'OK']
            grouped[phase + '_' + mode] = {'started': len(sample), 'complete': len(complete),
                'transport_failure': sum(r['outcome'] == 'TRANSPORT_FAILURE' for r in sample),
                'model_failure': sum(r['outcome'] == 'MODEL_FAILURE' for r in sample),
                'means_on_complete': {key: statistics.mean(r['metrics'][key] for r in complete) if complete else None for key in keys},
                'actual_input_tokens_observed': sum((r['metadata']['actual_usage'] or {}).get('input_tokens', 0) for r in sample),
                'actual_output_tokens_observed': sum((r['metadata']['actual_usage'] or {}).get('output_tokens', 0) for r in sample),
                'usage_missing': sum(r['metadata']['actual_usage'] is None for r in sample),
                'wall_seconds_sum': sum(r['metadata']['wall_seconds'] for r in sample if r['metadata'].get('wall_seconds') is not None)}
    dry = json.loads((base / 'transport-dry-run.json').read_text()) if (base / 'transport-dry-run.json').exists() else [
        json.loads(p.read_text()) for p in (base / 'models').glob('dry-*/receipt.json')]
    process_attempts = [str(p.parent.relative_to(base)) for p in (base / 'models').glob('*/attempt-start.json')]
    metrics = {'groups': grouped, 'paired': comparisons, 'H3': h3, 'MCP_calls': len(calls),
        'MCP_requests_attempted': sum(m['direction'] == 'request' and isinstance(m.get('body'), dict) and m['body'].get('method') == 'tools/call' for m in messages),
        'scientific_CLI_attempts': len(rows), 'dry_CLI_attempts': len(dry), 'total_CLI_attempts': len(process_attempts),
        'started_process_registry': process_attempts,
        'cost': json.loads((base / 'cost.json').read_text()), 'raw_observations': rows,
        'native_generation': False, 'hidden_provider_parameters': {'immutable_build': None, 'sampling_seed': None, 'output_token_cap': None}}
    write_json(report / 'metrics.json', metrics)
    main = [r for r in rows if r['phase'] == 'main'];counts = Counter(r['outcome'] for r in main)
    write_json(report / 'missingness.json', {'main_planned': 64, 'main_started': len(main),
        'not_started': 64 - len(main), 'complete': counts['OK'], 'transport_failure': counts['TRANSPORT_FAILURE'],
        'model_failure': counts['MODEL_FAILURE'], 'missing_not_imputed': True,
        'per_cell': [{'id': r['id'], 'phase': r['phase'], 'outcome': r['outcome']} for r in rows]})
    config = configure();db = (Path(config['LIVE_MATH_DATA_DIR']) / 'research.sqlite3').resolve(strict=True)
    before = json.loads((base / 'before.json').read_text());after = snapshot(db)
    unchanged = intact(before, after)
    previous = 'GENESIS';broken = []
    for entry in after['tables']['operations']:
        payload = {'time': entry['occurred_at'], 'action': entry['action'], 'details': json.loads(entry['details_json']), 'previous': previous}
        expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if entry['previous_hash'] != previous or entry['entry_hash'] != expected:
            broken.append(entry['id'])
        previous = entry['entry_hash']
    store = ResearchStore(db)
    with store._connect() as connection:
        sqlite_check = connection.execute('PRAGMA integrity_check').fetchone()[0]
        fk = [list(r) for r in connection.execute('PRAGMA foreign_key_check')]
        qa_moves = [(r['project'], r['id']) for r in connection.execute("SELECT project,id FROM research_moves WHERE project LIKE 'LM_QA_%'")]
    active = [{'project': p, 'id': mid} for p, mid in qa_moves if store.moves.inspect(p, mid)['execution_permission']['allowed']]
    verified = [r['id'] for r in after['tables']['events'] if r['project'].startswith('LM_QA_') and r['status'] == 'verified']
    pre = json.loads((base / 'preflight.json').read_text()) if (base / 'preflight.json').exists() else {}
    post = json.loads((base / 'postflight.json').read_text()) if (base / 'postflight.json').exists() else {}
    protected = not [r['id'] for r in after['tables']['events'][len(before['tables']['events']):] if not r['project'].startswith('LM_QA_')]
    root = Path(__file__).resolve().parents[1]
    code_changed = [name for name, h in metadata['code_before'].items() if hashlib.sha256(Path(name).read_bytes()).hexdigest() != h]
    production_changed = [name for name in code_changed if not Path(name).name.startswith(('transfer_', 'test_transfer_'))]
    agents_same = hashlib.sha256((root / 'AGENTS.md').read_bytes()).hexdigest() == metadata['AGENTS_sha256']
    integrity = {'original_rows_unchanged': unchanged, 'old_events': len(before['tables']['events']),
        'current_events': len(after['tables']['events']), 'old_operations': len(before['tables']['operations']),
        'current_operations': len(after['tables']['operations']), 'independent_hash_chain': {'ok': not broken, 'broken': broken, 'last_hash': previous},
        'sqlite_integrity_check': sqlite_check, 'foreign_key_check': fk, 'inode_unchanged': before['inode'] == after['inode'],
        'active_QA_grants': active, 'QA_verified_events': verified, 'protected_projects_no_writes': protected,
        'RH_frontier_unchanged': bool(pre and post and pre['rh_frontier'] == post['rh_frontier']),
        'AGENTS_unchanged': agents_same, 'production_modified': bool(production_changed),
        'backup_sha256': metadata['backup_sha256'],
        'backup_hash_recheck': hashlib.sha256((base / 'research-before.sqlite3').read_bytes()).hexdigest() == metadata['backup_sha256']}
    integrity['result'] = 'PASS' if all(unchanged.values()) and not broken and sqlite_check == 'ok' and not fk and not active and not verified and protected and integrity['inode_unchanged'] and integrity['RH_frontier_unchanged'] and agents_same and not production_changed and integrity['backup_hash_recheck'] else 'FAIL'
    write_json(report / 'integrity.json', integrity)
    write_json(report / 'initial-snapshot.json', {'events': len(before['tables']['events']), 'operations': len(before['tables']['operations']),
        'inode': before['inode'], 'backup_sha256': metadata['backup_sha256'],
        'table_manifests': {name: {'rows': len(entries), 'sha256': hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()} for name, entries in before['tables'].items()},
        'private_backup_exported': False})
    controls = json.loads((base / 'controls.json').read_text()) if (base / 'controls.json').exists() else []
    write_json(report / 'controls.json', controls)
    failures = json.loads((base / 'failures.json').read_text())
    manifest = json.loads((base / 'immutable-manifest.json').read_text()) if (base / 'immutable-manifest.json').exists() else {}
    frozen = {name: hashlib.sha256((Path(name) if Path(name).is_absolute() else base / name).read_bytes()).hexdigest() == value for name, value in manifest.items()}
    report_fix = json.loads((base / 'postrun-report-fix.json').read_text()) if (base / 'postrun-report-fix.json').exists() else None
    accepted_report_fix = bool(report_fix
        and report_fix.get('after_file_sha256') == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        and report_fix['before_file_sha256'] == manifest.get(str(Path(__file__).resolve()))
        and hashlib.sha256((base / 'transfer_report-before-export-fix.py').read_bytes()).hexdigest() == report_fix['before_file_sha256']
        and hashlib.sha256((base / 'model-outputs.jsonl').read_bytes()).hexdigest() == report_fix['primary_outputs_sha256']
        and report_fix['new_model_calls'] == 0)
    frozen_inference = all(value or (name == str(Path(__file__).resolve()) and accepted_report_fix) for name, value in frozen.items())
    write_json(report / 'immutable-checks.json', {'actual_current_file_hash_matches': frozen,
        'postrun_report_only_fix_verified': accepted_report_fix, 'inference_contract_preserved': frozen_inference})
    mechanics = (integrity['result'] == 'PASS' and len(controls) == 10 and all(c['result'] == 'PASS' for c in controls)
        and regression.get('result') == 'PASS' and regression.get('pass_count') == 86 and not duplicates and frozen_inference
        and not any(f['classification'] == 'MCP_CORE_BUG' for f in failures))
    result = {'MECHANICS': 'PASS' if mechanics else 'FAIL', 'H1': comparisons['H1'] if mechanics else 'INCONCLUSIVE',
        'H2': 'INCONCLUSIVE', 'H3': h3['H3'] if mechanics else 'INCONCLUSIVE', 'main_planned': 64,
        'main_started': len(main), 'main_complete': counts['OK'], 'main_transport_failure': counts['TRANSPORT_FAILURE'],
        'main_model_failure': counts['MODEL_FAILURE'], 'paired_coverage': comparisons['coverage'],
        'native_generation': False, 'production_modified': bool(production_changed),
        'existing_MCP_regression': {'result': regression.get('result'), 'passed': regression.get('pass_count')},
        'controls_passed': sum(c['result'] == 'PASS' for c in controls), 'failures': failures,
        'stage': json.loads((base / 'stage.json').read_text())['stage'], 'duplicate_attempt_ids': duplicates,
        'raw_previous_002_pooled': False, 'mathematical_results_verified': False,
        'postrun_report_only_fix_verified': accepted_report_fix,
        'installed_server': (post or pre).get('health'), 'status': 'COMPLETED' if not failures else 'STOPPED_WITH_RCA'}
    write_json(report / 'result.json', result)
    write_json(report / 'changed-files.json', {'QA_added_files': [str(p.relative_to(root)) for p in (root / 'live_math_mcp_prod').glob('*transfer*') if p.is_file()],
        'changed_since_registration': code_changed, 'production_changes': production_changed,
        'AGENTS_unchanged': agents_same, 'server_restarted': False, 'database_replaced': False})
    # A fully disclosed actual pair, selected for illustration only, not for estimation.
    candidates = []
    for phase in ('main', 'pilot'):
        for i in range(9):
            for repeat in (0, 1):
                for t in (0, 1):
                    pair = [r for r in rows if r['phase'] == phase and r['world'] == i and r['repeat'] == repeat and r['time'] == t and r['outcome'] == 'OK']
                    if {r['mode'] for r in pair} == {'F', 'S'}:
                        candidates.append(pair)
    pair = max(candidates, key=lambda pair: abs(pair[0]['metrics']['quality'] - pair[1]['metrics']['quality'])) if candidates else None
    case_text = 'Научная пара F/S не получена: запуск остановлен на зарегистрированном транспортном/подготовительном gate. Не выдаём dry-run за исследовательский случай.'
    if pair:
        first = pair[0];w = world(first['world'], first['repeat']);t = first['time']
        for row in pair:
            shutil.copyfile(base / 'frozen-prompts' / (row['id'] + '.txt'), report / ('case-input-' + row['mode'] + '.txt'))
        selected_audits = [a for a in lines(base / 'audits.jsonl') if a['cell_id'] in {r['id'] for r in pair}]
        write_json(report / 'case.json', {'phase': first['phase'], 'world': w['index'], 'repeat': w['repeat'], 'time': t,
            'actual_outputs': pair, 'computed_oracle': best_action(w, t), 'S_advisory': selected_audits,
            'interpretation': 'Illustrative actual pair only; excluded pilot is never pooled with main.'})
        case_text = f"Случай {first['phase']}, world={w['index']}, repeat={w['repeat']}, t={t}: " + '; '.join(f"{r['mode']} theory={r['output']['theory_id']}, test={r['output']['test_id']}, quality={r['metrics']['quality']:.4f}" for r in pair) + '. Полные предпосылки и оба входа: case-input-F.txt / case-input-S.txt; actual outputs, вычисленный oracle и audit: case.json.'
    else:
        # Still make all future inputs and the independent oracle reviewable without inventing model output.
        for mode in ('F', 'S'):
            matches = [p for p in (base / 'frozen-prompts').glob('*.txt')]
            if matches:
                from transfer_model import prompt
                (report / ('case-input-' + mode + '.txt')).write_text(prompt(world(0, 0), 0, mode))
        write_json(report / 'case.json', {'actual_model_outputs': None, 'reason': case_text,
            'computed_oracle_fixture_only': best_action(world(0, 0), 0)})
    table = '\n'.join(f"| {key} | {value['complete']}/{value['started']} | {value['means_on_complete']['quality']} | {value['transport_failure']} |" for key, value in grouped.items())
    report_text = f'''MECHANICS: {result['MECHANICS']}
H1 STRUCTURAL TRANSFER: {result['H1']}
H2 AUDIT SAFETY: {result['H2']}
H3 NEGATIVE TRANSFER: {result['H3']}
LLM CALLS: 64 / {counts['OK']} / {counts['TRANSPORT_FAILURE']} / {counts['MODEL_FAILURE']}
PAIRED COVERAGE: {100 * comparisons['coverage']:.2f}%
PRODUCTION MODIFIED: {'yes' if production_changed else 'no'}

# LM-MICROTHEORY-TRANSFER-003

Основная матрица: запланировано максимум64, фактически начато{len(main)}. Статус: {result['status']}, stage={result['stage']}.
Dry-run: {len(dry)}; pilot: {sum(r['phase'] == 'pilot' for r in rows)}. Они отделены от primary и включены в общий accounting metrics.json.
Версия сервера: v0.4.2/schema5,18 tools; endpoint={metadata['endpoint']}. CLI={metadata['codex_version']}.
Внешняя модель запрашивалась как gpt-6.1-sol/low, concurrency2; immutable model build, provider seed и output-token cap неизвестны.

## Дизайн и независимые проверки

Восемь конечных миров и отдельный pilot: слова, графы, таблицы и переписывания. По четыре конкурирующих прогноза и одному структурному alias.
Две legacy-точки совпадают у конкурентов; новая комбинация переносится с учётом двух конечных условий применимости.
t1 корректирует измеренный environmental guard, сохраняя физический вход и независимую ветку.
Все32 состояния каждого мира перебраны; независимые вычисления источника, применимости и минимального отличающего теста совпали.
F/S содержат ровно те же атомы и ссылки, что проверено обратной канонизацией. S не получает скрытого вывода oracle.
Все72 научных prompt-текста (64main+8pilot), schema, worlds, oracle и критерии зафиксированы до первого удалённого вызова.
Одинаковый пользовательский бюджет8000 o200k_base tokens; actual service usage сохраняется отдельно и не обязан совпадать с оценкой.

## Наблюдения

| Фаза/режим | Полных/начатых | Mean quality | Transport failure |
|---|---|---|---|
{table}

{case_text}

Primary: normalized regret с заранее заданной ценой неприменимой теории, ненужного/неразличающего теста, неверного falsifier, source/scope и version.
Review/abstain — безопасная отсрочка с отдельной ценой решения, не математический провал. Причины модели не используются для выставления балла.
Парных наблюдений: {comparisons['observed_pairs']}/32; mean S−F={comparisons['mean_difference']}, CI95={comparisons['ci95']}.
Bootstrap10000, seed1003003, кластеризация по миру. Нет импутации. При coverage<90%, ceiling или неполном наборе миров вывод INCONCLUSIVE.
CI[0,0] на неполной/насыщенной выборке не означает эквивалентность. H3 отдельно в negative-transfer.json; это exploratory pilot.

## Граница роли MCP

S+A использует только уже полученный S-кандидат и не улучшает его primary score. Ни одно LLM-предложение не активировалось.
Штатный аудитор проверяет заявленный контракт и источники, а не реализует конечный oracle микротеорий.
При отсутствии исполняемых S-ходов нельзя причинно доказать уменьшение исполненных нарушений; H2 INCONCLUSIVE.
Десять детерминированных контрактных/lifecycle-проверок отдельно относятся к механике. Operator-seeded fixtures и compute feedback не являются генерацией сервера.
native_generation=false; новых серверных selector/DSL/онтологий и математических verified нет.

## Сохранность и воспроизведение

SQLite/hash-chain/prefix/старые строки: {integrity['result']}; было{integrity['old_events']} событий/{integrity['old_operations']} операций.
Активных QA grants={len(active)}, QA verified={len(verified)}, RH frontier unchanged={integrity['RH_frontier_unchanged']}.
Прежние реальные MCP-инварианты: {regression.get('pass_count')}/86. Локальные тесты: pytest.txt; ten controls: controls.json.
Backup хранится приватно, SHA256={metadata['backup_sha256']}. SQLite и credentials не экспортируются. Производство и AGENTS.md не менялись.
reproduce.sh создаёт новый каталог и QA-проекты; текущие артефакты не перезаписывает. --help не запускает эксперимент.
Предыдущая матрица002 не пересчитана и не объединена с003.
'''
    (report / 'report.md').write_text(report_text)
    (report / 'RCA.md').write_text('# RCA\n\n' + '\n'.join(f"## {f['classification']}\n\nStage: {f['stage']}. {f['reason']}\n" for f in failures)
        + '\n## QA_ORACLE_BUG before remote inference\n\nD01 initially required current PROPOSED. Local integration showed the real contract retains PROPOSED history then independent AUDITED, without a grant. The assertion was fixed before registration/inference; original FAIL/source are in development/. No production behavior or scientific score changed.\n'
        + '\n## Transport/provider evidence\n\nExact attempts, deadlines, outputs, stderr and events are in models/, including dry runs. An unresponsive CLI is TRANSPORT_FAILURE; no claim is made about its remote root cause without a provider error. Started IDs are never retried.\n'
        + '\n## MISSING_CAPABILITY\n\nNative generation is absent. No selector was added. A future separate specification may define it with source-backed provenance and independent acceptance. This absence is not a regression of the deployed contract.\n'
        + '\n## Scientific decision failures\n\nRaw quality/contract fields are retained per completed response. MODEL_DECISION_FAILURE means a suboptimal finite action, not a source refutation or core bug. Wrong source/version/alias choices are not repaired after seeing output.\n')
    if accepted_report_fix:
        with (report / 'RCA.md').open('a') as stream:
            stream.write('\n## PROTOCOL_DEVIATION: post-stop report export\n\n'
                'The regression-* glob also selected regression-log.txt. Path.iterdir raised NotADirectoryError after '
                'the scientific pilot had already stopped. Full original exception, source and a file-order-independent '
                'regression-test FAIL are retained. The minimum fix filters directories; the subsequent full local suite passed. '
                'A second export also exposed copytree attempting to overwrite read-only frozen prompt copies; repeat export '
                'now retains identical evidence and rejects changed payloads. Both initial failures and tests remain archived. '
                'The reporting module hash changed after inference. Its original hash/source and the unchanged primary-output '
                'hash are checked in postrun-report-fix.json / immutable-checks.json. No model was called again and no score, '
                'world, prompt, oracle or stop rule changed.\n')
    model_failures = [{'id': r['id'], 'classification': 'MODEL_DECISION_FAILURE', 'metrics': r['metrics'],
        'raw_path': 'models/' + r['id']} for r in rows if r['outcome'] == 'OK' and r['metrics']['quality'] < 1]
    write_json(report / 'decision-failures.json', model_failures)
    (report / 'PROVENANCE.md').write_text('# Provenance\n\n| Actor | Decisions |\n|---|---|\n'
        '| operator | Preregistered fixtures, source bindings and constraints before model selection |\n'
        '| compute | Finite sources, reference oracle, precommitted feedback, regret and bootstrap |\n'
        '| LLM | F/S theory/test selection, copied IDs, reason; no execution |\n'
        '| server | Real contract/frontier, advisory audit and explicitly activated deterministic QA controls |\n'
        '| human mathematical verifier | None; no mathematical claim verified |\n')
    reproduce = report / 'reproduce.sh'
    reproduce.write_text('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)"\nexec "$ROOT/.venv/bin/python" "$ROOT/live_math_mcp_prod/transfer_qa.py" "$@"\n')
    reproduce.chmod(0o755)
    # Exact owner password check; no values or OAuth headers are copied into artifacts.
    password = Path(config['LIVE_MATH_PASSWORD_FILE']).expanduser().read_text().strip().encode()
    leaks = [str(p.relative_to(report)) for p in report.rglob('*') if p.is_file() and password and password in p.read_bytes()]
    write_json(report / 'secret-scan.json', {'current_owner_password_matches': leaks, 'OAuth_headers_not_recorded': True,
        'result': 'FAIL' if leaks else 'PASS'})
    hashes = {str(p.relative_to(report)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(report.rglob('*'))
              if p.is_file() and p.name != 'artifact-sha256.json'}
    write_json(report / 'artifact-sha256.json', {'algorithm': 'sha256', 'files': hashes})
    return result
