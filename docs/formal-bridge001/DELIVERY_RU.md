# Formal Bridge v1: опубликованная поставка

[Релиз v0.4.9-developer-preview](https://github.com/catman77/LivingMath/releases/tag/v0.4.9-developer-preview) ·
[Полный воспроизводимый ZIP](https://github.com/catman77/LivingMath/releases/download/v0.4.9-developer-preview/LIVINGMATH_FORMAL_BRIDGE_V1_DELIVERY_20261107.zip).

ZIP: 388317459bytes, SHA256
`27bf00ad81b2734f4889f9fa8dc4aabc8b18ce619dec4911cb321a524ae6fdfb`.
Source/tag: `6675c2251e85039d7f49fae011fc2efee66fb121`; base `5c756c038fa528bc933f03e99bab0cbc402a3606`.
Внутри735 payload files +SHA256SUMS.json; проверены все их bytes/SHA,
1617 source Git blobs и124 runtime Python files. Извлечённый source совпадает
с опубликованным Git и работающим runtime. После документированного native
prepare повторно прошли21 targeted tests; бинарный SHA ядра прежний.
GitHub fresh clone совпадает по каждому blob; публичный ZIP заново скачан
без credentials, размер и SHA совпали. Receipts лежат рядом в JSON.

Пакет включает full source/patch, current0.4.9 и отдельный historical0.4.8 wheels,
оригинальное ТЗ, frozen data/gold/annotation holder, все models/forests/traces,
full baseline/staged/public MCP request/response/wire, failed attempts,
reviews/logs/schemas/integrity и exact dependency constraints.
Приватные конфигурации/OAuth/SQLite/полные production workspaces исключены;
secret scan168known values +credential patterns PASS.

GitHub Actions:6jobs не стартовали из-за billing lock аккаунта. Это не зелёный CI;
полные annotations в GITHUB_CI.json.430source/430installed,1066legacy/20existingSKIP,
225reference и12103actual production acceptance checks задокументированы отдельно.

Новое в v1: CFG/DFA bounded induction, retained hypotheses, independent proofs,
active external annotation cycle и source-bound PROPOSED FOL alternatives.
Canary256UNKNOWN/no recovery; общий NL decoder не заявлен, native SUTI не
исполнялся, UNIVERSAL_INVARIANT=false, R3 PENDING, execution_permission=false.
