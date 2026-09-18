# DEAL language test stand

Measures how much of the DEAL language a model can actually write, and what
constraining decoding with a GBNF grammar costs.

The stand is one function of three inputs:

```
prompts + grammar + compiler  ->  benchmark result
```

Each input is swappable on its own. Nothing has a built-in default: an input you
did not set produces an error naming what to set, never a silent fall back to
somebody else's path.

This lives beside the published `deal-llm-grammar-benchmark` and does not touch
it — `grammar/`, `bench/`, `results/`, `manifest.json` and
`.github/workflows/audit.yml` stay frozen and independently verifiable.

## Quick start

Linux x64. Everything installs under `.deps/` and `models/`; no sudo, no
system packages.

```bash
test_stand/bin/setup_linux.sh        # JDK 25, LuaJIT, llama.cpp, the pinned DEAL compiler, a model
python3 test_stand/benchmark.py check --preset v12-baseline      # gates, no model involved
python3 test_stand/benchmark.py run   --preset v12-baseline --out test_stand/results/today
```

The run ends by printing its report and writing `summary.json`, `report.txt`
and `cost.csv` next to `raw.jsonl`. To measure your own compiler checkout
instead of the pinned one, set `DEAL_COMPILER=/path/to/deal` before running
setup, or write it into `test_stand/.env`. To see what would run without
running it: `python3 test_stand/benchmark.py doctor --preset v12-baseline`.

Two finished runs live in `test_stand/samples/` so you can read a result
before installing anything:

```bash
python3 test_stand/report.py  test_stand/samples/2026-09-03-coder-1.5b-prompts2
python3 test_stand/compare.py test_stand/samples/2026-09-03-coder-1.5b test_stand/samples/2026-09-03-coder-1.5b-prompts2
```

## The three inputs

### Prompts — a directory of task directories

A prompt set is self-contained, so swapping it swaps everything task-related at
once:

```
prompts/v12/
  primer.txt              the language description, with {example} and {task}
  example.deal            one complete module the primer shows, see below
  system.txt              the chat system message
  repair.txt              the compiler-guided repair prompt
  order_total/
    brief.md              what the model is asked for
    reference.deal        a correct solution
    test.deal             hidden checks (see below)
    support/              modules the brief says already exist
```

A brief states each requested export as a signature line, followed by what it
must do, and puts anything about *how* to write it — "walk the array with a
counting loop" — on a separate `Constraints:` line. The first is the task; the
second is there to elicit a language atom, and keeping them apart keeps that
visible. Wherever a hidden test checks a case the prose left open, the brief
says what happens there, because a task failed on interpretation says nothing
about the language.

`example.deal` is the one complete module the primer shows. Small models copy
shape far more than they follow rules, so the shape has to be on the page. It
is written in a domain no task uses, and `benchmark.py check` enforces that
neither it nor the primer mentions a task id or any name a task asks the model
to export — otherwise part of the answer would be sitting in the question. The
example must also compile and be accepted by the grammar, so the model is shown
real DEAL. Its hash is part of the fingerprint.

`reference.deal` earns its place twice. It defines the coverage denominator —
which language constructs this prompt set can actually elicit — and it is the
oracle a `test.deal` compares the model's answer against, so tests hold inputs
rather than hand-computed expected values.

Because references are written in the language, a prompt set is tied to a
dialect: swapping the grammar reuses the same set, while a language branch with
different syntax needs its own.

### Grammar — one GBNF file

Checked before any run: it must parse, accept every reference in the prompt set,
and accept every valid module in the compiler's own conformance corpus.

### Compiler — a DEAL checkout

Set once as `DEAL_COMPILER` in `test_stand/.env`, or passed per-run with
`--compiler`. Resolution order, the same for every entry point:

```
--flag  ->  --preset file  ->  test_stand/.env  ->  error
```

### Model

The model is a fourth input, resolved the same way: `--model`, then the
preset, then `DEAL_STAND_MODEL` in `.env`, then an error. `test_stand/models.json`
is the registry; a preset names an entry from it rather than restating a path.

```bash
python3 test_stand/models.py list                       # what the registry knows, what is on disk
python3 test_stand/models.py fetch qwen2.5-coder-1.5b-official   # download a ready GGUF, verify its hash
test_stand/bin/prepare_model.sh qwen2.5-coder-0.5b      # or convert from the original weights (needs torch)
```

Entries with a `url` are Qwen's own GGUF releases, downloaded and checked
against the hash in the registry. Entries with only a `repo` are converted
locally at a pinned revision, the published benchmark's conversion-control
path. Either way the file's SHA-256 goes into every run's fingerprint, so
switching models forces a rerun instead of mixing generations from two of
them, and a provenance record — repo, revision, quantization, hash, whether it
matches the registry and the published build — is written beside the file and
copied into each run's `inputs.json`.

