# The grammar prevents the repair it makes necessary

**Observed with:** Qwen2.5-Coder-0.5B-Instruct, DEAL compiler 73b93e6.

> **Narrowed by `when-repair-works.md`.** On 1.5B the mechanism below is
> real but not the whole story: it decides the outcome only when the first
> attempt is a plausible module the model would simply reproduce. Shown a
> visibly broken one, the same model repairs it under the same grammar.

A compiler-guided repair pass yields nothing under the `constrained` profile,
and the reason is not that the model cannot make the edit.

## The edit is within reach

Given a module missing `export` and the instruction to add it, the model
**unconstrained** produces the correct fix:

```
To add the `export` keyword before `function` in the code, you need to declare
the function as an exportable function. Here's how you can modify the code:

```javascript
export function makeCounter(start: int): () => int {
```

Prose first, then a fenced block containing the corrected module. The edit is
right; the packaging is wrong.

## The grammar forbids the packaging

Under the grammar the output must be a DEAL module from the first token. The
model's natural repair behaviour — explain, then show the code — has no legal
prefix. Blocked from its usual path, it falls back to re-emitting the input
verbatim: byte-identical output, every time, on every prompt shape tried
(instruction before the code, instruction after it, missing names listed
explicitly).

So the profile that produces most of the repairable failures is also the one
that cannot act on the diagnostics.

## What this is not

Not a defect in the diagnostics. The message handed to the model was rewritten
to name the missing exports in its own terms, and the result did not change.
Not a prompt-shape problem either: three shapes, same output.

## What it suggests

Repair and grammar-constrained decoding want different output contracts. Three
directions, untested:

* run the repair pass **unconstrained** and strip the Markdown fence, keeping
  the grammar for first attempts only — the stand already strips one outer
  fence, so this costs nothing structurally;
* allow a leading comment run in the grammar so the model has a legal place to
  put its preamble;
* accept that repair is not available at this model size and revisit with a
  larger model, where instruction-following is less fragile.

The stand measures the yield either way: `--repair-rounds N` records repair as
its own stage, never folded into Success@1.
