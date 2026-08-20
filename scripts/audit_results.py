#!/usr/bin/env python3
"""Audit result completeness and print the headline outcome counts."""

from __future__ import annotations

import argparse
import json
import pathlib


EXPECTED = {
    "deal-raw": {"functional_pass": 283, "syntax_success": 539, "compile_success": 383},
    "deal-constrained": {"functional_pass": 422, "syntax_success": 786, "compile_success": 571},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=pathlib.Path)
    parser.add_argument("--expect-published", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    keys = {(row.get("model"), row.get("profile"), row.get("task_id")) for row in rows}
    if len(rows) != 1600 or len(keys) != 1600:
        raise SystemExit(f"expected 1600 unique rows, got rows={len(rows)} unique={len(keys)}")
    if any(row.get("request_error") for row in rows):
        raise SystemExit("result file contains request errors")
    if len({row["task_id"] for row in rows}) != 800:
        raise SystemExit("expected 800 unique task IDs")
    failed = False
    for profile in EXPECTED:
        selected = [row for row in rows if row["profile"] == profile]
        counts = {
            key: sum(bool(row["evaluation"][key]) for row in selected)
            for key in ("functional_pass", "syntax_success", "compile_success")
        }
        print(profile, json.dumps(counts, sort_keys=True))
        if args.expect_published and counts != EXPECTED[profile]:
            print(f"expected {EXPECTED[profile]}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
