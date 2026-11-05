# ТЗ: SYMBOLIC_V1 PATCH-002 — bounded escape from local saturation

## Цель

Устранить нежелательное поведение локальной стратегии, когда несколько подряд неудачных предложений приводят к `NO_NOVEL_CANDIDATES` до просмотра других **уже сохранённых** перспективных состояний и доступных операторов. Изменение касается только политики исследования; формальная семантика символических операций, доказательных сертификатов и грамматического индуктора остаётся неизменной.

## Исходный подтверждённый случай

Nostradamus I:1–2: `61c5af7a…` — 18 состояний, 5 шагов, `NO_NOVEL_CANDIDATES`; `diagnostics`: `unproposed_operators=[RENAME]`, `global_exhaustion_proved=false`, `unseen_variants_may_exist=true`. Конфигурации с иными параметрами дают существенно больше состояний: `2dd8d078…` и `dd3dbb46…`. Не утверждать, что все различия вызваны только политикой выбора.

## Требования P0

1. **Детерминированный ограниченный frontier fallback.** Если локальное окно не создало нового пути, а в DAG есть необследованные сохранённые узлы/неиспытанные допустимые операторы, выбрать новый frontier candidate в фиксированном воспроизводимом порядке, основанном на seed, типе операции и id узла. НЕ делать полный перебор всех слов, деревьев или программ.
2. Сохранять `max_steps`, `max_nodes`, `max_word_tokens`, `max_candidates_per_step`, `max_total_tokens`, worker wall/CPU limits. Изменение политики не может расширять пользовательский ресурсный бюджет. Никаких бесконтрольных while, фоновых worker jobs или внешних LLM.
3. Различать как минимум `LOCAL_STAGNATION`, `FRONTIER_FALLBACK`, `ACTUAL_LOCAL_EXHAUSTION`, `MAX_STEPS`, `MAX_NODES`, `MAX_TOTAL_TOKENS`, `WORKER_LIMIT`. Старое `NO_NOVEL_CANDIDATES` допускается как совместимый alias, но НЕ как доказательство глобального исчерпания.
4. Нельзя менять `history_identity=word/provenance` незаметно. Fallback работает в явно выбранном режиме; отчёт включает режим и основания перехода на новое узловое состояние.
5. Протоколировать `frontier_size`, `untried_allowed_operators`, `candidate_attempts`, `fallback_count`, `fallback_reason`, `global_exhaustion_proved` (по умолчанию false) и ссылки на DAG/witness. Никакого «универсально исчерпано» без исчерпывающего сертификата в заранее ограниченном пространстве.
6. Preserve immutable run IDs, idempotency request_key, source digest, source spans, exact alpha/SP witnesses and evidence. Old `base_v1` and `cj_v1` untouched. Старые exports/replays должны оставаться читаемыми.

## Требования P1

7. Добавить сравнимую диагностику охвата операций при одинаковых исходных данных: counts proposed/accepted/duplicate/forbidden per operator, number of revisited nodes, distinct words and distinct provenance traces. Фиксировать общие бюджеты.
8. При перестановке строк литературного текста не объявлять появление новых смыслов; сохранять структурный comparison и явные source spans.
9. `symbolic_inspect(view="diagnostics")` возвращает информацию о fallback и при `MAX_NODES`, когда был хотя бы один локальный тупик; format расширять аддитивно.

## Что не делать

- Не внедрять новый DSL, глубокий формальный proof assistant, глобальный graph enumerator, новую White Star математику или ML/RL оптимизатор.
- Не вводить scalar score как универсальный objective; текущая seeded set-inclusion политика сохраняется для исходного локального выбора.
- Не менять grammar hypotheses, в том числе правило палиндрома, пока отдельный regression gate не обнаружит ошибку.
- Не обещать гарантию выходов из всех локальных тупиков: только bounded frontier escape.

## Критерий готовности

Новое поведение на том же exact fixture, где фиксировано раннее `NO_NOVEL_CANDIDATES`, воспроизводимо; при наличии ранее неизученного frontier оно либо успешно продолжает поиск, либо фиксирует ресурсный лимит; ложно не заявляет полное исчерпание. Все baseline контракты и тесты PATCH-001 проходят. История операций, alpha/SP сертификаты и replay неизменны по смыслу.
