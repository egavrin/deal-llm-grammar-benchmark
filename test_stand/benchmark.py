#!/usr/bin/env python3
"""The stand, as one command: prompts + grammar + compiler -> benchmark result.

    benchmark.py doctor    show what the three inputs resolve to, and stop
    benchmark.py check     validate the inputs without generating anything
    benchmark.py run       generate, evaluate, and write a result directory

Every subcommand takes the same three inputs and never assumes any of them.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import config as cfg

STAND = pathlib.Path(__file__).resolve().parent


def cmd_doctor(args: argparse.Namespace) -> int:
    """Print the resolved configuration before anything is spent on it."""
    resolved = cfg.resolve(args)
    if args.json:
        # For shell scripts: the same resolution every entry point uses, as
        # one JSON object, so no script has to guess a .deps layout.
        print(json.dumps({
            "preset": resolved.preset,
            "prompts": str(resolved.prompts),
            "grammar": str(resolved.grammar),
            "compiler": str(resolved.compiler),
            "compiler_commit": resolved.compiler_commit(),
            "primer": str(resolved.primer),
            "example": str(resolved.example) if resolved.example else None,
            "system": str(resolved.system) if resolved.system else None,
            "model": str(resolved.model),
            "model_exists": resolved.model.exists(),
            "backend": resolved.backend,
            "java": str(resolved.tools.java),
            "luajit": str(resolved.tools.luajit / "luajit"),
            "llama_server": str(resolved.tools.server),
            "gbnf_validator": str(resolved.tools.validator),
            "tasks": [t.id for t in resolved.tasks()],
        }, indent=2))
        return 0
    print("resolved inputs")
    print(resolved.describe())
    print()
    print("tasks")
    for task in resolved.tasks():
        parts = ["brief" if task.brief.exists() else "NO BRIEF",
                 "reference" if task.reference.exists() else "NO REFERENCE",
                 "test" if task.test.exists() else "no test"]
        support = f" +{len(task.support)} support" if task.support else ""
        print(f"  {task.id:20s} {', '.join(parts)}{support}")
    print()
    missing = [t.id for t in resolved.tasks() if not t.reference.exists()]
    if missing:
        print(f"WARNING: no reference solution for: {', '.join(missing)}")
        print("  Coverage cannot be measured for these tasks.")
    print("fingerprint")
    for key, value in resolved.fingerprint(seed=args.seed,
                                           max_tokens=args.max_tokens).items():
        shown = value if not isinstance(value, str) or len(value) <= 16 else value[:16] + "…"
        print(f"  {key:18s} {shown}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Everything that can be verified without invoking the model."""
    import gate
    import coverage as coverage_lib

    resolved = cfg.resolve(args)
    print("resolved inputs")
    print(resolved.describe())
    failures = 0

    # A reference that does not compile means an impossible brief; a reference
    # that fails its own hidden test means the test is wrong, not the model.
    print("\n=== references compile and pass their own tests")
    import evaluate
    untested = []
    for task in resolved.tasks(args.tier):
        if not task.reference.exists():
            print(f"  MISSING   {task.id}  no reference solution")
            failures += 1
            continue
        result = evaluate.evaluate(task.reference.read_text(encoding="utf-8"),
                                   config=resolved, task=task)
        if not result.compile_success:
            print(f"  FAILED    {task.id}  does not compile: "
                  f"{' '.join(result.diagnostics)}")
            failures += 1
        elif result.functional_pass:
            print(f"  ok        {task.id}")
        elif result.interface_success is None:
            untested.append(task.id)
            print(f"  no test   {task.id}")
        elif not result.interface_success:
            print(f"  FAILED    {task.id}  test does not bind: "
                  f"{' '.join(result.interface_diagnostics)}")
            failures += 1
        else:
            print(f"  FAILED    {task.id}  reference fails its own test")
            failures += 1
    if untested:
        print(f"  {len(untested)} task(s) carry no hidden test: "
              f"{', '.join(untested)}")
        print("  They are measured up to `compiles` and excluded from the run "
              "and functional rungs.")

    print("\n=== prompt example and leakage")
    failures += check_example(resolved)

    print("\n=== corpus completeness")
    failures += coverage_lib.check_references(resolved)

    print("\n=== grammar fidelity")
    failures += gate.check(resolved)

    print()
    print("all checks passed" if not failures else f"{failures} problem(s)")
    return 1 if failures else 0


WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def protected_names(tasks: list[cfg.Task]) -> dict[str, str]:
    """Names the primer must not mention: task ids and every export a task asks for."""
    protected: dict[str, str] = {}
    for task in tasks:
        protected[task.id] = f"task id {task.id}"
        if task.reference.exists():
            for name in cfg.EXPORTED.findall(task.reference.read_text(encoding="utf-8")):
                protected[name] = f"export {name} of {task.id}"
    return protected


def leaked_names(text: str, protected: dict[str, str]) -> list[str]:
    """Protected names that occur in the text as whole identifiers."""
    words = set(WORD.findall(text))
    return sorted(w for w in words if w in protected)


def check_example(config: cfg.Config) -> int:
    """The primer must teach the language, never the tasks.

    Three things are enforced. The worked example compiles and is accepted by
    the grammar, so the model is shown real DEAL. And neither the primer nor the
    example mentions a task id or any name a task asks the model to export: if
    it did, part of the answer would be in the question.
    """
    import evaluate
    import gate

    failures = 0
    example = config.example
    primer = config.primer.read_text(encoding="utf-8")
    if "{example}" in primer and example is None:
        print(f"  FAILED    primer uses {{example}} but {config.prompts}/example.deal is missing")
        return 1
    if example is not None:
        source = example.read_text(encoding="utf-8")
        result = evaluate.evaluate(source, config=config, task=None)
        if not result.compile_success:
            print(f"  FAILED    example.deal does not compile: {' '.join(result.diagnostics)}")
            failures += 1
        else:
            print("  ok        example.deal compiles")
        if gate.accepts(config.tools.validator, config.grammar, source):
            print("  ok        example.deal is accepted by the grammar")
        else:
            print("  FAILED    example.deal is rejected by the grammar")
            failures += 1

    protected = protected_names(config.tasks())
    for label, path in (("primer", config.primer), ("example", example)):
        if path is None:
            continue
        leaked = leaked_names(path.read_text(encoding="utf-8"), protected)
        if leaked:
            print(f"  FAILED    {label} mentions task names: "
                  + ", ".join(f"{w} ({protected[w]})" for w in leaked))
            failures += 1
        else:
            print(f"  ok        {label} shares no name with any task ({len(protected)} protected)")
    return failures


def cmd_run(args: argparse.Namespace) -> int:
    import generate
    return generate.main(args)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
            ("doctor", cmd_doctor, "show what the inputs resolve to"),
            ("check", cmd_check, "validate inputs without running the model"),
            ("run", cmd_run, "generate, evaluate, write a result directory")):
        child = sub.add_parser(name, help=help_text)
        cfg.add_arguments(child)
        child.add_argument("--seed", type=int, default=42)
        child.add_argument("--max-tokens", type=int, default=1024)
        child.set_defaults(handler=handler)
        if name == "doctor":
            child.add_argument("--json", action="store_true",
                               help="machine-readable resolution, for scripts")
        if name == "run":
            child.add_argument("--out", type=pathlib.Path, required=True,
                               help="result directory")
            child.add_argument("--profiles", nargs="+", default=["raw", "constrained"],
                               choices=("raw", "constrained"))
            child.add_argument("--tasks", nargs="*", help="limit to these task ids")
            child.add_argument("--fresh", action="store_true",
                               help="ignore anything already in --out")
            child.add_argument("--port", type=int, default=8110)
            child.add_argument("--repair-rounds", type=int, default=0,
                               help="compiler-guided repair passes over failures")

    args = parser.parse_args()
    try:
        return args.handler(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
