# PATCH003 acceptance follow-up — результат

Установлен **v0.4.4-developer-preview**, deployment `symbolic-patch003-acceptance-20261106T010226Z`, по прежнему адресу https://fares-september-rebel-board.trycloudflare.com/mcp. Публикуются **83 инструмента**; все82 прежних input/output schemas и annotations сохранены. Добавлен `white_star_symbolic_observer_verify`. Обновите список инструментов ChatGPT переподключением LivingMath по тому же адресу.

## Приёмка FIX-A/B/C

| Проверка | Результат | Свидетельства |
|---|---|---|
| FIX-A: предпосылки частичного комплекса | PASS | FIX_A.json; новые N6 bigons/diamonds, N10 none |
| FIX-B: действительно выведенный, использованный наблюдатель | PASS в конечном классе задач | FIX_B_FEATURE.json, FIX_B_VERIFIER.json |
| Запрет builtin pair_0 и вычисления скрытых зависимостей | PASS | allowlist derived:*; unit запрещает builtin-калькулятор во всём fit/predict |
| Замороженный holdout против ablation | PASS | 256/256 против128/256 на тех же данных/бюджетах |
| Испорченные AST/output hash/operator/source span | REJECTED / PASS | реальные MCP ответы в FIX_B_REJECTIONS.json |
| FIX-C:942 пары/1884 варианта, дерево источников | PASS | CORPUS_SOURCE_TREE_MANIFEST.json; полный31MiB JSON в evidence ZIP |
| Равные splits и ресурсы пяти primary baselines | PASS | CORPUS_RESOURCE_FAIRNESS.json |
| Все19 прогонов независимой приёмки | Сохранены без изменений | входящий RUN_IDS.json; production transcript |
| Replay старого PATCH003 | REPLAY_MATCH | установленные неизменяемые профили, общий предел2 jobs |

FIX-A меняет только сводку: `all_local_peaks_filled` появляется лишь при checked missing_peaks=0; возвращаются `selected_cells_policy`, `unresolved_peaks`, `partial_attachment`. N6 bigons:32 незаполненных пика; diamonds:48; N10 none:3360. Во всех трёх π₁ NOT_PROVED. Исторические сохранённые сводки не переписаны: для исправленного вычисления нужен новый request_key. Сам SP builder, независимый checker и численный код не переопределялись.

## Что именно получилось в P1

До inference зафиксирован класс: второй токен равен предпоследнему. Обучение — все64 бинарных слова длины6, heldout — все256 слов длины8; IDs — SHA текста, множества не пересекаются. Целевые метки вычисляет внешний оценщик; сервер получает queries без accepted. Ни название языка, ни целевой offset не передаются в request.

Неизменённый генератор существующих AST выбирает из train `aligned_token_equality(offset=1,expected_equal=true)`. Новый feature **`derived_216159a6476fd2d9dad6`**, origin DERIVED_FROM_OPERATORS, execution_verified=true, реально входит в used_feature_ids. На прогнозе выполняются настоящие REVERSE/SPLIT; pair_0_max/min/final и все builtin значения исключены. Листинг реестра теперь декларативный и не вычисляет даже первый пример.

Полные64 source witnesses сохраняют AST, исходные UTF-8 spans, content-addressed input/output states и шаги. Отдельный verifier не импортирует trace producer или grammar.relation_value; проверяет source bytes, все состояния, операторы, выходные хеши и readout. Проверки сохраняются и под Python -O. Через реальный MCP испорченные свидетельства отвергнуты, а замороженный model digest не изменился.

Heldout: TP128/TN128/FP0/FN0; ablation derive_relations=false:128 верных из256 (постоянный прогноз). Смена builtin-калькулятора на функцию, немедленно падающую при вызове, не нарушает operator-only fit/predict. Это **конечная конструктивная демонстрация** композиции заранее существующего семейства AST; новый fundamental operator, универсальный invariant, уникальная грамматика и open-ended learning не заявляются. execution_verified относится к вычислительным свидетельствам, не к математическому статусу verified.

## Корпус и границы вывода

