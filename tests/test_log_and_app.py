import pytest

from src import log as log_module
from src import app as app_module


def test_setup_logging_fails_when_file_missing(monkeypatch, tmp_path):
    # Point LOG_FILE to a non-existent path
    missing = tmp_path / "no_such_dir" / "app.log"
    monkeypatch.setenv("LOG_FILE", str(missing))
    monkeypatch.setenv("LOG_LEVEL", "1")

    with pytest.raises(SystemExit) as exc:
        log_module.setup_logging()
    assert exc.value.code == 1

def test_run_scoring_net_score_and_upload(monkeypatch):
    # Prepare a fake hf metadata
    monkeypatch.setattr(app_module, 'fetch_repo_metadata', lambda model: {'repo_id': 'org/model'})

    # Stub compute_all_metrics to return chosen MetricResult objects
    from metric import MetricResult

    results = [
        MetricResult(name='license', value=1.0, details={}, latency_ms=2),
        MetricResult(name='ramp_up_time', value=0.5, details={}, latency_ms=3),
        MetricResult(name='code_quality', value=0.8, details={}, latency_ms=4),
    ]

    monkeypatch.setattr(app_module, 'compute_all_metrics', lambda metadata, metrics, max_workers=4: results)

    # Stub storage.save_package so upload_package doesn't write files
    saved = {"id": "pkg-123"}
    monkeypatch.setattr(app_module.storage, 'save_package', lambda **kwargs: saved)

    # Ensure endpoint auth allows the request by returning an uploader user
    monkeypatch.setattr(app_module, 'get_current_user', lambda: {"username": "u", "role": "uploader"})

    payload = {"name": "p", "url": "https://huggingface.co/org/model"}
    with app_module.app.test_request_context('/package', method='POST', json=payload):
        resp = app_module.upload_package.__wrapped__()
    # Flask view may return (response, status) or a Response - normalize
    if isinstance(resp, tuple):
        data, status = resp
    else:
        data = resp
        status = getattr(resp, 'status_code', 200)
    assert status == 201
    data_json = data.get_json() if hasattr(data, 'get_json') else data
    assert data_json['success'] is True
    assert data_json['package_id'] == 'pkg-123'

    # Check that net_score was computed and present in response
    assert ('net_score' in data_json['scores'])


def test_package_validation_errors():
    client = app_module.app.test_client()

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
    # Not found
    monkeypatch.setattr(app_module.storage, 'get_package', lambda pid: None)
    with app_module.app.test_request_context('/package/notexist', method='GET'):
        r = app_module.get_package.__wrapped__('notexist')
    if isinstance(r, tuple):
        resp_body, status = r
    else:
        resp_body, status = r, getattr(r, 'status_code', 200)
    assert status == 404

    # Found
    pkg = {"id": "x", "name": "n"}
    monkeypatch.setattr(app_module.storage, 'get_package', lambda pid: pkg)
    with app_module.app.test_request_context('/package/x', method='GET'):
        r = app_module.get_package.__wrapped__('x')
    if isinstance(r, tuple):
        resp_body, status = r
    else:
        resp_body, status = r, getattr(r, 'status_code', 200)
    assert status == 200
    # resp_body may be a flask Response or dict
    body_json = resp_body.get_json() if hasattr(resp_body, 'get_json') else resp_body
    assert body_json == pkg


def test_search_by_regex_errors_and_success(monkeypatch):
    # Missing param
    with app_module.app.test_request_context('/packages/byRegex', method='GET'):
        r = app_module.search_by_regex.__wrapped__()
    # Expect error (bad request or unauthorized)
    if isinstance(r, tuple):
        _, status = r
    else:
        status = getattr(r, 'status_code', 200)
    assert status != 200

    # Invalid regex triggers ValueError
    def bad_search(pat):
        raise ValueError("bad regex")
    monkeypatch.setattr(app_module.storage, 'search_by_regex', bad_search)
    with app_module.app.test_request_context('/packages/byRegex?RegEx=([', method='GET'):
        r = app_module.search_by_regex.__wrapped__()
    if isinstance(r, tuple):
        _, status = r
    else:
        status = getattr(r, 'status_code', 200)
    assert status != 200

    # Success - allow auth by patching current user
    monkeypatch.setattr(app_module, 'get_current_user', lambda: {"username": "u", "role": "searcher"})
    def ok_search(pat):
        return [{"id": "a", "scores": {"net_score": {"value": 0.5}}}]
    monkeypatch.setattr(app_module.storage, 'search_by_regex', ok_search)
    with app_module.app.test_request_context('/packages/byRegex?RegEx=a', method='GET'):
        r = app_module.search_by_regex.__wrapped__()
    if isinstance(r, tuple):
        resp_body, status = r
    else:
        resp_body, status = r, getattr(r, 'status_code', 200)
    assert status == 200
    body_json = resp_body.get_json() if hasattr(resp_body, 'get_json') else resp_body
    if body_json:
        assert body_json['count'] == 1
