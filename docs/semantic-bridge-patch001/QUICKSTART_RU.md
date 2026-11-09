# Semantic Bridge PATCH001: запуск через MCP

Обновите список MCP-инструментов: ожидается102 метода. Если клиент сохраняет98,
переподключите приложение по тому же URL. Текущий транспорт без Authorization.
Новый слой не вызывает внешнюю LLM: формулы предлагает клиент.

1. Создайте свой проект через assurance_project_new.
2. Сохраните source через formal_store(kind=source). Точный DTO содержит
text_utf8, sha256, spans, context_refs, rights — здесь rights непустая строка.
3. Передайте выданный stored_object_ref в semantic_bridge_register вместе с
expected_source_sha256, target_signature и1…6 hypotheses. Для каждого нужны
client_id, language=FOL_V1, formula_ast либо unsupported, assumptions, source_links,
construction_trace и obligations. Необязательный creator — только декларация.
4. Сохраните сценарии formal_store(kind=model), затем передайте их реальные refs
и пары client_id в semantic_bridge_analyze. Максимум10 пар/8 сценариев.
5. Получите graph/checks/obligations/bundle через semantic_bridge_inspect.
Для replay используйте run_ref и result_sha256 из конкретного ответа.

[MCP_EXAMPLES.json](MCP_EXAMPLES.json) содержит полные реально принятые calls
с SHA/rights/AST и выданными refs. Для нового прогона замените project,
request_key и refs собственными ответами; чужой SHA не даёт доступа к объекту.

Формальные статусы отделены от source meaning. H0/H2 — α-равные формулы, но
разные гипотезы и контексты. H1⇒H0 проверяется16 булевыми строками; обратное
направление имеет контрмодель. H0/H3 сохраняют обе модели несравнимости.
Assumptions проверяются отдельно; исходные linguistic obligations остаются OPEN.
При TYPE_REJECTED отдельный language_gap не изменяет IDs и лимит исходных
obligations. future не считается поддержанным FOL.

Все несводные view возвращают base64 byte pages. Начните offset=0; декодируйте
каждую data, запрашивайте next_offset до null, соедините байты и проверьте полный
sha256. Не конкатенируйте сами base64-строки. Ничего не обрезается молча.

Готовые REGISTER_BUNDLE.json и ANALYSIS_BUNDLE.json находятся в release ZIP:

```bash
python tools/semantic_bridge001_replay.py ANALYSIS_BUNDLE.json --expected-sha256 <trusted_manifest_SHA>
```

Нужны установленный0.4.14 wheel, Python3.13/Linux и подготовленное native ядро.
Код берётся только из установленного пакета, не из bundle. Сверьте внешний SHA
архива и MANIFEST_SHA256.txt. Подмена input/result/binding отклоняется.
Ресурсная CPU-отсечка может менять место остановки; такой partial replay
честно вернёт REPLAY_MISMATCH. Нормальные конечные сценарии воспроизводятся точно.

В0.4.14 контекст проверяется даже при неподдержанной формуле: ILL_TYPED
с пустыми assumptions даёт APPLICABLE/NO_DECLARED_ASSUMPTIONS, а при ложной
предпосылке — CONTEXT_INCOMPATIBLE. Это не делает формулу допустимой и не
разрешает исполнение. Неверно типизированная предпосылка даёт UNKNOWN_CONTEXT.
