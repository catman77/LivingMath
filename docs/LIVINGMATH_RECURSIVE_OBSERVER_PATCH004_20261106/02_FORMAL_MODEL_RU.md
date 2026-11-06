# Формальная модель: проверяемый композиционный наблюдатель

## 1. Термины и семантические уровни

Пусть `Σ` — конечный алфавит, `Σ*` — конечные слова, `H` — конкретная неизменная история исходных операторов. Наблюдатель — типизированная программа композиции допустимых операций, интерпретируемая на каждом предъявленном исходном слове в заданных границах:

\[
\mathcal{O}=(A,\mathcal{D},\mathcal{P},\mathcal{C}),\qquad
\llbracket A\rrbracket_\mathcal{D}:\Sigma^*\rightharpoonup\{0,1\}.
\]

- `A`: конечный типизированный AST композиции над примитивами (не произвольный исполняемый код).
- `D`: область определения, в частности кодировка, ограничения токенов, версия операторов, permitted alphabet, max recursion depth. Вне D: `UNKNOWN`, а не False.
- `P`: immutable provenance: AST/hash, список примитивных operators, исходные source spans и train-only свидетельства.
- `C`: набор независимых *проверяемых* конечных свидетельств вычисления AST на указанных словах.

Три разных смысла достоверности:

1. `EXECUTION_CHECKED`: конечное вычисление AST и трасс корректно.
2. `TRAIN_COMPATIBLE`: наблюдаемое вычисление соответствует всем данным train. Не равно `PROVED_EXACT` обо всём языке.
3. `HOLDOUT_EVALUATED`: на независимых query-only примерах подсчитаны TP/TN/FP/FN, baseline; статистика не равна универсальному доказательству.

`UNIQUE_GRAMMAR_PROVED` запрещено без отдельного настоящего математического доказательства; по конечному train обычно `UNDERDETERMINED`.

## 2. Типы операционного ядра

Использовать существующие операции/типы, по возможности без новых примитивов:

- `Word`, `Atom`, `Fragment`, `Bool`, `SourceSpan`, `OperationTrace`;
- `SPLIT(Word, Position) -> (Word, Word)`; 
- `REVERSE(Word) -> Word`;
- `CONCAT(Word,Word) -> Word`;
- `literal_word_equality(Word,Word) -> Bool`;
- `AND(Bool,Bool) -> Bool`;
- выражение `POSITION_MIDPOINT` является *разрешённой структурной координатой разреза*, а не числовой проекцией слова/смысла;
- `CHECK_EVEN_LENGTH(Word) -> Bool`, допускает empty/odd guard без ложного отрицательного значения при выходе из области D.

Не допускать: произвольных callback/exec/eval, JSON-expression scripting, незарегистрированных operators, произвольной рекурсии без уменьшающейся меры и оговорённого лимита.

## 3. PAL как текущая train-compatible конструкция

Для пустого и односимвольного слова: `true`. Для `w=aub`, где `a,b∈Σ`:

\[
P(aub) = [a=b]\land P(u).
\]

Записать в AST текущего индуктора:

```json
{
  "composition": "iterate_on_inner_fragment",
  "trim_left": 1,
  "trim_right": 1,
  "fragment_operations": ["SPLIT", "SPLIT"],
  "relation": {
    "composition": "aligned_token_equality",
    "base_max_tokens": 1,
    "left_operations": ["SPLIT"],
    "right_operations": ["REVERSE", "SPLIT"],
    "offset": 0,
    "expected_equal": true
  }
}
```

Здесь `REVERSE+SPLIT` даёт последний атом оригинала; два последовательных `SPLIT` изолируют середину. В независимой проверке каждый шаг привязан к source spans и output hashes. Выполнять только при строго убывающей мере `|w|→|w|-2`.

Для самого **заданного** рекурсивного правила математически верно `P(w)⇔w=rev(w)` на всех конечных словах (индукция по длине). Но обнаружение этого правила из данных остаётся **эмпирическим выбором** среди конкурирующих train-compatible гипотез. Не присваивать гипотезе `universal_invariant=true` только из-за корректности формулы интерпретатора.

## 4. COPY как предлагаемое расширение пространства композиций

Для `w∈Σ*`:

\[
C(w)=[|w|\bmod 2=0]\land\operatorname{EqWord}
\left(w_{1:|w|/2}, w_{|w|/2+1:|w|}\right).
\]

Предлагаемый AST (не серверный результат):

```json
{
  "composition": "compare_fragments",
  "cut": {"operator": "SPLIT", "position": "MIDPOINT_EXACT_EVEN"},
  "comparison": "literal_word_equality",
  "expected_equal": true
}
```

Без чётности возвращает False для COPY *в пределах D*. У двух слов могут совпадать локальные частоты, однако `C(w)` различаться. Сравнивать именно две последовательности, не их скалярные хеши; хеш использовать лишь как сертификат с проверкой исходных байтов.

Новая грамматика candidates должна получать такой AST через общую композицию разрешённых типизированных операторов, а не через специальный production-флаг `COPY=true`.

## 5. Структура сертификата

Минимальная запись:

```
OperatorObserverCertificate(
  schema_version, ast, ast_digest, operator_bindings,
  declared_domain={max_tokens, alphabet, representation, normalization},
  source_dataset_refs, train_digest, train_sample_refs,
  construction_trace, execution_witnesses,
  witness_set_digest, verifier_version, verifier_digest,
  claim_status='CHECKED_FINITE_INSTANCE',
  universal_invariant=false, holdout_labels_read=false,
  provenance_origin='DERIVED_FROM_OPERATORS'
)
```

Для каждой записи в execution_witnesses сохранять полный исходный токенный порядок, UTF-8 байтовые span, шаги с input/output, operator ID и параметры; запрещена замена свидетеля простым хешем слова без проверяемого значения.

Независимый `verify` обязан пересчитать AST и трассу с нуля из исходных разрешённых байтов и pinned operations, не доверяя «verified=true». Изменение единственного шага, hash, UTF-8 span, позиции, оператора, метки, версии или области доказанности должно давать `REJECTED` и конкретную failed_obligation.

**Scope gate:** за пределами domain — `UNKNOWN`, `score=null`, `proof_status=NOT_PROVED`, без ложного «False». Отдельно предусмотреть `RESOURCE_LIMIT` (не трактовать как отрицательный класс).

## 6. Пример различий доказательного статуса

- AST (PAL) вычислен и равен разметке на 16 train: **TRAIN_COMPATIBLE**, но не теорема о всех словах.
- AST (PAL) воспроизведён независимым checker на 256 holdout: **CHECKED_FINITE_INSTANCE**, плюс эмпирическая оценка 256/256.
- Существуют другие регулярные/конечные грамматики, совпадающие с train и test, но отличающиеся вне этих конечных выборок: **UNDERDETERMINED**.
- COPY сравнивает равные половины: это точно вычислимое выражение, но сервер пока его **не нашёл**, и эталонная реализация не должна выдавать это за discovery.

## 7. Вне текущего патча

S/P-нуль как фактор по редукции `SP/PS→ε` и его фундаментальная группа — другой тип утверждения (комплексы с 2-клетками). Ни PAL, ни COPY не используют это сокращение. Нельзя переносить `π1`-сертификаты на грамматику или наоборот. Переход к языку Дика и структурам исторических текстов является отдельной экспериментальной фазой после успешного PAL/COPY.
