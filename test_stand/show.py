#!/usr/bin/env python3
"""Print what the model actually wrote, next to what the compiler said.

report.py tells you how much worked; this tells you why.

    show.py results/today --list                 one line per generation
    show.py results/today --task-id kv_cache     full sources and diagnostics
    show.py results/today --only-failures --profile constrained
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from generate import describe_outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=pathlib.Path,
                        help="raw.jsonl from a run, or the run directory")
    parser.add_argument("--task-id", dest="task_id")
    parser.add_argument("--profile", choices=("raw", "constrained"))
    parser.add_argument("--only-failures", action="store_true",
                        help="only generations that did not pass their test")
    parser.add_argument("--list", action="store_true",
                        help="one line per generation instead of full sources")
    args = parser.parse_args()

    results = args.results / "raw.jsonl" if args.results.is_dir() else args.results
    rows = [json.loads(line) for line in
            results.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if not r.get("request_error")]
    if args.task_id:
        rows = [r for r in rows if r["task_id"] == args.task_id]
    if args.profile:
        rows = [r for r in rows if r["profile"] == args.profile]
    if args.only_failures:
        rows = [r for r in rows if not r["evaluation"].get("functional_pass")]
    if not rows:
        print("nothing matched", file=sys.stderr)
        return 1

    for row in sorted(rows, key=lambda r: (r["task_id"], r["profile"], r.get("stage", "initial"))):
        ev = row["evaluation"]
        stage = row.get("stage", "initial")
        head = (f"{row['task_id']}  [{row['profile']}]"
                + (f"  {stage}" if stage != "initial" else "")
                + f"  {describe_outcome(row)}  "
                f"{row['generated_tokens']} tok  {(row.get('generation_ms') or 0) / 1000:.1f} s"
                + ("  HIT TOKEN CAP" if row.get("hit_token_limit") else "")
                + ("  COPIES EXAMPLE" if row.get("echoes_example") else ""))
        codes = " ".join(ev["diagnostics"] + (ev.get("interface_diagnostics") or []))
        if args.list:
            print(f"{head}  {codes}")
            continue
        print("=" * 78)
        print(head)
        if codes:
            print(f"diagnostics: {codes}")
        if ev.get("runtime_success") and not ev.get("functional_pass"):
            print(f"{ev.get('runtime_message', '')}")
        print("-" * 78)
        print(row["output"])
        if ev.get("compiler_message"):
            print("-" * 78)
            print(ev["compiler_message"][:1200])
        if ev.get("interface_errors"):
            print("-" * 78)
            for error in ev["interface_errors"][:6]:
                print(f"interface: {error['code']}: {error['message']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
