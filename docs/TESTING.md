# Тестирование

Из `live_math_mcp_prod/` в активированном окружении:

```bash
python -m pip install -r requirements-dav-dev.txt
python -m pytest -q
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

## v0.1 assurance package

From the repository root: `python -m pip install ".[test,mcp]"` then `python -m pytest -q tests`. Manual, model-free verification after installation: `lm-suti doctor --smoke`. The legacy server suite still runs from `live_math_mcp_prod/`. Public HTTPS/OAuth acceptance traces and external-human R3 pilot evidence are separate checks.
