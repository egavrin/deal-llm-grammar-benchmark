#!/usr/bin/env python3
"""The model registry: fetch, verify and describe the GGUF files the stand runs on.

    models.py list                what test_stand/models.json knows
    models.py fetch NAME          download NAME (or say how to convert it), verify, record
    models.py path NAME           print where NAME lives
    models.py verify NAME         re-check the file on disk against the registry

A model is an input like the grammar: every run records its SHA-256, so the
registry's job is to make sure everyone on the team has the same bytes, and to
say where they came from. Entries with a `url` are downloaded; entries with a
`repo` and no `url` are converted locally by bin/prepare_model.sh, which is the
published benchmark's conversion-control path and needs torch.

The provenance record is written beside the file (`<file>.provenance.json`
with the `.gguf` suffix replaced) and copied into every run's inputs.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request

import config as cfg

MODELS = cfg.ROOT / "models"


def entry(name: str) -> dict:
    registry = cfg.known_models()
    if name not in registry:
        available = ", ".join(sorted(registry)) or "(none)"
        raise cfg.ConfigError(f"unknown model {name!r}.\n  Names in models.json: {available}")
    return dict(registry[name], name=name)


def path_of(spec: dict) -> pathlib.Path:
    return MODELS / spec["file"]


def provenance_path(spec: dict) -> pathlib.Path:
    return path_of(spec).with_suffix(".provenance.json")


def record(spec: dict, sha256: str) -> pathlib.Path:
    out = provenance_path(spec)
    published = spec.get("published_sha256")
    out.write_text(json.dumps({
        "name": spec["name"],
        "file": f"models/{spec['file']}",
        "repo": spec.get("repo"),
        "revision": spec.get("revision"),
        "quantization": spec.get("quantization"),
        "source": "download" if spec.get("url") else "convert",
        "url": spec.get("url"),
        "sha256": sha256,
        "registry_sha256": spec.get("sha256"),
        "published_sha256": published,
        "matches_registry": (sha256 == spec["sha256"]) if spec.get("sha256") else None,
        "matches_published": (sha256 == published) if published else None,
    }, indent=2), encoding="utf-8")
    return out


def download(url: str, target: pathlib.Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "deal-test-stand"})
    with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / (1 << 20):8.0f} / {total / (1 << 20):.0f} MiB", end="",
                      file=sys.stderr, flush=True)
    print(file=sys.stderr)
    tmp.replace(target)


def cmd_list(_: argparse.Namespace) -> int:
    for name, spec in sorted(cfg.known_models().items()):
        present = "present" if (MODELS / spec["file"]).exists() else "absent"
        how = "download" if spec.get("url") else "convert"
        print(f"  {name:32s} {spec.get('quantization', '?'):7s} {how:9s} {present:8s} {spec['file']}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    print(path_of(entry(args.name)))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    spec = entry(args.name)
    target = path_of(spec)
    if not target.exists():
        print(f"missing: {target}\n  Run: python3 test_stand/models.py fetch {args.name}",
              file=sys.stderr)
        return 1
    actual = cfg.sha256_file(target)
    expected = spec.get("sha256")
    out = record(spec, actual)
    if expected and actual != expected:
        print(f"SHA-256 MISMATCH for {target.name}\n  registry: {expected}\n  on disk:  {actual}",
              file=sys.stderr)
        return 1
    print(f"{target.name}: sha256 {actual}" + ("" if expected else "  (registry has no hash yet)"))
    print(f"recorded {out}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    spec = entry(args.name)
    target = path_of(spec)
    MODELS.mkdir(exist_ok=True)
    if target.exists() and not args.force:
        print(f"already present: {target}")
    elif spec.get("url"):
        print(f"downloading {spec['url']}")
        download(spec["url"], target)
    else:
        print(f"{args.name} is a locally converted model; there is nothing to download.\n"
              f"  Run: test_stand/bin/prepare_model.sh {args.name}", file=sys.stderr)
        return 1
    return cmd_verify(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list").set_defaults(handler=cmd_list)
    for name, handler in (("fetch", cmd_fetch), ("path", cmd_path), ("verify", cmd_verify)):
        child = sub.add_parser(name)
        child.add_argument("name")
        if name == "fetch":
            child.add_argument("--force", action="store_true", help="re-download")
        child.set_defaults(handler=handler)
    args = parser.parse_args()
    try:
        return args.handler(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
