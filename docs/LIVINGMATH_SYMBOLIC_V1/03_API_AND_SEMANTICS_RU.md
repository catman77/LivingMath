# SYMBOLIC_V1: математика, контракт и формат проверяемых результатов

Эта спецификация задаёт **наблюдаемые свойства API**, а не требует переписывать внутреннюю структуру существующего сервера. Имена полей ниже — рекомендуемый новый контракт; кодовый агент вправе переиспользовать уже принятый в репозитории транспортный формат при сохранении семантики и полной обратной совместимости.

## 1. Математическое ядро

Пусть `Σ` — конечный алфавит атомарных токенов; свободный моноид `Σ*` состоит из конечных слов с конкатенацией `·`, единица `ε` — пустое слово. Токены — атомы без заранее присвоенной семантики. Границы строк/слов при наличии включены в отдельную структуру разметки; они не должны автоматически превращаться в грамматические правила.

- **Буквальная идентичность**: `u =_lit v` iff совпадают токены и границы в объявленной области.
- **α-эквивалентность**: `u =_α v` iff существует биекция алфавита, сохраняющая структуру повторений (переименование токенов). Для набора слов область переименования — `global` или `local`, выбирать явно. `ABBA =_α BAAB` как **отдельные слова**, но `AB|AB` и `AB|CD` различимы при глобальном scope.
- **S/P-редукция**: на `{S,P}*` правила `SP→ε`, `PS→ε`, `q(w)=#S−#P`; конечный результат редукции — `S^{q(w)}` при q≥0 и `P^{−q(w)}` при q<0. Следовательно `u ≡_SP v` iff `q(u)=q(v)`; это равенство нормальных форм, не равенство историй.
- **Экспериментальная неразличимость наблюдателями K**: `u ≈_K v` iff записи всех выбранных наблюдателей в данном конкретном тесте совпадают. **Не объявлять** это истинной грамматической или семантической эквивалентностью. При расширении K отношение может расщепляться.
- **Композиционная асимметрия**: `ab` и `ba` могут отличаться буквально/структурно при одинаковом `q`. Она не доказывает нового закона, пока не задано, какие операционные свойства переживают допустимые преобразования.

Свойства, подлежащие точным тестам: `q(uv)=q(u)+q(v)`, `q(SP_INV(u))=−q(u)`, `REDUCE_SP(INSERT_CANCEL_PAIR(u))` эквивалентно `REDUCE_SP(u)` по результату, но не по истории; `CONCAT(SPLIT(u,k))=_lit u`; `normalize(normalize(u))=normalize(u)`.

Существование внешних смыслов/семантики из этих тождеств не следует.

## 2. Новый MCP вызов (additive)

Рекомендуемое имя: `white_star_symbolic_explore`. Не пытаться послать полное слово в поле `concepts[].coordinates` прежнего `white_star_explore`: оно предназначено для 2D-векторов, а не текста.

Пример запроса (поля `source.sha256` и полная валидация обязательны в настоящем исполнении; пример в документации иллюстративный):

```json
{
  "project": "symbolic_validation",
  "request_key": "sp-first-001",
  "request": {
    "schema": "levinmas-white-star-symbolic-request/1",
    "source": {
      "title": "Four zero histories",
      "text": "SSPP\nSPSP\nPPSS\nPSPS",
      "sha256": "<64 lowercase hex sha256 of UTF-8 source>"
    },
    "segmentation": { "unit": "codepoint", "record_boundaries": "lines", "renaming_scope": "global" },
    "algebra": { "kind": "SP", "allow_reduce": true, "preserve_history": true },
    "observers": ["literal", "alpha_pattern", "adjacency", "composition", "sp_reduce"],
    "operators": ["CONCAT", "SPLIT", "RENAME", "REVERSE", "SP_INV", "REDUCE_SP", "INSERT_CANCEL_PAIR"],
    "search": {
      "seed": 119, "max_steps": 256, "max_candidates_per_step": 4,
      "max_word_tokens": 512, "max_nodes": 8192,
      "strategy": "local_structural_novelty"
    },
    "task": {"mode": "discover_relations"}
  }
}
```

**Нормализация Unicode:** перед запуском указать политику `none|NFC`, при `NFC` сохранить обе формы и отображение byte spans; хеш соответствует **переданным исходным** байтам. ASCII S/P тесты не зависят от Unicode.

**Сегментация:** минимально `codepoint`, `literal_token`, `whitespace`, `line`; все результаты ссылаются на исходные диапазоны. Точки/знаки не уничтожать без явного параметра. Отдельное `layout` для поэтической геометрии можно передавать как дополнительные структурные атрибуты, не подменяя историю текста.

## 3. Ответ и immutable artifacts

