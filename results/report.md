# Corrected DEAL v1.2 benchmark — 0.63B

## Validity and environment

- 800 frozen hidden tasks, 800 raw runs, and 800 grammar-constrained runs; seed 42, greedy decoding, 512 output-token limit, prompt cache disabled.
- The only inference difference between paired runs is the supplied DEAL GBNF constraint.
- Reference gate: 800/800 reference implementations compile and pass all hidden runtime tests.
- Functional evaluation removes at most one outer Markdown code fence, then uses the real DEAL compiler and LuaJIT runtime. Fence violations remain separately counted.
- DEAL compiler: `arkts-dev/deal` commit `58a6dd3aeafc06168f2010c07d0aeae84d5364f3` (v1.2).
- llama.cpp: commit `030ebb558a5820b444a8f836ed5cdd46c9b4bd7a`, Metal on Apple M4 Pro, macOS 26.5.2 arm64.
- Model: Qwen2.5-Coder-0.5B-Instruct control, 0.63017B parameters, Q4_K_M, 397,808,128-byte GGUF.
- Grammar SHA-256: `3b7a47c2079ccfc0d772091080c6410fbb17a7f0913ee5e122cdcfc109b78ecb`.

## Grammar recognizer throughput

The in-process llama.cpp recognizer checked 800 canonical DEAL reference programs for 10 rounds (8000 recognitions) with 0 failures in 27.36 seconds: **292.4 programs/s** and 0.0402 MiB/s. This excludes process startup and measures GBNF whole-program recognition, not compiler parse/type-check throughput.

## Overall result

| Mode | Correct programs (Success@1) | Parser syntax | Full compile | Out tok mean / p50 / p95 | Gen ms mean / p50 / p95 | Aggregate tok/s | Argmax rejected |
|---|---:|---:|---:|---:|---:|---:|---:|
| Raw | 283/800 (35.4%) | 67.4% | 47.9% | 62.7 / 63 / 118 | 282.2 / 283.8 / 557.2 | 222.2 | 0.0% |
| Constrained | 422/800 (52.8%) | 98.2% | 71.4% | 53.3 / 45 / 97 | 790.6 / 342.5 / 1850.2 | 67.4 | 3.4% |

Constraints add **17.4 percentage points** of Success@1 (283 → 422, 1.49× as many correct programs). They reduce mean output tokens by 15.1%, but increase median generation latency by 20.7% and mean latency by 180.1% because of a long constraint-pressure tail.

## Operational efficiency

| Mode | Prompt eval mean ms | Total server mean ms | Server ms per correct program | Correct programs per server minute |
|---|---:|---:|---:|---:|
| Raw | 113.6 | 395.9 | 1119.0 | 53.6 |
| Constrained | 126.8 | 917.5 | 1739.3 | 34.5 |

## Paired outcome

| Both correct | Rescued by constraints | Harmed by constraints | Neither correct | Net gain |
|---:|---:|---:|---:|---:|
| 183 | 239 | 100 | 278 | +139 |

## System-level comparison with VERA-L G1

| Language pipeline | Raw Success@1 | Constrained Success@1 | Constraint gain |
|---|---:|---:|---:|
| VERA-L v0.0 + G1 + VERA frontend | 291/800 (36.4%) | 346/800 (43.2%) | +6.9 pp |
| DEAL v1.2 + supplied `deal.gbnf` + DEAL compiler | 283/800 (35.4%) | 422/800 (52.8%) | +17.4 pp |

This is a comparison of two complete language pipelines, not an isolated grammar A/B test: DEAL and VERA-L have different prompts, surfaces, semantics, grammars, and compilers. The same 800 task specifications and the same 0.63B model are used, so it answers which tested pipeline produced more correct programs, but it does not prove that one GBNF is intrinsically better.

## Success@1 by task type

