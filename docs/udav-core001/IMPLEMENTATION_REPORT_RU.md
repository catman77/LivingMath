# UDAV Core PATCH001: инженерная приёмка

**PASS: P0/P1/P2 и все G0–G8.** Установлен `v0.4.12-developer-preview`,
`udav-core001-20261108T170545Z`. Публичный MCP `https://difficulty-nightlife-rca-missions.trycloudflare.com/mcp`,98 инструментов,
без аутентификации; прежний адрес и процесс туннеля сохранены.
[Матрица](TEST_MATRIX.json), [исходные SHA](PROVENANCE.json), [реальные run IDs](LIVE_RUNS.json).
Git baseline `e2bc20b`; точный source commit записан в PACKAGE_CONTENTS.json
релизного ZIP и в Git tag `v0.4.12-developer-preview`.

## Что изменено

P0: отдельный `udav_symbolic_explore` использует настоящие SymbolicState/History
и ленивые конечные `(node,operator,parameter)` cursors. Все части SPLIT доступны
дальше; расписание не зависит от порядка массива operators. Группы равных слов
влияют на очередь, но не склеивают source/history. В word identity наблюдаемые
выходы сохраняют собственные spans даже при повторном использовании node.

P1: raw witness SHA и явно объявленные structural quotient классы считаются
раздельно. Без structural observer — null/STRUCTURAL_NOVELTY_UNDEFINED.
Сохраняются причины выбора, DAG, границы и неполнота; sampled mapping family
помечается ARGUMENT_FAMILY_PARTIAL, глобальное исчерпание не заявляется.

P2: `white_star_explore_v2` требует явный `cat_distinction_tiebreak_v1`.
Реальный selector обновляет собственные graph/signature/phase/view/pair counters
на каждом шаге. Primary graph novelty всегда первый, новое однозначное
source-ID различие второе; последующие критерии прежние. Все aliases сохранены;
неоднозначность не назначается первой попавшейся паре и не закрывает все варианты.
WhiteStarOrbit, native и legacy symbolic/white_star не изменены.

## Измерения

| Проверка | Итог |
|---|---|
| Исходный suite до изменений |468 PASS|
| Установленный0.4.12 wheel |485 PASS,17 новых тестов|
| Полный legacy suite с оригинальной policy |1066 PASS/20 исторических SKIP|
| Reference tests из ТЗ |5 PASS|
| Реальные public symbolic проверки |490 PASS|
| Реальные public numeric проверки |1436 PASS|
| Дополнительный public контракт/экспорт |6 PASS|
| SPLIT119…124, прежние бюджеты72 applies |22/22 на каждом seed|
| Старые native21/22 ×k3/8 ×24 |96/96 view совпадений|
| Исторические owned runs |19/19 полных result SHA REPLAY_MATCH|
| Known quadratic23…52, k8/24 |22.633333333333333/28 против16.9/28|
| Новые геометрии:3 ×5 seeds |15/15 primary/replay/alias контролей|
| Независимая реконструкция numerical |55 260 candidate/state/hash проверок PASS|

Таблица всех45 парных прогонов: [JSON](RESULTS_TABLE.json), [CSV](RESULTS_TABLE.csv).
Реальные CPU/wall/RSS обоих arms: [RESOURCE_MEASUREMENTS.json](RESOURCE_MEASUREMENTS.json).
Сохранены5 CPU sec/6 wall sec/512MiB и общие квоты2active/16queued на engine.
Короткие node/token/CPU бюджеты дают явный частичный результат с provenance.
Нулевая продолжительность — валидный старый контракт, а не ошибка API.

## Данные, установка и воспроизведение

До изменений — полный архив103656 файлов Workspace и4 SQLite backup; во время
остановленного HTTP — второй согласованный snapshot и delta-overlay. Все
исходные bytes/rows, inode/path и journal hash-prefix сохранены; canonical audit
по-прежнему4817 записей с прежним head. [Проверка](PRODUCTION_INTEGRITY.json),
[откат](ROLLBACK_RU.md), [точные MCP вызовы](QUICKSTART_RU.md).
Стендовые проекты не импортировались в production. Публичные QA-проекты отдельные.
Неизменённый оригинальный AGENTS.md сохранён. Пользовательские87 правок вне задачи
не включаются и не перезаписываются.

Единый GitHub release ZIP содержит код, binary Git diff, wheel, входное ТЗ,
полные реальные request/response/wire, сохранённые неуспешные попытки, отчёты,
контрольные bundles, SHA-манифест и скрипты воспроизведения. Две реальные
экспортированные задачи воспроизвелись standalone CLI без модели/сети.
Большие трассы могут храниться в byte-exact gzip; RAW_GZIP_MAP.json связывает
SHA исходных байтов. Секреты, production базы и приватные approvals исключены.

## Точные границы вывода

Измерено инженерное покрытие на конечных synthetic входах. Known30-seed корпус
заранее известен: это regression, не blind научное открытие. Новые геометрии
проверяют сохранение primary и корректность aliases, не смысловую точность.
Число exact pairs включает определённую CAT-пару при нулевом witness direction
для сопоставимости с исходным контролем; nonzero counts вынесены отдельно.
Источник координат и source_relations остаются DECLARED, execution_permission=false.
Нет SEMANTICALLY_VERIFIED, универсального охвата, новых законов или физического
утверждения. Независимая human semantic/R3 приёмка остаётся невыполненной.
CPU-bound остановка зависит от реально затраченного CPU: повтор может отсечься
в другой позиции и тогда вернёт REPLAY_MISMATCH, а не ложное подтверждение.
