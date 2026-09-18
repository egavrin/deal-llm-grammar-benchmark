#!/usr/bin/env python3
"""Summarise a stand run: latency, solve@<=k, cost, and the baseline delta.

Two halves, deliberately separate:

  compute(rows, config)   needs the toolchain — it re-parses every generated
                          module with the compiler's AST walker — and returns
                          one plain dict, which `compare.py` and `coverage.py`
                          read out of summary.json;
  render(summary, rows)   needs nothing but that dict and the attempts, and
                          prints the report.

`run` calls both at the end of every run and writes `summary.json`,
`report.txt` and `cost.csv` into the result directory, so a result can be read
by someone who has no compiler, no JDK and no model.

What the report answers, and nothing else:

  latency    time to first and last token, prefill and decode rates, split by
             whether the prompt hit the server's cache
  quality    how many tasks are solved using k compiler-guided repair rounds
             or fewer, k = 0..N, and how many are never solved at all
  cost       what one attempt costs, and what one success costs once the
             failures are paid for
  baseline   the same four against the unconstrained profile: same tasks, same
             seeds, same retry loop, grammar the only difference

An attempt is one generation: `initial`, then `repair-1` and up. A task is
solved at k if any attempt up to k reached the rung, and stays solved after.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import pathlib
import re
import statistics
import sys
import tempfile
from typing import Any

import config as cfg

SCHEMA = 1

# The compiler groups its diagnostics by the layer that raises them. Which layer
# a profile dies on is the design signal: E1 means the model missed the syntax,
# E2/E3 mean it wrote valid DEAL that means the wrong thing.
LAYERS = {
    "E1": "lexer / parser",
    "E2": "names and scopes",
    "E3": "types",
    "E4": "class shape",
    "E5": "signatures",
    "E6": "modules",
    "E7": "declaration files",
    "E8": "runtime checks",
}

# Tokens DEAL simply does not have. Deliberately narrow: `=>` is a function
# type here and `?` marks an optional field, so matching those textually would
# flag valid DEAL. Names the model reaches for are counted separately, from the
# compiler's own diagnostics, where they can be identified exactly.
FOREIGN = {
    "++ / --": r"\+\+|--",
    "+= / -=": r"[+\-*/]=[^=]",
    "const / var": r"\b(const|var)\s+\w",
    "=== absent": r"[^=!<>]==[^=]",
}

UNDECLARED = re.compile(r"E2001: Undeclared identifier '([^']+)'")

RUNGS = [("syntax", "syntax_success"), ("compiles", "compile_success"),
         ("interface", "interface_success"), ("runs", "runtime_success"),
         ("passes", "functional_pass")]
RUNG_LABELS = ["parse failed"] + [label for label, _ in RUNGS]

PROFILE_ORDER = ("raw", "constrained")


# ------------------------------------------------------------------ rows ---

def load(path: pathlib.Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return [r for r in rows if not r.get("request_error")]


def initial(rows: list[dict]) -> list[dict]:
    """First attempts only. Success@1 has to stay Success@1."""
    return [r for r in rows if r.get("stage", "initial") == "initial"]


def rung_index(ev: dict) -> int:
    """0 = did not parse; 1..5 = index into RUNGS of the highest rung reached.

    A module with no hidden test stops at `compiles` (2): the rungs above are
    undefined for it, not failed.
    """
    reached = 0
    for number, (_, field) in enumerate(RUNGS, start=1):
        if ev.get(field):
            reached = number
        else:
            break
    return reached


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def profiles_in(rows: list[dict]) -> list[str]:
    present = {r["profile"] for r in rows}
    ordered = [p for p in PROFILE_ORDER if p in present]
    return ordered + sorted(present - set(ordered))


# --------------------------------------------------------------- compute ---

def tier_of(row: dict) -> str:
    """Rows written before tiers existed are module tasks."""
    return row.get("tier") or "modules"


def atoms_of_outputs(rows: list[dict], config: cfg.Config
                    ) -> tuple[dict[tuple, set[str]], dict[tuple, set[str]]]:
    """Atoms reproduced, keyed by (tier, profile).

    Returned twice, because the difference is the interesting part:
      compiled — atoms in modules that fully compiled. Evidence the model can
                 use the construct correctly.
      parsed   — atoms in modules that at least parsed. A construct here but
                 not in `compiled` means the model can write the syntax and
                 fails somewhere above it, which is a different problem from
                 never producing the construct at all.
    """
    import coverage as coverage_lib
    import evaluate

    compiled: dict[tuple, set[str]] = collections.defaultdict(set)
    parsed: dict[tuple, set[str]] = collections.defaultdict(set)
    with tempfile.TemporaryDirectory(prefix="stand-cov-") as raw:
        work = pathlib.Path(raw)
        index: list[tuple[pathlib.Path, tuple, bool]] = []
        for number, row in enumerate(rows):
            if not row["evaluation"]["syntax_success"]:
                continue
            # Measured exactly as generated. An answer that copies the
            # primer's example inflates coverage with constructs the model did
            # not choose, but the fix for that is the prompt, not a quiet
            # subtraction here: `echoes_example` makes it loud instead, and the
            # report calls the coverage contaminated while it happens.
            source, _ = evaluate.strip_fence(row["output"])
            path = work / f"g{number:05d}.deal"
            path.write_text(source, encoding="utf-8")
            index.append((path, (tier_of(row), row["profile"]),
                          row["evaluation"]["compile_success"]))
        if index:
            probed = coverage_lib.probe(config, [p for p, _, _ in index])
            for (_, key, did_compile), result in zip(index, probed):
                parsed[key].update(result["atoms"])
                if did_compile:
                    compiled[key].update(result["atoms"])
    return compiled, parsed


def union(atoms: dict[tuple, set[str]], profile: str, tiers: list[str]) -> set[str]:
    out: set[str] = set()
    for tier in tiers:
        out |= atoms.get((tier, profile), set())
    return out


def fill_grammar_verdicts(rows: list[dict], config: cfg.Config) -> None:
    """Results produced before the grammar post-check existed carry no verdict.

    It is derivable from the stored output, so compute it rather than asking
    for a re-run that would generate identical text.
    """
    missing = [r for r in rows if "strict_gbnf_valid" not in r]
    if not missing:
        return
    import evaluate
    import gate
    print(f"computing the grammar verdict for {len(missing)} stored generation(s)...",
          file=sys.stderr)
    for row in missing:
        output = row.get("output", "")
        normalized, _ = evaluate.strip_fence(output)
        row["strict_gbnf_valid"] = gate.accepts(config.tools.validator, config.grammar, output)
        row["normalized_gbnf_valid"] = (
            row["strict_gbnf_valid"] if normalized == output
            else gate.accepts(config.tools.validator, config.grammar, normalized))


def compute(all_rows: list[dict], config: cfg.Config,
            inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the report says, as one JSON-serialisable dict."""
    import coverage as coverage_lib

    rows = initial(all_rows)
    if not rows:
        raise ValueError("no usable rows")
    fill_grammar_verdicts(rows, config)

    universe = coverage_lib.derive_universe(config.compiler)
    references = [t.reference for t in config.tasks() if t.reference.exists()]
    reference_atoms: set[str] = set()
    for result in coverage_lib.probe(config, references):
        reference_atoms.update(result["atoms"])
    reachable = {a for a in reference_atoms
                 if a in universe
                 and a not in coverage_lib.STRUCTURAL
                 and a not in coverage_lib.OUT_OF_SCOPE}
    compiled_atoms, parsed_atoms = atoms_of_outputs(rows, config)
    tiers_present = [t for t in cfg.TIERS if any(tier_of(r) == t for r in rows)]

    profiles: dict[str, dict[str, Any]] = {}
    for profile in profiles_in(rows):
        items = sorted((r for r in rows if r["profile"] == profile), key=lambda r: r["task_id"])
        profiles[profile] = profile_summary(profile, items, reachable, universe,
                                           union(compiled_atoms, profile, tiers_present),
                                           union(parsed_atoms, profile, tiers_present))

    # The same summary per tier, so the quick and the module layer can be read
    # and compared on their own. With one tier present this repeats the whole.
    tiers: dict[str, dict[str, Any]] = {}
    for tier in tiers_present:
        tier_rows = [r for r in rows if tier_of(r) == tier]
        tier_profiles = {}
        for profile in profiles_in(tier_rows):
            items = sorted((r for r in tier_rows if r["profile"] == profile),
                           key=lambda r: r["task_id"])
            tier_profiles[profile] = profile_summary(
                profile, items, reachable, universe,
                compiled_atoms.get((tier, profile), set()),
                parsed_atoms.get((tier, profile), set()))
        tiers[tier] = {
            "tasks": sorted({r["task_id"] for r in tier_rows}),
            "profiles": tier_profiles,
            "paired": paired_summary(tier_rows),
        }

    untested = sorted({r["task_id"] for r in rows
                       if r["evaluation"].get("interface_success") is None
                       and r["evaluation"].get("compile_success")})
    return {
        "schema": SCHEMA,
        "inputs": inputs,
        "tasks": sorted({r["task_id"] for r in rows}),
        "tiers": tiers,
        "untested": untested,
        "coverage": {
            "reachable": len(reachable),
            "universe": len(universe),
            "categories": {a: universe[a] for a in sorted(reachable)},
        },
        "profiles": profiles,
        "paired": paired_summary(rows),
        "failed_tests": [
            {"profile": r["profile"], "task": r["task_id"],
             "message": r["evaluation"].get("runtime_message", "")}
            for r in sorted(rows, key=lambda r: (r["profile"], r["task_id"]))
            if r["evaluation"].get("runtime_success")
            and not r["evaluation"].get("functional_pass")],
        "repair": repair_summary(all_rows),
    }


