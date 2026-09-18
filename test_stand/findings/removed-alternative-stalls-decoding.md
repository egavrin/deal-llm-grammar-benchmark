# Removing an alternative that shares a prefix stalls the decoder

**Runs:** quick tier, 28 one-function tasks, Qwen2.5-Coder-1.5B Q4_K_M, greedy,
1024 tokens. `2026-09-03-quick-g1-typed-let` against
`2026-09-03-quick-g2-no-cfor`, a rehearsal of a DEAL v1.3 that drops the
C-style `for (init; condition; update)` loop and keeps `for ... of` and
`while` (the VERA-L direction).

| constrained, of 28 | typed-let | no C-for |
|---|---:|---:|
| syntax | 27 | 23 |
| compiles | 14 | 11 |
| passes | 11 | **8** |
| hit the token cap | 1 | **5** |
| atoms in compiled code | 58 | 51 |

Four tasks fell from `passes` or `syntax` straight to `parse failed`:
first_index, largest_of, reversed_ints, word_join. All four hit the token cap.

## The mechanism

`for (let i: int` is a valid prefix of the surviving `for ... of` loop, so the
grammar lets the model start it. The model wants a counting loop and reaches
for `=` next. The grammar forbids it: the only continuation is ` of `. The
model's probability mass is elsewhere, so it emits the one token that is
always legal at that point — a space — and keeps emitting spaces until the
cap. The tail of each of the four answers is 800 characters of nothing else.

```
export function firstIndexOf(values: int[], target: int): int {
  for (let i: int                                              ← 900 tokens of spaces
```

The grammar never rejects anything: `ws ::= separator*` is unbounded, so
whitespace is an infinite legal escape hatch. The generation is grammatically
valid at every step and useless at the end.

## What this means for language design

Removing a construct is not free even when the replacement is strictly more
expressive. If the removed construct shares a prefix with a surviving one, a
greedy decoder walks into the prefix and cannot get out. The cost here was
three passes and four burned generations, on a change that a spec review would
call a simplification.

Two mitigations, both testable:

- **Bound whitespace runs in the grammar.** `findings/lean-grammar-bounds.md`
  bounded comments and string literals for exactly this class of problem and
  measured no effect, because the loops it stopped were not the loops that
  occurred. This is the case it was built for, and whitespace is the one
  channel it did not bound. A `ws` that allows at most a few consecutive
  separators would turn the stall into a forced ` of `.
- **Say it in the prompt.** The v13 primer shows `while` and `for ... of` but
  never says the counting loop is gone. A model that has seen a million
  counting loops needs to be told.

Neither is done yet; the finding is the measurement, not the fix.

A repair round recovers three of the four stalls, and the compiler's
diagnostic for them advises the one character the grammar forbids:
`when-repair-works.md` has that measurement.

## Incidental

The raw profile is unaffected as it must be — five raw answers still contain a
C-style loop, because no grammar constrains them — but raw is not
byte-identical to the previous run: the v13 prompt set changed the primer and
the example along with the grammar, so raw moved by three tasks on syntax.
That is why the two changes were run as separate steps: step 1 (typed `let`)
changed the grammar alone, and there raw was byte-identical.

## Step 1, for the record

Requiring a type annotation on `let` changed exactly four constrained answers,
the four that had written `let sum = 0;`, and moved no task on any rung. Under
the candidate grammar no answer has an untyped `let`; under the base grammar
four do. A clean, neutral change: the model complies and nothing else moves.
