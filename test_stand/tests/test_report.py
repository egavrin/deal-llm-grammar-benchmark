import json

import compare
import report


def ev(**fields):
    base = {"syntax_success": False, "compile_success": False,
            "interface_success": None, "runtime_success": None, "functional_pass": None}
    return {**base, **fields}


def test_rung_index_counts_consecutive_rungs_only():
    assert report.rung_index(ev()) == 0
    assert report.rung_index(ev(syntax_success=True)) == 1
    assert report.rung_index(ev(syntax_success=True, compile_success=True)) == 2
    assert report.rung_index(ev(syntax_success=True, compile_success=True,
                                interface_success=True, runtime_success=True,
                                functional_pass=True)) == 5
    # A gap stops the count: a pass without a run is not a thing.
    assert report.rung_index(ev(syntax_success=True, functional_pass=True)) == 1


def test_paired_summary_is_baseline_first_and_names_moved_tasks():
    rows = [
        {"task_id": "a", "profile": "raw", "evaluation": ev()},
        {"task_id": "a", "profile": "constrained", "evaluation": ev(syntax_success=True)},
        {"task_id": "b", "profile": "raw", "evaluation": ev(syntax_success=True)},
        {"task_id": "b", "profile": "constrained", "evaluation": ev()},
        {"task_id": "c", "profile": "raw", "evaluation": ev(syntax_success=True)},
        {"task_id": "c", "profile": "constrained", "evaluation": ev(syntax_success=True)},
    ]
    paired = report.paired_summary(rows)
    assert paired["left"] == "raw" and paired["right"] == "constrained"
    assert paired["n"] == 3
    syntax = paired["rungs"]["syntax"]
    assert syntax == {"a": 2, "b": 2, "rescued": ["a"], "harmed": ["b"]}


def test_paired_summary_needs_both_profiles():
    rows = [{"task_id": "a", "profile": "raw", "evaluation": ev()}]
    assert report.paired_summary(rows) is None


def test_percentile_is_nearest_rank():
    assert report.percentile([], 0.5) == 0.0
    assert report.percentile([1, 2, 3, 4], 0.5) == 2
    assert report.percentile([1, 2, 3, 4], 0.95) == 4


def test_render_matches_the_stored_sample(sample_b):
    summary = json.loads((sample_b / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == report.SCHEMA
    rows = report.load(sample_b / "raw.jsonl")
    text = report.render(summary, rows, str(sample_b))
    assert text == (sample_b / "report.txt").read_text(encoding="utf-8")
    assert "LATENCY" in text and "QUALITY" in text and "COST PER SOLVED TASK" in text
    assert "BASELINE" in text


def attempt(task, profile, stage, **fields):
    return {"task_id": task, "profile": profile, "stage": stage,
            "model": "m", "fingerprint": {}, "evaluation": ev(**fields)}


def test_solve_curve_is_cumulative_and_stays_solved():
    rows = [
        attempt("a", "raw", "initial"),
        attempt("a", "raw", "repair-1", compile_success=True),
        # A later round that breaks it again must not un-solve k=1: the loop
        # would have stopped at the round that worked.
        attempt("a", "raw", "repair-2"),
        attempt("b", "raw", "initial", compile_success=True),
    ]
    assert report.solve_curve(rows, "raw", "compile_success", 2) == [1, 2, 2]
    assert report.solve_curve(rows, "raw", "functional_pass", 2) == [0, 0, 0]


def test_latency_block_says_not_measured_without_streaming(sample_b):
    summary = json.loads((sample_b / "summary.json").read_text(encoding="utf-8"))
    rows = report.load(sample_b / "raw.jsonl")
    assert all(row.get("ttft_ms") is None for row in rows)
    text = report.render(summary, rows, str(sample_b))
    assert "not measured" in text
    assert "ttft cold" not in text


def test_cache_splits_attempts_into_cold_and_warm():
    cold = {"input_toks_cached": 0}
    warm = {"input_toks_cached": 1502}
    assert report.is_warm(cold) is False
    assert report.is_warm(warm) is True
    assert report.is_warm({}) is None


def test_compare_reports_changed_inputs_and_moved_tasks(sample_a, sample_b):
    a = json.loads((sample_a / "summary.json").read_text(encoding="utf-8"))
    b = json.loads((sample_b / "summary.json").read_text(encoding="utf-8"))
    diff = compare.compare(a, b, "a", "b")
    changed = {item["key"] for item in diff["inputs_changed"]}
    assert {"primer_sha256", "example_sha256", "prompts_sha256"} <= changed
    assert "grammar_sha256" not in changed
    constrained = diff["profiles"]["constrained"]
    assert constrained["levels"]["passes"] == {"a": 0, "b": 1}
    moved = {m["task"]: (m["a_label"], m["b_label"]) for m in constrained["moved"]}
    assert moved["profile_json"] == ("parse failed", "passes")
    assert constrained["atoms"]["a"] == 29 and constrained["atoms"]["b"] == 57
    text = compare.render(diff)
    assert "profile_json" in text and "gained:" in text