def profile_summary(profile: str, items: list[dict], reachable: set[str],
                    universe: dict[str, str], compiled: set[str], parsed: set[str]
                    ) -> dict[str, Any]:
    ev = [r["evaluation"] for r in items]
    got = sorted(a for a in compiled if a in reachable)
    seen = sorted(a for a in parsed if a in reachable)
    missed: dict[str, list[str]] = collections.defaultdict(list)
    for atom in sorted(reachable - set(got)):
        missed[universe[atom]].append(atom.split(":", 1)[1])

    codes: collections.Counter = collections.Counter()
    per_layer: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    layer_tasks: dict[str, set[str]] = collections.defaultdict(set)
    undeclared: collections.Counter = collections.Counter()
    for row in items:
        e = row["evaluation"]
        for code in e["diagnostics"]:
            codes[code] += 1
        for code in set(e["diagnostics"]) | set(e.get("interface_diagnostics") or []):
            per_layer[code[:2]][code] += 1
        for code in e["diagnostics"]:
            layer_tasks[code[:2]].add(row["task_id"])
        for name in UNDECLARED.findall(e.get("compiler_message", "")):
            undeclared[name] += 1

    prompt_tokens = [r["prompt_tokens"] for r in items if r.get("prompt_tokens")]
    out_tokens = [r["generated_tokens"] for r in items if r.get("generated_tokens")]
    gen_ms = [r["generation_ms"] for r in items if r.get("generation_ms")]
    total_ms = sum(r.get("total_server_ms") or 0 for r in items)
    compiled_n = sum(1 for e in ev if e["compile_success"])
    passing_n = sum(1 for e in ev if e.get("functional_pass"))
    aggregate = (sum(out_tokens) / (sum(gen_ms) / 1000)) if gen_ms and sum(gen_ms) else 0.0
    rejection = [r["argmax_rejection_rate"] for r in items
                 if r.get("argmax_rejection_rate") is not None]

    per_task = {}
    for row in items:
        e = row["evaluation"]
        reached = rung_index(e)
        per_task[row["task_id"]] = {
            "rung": reached,
            "rung_label": RUNG_LABELS[reached],
            "diagnostics": sorted(set(e["diagnostics"]) | set(e.get("interface_diagnostics") or [])),
            "tokens": row.get("generated_tokens"),
            "generation_ms": row.get("generation_ms"),
            "hit_cap": bool(row.get("hit_token_limit")),
            "echoes_example": bool(row.get("echoes_example")),
            "failed_check": (e.get("runtime_message") if e.get("runtime_success")
                             and not e.get("functional_pass") else None),
        }

    return {
        "n": len(items),
        "no_fence": sum(1 for e in ev if not e["fence_normalized"]),
        "grammar_valid": sum(1 for r in items if r.get("strict_gbnf_valid")),
        "grammar_valid_normalized": sum(1 for r in items if r.get("normalized_gbnf_valid")),
        **{label: sum(1 for e in ev if e.get(field)) for label, field in RUNGS},
        "hit_cap": sum(1 for r in items if r.get("hit_token_limit")),
        "echoes_example": sorted(r["task_id"] for r in items if r.get("echoes_example")),
        "echoed_tokens": sum(r.get("generated_tokens") or 0
                             for r in items if r.get("echoes_example")),
        "diagnostics": dict(codes.most_common()),
        "layers": {layer: {"tasks": len(layer_tasks.get(layer, ())),
                           "codes": dict(per_layer[layer].most_common())}
                   for layer in sorted(per_layer)},
        "foreign": {name: sum(1 for r in items if re.search(pattern, r.get("output", "")))
                    for name, pattern in FOREIGN.items()},
        "undeclared": dict(undeclared.most_common()),
        "coverage": {"compiled": got, "parsed": seen, "missed": dict(missed)},
        "cost": {
            "n": len(items),
            "prompt_tokens_mean": statistics.mean(prompt_tokens) if prompt_tokens else 0,
            "output_tokens_mean": statistics.mean(out_tokens) if out_tokens else 0,
            "output_tokens_total": sum(out_tokens),
            "generation_ms_p50": percentile(gen_ms, 0.50),
            "generation_ms_p95": percentile(gen_ms, 0.95),
            "generation_ms_max": max(gen_ms) if gen_ms else 0,
            "aggregate_tokens_per_second": aggregate,
            "server_ms_total": total_ms,
            "server_ms_per_compiled": total_ms / compiled_n if compiled_n else None,
            "server_ms_per_pass": total_ms / passing_n if passing_n else None,
            "passes_per_server_minute": passing_n / (total_ms / 60000) if total_ms else None,
            "atoms_reproduced": len(got),
            "server_ms_per_atom": total_ms / len(got) if got else None,
            "hit_token_limit": sum(1 for r in items if r.get("hit_token_limit")),
            "argmax_rejection_rate": statistics.mean(rejection) if rejection else 0.0,
        },
        "per_task": per_task,
    }


