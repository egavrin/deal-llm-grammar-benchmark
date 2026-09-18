#!/usr/bin/env python3
"""Generate one module per task, unconstrained and grammar-constrained, and score it.

Resume is keyed on a fingerprint of the inputs, not just on the task id. Change
the grammar, the primer, a brief, the compiler or a decoding parameter, and the
previous rows stop being reusable — the run says so and stops, instead of
quietly reporting old numbers under new inputs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Any

import config as cfg
import evaluate
import gate
# Imported up front so a run holds one consistent snapshot of the stand's
# code: importing it only at the end once picked up a report.py edited
# during the run and crashed after forty minutes of generation.
import report

# ------------------------------------------------------------------ server ---

def post_json(url: str, body: dict[str, Any], timeout: float = 900.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def post_stream(url: str, body: dict[str, Any],
                timeout: float = 900.0) -> tuple[dict[str, Any], float, float]:
    """One streamed completion, plus the two latencies only a client can see.

    The server reports durations after the fact, so time to first token has to
    be taken here, on the first chunk that actually carries text. The chunks are
    folded back into the shape the non-streamed endpoint returns, so everything
    downstream — the message, the logprobs, usage, timings — reads the same.
    """
    request = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    pieces: list[str] = []
    logprobs: list[dict[str, Any]] = []
    finish_reason = None
    usage: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    ttft_ms = None
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for line in response:
            line = line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            usage = chunk.get("usage") or usage
            timings = chunk.get("timings") or timings
            for choice in chunk.get("choices") or []:
                text = (choice.get("delta") or {}).get("content")
                if text:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - started) * 1000
                    pieces.append(text)
                logprobs.extend((choice.get("logprobs") or {}).get("content") or [])
                finish_reason = choice.get("finish_reason") or finish_reason
    ttlt_ms = (time.perf_counter() - started) * 1000
    folded = {
        "choices": [{"message": {"role": "assistant", "content": "".join(pieces)},
                     "logprobs": {"content": logprobs},
                     "finish_reason": finish_reason}],
        "usage": usage,
        "timings": timings,
    }
    return folded, (ttft_ms if ttft_ms is not None else ttlt_ms), ttlt_ms


def pick_port(preferred: int) -> int:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def warn_if_another_server_is_running(threads: int) -> None:
    """Two runs at once thrash: each server takes most of the cores.

    Not an error — a second run is sometimes what you want — but it must be
    said, because the symptom is a run that looks hung rather than one that
    looks slow.
    """
    found = subprocess.run(["pgrep", "-c", "-f", "llama-server -m"],
                           capture_output=True, text=True, check=False)
    try:
        running = int(found.stdout.strip() or 0)
    except ValueError:
        return
    if running:
        cores = os.cpu_count() or 4
        print(f"NOTE: {running} llama-server already running. This run adds {threads} "
              f"threads to a {cores}-core machine,\n"
              f"      so both will be several times slower. Nothing is wrong; "
              f"wait for the other run if you can.\n", file=sys.stderr)


def wait_for_server(base_url: str, process: subprocess.Popen, timeout: float = 300.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited with {process.returncode}")
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=2.0) as response:
                if json.load(response).get("status") in {"ok", "no slot available"}:
                    return
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError("llama-server did not become healthy")


def pressure_metrics(response: dict[str, Any]) -> dict[str, Any]:
    """How hard the grammar pushed against the model's own preference."""
    content = response.get("choices", [{}])[0].get("logprobs", {}).get("content") or []
    steps = rejected = 0
    selected: list[float] = []
    for token in content:
        top = token.get("top_logprobs") or []
        if token.get("id") is None or not top:
            continue
        steps += 1
        if top[0].get("id") != token.get("id"):
            rejected += 1
        value = token.get("logprob")
        if isinstance(value, (int, float)) and math.isfinite(value):
            selected.append(math.exp(value))
    return {
        "pressure_steps": steps,
        "rejected_argmax_steps": rejected,
        "argmax_rejection_rate": rejected / steps if steps else None,
        "mean_raw_probability_of_selected": sum(selected) / len(selected) if selected else None,
    }


# ------------------------------------------------------------ regeneration ---

