#!/usr/bin/env python3
"""Check a variant's GBNF grammar against the language, in both directions.

accept: the grammar must accept every reference program of the variant and
        every fixture the compiler classifies as valid.
reject: the grammar must reject fixtures whose expected failure is lexical or
        syntactic (E1xxx).

Fixtures expecting E2xxx/E3xxx and above are reported but never required to be
rejected: those are name-resolution and typing errors, which a context-free
grammar cannot see. Demanding otherwise would be asking the grammar to do the
type checker's job.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

import config as cfg

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
EXPECTED = re.compile(r"@expected:\s*([a-z-]+)(?:\s+(E\d+))?")


def accepts(validator: pathlib.Path, grammar: pathlib.Path, source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(source)
        path = pathlib.Path(handle.name)
    try:
        run = subprocess.run([str(validator), str(grammar), str(path)],
                             capture_output=True, text=True, timeout=60, check=False)
        return "Input string is valid according to the grammar." in run.stdout + run.stderr
    finally:
        path.unlink(missing_ok=True)


def classify(text: str) -> tuple[str, str | None]:
    match = EXPECTED.search(text)
    return (match.group(1), match.group(2)) if match else ("unclassified", None)


# Exactly the four annotation names the conformance corpus uses as test
# metadata. Whitelisted rather than blacklisted on purpose: dropping every
# unrecognised `// @name` would delete the malformed directives that the
# negative fixtures exist to test, and the gate would score itself.
METADATA_NAMES = ("// @spec", "// @description", "// @expected", "// @features")


def strip_metadata(text: str) -> str:
    """Drop the conformance corpus's own test-metadata comments.

    They are that corpus's convention, not part of the language, and they
    collide with the compiler-directive syntax. Everything else, including
    malformed directives, is left for the grammar to judge.
    """
    lines = [line for line in text.splitlines()
             if not line.strip().startswith(METADATA_NAMES)]
    return "\n".join(lines) + "\n"


def check(config: cfg.Config, *, skip_fixtures: bool = False) -> int:
    """Gate: the grammar must accept every valid module the compiler accepts.

    Only the accept side is enforced. A grammar that rejects a valid program
    actively blocks the model from writing correct code; one that accepts a
    malformed program merely fails to help. The reject side is reported.
    """
    validator = config.tools.validator
    if not validator.exists():
        print(f"missing {validator}. Run: test_stand/bin/setup_linux.sh llama",
              file=sys.stderr)
        return 1

    grammar = config.grammar
    failures = 0

    references = [t.reference for t in config.tasks() if t.reference.exists()]
    references += [s for t in config.tasks() for s in t.support]
    rejected = [r for r in references
                if not accepts(validator, grammar, r.read_text(encoding="utf-8"))]
    print(f"accept / references: {len(references) - len(rejected)}/{len(references)}")
    for path in rejected:
        print(f"  NOT ACCEPTED  {path.parent.name}/{path.name}")
    failures += len(rejected)

    if skip_fixtures:
        return failures

    buckets: dict[str, list[tuple[pathlib.Path, bool]]] = {}
    for path in sorted((config.compiler / "test/conformance").rglob("*.deal")):
        # `.d.deal` declaration files use ExternalFunctionDeclaration, which the
        # spec marks "declaration files only" — a different surface from the
        # modules a model is asked to write.
        if path.name.endswith(".d.deal"):
            continue
        text = path.read_text(encoding="utf-8")
        kind, code = classify(text)
        if kind in ("compile-ok", "runtime-ok", "companion"):
            bucket = "valid"
        elif kind == "compile-error" and code and code.startswith("E1"):
            bucket = "syntax-error"
        elif kind in ("compile-error", "runtime-error"):
            bucket = "beyond-grammar"
        else:
            bucket = "unclassified"
        buckets.setdefault(bucket, []).append(
            (path, accepts(validator, grammar, strip_metadata(text))))

    valid = buckets.get("valid", [])
    wrong = [p for p, ok in valid if not ok]
    print(f"accept / valid fixtures: {len(valid) - len(wrong)}/{len(valid)}")

    # The conformance corpus is written in the language the compiler implements.
    # A candidate grammar for a later version must reject exactly the fixtures
    # using what that version removed: listing them in the preset turns a
    # blanket waiver into a two-way check, so a fixture that starts or stops
    # failing is still noticed.
    expected = set(config.expects_rejected_fixtures)
    if expected:
        got = {p.name for p in wrong}
        unexpected = sorted(got - expected)
        stale = sorted(expected - got)
        print(f"  of those, {len(got & expected)} are declared in the preset as written "
              f"in the older language")
        for name in unexpected[:20]:
            print(f"  NOT ACCEPTED, not declared  {name}")
        for name in stale[:20]:
            print(f"  declared but accepted, the list is stale  {name}")
        failures += len(unexpected) + len(stale)
    else:
        for path in wrong[:20]:
            print(f"  NOT ACCEPTED  {path.name}")
        if len(wrong) > 20:
            print(f"  ... and {len(wrong) - 20} more")
        if wrong:
            # The list is what a candidate grammar's preset has to declare, so
            # print it whole and paste-ready rather than making the reader
            # reconstruct it from a truncated log.
            print("  If this grammar is a later language version, declare them:")
            print("    \"expects_rejected_fixtures\": "
                  + json.dumps(sorted(p.name for p in wrong)))
        failures += len(wrong)

    # Reported, never enforced: once comments are in the grammar, a malformed
    # `// @deal-version ...` is indistinguishable from an ordinary comment, so
    # some E1xxx fixtures must leak through any honest context-free grammar.
    syntax = buckets.get("syntax-error", [])
    leaked = [p for p, ok in syntax if ok]
    print(f"reject / E1xxx fixtures: {len(syntax) - len(leaked)}/{len(syntax)}")
    for path in leaked[:20]:
        print(f"  NOT REJECTED  {path.name}")

    beyond = buckets.get("beyond-grammar", [])
    accepted = sum(1 for _, ok in beyond if ok)
    print(f"beyond grammar: {len(beyond)} fixture(s) fail above the parser; "
          f"the grammar accepts {accepted} of them, as a context-free grammar must")

    unclassified = buckets.get("unclassified", [])
    if unclassified:
        print(f"unclassified: {len(unclassified)} fixture(s) carry no @expected")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    cfg.add_arguments(parser)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--skip-fixtures", action="store_true")
    args = parser.parse_args()
    try:
        config = cfg.resolve(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2
    return 1 if check(config, skip_fixtures=args.skip_fixtures) else 0


if __name__ == "__main__":
    sys.exit(main())
