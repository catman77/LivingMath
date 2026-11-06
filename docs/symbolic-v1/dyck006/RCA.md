# RCA: DYCK006

## Исходная ошибка выразительности

Реальный0.4.7 допускает только equality-compositions без ориентированного
связывания атома с ролью. SP и PS изоморфны по equality pattern; train labels
требуют различать их.18 исходных runs воспроизведены до правок, baseline49 checks
подтвердил TP0/TN242/FN14. Увеличение бюджета не добавляет отсутствующий constructor.

Исправление: конечный train-generated ATOM_ROLE +0/1/2 RECURSE catalog, nullable
base и буквальный CONCAT. Роль привязана к источнику; обе ветви проверяются
отдельным checker, включая полный отрицательный interval DP. Нет special Dyck
builtin или копии reference/oracle в production.40 предложений, два совместимых
на84 train, structured tie-break; никакой uniqueness/universal claim.

## Найденные и исправленные дефекты до выпуска

1. Producer мог вернуть scalar, отличный от корректного сертификата. Теперь
   prediction берёт independent decision; monkeypatched liar regression PASS.
2. Новый worker action нарушал неизменяемый whitelist. Query verification
   перенесена на существующий observer_verify с query_record, реальный fork PASS.
3. Счётчик promotion не учитывал role marker; исправлен admission bookkeeping.
4. Source worktree не имел подготовленного native backend; prepare воспроизвёл
   прежний бинарный SHA. Первые ENGINE_UNAVAILABLE/RED логи сохранены.
5. Параллельные QA suite превысили существующий HTTP rate и получили429.
   Используется последовательный запуск и только клиентский bounded retry
   явного pre-execution018_RESOURCE_BUSY; byte-identical request/key, никаких
   retry математических ошибок/произвольного429. Исходные failed attempts сохранены.

## Остаточные границы

P0 и P1 N≤6 PASS. Две программы совместимы, не идентифицирован уникальный язык.
Scope12/91cells/512trials/recursion8 конечен; UNKNOWN не false и не checked truth.
Не выполнен смысловой перенос на произвольный текст, native SUTI, R3 approval
или математическое доказательство универсальности. UNIVERSAL_INVARIANT=false.
GitHub Actions учитывается отдельно: публикация не превращает billing failure
в успешный CI; точный текущий check-run receipt приложен после push.
