#!/usr/bin/env python3
"""Compare two runs: what changed in the inputs, and what moved as a result.

    compare.py results/before results/after
    compare.py results/before results/after --json compare.json

Reads each run's summary.json (written by `run`, or by `report.py DIR`), so it
needs no toolchain. Everything is paired by (task, profile): a rate that went
from 2/14 to 3/14 says less than "config_lookup moved from syntax to compiles
and kv_cache moved the other way".
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from report import PROFILE_ORDER, RUNGS, RUNG_LABELS


def load(path: pathlib.Path) -> dict[str, Any]:
    out_dir = path if path.is_dir() else path.parent
    summary = out_dir / "summary.json"
    if not summary.exists():
        raise SystemExit(f"{summary} does not exist.\n"
                         f"  Run: python3 test_stand/report.py {out_dir} --preset NAME")
    return json.loads(summary.read_text(encoding="utf-8"))


def fingerprint_diff(a: dict, b: dict) -> list[tuple[str, Any, Any]]:
    fa = ((a.get("inputs") or {}).get("fingerprint") or {})
    fb = ((b.get("inputs") or {}).get("fingerprint") or {})

    def same(x: Any, y: Any) -> bool:
        # A key the older run never wrote and an empty list mean the same
        # thing: nothing was declared. Only emptiness is forgiven, so a real
        # value against a missing key still shows.
        if x == y:
            return True
        return x in (None, [], (), "") and y in (None, [], (), "")

    return [(key, fa.get(key), fb.get(key)) for key in sorted(set(fa) | set(fb))
            if not same(fa.get(key), fb.get(key))]


def short(value: Any) -> str:
    text = str(value)
    return text[:16] + "…" if isinstance(value, str) and len(text) > 20 else text


def compare(a: dict, b: dict, label_a: str, label_b: str) -> dict[str, Any]:
    profiles = [p for p in PROFILE_ORDER if p in a["profiles"] and p in b["profiles"]]
    result: dict[str, Any] = {
        "a": label_a, "b": label_b,
        "inputs_changed": [{"key": k, "a": va, "b": vb} for k, va, vb in fingerprint_diff(a, b)],
        "profiles": {},
        "tiers": {},
    }
    for tier in [t for t in (a.get("tiers") or {}) if t in (b.get("tiers") or {})]:
        ta, tb = a["tiers"][tier]["profiles"], b["tiers"][tier]["profiles"]
        result["tiers"][tier] = {
            profile: {label: {"a": ta[profile][label], "b": tb[profile][label]}
                      for label in ("syntax", "compiles", "interface", "runs", "passes", "hit_cap")}
            for profile in PROFILE_ORDER if profile in ta and profile in tb}
    for profile in profiles:
        pa, pb = a["profiles"][profile], b["profiles"][profile]
        tasks = sorted(set(pa["per_task"]) | set(pb["per_task"]))
        moved = []
        for task in tasks:
            ra = pa["per_task"].get(task, {}).get("rung")
            rb = pb["per_task"].get(task, {}).get("rung")
            if ra != rb:
                moved.append({"task": task, "a": ra, "b": rb,
                              "a_label": RUNG_LABELS[ra] if ra is not None else "absent",
                              "b_label": RUNG_LABELS[rb] if rb is not None else "absent"})
        ca, cb = set(pa["coverage"]["compiled"]), set(pb["coverage"]["compiled"])
        cost_keys = ("prompt_tokens_mean", "output_tokens_mean", "generation_ms_p50",
                     "generation_ms_p95", "aggregate_tokens_per_second",
                     "server_ms_per_compiled", "server_ms_per_atom", "argmax_rejection_rate")
        result["profiles"][profile] = {
            "levels": {label: {"a": pa[label], "b": pb[label]}
                       for label in ("no_fence", "syntax", "compiles", "interface", "runs",
                                     "passes", "hit_cap")},
            "moved": moved,
            "up": sum(1 for m in moved if (m["b"] or 0) > (m["a"] or 0)),
            "down": sum(1 for m in moved if (m["b"] or 0) < (m["a"] or 0)),
            "atoms": {"a": len(ca), "b": len(cb),
                      "gained": sorted(cb - ca), "lost": sorted(ca - cb)},
            "cost": {key: {"a": pa["cost"].get(key), "b": pb["cost"].get(key)} for key in cost_keys},
            "echoes_example": {"a": len(pa.get("echoes_example", [])),
                               "b": len(pb.get("echoes_example", []))},
        }
    return result


def render(diff: dict[str, Any]) -> str:
    out: list[str] = []
    say = out.append
    a, b = diff["a"], diff["b"]
    say("=" * 78)
    say(f"COMPARE  A = {a}")
    say(f"         B = {b}")
    say("")
    say("inputs that differ")
    if not diff["inputs_changed"]:
        say("  none: same grammar, prompts, compiler, model and decoding parameters")
    for item in diff["inputs_changed"]:
        say(f"  {item['key']:18s} {short(item['a']):>20s} -> {short(item['b'])}")

    for profile, info in diff["profiles"].items():
        say("")
        say("=" * 78)
        say(f"{profile.upper()}")
        say(f"{'rung':12s} {'A':>5s} {'B':>5s} {'delta':>6s}")
        for label, pair in info["levels"].items():
            delta = pair["b"] - pair["a"]
            say(f"{label:12s} {pair['a']:5d} {pair['b']:5d} {delta:+6d}")
        say(f"  tasks moved up: {info['up']}, down: {info['down']}")
        for m in info["moved"]:
            arrow = "up  " if (m["b"] or 0) > (m["a"] or 0) else "down"
            say(f"    {arrow} {m['task']:18s} {m['a_label']:>13s} -> {m['b_label']}")
        atoms = info["atoms"]
        say(f"  atoms in compiled code: {atoms['a']} -> {atoms['b']} "
            f"(+{len(atoms['gained'])} / -{len(atoms['lost'])})")
        if atoms["gained"]:
            say(f"    gained: {', '.join(atoms['gained'])}")
        if atoms["lost"]:
            say(f"    lost:   {', '.join(atoms['lost'])}")
        say(f"  answers copying the primer's example: "
            f"{info['echoes_example']['a']} -> {info['echoes_example']['b']}")
        say("  cost")
        for key, pair in info["cost"].items():
            fa = "--" if pair["a"] is None else f"{pair['a']:.1f}"
            fb = "--" if pair["b"] is None else f"{pair['b']:.1f}"
            say(f"    {key:28s} {fa:>10s} -> {fb}")

    if len(diff.get("tiers") or {}) > 1:
        say("")
        say("=" * 78)
        say("BY TIER")
        say(f"{'tier':9s} {'profile':12s} " + " ".join(f"{l:>14s}" for l in ("syntax", "compiles", "interface", "runs", "passes", "hit_cap")))
        for tier, profiles in diff["tiers"].items():
            for profile, levels in profiles.items():
                say(f"{tier:9s} {profile:12s} " + " ".join(
                    f"{v['a']:>5d} -> {v['b']:<5d}" for v in levels.values()))

    say("")
    say("One task is 1/n of a rung; read the moved list, not the delta, when n is small.")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("a", type=pathlib.Path, help="the earlier run directory")
    parser.add_argument("b", type=pathlib.Path, help="the later run directory")
    parser.add_argument("--json", type=pathlib.Path, help="also write the comparison here")
    args = parser.parse_args()
    diff = compare(load(args.a), load(args.b), str(args.a), str(args.b))
    print(render(diff), end="")
    if args.json:
        args.json.write_text(json.dumps(diff, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
