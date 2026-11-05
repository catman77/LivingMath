# RCA — Semantic Bridge

## Исправленные причины отказов

1. **Provider schema transport.** Первые3 реальных попытки закончились HTTP400: выбранный hosted interface отверг `uniqueItems` в response schema до создания ответа. Изменена только передаваемая backend-схема; локальная строгая proposal schema и проверка уникальности сохранены. После исправления получены ровно6 содержательных ответов, без quality retry. Документация provider описывает подмножество JSON Schema: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses ; конкретный отказ подтверждён реальными receipts, а не предположением обо всех моделях.
2. **Owner-private transport warning.** Codex включал auxiliary error-item с предупреждением `Under-development features enabled:` и локальным путём. Неизменённый export_guard правильно запрещал его экспорт. public_receipt отделяет только этот диагностический warning, сохраняя SHA и ссылку на полный оригинал в приватном spool. Все prompts, ответы, provider failures и usage остаются неизменными. Первоначальный raw intake-журнал сохранён приватно; экспортируемый intake является отдельной записью происхождения тех же ответов. Повторной смысловой генерации не было.
3. **Metadata-only rebinding.** После проекции receipts непрозрачные адреса родителя изменились. Первоначальный model input сохранён буквально; binder дополнительно сравнивает declared semantic/source content родителя, исключая только producer/opaque refs. Это не смысловой repair. Изменение source, значений разметки или parent semantic content не проходит такое сопоставление. R04 отдельно подтверждает неизменность core verdict/witness при generator-only metadata changes.
4. **FastMCP JSON union.** На реальном HTTPS-клиенте `Json|None` автоматически декодировал JSON-строку в dict и затем отвергал её как str. Optional proposal теперь plain bounded string с пустым sentinel, без ослабления вложенной JSON Schema. ToolManager-validation regression и реальный MCP проходят.
5. **HTTP body size.** ZIP base64 превышал прежний bounded POST, replay отклонялся HTTP413. Лимит не увеличен: semantic_export сохраняет immutable ZIP по SHA в своём проекте; semantic_replay принимает только этот SHA/ref, проверяет digest и запускает существующий offline replay. Произвольные пути не допускаются. Новый regression отвергает чужой проект и tamper.
6. **Staging config permissions.** Временный файл release-v2 получил0644, owner-only loader правильно отказал в старте. Исправлено создание/0600 файла, loader не ослаблен. Ранние каталоги QA сохранены.

Две операторские ошибки при финализации (неверный путь к QA client helper до любых MCP вызовов; чтение baseline health без его `parsed` envelope) исправлены в локальных командах/скриптах. Они не затрагивали production данные или модельные результаты.

## Непреодолённые границы, а не выдуманные PASS

- Интерпретации и происхождение поэтического смысла не доказываются. Native SUTI не исполняется; formal adapter отсутствует. Истинность/полнота model annotation не установлена.
- SOURCE_ATTESTED относится к exact quote-envelope bytes после UTF-8 preflight, не к произвольной прозе observation. Некоторые фразы модели прямо признают отсутствие её собственной проверки издания; они сохранены.
- Публичное совпадение строк не сертифицирует редакторское издание и цифровые права. Запрошенный корпус экспортируется private-only; если bytes не разрешены, весь зависимый слой prompts/anchors также отсутствует и replay возвращает MISSING_SOURCE_DEPENDENCY.
- Structural preservation ограничено явно enumerated domain/Q. Семантические/физические вопросы остаются гипотезами. Отсутствие свидетеля вне полного контракта не становится proof of losslessness.
- Provider revision и стоимость неизвестны; для3 неуспешных попыток usage также null. MCP QA доказал реальный обмен через owner pipe и cache тех же фактических outputs, не дополнительные холодные генерации.
- Автоматический clean-room на двух Python не заменяет двух внешних участников: R3=PENDING, external reports0. Preview установлен по прямому запросу владельца, без заявления о final human admission.
- Базовые assurance release-строки v0.1 сохранены для старых контрактов; основной MCP и semantic_contract имеютv0.2, Python wheel0.2.0.dev0.
- Адрес сохраняется, пока жив текущий quick tunnel; долговременный named domain здесь не добавлялся.

Обязательная матрица36/36, установленный wheel155/155 на двух Python и real HTTPS25/25 прошли. Никакие отрицательные результаты или старые журналы не удалены; guard, frozen checker, approvals и execution=false сохранены.
