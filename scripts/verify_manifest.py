#!/usr/bin/env python3
"""Verify the frozen benchmark inputs and published result artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true", help="also require and hash the local GGUF")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    failed = False
    for relative, expected in manifest["sha256"].items():
        path = ROOT / relative
        actual = sha256(path) if path.exists() else "MISSING"
        ok = actual == expected
        print(f"{'OK' if ok else 'FAIL'}  {relative}  {actual}")
        failed |= not ok
    if args.model:
        path = ROOT / "models/qwen2.5-coder-0.5b-instruct-control-q4_k_m.gguf"
        expected = manifest["model"]["sha256"]
        actual = sha256(path) if path.exists() else "MISSING"
        ok = actual == expected
        print(f"{'OK' if ok else 'FAIL'}  {path.relative_to(ROOT)}  {actual}")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
