"""Russian018 private release capsule. Does not install or contact production."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def wire_counts(path):
    rows = [json.loads(s) for s in Path(path).read_text().splitlines()]
    methods = {}
    for row in rows:
        if row['direction'] == 'request':
            method = row['body'].get('method')
            methods[method] = methods.get(method, 0) + 1
    return methods


def copy_public(src, dst):
    """Explicit artifact allowlist; no DB, TLS credentials or cache."""
    for p in src.rglob('*'):
        rel = p.relative_to(src)
        if not p.is_file() or any(n in rel.parts for n in ('__pycache__', 'source', 'sources', 'sources018')):
            continue
        if p.suffix not in ('.json', '.jsonl', '.md', '.txt', '.py', '.sql', '.log', '.sh'):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)


def run(base: Path, out: Path, fault: Path):
    current = read(base / 'current.json')
    main = Path(current['output'])
    replay = base / 'final-clean-replay'
    mr, fr, rr = read(main / 'result.json'), read(fault / 'result.json'), read(replay / 'replay-result.json')
    assert mr['status'] == 'PASS_PRIVATE_HTTPS_STAGING' and fr['status'] == 'PASS'
    assert rr['status'] == 'PASS_SAME_MACHINE_PRIVATE_REPLAY'
    checks = read(main / 'checks.json')
    assert all(x['result'] == 'PASS' for x in checks)
    preservation = read(base / 'final-preservation.json')
    assert not preservation['modified_protected_files']
    pytest = (base / 'pytest-distribution.log').read_text()
    matched = re.search(r'(\d+) passed', pytest)
    assert matched and int(matched[1]) == 657
    historical = read(base / 'historical86-summary.json')
    assert historical['passed'] == 86 and not historical['failed']
    out.mkdir(parents=True, exist_ok=False)
    copy_public(main, out / 'https')
    copy_public(fault, out / 'faults')
    for name in ('backup-restore.json', 'schema-before-after.json'):
        shutil.copy2(base / 'storage-final/results' / name, out / name)
    shutil.copy2(base / 'guard-probes-engine.json', out / 'guard-probes-engine.json')
    assert read(base / 'guard-probes-engine.json')['all_exercised_pass']
    for name in ('final-preservation.json', 'retired-fault-grants.json'):
        shutil.copy2(base / name, out / name)
    shutil.copy2(base / 'pytest-distribution.log', out / 'pytest.log')
    shutil.copy2(base / 'historical86-summary.json', out / 'historical86.json')
    shutil.copy2(base / 'historical86.log', out / 'historical86.log')
    write(out / 'replay.json', rr)
    copy_public(replay / 'acceptance', out / 'replay/https')
    copy_public(replay / 'faults', out / 'replay/faults')
    for name in ('portable_tests.log', 'HTTPS.log', 'faults.log'):
        shutil.copy2(replay / name, out / 'replay' / name)
    shutil.copytree(base / 'frozen', out / 'frozen', ignore=shutil.ignore_patterns('__pycache__'))
    source = out / 'source'
    source.mkdir()
    for p in SOURCE.rglob('*'):
        rel = p.relative_to(SOURCE)
        if p.is_file() and not any(n in rel.parts for n in ('.venv', '__pycache__', '.pytest_cache')) and (
                p.suffix in ('.py', '.sql') or p.name.startswith('requirements') or p.suffix == '.json' and p.name != 'pilot_smoke_results.json'):
            dst = source / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    (out / 'AGENTS.md').write_bytes((ROOT / 'AGENTS.md').read_bytes())
    attempts = []
    for parent in ('LM-RELEASE-018-DEPLOY', 'LM-RELEASE-018-FAULTS', 'LM-RELEASE-018-RELEASE'):
        for folder in sorted((ROOT / 'docs/qa' / parent).iterdir()):
            if not folder.is_dir() or folder.resolve() in (main.resolve(), fault.resolve(), out.resolve()) or not (folder / 'result.json').exists():
                continue
            item = {'cohort': folder.name, 'result': read(folder / 'result.json')}
            if (folder / 'packaging-failure.json').exists():
                item['packaging'] = read(folder / 'packaging-failure.json')
            attempts.append(item)
            copy_public(folder, out / 'prior-cohorts' / parent / folder.name)
    write(out / 'prior-cohorts.json', attempts)
    counts = wire_counts(main / 'http-wire.jsonl')
    fault_counts = wire_counts(fault / 'http-wire.jsonl')
    write(out / 'protocol-counts.json', {'accepted_main': counts, 'accepted_faults': fault_counts,
        'completed_tool_calls': mr['MCP_tool_calls'] + fr['MCP_tool_calls_completed'],
        'note': 'Wire counts include interrupted/cancelled requests; completed calls counted separately. Prior cohorts/replay never pooled.'})
    catalogues = [json.loads(s) for s in (main / 'catalogues.jsonl').read_text().splitlines()]
    enabled = next(c for c in catalogues if c['enabled'])
    disabled = next(c for c in catalogues if not c['enabled'])
    write(out / 'capabilities.json', {'default_off_tools': disabled['tools'], '018_tools': enabled['tools'],
        'version': {'production': '0.4.2', 'schema': 5, 'private_HTTP': '018.1', 'private_engine': '017.1'},
        'reviewed_semantic_change': 'Only opt-in018 HTTP denies generic activation/completion for all projects. Original24 entrypoint unchanged.'})
    live_contract = read(base / 'live-contract.json')
    write(out / 'live-readonly-canary.json', {'health': live_contract['health'],
        'tool_names': [t['name'] for t in live_contract['tools']['tools']],
        'tools_sha256': hashlib.sha256(json.dumps(live_contract['tools'], sort_keys=True).encode()).hexdigest(),
        'research_writes': False, 'service_restarted': False, 'ingress': 'Temporary Quick Tunnel; NOT stable',
        'preservation': preservation})
    readiness = {
        'R1': {'status': 'PASS', 'scope': 'unchanged004–017,657 local tests,86 historical'},
        'R2': {'status': 'PASS', 'scope': 'private staging only; 18 typed cycles/3 families/4 outcomes'},
        'R3': {'status': 'PASS', 'scope': 'private HTTPS/OAuth; signatures/nonce/expiry; owner/executor separation'},
        'R4': {'status': 'FAIL', 'scope': 'production guards NOT installed; private migration/restore PASS'},
        'R5': {'status': 'FAIL', 'scope': 'production Quick Tunnel; no named DNS/TLS ingress or approved public write canary'},
        'R6': {'status': 'INCONCLUSIVE', 'scope': '019 independent machine/person; same-machine replay insufficient'},
        'R7': {'status': 'FAIL', 'scope': '019 real external source; computational fixtures are not external evidence'},
        'R8': {'status': 'FAIL', 'blocking': False, 'scope': 'existing scientific NO_GO retained; no proof promoted'}}
    gates = {g: {'status': 'PASS', 'scope': 'private/audit only'} for g in ('G0', 'G1', 'G2', 'G3', 'G4', 'G6', 'G7', 'G8')}
    gates['G5'] = {'status': 'BLOCKED_EXTERNAL_DEPENDENCY', 'reason': 'No named domain, DNS/tunnel credentials, TLS route or operator-approved production changes supplied.'}
    write(out / 'release-readiness.json', {'ready_for_production_1_0': False, 'deployment': 'NOT_PERFORMED', 'gates': gates, 'release_gates': readiness})
    allfiles = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*') if p.is_file() and
        ('018' in p.name or p.parent.name == 'migrations') and p.suffix not in ('.pyc',)}
    write(out / 'source-patch-manifest.json', {'changed_or_added_files': allfiles, 'old_protected_files': preservation['protected_files_checked'],
        'modified_old_files': [], 'old017_patch_sha256': read(base / 'baseline.json')['017_patch_sha256']})
    patch = []
    for name in sorted(allfiles):
        p = ROOT / name
        patch.extend(difflib.unified_diff([], p.read_text().splitlines(True), fromfile='/dev/null', tofile='b/' + name))
    (out / 'deployment-review.patch').write_text(''.join(patch))
    shutil.copy2(main / 'security-controls.json', out / 'security-controls.json')
    # Root full MCP wire retains the unmodified ordered main wire; fault wire
    # is separately named, preventing ID collisions between independent runs.
    shutil.copy2(main / 'http-wire.jsonl', out / 'http-wire.jsonl')
    shutil.copy2(fault / 'fault-matrix.json', out / 'fault-matrix.json')
    write(out / 'deployment-manifest.json', {'deployment': 'NOT_PERFORMED', 'production': preservation['live'],
        'service': preservation['service'], 'stage': {'HTTP': '018.1', 'engine': '017.1', 'schema': 5, 'tools': 27},
        'approval': 'NOT_GIVEN_FOR_PRODUCTION', 'default_enabled': False,
        'private_state': str(base), 'credentials_in_capsule': False})
    result = {'status': 'PASS_PRIVATE_STAGING_BLOCKED_PRODUCTION', 'deployment': 'NOT_PERFORMED',
        'created_at': datetime.now(timezone.utc).isoformat(), 'pytest': 657, 'historical': 86,
        'main': mr, 'faults': fr, 'replay': rr, 'G5': 'BLOCKED_EXTERNAL_DEPENDENCY',
        'ready_for_production_1_0': False, 'proof_status': 'unverified', 'production_research_rows_changed': 0}
    write(out / 'result.json', result)
    processes = [json.loads(s) for s in (main / 'http-processes.jsonl').read_text().splitlines()]
    fprocesses = [json.loads(s) for s in (fault / 'http-processes.jsonl').read_text().splitlines()]
    costs = read(main / 'costs.json')
    accounting = {'main': costs, 'main_HTTP_processes': len(processes), 'fault_HTTP_processes': len(fprocesses),
        'main_HTTP_CPU_ns': sum(p['CPU_ns'] for p in processes), 'fault_HTTP_CPU_ns': sum(p['CPU_ns'] for p in fprocesses),
        'main_HTTP_peak_RSS_KiB': max(p['peak_RSS_KiB'] for p in processes),
        'setup_wall': 'NOT_MEASURED; snapshot creation/source audit excluded from runtime speed claims',
        'failed_cohorts': 'Separate original logs; never added to PASS denominators', 'external_inference': 'NOT_USED',
        'API_payments': 'NONE', 'same_machine_replay_fault_costs': read(replay / 'faults/costs.json')}
    write(out / 'costs.json', accounting)
    (out / 'report.md').write_text(f'''# LM-RELEASE-018 — отчёт

**Итог: PASS private staging; production deployment НЕ выполнен.** G5 — BLOCKED_EXTERNAL_DEPENDENCY. Готовность production 1.0 не объявляется.

Основной принятый cohort: `{main.name}`. Получены {mr['checks']} PASS, {mr['MCP_tool_calls']} завершённых MCP-вызовов, 18 циклов: 9 SUCCESS, 3 FAILURE, 3 INCONCLUSIVE, 3 ERROR; affine/permutation/stack. Это вычислительные QA-источники, а не независимый внешний источник или математическое доказательство. Все новые результаты unverified.

Fault cohort `{fault.name}`: {fr['checks']} PASS, {fr['MCP_tool_calls_completed']} завершённых tool-вызовов плюс прерванные запросы, отдельно посчитанные в protocol-counts.json. Настоящие TLS/OAuth, PKCE и owner login; unauthenticated/expired/revoked/wrong scope отказы, точные причины signature/nonce/key/scope/expiry tamper; SQL/DB delta при отказах отсутствует.

Полный pytest: **657 PASS**, одно предупреждение Starlette из прежнего test_http.py. Historical86: **86 PASS** на мигрированной private копии, через stdio; это отдельная проверка legacy, не HTTPS. Чистый same-machine replay: 18 циклов + fault suite + 39 portable tests, без рабочих DB/ключей. R6 не установлен.

Версионированная schema5 миграция защищает events/operations и критическую историю; повтор — no-op, частичная схема/конфликтный trigger запрещены. Schema/FK preconditions зафиксированы в migrations/018_schema.json. SQL guards не защищают от владельца DDL/файла. Политики/ожидающие approvals/текущий указатель версии обязательства остаются штатно изменяемыми; их история защищена.

BackupAPI обеих рабочих DB; две новые restore-пары (4 DB) с совпадением строк/schema/sequence/full hashes/chain и разными inode. Дополнительно два восстановления committed018 ledger с чтением history по HTTPS. SIGKILL до/внутри/после транзакций, orphan grant reconciliation, ровно один receipt при повторе/конкурентном commit. Прерванное измерение сохраняется как evidence и требует нового owner-reviewed предложения; измерение не синтезируется и автоматически не повторяется.

Staging rollback **27 → 24 → 27** сохраняет committed evidence. Canary только `LM_QA_018_CANARY` в private DB; публичный canary только read-only. Перезапуск требует owner pre-start reconcile. Bare HTTP factory не является самостоятельно управляемым deployment supervisor.

Production фактически остаётся **0.4.2 / schema5 / 24 tools**, PID326193. Canonical: 2056 событий/4813 операций; typed: 2064/4836. Все исходные таблицы, schema, sequence, hash-chain и inode совпали; {preservation['protected_files_checked']} прежних файлов проверено, изменённых 0. Рабочий сервис не перезапускался, SQL guards в нём отсутствуют.

R1 PASS; R2/R3 PASS только staging; **R4/R5 FAIL**, R6 INCONCLUSIVE, R7 FAIL; R8 scientific NO_GO сохранён и не блокирует engine release. Никакого Bridge/SUTI или RH-исследования не выполнялось.

Ошибки предыдущих cohort сохранены в prior-cohorts/ и RCA.md. Их результаты не объединены с принятым cohort. Подробности: release-readiness.json, backup-restore.json, schema-before-after.json, security-controls.json, fault-matrix.json, integrity и полные обезличенные MCP-трассы в https/, faults/ и replay/.

Измеренные затраты основного прогона: wall {costs['driver_wall_ns']/1e9:.6f} с; CPU driver {costs['driver_CPU_ns']/1e9:.6f} с; {len(processes)} HTTP-процессов, суммарный wait4 CPU {accounting['main_HTTP_CPU_ns']/1e9:.6f} с, max RSS {accounting['main_HTTP_peak_RSS_KiB']} KiB. Owner/executor workers и отдельный replay перечислены в costs.json. Setup wall не измерялся; ускорение и стоимость внешнего inference не заявляются.
''')
    (out / 'RCA.md').write_text('''# RCA и границы 018

Принятый свежий cohort прошёл private gates. Promotion в production остановлен внешними условиями: отсутствуют именованный домен/DNS/TLS route и отдельный owner approval. Текущий Quick Tunnel не является stable ingress. R4/R5 не закрыты. R6/R7 требуют независимой beta019.

Сохранённые дефекты QA:

1. Первый /revoke не аутентифицировал конфиденциального клиента. Исправлено передачей credentials только в памяти; исходный FAIL сохранён.
2. Legacy research_contract лениво импортировал typed_cycle011_public после Landlock. Публичный декларативный модуль загружается до sandbox; каталог исходников целиком не разрешён.
3. Fault DB вне workspace давала generic REJECTED до проверки подписи. Старый cohort044245 не используется как доказательство signed-negative controls. Строгий последующий тест сохранил FAIL; новый cohort использует разрешённый private workspace и точную причину каждого отказа.
4. HTTP restore-копия вне allowlist была заблокирована; parser скрывал причину попыткой JSON parsing. Восстановления перемещены в НОВЫЕ private workspace paths, parser сохраняет текст MCP errors. Полный свежий fault cohort прошёл.
5. Первый package scan нашёл собственную строку-шаблон PRIVATE KEY в коде scanner, а не реальный ключ. Частичный пакет не принят; packaging-failure.json сохраняет STOP_WITH_RCA и отменяет G8 claim этого cohort. Маркер собирается из частей; новый пакет проверяется отдельно.

Один промежуточный cohort имеет вручную заданное имя050000000001Z; это ID, не фактическое время запуска. Исходные traces/checks/results не переписаны. Завершение остановленных QA-разрешений выполнено отдельными append-only owner записями; см. retired-fault-grants.json. Ни одна неправильная подпись не принята.

Ограничения: подпись подтверждает локальный вычислительный источник и exact binding, не физическую аутентичность; схема/DDL owner доверенный; TLS CA частная loopback, не публичная; same-machine replay не независимая установка. При relocation typed configuration сохраняется как историческое canonical binding;018 reviewed adapter изолирован, а старый24 rollback проверен на том же пути. Произвольный перенос старого24 canonical binding отдельно не заявляется.
''')
    (out / 'operator-runbook.md').write_text('''# Операторский runbook 018

Production installation этим пакетом не разрешена; Python migration дополнительно запрещает реальные live paths/inode. SQL diff предназначен для ревью. Отдельный одобренный production installer/approval record и window нужны прежде любых live SQL/config/service changes.

## Private воспроизведение

Python3.13; `python3 -m venv /tmp/lm018-venv`, `/tmp/lm018-venv/bin/python -m pip install -r source/requirements-018.txt`. Затем `PYTHON=/tmp/lm018-venv/bin/python bash reproduce.sh /tmp/lm018-new-work`. Work path должен отсутствовать. Никаких OpenAI API платежей, рабочих DB или внешнего математического источника не требуется. Для historical86 нужен отдельный приватный fixture22 backup, он не распространяется.

## Управляемый запуск

Сначала local owner: `printf '{}' | python source/deploy018_authority.py --db <PRIVATE_TYPED_DB> reconcile`. Затем отдельный HTTP процесс: `python source/deploy018_http.py --data <PRIVATE_WORKSPACE> --typed <PRIVATE_TYPED_DB> --origin https://localhost:<PORT> --port <PORT> --cert <CA_CERT> --key <TLS_KEY> --password <OWNER_PASSWORD_FILE> --enable018`. Пути и TLS/password создаёт QA runner. Не передавать executor keys этому процессу. Owner pre-start reconcile обязателен после каждого restart; остаточные permits отзываются, evidence остаётся. Проверить /healthz, OAuth и реальный tools/list27. Без --enable018 — прежние24 tools.

## Внешние действия для G5/R4/R5

1. Владелец выбирает постоянный hostname и предоставляет DNS/именованный tunnel route/TLS доступы локально в защищённой конфигурации, не в чате. Сейчас подходящих credentials/config не найдено; никакой постоянный URL не создан.
2. Проверить DNS/TLS, supervisor/restart с неизменным URL, OAuth resource/issuer origin и ChatGPT HTTPS callbacks. Credentials только0600; public OAuth research scope не даёт operator powers.
3. Проревьюить deployment-review.patch, миграцию двух DB, проверенные backup/restore, новую явную политику activation/complete. Зафиксировать отдельный approval на конкретные SHA/DB/service/config, затем подготовить одобренный installer. Текущее ТЗ approval не заменяет.
4. До approval публичный canary только read-only. После approval — только новый LM_QA_018_* namespace, без RH/FTL/SRT writes. Проверить hash-chain и отсутствие активных QA grants.
5. В ChatGPT после одобренного переноса изменить URL приложения на выбранный постоянный endpoint, переподключить OAuth и обновить перечень tools; проверить27 tools, research_cycle_next/history/source_contract. Сейчас переподключение не установит018: production всё ещё24.

## Rollback

Остановить приём новых предложений, owner reconcile, вернуть прежний service/config/feature flag, сохраняя текущие SQLite и всё append-only evidence. Проверить24 tools и цепочку; повторный rollout27 должен вернуть прежние receipts/history. Не подменять живую DB старым backup и не удалять экспериментальные события. Restore выполняется только на новом пути и сверяется до публикации файла; при mismatch — STOP_WITH_RCA.
''')
    (out / 'rollback-rehearsal.md').write_text('''# Staging rollback rehearsal

Фактически проверено HTTPS/OAuth27 → прежние24 → HTTPS/OAuth27 на том же private ledger. Canary LM_QA_018_CANARY записан только в private canonical; typed snapshots/history/receipts остались идентичными. Ни событие, ни journal/status/audit не удалены. После двух новых restore-paths committed history совпала через MCP. Fault matrix содержит фактические результаты; production rollback/rollout НЕ выполнялись.
''')
    (out / '019-handoff.md').write_text('''# Handoff019

Не считать018 разрешением развёртывания. R4/R5 production FAIL; сначала approval, production guards+restore и настоящий именованный HTTPS/OAuth ingress/canary. Пакет default-off, production0.4.2/24/schema5 не менялся.

На независимой машине/другим оператором проверить SHA, установить audited dependencies в чистое окружение, выполнить reproduce.sh на новом work path, сохранить реальные wire/costs/errors. Это отдельное доказательство R6. Same-machine replay018 его не заменяет.

R7: зарегистрировать реальный внешний источник через существующий source contract с точной provenance/правами/observer/version/bounds/definition/key pinning; тестировать все outcomes, expiry/nonce/replay/foreign scope. Не выдавать local computational fixtures за внешний источник или физическую аутентичность. Не вводить новый DSL/математические примитивы и не менять NO_GO004–017. Любой actual FAIL сохранять, STOP_WITH_RCA, минимальный патч и новый cohort.
''')
    (out / 'reproduce.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
TASK_PACKAGE=$(cd -- "$(dirname -- "$0")" && pwd)
TASK_PYTHON=${PYTHON:-python3}
exec "$TASK_PYTHON" "$TASK_PACKAGE/source/deploy018_reproduce.py" --package "$TASK_PACKAGE" --work "${1:?Specify a NEW private work directory}"
''')
    forbidden = [str(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.db', '.sqlite3', '.ed25519', '.pem') or p.name in ('owner-password', 'server.env'))]
    assert not forbidden, forbidden
    private_key_marker = b'-----BEGIN ' + b'PRIVATE KEY-----'
    # Match actual PEM material, not a scanner/source-code string literal.
    key_block = re.compile(re.escape(private_key_marker) + rb'\s*\n[A-Za-z0-9+/=\r\n]{32,}')
    assert not any(key_block.search(p.read_bytes()) for p in out.rglob('*') if p.is_file())
    secret_values = []
    for p in base.rglob('owner-password'):
        secret_values.append(p.read_bytes().strip())
    for p in base.rglob('*.ed25519'):
        secret_values.append(p.read_bytes().hex().encode())
    for p in base.rglob('oauth.sqlite3'):
        import sqlite3
        with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as c:
            for body, in c.execute("SELECT body FROM auth_records WHERE kind='client'"):
                value = json.loads(body).get('client_secret')
                if value:
                    secret_values.append(value.encode())
    assert not any(value in p.read_bytes() for p in out.rglob('*') if p.is_file() for value in secret_values if len(value) >= 20)
    write(out / 'capsule-security-scan.json', {'status': 'PASS', 'forbidden_credential_or_DB_files': [],
        'private_PEM_blocks': 0, 'known_QA_secrets_matched': 0, 'known_values_checked': len(secret_values),
        'scope': 'Private password/key hex/OAuth client secrets checked without logging their values; MCP wire never logs Authorization/token bodies.'})
    manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
    write(out / 'files-sha256.json', manifest)
    archive = out.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    return {'output': str(out), 'archive': str(archive), 'files': len(manifest) + 1, 'deployment': 'NOT_PERFORMED'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fault', type=Path, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(run(a.base, a.out, a.fault), ensure_ascii=False))
    except Exception as error:
        if a.out.exists():
            write(a.out / 'packaging-failure.json', {'status': 'STOP_WITH_RCA', 'G8': 'FAIL',
                'error': str(error), 'traceback': __import__('traceback').format_exc(), 'deployment': 'NOT_PERFORMED'})
        raise
