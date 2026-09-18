"""Test fixtures for the stand's own unit tests.

Everything here runs without the toolchain: no compiler, no JDK, no model.
Tests that need one are marked with `needs_toolchain` and skip themselves
when test_stand/.env is absent.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

STAND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STAND))

SAMPLES = STAND / "samples"
PROMPTS = STAND / "prompts/v12"


@pytest.fixture
def stand() -> pathlib.Path:
    return STAND


@pytest.fixture
def prompts() -> pathlib.Path:
    return PROMPTS


@pytest.fixture
def sample_a() -> pathlib.Path:
    return SAMPLES / "2026-09-03-coder-1.5b"


@pytest.fixture
def sample_b() -> pathlib.Path:
    return SAMPLES / "2026-09-03-coder-1.5b-prompts2"


needs_toolchain = pytest.mark.skipif(
    not (STAND / ".env").exists(),
    reason="needs the toolchain from test_stand/bin/setup_linux.sh")
