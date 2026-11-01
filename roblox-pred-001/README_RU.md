# ROBLOX-PRED-001

Изолированный пилот коммерческого прогноза аудитории Roblox-проектов. Реализована
обязательная итерация A приложенного ТЗ: аудит, типизированное хранилище, проверка
времени признаков, M0/M1 и воспроизводимый инженерный прогон.

**Текущий режим — быстрая проверка на50 топ-играх.** Описание, дата создания как
прокси запуска, текущий онлайн и прокси активности уже собраны. Ежедневный timer
отключён по уточнению пользователя. [Данные и команда](docs/QUICK_CHECK_RU.md).

```bash
python scripts/quick_top.py --limit 50
```

Предыдущие аудиты и срезы сохранены; основной вход модели теперь —
`data/quick-top/<UTC>/model_input.jsonl`, таблица — `top_games.csv`.

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

Все команды ниже запускаются из `roblox-pred-001/`.

Работа с настоящими публичными данными:

```bash
python scripts/observe_market.py --config configs/public-observation.yaml
python scripts/collect_snapshots.py --config configs/public-observation.yaml
```

Первая команда открывает публичные каталоги четырёх создателей и сохраняет
`data/observations/<UTC>/projects.csv` с описаниями, статистикой и provenance.
Выборка ограничена50 ID; сейчас найдено15. Вторая обновляет фиксированный список
из `configs/public-frame.json` в `data/public-observation/research.duckdb` и Parquet.
Все raw ответы и БД остаются локально. Эта маленькая выборка не представляет
все проекты Roblox; три ранних ID — прежние transport controls, не новые релизы.

Ежедневный сбор (Linux/systemd):

```bash
python scripts/install_daily_timer.py
systemctl --user list-timers livingmath-roblox-observation.timer
journalctl --user -u livingmath-roblox-observation.service -n 20
```

Этот прежний timer сейчас отключён; включать его для быстрого теста не требуется. Для остановки:
`systemctl --user disable --now livingmath-roblox-observation.timer`.
Компьютер и user manager должны работать; пропущенный запуск выполняется при
следующей активации. Время реального capture сохраняется, catch-up не выдаётся
за снимок пропущенного часа. Поля revenue_robux/release_date не выдумываются.

Отдельно — аудит, инженерный smoke и будущий benchmark:

```bash
python scripts/audit_sources.py --config configs/protocol.yaml
python scripts/build_dataset.py --config configs/protocol.yaml
python scripts/run_baseline.py --config configs/protocol.yaml --smoke
python scripts/run_semantic.py --config configs/protocol.yaml --dry-run
python scripts/run_eval.py --config configs/protocol.yaml
python scripts/collect_snapshots.py --config configs/protocol.yaml
```

`audit_sources` воспроизводит **сохранённый** реальный аудит 2026-11-01 без сети.
`--live` выполняет ограниченный настоящий запрос официального Games API. `--smoke` создаёт
480 помеченных синтетических объектов, обучает M0/M1, проверяет метрики и сохраняет
результат во временный каталог; это проверка исполнения, не бизнес-оценка.
`--output /tmp/roblox-smoke-run` задаёт каталог явно. Повтор идентичного прогона
читает сохранённый результат; изменение данных/кода/конфига после freeze запрещено.

`run_semantic --dry-run` проверяет только контракт: native execution=false,
features/relations=null, статус UNSUPPORTED. Без подтверждённого native binding
реальный вызов отклоняется. Ни платных LLM-вызовов, ни суррогатного SUTI-парсера нет.

Реальные build/train/eval сейчас возвращают **exit 3** с конкретным data-gate
сообщением. Старый `protocol.yaml` сохраняет сбор выключенным; для наблюдения используйте
`public-observation.yaml`. Его коллектор работает и подключён к ежедневному timer. Успешное исполнение и сохранённый аудит возвращают 0.

## Структура

- `src/roblox_pred/`: schemas, sources, storage, features, models, semantic, evaluation.
- `configs/`: протокол, бюджеты и реестр оснований использования источников.
- `scripts/`: шесть CLI из ТЗ; `tests/`: временные БД, фикстуры и граничные проверки.
- `docs/`: аудит, словарь, перспективный протокол, native capabilities и RCA.
- `reports/`: публичные агрегаты аудита и инженерной приёмки.
- `data/`: локальные captures, нормализованные записи, Parquet и DuckDB; вне Git.

## Как появится реальная оценка

Для итогового benchmark нужны полная заранее определённая выборка, включая
малоактивные проекты, доказуемые версии признаков и будущие outcomes.
Публичные snapshots уже накапливаются; до дозревания горизонта это наблюдение,
а не проверка прогноза.
[Протокол](docs/PROSPECTIVE_PROTOCOL_RU.md) описывает регистрацию Pfirst, расписание,
дозревание горизонта и импорт. Scope flags фиксируют выбранный пользователем режим анализа; они не заменяют
проверку наличия фактических данных. Не передавайте секретные ключи в чат.

Порог top-decile вычисляется только на train; split — по времени, с embargo 91 день
и разделением creator/universe/известных clone groups. Заполнение пропусков и
кодирование категорий обучаются только на train. Незавершённые outcomes не
превращаются в нули и не удаляются ради получения метрик. Калибровка, CI,
M2/S1/H1 и коммерческое решение — последующие этапы после data gate.
