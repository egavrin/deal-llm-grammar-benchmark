import evaluate


def test_strip_fence_removes_one_outer_fence():
    source, fenced = evaluate.strip_fence("```typescript\nexport function f(): int { return 1; }\n```")
    assert fenced
    assert source == "export function f(): int { return 1; }"


def test_strip_fence_leaves_plain_source_alone():
    text = "export function f(): int { return 1; }\n"
    assert evaluate.strip_fence(text) == (text, False)


def test_strip_fence_only_strips_when_the_fence_wraps_everything():
    text = "prose first\n```\ncode\n```"
    assert evaluate.strip_fence(text) == (text, False)


def test_uncaught_regex_reads_code_message_and_position():
    line = "__DEAL_UNCAUGHT__\tDIFF\tcountTo(5)\tline 42"
    match = evaluate.UNCAUGHT.search("noise\n" + line + "\n")
    assert match is not None
    assert match.group(1) == evaluate.TEST_FAIL_CODE
    assert match.group(2) == "countTo(5)"
    assert match.group(3) == "line 42"


def test_uncaught_regex_handles_lua_string_errors():
    match = evaluate.UNCAUGHT.search("__DEAL_UNCAUGHT__\t\tattempt to index nil\t")
    assert match is not None
    assert match.group(1) == ""
    assert match.group(2) == "attempt to index nil"


def test_runner_script_reports_tables_and_strings():
    # The Lua wrapper must print exactly what UNCAUGHT parses.
    assert "__DEAL_UNCAUGHT__" in evaluate.RUNNER
    assert 'type(err) == "table"' in evaluate.RUNNER
