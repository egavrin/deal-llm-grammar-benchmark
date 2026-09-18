#!/usr/bin/env python3
"""Compile, and optionally run, a generated DEAL module with the real compiler.

Derived from the published benchmark's deal_v12_eval.py, with three changes:

  * diagnostics come from `--diagnostics-json` instead of a regex over stderr,
    so codes and severities are read rather than guessed;
  * the project uses a named module root. The benchmark used
    `moduleRoots: ["."]`, which the current compiler rejects for any exported
    class with E2010 "the configured root '.' is not representable";
  * execution is optional. The primary metric is compilation: it means names
    resolved, types checked and lowering succeeded, which is what tells us the
    model hit the language rather than merely its grammar.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import config as cfg

FENCE = re.compile(r"\A\s*```[^\n]*\n([\s\S]*?)\n```\s*\Z")

PASS_MARKER = "__DEAL_BENCH_PASS__"

# The convention every test.deal follows: a mismatch against the reference is
# `throw { code: "DIFF", message: "<which check>" }`. Any other uncaught error
# is the module or the runtime failing, which is the `runs` rung.
TEST_FAIL_CODE = "DIFF"
UNCAUGHT = re.compile(r"^__DEAL_UNCAUGHT__\t([^\t]*)\t([^\t]*)\t(.*)$", re.M)

# Runs the compiled entry under pcall and reports an uncaught DEAL error with
# its code and message on one tab-separated line. A non-table error (a Lua
# runtime fault) is reported as a string with an empty code.
RUNNER = r"""
local entry = arg[1]
local ok, err = pcall(dofile, entry)
if ok then os.exit(0) end
local code, message, where = "", "", ""
if type(err) == "table" then
  code = tostring(err.code or "")
  message = tostring(err.message or "")
  if err.line then where = "line " .. tostring(err.line) end
else
  message = tostring(err)
end
io.stderr:write("__DEAL_UNCAUGHT__\t" .. code .. "\t" .. message .. "\t" .. where .. "\n")
os.exit(1)
"""

# Phase one uses an entry that only imports the module. Keeping it free of the
# hidden test is what lets "compiles" keep meaning exactly what it meant before
# tests existed: a failure to match the requested interface then shows up as its
# own rung instead of silently degrading the compile rate.
ENTRY_MODULE = """import * as solution from "./solution";