def paired_summary(rows: list[dict]) -> dict[str, Any] | None:
    """Baseline first, treatment second, paired by task.

    A difference in two independent rates hides which tasks moved; the
    published benchmark's headline +17.4 pp was in fact +239 rescued and -100
    harmed.
    """
    order = [p for p in PROFILE_ORDER if p in {r["profile"] for r in rows}]
    if len(order) != 2:
        return None
    left, right = order
    by_task: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for row in rows:
        by_task[row["task_id"]][row["profile"]] = row["evaluation"]
    paired = {t: v for t, v in by_task.items() if left in v and right in v}
    rungs = {}
    for label, field in RUNGS:
        a = sum(1 for v in paired.values() if v[left].get(field))
        b = sum(1 for v in paired.values() if v[right].get(field))
        rescued = sorted(t for t, v in paired.items() if v[right].get(field) and not v[left].get(field))
        harmed = sorted(t for t, v in paired.items() if v[left].get(field) and not v[right].get(field))
        rungs[label] = {"a": a, "b": b, "rescued": rescued, "harmed": harmed}
    return {"left": left, "right": right, "n": len(paired), "rungs": rungs}


def repair_summary(rows: list[dict]) -> dict[str, Any] | None:
    """What a compiler-guided second pass bought, reported on its own."""
    repairs = [r for r in rows if r.get("stage", "initial") != "initial"]
    if not repairs:
        return None
    first = {(r["profile"], r["task_id"]): r for r in initial(rows)}
    best: dict[tuple, dict] = {}
    for row in sorted(repairs, key=lambda r: r["stage"]):
        best[(row["profile"], row["task_id"])] = row

    profiles = {}
    for profile in sorted({r["profile"] for r in repairs}):
        keys = [k for k in best if k[0] == profile]
        profiles[profile] = {
            "attempted": len(keys),
            "stalled": sum(1 for k in keys if best[k].get("repair_stalled")),
            "gained": {label: sum(1 for k in keys
                                  if best[k]["evaluation"].get(field)
                                  and not first[k]["evaluation"].get(field))
                       for label, field in RUNGS},
        }
    outcomes: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for key, row in best.items():
        before = first[key]["evaluation"]
        codes = set(before.get("diagnostics") or []) | set(before.get("interface_diagnostics") or [])
        fixed = set(row["evaluation"].get("diagnostics") or []) | set(
            row["evaluation"].get("interface_diagnostics") or [])
        for code in codes:
            outcomes[code][0] += 1
            if code not in fixed:
                outcomes[code][1] += 1
    return {
        "profiles": profiles,
        "extra_tokens": sum(r.get("generated_tokens") or 0 for r in repairs),
        "extra_server_ms": sum(r.get("total_server_ms") or 0 for r in repairs),
        "codes": {code: {"seen": seen, "cleared": cleared}
                  for code, (seen, cleared) in sorted(outcomes.items(), key=lambda kv: -kv[1][0])},
    }


