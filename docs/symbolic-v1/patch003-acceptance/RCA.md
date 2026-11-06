# RCA PATCH003 acceptance

## FIX-A

Причина: summary.assumptions копировалось из планируемого полного path-certificate независимо от выбранной политики клеток. Checker/pi1 были корректны. Исправлена только конструкция summary по independently checked missing_peaks. Исторические результаты не переписываются; старый профиль сохраняет точный replay.

## FIX-B

Прежняя приёмка показывала builtin Dyck-классификацию и контекстные трассы, но не полезный новый feature. Новая заранее фиксированная задача отделяет эти факты: train-inferred offset1, новый зарегистрированный DERIVED feature, реальные primitive executions при fit/predict,64 полных source witnesses и независимый verifier,256/256 против128/256 ablation. Семейство AST предзадано, язык/offset не зашиты в production flag. Конечный успех не является universal invariant или semantic discovery.

Дополнительно устранено вычисление builtin values при объявлении реестра: имена теперь перечисляются декларативно и сверяются с неизменённым grammar.features в differential tests. Monkeypatch запрещает calculator целиком ещё до fit. Verifier использует явные runtime checks, поэтому Python -O не отключает проверку.

## FIX-C

Прежний внутренний corpus-run был шире независимого20-катренного sample, но полная source hierarchy не была отдельно предъявлена. Теперь каждый из942 pair IDs проверен по реальным parent bytes. Важное уточнение: локальный century segment — проекция, не целая центурия; полный global source tree строится harness отдельно из19 immutable chunks, без изменения исторических записей и без новых семантических аксиом.

## Ошибки запуска, сохранённые в evidence

Первый baseline regression runner получил82-schema snapshot при исторически фиксированном75-schema contract; это ошибка выбора baseline файла, не изменение сервера. Повтор использовал исходный75-schema snapshot и прошёл253 проверки. Отдельная новая проверка сравнивает все82 прежние схемы.

Первая сборка использовала runtime venv без setuptools; финальный wheel собран существующим build venv, зависимости production не обновлялись. Первые6 legacy failures были ModuleNotFoundError в дочерних процессах из-за неверного cwd/PYTHONPATH. Повтор из live_math_mcp_prod с PYTHONPATH=.:../src дал1066 PASS/20 SKIPPED; тесты и защитные проверки не ослаблялись. Все исходные failed logs сохранены. После усиления запрета builtin calculations выполнены новые320 tests и отдельная полная финальная MCP-приёмка; промежуточные результаты не подменяют финальную сборку.