```json
{
  "schema": "levinmas-white-star-symbolic-response/1",
  "ok": true,
  "status": "COMPLETED",
  "data": {
    "schema": "levinmas-white-star-symbolic-run/1",
    "engine": "symbolic_v1",
    "project": "symbolic_validation",
    "run_id": "<server generated digest>",
    "source_sha256": "<echo>",
    "kernel_binding": "<version/hash of symbolic operations>",
    "numeric_kernel_binding": "<unchanged existing white star kernel hash>",
    "summary": {"steps": 256, "unique_literal_words": 0, "distinct_alpha_classes": 0,
      "proved_claims": 0, "empirical_claims": 0, "underdetermined_claims": 0},
    "artifacts": ["input", "ops_trace", "structural_observations", "equivalence_claims",
      "grammar_hypotheses", "heldout_eval", "checks", "manifest"]
  }
}
```

Числа в примере ответа `0` — **плейсхолдеры контракта**, а не результаты запуска.

`white_star_symbolic_inspect` (либо расширенный существующий inspect без breaking change) должен отдавать страницы `view=summary|input|operations|observations|claims|grammar|evaluation|report|export` с `offset`, `limit`, `total`, `next_offset`. Нельзя отдавать непроверенные литературные интерпретации как математические факты. `white_star_symbolic_replay` (либо существующий replay с типизированным bundle) воспроизводит data-only экспорт.

## 4. Формат атомарного свидетельства

```json
{
  "claim_id": "C0001",
  "kind": "proved_exact",
  "relation": "same_sp_normal_form",
  "left_word_id": "w01",
  "right_word_id": "w02",
  "observer_scope": ["sp_reduce"],
  "witness": {
    "left_original": "SSPP",
    "right_original": "SPSP",
    "left_reduction_steps": [[1, 2], [0, 1]],
    "right_reduction_steps": [[0, 1], [0, 1]],
    "normal_form": "",
    "source_spans": []
  },
  "assumptions": ["SP/PS cancellation grammar"],
  "non_claims": ["literal_word_equality", "semantic_equivalence"]
}
```

Индексация позиций в событиях редукции — **по текущей строке, с 0**, детерминированный leftmost pair. В `SSPP` сначала удаляется центральная пара (индексы 1,2), затем оставшаяся (0,1). У `SPSP` последовательно (0,1) и (0,1).

`kind` допускает `observed`, `proved_exact`, `empirical`, `conjecture`, `interpretation`. Любое `proved_exact` обязано иметь машинно проверяемый сертификат либо тестируемую воспроизводимую операцию. Система не может подменять `empirical` на `proved_exact` на основании частоты.

## 5. Структурная новизна без скрытого скаляра

Пусть у кандидата есть конечный набор наблюдаемых **отношений-свидетелей** `W(s)` и множество уже обнаруженных свидетелей `H_t`. Полезная новизна кандидата — множество `N_t(s)=W(s)\H_t`. Можно сравнивать два кандидата отношением включения `N_t(s1)⊂N_t(s2)` и приоритетом новых классов различимости; для несравнимых — стабильный seed-зависимый выбор или зарегистрированная локальная эвристика. Нельзя публиковать «общую смысловую новизну» в виде произвольного числа без определения и абляции.

Нельзя генерировать все слова до `L`: число растёт как `|Σ|^L`. Кандидаты образуются ограниченными локальными преобразованиями и повторно используют выученные различающие контексты. Обязательно включить тест budget exhaustion и halt.

## 6. Грамматическая гипотеза и отложенная оценка

```json
{
  "grammar_hypothesis": {
    "id": "G01", "status": "EMPIRICAL", "formalism": "finite_context_relation",
    "train_source_ids": ["train1"], "rules": [], "support_witness_ids": [],
    "counterexample_ids": [], "complexity": {"rule_count": 0},
    "prediction_interface": "membership_or_next_token"
  },
  "heldout_eval": {
    "visibility": "sealed_until_freeze", "test_source_ids": [],
    "metrics": ["heldout_membership_accuracy", "next_token_logloss", "description_length"],
    "baselines": ["unigram", "bigram", "simple_context"],
    "status": "UNASSESSED"
  }
}
```

Пример — контракт, а не достигнутые результаты. `description_length` допустим как **метрика оценки**, но не как замена полного символьного состояния. Если грамматика неидентифицируема по данным, вернуть `UNDERDETERMINED` и как минимум две различимые гипотезы, совместимые с train.

## 7. Инварианты и свойства по уровням

Тесты должны явно указывать уровень, на котором сохраняется инвариант:

| Трансформация | Что обязано сохраняться | Что не обязано |
|---|---|---|
| Биективное переименование алфавита | α-класс, отношения равенства токенов | буквальные метки, S/P-смысл без переназначения ролей |
| Глобальная S↔P (только S/P) | нулевость q, модуль q, формы парных проверок с указанной дуальностью | знак q, raw-числовые CAD веса |
| Перестановка компонентов ab↔ba | сумма q, общая длина и счётчики S/P | исходное слово, префиксная история |
| Вставка SP/PS | q и нормальная форма | длина, история, локальные контексты |
| Конкатенация со split | буквальное слово после обратной склейки | идентичность provenance DAG, если операции логируются |
| Смена КАД-наблюдателя | объект и provenance | наблюдаемые проекции, числовые признаки |

Требуемый результат: отчёт с фактическими свидетельствами **и указанием уровня эквивалентности**. Цель — поиск закономерностей, а не принуждение всех графовых β₁-чисел совпадать при изменении ориентации.
