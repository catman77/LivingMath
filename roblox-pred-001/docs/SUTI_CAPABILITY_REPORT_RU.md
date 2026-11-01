# Реальные вычислительные возможности

Проверка 2026-11-01: read-only вызовы через уже подключённый LivingMath plugin и
инспекция локальных рабочих исходников. Это **не прямой вызов tools/list** и не
исполнение native модели. Полный список 44 рекламируемых инструментов и SHA
трёх исходных квитанций — в [capabilities.json](../reports/capabilities.json).

## Подключённый сервер

| Реальный вызов | Аргументы | Наблюдаемый результат |
|---|---|---|
| livingmath_bridge_system_status | {} | version1.2.0rc3-observer012, deployment20261101T044526Z-observer012, reported44tools, livingmath-artifact/1, typed008/1 |
| livingmath_bridge_catalog | limit=5 | 3 источника: P1-001 learning crystal, P1-002 study session, ALCH006 |
| livingmath_service_health | {} | SQLite ok, schema_version по квитанции, canonical events2058; audit ok,4817 записей |

Audit head: `c9c0048be5cc2e782cb2f2377da524e5ad04303d86b65792ef1d503b8c1c3d50`.
SUTI_native_runtime=NOT_EXECUTED, proof_status=unverified, execution_permission.allowed=false.
Сервер предлагает построение source graphs, условные конечные проверки/контрпримеры,
исследовательский lifecycle и autonomy API. Наличие метода ingest не означает
наличия замороженного Roblox feature extractor. Его вызов создал бы рабочие задачи,
поэтому новые production задачи не создавались. Исторический last_call_status=OK
не считается нашим LLM-вызовом. Новых платных или иных model calls — 0.

## SOMA: исходная реализация действительно найдена

Рабочий соседний файл `../SOMA/soma_m0/src/soma_m0/core/adapter.py`, класс
`SomaMarketAdapter`; SHA256
`ef3dfc951acb4b18ef117cf45c073c34f7f181cb7632eca8ca87faa598f3f103`.
Проверены реальные сигнатуры, а не придуманный endpoint. `kernel.py:24` задаёт
NCH=5. Конструктор принимает quantum, seed, mode, delta, lease, rej_bits, anchors,
adapter, state, nc; известны RAW и CAUSAL_SCALE.

| Операция | Вход → выход / эффект по исходнику |
|---|---|
| predict_next | состояние → snapshot score(x) в bits, без observe |
| observe | числовой x_float[5], optional score/adapted/t/new_episode → persistent update |
| probe_state | зафиксированная schema → числовые признаки состояния, read-only |
| structural_state / checkpoint / load_checkpoint | состояние / файл → структурный снимок либо сохранение/восстановление |
| run / run_probe | XI/XF/EPI, границы t0/t1 и outputs → prequential запуск / features |

Kernel не изменялся и новый native run не запускался. Не определено операционное
отображение Roblox text/project observations в эти пять каналов, правило
квантования и причинного порядка, frozen probe schema, readout и связь с будущим
90-дневным outcome. Результаты прежних финансовых экспериментов не переносятся на
Roblox. Глобально объявлять SOMA недоступной неправильно; **задачное сопряжение
NOT_IDENTIFIED** — точная граница.

## SUTI/DAVE/LevinMass и adapter contract

В локальных SUTI.os/SUTI.uni архивах проверены имена и состав рабочих файлов:
в SUTI.os есть operational Python-инструменты, в SUTI.uni не обнаружены исполняемые
файлы выбранных языков. Имена не доказывают отсутствие всех возможных runtime.
В обследованных местах готовый DAVE/LevinMass Roblox binding не найден. Bridge
схемы не объявлены native probabilistic predictor.

Внутренний Python-контракт `roblox_project_structural_features/v1` передаёт только
as_of и допустимые версии title/description/image/concept artifacts. Outcome,
success, future history и train threshold не передаются. Это API-структура, не
новый DSL или фундаментальная операция. Dry-run синтетический; результат
UNSUPPORTED с relations=null/features=null. Нет нулевого вектора, выданного за
реальное измерение. Реализация S1/H1 отложена до разрешённых данных и проверяемого
сопряжения. [Предложение005](../../suti_author_proposals/005-native-prediction-binding/README.md)
фиксирует варианты согласования; оно никому не отправлялось.