# ---------------------------------------------------------------- render ---

# ---------------------------------------------------------------- render ---
#
# What the report prints, and nothing else: latency, the solve@<=k curve, what
# an attempt costs, what a success costs, and the same four against the
# unconstrained baseline. Everything is read from the attempts themselves, so a
# result directory renders without the compiler, the JDK or the model.

WIDTH = 78
# One grid for every table: a label, then fixed-width numeric columns. Numbers
# line up across sections, and a flag never pushes a digit out of its column.
LABEL = 26
NUM = 8
COUNT = 5
PROFILE_LABELS = {"raw": "unconstrained", "constrained": "grammar"}
NOT_MEASURED = "not measured"


def profile_label(profile: str) -> str:
    return PROFILE_LABELS.get(profile, profile)


def attempt_k(row: dict) -> int:
    """0 for the first generation, N for repair-N."""
    stage = row.get("stage", "initial")
    if stage == "initial":
        return 0
    return int(stage.split("-")[1])


def attempts_of(rows: list[dict], profile: str) -> list[dict]:
    return sorted((r for r in rows if r["profile"] == profile),
                  key=lambda r: (r["task_id"], attempt_k(r)))


def solve_curve(rows: list[dict], profile: str, field: str, kmax: int) -> list[int]:
    """How many tasks are solved using k repair rounds or fewer, k = 0..kmax.

    Cumulative on purpose: a task solved at k=1 stays solved at k=2 even if a
    later round breaks it again, because the loop would have stopped there.
    """
    first: dict[str, int] = {}
    for row in rows:
        if row["profile"] != profile or not (row.get("evaluation") or {}).get(field):
            continue
        k = attempt_k(row)
        task = row["task_id"]
        if k < first.get(task, kmax + 1):
            first[task] = k
    return [sum(1 for k in first.values() if k <= limit) for limit in range(kmax + 1)]


