#!/usr/bin/env python3
"""Resolve the three benchmark inputs — prompts, grammar, compiler.

One rule holds this together: **no module has its own default for an input.**
A missing input raises a message naming exactly what to set. It never falls back
to a path that happened to work on the machine where this was written, because
that failure mode is silent: the stand keeps running and reports numbers for the
wrong compiler.

Resolution order, the same everywhere:

    explicit argument  ->  preset file  ->  test_stand/.env  ->  error

The toolchain (JDK, LuaJIT, llama.cpp) is resolved the same way, from the .env
that `bin/setup_linux.sh` writes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import subprocess

STAND = pathlib.Path(__file__).resolve().parent
ROOT = STAND.parent
ENV_FILE = STAND / ".env"

ENV_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
EXPORTED = re.compile(r"^export\s+(?:async\s+)?(?:function|class)\s+([A-Za-z_][A-Za-z0-9_]*)",
                      re.M)
MODEL_REGISTRY = STAND / "models.json"


class ConfigError(Exception):
    """An input could not be resolved. The message says what to set."""


# --------------------------------------------------------------------- env ---

def read_env() -> dict[str, str]:
    """Values from test_stand/.env, overridden by the real environment."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    values.update({k: v for k, v in os.environ.items() if k in ENV_KEYS or k.startswith("DEAL_")})
    return values


ENV_KEYS = {"DEAL_COMPILER", "DEAL_STAND_JDK", "DEAL_STAND_LUAJIT",
            "DEAL_STAND_LLAMA", "DEAL_STAND_MODEL"}

# The model a run uses when nothing names one. The smallest of the pair the
# stand ships: a first run finishes in minutes, and a bigger model is one
# `--model` away.
DEFAULT_MODEL = "qwen2.5-coder-0.5b"


def expand(value: str, env: dict[str, str]) -> str:
    """Expand ${VAR} against the resolved environment, or say what is missing."""
    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ConfigError(
                f"{name} is not set.\n"
                f"  Set it in {ENV_FILE} or export it, for example:\n"
                f"    echo '{name}=/path/to/value' >> {ENV_FILE}")
        return env[name]
    return ENV_VAR.sub(one, value)


# ----------------------------------------------------------------- inputs ---

@dataclasses.dataclass(frozen=True)
class Toolchain:
    jdk: pathlib.Path
    luajit: pathlib.Path
    llama: pathlib.Path

    @property
    def java(self) -> pathlib.Path:
        return self.jdk / "bin/java"

    @property
    def javac(self) -> pathlib.Path:
        return self.jdk / "bin/javac"

    @property
    def validator(self) -> pathlib.Path:
        return self.llama / "test-gbnf-validator"

    @property
    def server(self) -> pathlib.Path:
        return self.llama / "llama-server"


# Two tiers of task. `modules` are the task directories at the top of the
# prompt set: several exports, classes, stdlib, a hidden test per module.
# `quick` are the directories under prompts/<set>/quick/: one function each,
# small enough that a small model passes a fair share of them, so a change in
# grammar or prompt shows as a shift of many tasks rather than of one.
TIERS = ("modules", "quick")
QUICK_DIR = "quick"


@dataclasses.dataclass(frozen=True)
class Task:
    """One prompt directory: the brief, its reference solution, its test."""
    id: str
    directory: pathlib.Path
    tier: str = "modules"

    @property
    def brief(self) -> pathlib.Path:
        return self.directory / "brief.md"

    @property
    def reference(self) -> pathlib.Path:
        return self.directory / "reference.deal"

    @property
    def test(self) -> pathlib.Path:
        return self.directory / "test.deal"

    @property
    def support(self) -> list[pathlib.Path]:
        """Companion modules the task's brief says already exist."""
        directory = self.directory / "support"
        return sorted(directory.glob("*.deal")) if directory.is_dir() else []


def known_models() -> dict[str, dict]:
    """Entries of test_stand/models.json, minus the `_about` commentary key."""
    if not MODEL_REGISTRY.exists():
        return {}
    registry = json.loads(MODEL_REGISTRY.read_text(encoding="utf-8"))
    return {name: spec for name, spec in registry.items() if not name.startswith("_")}


def resolve_model(value: str, env: dict[str, str]) -> pathlib.Path:
    """A model may be named from models.json, or given as a path.

    Naming it is the friendlier form: the registry knows the repo, revision and
    quantization, so `bin/prepare_model.sh <name>` and the preset agree on where
    the file lands without either restating it.
    """
    registry = known_models()
    if value in registry:
        return (ROOT / "models" / registry[value]["file"]).resolve()
    path = pathlib.Path(expand(value, env)).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