def prepare_output(out: pathlib.Path, fingerprint: dict[str, Any],
                   fresh: bool, provenance: dict[str, Any] | None = None
                   ) -> set[tuple[str, str, str]]:
    """Decide what may be reused, and refuse to mix results from different inputs."""
    out.mkdir(parents=True, exist_ok=True)
    inputs_path = out / "inputs.json"
    raw_path = out / "raw.jsonl"

    if fresh:
        raw_path.unlink(missing_ok=True)
        inputs_path.unlink(missing_ok=True)

    if inputs_path.exists():
        previous = json.loads(inputs_path.read_text(encoding="utf-8"))["fingerprint"]
        changed = [k for k in sorted(set(previous) | set(fingerprint))
                   if previous.get(k) != fingerprint.get(k)]
        if changed:
            print(f"\n{out} holds results for different inputs.\n", file=sys.stderr)
            for key in changed:
                print(f"  {key}\n    was: {previous.get(key)}\n    now: "
                      f"{fingerprint.get(key)}", file=sys.stderr)
            print("\n  Reusing them would report old generations under new inputs.\n"
                  "  Re-run with --fresh to regenerate here, or pass a different --out.\n",
                  file=sys.stderr)
            raise SystemExit(2)

    inputs_path.write_text(json.dumps(
        {"fingerprint": fingerprint, "model_provenance": provenance,
         "written": time.strftime("%Y-%m-%dT%H:%M:%S")},
        indent=2), encoding="utf-8")

    done: set[tuple[str, str, str]] = set()
    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("request_error"):
                done.add((row["profile"], row["task_id"],
                          row.get("stage", "initial")))
    return done


# --------------------------------------------------------------------- run ---

def main(args: argparse.Namespace) -> int:
    config = cfg.resolve(args)
    if not config.model.exists():
        raise cfg.ConfigError(
            f"model not found: {config.model}\n"
            "  Run test_stand/bin/setup_linux.sh model, or pass --model PATH.")

    tier = getattr(args, "tier", "all")
    tasks = config.tasks(tier)
    if args.tasks:
        wanted = set(args.tasks)
        unknown = wanted - {t.id for t in tasks}
        if unknown:
            raise cfg.ConfigError(f"unknown task(s): {', '.join(sorted(unknown))}")
        tasks = [t for t in tasks if t.id in wanted]

    fingerprint = config.fingerprint(seed=args.seed, max_tokens=args.max_tokens)
    if args.repair_rounds:
        fingerprint = dict(fingerprint, repair_rounds=args.repair_rounds)
    if args.tasks:
        fingerprint = dict(fingerprint, task_subset=sorted(args.tasks))
    if tier != "all":
        fingerprint = dict(fingerprint, tier=tier)
    # Where the model file came from travels with the result: repo, revision,
    # quantization, and whether it matches the published benchmark's build.
    provenance_path = config.model.with_suffix(".provenance.json")
    provenance = (json.loads(provenance_path.read_text(encoding="utf-8"))
                  if provenance_path.exists() else None)
    done = prepare_output(args.out, fingerprint, args.fresh, provenance)

    print("inputs")
    print(config.describe())
    print()

    repair_template = ""
    if args.repair_rounds:
        repair_path = config.prompts / "repair.txt"
        if not repair_path.exists():
            raise cfg.ConfigError(
                f"--repair-rounds needs a repair prompt at {repair_path}\n"
                "  It takes {attempt} and {diagnostics}.")
        repair_template = repair_path.read_text(encoding="utf-8")
    grammar_text = config.grammar.read_text(encoding="utf-8")
    raw_path = args.out / "raw.jsonl"
    model_id = config.model.stem

    port = pick_port(args.port)
    base_url = f"http://127.0.0.1:{port}"
    threads = str(max(1, (os.cpu_count() or 4) - 2))
    warn_if_another_server_is_running(int(threads))
    command = [str(config.tools.server), "-m", str(config.model), "-c", "4096",
               "-np", "1", "--host", "127.0.0.1", "--port", str(port),
               "--metrics", "-t", threads]

    total = len(tasks) * len(args.profiles)
    completed = skipped = 0
    by_tier = {t: sum(1 for task in tasks if task.tier == t) for t in cfg.TIERS}
    print("tasks: " + ", ".join(f"{n} {t}" for t, n in by_tier.items() if n))
    with (args.out / "llama-server.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   text=True)
        try:
            wait_for_server(base_url, process)
            for index, task in enumerate(tasks):
                # Alternate the profile order so drift in machine state does not
                # land systematically on one profile.
                profiles = list(args.profiles)
                if index % 2:
                    profiles.reverse()
                prompt = config.render_prompt(task)

                for profile in profiles:
                    completed += 1
                    if (profile, task.id, "initial") in done:
                        skipped += 1
                        continue
                    row = generate_one(
                        base_url=base_url, model_id=model_id, prompt=prompt,
                        grammar=grammar_text if profile == "constrained" else None,
                        config=config, task=task, profile=profile,
                        seed=args.seed, max_tokens=args.max_tokens,
                        fingerprint=fingerprint)
                    with raw_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(f"[{completed}/{total}] {profile:11s} {task.id:20s} "
                          f"{describe_outcome(row)}", flush=True)

                    # Repair runs only on a failure and only if asked for. Its
                    # rows are separate stages, never merged into the first
                    # attempt: Success@1 has to stay Success@1 or nothing is
                    # comparable with earlier runs.
                    for attempt in range(1, args.repair_rounds + 1):
                        if row.get("request_error") or succeeded(row):
                            break
                        stage = f"repair-{attempt}"
                        if (profile, task.id, stage) in done:
                            break
                        repaired = repair_once(
                            base_url=base_url, model_id=model_id,
                            previous=row, attempt_prompt=prompt,
                            template=repair_template, config=config, task=task,
                            profile=profile, seed=args.seed,
                            max_tokens=args.max_tokens, stage=stage,
                            fingerprint=fingerprint)
                        with raw_path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(repaired, ensure_ascii=False) + "\n")
                        print(f"    {stage:11s} {task.id:20s} "
                              f"{describe_outcome(repaired)}", flush=True)
                        if repaired.get("repair_stalled"):
                            break
                        row = repaired
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    if skipped:
        print(f"\nreused {skipped} generation(s) from a previous run with the "
              f"same inputs; --fresh regenerates them")
    print(f"wrote {raw_path}")

    # The result directory must stand on its own: summary.json and report.txt
    # let anyone read it without the compiler, the JDK or the model.
    print()
    summary = report.summarise_run(args.out, config)
    print(report.render(summary, report.load(raw_path), str(args.out)), end="")
    print(f"wrote {args.out / 'summary.json'}, report.txt, cost.csv")
    return 0


