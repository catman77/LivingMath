# Регрессии

447 PASS из source; 447 PASS из установленного wheel с отключённым pytest pythonpath.
Legacy: 1066 PASS, 20 прежних SKIP. 31 прежняя gate, source/proof/replay/epsilon/a
и1024 формальные решения проверены реальным MCP SDK на staging.
Старые91 tool records совпадают полностью, добавлены2;214 прежних runtime
компонентов побайтно сохранены, изменён только entry. Native SO неизменён.
Отдельные17 unit cases и18 независимых operational probes PASS.

Подробности: REGRESSION_RESULTS.json, KERNEL_PRESERVATION.json,
MCP_SCHEMA_DIFF.json и исходные полные MCP traces в delivery.
Результаты staging не выдаются за публичные HTTPS-вызовы; они отражены отдельно
в DEPLOYMENT.json и итоговой production приёмке.

Измерены4 пары переименований: alpha-AST наборы ковариантны во всех4 плечах;
finite vectors сравнимы для3/4 пар, четвёртая UNKNOWN_BOUND. Публичные E1
Read/Lost имеют одинаковый alpha-pattern, разные source refs и предикаты.
См. RENAMING_AND_LEXICAL_CONTROLS.json; semantic invariance не утверждается.
