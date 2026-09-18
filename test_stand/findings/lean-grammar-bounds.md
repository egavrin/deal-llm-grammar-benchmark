# Comments cannot be removed from the grammar; they can be bounded

**Context:** with the v1.2 grammar, small models under greedy decoding loop
inside comments and string literals until the 1024-token cap: 3 of 14
constrained answers for Coder-0.5B, 2 of 14 for Coder-1.5B, with prompts v1;
4 and 2 with prompts v2. The grammar puts no bound on either channel.

## Why not just drop comments

Measured over the compiler's own conformance corpus, the 280 fixtures the
grammar gate must accept:

| | fixtures |
|---|---:|
| with a non-directive line comment | 57 |
| with a comment line inside a block | 17 |
| with a block comment | 1 |
| longest run of consecutive comment lines | 8 |
| longest comment, characters | 96 |
| longest string literal, characters | 99 |
| longest template literal, characters | 41 |

A grammar without comments rejects 57 valid modules. A grammar allowing one
comment per gap rejects about 30. Neither is the language.

## What `deal-v1.2-lean.gbnf` does instead

Every bound is the largest value the corpus uses, rounded up, so the gate
stays at 280/280 and 15/15 references:

- a line comment is at most 120 characters (`[^\r\n]{0,120}`);
- at most 8 comments in a row in one whitespace gap (`comment-run ::= (comment blank*){1,8}`);
- a string literal is at most 120 characters, a template literal at most 120 pieces;
- a block comment is at most 400 items.

Nothing else changes; the file is derived from the base grammar by a
substitution of five rules.

## What it can and cannot do

It stops the two loop shapes seen so far: hundreds of consecutive comment
lines (kv_cache, 1.5B) and a thousand-character string (tic_tac_toe, 0.5B).
It cannot stop a loop that repeats *code* with a short comment on every line
(order_total, 0.5B): that is valid DEAL line by line. Whether it changes
anything above the syntax rung is an empirical question; the answer is in the
compare of preset `v12-lean` against `v12-baseline` on the same model.