def describe_outcome(row: dict[str, Any]) -> str:
    """The highest rung the generation reached."""
    if row.get("request_error"):
        return "ERROR"
    ev = row["evaluation"]
    if ev.get("functional_pass"):
        return "PASSES TESTS"
    if ev.get("runtime_success"):
        return "runs, wrong answer"
    if ev.get("interface_success"):
        return "binds, does not run"
    if ev.get("interface_success") is False:
        return "compiles, wrong interface"
    if ev["compile_success"]:
        return "compiles (no test)"
    return "syntax ok" if ev["syntax_success"] else "parse failed"


def generate_one(*, base_url: str, model_id: str, prompt: str,
                 grammar: str | None, config: cfg.Config, task: cfg.Task,
                 profile: str, seed: int, max_tokens: int,
                 fingerprint: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "system", "content": config.system_prompt()},
                     {"role": "user", "content": prompt}],
        "temperature": 0.0, "seed": seed, "max_tokens": max_tokens,
        "stream": True, "stream_options": {"include_usage": True},
        "cache_prompt": True, "repeat_penalty": 1.0,
        "frequency_penalty": 0.0, "presence_penalty": 0.0,
        "top_k": 0, "top_p": 1.0, "min_p": 0.0,
        "logprobs": True, "top_logprobs": 1, "post_sampling_probs": False,
    }
    if grammar is not None:
        body["grammar"] = grammar

    base = {"timestamp_unix": time.time(), "task_id": task.id, "tier": task.tier,
            "profile": profile, "model": model_id, "seed": seed, "max_tokens": max_tokens,
            "fingerprint": fingerprint, "stage": "initial"}
    try:
        started = time.perf_counter()
        response, ttft_ms, ttlt_ms = post_stream(
            base_url + "/v1/chat/completions", body)
        wall_ms = (time.perf_counter() - started) * 1000
    except Exception as exc:
        return dict(base, request_error=repr(exc))

    choice = response["choices"][0]
    output = choice["message"].get("content") or ""
    evaluation = evaluate.evaluate(output, config=config, task=task)

    # Check the output against the grammar after the fact. Under `constrained`
    # this must hold unless the generation was cut off at the token cap, so it
    # turns "the grammar held" from an inference into a measurement; under `raw`
    # it says how close unconstrained output comes to the grammar on its own.
    validator = config.tools.validator
    normalized, _ = evaluate.strip_fence(output)
    strict_valid = gate.accepts(validator, config.grammar, output)
    normalized_valid = (strict_valid if normalized == output
                        else gate.accepts(validator, config.grammar, normalized))
    timings, usage = response.get("timings", {}), response.get("usage", {})
    generated = usage.get("completion_tokens", timings.get("predicted_n"))
    finish = choice.get("finish_reason")
    # How much of the prompt the server did not have to evaluate again. Both
    # names come from the same server; take the OpenAI-shaped one first and
    # fall back to llama.cpp's own, so neither spelling silently reads as zero.
    prompt_tokens = usage.get("prompt_tokens")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached is None:
        cached = timings.get("cache_n")
    fresh = timings.get("prompt_n")
    if fresh is None and cached is not None and prompt_tokens is not None:
        fresh = prompt_tokens - cached

    row = dict(base, **{
        "prompt_tokens": prompt_tokens,
        "input_toks_cached": cached,
        "input_toks_new": fresh,
        "generated_tokens": generated,
        "prompt_eval_ms": timings.get("prompt_ms"),
        "generation_ms": timings.get("predicted_ms"),
        "total_server_ms": (timings.get("prompt_ms", 0) + timings.get("predicted_ms", 0)),
        "wall_ms": wall_ms,
        "ttft_ms": ttft_ms,
        "ttlt_ms": ttlt_ms,
        "generated_tokens_per_second": timings.get("predicted_per_second"),
        "finish_reason": finish,
        "hit_token_limit": finish == "length" or (
            generated is not None and generated >= max_tokens),
        "output": output,
        "strict_gbnf_valid": strict_valid,
        "normalized_gbnf_valid": normalized_valid,
        # The primer shows one worked example. An answer that reproduces its
        # exports did not solve the task, it copied the page; the report counts
        # these so an example that gets echoed is noticed, not mistaken for
        # coverage.
        "echoes_example": any(name in output for name in config.example_exports()),
        "evaluation": evaluation.to_dict(),
        "request_error": None,
    })
    row.update(pressure_metrics(response))
    return row


