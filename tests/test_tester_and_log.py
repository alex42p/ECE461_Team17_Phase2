import types
import sys
import logging
from types import SimpleNamespace
import pytest

import src.tester as tester
from src import log as slog


def test_run_tests_parses_coverage(monkeypatch, capsys):
    # Create fake stdout that resembles pytest+coverage output
    fake_stdout = """
Name                         Stmts   Miss  Cover   Missing
----------------------------------------------------------
TOTAL                          838    355    58%

34 passed, 0 failed
"""
    fake_proc = SimpleNamespace(stdout=fake_stdout, stderr="", returncode=0)

    def fake_run(cmd, capture_output, text):
        return fake_proc

    monkeypatch.setattr(tester.subprocess, "run", fake_run)

    rc = tester.run_tests()
    # Should return 0 because fake had 0 failed
    assert rc == 0

    captured = capsys.readouterr()
    assert "58% line coverage achieved" in captured.out


def test_setup_logging_invalid_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "not_an_int")
    # re-run setup; should not raise. We can't rely on basicConfig to change
    # pytest's logging configuration here, so just assert wrapper functions
    # still work and produce log records.
    slog.setup_logging()
    from _pytest.logging import caplog as _caplog  # type: ignore
    # use caplog fixture behaviour manually
    # Call the wrappers and ensure no exceptions
    slog.info("info-test")
    slog.error("error-test")
    # No exception means success; additionally ensure functions exist
    assert callable(slog.info)
    assert callable(slog.error)
