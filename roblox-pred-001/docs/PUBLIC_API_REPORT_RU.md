# Публичный API: рабочий результат

> Исторический режим наблюдения. Сейчас по уточнению пользователя используется
> [быстрый срез50 топ-игр](QUICK_CHECK_RU.md); ежедневный timer отключён.

Дата: 2026-11-01. **Сбор работает.** Общая блокировка публичного API в первой
версии была чрезмерной; после уточнения пользователя она заменена обычным
режимом публичного наблюдения и анализа. Никакого отдельного разрешения на каждый
документированный GET этот режим не требует. Исходный отчёт коммита777ec3e сохранён.

## Что получено

Через официальные Games API выполнены7 HTTP-запросов без ключей/cookie и повторов:
четыре каталога создателей, первая партия карточек и ещё два capture того же списка.
Проверены портфолио Gamer Robot Inc, Uplift Games, ROLVe и аккаунта Roblox.
В выборку также входят три прежних transport ID. Это ограниченная наблюдаемая
группа, не перечень всех выпусков Roblox.

Получено **15 проектов**, **45 версионных snapshots**. У10 карточек непустые
описания; в первом capture7 проектов имели CCU0. Raw ответы, descriptions,
Parquet и DuckDB сохранены локально. CSV: `roblox-pred-001/data/observations/20261101T171355069471Z/projects.csv`.

| Проект | Universe ID | CCU первого снимка | Visits накопленные | Жанр API |
|---|---:|---:|---:|---|
| test103120131046am's Place | 1 | 0 | 0 | All |
| ZZZZZZZZZ---   | 2 | 0 | 138 | All |
| W1Test10312013e's Place | 3 | 0 | 58 | All |
| Crossroads | 13058 | 28 | 39844474 | Fighting |
| Rocket Arena | 246424 | 14 | 16616555 | Fighting |
| Chaos Canyon | 295594 | 9 | 12134668 | Fighting |
| Arsenal | 111958650 | 3572 | 6325238909 | Fighting |
| Unit 1968 | 327709123 | 9 | 52440814 | FPS |
| [1.2X🎃] Adopt Me! | 383310974 | 300982 | 45288728192 | RPG |
| [🎃] Blox Fruits | 994732206 | 579806 | 65203319139 | Adventure |
| Unit: Classified (Inactive) | 1392301017 | 0 | 10214326 | All |
| Arsenal Skin Maker | 1468394780 | 0 | 808110 | All |
| Right 2 Fight (Inactive) | 3139902823 | 53 | 92195564 | Fighting |
| The Last Resort | 5351946502 | 0 | 28715 | All |
| r0 | 6731755890 | 0 | 85513 | All |

Метрики таблицы относятся к2026-11-01T17:14:01.808176Z; точные времена повторов,
receipt SHA и source URLs — в [машиночитаемом результате](../reports/public-api-observation.json).
Описания лежат в CSV; заголовок, описание и жанр не выданы за результат native SUTI.

## Доход и даты запуска

[Публичный Games API](https://create.roblox.com/docs/cloud/reference/domains/games)
даёт метаданные и статистику проектов. В проверенных ответах нет фактической
выручки. [Monetization Analytics](https://create.roblox.com/docs/production/analytics/monetization)
показывает её владельцу/пользователю с правами аналитики. Поэтому revenue_robux=NULL,
status=OWNER_ANALYTICS_REQUIRED_NOT_PUBLIC. Это отсутствие конкретного поля,
а не запрет исследовать остальные сведения. Visits/CCU не переименованы в Robux.
Публичные финансовые раскрытия авторов можно добавлять отдельными dated sources;
оценки дохода должны оставаться estimates. Сейчас финансовых оценок не сделано.

В API есть creation_date; она не доказывает первый публичный релиз. Поле
release_date остаётся пустым, неизвестность не превращается в выдуманную дату.

## Ежедневный сбор

На текущем компьютере установлен и включён user timer
`livingmath-roblox-observation.timer`: каждый день18:00 UTC /21:00 Москва,
один ограниченный запрос по фиксированным15 IDs. Linger=yes. Настоящий service
прогнан: Result=success, ExecMainStatus=0. На выключенном компьютере сетевой сбор
не выполняется; Persistent catch-up фиксирует настоящее время после включения.
Конфигурация — `configs/public-observation.yaml`, список — `configs/public-frame.json`.

```bash
python scripts/observe_market.py --config configs/public-observation.yaml
python scripts/collect_snapshots.py --config configs/public-observation.yaml
systemctl --user list-timers livingmath-roblox-observation.timer
```

Отключение: `systemctl --user disable --now livingmath-roblox-observation.timer`.
Данные лежат в `data/public-observation/`, не в production SQLite LivingMath.
История будущих outcomes ещё не накоплена; предиктивная проверка остаётся pending.

## Проверка и сохранённая ошибка

При первой проверке unit обнаружен дефект установщика: resolve() разыменовал
ссылку Python из venv в базовый интерпретатор, и import roblox_pred завершился
ошибкой до сетевого запроса. Дефект исправлен, добавлен regression dry-run с
реальным запуском выбранного Python и импортом пакета. Для oneshot установлен
TimeoutStartSec=90 вместо игнорируемого RuntimeMaxSec. Первый FAIL сохранён в
journal и машинном отчёте; исправленный service действительно завершился успешно.

Новых LLM/native-прогонов нет; действующий MCP и его SQLite не менялись.
Новый синтетический smoke проверяет только исполнение кода, не доходность.

Итог: **56 pytest PASS,0 FAIL; Ruff E9/F PASS; synthetic smoke ENGINEERING_PASS**.
