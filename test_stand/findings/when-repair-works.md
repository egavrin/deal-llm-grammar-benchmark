# Repair works when the model can see its own wreckage

**Supersedes the conclusion of `grammar-blocks-repair.md`**, which was measured
on Qwen2.5-Coder-0.5B with the v1 prompts and concluded that repair is
unavailable under the constrained profile. On 1.5B the mechanism it describes
is real but not universal.

Two measurements, same model (Qwen2.5-Coder-1.5B Q4_K_M), same compiler
(73b93e6), one repair round each.

| | quick tier, base grammar | four stalled tasks, grammar v1.3b |
|---|---|---|
| repair attempts, constrained | 11 | 4 |
| returned byte-identical text | **11** | **0** |
| moved up to `syntax` | 0 | **3** |
| moved up to `passes` | 0 | **1** |
| repair attempts, raw | 19 | 4 |
| returned byte-identical text, raw | 2 | 4 |
| cost | 6 064 tokens, 953 s | 1 571 tokens, 169 s |

## The rule

Repair yields nothing when the first attempt is *plausible* — a complete
module that simply means the wrong thing. Greedy decoding on a prompt that
contains that module reproduces it: eleven of eleven, byte for byte. The model
has nothing to react to.

Repair yields a lot when the first attempt is *visibly broken*. The four
stalled generations end in nine hundred tokens of whitespace after
`for (let i: int` (see `removed-alternative-stalls-decoding.md`). Shown that,
the model does not reproduce it — it rewrites the loop as `for ... of` and
three of four recover, one all the way to a passing test.

So the earlier finding's claim, that the grammar blocks the model's natural
"explain, then show the code" packaging, holds; but it only decides the outcome
when the model has no other reason to deviate from its previous answer.

## The diagnostic pointed the wrong way and it recovered anyway

The compiler is still v1.2 and still has the counting loop, so on a stalled
generation it says:

```
E1013: Expected '=' initializer in for-loop variable
```

That is precisely the character grammar v1.3b forbids. Three of the four
repairs succeeded in spite of the advice, not because of it: the model read its
own truncated module rather than the message. The fourth took the advice, wrote
the diagnostic text into the source as a comment, and stalled again:

```deal
for (let i: int | null  // E1013: Expected '=' initializer in for-loop variable
  // E1006: Expected '}'  (line 5, column 1005)
  // E1006: Expected '}'  (line 5, column 1005)
```

**A language version change has to change the compiler's messages with it.**
A diagnostic written for the old language is not merely unhelpful under the new
grammar; it is an instruction to emit a forbidden token.

## Should repair be on by default

The comparability objection does not apply: repair rows carry their own
`stage`, the ladder counts first attempts only, and the report gives repair its
own section. Turning it on cannot move a headline number.

What remains is cost, which is proportional to failures, and failures are the
subject. Roughly it doubles a run.

Standing recommendation, not yet implemented: one round by default on the quick
tier, where it costs about five minutes and is the only measurement of whether
the compiler's diagnostics are actionable; zero by default on the module tier,
where it turns forty minutes into seventy.

## Strength of the evidence

The negative result is solid: eleven of eleven identical outputs is not noise,
and greedy decoding makes it exactly reproducible. The positive result rests on
four tasks. It is enough to retire "repair does nothing", not enough to put a
rate on it.