def solved_tasks(rows: list[dict], profile: str, field: str) -> set[str]:
    return {r["task_id"] for r in rows if r["profile"] == profile
            and (r.get("evaluation") or {}).get(field)}


def ttft_s(row: dict) -> float | None:
    ms = row.get("ttft_ms")
    return None if ms is None else ms / 1000


def ttlt_s(row: dict) -> float | None:
    ms = row.get("ttlt_ms")
    return None if ms is None else ms / 1000


def prefill_rate(row: dict) -> float | None:
    """Tokens the server actually had to evaluate, over the time to first token."""
    fresh, ms = row.get("input_toks_new"), row.get("ttft_ms")
    if fresh is None or not ms:
        return None
    return fresh / (ms / 1000)


def decode_rate(row: dict) -> float | None:
    out, first, last = row.get("generated_tokens"), row.get("ttft_ms"), row.get("ttlt_ms")
    if not out or first is None or last is None or last <= first:
        return None
    return out / ((last - first) / 1000)


def is_warm(row: dict) -> bool | None:
    cached = row.get("input_toks_cached")
    return None if cached is None else cached > 0


def stat(attempts: list[dict], pick, fraction: float) -> float | None:
    values = [v for v in (pick(a) for a in attempts) if v is not None]
    return percentile(values, fraction) if values else None


def cell(value: float | None, digits: int) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}" if digits else f"{value:.0f}"


# Nearest-rank p95 equals the maximum until there are twenty observations, so
# below that the column is the worst attempt wearing a percentile's name. Marked
# rather than hidden: the worst attempt is a real number worth seeing.
P95_NEEDS = 20


def two(attempts: list[dict], pick, digits: int) -> str:
    """p50, p95, and how many attempts the pair was taken from.

    The count belongs next to the percentiles: two numbers over three attempts
    and the same two over eighty read very differently.
    """
    values = [v for v in (pick(a) for a in attempts) if v is not None]
    flag = "*" if values and len(values) < P95_NEEDS else " "
    return (f"{cell(stat(attempts, pick, 0.50), digits):>{NUM}}"
            f"{cell(stat(attempts, pick, 0.95), digits):>{NUM}}{flag}"
            f"{len(values):>{COUNT - 1}}")