### Presets

A preset is a saved set of the three inputs, for convenience only:

```bash
python3 test_stand/benchmark.py run --preset v12-baseline --out results/today
```

Presets run on Qwen2.5-Coder-0.5B, and so does a run that names no model at
all; `report.py` and `doctor` mark the model, and a defaulted one says so.
Pass `--model qwen2.5-coder-1.5b` or use the `v12-1.5b` preset for the larger
pair.

* `v12-baseline` — the compiler's main branch with a grammar corrected against
  it; accepts 280/280 valid modules in the conformance corpus.
* `v12-published-grammar` — same language and prompts, with the grammar as
  published alongside the raw-vs-GBNF benchmark; accepts 167/280. Kept as the
  A/B counterpart showing what grammar fidelity buys.
* `v12-1.5b` — everything as `v12-baseline`, on Qwen2.5-Coder-1.5B instead of
  the default 0.5B. Three times the parameters, to tell "the language is hard
  to generate" apart from "the model is small".
* `v12-lean` — the same language on `grammars/deal-v1.2-lean.gbnf`, which
  bounds comment length and run, string and template length. A looping model
  then hits the grammar instead of the token cap. Still 280/280 fixtures;
  `findings/lean-grammar-bounds.md` has the measurements.

## Regeneration actually regenerates

Every result row carries a fingerprint of the inputs it came from: the grammar,
the primer, the briefs, the compiler commit, the model, and the decoding
parameters. Resume compares that fingerprint, not just the task name.

* same inputs, same `--out` — finished generations are reused and the run says
  how many;
* **any input changed** — the run refuses to append, names what differs, and
  exits 2. Reusing them would report old generations under new inputs;
* `--fresh` — regenerate in place, discarding what was there.

The same rule applies to derived artefacts. The AST walker used for coverage is
rebuilt whenever the walker source *or* the compiler's AST changes, so it cannot
silently measure against an old language. Toolchain steps in `setup_linux.sh`
are cached by the ref they were built from, so changing a pinned commit rebuilds;
`--force` rebuilds regardless.

## Gates

Run after any language change, before trusting a number. No model involved,
about 20 seconds.

```bash
test_stand/bin/gates.sh              # builds the compiler, then runs check
python3 test_stand/benchmark.py check
```

**References compile.** A brief whose reference does not compile is an
impossible task, not a hard one.

**No leakage.** The primer and its example compile, pass the grammar, and share
no identifier with any task id or exported name. The primer teaches the
language; it never teaches the tasks.

**Corpus completeness.** The references must exercise every in-scope language
atom. The universe is derived from `deal/ast/*.java`, `BinaryOp`, `UnaryOp`,
`deal/types/Type.java` and `std/*.d.deal`, so it grows with the language and a
stale corpus cannot pass unnoticed. Four atoms are out of scope with the reason
recorded in `coverage.py`: they belong to declaration files and the C FFI
surface, which no module prompt can reach.

**Grammar fidelity.** Only the accept side is enforced. A grammar that rejects a
valid program actively blocks the model from writing correct code; one that
accepts a malformed program merely fails to help. The reject side is reported —
it cannot be required, because once comments are in the grammar a malformed
`// @deal-version ...` is indistinguishable from an ordinary comment.

## The ladder

A generation is scored by how far up it got. Each rung is a share of the tasks,
measured separately for the unconstrained and the constrained profile.

| Rung | Means |
|---|---|
| no fence | the answer is source, not a Markdown code block |
| syntax | the compiler reports no `E1xxx` |
| compiles | names resolved, types checked, lowering succeeded |
| interface | the hidden test binds against it — the requested exports are there |
| runs | LuaJIT executed the test to its verdict, pass or `DIFF` |
| passes | the module agreed with the reference on every input |

A test reports a mismatch as `throw { code: "DIFF", message: "<which check>" }`.
The stand runs the entry under a small Lua wrapper that catches an uncaught
DEAL error and prints its code and message, so a failed assertion lands on
`passes` with the name of the check in the report, while any other uncaught
error — the module throwing, a runtime fault — lands on `runs`. Without the
wrapper LuaJIT prints only `(error object is not a string)` and the two are
indistinguishable.

When the evaluator changes, re-score stored generations instead of
regenerating identical text or comparing runs scored two different ways:

```bash
python3 test_stand/reevaluate.py results/today --preset v12-baseline
```

It keeps the previous `raw.jsonl` beside the new one and refuses to re-score
under a compiler other than the one recorded in `inputs.json`.

**compiles** is the headline for language design: it separates hitting the
language from hitting only its grammar. **passes** is the end-to-end answer.

