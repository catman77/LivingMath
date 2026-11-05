# Готовый промпт для кодового агента

Ты — кодовый агент действующего LivingMath MCP. В работу передан ZIP `LIVINGMATH_SYMBOLIC_COMPLEX_OBSERVER_PATCH003_20261106.zip`. Задача — выполнить **точечное аддитивное расширение** существующего сервера с исходным verified deployment `v0.4.2-developer-preview`, `symbolic_v1/1-patch002`: построить `symbolic_complex_v1`, `observer_synthesis_v1`, `pairwise_context_v1`, не ломая White Star numerical/SUTI/legacy.

## Порядок обязательных действий

1. Распакуй переданный архив; проверь `CHECKSUMS_SHA256.txt`. Прочитай последовательно `README_RU.md`, `01_RCA_AND_DECISIONS_RU.md`, `02_TECHNICAL_SPEC_RU.md`, `04_FORMAL_MODEL_RU.md`, `05_MCP_API_CONTRACTS_RU.md`, `06_ACCEPTANCE_PROTOCOL_RU.md`, `07_RESEARCH_PROGRAM_RU.md`, `08_RELEASE_AND_REPORTING_RU.md`. Сначала выполни независимый эталон: `python3 tests/test_reference.py` и `python3 reference/sp_complex_reference.py --max-len 10`.
2. **Сначала проинвентаризируй реальный production repository.** Найди source of truth для `white_star_symbolic_explore`, `white_star_symbolic_inspect`, `white_star_symbolic_replay`, reducer SP, provenance DAG, existing operation registry, grammar predictor, feature families (`pair_0_max` и др.), worker sandbox, idempotency, export/replay и `bridge_system_status`. Зафиксируй реальные пути модулей и SHA-256 оригинальных численных kernel files; исходный реальный код **не содержится в ZIP**. Не делай вид, что локальный эталон является кодом production.
3. Реализуй **P0**, минимальным изменением: сохранение текущих APIs + новые независимые типы finite oriented 1-cell/2-cell и checker; построение `X_N` с `N=2,4,6,8,10`, точная `∂1,∂2` над F2, verifiable `π1` certificate только для указанного terminating+locally coherent SP-complex. Не объявляй тривиальность π₁ на основании `H1=0` без отдельного path coherence proof. Слоты `source spans`, `rule id`, `position`, immutable lineage обязательны. Не схлопывай параллельные рёбра.
4. **Напиши независимый verifier** нового сертификата (не boolean приписанный generator-ом). Verifier проверяет настоящий DAG зависимостей на более коротких словах, покрытие всех критических пиков, 2-cell boundary, confluence witnesses и правила формального сокращения. Повреждённый proof проходит `REJECTED`, missing face — `NOT_PROVED`. Рабочая эталонная реализация в `reference/sp_complex_reference.py` — сравнительный тест, не trusted production proof checker.
5. Выполни P0 unit, adversarial и metamorphic gates. Сделай data-only archive, replay, pagination / artifact chunking, ограничение CPU/wall/memory, cross-project isolation. Проверяй исходные численные хеши, чтобы гарантировать отсутствие изменений White Star numeric.
6. Только после этого реализуй **P1**: реестр происхождения grammar features, dependency-aware ablation, bounded композиционную генерацию контекстных отношений из реально разрешённых операций, сопровождаемые `operator_ast`/witness/provenance, внешние контрпримеры, `UNDERDETERMINED`, `NOT_IDENTIFIABLE`, `TIE`, no label leakage. `pair_0_max` — `BUILTIN`, если в production он уже существует; не «открывай» его задним числом.
7. **Проведи P2 на подлинном французском корпусе** через существующий контролируемый источник или набор зафиксированных input hashes. Сохрани edition и hierarchical segmentation. Split train I–VIII / holdout IX–X, независимая per-variant α-канонизация, контроли punctuation-only, length-only, majority. Случаи II.5, VII.2 и все alpha-identical pairs должны помечаться как неидентифицируемые, а не засчитываться в «успех». При отрицательном переносе дай честный отчёт; не меняй metric после просмотра результата.
8. Выпусти готовый интегрированный diff/commit, тестовый журнал с фактическими PASS/FAIL и source-bound reproducible ZIP. Отдельно перечисли невыполненные пункты, реальные blockers и непроверенные гипотезы. Никаких «всё готово» без live endpoint + replay.

## Строгие запреты

- **Не переписывай** White Star численное ядро, `base_v1/cj_v1`, СУТИ, MCP projects и старые immutable runs.
- **Не делай** универсальный DSL, «автономного исследователя», global brute force of programs/strings или ещё один независимый сервер. Режим полного finite enumeration допустим только для строго ограниченного эталона `sp_balanced_fixture(N≤10)`, где он является определением проверяемого объекта.
- **Не подменяй** π₁ графовой цикломатикой, гомологией F2 или сравнением финальных слов. Не называй недоказанное «теоремой». Не скрывай предположение `all_local_peaks_filled`.
- **Не используй** test labels при подборе features. Слепой holdout должен быть физически отделён от inference process. Метки от внешнего оценщика; случайно сгенерированные отрицательные варианты — не семантические отрицания исходного текста.
- **Не выдавай** runtime diagnostic `NO_NOVEL_CANDIDATES/MAX_*` за математическую полноту; не называй рост `unique signatures` качеством грамматики.
- **Не добавляй** в ядро дополнительные LLM, сеть, выполнение произвольного пользовательского кода/ZIP, приватные пути и filesystem writes вне заданной sandbox.

## Приоритет при нехватке времени/ресурсов

Заканчивай P0 полностью и воспроизводимо, с честным `P1=NOT_IMPLEMENTED`, вместо недоделанной широкой архитектуры. Рабочее P0 намного полезнее 5000 строк мёртвого кодового каркаса. Если P0 закрыт — P1, затем P2. **Не задавай заказчику вопрос по уже указанным параметрам**; выбирай простейший совместимый вариант и документируй его.

## Acceptance obligations

- `2,4,6,8,10` дают точные tuple `(V,E,graphβ1,faces,rank∂2)`: `(3,2,0,0,0)`, `(9,14,6,8,6)`, `(29,74,46,80,46)`, `(99,354,256,560,256)`, `(351,1614,1264,3360,1264)`.
- `H1(F2)=0` для заявленного полного SP-complex; `π1_status=PROVED_TRIVIAL_WITH_CERTIFICATE` **только при отдельной проверке полного 2D path-coherence**. При `cells=none` доказательство не допускается; graph `π1 ≅ F_β1`. Повреждённые edges/faces/certs отвергаются.
- Проверить совместимость old symbol/numeric interfaces и source SHA; equal requests/replays дают matching digests.
- На Dyck-лаборатории 28 train, 70+252 holdout (14+42 positives) показать feature origin и leakage/ablation. Не вшивать Dyck как конфигурационный костыль.
- На corpus-полигоне отчёт включает `NOT_IDENTIFIABLE`, pairwise wins/losses/ties, confidence, punctuation-only baseline и строго одинаковые test splits. Никаких придуманных процентов.
- Итоговый статус каждого утверждения: `PROVED_EXACT`, `CHECKED_FINITE_INSTANCE`, `EMPIRICAL`, `CONJECTURE`, `NOT_PROVED` либо `INTERPRETATION`; сериализация не повышает статус утверждения.

Действуй с реальным кодом, выполняй тесты, фиксируй источники и ошибки. Не отчёт о намерениях — сдача работающей совместимой версии и воспроизводимого evidence bundle.
