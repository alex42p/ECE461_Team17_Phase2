import pytest
from types import SimpleNamespace

import src.git_repo as git_repo

class FakeResponse:
    def __init__(self, code, payload):
        self.status_code = code
        self._payload = payload
    def json(self):
        return self._payload


def test_fetch_bus_factor_raw_contributors_success(monkeypatch):
    calls = []
    # Simulate contributors API: page 1 -> list, page 2 -> [] to stop
    def fake_get(url, params=None, headers=None):
        calls.append((url, params, headers))
        if 'contributors' in url:
            if params and params.get('page', 1) == 1:
                return FakeResponse(200, [
                    {"login": "alice", "contributions": 10},
                    {"login": "bob", "contributions": 5}
                ])
            else:
                return FakeResponse(200, [])
        else:
            # repo API
            return FakeResponse(200, {"pushed_at": "2020-01-01T00:00:00Z"})

    monkeypatch.setattr(git_repo.requests, "get", fake_get)

    result = git_repo.fetch_bus_factor_raw_contributors("https://github.com/org/repo", token="t")
    assert result["unique_committers_count"] == 2
    assert result["commit_count_by_committer"]["alice"] == 10
    assert result["method"] == "contributors"
    assert result["last_commit_date"] == "2020-01-01T00:00:00Z"


def test_fetch_bus_factor_raises_on_bad_status(monkeypatch):
    def fake_get(url, params=None, headers=None):
        return FakeResponse(404, {})
    monkeypatch.setattr(git_repo.requests, "get", fake_get)
    with pytest.raises(Exception):
        git_repo.fetch_bus_factor_raw_contributors("https://github.com/org/repo")
