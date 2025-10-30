import os
import shutil
from types import SimpleNamespace
import pytest

import src.huggingface_inspect as inspect

class DummyRepo:
    @staticmethod
    def clone_from(url, path):
        # create the path to simulate clone
        os.makedirs(path, exist_ok=True)


def test_clone_and_cleanup(tmp_path, monkeypatch):
    # Use tmp_path as cache_dir to avoid touching repo cache
    monkeypatch.setattr(inspect.git, "Repo", DummyRepo)

    model_dir = inspect.clone_model_repo("my-model", cache_dir=tmp_path)
    assert model_dir.exists()

    # Now cleanup
    inspect.clean_up_cache(model_dir)
    assert not model_dir.exists()

def test_clone_noop_if_exists(tmp_path, monkeypatch):
    # If model dir exists, clone_from should not be called.
    target = tmp_path / "existing-model"
    target.mkdir()
    called = {"cloned": False}
    def fake_clone(url, path):
        called["cloned"] = True
    class RepoShim:
        @staticmethod
        def clone_from(u, p):
            fake_clone(u,p)
    monkeypatch.setattr(inspect.git, "Repo", RepoShim)

    model_dir = inspect.clone_model_repo("existing-model", cache_dir=tmp_path)
    assert model_dir == target
    assert called["cloned"] is False
