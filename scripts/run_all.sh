#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 scripts/verify_references.py
python3 run_benchmark.py --output results/reproduced-results.jsonl
scripts/build_validator.sh
mkdir -p results/reproduced
python3 benchmark_validator.py --rounds 10 --output results/reproduced/validator-throughput.csv
python3 summarize.py \
  --input results/reproduced-results.jsonl \
  --output-dir results/reproduced
