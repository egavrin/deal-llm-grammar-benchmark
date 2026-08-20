# DEAL LLM Grammar Benchmark

Reproducible raw-versus-GBNF constrained-generation benchmark for
[DEAL v1.2](https://github.com/arkts-dev/deal), using an untuned 0.63B code
model, `llama.cpp` Metal inference, the real DEAL compiler, LuaJIT execution,
and 800 hidden functional tasks.

The benchmark answers a narrow question:

> How much does grammar-constrained decoding improve first-attempt functional
> correctness for a very small local code model, and what does it cost in
> tokens, latency, and throughput?

## Headline result

Model: **Qwen2.5-Coder-0.5B-Instruct**, 0.63017B parameters, conversion-control
GGUF, Q4_K_M, 397.8 MB.

| Mode | Correct programs, Success@1 | DEAL syntax | Full compile | Output tokens mean / p50 / p95 | Generation ms mean / p50 / p95 | Aggregate tok/s |
|---|---:|---:|---:|---:|---:|---:|
| Raw | **283/800 — 35.4%** | 67.4% | 47.9% | 62.7 / 63 / 118 | 282.2 / 283.8 / 557.2 | **222.2** |
| GBNF constrained | **422/800 — 52.8%** | 98.2% | 71.4% | 53.3 / 45 / 97 | 790.6 / 342.5 / 1,850.2 | **67.4** |
| Constraint effect | **+139 programs, +17.4 pp, 1.49×** | +30.9 pp | +23.5 pp | −15.1% mean | +20.7% p50, +180.1% mean | −69.7% |

Constraints substantially improve one-shot correctness, especially for arrays
and nullable values, but the supplied grammar has a severe latency tail and
regresses the standard-library tasks. It is useful evidence for constrained
decoding, not a claim that this grammar is production-optimal.

The full analysis is in [`results/report.md`](results/report.md). Raw records,
including every prompt/output timing, diagnostic, and functional result, are in
[`results/raw-results.jsonl`](results/raw-results.jsonl).

## Metric definitions

- **Success@1 / correct program:** the first and only deterministic model
  response compiles with the pinned DEAL v1.2 compiler, executes through
  LuaJIT, and passes every hidden input/output assertion for that task. There is
  no retry, repair pass, or LLM judge.
- **DEAL syntax:** the DEAL compiler reports no `E1xxx` lexical or parse error
  after removing at most one outer Markdown code fence. Syntax does not imply
  resolved names, valid types, successful compilation, or correct behavior.
- **Full compile:** parsing, name and module resolution, type checking, and
  backend lowering all succeed.
- **Aggregate tok/s:** total generated tokens divided by total generation time,
  so slow constraint-pressure outliers are included.
- **Argmax rejection:** on constrained runs, the fraction of decoding steps for
  which the grammar rejected the model's otherwise most probable token.

## Functional results by task family

| Task family | n | Raw Success@1 | Constrained Success@1 | Delta |
|---|---:|---:|---:|---:|
| Arithmetic | 96 | 81.2% | **97.9%** | +16.7 pp |
| Conditionals | 112 | 28.6% | **30.4%** | +1.8 pp |
| Boolean | 48 | **100.0%** | **100.0%** | 0.0 pp |
| Numeric loops | 96 | **5.2%** | 4.2% | −1.0 pp |
| Arrays | 176 | 11.4% | **63.6%** | +52.3 pp |
| Boolean arrays | 32 | 50.0% | **100.0%** | +50.0 pp |
| Nullable arrays | 32 | 0.0% | **75.0%** | +75.0 pp |
| Nested arrays | 48 | 0.0% | **87.5%** | +87.5 pp |
| Nullable flow | 32 | 6.2% | **100.0%** | +93.8 pp |
| String stdlib | 80 | **82.5%** | 0.0% | −82.5 pp |
| Math stdlib | 32 | **50.0%** | 0.0% | −50.0 pp |
| Classes | 16 | 0.0% | 0.0% | 0.0 pp |

See [`results/category-summary.csv`](results/category-summary.csv) for compile,
syntax, latency, throughput, rescued-task, and harmed-task counts by family.

## Frozen experiment

| Component | Frozen value |
|---|---|
| Hardware | Apple M4 Pro, 24 GB unified memory |
| OS | macOS 26.5.2, arm64 |
| Inference | llama.cpp Metal, commit [`030ebb5`](https://github.com/ggml-org/llama.cpp/commit/030ebb558a5820b444a8f836ed5cdd46c9b4bd7a) |
| Compiler | DEAL v1.2, commit [`58a6dd3`](https://github.com/arkts-dev/deal/commit/58a6dd3aeafc06168f2010c07d0aeae84d5364f3) |
| Runtime | LuaJIT |
| Model source | [`Qwen/Qwen2.5-Coder-0.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct), revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25` |
| GGUF | conversion control, Q4_K_M, SHA-256 `5231325088f468169793028bd680f714548fe36977f89f0fc64fbdffeb519220` |
| Tasks | 800 frozen tasks; 800/800 reference implementations pass the compiler/runtime gate |
| Runs | 800 raw + 800 constrained |
| Sampling | greedy, seed 42, temperature 0, 512 max output tokens |
| Context | 4,096 tokens |
| Prompt cache | disabled |
| Grammar | fixed for every task; SHA-256 `3b7a47c2079ccfc0d772091080c6410fbb17a7f0913ee5e122cdcfc109b78ecb` |

All pinned revisions, parameters, hashes, and artifact provenance are also in
[`manifest.json`](manifest.json).

## Repository layout

```text
bench/tasks.jsonl                    800 task specs, references, hidden tests
config/models.json                   pinned model metadata and GGUF hash
grammar/deal-v1.2.gbnf              supplied, task-independent DEAL grammar
prompts/deal-v1.2.txt                common generation prompt
deal_v12_eval.py                     compile -> LuaJIT -> hidden-test evaluator
run_benchmark.py                     paired llama-server raw/constrained runner
summarize.py                         aggregate and category report generator
benchmark_validator.py              in-process GBNF recognition benchmark
tools/gbnf_throughput.cpp            llama.cpp grammar recognizer harness
scripts/                             dependency, model, audit, and run scripts
results/raw-results.jsonl            all 1,600 published run records
results/summary.csv                  two-row headline summary
results/category-summary.csv         task-family breakdown
results/validator-throughput.csv     grammar recognizer throughput
results/report.md                    complete findings and interpretation
manifest.json                        frozen configuration and SHA-256 values
```

Model weights, dependency checkouts, compiler classes, virtual environments,
and local server logs are intentionally excluded from Git.

## Verify the published artifacts

This requires only Python 3:

```bash
git clone https://github.com/egavrin/deal-llm-grammar-benchmark.git
cd deal-llm-grammar-benchmark

python3 scripts/verify_manifest.py
python3 scripts/audit_results.py results/raw-results.jsonl --expect-published
python3 summarize.py
```

Expected audit counts:

```text
deal-raw {"compile_success": 383, "functional_pass": 283, "syntax_success": 539}
deal-constrained {"compile_success": 571, "functional_pass": 422, "syntax_success": 786}
```

The checked-in raw result file is a publication-safe copy of the original. The
only transformations were replacement of machine-local absolute paths and
ephemeral temporary-directory names. Generated programs, timing data,
diagnostics, and outcomes were not changed. Both original and published hashes
are recorded in `manifest.json`.

## Full reproduction on Apple Silicon

### 1. Install system requirements

The exact performance reproduction targets an Apple Silicon Mac with Metal.
The functional pipeline also requires Java 25 and LuaJIT.

```bash
brew install cmake luajit openjdk@25

export PATH="$(brew --prefix openjdk@25)/bin:$PATH"
java -version
luajit -v
cmake --version
```

Also ensure `git`, Xcode Command Line Tools, and Python 3 are available.

### 2. Build pinned llama.cpp with Metal

```bash
scripts/build_llama.sh
```

This checks out the exact llama.cpp commit and builds:

- `llama-server`;
- `llama-cli`;
- `llama-quantize`;
- `test-gbnf-validator`.

The script prints the discovered devices. The exact target should include:

```text
MTL0: Apple M4 Pro
```

### 3. Build the pinned DEAL compiler

```bash
scripts/build_deal.sh
```

The compiler is checked out under `.deps/deal`, pinned to the commit used by the
published run, and compiled with `javac --release 25`.

### 4. Recreate the exact conversion-control GGUF

```bash
scripts/prepare_model.sh
```

This downloads the pinned untouched Hugging Face model, converts it with the
pinned llama.cpp converter, quantizes it to Q4_K_M, and requires the resulting
GGUF to match the published SHA-256. The large F16 intermediate and final model
remain untracked under `models/`.

Verify it independently with:

```bash
python3 scripts/verify_manifest.py --model
```

### 5. Run all 1,600 generations and evaluate them

```bash
scripts/run_all.sh
```

Equivalent explicit commands:

```bash
python3 scripts/verify_references.py

python3 run_benchmark.py \
  --profiles deal-raw deal-constrained \
  --seed 42 \
  --max-tokens 512 \
  --output results/reproduced-results.jsonl

scripts/build_validator.sh

mkdir -p results/reproduced
python3 benchmark_validator.py \
  --rounds 10 \
  --output results/reproduced/validator-throughput.csv

python3 summarize.py \
  --input results/reproduced-results.jsonl \
  --output-dir results/reproduced

python3 scripts/audit_results.py results/reproduced-results.jsonl
```

The generation runner is resumable by `(model, profile, task_id)`. If it is
interrupted, rerun the same command and output path. Use a new output filename
for a statistically independent rerun.

Greedy text output should be reproducible with the pinned stack. Wall-clock
timings can vary with macOS version, temperature, power mode, and concurrent
system load, so compare latency distributions rather than requiring byte-exact
timing fields.

## Grammar recognizer throughput

The in-process llama.cpp recognizer accepted all 800 canonical DEAL reference
programs over 10 rounds:

| Recognitions | Failures | Time | Programs/s | MiB/s |
|---:|---:|---:|---:|---:|
| 8,000 | 0 | 27.36 s | **292.4** | 0.0402 |

This is whole-program GBNF recognition with process startup excluded. It is not
the DEAL compiler's parser/type-check throughput.

## Important methodological notes

1. The grammar is fixed and task-independent. It is not instantiated with the
   requested function signature or hidden test values.
2. The generation prompt and all non-grammar sampling parameters are identical
   between paired raw and constrained runs.
3. A single outer Markdown code fence is removed before functional evaluation;
   fence use is still separately recorded. Raw emitted fences in 800/800 runs.
4. Constrained syntax is 98.25%, rather than 100%, because 16 generations hit
   the 512-token cap. All 784 non-truncated constrained outputs passed DEAL
   syntax.
5. GBNF guarantees only membership in a context-free surface language. The real
   compiler and hidden runtime tests determine semantic and functional success.
6. No benchmark task was used for model fine-tuning in this experiment. The
   evaluated model is the untouched conversion control.
7. There is no repair pass in these numbers. A compiler-guided repair experiment
   must report its additional pass, latency, and token cost separately.

## Main findings

- Constraints rescued 239 tasks and harmed 100, for a net gain of 139 correct
  programs.
- The largest gains are nullable flow (`6.2% -> 100%`), nested arrays
  (`0% -> 87.5%`), nullable arrays (`0% -> 75%`), and arrays
  (`11.4% -> 63.6%`).
- Standard-library tasks regress because syntax constraints do not enforce the
  semantic relationship between namespace use, imports, and declared members.
- Array-task p95 constrained latency reaches 11 seconds when the grammar fights
  strongly against JavaScript-like continuations such as `.reduce(...)`.
- For this exact configuration, constrained decoding is better for first-attempt
  reliability; raw decoding is better for aggregate batch throughput.

The next experiment should preserve the array/nullable gains while adding a
task-independent canonical stdlib namespace/member layer, reducing high-branch
expression paths, and measuring compiler-guided repair as a separate pass.
