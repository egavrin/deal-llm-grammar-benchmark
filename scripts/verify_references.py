#!/usr/bin/env python3
"""Compile and execute all frozen reference implementations as an evaluator gate."""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deal_v12_eval import deal_reference, evaluate_deal_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--deal-repo", type=pathlib.Path, default=ROOT / ".deps/deal")
    args = parser.parse_args()
    tasks = [
        json.loads(line)
        for line in (ROOT / "bench/tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def check(task: dict):
        return task, evaluate_deal_source(
            deal_reference(task), task=task, deal_repo=args.deal_repo
        )

    started = time.perf_counter()
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), 1):
            task, result = future.result()
            if not result.functional_pass:
                failures.append((task, result))
            if index % 100 == 0:
                print(f"validated={index}/{len(tasks)} failures={len(failures)}", flush=True)
    elapsed = time.perf_counter() - started
    print(f"REFERENCE_GATE={len(tasks) - len(failures)}/{len(tasks)} elapsed={elapsed:.1f}s")
    if failures:
        print("failure categories:", Counter(task["category"] for task, _ in failures))
        for task, result in failures[:10]:
            print(task["id"], result.diagnostics, result.compiler_message, result.runtime_message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
