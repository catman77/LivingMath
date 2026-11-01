# ROBLOX-PRED-001: отчёт Stage 0 / итерации A

> Исторический срез первого прогона (коммит777ec3e). После прямого указания
> пользователя общий запрет публичного API снят: получено15 проектов и включён
> ежедневный сбор. [Актуальный результат](docs/PUBLIC_API_REPORT_RU.md). Прежние наблюдения и FAIL сохранены.

**Дата:** 2026-11-01. **Поставка:** исполняемая итерация A реализована и проверена.
**Data gate: BLOCKED. Научный результат: INCONCLUSIVE.** Пользователь подтвердил,
что собственных Roblox-проектов и лицензированной истории пока нет, и выбрал
аудит с перспективным протоколом. Реальный предиктивный benchmark не проведён.

## Реальные наблюдения

Выполнены четыре ограниченных HTTP-запроса: два старых Swagger URL вернули404,
два документированных Games/creator-catalog контракта —200. Получены6 полных
записей игр и3 записи каталога,9 уникальных universe IDs. Срез данных — только
2026-11-01, примерно16:18 UTC. Три полных записи имеют текущий CCU0; это не
отрицательные90-дневные outcomes. Creation dates2013–2019 не являются historical
feature snapshots. Исторические версии и будущие outcomes — **0**; eligible ML
cohort — **0**. Raw responses сохранены приватно, SHA и квитанции опубликованы
в [data-audit.json](reports/data-audit.json).

[Актуальная документация Roblox](https://create.roblox.com/docs/cloud/reference/domains/games)
подтверждает использованные текущие контракты. Дальнейший автоматический ML-сбор
остановлен после проверки [Roblox Terms](https://en.help.roblox.com/hc/en-us/articles/115004647846-Roblox-Terms-of-Use).
Analytics требует отдельного правомерного доступа к universe; документация не
считается доступным нам датасетом. [Полный аудит и границы прав](docs/DATA_AUDIT_RU.md).
Планировщик, коммерческий скрейпинг и запросы к чужой приватной аналитике не запускались.

## Реализованная система

Отдельный `roblox-pred-001/` содержит Python package и шесть CLI из ТЗ. Game,
Snapshot, ConceptArtifact, Outcome, SemanticFeatures, Prediction и Run имеют
типизированные Arrow/DuckDB поля и полную модель. Parquet parts неизменяемы через
API, точный повтор не создаёт записи, конфликт payload отклоняется. На6 настоящих
API-записях отдельно проверены as-of construction, roundtrip и повтор без дублей;
они не использованы для ML.

Проверяются время каждой версии признака, source hashes, creator/clone dates,
известность train labels до следующего fold и horizon embargo91день. Текст не
датируется creation date. Unknown остаётся NULL. M0: random, train base-rate,
logistic; M1: sklearn RandomForest с train-only preprocessing. Backend CatBoost
предусмотрен отдельно, но не установлен и не испытан. Порог — train-only quantile0.9;
test не используется для настройки. Freeze включает protocol/data/code/dependency
hashes до обучения; точный повтор читает результат, изменение содержимого блокируется.

Неполные/censored данные сохраняются и останавливают оценку целой cohort; они не
удаляются ради красивых метрик. Неизвестные клоны автоматически не выявляются.
Это минимальная инженерная итерация, не завершённый промышленный benchmark.
[Словарь](docs/DATA_DICTIONARY_RU.md), [RCA](docs/RCA_RU.md).

## Приёмка и синтетический прогон

**50 pytest PASS, 0 FAIL, 0 SKIP; 17 инженерных acceptance checks PASS.**
Проверены leakage, missing/zero, duplicate IDs, неизменность лицензии/captures,
30 различных outcome days, межгрупповые ограничения, train-only imputation,
отсутствие outcome в semantic contract, source429 без повторов и CLI gates.
Ruff E9/F — PASS. [Полные команды, exit codes и версии](reports/acceptance.json).

Synthetic smoke:480 явно искусственных проектов; train240/validation120/test120;
960 prediction records, seed20261101. Полный отдельный CLI-процесс занял **1.588с**
на этом компьютере, значительно меньше5мин; время не обещается для любого железа.
Идентичный повтор вернул тот же результат без новых predictions. Числа качества
сохранены только в [synthetic-smoke.json](reports/synthetic-smoke.json) с областью
`SYNTHETIC_ENGINEERING_ONLY`; они не свидетельствуют о реальном прогнозе, SOMA
или доходности. Реальные quality/ROI metrics=null.

Проверенные команды из каталога пилота:

```bash
python -m pytest -q
python scripts/audit_sources.py --config configs/protocol.yaml
python scripts/run_baseline.py --config configs/protocol.yaml --smoke --output /tmp/roblox-pred-smoke
python scripts/run_semantic.py --config configs/protocol.yaml --dry-run
```

Реальные `build_dataset`, `run_baseline`, `run_eval`, `collect_snapshots` и
`audit_sources --live` ожидаемо возвращают exit3 с причиной блокировки. Semantic
без dry-run также отклоняется. Эти проверки подтверждают работу ограничений,
а не готовность коммерческого результата. Установка проверена в отдельном venv
с hash-locked dependencies и editable package; production environment не менялась.

## Настоящие SOMA / MCP возможности

Через существующий plugin выполнены3 вида read-only вызовов и повторный health
(всего4 вызова). Это не прямой tools/list. Доступная metadata содержит44 tools;
сервер также сообщает44. Version **1.2.0rc3-observer012**, deployment
**20261101T044526Z-observer012**. SQLite ok; до и после2058canonical events,
4817audit records, неизменный audit head
`c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50`.
Производственные данные не изменялись, model calls=0, native runs=0.

В локальном SOMA найден настоящий `SomaMarketAdapter` с пятью каналами и
predict_next/observe/probe_state. Проверены исходники и сигнатуры; исполнимость
native runtime в этой среде не испытана. Не определён Roblox mapping/readout.
Возможности source-graph LivingMath не переименованы в native predictor.
[Capability report](docs/SUTI_CAPABILITY_REPORT_RU.md) и [карточка автору005](../suti_author_proposals/005-native-prediction-binding/README.md)
сохраняют конкретный пробел и варианты решения; материалы никому не отправлены.

## Перспективный путь и следующий шаг

[Протокол Pfirst](docs/PROSPECTIVE_PROTOCOL_RU.md) фиксирует daily-slot target,
рамку включения, дозревание дней61–90, работу с пропусками и относительные folds.
Общий последовательный дизайн займёт примерно393дня от первого разрешённого
снимка. Сейчас дата старта не выдумана, сбор выключен. M2/S1/H1, CI, калибровка и
экономическое решение отложены до прохождения gate, их результаты не синтезированы.

**Самое полезное следующее действие:** получить документированно разрешённую для
ML агрегированную историческую выгрузку с полной cohort, timestamps версий и
future observations. Это быстрее проверит коммерческую гипотезу, чем ожидание
полного перспективного дизайна. [result.json](reports/result.json) фиксирует статус.

Исходный [архив ТЗ](../docs/ROBLOX_PRED_001_STARTER.zip) скопирован без изменения;
SHA256 `58d28cb4265185d1b2fef61c9056ec35ffeed2e3dc58f79ed8d5ed936bc1d9ff`.
Корневой AGENTS.md сохранён. Код LivingMath и рабочая SQLite не менялись.
Приватные raw/логи/БД/model outputs исключены из Git; локальный commit сообщён
в итоговом ответе. Автоматическая публикация или production deployment не выполнялись.
