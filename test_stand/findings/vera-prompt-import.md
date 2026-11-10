# VERA prompt contribution: duplicate audit and DEAL adaptation

## Scope and provenance

Audited all **62 tasks in 25 categories** from `vera-llm-bench/prompts.py`
against the **28 existing DEAL v1.2 quick tasks** at benchmark commit
`026aec8`. The source directory was supplied by the contributor; it is not a
runtime dependency. The adjacent [JSON inventory](vera-prompt-import.json)
records every original prompt, category, focus tags, source ID, disposition,
target task, and the SHA-256 of both source files (`prompts.py` and
`refs.vera.txt`). References here are DEAL adaptations, not executable copies
of the VERA programs.

**Result: 11 duplicates omitted, 51 tasks added directly to
`prompts/v12/quick/`, using the original source IDs.** There is no VERA wrapper
directory or prefix. The quick tier grows from 28 to **79 tasks**; the full
v1.2 set grows from 62 to **113**. The published experiment and v1.3 prompt
sets are unchanged.

## Duplicate policy

Compare the computational behavior and requested interface, not task names or
fixed demonstration inputs. Renaming exports, changing constants, encoding a
sign as words instead of integers, or printing a result does not create a new
task. Complementary parity counts are one behavior. A genuinely additional
operation (filtering and formatting, callbacks, mutation, parsing, structured
results, or nested nullable access) is retained even if it uses a familiar
loop or predicate.

This audit is against **quick**, as requested, not the module tier. Therefore
small versions of existing module-tier subjects (accounts, closure factories,
traffic lights, rectangle area) remain eligible. New imports were also checked
against each other; none differ only by the presentation changes above.

| Source task | Existing quick task | Why omitted |
|---|---|---|
| `int_div` | `quotient_or_null` | Already tests truncation toward zero for signed integer division; fixing divisor 2 is specialization. |
| `void_greet` | `greeting_for` | Same greeting; printing it is presentation, not new independently checked behavior. |
| `arr_reverse` | `reversed_ints` | Same new reversed array and unchanged input. |
| `let_swap` | `swap_pair` | Same exchange of two integers; locals/record fields are packaging. |
| `str_vowels` | `vowel_count` | Same lowercase-vowel count. |
| `tern_sign` | `sign_of` | Same three-way sign classification, different output encoding. |
| `tern_parity` | `even_count` | Same parity predicate; printing labels adds no new API. |
| `nul_default` | `or_default` | Same nullable fallback, changing int to string. |
| `sw_day` | `day_label` | Same day lookup and unknown fallback, differing in indexing, case and range. |
| `bit_odd` | `even_count` | Complementary parity counting, not a new algorithm or API. |
| `nest_digits` | `digit_sum` | Same digit sum; the VERA reference itself hoists the helper, contrary to the prompt's impossible nested-recursion requirement. |

The JSON inventory is the exhaustive 62-row audit, including retained tasks.
For example, `arr_evens` remains distinct from `even_count`: it must select,
preserve order, convert values to decimal text, and place separators correctly.
`ds_default` combines greeting construction with a nullable default;
`nul_chain` must traverse a nullable class field rather than just return a
fallback scalar. `json_encode` uses a generated class encoder, unlike
`person_json`'s table serializer.

## Adaptation rules

- Replace fixed complete programs and stdout grading with exported functions,
  parameterized inputs and hidden comparisons against `reference.deal`.
  `void_range` preserves the null-returning procedure and output order through
  an injected callback, so its effects can be checked without changing the
  evaluator to capture stdout.
- Use DEAL imports (`std/string`, `std/math`, `std/json`), typed class defaults,
  `// @jsonable`, array indexing/appends, and explicit in-branch null narrowing.
  Do not carry over the VERA-specific forbidden-syntax detectors: DEAL permits
  several constructs VERA disallows.
- DEAL's pinned std/string has no int-to-string or int-parsing API. Numeric
  formatting tasks extract the scalar encoding from a one-field `std/json`
  object using `std/string`. The briefs state this available route. Integer
  parsing similarly wraps a scalar token in an object and validates the field
  as int; malformed JSON, null, non-integral values and out-of-range integers
  fail. The domain excludes object fragments. This is an explicit DEAL
  adaptation, not a claim of identical VERA parsing rules.
- DEAL's `int(number)` checks integrality rather than truncating. `num_to_int`
  first floors positive Celsius values or ceils negative ones, then converts.
- `exc_name` returns DEAL's `Error.code` (`E8004` for int32 overflow), not
  VERA's exception name. Other exception tasks preserve the actual runtime
  operation and catch it, rather than replacing it with a pre-check.
- `uni_age` and `uni_sensor` preserve the source references' record-based
  representation of success/error alternatives; they do not request unsupported
  non-null union types. `top_const` uses a named function for a shared constant;
  `top_visits` passes state explicitly. `ds_default` uses null rather than
  an unsupported optional/default argument.
- Constraints intended to elicit an implementation form (loops, local lambda,
  try/catch, shared-rate call) are separate from behavior in the brief. Hidden
  tests check behavior, not a regex-based proof that the model used that form.

## Testability

**49 additions have hidden functional tests.** They import candidate and oracle
separately, throw `DIFF` on mismatch, and print one `__DEAL_BENCH_PASS__` on
success. Tests cover the original examples plus empty, negative, boundary,
invalid, tie, mutation, or independence cases where relevant. JSON comparisons
ignore object key order. State/callback tasks check observable side effects and
null results, not just compilation.

**`async_basic` and `async_sum` are compile-only**, explicitly documented with
`NO_TEST.md`, following the existing `fetch_pipeline` convention. The stand's
synchronous hidden entry cannot await async exports. They contribute neither
runtime nor functional passes; adding an external async driver is deliberately
outside this prompt-only contribution. The full v1.2 set therefore has three
compile-only tasks, and the quick tier has two.

The prompt-set structural/export/leakage tests now include the quick tier as
well as modules. An inventory test ensures every source task is accounted for,
all target directories exist, and imported tasks have references and either
hidden tests or the two explicit async exclusions.

## Validation

On Linux x64, using the pinned DEAL compiler `73b93e60ebe9`, JDK 25,
LuaJIT, and the pinned llama.cpp GBNF validator `030ebb558a58`:

```bash
/usr/bin/python3 -m pytest -q test_stand/tests
python3 test_stand/benchmark.py check --preset v12-baseline
```

Results:

- **37 unit tests passed.**
- **110 task references passed their hidden tests**; the other three tasks
  (`fetch_pipeline`, `async_basic`, `async_sum`) compiled and explicitly reported
  no test.
- **114/114 references** (113 tasks plus the worked example) accepted by the
  grammar; **280/280 valid compiler fixtures** accepted.
- Language-atom coverage remained **99/99**; primer/example leakage checks passed.
- The frozen manifest verification and published-results audit both passed.
- A manual mutation check rejected nine deliberately wrong candidates: input
  mutation in map/concatenation, counter increments by two, no-op deposits,
  returning a negative value instead of its index, wrong split delimiter,
  flooring negative Celsius, encoding an empty JSON object, and clearing a
  stack on pop. This checks that reference agreement is not an automatic pass;
  the mutations are not part of the task corpus.

No model inference is needed for these checks; no generation results or
performance claims are contributed. Future runs have a different prompt
fingerprint and should use a new result directory.