Проверены19 исходных immutable source chunks и942 основных катрена: I–VIII —1484 train records, IX–X —400 queries. Сохранены смешанная редакция, аномалии и исходная кодировка. Для каждого оригинала/swap2↔3 проверены pair_id, byte spans, source SHA, edition/rights и независимая per-variant alpha-канонизация.

Внутри предъявления сегмент century является **проекцией на один катрен**, а не полным текстом центурии. Новый воспроизводимый harness строит настоящее глобальное дерево century→quatrain→variant→line→word с19 исходными блоками. Каждое слово переставленного варианта связано с точным фрагментом оригинального блока. В этой проверке внешние holdout-метки вообще не открываются.

Все13 конфигураций повторены локально и через публичный MCP. Primary global_alpha/local_alpha/punctuation/length/majority используют одни и те же inputs, seed и budgets, без исключений. Условный и строгий conflict controls отделены и не подменяют основной опыт.

| Вариант | Победы | Поражения | Ничьи | NOT_IDENTIFIABLE | UNDERDETERMINED |
|---|---:|---:|---:|---:|---:|
| global_alpha | 0 | 1 | 183 | 16 | 0 |
| local_alpha | 8 | 4 | 132 | 56 | 0 |
| literal | 8 | 4 | 188 | 0 | 0 |
| punctuation | 77 | 28 | 0 | 95 | 0 |
| length | 8 | 4 | 127 | 61 | 0 |
| majority | 0 | 0 | 200 | 0 | 0 |
| no_builtin_attempt | 0 | 0 | 184 | 16 | 0 |
| strict_global_alpha | 0 | 0 | 0 | 16 | 184 |
| conditional_global_alpha | 0 | 1 | 183 | 16 | 0 |
| renaming_control | 0 | 1 | 183 | 16 | 0 |
| boundary_control | 0 | 1 | 183 | 16 | 0 |
| provenance_control | 0 | 1 | 183 | 16 | 0 |
| seed_control | 9 | 10 | 165 | 16 | 0 |

Преимущество global-alpha на задаче перестановки **не подтверждено**. Это прежний честный отрицательный результат, сохранённый после исправлений; положительный синтетический P1-тест не переносится автоматически на французские тексты. Ничьи/неидентифицируемые пары не считаются успешными предпочтениями. Перестановка строк — синтетическая метка, не семантическое отрицание.

## Проверки и эксплуатация

12 исходных reference tests,302 baseline tests, затем320 source и320 installed-wheel tests PASS. Полный legacy:1066 PASS/20 SKIPPED. Production через настоящий публичный HTTPS/OAuth MCP-клиент: **149 followup +769 PATCH003 +253 legacy PASS**. Полные запросы/ответы и wire сохранены в ZIP. Итоговые PID туннеля и URL прежние; перезапускался только HTTP-сервис.

До замены выполнены online и quiescent backups4 SQLite. Исследовательские строки,16118 initial files,16767 cutover files, immutable runs и hash-chain сохранены; SQLite4/4 ok. Истекающие OAuth sessions меняются штатно; обе исходные резервные копии сохранены. Никаких grants или mathematical verified не присвоено. Численный White Star, frozen core, symbolic_v1 и SP checker совпадают по SHA. Исторический extension binding исполняется в старом установленном hash-bound worker, не кодом из ZIP; квота общая2 active/16 queued, CPU5s/wall6s/RAM512MiB.

Код `cb0dcb01732fac274ee881d60948911ec5903288`; wheel SHA256 `18d8591bb5bfe94a4a5ecffa20ee8c1d727c879ced1c6a2ba59c62316c8e1967`; runtime manifest `8ac9d64f3d50ce480a5cae44f8e469a64cdac32de181f5e0dd3a37dcbb36bd0e`. Точные примеры — api_examples.json, run IDs — run_ids_and_replay_refs.json, результаты — acceptance_matrix.json и result.json. Архив задания сохранён без изменения в docs.

Ограничения: конечный empirical observer, общий semantic transfer NOT_SUPPORTED, внешний окончательный release sign-off не заявлен, R3 остаётся PENDING и native SUTI NOT_EXECUTED. Полный pentest/hosted CI не проводились.
