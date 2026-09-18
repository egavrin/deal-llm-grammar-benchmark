# A module that exports nothing compiles clean

**Severity:** silently useless artifact; measurement hazard.

Both modules the model got to compile in the first end-to-end run dropped the
`export` keyword:

```deal
function makeCounter(start: int): () => int {   // no `export`
  let count = start;
  ...
}
```

The compiler accepts this without a diagnostic — it is valid DEAL. Nothing can
use the module:

```
E2004: Export 'makeCounter' not found in module 'candidate'. Available:
```

The `Available:` list is empty. A module whose every declaration is unexported
has no reason to exist, yet nothing says so at compile time.

**Why it matters for the stand.** Before the interface rung existed, these two
counted as compile successes, and the headline read "2/14 compiled". They are in
fact unusable: the real figure is 0/14 modules that expose what was asked for.
A compile-only measurement overstates the result, and by exactly the amount the
model forgets one keyword.

**Worth considering for the language.** A warning for a module with no exported
declarations would catch this at the source. It is a plausible human mistake
too — the failure surfaces only at the import site, in another file.

Observed with DEAL compiler 73b93e6, Qwen2.5-Coder-0.5B, constrained decoding.
