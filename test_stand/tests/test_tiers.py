import pathlib

import pytest

import config as cfg
import report


def make_set(root: pathlib.Path, modules: list[str], quick: list[str]) -> pathlib.Path:
    prompts = root / "prompts"
    for name in modules:
        (prompts / name).mkdir(parents=True)
        (prompts / name / "brief.md").write_text("export function f(): int\n")
    for name in quick:
        (prompts / cfg.QUICK_DIR / name).mkdir(parents=True)
        (prompts / cfg.QUICK_DIR / name / "brief.md").write_text("export function g(): int\n")
    return prompts


def config_for(prompts: pathlib.Path) -> cfg.Config:
    tools = cfg.Toolchain(jdk=prompts, luajit=prompts, llama=prompts)
    return cfg.Config(prompts=prompts, grammar=prompts, compiler=prompts, primer=prompts,
                      model=prompts, backend="luajit", tools=tools, preset=None)


def test_tasks_carry_their_tier_and_filter_by_it(tmp_path):
    config = config_for(make_set(tmp_path, ["alpha", "beta"], ["one", "two", "three"]))
    everything = config.tasks()
    assert [(t.id, t.tier) for t in everything] == [
        ("alpha", "modules"), ("beta", "modules"),
        ("one", "quick"), ("three", "quick"), ("two", "quick")]
    assert [t.id for t in config.tasks("quick")] == ["one", "three", "two"]
    assert [t.id for t in config.tasks("modules")] == ["alpha", "beta"]


def test_a_prompt_set_without_a_quick_tier_still_works(tmp_path):
    config = config_for(make_set(tmp_path, ["alpha"], []))
    assert [t.tier for t in config.tasks()] == ["modules"]
    with pytest.raises(cfg.ConfigError):
        config.tasks("quick")


def test_task_ids_must_be_unique_across_tiers(tmp_path):
    config = config_for(make_set(tmp_path, ["same"], ["same"]))
    with pytest.raises(cfg.ConfigError, match="unique"):
        config.tasks()


def test_rows_without_a_tier_are_module_tasks():
    assert report.tier_of({"task_id": "x"}) == "modules"
    assert report.tier_of({"task_id": "x", "tier": "quick"}) == "quick"


def test_the_real_prompt_set_has_both_tiers(prompts):
    config = config_for(prompts)
    tiers = {t.tier for t in config.tasks()}
    assert tiers == {"modules", "quick"}
    assert len(config.tasks("quick")) >= 20
