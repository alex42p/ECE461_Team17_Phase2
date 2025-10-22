import os
import logging
import tempfile
from pathlib import Path
import pytest

import src.cli_project.core.log as log


def test_setup_logging_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Default setup should disable logging (level above CRITICAL)."""
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "default.log"))
    monkeypatch.delenv("LOG_LEVEL", raising=False)  # remove to use default

    log.setup_logging()
    log.info("This should not appear")

    # Since default level = 0 → disabled logging
    assert caplog.records == []


@pytest.mark.parametrize(
    "level_env, msg, expected_in",
    [
        ("1", "info msg", "INFO"),
        ("2", "debug msg", "DEBUG"),
        ("not-an-int", "should not appear", None),
        ("99", "should not appear", None),
    ],
)
def test_setup_logging_levels(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                              level_env: str, msg: str, expected_in: str | None) -> None:
    """Check that LOG_LEVEL environment variable controls logging output."""
    monkeypatch.setenv("LOG_FILE", "test.log")
    monkeypatch.setenv("LOG_LEVEL", level_env)

    log.setup_logging()

    with caplog.at_level(logging.DEBUG):
        if level_env == "1":
            log.info(msg)
        elif level_env == "2":
            log.debug(msg)
        else:
            log.info(msg)

    if expected_in:
        assert any(expected_in in rec.levelname for rec in caplog.records)
    else:
        assert caplog.records == []


def test_log_wrappers(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Ensure each wrapper emits a log message at the correct level."""
    monkeypatch.setenv("LOG_LEVEL", "2")  # DEBUG enabled
    monkeypatch.delenv("LOG_FILE", raising=False)

    log.setup_logging()

    with caplog.at_level(logging.DEBUG):
        log.debug("debug msg")
        log.info("info msg")
        log.warn("warn msg")
        log.error("error msg")
        log.critical("critical msg")

    messages = [rec.getMessage() for rec in caplog.records]
    assert "debug msg" in messages
    assert "info msg" in messages
    assert "warn msg" in messages
    assert "error msg" in messages
    assert "critical msg" in messages


def test_log_file_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that messages are written to the configured log file."""
    log_path = tmp_path / "custom.log"
    monkeypatch.setenv("LOG_FILE", str(log_path))
    monkeypatch.setenv("LOG_LEVEL", "1")  # INFO

    log.setup_logging()
    log.info("file log message")

    # Ensure file exists and contains the message
    content = log_path.read_text()
    assert "file log message" in content
