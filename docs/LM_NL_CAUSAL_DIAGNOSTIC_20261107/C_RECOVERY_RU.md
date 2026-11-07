# Восстановление C из сохранённого результата — без LLM

`project = nl_independent_eval_20261107`
`run_ref = 076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46`

Это завершённый ранее `matched_ablation` для U21–U26. Последний успешный `formal_nl_inspect(view=summary)` показывал `COMPLETED`. Сейчас MCP connector возвращает `The tool failed internally` без серверного JSON даже на `bridge_system_status`. Не делайте вывод, что архив на сервере повреждён.

После восстановления подключения выполните:

```text
bridge_system_status({})
formal_nl_inspect({project:"nl_independent_eval_20261107",run_ref:"076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46",view:"summary"})
formal_nl_inspect({project:"nl_independent_eval_20261107",run_ref:"076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46",view:"result",offset:0,limit:48})
formal_nl_inspect({project:"nl_independent_eval_20261107",run_ref:"076ccc229e6c661dae47459449ffc28f5e499f90c68ffe03bb10cc77a7f2ef46",view:"replay"})
```

При `encoding=base64` читать ВСЕ byte-offset страницы до `next_offset:null`; сверить результатный SHA; разобрать кандидатов U21–U25. U26 исключить `INVALID_PRECOMMITTED_ORACLE`. Сверить `candidate_ast_sha` с B из `AMBIGUITY_SCORES_PARTIAL.json` и посчитать finite truth vectors против *двух* исходных gold формул.

Требования: `REPLAY_MATCH`, `LLM_calls=0`, `network_calls=0`; новый `formal_nl_propose` не вызывать для восстановления. В случае отсутствия исходного blob — статус `NOT_RECOVERABLE`, не подменять его повторным LLM.

Если tool error сохраняется, кодовому агенту нужны ровно диагностические значения: живой HTTP/OAuth status, tunnel PID, server worker readiness, MCP tools/list, журнал `nl.finish` по `run_ref`, presence/sha в owned workspace, size/offset handling. Полный дамп прав пользователя не публиковать.
