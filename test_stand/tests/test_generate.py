import json

import pytest

import generate


def row(**evaluation):
    base = {"syntax_success": False, "compile_success": False,
            "interface_success": None, "runtime_success": None, "functional_pass": None}
    return {"evaluation": {**base, **evaluation}, "request_error": None}


def test_describe_outcome_names_the_highest_rung():
    assert generate.describe_outcome(row()) == "parse failed"
    assert generate.describe_outcome(row(syntax_success=True)) == "syntax ok"
    assert generate.describe_outcome(row(syntax_success=True, compile_success=True)) == "compiles (no test)"
    assert generate.describe_outcome(row(syntax_success=True, compile_success=True,
                                         interface_success=False)) == "compiles, wrong interface"
    assert generate.describe_outcome(row(syntax_success=True, compile_success=True,
                                         interface_success=True, runtime_success=False)) == "binds, does not run"
    assert generate.describe_outcome(row(syntax_success=True, compile_success=True,
                                         interface_success=True, runtime_success=True,
                                         functional_pass=False)) == "runs, wrong answer"
    assert generate.describe_outcome(row(syntax_success=True, compile_success=True,
                                         interface_success=True, runtime_success=True,
                                         functional_pass=True)) == "PASSES TESTS"
    assert generate.describe_outcome({"request_error": "boom"}) == "ERROR"


def test_succeeded_means_nothing_left_to_repair():
    assert generate.succeeded(row(syntax_success=True, compile_success=True,
                                  interface_success=True, runtime_success=True,
                                  functional_pass=True))
    # Compiled and no test to fail: also done.
    assert generate.succeeded(row(syntax_success=True, compile_success=True))
    assert not generate.succeeded(row(syntax_success=True, compile_success=True,
                                      interface_success=False))
    assert not generate.succeeded(row())


def test_format_diagnostics_restates_missing_exports_for_the_model():
    r = row(syntax_success=True, compile_success=True, interface_success=False)
    r["evaluation"]["errors"] = []
    r["evaluation"]["interface_errors"] = [
        {"code": "E2004", "message": "Export 'makeCounter' not found in module 'candidate'. Available:"},
        {"code": "E2004", "message": "Export 'makeAdder' not found in module 'candidate'. Available:"},
    ]
    text = generate.format_diagnostics(r)
    assert "Missing exports: makeCounter, makeAdder" in text
    assert "candidate" not in text.split("Missing exports")[0]


def test_format_diagnostics_lists_compiler_errors_with_positions():
    r = row()
    r["evaluation"]["errors"] = [{"code": "E1037", "message": "Expected expression",
                                  "line": 16, "column": 3}]
    assert generate.format_diagnostics(r) == "  E1037: Expected expression  (line 16, column 3)"


FINGERPRINT = {"grammar_sha256": "g", "primer_sha256": "p", "seed": 42}


def test_prepare_output_records_the_fingerprint_and_starts_empty(tmp_path):
    done = generate.prepare_output(tmp_path / "run", FINGERPRINT, fresh=False)
    assert done == set()
    inputs = json.loads((tmp_path / "run/inputs.json").read_text())
    assert inputs["fingerprint"] == FINGERPRINT


def test_prepare_output_resumes_finished_rows_with_the_same_inputs(tmp_path):
    out = tmp_path / "run"
    generate.prepare_output(out, FINGERPRINT, fresh=False)
    (out / "raw.jsonl").write_text(
        json.dumps({"profile": "raw", "task_id": "a", "request_error": None}) + "\n"
        + json.dumps({"profile": "constrained", "task_id": "a", "request_error": "timeout"}) + "\n")
    done = generate.prepare_output(out, FINGERPRINT, fresh=False)
    # The errored row is not reused; it will be generated again.
    assert done == {("raw", "a", "initial")}


def test_prepare_output_refuses_to_mix_inputs(tmp_path, capsys):
    out = tmp_path / "run"
    generate.prepare_output(out, FINGERPRINT, fresh=False)
    with pytest.raises(SystemExit) as stop:
        generate.prepare_output(out, dict(FINGERPRINT, grammar_sha256="other"), fresh=False)
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "grammar_sha256" in err and "--fresh" in err


def test_prepare_output_fresh_discards_everything(tmp_path):
    out = tmp_path / "run"
    generate.prepare_output(out, FINGERPRINT, fresh=False)
    (out / "raw.jsonl").write_text(
        json.dumps({"profile": "raw", "task_id": "a", "request_error": None}) + "\n")
    done = generate.prepare_output(out, dict(FINGERPRINT, grammar_sha256="other"), fresh=True)
    assert done == set()
    assert not (out / "raw.jsonl").exists()
