#!/usr/bin/env python3
"""Measure in-process llama.cpp GBNF recognition on canonical DEAL references."""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import subprocess
import tempfile

from deal_v12_eval import deal_reference


HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument(
        "--grammar", type=pathlib.Path,
        default=HERE / "grammar/deal-v1.2.gbnf",
    )
    parser.add_argument(
        "--validator", type=pathlib.Path, default=HERE / "tools/gbnf-throughput"
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        default=HERE / "results/validator-throughput.csv",
    )
    args = parser.parse_args()
    tasks = [
        json.loads(line)
        for line in (HERE / "bench/tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with tempfile.TemporaryDirectory(prefix="deal-v12-gbnf-") as temp_name:
        temp = pathlib.Path(temp_name)
        paths: list[pathlib.Path] = []
        for index, task in enumerate(tasks):
            path = temp / f"reference-{index:04d}.deal"
            path.write_text(deal_reference(task), encoding="utf-8")
            paths.append(path)
        run = subprocess.run(
            [str(args.validator), str(args.grammar), str(args.rounds), *map(str, paths)],
            capture_output=True, text=True, check=True,
        )
    measured = json.loads(run.stdout)
    row = {
        "profile": "deal-v1.2-supplied",
        "validator": "llama.cpp-gbnf-in-process",
        "corpus_programs": len(tasks),
        "rounds": args.rounds,
        **measured,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    print(json.dumps(row, sort_keys=True))
    return 0 if measured["failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
