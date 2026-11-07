# Formal Bridge v1: точный MCP-контракт

Сервер0.4.9,91 tools:83 прежних и8 новых. Все formal вызовы используют текущий
HTTPS/OAuth endpoint и существующую авторизацию. Сначала создайте проект через
assurance_project_new. Полные actual request/response — api_examples.json;
схемы8 inputs — MCP_FORMAL_INPUT_SCHEMAS.json, все91 — MCP_TOOL_SCHEMAS.json.

## Данные и синтез

Train и queries регистрируются через прежний white_star_symbolic_dataset_store.
Формат livingmath-observer-dataset/1, SHA=canonical JSON digest без sha256;
каждый record имеет id,tokens,source:{text,sha256,edition,rights}. В queries
не должно быть accepted. Предъявляйте actual issued refs того же проекта.

Пример запроса formal_synthesize после регистрации данных:

```json
{"project":"my-research","request_key":"fit-v1",
 "train_ref":"<actual train dataset_ref>","predict_ref":"<actual queries dataset_ref>",
 "constraints":{"kind":"cfg"},"budget":{"max_cpu_ms":4000,"max_candidates":128,"max_tokens":12}}
```

Для автомата kind=dfa. Роли/правила не задаются готовой oracle-грамматикой в fit.
Сохраняются candidates, considered ASTs/counterexamples, untried recipe и budgets.
Исследовательское имя языка и correct query labels не входят в worker payload.
Все limits перечислены в BOUNDS.json. Превышение =>UNKNOWN_BOUND, cyclic nullable
forest =>UNKNOWN_CYCLE. NO_COMPATIBLE_IN_DECLARED_CATALOG не означает невозможность CFG.

Ответ formal_* имеет data.run_ref, операционный data.status и отдельно
содержательный data.result_status. COMPLETED означает окончание job, не истинность.
formal_inspect(project,run_ref,view="result") читает содержательный результат;
view=model|candidates|considered|predictions|objects — разделы/страницы.
Большие dict/result/bundle возвращаются byte/base64 chunks с next_offset/sha256;
списки имеют offset/limit (1…128); для больших proof lists используйте limit=1
либо полный result в chunks. Ничего не усечено молча.

## Независимая проверка и контраст

formal_verify(project,request_key,run_ref,source_ref,candidate_ref?,proof_ref?)
проверяет actual registered candidate на owned source record. Без proof_ref
строится witness и повторно проверяется; с proof_ref проверяются недоверенные
данные. Для произвольного proof test сначала formal_store(kind="proof",data=...).
Существующие imported grammar/DFA можно сохранить через store и проверить, но
они явно IMPORTED_DATA_NOT_INDUCED; это не результат synthesize.

Packed forest содержит все production alternatives, порядок детей, token ranges,
UTF8 spans, start symbol, source/AST/bounds SHA. Negative требует complete chart.
Получить record/proof/candidate storage refs можно через inspect(view="objects"):
identity — содержательный fingerprint, object_ref — actual issued blob ref.
Проверка =>CHECKED_INSTANCE/REJECTED_PROOF/UNKNOWN, execution_permission=false.

formal_contrast(project,request_key,run_ref,candidate_refs,budget?) принимает
не менее2 кандидатов. Возвращает DISTINGUISHING_QUERY с prediction_vector,
correct_label=null и external_annotation_required=true. ε представлен tokens=[],
text="", настоящим SHA и rights, без placeholder. Метка приходит от внешнего
источника: создайте НОВЫЙ train dataset и request_key, сохранив прежний run.
NO_DIFFERENCE_WITHIN_BOUND никогда не EQUIVALENT. Imported pair controls помечены
отдельно от train-compatible induced candidates.

## Предлагаемые FOL-трактовки

formal_store(kind="source") принимает ровно TextSource:
{text_utf8,sha256,spans:[{byte_utf8:[start,end],literal}],context_refs:[],rights}.
rights — непустая декларация происхождения/прав; bytes UTF8, не codepoints.
source_ref берётся из data.stored_object_ref, а не вычисляется вручную.
formal_interpret передаёт source_ref,candidate_provider:{kind,provenance},
target_signature:{sorts,predicates},proposals:[{formula_ast,assumptions,
token_role_links,construction_trace}]. Все4 proposal поля обязательны; links и
trace непусты. Human/imported предложения допустимы, общий NL decoder отсутствует.
Kind/provider provenance — декларация поставщика, не доказательство происхождения.

Каждый FormalCandidate остаётся PROPOSED; type_status=TYPED или TYPE_REJECTED
отделён от source alignment и truth. assumptions — типизированные закрытые формулы.
Signature Checked:[researcher,hypothesis] запрещает Checked(hypothesis,researcher).
Свободные переменные, неизвестные предикаты и shadowed binders отвергаются.

Модель сохраняется formal_store(kind="model",data={domains,relations,world:"closed"}).
Сорта непусты/конечны, relation tuples типизированы; отсутствие факта ложно только
в явно closed модели. formal_model_check(project,request_key,run_ref,candidate_ref,
model_ref) даёт TRUE/FALSE/ILL_TYPED/UNKNOWN, отдельно assumption_results.
Open world =>UNKNOWN. formal_contrast над FOL находит FINITE_COUNTERMODEL,
где все предпосылки кандидатов истинны, и возвращает truth vectors.
NO_COUNTERMODEL_WITHIN_BOUND не эквивалентность и не доказательство смысла.

## Повторение и границы

formal_replay(project,request_key,run_ref) повторяет сохранённый packet при точном
kernel binding и оставляет append-only receipt REPLAY_MATCH/MISMATCH.
Offline data-only bundle: inspect(view="bundle"), затем tools/formal001_replay.py.
Повторный request_key возвращает прежний job; другой payload с тем же ключом
отвергается. Чужие refs/anchor не являются основаниями. Ни один ответ не grant.
UNIVERSAL_INVARIANT=false. Две/несколько compatible models сохраняются независимо
от одинаковых конечных предсказаний. Human author-intent agreement не измерено.

После deployment обновите список инструментов приложения LivingMath в настройках
ChatGPT. Если кнопки обновления нет — отключите/подключите его снова, тот же URL
и OAuth. SDK tools/list проверен отдельно; старый кэш приложения может показывать83.
