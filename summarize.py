#!/usr/bin/env python3
"""Summarize the corrected DEAL v1.2 paired raw/GBNF benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import statistics
from typing import Any


HERE = pathlib.Path(__file__).resolve().parent
CATEGORY_ORDER = [
    "arithmetic", "conditional", "boolean", "numeric_loop", "array",
    "array_boolean", "array_nullable", "nested_array", "nullable",
    "stdlib_string", "stdlib_math", "class",
]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def profile_summary(rows: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    selected = [row for row in rows if row["profile"] == profile]
    n = len(selected)
    evaluation_count = lambda key: sum(
        bool(row["evaluation"].get(key)) for row in selected
    )
    tokens = [float(row["generated_tokens"]) for row in selected]
    generation_ms = [float(row["generation_ms"]) for row in selected]
    prompt_ms = [float(row["prompt_eval_ms"]) for row in selected]
    total_server_ms = [float(row["total_server_ms"]) for row in selected]
    pressure_steps = sum(int(row.get("pressure_steps") or 0) for row in selected)
    rejected_steps = sum(int(row.get("rejected_argmax_steps") or 0) for row in selected)
    functional = evaluation_count("functional_pass")
    return {
        "model": selected[0]["model"],
        "parameters_b": selected[0]["model_parameters_b"],
        "quantization": selected[0]["quantization"],
        "profile": profile,
        "tasks": n,
        "functional_passes": functional,
        "functional_pass_at_1": rate(functional, n),
        "syntax_passes": evaluation_count("syntax_success"),
        "syntax_rate": rate(evaluation_count("syntax_success"), n),
        "compile_passes": evaluation_count("compile_success"),
        "compile_rate": rate(evaluation_count("compile_success"), n),
        "strict_gbnf_passes": sum(bool(row["strict_gbnf_validity"]) for row in selected),
        "strict_gbnf_rate": rate(sum(bool(row["strict_gbnf_validity"]) for row in selected), n),
        "normalized_gbnf_passes": sum(bool(row["normalized_gbnf_validity"]) for row in selected),
        "normalized_gbnf_rate": rate(sum(bool(row["normalized_gbnf_validity"]) for row in selected), n),
        "fence_outputs": sum(bool(row["fence_normalized"]) for row in selected),
        "fence_rate": rate(sum(bool(row["fence_normalized"]) for row in selected), n),
        "token_limit_outputs": sum(bool(row["hit_token_limit"]) for row in selected),
        "token_limit_rate": rate(sum(bool(row["hit_token_limit"]) for row in selected), n),
        "prompt_tokens_mean": statistics.mean(float(row["prompt_tokens"]) for row in selected),
        "output_tokens_mean": statistics.mean(tokens),
        "output_tokens_p50": statistics.median(tokens),
        "output_tokens_p95": percentile(tokens, 0.95),
        "prompt_eval_ms_mean": statistics.mean(prompt_ms),
        "generation_ms_mean": statistics.mean(generation_ms),
        "generation_ms_p50": statistics.median(generation_ms),
        "generation_ms_p95": percentile(generation_ms, 0.95),
        "generation_ms_max": max(generation_ms),
        "server_ms_mean": statistics.mean(total_server_ms),
        "aggregate_generation_tokens_per_second": sum(tokens) / (sum(generation_ms) / 1000.0),
        "mean_run_tokens_per_second": statistics.mean(float(row["generated_tokens_per_second"]) for row in selected),
        "weighted_argmax_rejection_rate": rate(rejected_steps, pressure_steps),
        "server_ms_per_correct": sum(total_server_ms) / functional,
        "correct_programs_per_server_minute": functional / (sum(total_server_ms) / 60_000.0),
    }


def category_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["task_id"], row["profile"]): row for row in rows}
    result: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        task_ids = sorted({row["task_id"] for row in rows if row["category"] == category})
        raw = [indexed[(task_id, "deal-raw")] for task_id in task_ids]
        constrained = [indexed[(task_id, "deal-constrained")] for task_id in task_ids]
        raw_passes = sum(row["evaluation"]["functional_pass"] for row in raw)
        constrained_passes = sum(row["evaluation"]["functional_pass"] for row in constrained)
        rescued = sum(
            not indexed[(task_id, "deal-raw")]["evaluation"]["functional_pass"]
            and indexed[(task_id, "deal-constrained")]["evaluation"]["functional_pass"]
            for task_id in task_ids
        )
        harmed = sum(
            indexed[(task_id, "deal-raw")]["evaluation"]["functional_pass"]
            and not indexed[(task_id, "deal-constrained")]["evaluation"]["functional_pass"]
            for task_id in task_ids
        )
        raw_ms = [float(row["generation_ms"]) for row in raw]
        constrained_ms = [float(row["generation_ms"]) for row in constrained]
        result.append({
            "category": category,
            "tasks": len(task_ids),
            "raw_passes": raw_passes,
            "raw_pass_at_1": rate(raw_passes, len(task_ids)),
            "constrained_passes": constrained_passes,
            "constrained_pass_at_1": rate(constrained_passes, len(task_ids)),
            "constraint_delta_percentage_points": 100.0 * rate(constrained_passes - raw_passes, len(task_ids)),
            "rescued_by_constraints": rescued,
            "harmed_by_constraints": harmed,
            "raw_syntax_rate": rate(sum(row["evaluation"]["syntax_success"] for row in raw), len(raw)),
            "constrained_syntax_rate": rate(sum(row["evaluation"]["syntax_success"] for row in constrained), len(constrained)),
            "raw_compile_rate": rate(sum(row["evaluation"]["compile_success"] for row in raw), len(raw)),
            "constrained_compile_rate": rate(sum(row["evaluation"]["compile_success"] for row in constrained), len(constrained)),
            "raw_generation_ms_p50": statistics.median(raw_ms),
            "constrained_generation_ms_p50": statistics.median(constrained_ms),
            "constrained_generation_ms_p95": percentile(constrained_ms, 0.95),
            "raw_aggregate_tokens_per_second": sum(float(row["generated_tokens"]) for row in raw) / (sum(raw_ms) / 1000.0),
            "constrained_aggregate_tokens_per_second": sum(float(row["generated_tokens"]) for row in constrained) / (sum(constrained_ms) / 1000.0),
        })
    return result


def write_csv(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pc(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=HERE / "results/raw-results.jsonl")
    parser.add_argument("--output-dir", type=pathlib.Path, default=HERE / "results")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    keys = {(row.get("model"), row.get("profile"), row.get("task_id")) for row in rows}
    assert len(rows) == 1600 and len(keys) == 1600
    assert not any(row.get("request_error") for row in rows)
    assert {row["deal_commit"] for row in rows} == {"58a6dd3aeafc06168f2010c07d0aeae84d5364f3"}
    assert {row["profile"] for row in rows} == {"deal-raw", "deal-constrained"}

    summaries = [profile_summary(rows, profile) for profile in ("deal-raw", "deal-constrained")]
    categories = category_summaries(rows)
    validator_path = args.output_dir / "validator-throughput.csv"
    validator = None
    if validator_path.exists():
        with validator_path.open(encoding="utf-8", newline="") as handle:
            validator = next(csv.DictReader(handle), None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "summary.csv", summaries)
    write_csv(args.output_dir / "category-summary.csv", categories)

    raw, constrained = summaries
    indexed = {(row["task_id"], row["profile"]): row for row in rows}
    task_ids = sorted({row["task_id"] for row in rows})
    both = sum(indexed[(task_id, "deal-raw")]["evaluation"]["functional_pass"] and indexed[(task_id, "deal-constrained")]["evaluation"]["functional_pass"] for task_id in task_ids)
    rescued = sum(not indexed[(task_id, "deal-raw")]["evaluation"]["functional_pass"] and indexed[(task_id, "deal-constrained")]["evaluation"]["functional_pass"] for task_id in task_ids)
    harmed = sum(indexed[(task_id, "deal-raw")]["evaluation"]["functional_pass"] and not indexed[(task_id, "deal-constrained")]["evaluation"]["functional_pass"] for task_id in task_ids)
    neither = len(task_ids) - both - rescued - harmed

    report = [
        "# Corrected DEAL v1.2 benchmark — 0.63B",
        "",
        "## Validity and environment",
        "",
        "- 800 frozen hidden tasks, 800 raw runs, and 800 grammar-constrained runs; seed 42, greedy decoding, 512 output-token limit, prompt cache disabled.",
        "- The only inference difference between paired runs is the supplied DEAL GBNF constraint.",
        "- Reference gate: 800/800 reference implementations compile and pass all hidden runtime tests.",
        "- Functional evaluation removes at most one outer Markdown code fence, then uses the real DEAL compiler and LuaJIT runtime. Fence violations remain separately counted.",
        "- DEAL compiler: `arkts-dev/deal` commit `58a6dd3aeafc06168f2010c07d0aeae84d5364f3` (v1.2).",
        "- llama.cpp: commit `030ebb558a5820b444a8f836ed5cdd46c9b4bd7a`, Metal on Apple M4 Pro, macOS 26.5.2 arm64.",
        "- Model: Qwen2.5-Coder-0.5B-Instruct control, 0.63017B parameters, Q4_K_M, 397,808,128-byte GGUF.",
        "- Grammar SHA-256: `3b7a47c2079ccfc0d772091080c6410fbb17a7f0913ee5e122cdcfc109b78ecb`.",
        "",
        "## Grammar recognizer throughput",
        "",
        (
            f"The in-process llama.cpp recognizer checked 800 canonical DEAL reference programs for {validator['rounds']} rounds "
            f"({validator['programs']} recognitions) with {validator['failures']} failures in {float(validator['seconds']):.2f} seconds: "
            f"**{float(validator['programs_per_second']):.1f} programs/s** and {float(validator['mib_per_second']):.4f} MiB/s. "
            "This excludes process startup and measures GBNF whole-program recognition, not compiler parse/type-check throughput."
            if validator else
            "Not measured; run `benchmark_deal_validator.py` before the summarizer."
        ),
        "",
        "## Overall result",
        "",
        "| Mode | Correct programs (Success@1) | Parser syntax | Full compile | Out tok mean / p50 / p95 | Gen ms mean / p50 / p95 | Aggregate tok/s | Argmax rejected |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        label = "Raw" if summary["profile"] == "deal-raw" else "Constrained"
        report.append(
            f"| {label} | {summary['functional_passes']}/800 ({pc(summary['functional_pass_at_1'])}) "
            f"| {pc(summary['syntax_rate'])} | {pc(summary['compile_rate'])} "
            f"| {summary['output_tokens_mean']:.1f} / {summary['output_tokens_p50']:.0f} / {summary['output_tokens_p95']:.0f} "
            f"| {summary['generation_ms_mean']:.1f} / {summary['generation_ms_p50']:.1f} / {summary['generation_ms_p95']:.1f} "
            f"| {summary['aggregate_generation_tokens_per_second']:.1f} "
            f"| {pc(summary['weighted_argmax_rejection_rate'])} |"
        )
    report.extend([
        "",
        f"Constraints add **{100.0 * (constrained['functional_pass_at_1'] - raw['functional_pass_at_1']):.1f} percentage points** of Success@1 ({raw['functional_passes']} → {constrained['functional_passes']}, {constrained['functional_passes'] / raw['functional_passes']:.2f}× as many correct programs). They reduce mean output tokens by {100.0 * (1.0 - constrained['output_tokens_mean'] / raw['output_tokens_mean']):.1f}%, but increase median generation latency by {100.0 * (constrained['generation_ms_p50'] / raw['generation_ms_p50'] - 1.0):.1f}% and mean latency by {100.0 * (constrained['generation_ms_mean'] / raw['generation_ms_mean'] - 1.0):.1f}% because of a long constraint-pressure tail.",
        "",
        "## Operational efficiency",
        "",
        "| Mode | Prompt eval mean ms | Total server mean ms | Server ms per correct program | Correct programs per server minute |",
        "|---|---:|---:|---:|---:|",
        f"| Raw | {raw['prompt_eval_ms_mean']:.1f} | {raw['server_ms_mean']:.1f} | {raw['server_ms_per_correct']:.1f} | {raw['correct_programs_per_server_minute']:.1f} |",
        f"| Constrained | {constrained['prompt_eval_ms_mean']:.1f} | {constrained['server_ms_mean']:.1f} | {constrained['server_ms_per_correct']:.1f} | {constrained['correct_programs_per_server_minute']:.1f} |",
        "",
        "## Paired outcome",
        "",
        "| Both correct | Rescued by constraints | Harmed by constraints | Neither correct | Net gain |",
        "|---:|---:|---:|---:|---:|",
        f"| {both} | {rescued} | {harmed} | {neither} | +{rescued - harmed} |",
        "",
        "## System-level comparison with VERA-L G1",
        "",
        "| Language pipeline | Raw Success@1 | Constrained Success@1 | Constraint gain |",
        "|---|---:|---:|---:|",
        "| VERA-L v0.0 + G1 + VERA frontend | 291/800 (36.4%) | 346/800 (43.2%) | +6.9 pp |",
        f"| DEAL v1.2 + supplied `deal.gbnf` + DEAL compiler | {raw['functional_passes']}/800 ({pc(raw['functional_pass_at_1'])}) | {constrained['functional_passes']}/800 ({pc(constrained['functional_pass_at_1'])}) | +{100.0 * (constrained['functional_pass_at_1'] - raw['functional_pass_at_1']):.1f} pp |",
        "",
        "This is a comparison of two complete language pipelines, not an isolated grammar A/B test: DEAL and VERA-L have different prompts, surfaces, semantics, grammars, and compilers. The same 800 task specifications and the same 0.63B model are used, so it answers which tested pipeline produced more correct programs, but it does not prove that one GBNF is intrinsically better.",
        "",
        "## Success@1 by task type",
        "",
        "| Task type | n | Raw | Constrained | Delta | Rescued | Harmed | Raw compile | Constrained compile |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in categories:
        report.append(
            f"| {row['category']} | {row['tasks']} | {row['raw_passes']} ({pc(row['raw_pass_at_1'])}) "
            f"| {row['constrained_passes']} ({pc(row['constrained_pass_at_1'])}) "
            f"| {row['constraint_delta_percentage_points']:+.1f} pp | {row['rescued_by_constraints']} | {row['harmed_by_constraints']} "
            f"| {pc(row['raw_compile_rate'])} | {pc(row['constrained_compile_rate'])} |"
        )
    report.extend([
        "",
        "## Performance by task type",
        "",
        "| Task type | Raw gen p50 ms | Constrained gen p50 ms | Constrained p95 ms | Raw aggregate tok/s | Constrained aggregate tok/s |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in categories:
        report.append(
            f"| {row['category']} | {row['raw_generation_ms_p50']:.1f} | {row['constrained_generation_ms_p50']:.1f} "
            f"| {row['constrained_generation_ms_p95']:.1f} | {row['raw_aggregate_tokens_per_second']:.1f} "
            f"| {row['constrained_aggregate_tokens_per_second']:.1f} |"
        )
    report.extend([
        "",
        "## Interpretation",
        "",
        "`Success@1` means that the first and only deterministic response compiled with the real DEAL v1.2 compiler, executed under LuaJIT, and passed every hidden input/output assertion for that task. No compiler repair, retry, or LLM judge was used.",
        "",
        "`Parser syntax` only means that the DEAL parser reported no E1xxx lexical/parse error after optional outer-fence removal. It does not imply resolved names, correct types, successful compilation, or correct behavior.",
        "",
        "The constrained syntax rate is 98.25%, not 100%, because 16 outputs reached the 512-token cap. Every one of the 784 non-truncated constrained outputs passed DEAL syntax; 14 truncated outputs were syntactically incomplete.",
        "",
        "The grammar is strongly beneficial for array and nullable syntax, but it is not uniformly beneficial. It loses all raw successes on `stdlib_string` and `stdlib_math`: the grammar can enforce surface form, but not that `strings`/`math` is imported before use or that a generated member is a declared API. Several math outputs also enter long, grammar-forced continuations after copying API descriptions, producing the latency tail. Class tasks fail in both modes because this small model emits a second `solve` declaration from the prompt example.",
        "",
        "For this exact 0.63B configuration, constrained decoding is the better choice when first-attempt reliability matters (52.75% vs 35.38%). It is not the better choice for maximum batch throughput: aggregate generation throughput falls from 222.2 to 67.4 tokens/s, and correct programs per server minute falls from 53.6 to 34.5 because a minority of high-pressure outputs are extremely slow.",
        "",
        "## Next grammar experiment",
        "",
        "1. Keep the language grammar task-independent, but add a canonical, globally valid standard-library namespace/member subset and test missing-import behavior with semantic compilation.",
        "2. Remove or refactor high-branching expression paths that let a rejected JavaScript method chain degrade into long but still grammatically viable output; use per-token rejection traces from the array families as the regression corpus.",
        "3. Add compiler-diagnostic repair as a separate measured pass for duplicate declarations, missing imports, unknown members, and token-limit failures. Do not count repair as Success@1.",
        "4. Re-run the same frozen 800 tasks with the revised grammar and require no regression in raw prompting, stdlib categories, parser throughput, p95 latency, or functional Success@1.",
        "",
    ])
    (args.output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
