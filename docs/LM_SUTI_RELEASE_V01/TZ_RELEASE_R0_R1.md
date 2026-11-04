# Техническое задание RELEASE-R0/R1 — минимально полезный LivingMath × SUTI v0.1

**Статус:** ready for Codex implementation; изолированная release-ветка. **Основа:** `LM_SUTI_ASSURANCE_003_DELIVERY.zip` со вложенными baseline001/002. Не менять исторические исследования или production.

## Цель

Собрать один независимый от LLM воспроизводимый пользовательский путь поверх существующего assurance checker и binder, без новой математической теории, DSL и попыток обучать малую LLM.

## Состав работ

1. **Read-only intake + integrity baseline.** Верифицировать ZIP MANIFEST, replay и доступные тесты. Указать точно, какие версии runtime, schema и checker включаются в target; создать BASELINE_LOCK.json и capability map. Не копировать три вложенных vendor ядра как три «экземпляра продукта». Исторические ZIP остаются сохранены без правок.
2. **Single canonical package.** В `src/lm_suti_assurance/` или аналогичном изолированном пакете единожды собрать текущие contracts, binder, original verifier и direct/compiled evaluator. Порядок источников и сборка должны сохранять смысл вердиктов. Если исходное ядро нельзя безопасно переместить без хеш-расхождения — оставить frozen vendor core в одном месте, положив над ним тонкий facade, и пояснить причину.
3. **CLI pipeline.** Реализовать `project new`, `source add`, `task import/draft`, `candidate import`, `check`, `report`, `export`, `replay --offline`, `doctor`. Draft-only NL translation разрешена, если user review подтверждает scope/assumptions; никакой автоматической подмены доказательства. `propose` через одну существующую hosted-модель — optional adapter; ручной candidate должен покрывать весь happy path.
4. **Stable machine schemas.** Явные v0.1 schemas для task, candidate, decision, witness, package_manifest и publication/rights policy. Для version mismatch возвращать HOLD/MIGRATION_REQUIRED, не молча исправлять.
5. **Human-readable report.** Печатать `status`, `claim_kind`, исходную формулировку, `machine_term`, exact assumptions & scope, source refs с SHA/byte span, verifier hash, witnesses/countermodels и границу достоверности. `CHECKED_FINITE` = доказано только относительно полного объявленного класса/конечного домена; `SOURCE_ATTESTED` = проверено только точное поле/потеря проекции; `EMPIRICAL_HYPOTHESIS` не повышается до proof.
6. **Immutable research bundle.** Export с исходными байтами только при can_embed/rights policy; без модели, credentials, local path secrets. Сохранить все failed candidates и supersession; новый результат — новый record. Offline replay всегда без model/network/OAuth; при пропущенном dependency — честная ошибка.
7. **Minimum smoke cases.** (a) исторический 23/24 false ENTAILED -> REJECTED + two countermodels; (b) true bounded program invariant -> CHECKED_FINITE; (c) SUTI source projection difference -> LOSS_DETECTED/ SOURCE_ATTESTED; (d) empirical unknown -> UNKNOWN/HOLD; (e) попытка молча поменять scope/source -> REJECTED/HOLD. У каждого expected status заранее фиксируется отдельно от результата генератора.
8. **Clean environment.** Задокументировать dependency installation, `doctor`, smoke и единую команду offline verification; старые тесты должны остаться зелеными. Не делать сетевой тест обязательным для `replay`.

## Не делать

- Qwen3-0.6B/3B/4B, LoRA, constrained-decoding benchmark и любые competition suites.
- Native SUTI и formal Lean admission; не выводить PROVED_FORMAL без реального kernel checker.
- Устанавливать новый публичный MCP или обходить проблемы TLS/OAuth на живом сервисе; отдельный MCP pilot — после R2.
- Multiuser, billing, UX-heavy web app, Research Commons production, самостоятельное право выполнять внешние действия.

## Тесты приёмки

- `baseline_replay_match`: same logical digests для тестового ядра, offline direct & compiled;
- `source_truth_boundary`: source/projection НЕ претендует на physical truth;
- `countermodel_integrity`: historical false entailment rejected with witness;
- `manual_generator_independence`: полный workflow без вызова LLM;
- `source_binding_integrity`: не принимаются измененные source/scope/evidence refs;
- `offline_cleanroom`: export → clean unpack → offline replay без сети и secrets;
- `invalid_input_handling`: duplicate JSON keys, malformed term, oversize source, path traversal, version mismatch дают явную причину отказа;
- `no_prod_change`: hashes/health production, если доступ, неизменны;
- `no_claim_inflation`: никакой PROVED_FORMAL / native SUTI PASS.

## Поставка

В отдельном delivery каталоге: `src/`, `tests/`, `pyproject.toml` (или requirements + launcher), `README_QUICKSTART_RU.md`, `CLI_REFERENCE.md`, `BASELINE_LOCK.json`, `CAPABILITIES.json`, `SMOKE_RESULTS.json`, `REPLAY_DIRECT.json`, `REPLAY_COMPILED.json`, `COMPATIBILITY_AUDIT.md`, `LIMITATIONS.md`, `RELEASE_GATE_R0_R1.md`, `USER_REPORT_RU.md`, `RCA.md`, `MANIFEST.sha256`. Никаких секретов, SQLite production или веса модели в пакете.

**Решение:** `R0_R1_PASS` только если реальный clean-room end-to-end workflow доказуемо воспроизводим без исходной LLM. Если не проходит — `BLOCKED` с конкретным reason. Не подменять частичный результат словом «релиз».