The split between *compiles* and *interface* is deliberate. Phase one compiles
the module behind an entry that only imports it, so `compiles` keeps meaning
what it always meant. Phase two compiles the hidden test against it, so a module
that is valid DEAL but exports the wrong thing fails on its own rung instead of
quietly depressing the compile rate.

A task with no hidden test — currently `fetch_pipeline`, whose exports are all
`async` and unreachable from a synchronous entry module — is measured up to
`compiles` and excluded from the last three rungs. It is never counted as a pass
and never silently dropped from the denominator; `prompts/v12/fetch_pipeline/NO_TEST.md`
records why.

## Repair

A compiler-guided second pass is available and off by default:

```bash
python3 test_stand/benchmark.py run --repair-rounds 1 --out results/today
```

A failed generation is shown its own module and the compiler's complaint, and
asked to fix it. Repair rows are a separate `stage` in `raw.jsonl` and are
reported in their own section — **Success@1 stays Success@1**, or nothing is
comparable with earlier runs.

The diagnostics handed to the model are restated in terms of the module it
wrote. Raw compiler output on an interface failure names a temporary path and an
entry module the model never saw, which reads as errors in someone else's file.

Two guards. A repair that returns byte-identical text is marked
`repair_stalled` and the loop stops — greedy decoding on a similar prompt
reproduces itself readily. And the report shows, per diagnostic code, how often
it was seen and how often it was cleared: a code that never yields to repair is
a code that does not tell its reader what to do, which is a property of the
message as much as of the model.

`prompts/v12/repair.txt` is part of the prompt set, since what to say about an
error depends on the language.

## Reading a result

```bash
python3 test_stand/report.py  results/today           # latency, solve@<=k, cost, baseline delta
python3 test_stand/compare.py results/before results/after   # what changed, task by task
python3 test_stand/show.py    results/today --list    # one line per generation
python3 test_stand/show.py    results/today --task-id tic_tac_toe
```

A result directory holds `raw.jsonl` (one row per generation), `inputs.json`
(the fingerprint of what produced it, and the model's provenance),
`summary.json` (coverage and levels as data, which `compare.py` reads),
`report.txt` and `cost.csv`. `report.py` renders from `raw.jsonl` and
`summary.json` together, so a result can be read on a machine with no compiler
and no model; `report.py --recompute` rebuilds `summary.json`, which needs the
toolchain because coverage re-parses every generated module with the compiler's
own AST walker.

`report.txt` answers four questions and nothing else: how long a generation
takes (time to first and last token, prefill and decode rates, split by whether
the prompt hit the server's cache), how many tasks are solved using k
compiler-guided repair rounds or fewer, what an attempt and a success cost, and
how all of that compares with the unconstrained profile — same tasks, same
seeds, same retry loop, the grammar being the only difference. Pass
`--repair-rounds 5` to fill the solve@<=k curve; without it every task is
measured at k=0 only.

`compare.py` pairs two runs by (task, profile): the inputs that differ, the
tasks that moved up or down a rung, the atoms gained and lost, the cost
deltas. A rate that went from 2/34 to 3/34 says less than which task moved
and from where.

Coverage of language atoms is the primary measure: with 34 tasks, pass/fail
gives 34 observations per profile while atoms give 99. Compilation is the
headline level — it means names resolved, types checked and lowering
succeeded, which is what separates hitting the language from hitting only its
grammar.

## Tests

The stand's own tests run without the toolchain and are what CI runs:

```bash
python3 -m pytest -q test_stand/tests
```

They cover fence stripping, the runner's error line, outcome naming, resume
and refuse-to-mix, the prompt set's structure, the no-leakage rule with a
negative case, report rendering against a stored sample, and compare on two
samples. Anything that needs a compiler is a gate in `benchmark.py check`,
not a test.

## Convince yourself

```bash
test_stand/bin/prove.sh              # inference is local; the grammar binds
unshare -rn bash -c 'ip link set lo up; test_stand/bin/prove.sh'   # no network
```

Then break the gates on purpose and watch them fail:

```bash
# remove one reference: coverage drops and names the atom it lost, exit 1
mv test_stand/prompts/v12/packet_buffer/reference.deal /tmp/
python3 test_stand/benchmark.py check --preset v12-baseline
mv /tmp/reference.deal test_stand/prompts/v12/packet_buffer/

# feed the grammar something that is not DEAL: it points at the character
printf 'export const f = (a) => a + 1;\n' > /tmp/js.deal
.deps/llama.cpp/build/bin/test-gbnf-validator \
  test_stand/grammars/deal-v1.2.gbnf /tmp/js.deal
```

## Caveats

Timings are CPU-only on a shared workstation. Compare profiles within one run;
never against the Metal-based published benchmark. Token counts are
deterministic under greedy decoding; wall-clock is not.
