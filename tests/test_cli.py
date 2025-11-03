import importlib
import sys
from types import SimpleNamespace
import pytest


def test_install_calls_pip_and_exits(monkeypatch):
    # Ensure GITHUB_TOKEN exists before importing module (module reads it at import)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    # reload module to pick up env var
    import src.cli as cli
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
    import src.cli as cli
    importlib.reload(cli)

    # Patch tester.run_tests
    monkeypatch.setattr(cli.tester, "run_tests", lambda: 3)

    with pytest.raises(SystemExit) as se:
        cli.test()
    assert se.value.code == 3


# def test_main_dispatch_calls_expected(monkeypatch):
#     monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
#     import src.cli as cli
#     importlib.reload(cli)

#     called = {"install": False, "test": False, "score": False}

#     monkeypatch.setattr(cli, "install", lambda: called.__setitem__("install", True))
#     monkeypatch.setattr(cli, "test", lambda: called.__setitem__("test", True))
#     monkeypatch.setattr(cli, "score", lambda arg: called.__setitem__("score", arg))

#     # Run main with install
#     cli.main(["install"])
#     assert called["install"] is True

#     # Run main with test
#     cli.main(["test"])
#     assert called["test"] is True

#     # Run main with score and path
#     cli.main(["/path/to/file.txt"])
#     assert called["score"] == "/path/to/file.txt"
