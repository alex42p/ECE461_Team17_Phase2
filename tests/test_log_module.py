import os
import tempfile
import stat
import pytest

import src.log as logmod


def test_setup_logging_success(tmp_path, monkeypatch):
    f = tmp_path / 'app.log'
    f.write_text('')
    monkeypatch.setenv('LOG_FILE', str(f))
    monkeypatch.setenv('LOG_LEVEL', '1')

    # Should not raise
    logmod.setup_logging()


def test_setup_logging_missing_parent(monkeypatch, tmp_path):
    # Point to non-existent directory
    p = tmp_path / 'no-dir' / 'file.log'
    monkeypatch.setenv('LOG_FILE', str(p))
    monkeypatch.setenv('LOG_LEVEL', '1')

    with pytest.raises(SystemExit):
        logmod.setup_logging()
