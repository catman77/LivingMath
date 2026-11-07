# Formal Bridge001 delivery

[Отчёт](IMPLEMENTATION_REPORT_RU.md), [RCA](RCA.md), [MCP quickstart](QUICKSTART_RU.md),
[результаты](FORMAL_LANGUAGE_MATRIX.json), [приёмка](acceptance_matrix.json).
Полный ZIP публикуется в GitHub releasev0.4.9-developer-preview: source/patch,
current/historical wheels, frozen inputs/gold/annotation holder, original TZ,
все модели/forests/transition tables, actual MCP transcripts baseline/stage/public
и failed attempts, reviews/logs, integrity checks и dependency constraints.
Никаких private configs/OAuth/SQLite/полных production workspaces.
SHA256SUMS.json указывает точный source_commit и SHA/size каждого файла;
внешний checksum и GitHub digest связывают весь ZIP без рекурсивного self-hash.

Установите Python3.13 пакет с [white-star,mcp,test], native prepare, затем tests/.
Для online suite используйте tools/formal001_mcp_qa.py --help с новыми project/tag/
output и собственным owner HTTPS/OAuth. Fixtures sealed; external-gold не передаётся
серверу. Optional short annotation table используется только клиентским внешним
держателем после actual contrast, отдельные новые train поколения.
Offline: unshare -Urn <venv>/bin/python tools/formal001_replay.py <OFFLINE_BUNDLE.json>.
Исторический0.4.8 wheel —только в отдельную среду, не поверх production.

Все результаты конечны. Manual FOL proposals остаются PROPOSED. Native SUTI не
исполнялся, общий NL parser не заявлен, UNIVERSAL_INVARIANT=false, R3 pending.
