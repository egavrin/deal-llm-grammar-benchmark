#!/usr/bin/env python3
"""Measure how much of the DEAL language a set of programs exercises.

The universe of language atoms is derived from the compiler sources, never
hand-listed: add a construct to the language and the universe grows on the next
run, so a corpus cannot silently go stale. Coverage of each program is measured
by stand.CoverageProbe, which walks the real parser's AST.

Two questions, same measurement:
  --references  are the stand's reference programs complete? (gate: 100%)
  --outputs     how much of the language did the model actually reproduce?
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import subprocess
import sys

import config as cfg

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

# Nodes every program instantiates, or that encode structure rather than a
# construct an author chooses. Counted in the universe but reported separately
# so the discretionary figure is not diluted.
STRUCTURAL = {
    "node:ProgramNode", "node:Block", "node:FileDirectives", "node:DealVersion",
    "node:Parameter", "node:Property", "node:ClassField", "node:FunctionTypeParam",
    "type:user-named", "either:Left", "either:Right",
}

# Atoms that no "write me one module" prompt can reach, with the reason.
# Reported separately so the reference gate stays honest instead of being
# padded with contrived programs that could never be elicited from a model.
OUT_OF_SCOPE = {
    "modifier:external": "ExternalFunctionDeclaration is declaration-files-only",
    "directive:C_STRUCT": "C FFI declaration surface",
    "directive:C_POINTER": "C FFI declaration surface",
    "import:host": "host ABI needs a host harness, not a DEAL module",
}

MODIFIERS = [
    "modifier:async", "modifier:external", "modifier:field-optional",
    "modifier:field-required", "modifier:field-default",
]

TYPE_NAMES = {
    "Null": "null", "Boolean": "boolean", "Int": "int", "Number": "number",
    "String": "string", "Bytes": "bytes", "Table": "table", "Error": "Error",
}


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def derive_universe(compiler: pathlib.Path) -> dict[str, str]:
    """Map atom -> category, derived from compiler sources and the stdlib."""
    universe: dict[str, str] = {}

    ast_dir = compiler / "deal/ast"
    for source in sorted(ast_dir.glob("*.java")):
        text = read(source)
        # Top-level node records.
        for name in re.findall(r"^public record (\w+)", text, re.M):
            universe[f"node:{name}"] = "node"
        # Nested records inside sealed interfaces (LiteralValue, ForInit, Either).
        outer = source.stem
        for name in re.findall(r"^\s{4}record (\w+)", text, re.M):
            if outer == "LiteralValue":
                universe[f"literal:{name}"] = "literal"
            else:
                universe[f"{outer.lower()}:{name}"] = "structure"

    for enum_file, prefix in (("BinaryOp", "binop"), ("UnaryOp", "unop"),
                              ("DeclarationDirective", "directive")):
        text = read(ast_dir / f"{enum_file}.java")
        # Anchor on the declaration, not the first brace: the javadoc above it
        # contains {@link #CONSTANT} references that would otherwise be parsed
        # as enum body.
        start = re.search(rf"enum {enum_file}\b[^{{]*{{", text)
        body = text[start.end():]
        # The final constant carries no trailing comma or semicolon.
        for name in re.findall(r"^\s+([A-Z][A-Z_0-9]*)\s*(?:[,;]|//|$)", body, re.M):
            universe[f"{prefix}:{name}"] = prefix

    # Primitive types: singleton enums in the sealed Type hierarchy.
    type_text = read(compiler / "deal/types/Type.java")
    for name in re.findall(r"^\s+enum (\w+) implements Type", type_text, re.M):
        universe[f"type:{TYPE_NAMES.get(name, name)}"] = "type"

    for decl in sorted((compiler / "std").glob("*.d.deal")):
        module = decl.name.removesuffix(".d.deal")
        for fn in re.findall(r"export function (\w+)\s*\(", read(decl)):
            universe[f"stdlib:{module}.{fn}"] = "stdlib"
        universe[f"import:std/{module}"] = "import"

    for modifier in MODIFIERS:
        universe[modifier] = "modifier"

    # Module-system capabilities that carry no fixed name: importing a sibling
    # module and importing a host module.
    universe["import:local"] = "import"
    universe["import:host"] = "import"
    # Referring to a user-declared class in type position.
    universe["type:user-named"] = "type"

    for name in ("Span", "DiagnosticRange"):
        universe.pop(f"node:{name}", None)
    return universe


def build_probe(config: cfg.Config) -> pathlib.Path:
    """Compile the AST walker, rebuilding whenever anything it depends on moved.

    The walker is compiled against the compiler's own AST classes, so a stale
    build silently measures coverage against an old language. Keying the cache
    on a fingerprint of both the walker source and the compiler checkout makes
    that impossible; an mtime check on the source alone does not.
    """
    out = HERE / "capability/build"
    source = HERE / "capability/stand/CoverageProbe.java"
    stamp = out / ".fingerprint"
    want = "\n".join([
        cfg.sha256_file(source),
        config.compiler_commit(),
        cfg.sha256_tree(config.compiler / "deal/ast", *()),
    ])
    if stamp.exists() and stamp.read_text(encoding="utf-8") == want:
        return out
    subprocess.run(
        [str(config.tools.javac), "--release", "25", "-proc:none",
         "-cp", str(config.compiler / "build"), "-d", str(out), str(source)],
        check=True,
    )
    out.mkdir(parents=True, exist_ok=True)
    stamp.write_text(want, encoding="utf-8")
    return out


def probe(config: cfg.Config, files: list[pathlib.Path],
          tolerate_directive_noise: bool = False) -> list[dict]:
    if not files:
        return []
    build = build_probe(config)
    rows: list[dict] = []
    # Batched to keep the argument list well inside the OS limit.
    for start in range(0, len(files), 200):
        chunk = files[start:start + 200]
        run = subprocess.run(
            [str(config.tools.java), "-cp", f"{build}:{config.compiler / 'build'}",
             "stand.CoverageProbe",
             *(["--ignore-directive-noise"] if tolerate_directive_noise else []),
             *map(str, chunk)],
            capture_output=True, text=True, check=True,
        )
        rows.extend(json.loads(line) for line in run.stdout.splitlines() if line.strip())
    return rows


def report(universe: dict[str, str], rows: list[dict], label: str,
           out_dir: pathlib.Path | None,
           extra_out_of_scope: dict[str, str] | None = None) -> int:
    seen: dict[str, list[str]] = {}
    unknown: set[str] = set()
    for row in rows:
        for atom in row["atoms"]:
            if atom in universe:
                seen.setdefault(atom, []).append(row["file"])
            else:
                unknown.add(atom)

    out_of_scope = dict(OUT_OF_SCOPE, **(extra_out_of_scope or {}))

    def split(items):
        return [a for a in items
                if a not in STRUCTURAL and a not in out_of_scope]

    covered = split(seen)
    missing = split([a for a in universe if a not in seen])
    total = len(covered) + len(missing)
    pct = 100.0 * len(covered) / total if total else 0.0

    print(f"\n{label}: {len(rows)} file(s)")
    print(f"in-scope coverage: {len(covered)}/{total} = {pct:.1f}%")
    print(f"out of scope:      {len(out_of_scope)} atom(s) unreachable from a module prompt")
    unparsed = [r["file"] for r in rows if not r["parse_ok"]]
    if unparsed:
        print(f"did not parse: {len(unparsed)}")

    if missing:
        print(f"\nmissing ({len(missing)}):")
        by_category: dict[str, list[str]] = {}
        for atom in missing:
            by_category.setdefault(universe[atom], []).append(atom)
        for category in sorted(by_category):
            print(f"  {category:9s} {', '.join(sorted(by_category[category]))}")

    if unknown:
        # The probe emitted an atom the universe does not know: either the
        # language grew or the derivation is wrong. Never silently ignored.
        print(f"\nWARNING: {len(unknown)} atom(s) outside the derived universe:")
        for atom in sorted(unknown):
            print(f"  {atom}")

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "coverage.csv"
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["atom", "category", "structural", "out_of_scope",
                             "covered", "occurrences"])
            for atom in sorted(universe):
                writer.writerow([atom, universe[atom], atom in STRUCTURAL,
                                 atom in out_of_scope, atom in seen,
                                 len(seen.get(atom, []))])
        print(f"\nwrote {target}")

    return len(missing)


def check_references(config: cfg.Config) -> int:
    """Gate: the prompt set's reference solutions must exercise every in-scope atom.

    Returns the number of gaps; zero means the corpus is complete. An incomplete
    corpus makes "the model reproduced N atoms" uninterpretable, because the
    denominator would include atoms no brief ever asks for.
    """
    universe = derive_universe(config.compiler)
    # A candidate grammar for a later language version drops constructs the
    # compiler still has. Those atoms cannot be covered and must not be demanded;
    # a name that is not in the universe is a typo in the preset, not a removal.
    removed = {}
    for atom in config.removes:
        if atom not in universe:
            print(f"  preset lists an unknown atom in `removes`: {atom}")
            return 1
        removed[atom] = f"removed by this language version ({config.preset})"
    if removed:
        print(f"removed by this language version: {len(removed)} atom(s) — "
              + ", ".join(sorted(removed)))
    references = [t.reference for t in config.tasks() if t.reference.exists()]
    references += [s for t in config.tasks() for s in t.support]
    rows = probe(config, references)
    return report(universe, rows, "references", None, extra_out_of_scope=removed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    cfg.add_arguments(parser)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--references", action="store_true",
                        help="measure the prompt set's reference solutions (gate)")
    parser.add_argument("--corpus", choices=("conformance",),
                        help="measure the compiler's own conformance fixtures")
    parser.add_argument("--files", nargs="*", type=pathlib.Path)
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--universe", action="store_true",
                        help="print the derived universe and exit")
    args = parser.parse_args()

    try:
        config = cfg.resolve(args)
    except cfg.ConfigError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    universe = derive_universe(config.compiler)
    if args.universe:
        by_category: dict[str, int] = {}
        for category in universe.values():
            by_category[category] = by_category.get(category, 0) + 1
        for category in sorted(by_category):
            print(f"{category:9s} {by_category[category]}")
        in_scope = [a for a in universe
                    if a not in STRUCTURAL and a not in OUT_OF_SCOPE]
        print(f"{'TOTAL':9s} {len(universe)}  ({len(in_scope)} in scope)")
        return 0

    tolerate = False
    if args.corpus == "conformance":
        files = sorted((config.compiler / "test/conformance").rglob("*.deal"))
        label = "conformance fixtures"
        tolerate = True
    elif args.references:
        return 1 if check_references(config) else 0
    elif args.files:
        files = list(args.files)
        label = "files"
    else:
        parser.error("choose one of --references, --corpus, --files, --universe")

    rows = probe(config, files, tolerate)
    report(universe, rows, label, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
