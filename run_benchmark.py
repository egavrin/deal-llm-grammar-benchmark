#!/usr/bin/env python3
"""Run DEAL v1.2 raw/constrained generation and real compiler evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import socket
import subprocess
import tempfile
import time
import urllib.request
from typing import Any

from deal_v12_eval import evaluate_deal_source


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE
PROMPT_PATH = HERE / "prompts/deal-v1.2.txt"
DEFAULT_GRAMMAR = HERE / "grammar/deal-v1.2.gbnf"
DEAL_COMMIT = "58a6dd3aeafc06168f2010c07d0aeae84d5364f3"
FENCE = re.compile(r"\A\s*```[^\n]*\n([\s\S]*?)\n```\s*\Z")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def post_json(url: str, body: dict[str, Any], timeout: float = 240.0) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def pick_port(preferred: int) -> int:
    with socket.socket() as sock:
        try: sock.bind(("127.0.0.1", preferred)); return preferred
        except OSError: sock.bind(("127.0.0.1", 0)); return int(sock.getsockname()[1])


def wait_for_server(base_url: str, process: subprocess.Popen, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None: raise RuntimeError(f"llama-server exited with {process.returncode}")
        try:
            if get_json(base_url + "/health").get("status") in {"ok", "no slot available"}: return
        except Exception: pass
        time.sleep(0.2)
    raise TimeoutError("llama-server did not become healthy")


def grammar_valid(validator: pathlib.Path, grammar: pathlib.Path, source: str) -> bool:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(source); path = pathlib.Path(handle.name)
    try:
        run = subprocess.run([str(validator), str(grammar), str(path)], capture_output=True, text=True, timeout=20, check=False)
        return "Input string is valid according to the grammar." in run.stdout + run.stderr
    finally: path.unlink(missing_ok=True)


def pressure_metrics(response: dict[str, Any]) -> dict[str, Any]:
    content = response.get("choices", [{}])[0].get("logprobs", {}).get("content") or []
    steps = rejected = 0; selected: list[float] = []
    for token in content:
        top = token.get("top_logprobs") or []
        if token.get("id") is None or not top: continue
        steps += 1
        if top[0].get("id") != token.get("id"): rejected += 1
        value = token.get("logprob")
        if isinstance(value, (int, float)) and math.isfinite(value): selected.append(math.exp(value))
    return {
        "pressure_steps": steps,
        "rejected_argmax_steps": rejected,
        "argmax_rejection_rate": rejected / steps if steps else None,
        "mean_raw_probability_of_selected": sum(selected) / len(selected) if selected else None,
    }


def generation_prompt(task: dict[str, Any]) -> str:
    request = f"Export {task['signature']}. {task['description']}"
    return PROMPT_PATH.read_text(encoding="utf-8").replace("{task}", request)


def append_row(path: pathlib.Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row.get("model", ""), row.get("profile", ""), row.get("task_id", "")


def generate(
    *, base_url: str, model: dict[str, Any], task: dict[str, Any], profile: str,
    prompt: str, seed: int, max_tokens: int, validator: pathlib.Path,
    deal_repo: pathlib.Path, grammar: pathlib.Path,
) -> dict[str, Any]:
    grammar_text = grammar.read_text(encoding="utf-8") if profile == "deal-constrained" else None
    body: dict[str, Any] = {
        "model": model["id"],
        "messages": [
            {"role": "system", "content": "You are a precise DEAL v1.2 code generator. Follow the source-only output protocol exactly."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0, "seed": seed, "max_tokens": max_tokens,
        "stream": False, "cache_prompt": False, "repeat_penalty": 1.0,
        "frequency_penalty": 0.0, "presence_penalty": 0.0,
        "top_k": 0, "top_p": 1.0, "min_p": 0.0,
        "logprobs": True, "top_logprobs": 1, "post_sampling_probs": False,
    }
    if grammar_text is not None: body["grammar"] = grammar_text
    started = time.perf_counter(); response = post_json(base_url + "/v1/chat/completions", body); wall_ms = (time.perf_counter() - started) * 1000
    choice = response["choices"][0]; output = choice["message"].get("content") or ""
    match = FENCE.fullmatch(output); normalized = match.group(1) if match else output
    # A single outer Markdown fence is a transport-format violation, not a DEAL
    # program defect.  Strip it deterministically for compiler/runtime Success@1,
    # while preserving the exact output and strict grammar/fence measurements.
    # Reference programs finish in milliseconds.  A two-second compiler/runtime
    # budget is generous for these tasks and keeps generated infinite loops from
    # dominating the benchmark wall clock.
    evaluation = evaluate_deal_source(
        normalized, task=task, deal_repo=deal_repo, timeout=2.0
    )
    timings, usage = response.get("timings", {}), response.get("usage", {})
    generated_tokens = usage.get("completion_tokens", timings.get("predicted_n")); finish = choice.get("finish_reason")
    row = {
        "timestamp_unix": time.time(), "suite_version": "deal-v1.2-corrected-v1",
        "deal_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=deal_repo, capture_output=True, text=True, check=True).stdout.strip(),
        "model": model["id"], "model_parameters_b": model["parameters_b"], "model_file": model["file"], "quantization": model["quantization"],
        "task_id": task["id"], "family": task["family"], "category": task["category"],
        "profile": profile, "stage": "initial", "seed": seed, "max_tokens": max_tokens,
        "grammar_file": "grammar/deal-v1.2.gbnf" if grammar_text else None,
        "grammar_sha256": hashlib.sha256(grammar_text.encode()).hexdigest() if grammar_text else None,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_tokens": usage.get("prompt_tokens"), "generated_tokens": generated_tokens,
        "prompt_eval_ms": timings.get("prompt_ms"), "generation_ms": timings.get("predicted_ms"),
        "total_server_ms": timings.get("prompt_ms", 0) + timings.get("predicted_ms", 0), "wall_ms": wall_ms,
        "generated_tokens_per_second": timings.get("predicted_per_second"), "finish_reason": finish,
        "hit_token_limit": finish == "length" or (generated_tokens is not None and generated_tokens >= max_tokens),
        "strict_gbnf_validity": grammar_valid(validator, grammar, output),
        "normalized_gbnf_validity": grammar_valid(validator, grammar, normalized),
        "fence_normalized": bool(match), "output": output, "normalized_output": normalized,
        "evaluation": evaluation.to_dict(), "request_error": None,
    }
    row.update(pressure_metrics(response)); return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", choices=("deal-raw", "deal-constrained"), default=["deal-raw", "deal-constrained"])
    parser.add_argument("--task-limit", type=int)
    parser.add_argument("--task-ids", nargs="*")
    parser.add_argument("--models", nargs="*")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--port", type=int, default=8102)
    parser.add_argument("--output", type=pathlib.Path, default=HERE / "results/raw-results.jsonl")
    parser.add_argument("--tasks", type=pathlib.Path, default=HERE / "bench/tasks.jsonl")
    parser.add_argument("--grammar", type=pathlib.Path, default=DEFAULT_GRAMMAR)
    parser.add_argument("--model-config", type=pathlib.Path, default=ROOT / "config/models.json")
    parser.add_argument("--server-bin", type=pathlib.Path, default=ROOT / ".deps/llama.cpp/build/bin/llama-server")
    parser.add_argument("--validator", type=pathlib.Path, default=ROOT / ".deps/llama.cpp/build/bin/test-gbnf-validator")
    parser.add_argument("--deal-repo", type=pathlib.Path, default=ROOT / ".deps/deal")
    args = parser.parse_args()
    if not args.grammar.exists(): raise SystemExit(f"missing grammar: {args.grammar}")
    actual_deal_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=args.deal_repo,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if actual_deal_commit != DEAL_COMMIT:
        raise SystemExit(f"DEAL compiler commit mismatch: expected {DEAL_COMMIT}, got {actual_deal_commit}")
    tasks = read_jsonl(args.tasks)
    if args.task_ids:
        wanted = set(args.task_ids); tasks = [task for task in tasks if task["id"] in wanted]
    if args.task_limit: tasks = tasks[:args.task_limit]
    models = json.loads(args.model_config.read_text(encoding="utf-8"))
    models = [item for item in models if round(float(item["parameters_b"]), 2) == 0.63]
    if args.models:
        wanted = set(args.models); models = [model for model in models if model["id"] in wanted]
    existing_rows = read_jsonl(args.output) if args.output.exists() else []
    existing = {row_key(row): row for row in existing_rows if not row.get("request_error")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = len(models) * len(tasks) * len(args.profiles); completed = 0
    for model in models:
        port = pick_port(args.port); base_url = f"http://127.0.0.1:{port}"
        log_path = HERE / f"results/server-{model['id']}.log"
        with log_path.open("a", encoding="utf-8") as log:
            command = [str(args.server_bin), "-m", str(ROOT / model["file"]), "-c", "4096", "-ngl", "99", "-np", "1", "--host", "127.0.0.1", "--port", str(port), "--no-cache-prompt", "--metrics", "-lv", "2"]
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
            try:
                wait_for_server(base_url, process); print(f"model={model['id']} tasks={len(tasks)} profiles={args.profiles}", flush=True)
                for task_index, task in enumerate(tasks):
                    profiles = list(args.profiles)
                    if task_index % 2: profiles.reverse()
                    for profile in profiles:
                        key = (model["id"], profile, task["id"])
                        row = existing.get(key)
                        if row is None:
                            try:
                                row = generate(base_url=base_url, model=model, task=task, profile=profile, prompt=generation_prompt(task), seed=args.seed, max_tokens=args.max_tokens, validator=args.validator, deal_repo=args.deal_repo, grammar=args.grammar)
                            except Exception as exc:
                                row = {"model": model["id"], "model_parameters_b": model["parameters_b"], "task_id": task["id"], "family": task["family"], "category": task["category"], "profile": profile, "stage": "initial", "request_error": repr(exc)}
                            append_row(args.output, row); existing[key] = row
                        completed += 1
                        if completed % 20 == 0 or completed == total:
                            members = [item for item in existing.values() if item.get("model") == model["id"]]
                            passes = sum(bool(item.get("evaluation", {}).get("functional_pass")) for item in members)
                            print(f"progress={completed}/{total} recorded={len(members)} passes={passes}", flush=True)
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
