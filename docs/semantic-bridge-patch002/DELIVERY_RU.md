# Поставка Semantic Bridge PATCH002

Один SEMANTIC_BRIDGE_PATCH002_DELIVERY_20261109.zip содержит полный source.zip и binary patch от b48c44e, wheel0.4.15, сохранённый wheel0.4.14 для старого replay, неизменённый исходный архив/ТЗ, независимые проверки, все журналы попыток, сырые MCP request/response, модели/сертификаты, resource/integrity/rollback и два клиентских LLM-протокола. Большие JSONL сохраняются byte-exact gzip с RAW_GZIP_MAP.json. MANIFEST_SHA256.txt проверяет каждую запись.

GitHub commit/tag/release и внешняя SHA финального ZIP фиксируются после публикации в PUBLICATION_CERTIFICATE.json. Базы, private datasets, credentials и owner config исключены. GitHub Actions отключён по решению владельца; пакет собирается локально. Engineering PASS не означает семантическую лицензию или измеренный причинный LLM uplift.
