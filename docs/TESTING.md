# Тестирование

## Актуальный пакет v0.4.9

Из корня checkout после установки `python -m pip install '.[white-star,mcp,test]'`:

```bash
lm-suti white-star prepare
python -m pytest -q tests
lm-suti doctor --smoke
```

Symbolic/White Star тестам нужны Linux, Landlock и подготовленное native ядро.
Проверяются полный токенный carrier, primitive traces и source spans, SP-checker,
train/query isolation, независимый observer verifier, поддельные сертификаты,
идемпотентность и ablation реальных родителей. Один только `.[test,mcp]`
не устанавливает NumPy/pandas для численных тестов.

Для DYCK006: **409 source PASS,409 installed-wheel PASS**,1066 legacy PASS/20 прежних SKIP,
24 supplied reference PASS. На стенде и публичном HTTPS/OAuth endpoint прошли
333 role +41 edge +8547 continuation +943 regression +916 generator checks.
Всего10780 проверок на каждом endpoint;943 включает320 явно локальных
supplied-AST controls, не серверное открытие. Все31 прежний A/B gate PASS.
[Точная матрица и счётчики MCP](symbolic-v1/dyck006/acceptance_matrix.json).

`tests/test_role006.py` проверяет84→256, независимое двухветвевое дерево,
исчерпывающий отрицательный DP, подделки, роли/Unicode, covariance/NF, UNKNOWN,
реальный fork worker и недоверие producer scalar. `tools/role006_mcp_qa.py`
проводит baseline/accept/edges/continuations через настоящий MCP SDK и OAuth.
Положительные/отрицательные labels golden набора читаются после inference.
В P1 группируются реальные множества продолжений, не вычисленная высота.
Прежние `recursive_observer_mcp_qa.py` и `generator005_mcp_qa.py` повторены.
Клиентский retry018_RESOURCE_BUSY не меняет worker/HTTP caps; другие ошибки
не маскируются. Полные трассы, исходные RED/failed harness logs и offline
REPLAY_MATCH входят в ZIP релиза. GitHub CI оценивается отдельно.

## Formal Bridge001

430 source PASS и430 installed-wheel PASS (последний с отключённым pytest
pythonpath, вне checkout).1066 legacy PASS/20 прежних SKIP,225 supplied reference
assertions/9450 membership comparisons.21 targeted tests включают nullable start,
ambiguous forest, cycles/negative completeness, forged proofs, source types,
canonical DFA, long prefix trie, total synthesis budget и FOL assumptions.

`tools/formal001_fixture.py` сохраняет original8 cases и enriched query-only
наборы, external gold и отдельный short-query annotation holder. Основная SDK/OAuth
приёмка — `formal001_mcp_qa.py`; `formal001_controlled_qa.py` проверяет25 ручных
source-aligned proposals и50 model evaluations. Ручные proposals не являются NLP
accuracy. `formal001_report_scope.py` отдельно считает seen/unseen words: в `(ab)+`
ε уже был размечен и не входит в130 новых query words.

Прежние пять SDK suite повторяются через --allow-formal-api: исключаются ровно8
известных additive имён, а83 старых схемы продолжают сравниваться полностью.
Новые8 схем отдельно проверяет formal suite; неизвестные additions не скрываются.
Стенд:12102 проверки; production:12103 проверки (включая aux), исходные неуспешные попытки и2 pre-active
FP сохранены. GitHub Actions оценивается отдельно от local/installed/live evidence.

## Legacy тесты

Из `live_math_mcp_prod/` в активированном окружении:

```bash
python -m pip install -r requirements-dav-dev.txt
PYTHONPATH=.:../src python -m pytest -q .
```

Основной framework — pytest; ledger также содержит `unittest.TestCase`.
Тесты используют временные SQLite. Локально установленные `z3-solver`, Ruff и
mypy добавляются через `requirements-dav-dev.txt`; lock019 уже содержит pytest.

Проверки по слоям:

- Ledger/lifecycle: миграции, idempotency, project isolation, result/evidence,
  отдельные активации и append-only hash-chain.
- DAV/semantic pipeline: конечные модели и контрпримеры, точные цитаты,
  source binding, UNKNOWN/negative/quoted/asserted различия.
- `test_checkout_install.py`: установка без авторских архивов, сохранение
  существующего экземпляра, права файлов, проверка SHA и недопустимых origin.
- `test_meaning_pivot014.py`: неизменная A0, ограниченный repair, содержательные
  различия, отсутствие автоматического source verification.
- `unified_system.local smoke`: настоящий HTTPS/OAuth SDK-клиент, tools/list
  и read-only вызовы. Unit-тесты не заменяют эту проверку.

Исторические signed-release тесты требуют оригинальных закрытых пакетов,
которые не входят в Git; существующие явные SKIP сохраняются. Для015/016
включены точные исходные файлы с SHA-256, без замены математических определений.
Для Bridge/ALCH используется проверенный исходный bundle в `assets/unified/`.
Дополнительные фиксированные входы перечислены в
`assets/test-fixtures.manifest.json`. Единственный исходный baseline ZIP в этом
наборе необходим проверке первоначального SourceVault freeze; не пересобирайте
его и не сокращайте manifest ради нового PASS.

Обычный pytest не вызывает LLM и не открывает production-базы. Live inference,
полный исследовательский replay и ручная проверка подключения в ChatGPT —
отдельные проверки; их нельзя объявлять прошедшими по результату pytest.

Имена файлов — `test_*.py`, функций — `test_<behavior>`. Проверяйте наблюдаемое
поведение и отрицательные границы. При изменении persistence обязательно
покройте миграцию, повтор запроса, изоляцию проектов и сохранение истории.
Порог покрытия в проекте не установлен.

Формальное прохождение теста не является верификацией источниковой интерпретации.
Научные отрицательные результаты сохраняйте отдельно от инженерного PASS.

## GitHub Actions

`.github/workflows/assurance-v01.yml` устанавливает `white-star` extra и запускает
**все** `tests/` на Python 3.13 без исключений и `continue-on-error`.
Отдельный Python 3.14 job проверяет `test_release.py`, `test_semantic_bridge.py`
и doctor smoke; он не заявляет проверку численного backend на 3.14.
Зафиксированный pandas 2.2.3 имеет готовые cp313 wheels, но не cp314; версия
production dependency ради CI не меняется. Старый `.github/workflows/test.yml`
проверяет legacy с `PYTHONPATH=.:../src` для дочерних процессов.

## Проверка MCP-интерфейса

`unified_system.local smoke` проверяет 44 метода своего legacy стенда.
Для полной установки `tools/context_promotion_mcp_qa.py`,
`tools/symbolic_patch003_acceptance_qa.py` и
`tools/symbolic_patch001_mcp_qa.py` используют настоящий SDK/OAuth; параметры
уточняются через `--help`. Эти runner создают QA-объекты и требуют доступа
владельца; они не являются read-only health check.
Точную текущую схему читайте через [tools/list](MCP_INTERFACE.md).
При заполненной client-registration quota QA поддерживает
`LIVINGMATH_QA_CLIENT_FILE` с существующим owner-only mode600 OAuth client JSON;
токены/пароли не выводятся и не публикуются. Защитные лимиты сервера не меняются.
