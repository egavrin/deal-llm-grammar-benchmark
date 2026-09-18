# The lean grammar changes nothing measurable on Coder-1.5B

**Runs:** `2026-09-03-c34-1.5b-q4` (v12-baseline) against `2026-09-03-c34-1.5b-lean`
(v12-lean), 34 module tasks, prompts v2, Qwen2.5-Coder-1.5B Q4_K_M, greedy,
1024 tokens. The only input that differs is the grammar hash.

| constrained, of 34 | baseline | lean |
|---|---:|---:|
| syntax | 28 | 29 |
| compiles | 6 | 6 |
| interface | 6 | 6 |
| runs | 5 | 5 |
| passes | 2 | 2 |
| hit the token cap | 6 | 6 |
| atoms in compiled code | 65 | 65 |
| generation time, s | 983 | 910 |

One task moved: queue_ring from *parse failed* to *syntax*. The six answers
that hit the cap are the same six tasks under both grammars: chain_list,
grade_book, matrix_ops, queue_ring, status_report, tic_tac_toe. The raw
profile is byte-identical, as it must be.

## Why the bounds did not bite

`findings/lean-grammar-bounds.md` predicted this case. The loops this model
falls into on this corpus repeat *code* — a statement, a method chain, a
whole function — line after line. Every line is valid DEAL, so a bound on
comment length, comment runs or string length never engages. The two loop
shapes the bounds do stop, hundreds of consecutive comment lines and a
thousand-character string literal, were seen on the 14-task corpus with
prompts v1 and with the 0.5B model; on 34 tasks with prompts v2 and 1.5B they
did not occur.

## What follows

- Keep `v12-lean` as a preset; it costs nothing and is still the right
  grammar for a smaller model or a prompt without an example. It is not the
  default.
- Loops of code are a decoding problem, not a grammar problem: a repetition
  penalty or a lower token cap would address them, and both are sampling
  changes that must be recorded in the fingerprint before they are compared.
- The grammar's contribution is exactly where it was: syntax 8 → 28 of 34
  paired tasks rescued, nothing above compiles separated.
