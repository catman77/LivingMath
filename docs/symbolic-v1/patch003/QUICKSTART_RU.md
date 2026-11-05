# PATCH003: конечные комплексы и наблюдатели

Версия сервера `v0.4.3-developer-preview`, пакет `0.4.3.dev0`. Через существующий HTTPS/OAuth endpoint публикуются82 инструмента. Если ChatGPT показывает75, переподключите LivingMath по прежнему адресу, чтобы перечитать `tools/list`. Адрес указан в локальном `~/.local/state/livingmath/mcp-url`.

## Первый SP-комплекс

Сначала зарегистрируйте проект инструментом `assurance_project_new`:

```json
{"project":"sp-lab","request_key":"init"}
```

Вызовите `white_star_symbolic_complex_analyze`:

```json
{
  "project":"sp-lab",
  "request_key":"sp4-first",
  "request":{
    "schema":"livingmath-symbolic-complex-request/1",
    "complex_source":{"kind":"sp_balanced_fixture","max_length":4,"rewrite_rules":["SP_TO_EMPTY","PS_TO_EMPTY"],"edge_identity":"source_position_rule"},
    "cells":{"policy":"all_local_peaks","join_depth_limit":1},
    "analysis":["graph_cycles","homology_F2","path_coherence","pi1_certificate"],
    "budgets":{"max_vertices":500,"max_edges":2500,"max_cells":5000,"max_cpu_ms":4000}
  }
}
```

Из ответа возьмите `run_id`. Передайте его в `white_star_symbolic_complex_verify(project,run_id)`. Для N4 получаются9 вершин,14 позиционных рёбер,8 клеток, ранг ∂₂=6 и H₁(F₂)=0. Путевая согласованность проверяется отдельным verifier; одна гомология не доказывает π₁. Ограниченный fixture принимает только чётные N2…10. Произвольная сохранённая история не получает этот сертификат автоматически.

## Наблюдатели и датасеты

`white_star_symbolic_dataset_store` принимает `livingmath-observer-dataset/1` с `kind="train"` или `"queries"`, массивом `records` и `sha256`. SHA вычисляется по каноническому JSON всего объекта **без** поля `sha256` (`lm_suti_assurance.core.digest`). Каждая запись содержит `id`, `tokens`, `source.text`, SHA256 точных UTF-8 байтов текста, `source.edition` и непустую строку `source.rights`. Это отдельный контракт dataset, а не `ArtifactInput.Rights`. Учебная запись имеет boolean `accepted`; query с этим полем отвергается. Токены должны совпадать с whitespace-токенизацией исходного текста.

Полные валидные запросы, включая source/rights, опубликованы в [api_examples.json](api_examples.json); это реальные принятые MCP-вызовы. Зарегистрированные `dataset_ref` того же проекта передаются как `task.train_ref` и `task.predict_ref` в `white_star_symbolic_observer_synthesize`. Полные JSON Schema находятся в [MCP_TOOL_SCHEMAS.json](MCP_TOOL_SCHEMAS.json) и `bridge_system_status`.

Вызов сохраняет конечную эмпирическую модель, происхождение признаков, AST/трассы реальных операций, source spans и контекстные свидетели. `pair_0_max` остаётся BUILTIN. `derived:*` допускает только проверяемые композиции существующих операций; отсутствие подходящего признака возвращает `NO_VERIFIABLE_NEW_OBSERVER`. `CONTRADICTORY_TRAINING`, `UNDERDETERMINED`, `NOT_IDENTIFIABLE` не превращаются в доказанный язык. Разрешение `retain_as_empirical` сохраняет противоречащие метки как наблюдения; строгий режим не выдаёт модель.

## Чтение и воспроизведение

Оба инспектора поддерживают `view="summary"`, тематические секции и `view="export"`. Следуйте `next_offset`; большие секции возвращают `artifact_ref` для `view="artifact"`. Соедините декодированные base64 chunks и проверьте SHA256. Первый экспорт фиксирует неизменяемый снимок журнала; следующие страницы используют тот же снимок. ZIP содержит только данные.

На сервере: `white_star_symbolic_extension_replay(project,bundle_ref)`. Вне сети:

```bash
python -m pip install '.[white-star,mcp,test]'
python -m lm_suti_assurance white-star prepare
python tools/symbolic_patch003_replay.py /path/to/sp-10.zip
python -m pytest -q tests
```

Для корпусного эксперимента используйте замороженные данные из evidence-пакета:

```bash
python tools/symbolic_patch003_research.py run --frozen /path/to/corpus-freeze --output /tmp/patch003-rerun
```

Внешние holdout-метки читает только оценщик после всех inference jobs. Общая квота остаётся2 активных воркера,16 в очереди,5 CPU/6 wall секунд и512 MiB на job. Нет дополнительных LLM, сети или исполнения кода из ZIP. `execution_permission=false`; новый аудит не присваивает математический `verified`. Старые run IDs и профили replay продолжают работать.