export function main(): null {
  return null;
}
"""

# `moduleRoots` must be a named relative directory. The published benchmark used
# ["."], which the current compiler rejects for any exported class with E2010
# "the configured root '.' is not representable".
PROJECT = {
    "languageVersion": "1.2",
    "moduleRoots": ["src"],
    "output": "lua",
    "backend": "luajit",
}


@dataclass
class Evaluation:
    """Where a generated module got to, one field per rung of the ladder."""
    syntax_success: bool = False
    compile_success: bool = False
    # None means "not applicable": the task ships no hidden test, so the run and
    # functional rungs are undefined rather than failed.
    interface_success: bool | None = None
    runtime_success: bool | None = None
    functional_pass: bool | None = None
    diagnostics: list[str] = field(default_factory=list)
    interface_diagnostics: list[str] = field(default_factory=list)
    # Structured errors, kept for the repair prompt: a bare code tells the model
    # nothing, and the raw compiler output carries a temp path that would be
    # noise in the prompt and machine-specific noise in the record.
    errors: list[dict] = field(default_factory=list)
    interface_errors: list[dict] = field(default_factory=list)
    compiler_message: str = ""
    runtime_message: str = ""
    compile_ms: float = 0.0
    interface_ms: float = 0.0
    runtime_ms: float = 0.0
    fence_normalized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def structured(diagnostic: dict) -> dict:
    """One error, reduced to what is useful and free of machine-local paths."""
    span = diagnostic.get("range") or {}
    return {
        "code": diagnostic.get("code"),
        "message": diagnostic.get("message", ""),
        "line": span.get("startLine"),
        "column": span.get("startColumn"),
    }


def strip_fence(output: str) -> tuple[str, bool]:
    """Remove a single outer Markdown fence.

    A fence is a transport-format violation, not a defect in the DEAL program,
    so it is stripped before compiling and recorded separately.
    """
    match = FENCE.fullmatch(output)
    return (match.group(1), True) if match else (output, False)


def evaluate(
    output: str,
    *,
    config: cfg.Config,
    task: cfg.Task | None = None,
    execute: bool = False,
    timeout: float = 30.0,
) -> Evaluation:
    """Compile the module, and optionally run it.

    Paths come from the resolved configuration, never from a module-level
    default: a wrong compiler must fail loudly, not produce plausible numbers.
    """
    source, fenced = strip_fence(output)
    result = Evaluation(fence_normalized=fenced)
    support = task.support if task else []

    with tempfile.TemporaryDirectory(prefix="deal-stand-") as raw:
        work = pathlib.Path(raw)
        src = work / "src"
        src.mkdir()
        (src / "solution.deal").write_text(source, encoding="utf-8")
        (src / "main.deal").write_text(ENTRY_MODULE, encoding="utf-8")
        project = dict(PROJECT, backend=config.backend)
        (work / "deal.json").write_text(json.dumps(project), encoding="utf-8")
        for module in support:
            shutil.copy(module, src / module.name)

        diagnostics_path = work / "diagnostics.json"
        started = time.perf_counter()
        try:
            compiled = subprocess.run(
                [str(config.tools.java), "-cp", "build", "deal.Main", "compile",
                 str(src / "main.deal"), "--output", str(work / "lua"),
                 "--diagnostics-json", str(diagnostics_path)],
                cwd=config.compiler, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            result.compile_ms = (time.perf_counter() - started) * 1000
            result.compiler_message = f"compile timeout: {exc}"
            return result
        result.compile_ms = (time.perf_counter() - started) * 1000
        result.compiler_message = (compiled.stdout + compiled.stderr).strip()[:8000]

        if diagnostics_path.exists():
            payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            errors = [d for d in payload.get("diagnostics", [])
                      if d.get("severity") == "error"]
            result.diagnostics = sorted({d["code"] for d in errors})
            result.errors = [structured(d) for d in errors]
        # Syntax is the lexer/parser layer: E1xxx. Everything above it is name
        # resolution, typing and lowering.
        result.syntax_success = not any(c.startswith("E1") for c in result.diagnostics)
        result.compile_success = compiled.returncode == 0
        if not result.compile_success:
            return result

    if task is None or not task.test.exists():
        # No hidden test: the remaining rungs are undefined, not failed.
        return result
    return run_hidden_test(result, source, config=config, task=task, timeout=timeout)


def run_hidden_test(result: Evaluation, source: str, *, config: cfg.Config,
                    task: cfg.Task, timeout: float) -> Evaluation:
    """Phase two: compile and run the task's hidden test against the module.

    The test imports the candidate and the reference side by side and compares
    their behaviour, so a mismatch means the module misbehaves, not that someone
    wrote down the wrong expected value.
    """
    with tempfile.TemporaryDirectory(prefix="deal-stand-test-") as raw:
        work = pathlib.Path(raw)
        src = work / "src"
        src.mkdir()
        (src / "solution.deal").write_text(source, encoding="utf-8")
        shutil.copy(task.reference, src / "reference.deal")
        shutil.copy(task.test, src / "main.deal")
        for module in task.support:
            shutil.copy(module, src / module.name)
        project = dict(PROJECT, backend=config.backend)
        (work / "deal.json").write_text(json.dumps(project), encoding="utf-8")

        diagnostics_path = work / "diagnostics.json"
        started = time.perf_counter()
        try:
            compiled = subprocess.run(
                [str(config.tools.java), "-cp", "build", "deal.Main", "compile",
                 str(src / "main.deal"), "--output", str(work / "lua"),
                 "--diagnostics-json", str(diagnostics_path)],
                cwd=config.compiler, capture_output=True, text=True,
                timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            result.interface_ms = (time.perf_counter() - started) * 1000
            result.interface_success = False
            result.runtime_message = f"interface compile timeout: {exc}"
            return result
        result.interface_ms = (time.perf_counter() - started) * 1000

        if diagnostics_path.exists():
            payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            errors = [d for d in payload.get("diagnostics", [])
                      if d.get("severity") == "error"]
            result.interface_diagnostics = sorted({d["code"] for d in errors})
            result.interface_errors = [structured(d) for d in errors]
        # The module itself already compiled, so anything failing here is the
        # test module failing to bind: the requested interface is not there.
        result.interface_success = compiled.returncode == 0
        if not result.interface_success:
            result.runtime_message = (compiled.stdout + compiled.stderr).strip()[:4000]
            return result

        entry = work / "lua" / "main.lua"
        if not entry.exists():
            result.runtime_success = False
            result.functional_pass = False
            result.runtime_message = "missing generated main.lua"
            return result

        # A DEAL error is a Lua table, which a bare `luajit main.lua` reports as
        # "(error object is not a string)", losing the code and message. The
        # wrapper catches it and prints both, so a failed assertion can be told
        # apart from a crash and the report can say which check failed.
        wrapper = work / "lua" / "__stand_main.lua"
        wrapper.write_text(RUNNER, encoding="utf-8")
        started = time.perf_counter()
        try:
            executed = subprocess.run(
                [str(config.tools.luajit / "luajit"), str(wrapper), str(entry)],
                cwd=work / "lua", capture_output=True, text=True,
                timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            result.runtime_ms = (time.perf_counter() - started) * 1000
            result.runtime_success = False
            result.functional_pass = False
            result.runtime_message = f"runtime timeout: {exc}"
            return result
        result.runtime_ms = (time.perf_counter() - started) * 1000
        output = (executed.stdout + executed.stderr).strip()
        uncaught = UNCAUGHT.search(output)
        if uncaught and uncaught.group(1) == TEST_FAIL_CODE:
            # The test ran to its verdict and the verdict was "different from
            # the reference": that is the `passes` rung failing, not `runs`.
            result.runtime_success = True
            result.functional_pass = False
            result.runtime_message = f"test failed: {uncaught.group(2)}"
            return result
        result.runtime_message = output[:4000]
        result.runtime_success = executed.returncode == 0
        result.functional_pass = (result.runtime_success
                                  and output.splitlines().count(PASS_MARKER) == 1)
        return result
