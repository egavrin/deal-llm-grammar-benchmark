#!/usr/bin/env python3
"""Re-score the stored generations of a run without generating anything.

Generated text is deterministic under greedy decoding and is stored in
raw.jsonl; the evaluation of it is not sacred. When the evaluator changes — a
better runtime classification, a compiler fix — the honest move is to re-run
the evaluator over the stored outputs rather than to regenerate identical text
or, worse, to compare runs scored by different evaluators.

    reevaluate.py results/today --preset v12-baseline

The previous raw.jsonl is kept as raw.jsonl.before-reevaluate. The fingerprint
is left untouched: it describes the inputs that produced the text, and the
text is unchanged. The compiler commit used for re-scoring must match it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

import config as cfg
import evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=pathlib.Path, help="run directory or raw.jsonl")
    cfg.add_arguments(parser)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=1024)
    args = parser.parse_args()
    try:
        config = cfg.resolve(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    raw = args.results / "raw.jsonl" if args.results.is_dir() else args.results
    inputs = raw.parent / "inputs.json"
    if inputs.exists():
        recorded = json.loads(inputs.read_text(encoding="utf-8"))["fingerprint"]
        current = config.compiler_commit()
        if recorded.get("compiler_commit") != current:
            print(f"compiler differs from the one that produced this run:\n"
                  f"  run:  {recorded.get('compiler_commit')}\n  now:  {current}\n"
                  "  Re-scoring under another compiler would change what the "
                  "numbers mean. Check out that commit, or regenerate.",
                  file=sys.stderr)
            return 2

    tasks = {t.id: t for t in config.tasks()}
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    backup = raw.with_name("raw.jsonl.before-reevaluate")
    if not backup.exists():
        shutil.copy(raw, backup)

    changed = 0
    for row in rows:
        if row.get("request_error"):
            continue
        task = tasks.get(row["task_id"])
        if task is None:
            print(f"  skipping {row['task_id']}: not in the current prompt set")
            continue
        before = row["evaluation"]
        after = evaluate.evaluate(row["output"], config=config, task=task).to_dict()
        # Timings are of this machine now, not of the run; keep the originals.
        for key in ("compile_ms", "interface_ms", "runtime_ms"):
            after[key] = before.get(key, after[key])
        if {k: v for k, v in after.items() if k in RUNGS} != {k: v for k, v in before.items() if k in RUNGS}:
            changed += 1
            print(f"  {row['profile']:11s} {row['task_id']:18s} "
                  + ", ".join(f"{k}: {before.get(k)} -> {after[k]}"
                              for k in RUNGS if before.get(k) != after[k]))
        row["evaluation"] = after
        if "echoes_example" not in row:
            row["echoes_example"] = any(name in row["output"]
                                        for name in config.example_exports())

    raw.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    print(f"re-scored {len(rows)} row(s), {changed} changed a rung; "
          f"previous file kept as {backup.name}")
    return 0


RUNGS = ("syntax_success", "compile_success", "interface_success",
         "runtime_success", "functional_pass")


if __name__ == "__main__":
    sys.exit(main())
