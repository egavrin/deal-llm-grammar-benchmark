# The worked example earns its passes by being copied

**Runs:** quick tier, 28 one-function tasks, Qwen2.5-Coder-1.5B Q4_K_M, greedy,
1024 tokens, grammar v12-baseline. Three primers, one input changed at a time.

| primer | profile | syntax | compiles | passes | atoms | copies | tokens | gen s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| example, no instruction about it | raw | 16 | 10 | **9** | 54 | 14 | 6 625 | 507 |
| | constrained | 27 | 20 | **17** | 63 | 14 | 7 099 | 368 |
| example framed as unrelated, "do not copy" | raw | 13 | 5 | **5** | 34 | 0 | 1 675 | 77 |
| | constrained | 27 | 14 | **11** | 58 | 0 | 2 670 | 153 |
| no example at all | raw | 6 | 2 | **2** | 22 | 0 | 1 860 | 82 |
| | constrained | 26 | 10 | **8** | 54 | 0 | 3 768 | 227 |

## What happened

With the first primer, half the answers reproduced the example module verbatim
— all six of its exports, about 300 tokens — and then appended a correct
solution. Under the constrained profile 13 of those 14 copies passed their
test, against 4 of the 14 answers that did not copy.

Telling the model the example belongs to an unrelated project and must not be
copied worked: copies went to zero. Passes fell with them, 17 to 11
constrained and 9 to 5 raw. Removing the example entirely costs more again:
8 and 2.

So the example does two separate jobs. As a reference it is worth about 3
passes constrained (8 → 11). As something to transcribe first it is worth
another 6 (11 → 17). The second job is the larger one, and it is the one that
costs four times the tokens and three times the wall clock.

## Reading it

Transcribing 300 tokens of valid DEAL immediately before answering is
test-time compute: the model spends generation putting the language's shape
into its own context, where it weighs far more than the same shape sitting in
the prompt. Nothing is leaked — `benchmark.py check` proves the example shares
no name with any task, and the appended solution is the model's own.

What is wrong with it is the answer, not the measurement: a module that
exports `plantNamed`, `labelOf`, `waterByName`, `thirstyNames` and `report`
alongside the requested function is not what anybody asked for. The hidden
test binds to the requested export and passes regardless.

It also inflates coverage. Atoms are a union over answers, so the effect is
smaller than the copy rate suggests — 63 against 58 constrained — but it is
real, and the report now names it rather than correcting for it.

## Decision

The stand keeps the primer that forbids copying. The number it reports is
then the model writing DEAL, not the model transcribing DEAL, which is what
the stand exists to measure. The cheaper, cleaner primer is also the honest
one.

The 17-pass configuration stays on the record here because it answers a
different and useful question: how much a small model gains from a warm-up
pass it generates itself. If that is worth pursuing it belongs in the runner
as an explicit two-phase protocol with its own cost reported, not as an
accident of prompt wording.
