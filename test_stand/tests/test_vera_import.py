"""The contribution inventory is portable and accounts for every source task."""

import json

import config as cfg


def inventory(stand):
    return json.loads((stand / "findings/vera-prompt-import.json").read_text())


def test_all_source_prompts_have_one_audit_decision(stand, prompts):
    audit = inventory(stand)
    rows = audit["tasks"]
    assert len(rows) == audit["source_task_count"] == 62
    assert len({row["source_id"] for row in rows}) == len(rows)
    assert len({row["category"] for row in rows}) == 25
    assert all(row["prompt"] and row["focus"] and row["reason"] for row in rows)
    for field in ("source_sha256", "references_sha256"):
        assert len(audit[field]) == 64
        int(audit[field], 16)

    imported = [r for r in rows if r["disposition"] == "imported"]
    duplicates = [r for r in rows if r["disposition"] == "duplicate"]
    assert len(imported) == audit["imported_count"] == 51
    assert len(duplicates) == audit["duplicate_count"] == 11
    assert len(imported) + len(duplicates) == len(rows)
    assert all(r["source_id"] == r["task_id"] for r in imported)
    imported_ids = {r["task_id"] for r in imported}
    assert len(imported_ids) == len(imported)
    assert not imported_ids.intersection(r["task_id"] for r in duplicates)

    for row in rows:
        task = cfg.Task(row["task_id"], prompts / "quick" / row["task_id"], "quick")
        assert task.brief.exists(), row["source_id"]
        assert task.reference.exists(), row["source_id"]
        if row["disposition"] == "imported":
            if row["source_id"] in {"async_basic", "async_sum"}:
                assert not task.test.exists()
                assert (task.directory / "NO_TEST.md").exists()
            else:
                assert task.test.exists(), row["source_id"]


def test_quick_tasks_are_included_in_prompt_set_checks(prompts):
    # Guard against accidentally restoring module-only structural/leak checks.
    from test_prompt_set import tasks_of

    tasks = tasks_of(prompts)
    quick_ids = {t.id for t in tasks if t.tier == "quick"}
    assert {"lam_counter", "json_parse", "async_sum", "even_count"} <= quick_ids
