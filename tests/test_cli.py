import importlib
import sys
from types import SimpleNamespace
import pytest
import src.cli as cli


def test_install_calls_pip_and_exits(monkeypatch):
    # Ensure GITHUB_TOKEN exists before importing module (module reads it at import)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    # reload module to pick up env var
    
    importlib.reload(cli)

    # Patch subprocess.run to return an object with returncode
    def fake_run(cmd):
        return SimpleNamespace(returncode=7)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as se:
        cli.install()
    assert se.value.code == 7


def test_test_calls_tester_and_exits(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    
    importlib.reload(cli)

    # Patch tester.run_tests
    monkeypatch.setattr(cli.tester, "run_tests", lambda: 3)

    with pytest.raises(SystemExit) as se:
        cli.test()
    assert se.value.code == 3


def test_install_exits_with_subprocess(monkeypatch):
    class FakeRes:
        returncode = 0

    monkeypatch.setattr('subprocess.run', lambda *a, **k: FakeRes())

    with pytest.raises(SystemExit) as se:
        cli.install()
    assert se.value.code == 0


def test_test_invokes_tester(monkeypatch):
    monkeypatch.setattr('src.cli.log.setup_logging', lambda: None)
    monkeypatch.setattr('src.cli.tester.run_tests', lambda: 3)

    with pytest.raises(SystemExit) as se:
        cli.test()
    assert se.value.code == 3

def test_main_score_and_help(monkeypatch, tmp_path):
    # test help (no args) - should not raise
    monkeypatch.setattr(sys, 'argv', ['run'])
    cli.main()

    # test install dispatch via main (monkeypatch install)
    monkeypatch.setattr(sys, 'argv', ['run', 'install'])
    monkeypatch.setattr(cli, 'install', lambda: (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        cli.main()
