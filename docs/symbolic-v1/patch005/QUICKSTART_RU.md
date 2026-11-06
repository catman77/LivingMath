# PATCH005: использование и воспроизведение

Input API не менялся:83 input/output schemas/annotations прежние.
Используйте existing observer synthesize с promotion_policy.mode=compositional_ast,
candidate_sources=["derivation_trace"],enabled_builtins=[],derive_relations=true.
Полные настоящие [api_examples.json](api_examples.json),
[tools/list](MCP_TOOL_SCHEMAS.json). Сначала создайте свой проект и datasets,
используйте возвращённые refs и свежий request_key; чужой digest не даёт доступ.

Новый grammar_version=mixed_length_typed_composition/1. Через inspect view=model
или diagnostics доступны candidate_generation и прежние composition_promotion/
failed_obligations. Каждый кандидат имеет generation/type/train/promotion stages,
реальные counterexamples и AST digest. Большую секцию дочитайте artifact chunks,
проверьте artifact_sha256. Схема — CANDIDATE_GENERATION_SCHEMA.json.

Для установленного кода: python -m pip install '.[white-star,mcp,test]',
lm-suti white-star prepare, python -m pytest -q tests.
Для полного live run: python tools/generator005_mcp_qa.py --help. Нужны owner login,
новый tag/output и frozen fixture; runner изменяет только собственный QA project
и читает предоставленные исторические runs. Baseline --before предназначен
для старой0.4.6 сборки, на новой он закономерно не воспроизводит старый дефект.

Delivery содержит evidence/fixed-fixture и exact frozen-historical. При
пересоздании: python tools/generator005_fixture.py --historical <snapshots>
--output <new-fixture>. Gold читается внешним scorer только после inference.
Полный regression: tools/recursive_observer_mcp_qa.py с --expected-version
v0.4.7-developer-preview и --expected-observer-version
observer_synthesis_v1/4-mixed-length-typed-generation.

Replay без сети: unshare -Urn <venv>/bin/python tools/symbolic_patch003_replay.py
<delivery>/evidence/production-qa/mix1234-s137-n7.zip. Аналогично COPY52 bundle.
Исторический replay требует утверждённый runtime соответствующей версии.
Worker/provenance/checker/SQLite proofs и весь request/response находятся в ZIP,
credentials/рабочих баз там нет. CHECKED_INSTANCE — finite execution, не theorem.
