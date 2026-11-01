# ROBLOX-PRED-001

Изолированный пилот коммерческого прогноза аудитории Roblox-проектов. Реализована
обязательная итерация A приложенного ТЗ: аудит, типизированное хранилище, проверка
времени признаков, M0/M1 и воспроизводимый инженерный прогон.

**Текущий data gate: BLOCKED; научный вывод: INCONCLUSIVE.** Пользователь выбрал
аудит и перспективный протокол; собственных проектов и лицензированной истории
пока нет. Реальные метрики качества, выигрыш SOMA/SUTI и доходность не измерены.
[Отчёт](STAGE0_STAGE1_REPORT_RU.md) отделяет реальные наблюдения от синтетики.

## Установка

Из корня LivingMath, Python 3.11+ (приёмка выполнена на Python 3.13):

```bash
cd roblox-pred-001
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-test.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest -q
```

Для editable-установки нужны setuptools из lock-файла. Более простой режим
разработки: `python -m pip install -e '.[test]'`; версии при этом могут отличаться.
CatBoost — отдельная необязательная зависимость; испытан sklearn fallback
(RandomForest). Проверяемые зависимости и их хеши зафиксированы в lock-файле.
Ни сервер LivingMath, ни GPU, ни ключ API для smoke не нужны.

## Команды

Все команды ниже запускаются из `roblox-pred-001/`:

```bash
python scripts/audit_sources.py --config configs/protocol.yaml
python scripts/build_dataset.py --config configs/protocol.yaml
python scripts/run_baseline.py --config configs/protocol.yaml --smoke
python scripts/run_semantic.py --config configs/protocol.yaml --dry-run
python scripts/run_eval.py --config configs/protocol.yaml
python scripts/collect_snapshots.py --config configs/protocol.yaml
```

`audit_sources` воспроизводит **сохранённый** реальный аудит 2026-11-01 без сети.
`--live` проверяет права до запроса и сейчас отклоняется. `--smoke` создаёт
480 помеченных синтетических объектов, обучает M0/M1, проверяет метрики и сохраняет
результат во временный каталог; это проверка исполнения, не бизнес-оценка.
`--output /tmp/roblox-smoke-run` задаёт каталог явно. Повтор идентичного прогона
читает сохранённый результат; изменение данных/кода/конфига после freeze запрещено.

`run_semantic --dry-run` проверяет только контракт: native execution=false,
features/relations=null, статус UNSUPPORTED. Без подтверждённого native binding
реальный вызов отклоняется. Ни платных LLM-вызовов, ни суррогатного SUTI-парсера нет.

Реальные build/train/eval сейчас возвращают **exit 3** с конкретным data-gate
сообщением. Коллектор также возвращает 3: текущие права запрещают ML-сбор;
планировщик не установлен. Успешное исполнение и сохранённый аудит возвращают 0.

## Структура

- `src/roblox_pred/`: schemas, sources, storage, features, models, semantic, evaluation.
- `configs/`: протокол, бюджеты и реестр оснований использования источников.
- `scripts/`: шесть CLI из ТЗ; `tests/`: временные БД, фикстуры и граничные проверки.
- `docs/`: аудит, словарь, перспективный протокол, native capabilities и RCA.
- `reports/`: публичные агрегаты аудита и инженерной приёмки.
- `data/`: локальные captures, нормализованные записи, Parquet и DuckDB; вне Git.

## Как появится реальная оценка

Нужен документированно разрешённый для коммерческого ML источник с полным реестром
включения проектов, включая малоактивные, и доказуемыми версиями данных.
[Протокол](docs/PROSPECTIVE_PROTOCOL_RU.md) описывает регистрацию Pfirst, расписание,
дозревание горизонта и импорт. Одной галочки `ml_allowed` или доступного API
недостаточно. Не передавайте секретные ключи в чат.

Порог top-decile вычисляется только на train; split — по времени, с embargo 91 день
и разделением creator/universe/известных clone groups. Заполнение пропусков и
кодирование категорий обучаются только на train. Незавершённые outcomes не
превращаются в нули и не удаляются ради получения метрик. Калибровка, CI,
M2/S1/H1 и коммерческое решение — последующие этапы после data gate.
