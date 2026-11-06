# LivingMath DYCK006 delivery

[Отчёт](USER_REPORT_RU.md) · [RCA](RCA.md) · [MCP quickstart](QUICKSTART_RU.md) ·
[Матрица](acceptance_matrix.json) · [Run registry](RUN_REGISTRY.json) ·
[Схемы](MCP_TOOL_SCHEMAS.json) · [Integrity](integrity_results.json).

Полный воспроизводимый ZIP находится в GitHub release v0.4.8-developer-preview.
В нём source snapshot/patch, wheels текущего и historical0.4.7, неизменённое ТЗ,
frozen inputs/gold, все модели/DP/proofs, полный real MCP request/response/wire
для baseline/staged/public пяти suite, failed attempts и тестовые логи.
SHA каждого файла и точный source_commit — SHA256SUMS.json внутри;
SHA контейнера — внешний .zip.sha256 и release asset digest.
Credentials, SQLite, private config и полные production workspaces исключены.

`python -m pip install '.[white-star,mcp,test]'`, `lm-suti white-star prepare`,
`python -m pytest -q tests`. Для реального повторения используйте новые project/
tag/output в tools/role006_mcp_qa.py и параметры из --help. Исходный0.4.7 baseline
не следует запускать на0.4.8 как положительный тест. Offline replay без сети:
`unshare -Urn <venv>/bin/python tools/symbolic_patch003_replay.py <evidence/production-role-qa/role-full.zip>`.
Historical wheel предназначен только для отдельной среды проверки.

10780 проверок на каждом endpoint PASS;409 source/installed-wheel PASS,
1066 legacy PASS/20 existing SKIP,24 reference PASS.
UNIVERSAL_INVARIANT=false; family UNDERDETERMINED; R3 PENDING.
