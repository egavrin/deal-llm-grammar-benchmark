"""The prompt set's structure and the no-leakage rule, without a compiler."""

import benchmark
import config as cfg


def tasks_of(prompts):
    return [cfg.Task(d.name, d) for d in sorted(prompts.iterdir())
            if d.is_dir() and (d / "brief.md").exists()]


def test_every_task_has_a_brief_and_a_reference(prompts):
    tasks = tasks_of(prompts)
    assert len(tasks) >= 14
    for task in tasks:
        assert task.brief.exists(), task.id
        assert task.reference.exists(), task.id
        assert task.test.exists() or (task.directory / "NO_TEST.md").exists(), task.id


def test_briefs_state_exports_as_signature_lines(prompts):
    for task in tasks_of(prompts):
        text = task.brief.read_text(encoding="utf-8")
        assert "export " in text, f"{task.id}: no export signature line"


def test_every_reference_exports_what_its_brief_asks_for(prompts):
    for task in tasks_of(prompts):
        asked = set(cfg.EXPORTED.findall(task.brief.read_text(encoding="utf-8")))
        provided = set(cfg.EXPORTED.findall(task.reference.read_text(encoding="utf-8")))
        assert asked <= provided, f"{task.id}: brief asks for {asked - provided}"


def test_primer_has_both_placeholders_and_the_files_they_need(prompts):
    primer = (prompts / "primer.txt").read_text(encoding="utf-8")
    assert "{task}" in primer
    assert "{example}" in primer
    assert (prompts / "example.deal").exists()
    assert (prompts / "system.txt").exists()
    assert (prompts / "repair.txt").exists()


def test_primer_and_example_share_no_name_with_any_task(prompts):
    protected = benchmark.protected_names(tasks_of(prompts))
    assert len(protected) > 50
    for name in ("primer.txt", "example.deal", "system.txt"):
        text = (prompts / name).read_text(encoding="utf-8")
        assert benchmark.leaked_names(text, protected) == [], name


def test_leak_check_catches_a_task_name_and_an_export():
    protected = {"kv_cache": "task id kv_cache", "hitRatioPercent": "export of kv_cache"}
    text = "Hint: hitRatioPercent divides hits by the total, see kv_cache."
    assert benchmark.leaked_names(text, protected) == ["hitRatioPercent", "kv_cache"]
    # Substrings are not identifiers: `cache` alone is fine.
    assert benchmark.leaked_names("a cache of ratios", protected) == []


def test_tests_follow_the_diff_convention(prompts):
    for task in tasks_of(prompts):
        if not task.test.exists():
            continue
        text = task.test.read_text(encoding="utf-8")
        assert 'code: "DIFF"' in text, task.id
        assert "__DEAL_BENCH_PASS__" in text, task.id
        assert 'from "./solution"' in text and 'from "./reference"' in text, task.id
