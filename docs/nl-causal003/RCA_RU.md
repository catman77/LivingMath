# RCA — NL-CAUSAL-003

## Двойная интервенция

В прежнем build_request(mode=matched_ablation) source_order разворачивался перед
передачей LLM, а build_move(placebo=True) затем разворачивал permutation снова.
Это меняло два фактора и сам модельный ответ. Исторический decoder сохранён
byte-identical ради старых replay; для новых сравнений добавлен отдельный
formal_nl_redecode, который не вызывает provider. SHAM меняет порядок ровно один
раз внутри decoder. Один receipt/base AST используется всеми четырьмя arm.

## Ложная новизна простого swap

Открытые U21–U25 дают5/5 совпадений с B-derived SHA при обычной транспозиции.
Различие истинности176/530 является finite relation, а не подтверждением пользы
White Star. U26 имеет ошибочный текстовый эталон: сохранён как EXCLUDED_INVALID_ORACLE.
Новая H05 выходит за closure depth2, но имеет минимальный обычный путь длины3.
Такая разница границ перебора не подтверждает semantic benefit.

## Нестабильный CPU/replay при параллельных запросах

Первая staging-попытка использовала time.process_time: CPU соседнего MCP запроса
потреблял бюджет replay и мог менять полноту finite enumeration. Сохранён отказ
STAGE_CAUSAL.log/OPEN_REPLAY.json. Исправление: time.thread_time и одинаковые
зарезервированные доли для arm; регрессия запрещает процессный clock. Новый
staging и production replay MATCH. При настоящем исчерпании границы сохраняется
UNKNOWN_BOUND или REPLAY_BOUND_DIVERGENCE, не отрицательный научный результат.

## Старый C и tunnel

C не отсутствовал: реальный Workspace содержал COMPLETED result, receipt и bundle.
Непосредственный inspect/replay успешен. Причина внешнего MCP-отказа — удалённый
Cloudflare quick tunnel (Unauthorized: Tunnel not found), старый hostname не
резолвился. После backup tunnel восстановлен с новым временным origin. Ни C,
ни БД, ни исторические хеши не пересоздавались. Production cutover сохранил новый URL.

## Границы заключения

Типы, source origin, finite relation и primitive derivation проверяются отдельно.
Лингвистического adjudication людьми не было; все12 новых источников и рубрика
ASSISTANT_AUTHORED_ORACLE/HUMAN_NOT_EVALUATED. Невыразимая модальность остаётся
невыразимой. Не заявлены SEMANTICALLY_LICENSED, verified или execution grant.
SHA receipts не являются цифровыми подписями независимого провайдера.