| Task type | n | Raw | Constrained | Delta | Rescued | Harmed | Raw compile | Constrained compile |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| arithmetic | 96 | 78 (81.2%) | 94 (97.9%) | +16.7 pp | 18 | 2 | 82.3% | 97.9% |
| conditional | 112 | 32 (28.6%) | 34 (30.4%) | +1.8 pp | 2 | 0 | 58.0% | 58.9% |
| boolean | 48 | 48 (100.0%) | 48 (100.0%) | +0.0 pp | 0 | 0 | 100.0% | 100.0% |
| numeric_loop | 96 | 5 (5.2%) | 4 (4.2%) | -1.0 pp | 4 | 5 | 5.2% | 66.7% |
| array | 176 | 20 (11.4%) | 112 (63.6%) | +52.3 pp | 103 | 11 | 33.0% | 91.5% |
| array_boolean | 32 | 16 (50.0%) | 32 (100.0%) | +50.0 pp | 16 | 0 | 50.0% | 100.0% |
| array_nullable | 32 | 0 (0.0%) | 24 (75.0%) | +75.0 pp | 24 | 0 | 0.0% | 100.0% |
| nested_array | 48 | 0 (0.0%) | 42 (87.5%) | +87.5 pp | 42 | 0 | 0.0% | 87.5% |
| nullable | 32 | 2 (6.2%) | 32 (100.0%) | +93.8 pp | 30 | 0 | 50.0% | 100.0% |
| stdlib_string | 80 | 66 (82.5%) | 0 (0.0%) | -82.5 pp | 0 | 66 | 82.5% | 0.0% |
| stdlib_math | 32 | 16 (50.0%) | 0 (0.0%) | -50.0 pp | 0 | 16 | 93.8% | 0.0% |
| class | 16 | 0 (0.0%) | 0 (0.0%) | +0.0 pp | 0 | 0 | 0.0% | 0.0% |

## Performance by task type

| Task type | Raw gen p50 ms | Constrained gen p50 ms | Constrained p95 ms | Raw aggregate tok/s | Constrained aggregate tok/s |
|---|---:|---:|---:|---:|---:|
| arithmetic | 202.4 | 140.0 | 259.7 | 216.3 | 168.2 |
| conditional | 197.4 | 179.3 | 347.1 | 213.7 | 152.9 |
| boolean | 136.7 | 127.3 | 160.5 | 214.0 | 170.5 |
| numeric_loop | 295.5 | 1248.2 | 1845.0 | 218.9 | 48.4 |
| array | 329.8 | 636.9 | 11021.5 | 227.2 | 36.3 |
| array_boolean | 295.4 | 299.7 | 319.7 | 227.0 | 149.9 |
| array_nullable | 307.6 | 292.7 | 664.0 | 227.6 | 140.0 |
| nested_array | 353.8 | 1250.3 | 1828.7 | 219.1 | 62.4 |
| nullable | 374.9 | 873.9 | 1343.7 | 223.7 | 71.5 |
| stdlib_string | 182.4 | 120.8 | 2019.2 | 229.5 | 57.4 |
| stdlib_math | 180.2 | 2434.2 | 5080.9 | 229.6 | 117.5 |
| class | 465.0 | 617.8 | 747.0 | 224.5 | 164.9 |

## Interpretation

`Success@1` means that the first and only deterministic response compiled with the real DEAL v1.2 compiler, executed under LuaJIT, and passed every hidden input/output assertion for that task. No compiler repair, retry, or LLM judge was used.

`Parser syntax` only means that the DEAL parser reported no E1xxx lexical/parse error after optional outer-fence removal. It does not imply resolved names, correct types, successful compilation, or correct behavior.

The constrained syntax rate is 98.25%, not 100%, because 16 outputs reached the 512-token cap. Every one of the 784 non-truncated constrained outputs passed DEAL syntax; 14 truncated outputs were syntactically incomplete.

The grammar is strongly beneficial for array and nullable syntax, but it is not uniformly beneficial. It loses all raw successes on `stdlib_string` and `stdlib_math`: the grammar can enforce surface form, but not that `strings`/`math` is imported before use or that a generated member is a declared API. Several math outputs also enter long, grammar-forced continuations after copying API descriptions, producing the latency tail. Class tasks fail in both modes because this small model emits a second `solve` declaration from the prompt example.

For this exact 0.63B configuration, constrained decoding is the better choice when first-attempt reliability matters (52.75% vs 35.38%). It is not the better choice for maximum batch throughput: aggregate generation throughput falls from 222.2 to 67.4 tokens/s, and correct programs per server minute falls from 53.6 to 34.5 because a minority of high-pressure outputs are extremely slow.

## Next grammar experiment

1. Keep the language grammar task-independent, but add a canonical, globally valid standard-library namespace/member subset and test missing-import behavior with semantic compilation.
2. Remove or refactor high-branching expression paths that let a rejected JavaScript method chain degrade into long but still grammatically viable output; use per-token rejection traces from the array families as the regression corpus.
3. Add compiler-diagnostic repair as a separate measured pass for duplicate declarations, missing imports, unknown members, and token-limit failures. Do not count repair as Success@1.
4. Re-run the same frozen 800 tasks with the revised grammar and require no regression in raw prompting, stdlib categories, parser throughput, p95 latency, or functional Success@1.
