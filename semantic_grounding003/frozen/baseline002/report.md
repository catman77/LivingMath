INSUFFICIENT_SEMANTIC_EVIDENCE

# ARTIFACT-GENESIS-002 — отчёт

Научный G3 остаётся **FAIL**. Software PASS и совпадение грамматического шаблона не объявляются новым источниковым законом. Интеграция — **STAGING_ONLY**; production не менялся.

## Что изменено

Добавлен отдельный небольшой `artifact_genesis/`; прежние DAV core, ARTIFACT-TRANSLATION-001, источники, scripts, FAIL/RCA и рабочие базы сохранены. 001 независимо воспроизведён из прежнего ZIP: G3 снова `FAIL_NO_NEW_STRUCTURAL_TRANSFER`.

Новый proposer получает **сырые строки**, точные байтовые адреса, edition/hash и разрешённый контекст. В packet нет редакторских SourceGraph/B-relations, target graphs или expected labels. Такие поля запрещены также внутри metadata/grammar. Изолированный процесс реально отклоняет файловую и socket-пробы; не импортирует source checker, прежний генератор или DAV evaluator.

Доступного интерфейса с pinned LLM/model/token accounting для этого эксперимента нет: `NO_LLM_SEMANTIC_PROPOSER`, B3 `NOT_RUN`. Реализован ограниченный грамматический extractor, не универсальная модель понимания. Новые H содержат цитаты, адресованные роли/события, аргумент, опровержимое прочтение и альтернативу. Независимый source proxy работает **до** target binding и не принимает target proof как подтверждение смысла.

## Freeze и независимость

[Source freeze](source-freeze.json) создан до semantic generator. Сохранены прежние Ripley/Pushkin edition и train/holdout: Gates 1/3 и первые восемь строк «Тучи» — обучение; Gates 5/8 и последние четыре строки — challenge; Gate6 — отдельный отрицательный контроль. Закрытые ALCH005 passages/key не открывались.

H и source-прогнозы запечатаны до выдачи heldout packets. Доступ до seal и подмена seal отвергаются. После reveal работает отдельный process checker без proposer/target imports. Публичный текст был известен coding agent и мог встречаться LLM; это **engineering holdout**, не проспективно независимое исследование. Отладочные cohorts не считаются независимыми повторными научными испытаниями.

## Фактический результат

- 4 train packets → **20 исходных H**, не менее двух альтернатив на каждый packet. **10** поддержаны ограниченным source proxy, остальные требуют review.
- Проверены порядок текста/процесса, отрицание/смена субъекта, co-predication и параллельные словесные frames с проверкой обратных адресов. Сходство frames не принимается за тождество референтов.
- **2 содержательных ремонта binding**: actual DAV countermodel P=1,Q=0 отвергает необходимость, навязанную совместной предикации. Направленный переход заменён совместным символическим guard; исходные H, модели и counterexample сохранены append-only.
- До reveal зафиксированы **4 source-прогноза C** и все ablation-прогнозы B2. Для C выполнено **7** проверок: **3 PROXY_MATCH**, 3 FAIL_NO_SOURCE_MATCH, 1 REQUIRES_SEMANTIC_REVIEW.
- Новый независимый источниковый закон: **0**. Статус всех смысловых результатов — `SEMANTIC_NOT_EXTERNALLY_REVIEWED`.

Прогноз отрицательной предпосылки получил локальное свидетельство на Gate5; прогноз противопоставленных способов с порядком — на Gate8; грамматическая смена субъекта/объекта — в последней строфе. Это экземпляры ограниченных грамматических схем, не доказательство нового переносимого смысла. Для прогноза обратного преобразования ролей найдены `first/then`, но равенства между четырьмя ролями независимо не установлены.

## Где цикл обрывается

Замкнуты raw proposal → source critique → DAV counterexample → binding revision → source precommit → independent heldout challenge. Не замкнут переход **«адресованная грамматическая схема → независимое новое семантическое отношение, отличимое от шаблона/rename»**. Hash подтверждает байты, а конечный `proved` — модель. Ни один не устанавливает референт, смысловую инверсию или физическую причинность.

| Статус | Что действительно получено |
| --- | --- |
| Математически построено | Конечные symbolic networks, реальные countermodels, проверка удаления предпосылки на том же domain |
| Экспериментально обнаружено | 3 грамматических proxy-совпадения на отложенных публичных отрывках |
| Физически интерпретировано | Не установлено; chemical identity, rate laws, ODE, психологические эффекты и F остаются UNKNOWN |

## Baselines и проверки

B0 действительно извлекает буквальные события; B1 — неизменённый 001 с привилегированными редакторскими графами и воспроизведённым G3 FAIL. B2 выполняет те же raw/source/target trials без ремонта и сохраняет неподтверждённую необходимость; C отказывается от неё. Сравнение B1 не называется полностью matched: априорные входы различны. Число формул не является метрикой победы; научного превосходства C не установлено.

**19 adversarial/calibration controls PASS**: порядок, negation, subject, alpha rename, shuffle, duplicate evidence, fake quote/hash/edition, hidden/cross-source access, source/target separation, prompt injection as data, no-premise и независимая target topology. Синтетический положительный transfer и essential-premise counterexample отделены от Ripley/Pushkin. `FAIL_VACUOUS_LAW` для пустой предпосылки и независимых команд — ожидаемое отклонение, не научный PASS.

Полный pytest: **780 PASS, 12 SKIP**, включая 13 новых тестов; неизменённые golden 7/7. Пропуски старых authorization/signed019 fixtures не объявлены PASS. Ruff F/E9 и mypy проходят. Существующее Starlette deprecation warning сохранено.

Реальный OAuth MCP на приватных BackupAPI-копиях: **42 PASS, 25 вызовов**. Использованы только существующие методы, actual registered IDs, scoped finite evidence и unverified source events. Проверены repeated keys, запрет `verified`, foreign project/parent и полная hash-chain. Новые методы в production не установлены. [MCP trace](mcp-wire.jsonl), [целостность](integrity.json), [RCA](RCA.md).

## Воспроизведение

В корне чистой распаковки выдаваемого ZIP:

```bash
LM_AG_REPLAY_PYTHON=/path/to/pinned/python bash reproduce.sh /new/private/output
```

Replay проверяет SHA, отдельно воспроизводит неизменённый 001, выполняет старые/новые целевые регрессии, новый raw experiment и реальный private OAuth MCP. При повторе должны совпасть H, роли/цитаты, revisions, прогнозы и результаты; измеренные resource metrics сравниваются отдельно. Append-only journal каждой новой сессии проверяется независимо: его execution hashes могут различаться из-за измерений. Результат чистого запуска фиксируется receipt, а точный финальный ZIP проверяется отдельно перед выдачей.

Чистая распаковка проверена: **PASS_CLEAN_EXTRACTED_GENESIS_REPLAY**, 62 целевые регрессии, повторные 42 MCP проверки и совпадение 10 scientific hashes. [Receipt](clean-extraction-receipt.json) относится к предварительному ZIP; [финальный receipt](final-replay-receipt.json) фиксирует SHA выдаваемого архива и его отдельный запуск. Финальный receipt и `final-manifest.json` исключены из ZIP, чтобы избежать циклических хешей; они выдаются рядом с архивом. Полная проверка рабочей копии — 780 PASS, 12 SKIP.