@dataclasses.dataclass(frozen=True)
class Config:
    prompts: pathlib.Path
    grammar: pathlib.Path
    compiler: pathlib.Path
    primer: pathlib.Path
    model: pathlib.Path
    backend: str
    tools: Toolchain
    preset: str | None
    # A grammar for a language version the compiler does not implement yet: it
    # is a subset, so everything it allows still compiles, but two gates would
    # fail for reasons that are the point rather than a defect. `removes` names
    # the atoms the candidate version drops, so corpus completeness stops
    # demanding them; `expects_rejected_fixtures` names the compiler's own
    # conformance fixtures written in the older language, so grammar fidelity
    # can require exactly those and no others.
    removes: tuple[str, ...] = ()
    expects_rejected_fixtures: tuple[str, ...] = ()
    # True when nothing named a model and DEFAULT_MODEL was used. The default
    # exists so a first run works, but it is never silent: `describe` says so,
    # and the fingerprint records the model that actually ran either way.
    model_defaulted: bool = False

    def tasks(self, tier: str = "all") -> list[Task]:
        """Tasks of one tier, or of both; ids are unique across tiers."""
        found = [Task(d.name, d, "modules") for d in sorted(self.prompts.iterdir())
                 if d.is_dir() and (d / "brief.md").exists()]
        quick = self.prompts / QUICK_DIR
        if quick.is_dir():
            found += [Task(d.name, d, "quick") for d in sorted(quick.iterdir())
                      if d.is_dir() and (d / "brief.md").exists()]
        if tier != "all":
            if tier not in TIERS:
                raise ConfigError(f"unknown tier {tier!r}; one of {', '.join(TIERS)}, all")
            found = [t for t in found if t.tier == tier]
        if not found:
            raise ConfigError(f"no tasks in {self.prompts} (tier {tier})\n"
                              "  A task is a directory holding brief.md, "
                              "reference.deal and test.deal.")
        ids = [t.id for t in found]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ConfigError("task ids must be unique across tiers: " + ", ".join(duplicates))
        return found

    @property
    def example(self) -> pathlib.Path | None:
        """The prompt set's worked example, substituted for {example} in the primer.

        Part of the prompt set, not of the stand: what a complete module looks
        like depends on the language. Checked by `benchmark.py check` to compile,
        to be accepted by the grammar, and to share no names with any task.
        """
        path = self.prompts / "example.deal"
        return path if path.exists() else None

    @property
    def system(self) -> pathlib.Path | None:
        """The chat system message, part of the prompt set like the primer."""
        path = self.prompts / "system.txt"
        return path if path.exists() else None

    def system_prompt(self) -> str:
        if self.system is None:
            raise ConfigError(
                f"{self.prompts}/system.txt does not exist.\n"
                "  The system message is part of the prompt set; add the file.")
        return self.system.read_text(encoding="utf-8").strip()

    def example_exports(self) -> list[str]:
        """Names the worked example exports; an answer containing them copied it."""
        if self.example is None:
            return []
        return EXPORTED.findall(self.example.read_text(encoding="utf-8"))

    def render_prompt(self, task: Task) -> str:
        """The exact user message for a task: primer with example and brief filled in."""
        text = self.primer.read_text(encoding="utf-8")
        if "{example}" in text:
            if self.example is None:
                raise ConfigError(
                    f"{self.primer} uses {{example}} but {self.prompts}/example.deal "
                    "does not exist.")
            text = text.replace("{example}",
                                self.example.read_text(encoding="utf-8").strip())
        return text.replace("{task}", task.brief.read_text(encoding="utf-8").strip())

    def compiler_commit(self) -> str:
        run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.compiler,
                             capture_output=True, text=True, check=False)
        return run.stdout.strip() or "unknown"

    def fingerprint(self, *, seed: int, max_tokens: int) -> dict[str, object]:
        """Everything a result depends on.

        Recorded with every run and compared on resume: if any of it changed,
        previously generated rows are not reusable and the run says so instead
        of quietly mixing old and new numbers.
        """
        return {
            "grammar_sha256": sha256_file(self.grammar),
            "primer_sha256": sha256_file(self.primer),
            "example_sha256": sha256_file(self.example) if self.example else None,
            "system_sha256": sha256_file(self.system) if self.system else None,
            "prompts_sha256": sha256_tree(self.prompts, "brief.md"),
            "compiler_commit": self.compiler_commit(),
            "model_sha256": sha256_file(self.model) if self.model.exists() else None,
            "backend": self.backend,
            **({"removes": list(self.removes)} if self.removes else {}),
            "seed": seed,
            "max_tokens": max_tokens,
        }

    def describe(self) -> str:
        lines = [
            f"  preset    {self.preset or '(none, explicit arguments)'}",
            f"  prompts   {self.prompts}  ({len(self.tasks())} tasks)",
            f"  grammar   {self.grammar}",
            f"  compiler  {self.compiler}  @ {self.compiler_commit()[:12]}",
            f"  primer    {self.primer}",
            f"  model     {self.model.name}"
            + ("   (default: nothing chose it)" if self.model_defaulted else "")
            + ("" if self.model.exists() else
               "   MISSING — run bin/prepare_model.sh"),
            f"  backend   {self.backend}",
        ] + ([f"  removes   {', '.join(self.removes)}"] if self.removes else []) + [

            f"  jdk       {self.tools.jdk}",
            f"  luajit    {self.tools.luajit}",
            f"  llama.cpp {self.tools.llama}",
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------ hashes ---

def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(directory: pathlib.Path, *names: str) -> str:
    """Hash of selected files across a task tree, in a stable order."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and (not names or path.name in names):
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(sha256_file(path).encode())
    return digest.hexdigest()


# ------------------------------------------------------------------ resolve ---

def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The three inputs, plus the escape hatches. Deliberately no defaults."""
    group = parser.add_argument_group("inputs")
    group.add_argument("--preset", help="named set of inputs from test_stand/presets")
    group.add_argument("--prompts", type=pathlib.Path,
                       help="directory of task directories")
    group.add_argument("--grammar", type=pathlib.Path, help="GBNF file")
    group.add_argument("--compiler", type=pathlib.Path,
                       help="DEAL compiler checkout (or set DEAL_COMPILER)")
    group.add_argument("--primer", type=pathlib.Path,
                       help="language primer prompt with a {task} placeholder")
    group.add_argument("--model",
                       help="a name from test_stand/models.json, or a GGUF path")
    group.add_argument("--tier", default="all", choices=("all", *TIERS),
                       help="which tier of tasks: modules (the long one), quick, or all")


def resolve(args: argparse.Namespace) -> Config:
    env = read_env()
    preset: dict[str, str] = {}
    name = getattr(args, "preset", None)
    if name:
        path = STAND / "presets" / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in (STAND / "presets").glob("*.json"))
            raise ConfigError(f"no preset {name!r}\n  available: "
                              + (", ".join(available) or "(none)"))
        preset = json.loads(path.read_text(encoding="utf-8"))

    def pick(field: str, description: str, *, required: bool = True,
             env_key: str | None = None) -> pathlib.Path | None:
        given = getattr(args, field, None)
        if given is not None:
            return pathlib.Path(given).expanduser().resolve()
        if field in preset:
            value = expand(str(preset[field]), env)
            path = pathlib.Path(value).expanduser()
            return (path if path.is_absolute() else STAND / path).resolve()
        if env_key and env_key in env:
            return pathlib.Path(env[env_key]).expanduser().resolve()
        if not required:
            return None
        raise ConfigError(
            f"{description} is not set.\n"
            f"  Pass --{field} PATH, or use --preset NAME, or set it in {ENV_FILE}.\n"
            f"  Run `python3 test_stand/benchmark.py doctor` to see what resolves.")

    def tool(key: str, description: str) -> pathlib.Path:
        if key not in env:
            raise ConfigError(
                f"{description} is not set ({key}).\n"
                f"  Run test_stand/bin/setup_linux.sh — it writes {ENV_FILE}.")
        return pathlib.Path(env[key]).expanduser().resolve()

    compiler = pick("compiler", "the DEAL compiler checkout", env_key="DEAL_COMPILER")
    if "DEAL_COMPILER" not in env:
        env["DEAL_COMPILER"] = str(compiler)

    # Explicit argument, then the preset, then .env, then the smallest Qwen the
    # stand ships with. The default is deliberately loud rather than silent:
    # `describe` marks it, so a run never reports numbers for a model the reader
    # believes somebody picked.
    chosen = (getattr(args, "model", None) or preset.get("model")
              or env.get("DEAL_STAND_MODEL"))
    defaulted = not chosen
    model = resolve_model(str(chosen or DEFAULT_MODEL), env)

    config = Config(
        removes=tuple(preset.get("removes", ())),
        expects_rejected_fixtures=tuple(preset.get("expects_rejected_fixtures", ())),
        prompts=pick("prompts", "the prompt set"),
        grammar=pick("grammar", "the grammar"),
        compiler=compiler,
        primer=pick("primer", "the language primer"),
        model=model,
        backend=str(preset.get("backend", "luajit")),
        tools=Toolchain(jdk=tool("DEAL_STAND_JDK", "the JDK"),
                        luajit=tool("DEAL_STAND_LUAJIT", "LuaJIT"),
                        llama=tool("DEAL_STAND_LLAMA", "llama.cpp binaries")),
        preset=name,
        model_defaulted=defaulted,
    )

    missing = [f"{label}: {path}" for label, path in
               (("prompts", config.prompts), ("grammar", config.grammar),
                ("compiler", config.compiler), ("primer", config.primer))
               if not path.exists()]
    if missing:
        raise ConfigError("input path does not exist:\n  " + "\n  ".join(missing))
    return config