def succeeded(row: dict[str, Any]) -> bool:
    """Nothing left to repair: it passed its test, or it has no test to fail."""
    ev = row.get("evaluation") or {}
    if ev.get("functional_pass"):
        return True
    return ev.get("compile_success") and ev.get("interface_success") is None


MISSING_EXPORT = re.compile(r"Export '([^']+)' not found")


def format_diagnostics(row: dict[str, Any]) -> str:
    """The compiler's complaint, restated as something about the model's module.

    Raw compiler output is written for whoever holds the whole project. On an
    interface failure it names a temp path and an entry module the model never
    saw, so pasting it verbatim asks the model to fix someone else's file. The
    facts are kept; the frame of reference is moved to the module it wrote.
    """
    ev = row["evaluation"]
    errors = list(ev.get("errors") or [])
    if errors:
        lines = []
        for error in errors[:12]:
            where = (f"  (line {error['line']}, column {error['column']})"
                     if error.get("line") else "")
            lines.append(f"  {error['code']}: {error['message']}{where}")
        return "\n".join(lines)

    interface = list(ev.get("interface_errors") or [])
    if interface:
        missing = []
        other = []
        for error in interface:
            found = MISSING_EXPORT.search(error.get("message", ""))
            if found:
                if found.group(1) not in missing:
                    missing.append(found.group(1))
            else:
                other.append(f"  {error['code']}: {error['message']}")
        lines = []
        if missing:
            lines.append("  Your module does not export what the task asked for.")
            lines.append(f"  Missing exports: {', '.join(missing)}")
            lines.append("  Every declaration the task says to export needs the "
                         "`export` keyword.")
        lines.extend(other[:8])
        return "\n".join(lines)

    return (ev.get("compiler_message", "") or "").strip()[:1500]


def repair_once(*, base_url: str, model_id: str, previous: dict[str, Any],
                attempt_prompt: str, template: str, config: cfg.Config,
                task: cfg.Task, profile: str, seed: int, max_tokens: int,
                stage: str, fingerprint: dict[str, Any]) -> dict[str, Any]:
    """One compiler-guided repair pass over a failed generation."""
    module, _ = evaluate.strip_fence(previous.get("output", ""))
    prompt = (template
              .replace("{attempt}", attempt_prompt.rstrip() + "\n\n" + module)
              .replace("{diagnostics}", format_diagnostics(previous)))
    row = generate_one(
        base_url=base_url, model_id=model_id, prompt=prompt,
        grammar=(config.grammar.read_text(encoding="utf-8")
                 if profile == "constrained" else None),
        config=config, task=task, profile=profile, seed=seed,
        max_tokens=max_tokens, fingerprint=fingerprint)
    row["stage"] = stage
    # Greedy decoding on a similar prompt can reproduce the same text; saying so
    # is more useful than spending further rounds on it.
    row["repair_stalled"] = row.get("output") == previous.get("output")
    return row