# The cost of one attempt, and the same fields summed for cost per success.
COST_ROWS = [
    ("llm wall time", "s", lambda r: (r.get("ttlt_ms") or r.get("wall_ms") or 0) / 1000, 1),
    ("compile time", "ms", lambda r: (r.get("evaluation") or {}).get("compile_ms"), 0),
    ("test time", "ms", lambda r: (r.get("evaluation") or {}).get("runtime_ms"), 0),
    ("input toks cached", "", lambda r: r.get("input_toks_cached"), 0),
    ("input toks new", "", lambda r: r.get("input_toks_new"), 0),
    ("output toks", "", lambda r: r.get("generated_tokens"), 0),
]


def cost_rows(cache_known: bool) -> list[tuple[str, str, Any, int]]:
    """The cache columns are dropped, not zeroed, on runs that never had them."""
    if cache_known:
        return COST_ROWS
    return [row for row in COST_ROWS if "input toks" not in row[0]]


def fingerprint_of(rows: list[dict], summary: dict[str, Any]) -> dict[str, Any]:
    return ((summary.get("inputs") or {}).get("fingerprint")
            or (rows[0].get("fingerprint") if rows else {}) or {})


def render(summary: dict[str, Any], rows: list[dict], run: str = "") -> str:
    out: list[str] = []
    say = out.append
    rule = lambda: say("  " + "-" * (WIDTH - 2))
    profiles = profiles_in(rows)
    baseline = "raw" if "raw" in profiles else profiles[0]
    others = [p for p in profiles if p != baseline]
    attempts = {p: attempts_of(rows, p) for p in profiles}
    tasks = sorted({r["task_id"] for r in rows})
    # The curve runs to the number of rounds that was asked for, not to the
    # number that happened: a loop that stops early has to look flat, not short.
    rounds_seen = max((attempt_k(r) for r in rows), default=0)
    kmax = max(rounds_seen, int(fingerprint_of(rows, summary).get("repair_rounds") or 0))
    fingerprint = fingerprint_of(rows, summary)
    measured = any(r.get("ttft_ms") is not None for r in rows)
    cache_known = any(r.get("input_toks_cached") is not None for r in rows)

    say("=" * WIDTH)
    # The directory's name, not its path: a sample has to render the same from
    # anywhere, and the path says nothing the name does not.
    say(f"run        {pathlib.Path(run).name if run else ''}".rstrip())
    say(f"model      {rows[0]['model'] if rows else '?':<28} "
        f"seed {fingerprint.get('seed')}      max_tokens {fingerprint.get('max_tokens')}")
    say(f"grammar    {(fingerprint.get('grammar_sha256') or '?')[:12]:<28} "
        f"compiler {(fingerprint.get('compiler_commit') or '?')[:12]}")
    say(f"tasks      {len(tasks)}     repair rounds {kmax} asked, {rounds_seen} run     "
        f"prompt cache {'on' if cache_known and any(is_warm(r) for r in rows) else 'off'}")
    say("attempts   " + "     ".join(f"{profile_label(p)} {len(attempts[p])}" for p in profiles))
    say("=" * WIDTH)

    # ------------------------------------------------------------------ [1]
    say("")
    say("[1] LATENCY   per attempt")
    if not measured:
        say(f"  {NOT_MEASURED}: this run predates streaming, so there is no")
        say("  first-token event to time. Re-run to fill this block.")
    else:
        say(" " * LABEL + "".join(f"{profile_label(p):^{2*NUM + COUNT}}" for p in profiles))
        say(" " * LABEL + "".join(f"{'p50':>{NUM}}{'p95':>{NUM}} {'n':>{COUNT - 2}}"
                                  for p in profiles))
        # Grouped by cache outcome, not by measure: a cold prefill and a warm
        # one are different populations, and rows from different populations
        # must not sit under each other inviting a comparison.
        pools = (("cold, prompt cache miss", lambda a: is_warm(a) is False),
                 ("warm, prompt cache hit", is_warm))
        for title, keep in pools:
            pool = {p: [a for a in attempts[p] if keep(a)] for p in profiles}
            rule()
            say(f"  {title}")
            for label, pick, digits in (("ttft, s", ttft_s, 1),
                                        ("ttlt, s", ttlt_s, 1),
                                        ("prefill tok/s", prefill_rate, 1),
                                        ("decode tok/s", decode_rate, 1)):
                say(f"    {label:<{LABEL - 4}}"
                    + "".join(two(pool[p], pick, digits) for p in profiles))

    # ------------------------------------------------------------------ [2]
    if any(0 < len(attempts[p]) < P95_NEEDS for p in profiles):
        say(f"  * max, not p95: fewer than {P95_NEEDS} attempts to take one from")

    say("")
    say(f"[2] QUALITY   COUNT of tasks solved at k repair rounds or fewer, n={len(tasks)}")
    say(" " * 26 + "".join(f"{'k=' + str(k):>6}" for k in range(kmax + 1)))
    rule()
    curves = {}
    for field, name in (("compile_success", "compiles"), ("functional_pass", "passes")):
        for profile in profiles:
            curve = solve_curve(rows, profile, field, kmax)
            curves[(field, profile)] = curve
            say(f"  {name:<10}{profile_label(profile):<14}"
                + "".join(f"{value:>6d}" for value in curve))
    # Where the curve is carried forward rather than measured. A round nobody
    # entered cannot change the count, but the reader must not mistake an
    # untried round for one that was tried and failed.
    say("  " + "-" * (WIDTH - 2))
    for profile in profiles:
        tried = [len({r["task_id"] for r in rows if r["profile"] == profile
                      and attempt_k(r) == k}) for k in range(kmax + 1)]
        say(f"  {'ran round':<10}{profile_label(profile):<14}"
            + "".join(f"{value:>6d}" for value in tried))
    rule()
    stalled = {p: len({r["task_id"] for r in rows
                       if r["profile"] == p and r.get("repair_stalled")})
               for p in profiles}
    if any(stalled.values()):
        say(f"  {'stopped early, same output':<28}" + "     ".join(
            f"{profile_label(p)} {stalled[p]}" for p in profiles))
    for field, name in (("compile_success", "never compiled"), ("functional_pass", "never passed")):
        say(f"  {name:<28}" + "     ".join(
            f"{profile_label(p)} {len(tasks) - len(solved_tasks(rows, p, field))}"
            for p in profiles))

    # ------------------------------------------------------------------ [3]
    say("")
    say("[3] COST PER ATTEMPT")
    say(" " * LABEL + "".join(f"{profile_label(p):^{2*NUM + COUNT}}" for p in profiles))
    say(" " * LABEL + "".join(f"{'p50':>{NUM}}{'p95':>{NUM}} {'n':>{COUNT - 2}}"
                              for p in profiles))
    rule()
    if not cache_known:
        say(f"  input toks cached / new    {NOT_MEASURED} (run predates prompt caching)")
    for label, unit, pick, digits in cost_rows(cache_known):
        name = f"{label}, {unit}" if unit else label
        say(f"  {name:<{LABEL - 2}}"
            + "".join(two(attempts[p], pick, digits) for p in profiles))

    # ------------------------------------------------------------------ [4]
    say("")
    say("[4] COST PER SOLVED TASK   its own attempts, its failed rounds included")
    say(" " * LABEL + "".join(f"{profile_label(p):>{2*NUM}}" for p in profiles))
    per_solved = {}
    for field, name in (("compile_success", "compiled"), ("functional_pass", "passed")):
        wins = {p: len(solved_tasks(rows, p, field)) for p in profiles}
        rule()
        say(f"  {'tasks that ' + name:<{LABEL - 2}}"
            + "".join(f"{wins[p]:>{2*NUM}d}" for p in profiles) + "   tasks")
        if not any(wins.values()):
            say(f"  no task {name}, so there is nothing to divide the spend by")
            for label, _, _, _ in cost_rows(cache_known):
                for profile in profiles:
                    per_solved[(field, profile, label)] = None
            continue
        for label, unit, pick, digits in cost_rows(cache_known):
            cells = []
            for profile in profiles:
                mine = [a for a in attempts[profile]
                        if a["task_id"] in solved_tasks(rows, profile, field)]
                spend = sum(v for v in (pick(a) for a in mine) if v is not None)
                value = spend / wins[profile] if wins[profile] else None
                per_solved[(field, profile, label)] = value
                cells.append(f"{cell(value, digits):>{2*NUM}}")
            title = f"{label}, {unit}" if unit else label
            say(f"    {title:<{LABEL - 4}}" + "".join(cells))

    # ------------------------------------------------------------------ [5]
    if others:
        say("")
        say("[5] GRAMMAR vs UNCONSTRAINED BASELINE   same tasks, seeds, retry loop")
        for profile in others:
            say(f"  {'':<{LABEL - 2}}{'baseline':>{NUM}}"
                f"{profile_label(profile):>{NUM + 3}}{'delta':>{NUM + 2}}")
            rule()

            def line(label: str, a: float | None, b: float | None, digits: int,
                     indent: int = 2) -> None:
                delta = (f"{b - a:+.{digits}f}" if a is not None and b is not None else "-")
                say(f"{' ' * indent}{label:<{LABEL - indent}}{cell(a, digits):>{NUM}}"
                    f"{cell(b, digits):>{NUM + 3}}{delta:>{NUM + 2}}")

            if measured:
                warm = {p: [a for a in attempts[p] if is_warm(a)] for p in profiles}
                say("  latency p50, warm attempts")
                for label, pick, digits in (("ttft, s", ttft_s, 1),
                                            ("ttlt, s", ttlt_s, 1),
                                            ("prefill tok/s", prefill_rate, 1),
                                            ("decode tok/s", decode_rate, 1)):
                    line(label, stat(warm[baseline], pick, 0.50),
                         stat(warm[profile], pick, 0.50), digits, indent=4)
                rule()
            say("  tasks solved")
            for field, name in (("compile_success", "compiles"), ("functional_pass", "passes")):
                for k in (0, kmax) if kmax else (0,):
                    line(f"{name} @k={k}", curves[(field, baseline)][k],
                         curves[(field, profile)][k], 0, indent=4)
            line("never passed",
                 len(tasks) - len(solved_tasks(rows, baseline, "functional_pass")),
                 len(tasks) - len(solved_tasks(rows, profile, "functional_pass")), 0,
                 indent=4)
            rule()
            say("  cost per attempt, p50")
            for label, unit, pick, digits in cost_rows(cache_known):
                name = f"{label}, {unit}" if unit else label
                line(name, stat(attempts[baseline], pick, 0.50),
                     stat(attempts[profile], pick, 0.50), digits, indent=4)
            shown = [(label, unit, digits) for label, unit, _, digits in cost_rows(cache_known)
                     if per_solved[("functional_pass", baseline, label)] is not None
                     or per_solved[("functional_pass", profile, label)] is not None]
            if shown:
                rule()
                say("  cost of a task that passed")
                for label, unit, digits in shown:
                    name = f"{label}, {unit}" if unit else label
                    line(name, per_solved[("functional_pass", baseline, label)],
                         per_solved[("functional_pass", profile, label)], digits, indent=4)

    say("=" * WIDTH)
    return "\n".join(out) + "\n"


