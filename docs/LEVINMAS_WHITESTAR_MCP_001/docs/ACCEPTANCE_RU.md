# Матрица приёмки

Локальные доказательства текущей поставки — verification/. Пункты MCP/SUTI/production ниже являются работой исполнителя, а не уже пройденными проверками.

| ID | Проверка | Ожидаемый результат |
|---|---|---|
| A01 | SHA 75 файлов code/ и исходного kernel | Полное совпадение с поставкой 003 |
| A02 | 001/002/003 unittest suites | 5+8+8 успешно |
| A03 | Новый adapter suite | 8 успешно |
| A04 | Blok base_v1 trace | Byte-canonical equality с 001 |
| A05 | Blok cj_v1 trace/readouts | Equality с 003; 64 шага/192 проекции/52 режима |
| A06 | All aliases после dedup | Все подписи сохранены, число поисков не увеличено |
| A07 | Второй оригинальный текст | Новый source hash, только его concept IDs; 32 шага/96 проекций |
| A08 | Неверный source SHA или UTF-8 span | Адресный отказ до native run |
| A09 | Bool/float в integer, NaN, неизвестные поля/policy | Strict preflight rejection |
| A10 | 46 независимых понятий, expanded maps>4096 | ATLAS_LIMIT_EXCEEDED без обрезания |
| A11 | Малый бюджет, нет полного кадра | Честный completed empty/partial result, не 6 придуманных кадров |
| A12 | Одинаковый request_key + payload | Один run, тот же run_id, без повторного вычисления |
| A13 | Тот же request_key + другой payload | REQUEST_CONFLICT |
| A14 | Конкурентные запросы/разные projects | Независимые состояния; нет потери записей/чужого доступа |
| A15 | Restart после complete и посреди run | Complete доступен; unfinished маркирован INTERRUPTED |
| A16 | Pagination/export | Все immutable записи, корректный next_offset, нет тихой потери |
| A17 | Реальные tools/list и tools/call | 6 новых доступных команд/эквивалентных согласованных имён |
| A18 | Старые MCP/assurance tests | Без регрессий старых 55; реальные новые schemas совместимы |
| A19 | Профили input и budgets | Расход ровно заданный, никаких full reachability в explore |
| A20 | SUTI и White Star на двух inputs | Реальные backend receipts, одинаковый common snapshot |
| A21 | Отдельный extraction в одной ветви | UNMATCHED_INPUT; не ложный matched |
| A22 | Decoder, record_interpretation и оценка | Одинаковый протокол; явные LLM additions и источники |
| A23 | Три матричных семейства | Positive pass + negative counterexample/REJECTED |
| A24 | Неизвестная chemistry/physics schema | UNSUPPORTED_MODEL, не формальный успех |
| A25 | Подмена source/trace/matrix в export | Integrity/provenance failure или REJECTED |
| A26 | Offline replay | Без LLM, без сети, logical digest совпал |
| A27 | Worker timeout/native missing | Явный сохранённый отказ; основной сервер жив |
| A28 | Warm/cold latency | Реальные числа; import/build/LLM не включены в numeric тайком |
| A29 | Deploy/rollback | Проверены в фактически доступной целевой среде; указана степень выполнения |

Если SUTI ingress или модельный backend недоступны, A20 остаётся незавершённым. Это не блокирует передачу исправной White Star части, но запрещает назвать весь эксперимент двух режимов завершённым. Никакого требования статистической победы White Star нет.

В verification/RUN_REPORT.json следует добавлять новые проверки сервера отдельно от уже приложенных локальных результатов; не редактировать исторические результаты code/**/results под новые ожидания.

