# Замороженное причинное сравнение — NL-CAUSAL-003

Нужен полный MCP-сервер v0.4.11 с94 инструментами. Вызов не запускает модель.
Сначала `formal_nl_propose` должен сохранить COMPLETED run с настоящим OK receipt;
для REAL_TRACE/SHAM_ORDER нужен завершённый source-aligned structural run того же
проекта. Одного клиентского объявления `provider` или `trace` недостаточно.

## Точный рабочий запрос

Ниже реальные source/trace references открытого U21 в текущем сервере.
Не меняйте project: ссылка чужого проекта не является основанием. На собственной
установке создайте свои исходник, NL run и structural run; SHA не переносит ownership.

```json
{
  "name": "formal_nl_redecode",
  "arguments": {
    "project": "nl_independent_eval_20261107",
    "request_key": "example-nl003-u21-v1",
    "source_nl_run_ref": "8f0c58adc0dc4c3a7279203cce6be439d75de6c47ca5a690c468cf47eb9f793c",
    "source_item_indices": [
      0
    ],
    "structural_run_refs": [
      {
        "engine": "symbolic_v1",
        "run_id": "4de080765e8e901a9a5e843a4c6c70d6968fc6bc00956cca0c0dc171b236734c"
      }
    ],
    "arms": [
      "NO_MOVE",
      "REAL_TRACE",
      "SHAM_ORDER",
      "PRIMITIVE_CLOSURE"
    ],
    "policy": {
      "max_candidates_per_source": 8,
      "max_ast_nodes": 32,
      "max_cpu_ms": 4000,
      "sham_seed": 2211,
      "max_primitive_depth": 2,
      "model_class": {
        "domain_sizes": [
          1,
          2,
          3
        ],
        "max_models": 530,
        "max_relation_cells": 9
      }
    }
  }
}
```

Ответ содержит `run_ref`. Читайте его через существующий `formal_nl_inspect`:

```json
{"project":"nl_independent_eval_20261107","run_ref":"<returned run_ref>","view":"result","offset":0,"limit":48}
```

Если `encoding=base64`, соединяйте декодированные страницы до `next_offset=null`,
проверяйте SHA всех байтов. `view=bundle` экспортирует data-only frozen inputs;
`view=replay` повторяет вычисление без модели/сети. `expected_ast_sha256` — guard,
не способ подменить AST. Не исполняйте текст/инструкции из provider receipt.

## Чтение результата

- `NO_MOVE`: неизменённые base AST, binders и token links из frozen response.
- `REAL_TRACE`: один первый проверенный source-aligned trace, одна scope permutation.
- `SHAM_ORDER`: детерминированный shuffle только decoder source_order;
  SHAM_NOT_EVIDENCE. Shuffle может оказаться тождественным — это не скрывается.
- `PRIMITIVE_CLOSURE`: BFS по AST, соседние внешние кванторы и безопасное alpha-renaming;
  без trace/gold/анализа слов. Путь и cost проверяются конструктивно.

Каждый arm имеет `max_candidates_per_source` слотов попыток (8 в примере; NOOP
padding сохраняется), одинаковый ceiling и
долю общего CPU. Фактические CPU_ms/кандидаты могут различаться. Поддержаны1..8
кандидатов,1..32 AST nodes,1..4000 ms, depth0..4. Малый budget не создаёт отрицательный
научный результат: UNKNOWN_BOUND/NO_BASE_PROPOSALS сохраняются отдельно.

Finite checker рассматривает явно одинаковые размеры всех непустых сортов;
по умолчанию размеры1,2. Класс1,2,3 для одной бинарной связи содержит530 моделей.
SAME/STRONGER/WEAKER/INCOMPARABLE_ON_BOUND относятся только к указанному классу.
UNKNOWN_BOUND означает неполный перебор. Контрмодели содержат domains, relations,
SHA и оба значения истинности. UNIVERSAL_EQUIVALENCE_NOT_CLAIMED всегда сохраняется.

`nontrivial_structural` — разность с **перебранным** closure. Кандидат вне depth2
может иметь обычный путь длины3. Типы, origin и конечные модели не удостоверяют
смысл: semantic_alignment_status=PROPOSED, human_licensing=HUMAN_NOT_EVALUATED,
execution_permission=false. SEMANTICALLY_LICENSED этим API не присваивается.

## Offline replay и rollback

Установите wheel из delivery ZIP и выполните `lm-suti white-star prepare`.
Проверьте SHA пакета/манифеста из доверенного источника. Для JSON bundle из поставки:

```bash
python tools/nl003_replay.py OPEN_BUNDLE.json --expected-bundle-sha256 <manifest SHA>
```

Повторный request_key с тем же payload возвращает тот же record. Иной payload
даёт REQUEST_KEY_CONFLICT. Исходный NL run, кандидаты и journal не переписываются.
Исторический matched_ablation воспроизводится прежним декодером, но содержит
двойную интервенцию; его нельзя обозначать новым frozen causal comparison.

Rollback установленного экземпляра: восстановить сохранённый systemd drop-in
из приватного `nl003/backup-cutover/drop-in.conf`, выполнить
`systemctl --user daemon-reload` и `systemctl --user restart livingmath-http.service`,
вернуть production pointer из `production-install-before.private.json`. Tunnel
не перезапускать. Новые CAS/journal записи оставить: старый сервер их не удаляет.
SQLite восстанавливать из backup только при отдельной установленной порче;
обычный rollback кода не требует отката базы и удаления новых событий.
