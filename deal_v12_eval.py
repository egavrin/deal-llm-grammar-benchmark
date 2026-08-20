#!/usr/bin/env python3
"""Compile and functionally evaluate a generated DEAL v1.2 library module."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Any


PASS_MARKER = "__DEAL_BENCH_PASS__"
DIAGNOSTIC_CODE = re.compile(r"\b(E[1-8][0-9]{3})\b")


@dataclass
class DealEvaluation:
    syntax_success: bool
    compile_success: bool
    runtime_success: bool
    functional_pass: bool
    diagnostics: list[str]
    compiler_message: str
    runtime_message: str
    compile_ms: float
    runtime_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deal_string(value: str) -> str:
    result = ['"']
    for char in value:
        if char == "\\": result.append("\\\\")
        elif char == '"': result.append('\\"')
        elif char == "\n": result.append("\\n")
        elif char == "\t": result.append("\\t")
        elif char in {"\r", "\b", "\f"}:
            raise ValueError(f"unsupported DEAL benchmark string control character: {ord(char)}")
        else: result.append(char)
    result.append('"')
    return "".join(result)


def deal_literal(value: Any) -> str:
    if value is None: return "null"
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value, int): return str(value)
    if isinstance(value, float):
        text = repr(value)
        return text if any(marker in text for marker in ".eE") else text + ".0"
    if isinstance(value, str): return deal_string(value)
    if isinstance(value, list): return "[" + ", ".join(deal_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key}: {deal_literal(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"unsupported benchmark value: {value!r}")


def fail_statement(case_index: int) -> str:
    return f'throw {{ code: "BENCH_FAIL", message: "case {case_index}" }};'


def materialize_argument(
    lines: list[str], name: str, declared_type: str, value: Any, indent: str = "  "
) -> None:
    """Build a hidden-test value without depending on incomplete literal inference."""
    if declared_type.endswith("[]") and isinstance(value, list):
        lines.append(f"{indent}let {name}: {declared_type} = [];")
        element_type = declared_type[:-2]
        for index, element in enumerate(value):
            if element_type.endswith("[]") and isinstance(element, list):
                child = f"{name}_item_{index}"
                materialize_argument(lines, child, element_type, element, indent)
                expression = child
            else:
                expression = deal_literal(element)
            lines.append(f"{indent}{name}[{name}.length] = {expression};")
        return
    lines.append(f"{indent}let {name}: {declared_type} = {deal_literal(value)};")


def build_main(task: dict[str, Any]) -> str:
    interface = task["interface"]
    return_type = interface["returnType"]
    parameters = interface["parameters"]
    lines = [
        'import * as solution from "./solution";',
        'import * as console from "std/console";',
        "",
        "export function main(): null {",
    ]
    for index, test in enumerate(task["tests"]):
        args: list[str] = []
        for param_index, (parameter, value) in enumerate(zip(parameters, test["args"])):
            name = f"arg_{index}_{param_index}"
            parameter_type = parameter["type"]
            if parameter_type == "Pair":
                parameter_type = "solution.Pair"
            # Materialize hidden-test arguments with exact interface types.  The
            # current v1.2 compiler does not yet contextually type every nullable
            # or nested literal, so arrays are assembled through typed writes.
            materialize_argument(lines, name, parameter_type, value)
            args.append(name)
        actual = f"actual_{index}"
        lines.append(
            f"  let {actual}: {return_type} = solution.solve({', '.join(args)});"
        )
        expected = test["expected"]
        if "| null" in return_type and expected is not None:
            lines.append(f"  if ({actual} === null) {{ {fail_statement(index)} }} else {{")
            lines.append(f"    if ({actual} !== {deal_literal(expected)}) {{ {fail_statement(index)} }}")
            lines.append("  }")
        else:
            lines.append(
                f"  if ({actual} !== {deal_literal(expected)}) {{ {fail_statement(index)} }}"
            )
    lines.extend([
        f'  console.log("{PASS_MARKER}");',
        "  return null;",
        "}",
        "",
    ])
    return "\n".join(lines)


def compiler_diagnostics(message: str) -> list[str]:
    return sorted(set(DIAGNOSTIC_CODE.findall(message)))


def evaluate_deal_source(
    source: str,
    *,
    task: dict[str, Any],
    deal_repo: pathlib.Path,
    timeout: float = 20.0,
) -> DealEvaluation:
    with tempfile.TemporaryDirectory(prefix="deal-v12-eval-") as raw_temp:
        temp = pathlib.Path(raw_temp)
        source_path = temp / "solution.deal"
        main_path = temp / "main.deal"
        output = temp / "lua"
        source_path.write_text(source, encoding="utf-8")
        main_path.write_text(build_main(task), encoding="utf-8")
        (temp / "deal.json").write_text(json.dumps({
            "languageVersion": "1.2",
            "moduleRoots": ["."],
            "output": "lua",
            "backend": "luajit",
        }), encoding="utf-8")

        started = time.perf_counter()
        try:
            compiled = subprocess.run(
                [
                    "java", "-cp", str(deal_repo / "build"), "deal.Main",
                    "compile", str(main_path), "--output", str(output),
                ],
                cwd=deal_repo,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            compile_ms = (time.perf_counter() - started) * 1000
        except subprocess.TimeoutExpired as exc:
            return DealEvaluation(False, False, False, False, [], f"compile timeout: {exc}", "", (time.perf_counter() - started) * 1000, 0.0)

        compiler_message = (compiled.stdout + compiled.stderr).strip()
        diagnostics = compiler_diagnostics(compiler_message)
        syntax_success = not any(code.startswith("E1") for code in diagnostics)
        if compiled.returncode != 0:
            return DealEvaluation(syntax_success, False, False, False, diagnostics, compiler_message[:8000], "", compile_ms, 0.0)

        lua_entry = output / "main.lua"
        if not lua_entry.exists():
            return DealEvaluation(True, False, False, False, diagnostics, compiler_message[:8000], "missing generated main.lua", compile_ms, 0.0)

        started = time.perf_counter()
        try:
            executed = subprocess.run(
                ["luajit", str(lua_entry)], cwd=output,
                capture_output=True, text=True, timeout=timeout, check=False,
            )
            runtime_ms = (time.perf_counter() - started) * 1000
        except subprocess.TimeoutExpired as exc:
            return DealEvaluation(True, True, False, False, diagnostics, compiler_message[:8000], f"runtime timeout: {exc}", compile_ms, (time.perf_counter() - started) * 1000)

        runtime_message = (executed.stdout + executed.stderr).strip()
        passed = executed.returncode == 0 and runtime_message.splitlines().count(PASS_MARKER) == 1
        return DealEvaluation(
            True, True, executed.returncode == 0, passed, diagnostics,
            compiler_message[:8000], runtime_message[:8000], compile_ms, runtime_ms,
        )


def deal_reference(task: dict[str, Any]) -> str:
    source = task["reference"]
    source = source.replace(".length()", ".length")
    source = source.replace("value!", "value")
    source = source.replace(
        "class Pair { left: int; right: int; }",
        "export class Pair { left: int = 0; right: int = 0; }",
    )
    source = re.sub(r"\bfunction\s+solve\b", "export function solve", source, count=1)
    return source
