import os
import stat
import logging
import json
import tempfile

import pytest

from src import log as log_module
from src import app as app_module
from metric import MetricResult


def test_setup_logging_fails_when_file_missing(monkeypatch, tmp_path):
    # Point LOG_FILE to a non-existent path
    missing = tmp_path / "no_such_dir" / "app.log"
    monkeypatch.setenv("LOG_FILE", str(missing))
    monkeypatch.setenv("LOG_LEVEL", "1")

    with pytest.raises(SystemExit) as exc:
        log_module.setup_logging()
    assert exc.value.code == 1


def test_setup_logging_fails_when_file_not_writable(monkeypatch, tmp_path):
    # Create a real file but remove write permissions
    f = tmp_path / "readonly.log"
    f.write_text("")
    # remove write permission
    f.chmod(0o444)

    monkeypatch.setenv("LOG_FILE", str(f))
    monkeypatch.setenv("LOG_LEVEL", "1")

    try:
        with pytest.raises(SystemExit) as exc:
            log_module.setup_logging()
        assert exc.value.code == 1
    finally:
        # restore permission so cleanup works on some systems
        f.chmod(0o666)


def make_metric(name: str, value: float, latency: int = 5) -> MetricResult:
    return MetricResult(name=name, value=value, details={}, latency_ms=latency)


def test_run_scoring_net_score_and_upload(monkeypatch):
    # Prepare a fake hf metadata
    monkeypatch.setattr(app_module, 'fetch_repo_metadata', lambda model: {'repo_id': 'org/model'})

    # Stub compute_all_metrics to return chosen MetricResult objects
    results = [
        make_metric('license', 1.0, latency=2),
        make_metric('ramp_up_time', 0.5, latency=3),
        make_metric('code_quality', 0.8, latency=4),
    ]

    monkeypatch.setattr(app_module, 'compute_all_metrics', lambda metadata, metrics, max_workers=4: results)

    # Stub storage.save_package so upload_package doesn't write files
    saved = {"id": "pkg-123"}
    monkeypatch.setattr(app_module.storage, 'save_package', lambda **kwargs: saved)

    client = app_module.app.test_client()

    payload = {"name": "p", "url": "https://huggingface.co/org/model"}
    resp = client.post('/package', json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    if data:
        assert data['success'] is True
        assert data['package_id'] == 'pkg-123'

        # Check that net_score was computed and present in response
        assert ('net_score' in data['scores'])


def test_package_validation_errors(client=None):
    client = client or app_module.app.test_client()

    # No body
    r = client.post('/package')
    assert r.status_code != 200

    # Missing name
    r = client.post('/package', json={"url": "u"})
    assert r.status_code != 200

    # Missing url
    r = client.post('/package', json={"name": "n"})
    assert r.status_code != 200


def test_get_package_not_found_and_found(monkeypatch):
    client = app_module.app.test_client()

    # Not found
    monkeypatch.setattr(app_module.storage, 'get_package', lambda pid: None)
    r = client.get('/package/notexist')
    assert r.status_code == 404

    # Found
    pkg = {"id": "x", "name": "n"}
    monkeypatch.setattr(app_module.storage, 'get_package', lambda pid: pkg)
    r = client.get('/package/x')
    assert r.status_code == 200
    assert r.get_json() == pkg


def test_search_by_regex_errors_and_success(monkeypatch):
    client = app_module.app.test_client()

    # Missing param
    r = client.get('/packages/byRegex')
    assert r.status_code == 400

    # Invalid regex triggers ValueError
    def bad_search(pat):
        raise ValueError("bad regex")
    monkeypatch.setattr(app_module.storage, 'search_by_regex', bad_search)
    r = client.get('/packages/byRegex', query_string={'RegEx': '(['})
    assert r.status_code == 400

    # Success
    def ok_search(pat):
        return [{"id": "a", "scores": {"net_score": {"value": 0.5}}}]
    monkeypatch.setattr(app_module.storage, 'search_by_regex', ok_search)
    r = client.get('/packages/byRegex', query_string={'RegEx': 'a'})
    assert r.status_code == 200
    j = r.get_json()
    if j:
        assert j['count'] == 1