def write(out_dir: pathlib.Path, summary: dict[str, Any],
          rows: list[dict]) -> list[pathlib.Path]:
    """summary.json, report.txt and cost.csv into the result directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    path = out_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    written.append(path)
    path = out_dir / "report.txt"
    path.write_text(render(summary, rows, str(out_dir)), encoding="utf-8")
    written.append(path)
    path = out_dir / "cost.csv"
    rows = [dict(profile=profile, **summary["profiles"][profile]["cost"])
            for profile in summary["profiles"]]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    written.append(path)
    return written


def summarise_run(out_dir: pathlib.Path, config: cfg.Config) -> dict[str, Any]:
    """Compute and write everything for a result directory. Used by `run`."""
    rows = load(out_dir / "raw.jsonl")
    inputs_path = out_dir / "inputs.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8")) if inputs_path.exists() else None
    summary = compute(rows, config, inputs)
    write(out_dir, summary, rows)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=pathlib.Path,
                        help="a run directory, or its raw.jsonl")
    cfg.add_arguments(parser)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--recompute", action="store_true",
                        help="rebuild summary.json even if it exists (needs the toolchain)")
    args = parser.parse_args()

    out_dir = args.results if args.results.is_dir() else args.results.parent
    summary_path = out_dir / "summary.json"
    rows = load(out_dir / "raw.jsonl")
    if summary_path.exists() and not args.recompute:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print(render(summary, rows, str(out_dir)), end="")
        print(f"(rendered from {summary_path}; --recompute rebuilds it)", file=sys.stderr)
        return 0

    try:
        config = cfg.resolve(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2
    try:
        summary = summarise_run(out_dir, config)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(render(summary, rows, str(out_dir)), end="")
    print(f"wrote {out_dir / 'summary.json'}, report.txt, cost.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
