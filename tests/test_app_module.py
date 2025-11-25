import subprocess
import types

import src.app as app

def test_execute_monitoring_script_success(monkeypatch, tmp_path):
    # Simulate node execution success
    fake_result = types.SimpleNamespace(returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: fake_result)

    success, output = app.execute_monitoring_script(
        script_content='console.log("hi")',
        model_name='m',
        uploader_username='u',
        downloader_username='d',
        zip_file_path=str(tmp_path / 'f.zip')
    )

    assert success is True
    assert output == "OK"

def test_execute_monitoring_script_timeout(monkeypatch, tmp_path):
    # Simulate timeout
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd='node', timeout=1)

    monkeypatch.setattr(subprocess, 'run', raise_timeout)

    success, output = app.execute_monitoring_script(
        script_content='console.log("hi")',
        model_name='m',
        uploader_username='u',
        downloader_username='d',
        zip_file_path=str(tmp_path / 'f.zip')
    )

    assert success is False
    assert 'timed out' in output.lower()

def test_run_scoring_handles_exceptions(monkeypatch):
    # Make HFModelURL raise to trigger exception handling
    monkeypatch.setattr(app, 'HFModelURL', lambda url: (_ for _ in ()).throw(ValueError('bad')))

    res = app.run_scoring('https://example.com')
    assert 'error' in res
    assert res['net_score']['value'] == 0.0


def test_authenticate_endpoint_errors():
    client = app.app.test_client()

    # No body -> 400 (or internal error in test env) - ensure non-200
    resp = client.put('/authenticate')
    assert resp.status_code in (400, 500)

    # Missing username/password -> 400
    resp = client.put('/authenticate', json={"User": {}, "Secret": {}})
    assert resp.status_code == 400

    # Partial body (username only) -> 400
    resp = client.put('/authenticate', json={"User": {"name": "u"}})
    assert resp.status_code == 400

def test_unauthorized_json_response():
    with app.app.test_request_context('/', headers={'Accept': 'application/json'}):
        resp, status = app.unauthorized('err')
        assert status == 401
        assert 'error' in resp.json # type: ignore

def test_forbidden_json_response():
    with app.app.test_request_context('/', headers={'Accept': 'application/json'}):
        resp, status = app.forbidden('err')
        assert status == 403
        assert resp.json['error'] == 'Forbidden' # type: ignore


# --- Additional tests for coverage ---
import types
import pytest
from unittest.mock import MagicMock

# def test_main_block(monkeypatch):
#     # Patch app.run to prevent actually running the server
#     monkeypatch.setattr(app, 'app', MagicMock())
#     monkeypatch.setattr(app, 'USE_COGNITO', False)
#     monkeypatch.setattr(app, 'init_db', lambda: None)
#     monkeypatch.setattr(app, 'storage', MagicMock())
#     monkeypatch.setattr(app, 'db_manager', MagicMock())
#     # Patch print to capture output
#     output = io.StringIO()
#     monkeypatch.setattr(sys, 'argv', ['app.py'])
#     monkeypatch.setattr(builtins, 'print', lambda *a, **k: output.write(' '.join(map(str, a)) + '\n'))
#     # Patch __name__ to '__main__' and run the block
#     import importlib
#     import importlib.util
#     import types as pytypes
#     spec = importlib.util.spec_from_file_location("src.app", app.__file__)
#     module = importlib.util.module_from_spec(spec) # type: ignore
#     setattr(module, 'app', MagicMock())
#     setattr(module, 'USE_COGNITO', False)
#     setattr(module, 'init_db', lambda: None)
#     setattr(module, 'storage', MagicMock())
#     setattr(module, 'db_manager', MagicMock())
#     setattr(module, '__name__', '__main__')
#     setattr(module, 'print', lambda *a, **k: output.write(' '.join(map(str, a)) + '\n'))
#     # Patch app.run to avoid running server
#     setattr(module.app, 'run', lambda *a, **k: output.write('RUN\n'))
#     code = open(app.__file__).read()
#     exec(code, module.__dict__)
#     assert 'ECE461 Team 17' in output.getvalue()
#     assert 'Listening on http://127.0.0.1:8080' in output.getvalue()

def test_home_route(monkeypatch):
    client = app.app.test_client()
    # Patch render_template to avoid template error
    monkeypatch.setattr(app, 'render_template', lambda t: f'rendered:{t}')
    resp = client.get('/')
    assert resp.data == b'rendered:index.html'
    assert resp.status_code == 200

@pytest.mark.parametrize('handler,code', [
    (app.unauthorized, 401),
    (app.forbidden, 403),
])
def test_error_handlers_html(monkeypatch, handler, code):
    # Patch render_template to return a string
    monkeypatch.setattr(app, 'render_template', lambda *a, **k: f'html:{code}')
    class FakeAccept:
        accept_html = True
        accept_json = False
    monkeypatch.setattr(app, 'request', types.SimpleNamespace(accept_mimetypes=FakeAccept()))
    resp = handler('err')
    assert resp[0].startswith('html:')
    assert resp[1] == code

def test_upload_package_missing_fields(monkeypatch):
    client = app.app.test_client()
    # Patch get_current_user and storage
    monkeypatch.setattr(app, 'get_current_user', lambda: {'username': 'u'})
    monkeypatch.setattr(app, 'storage', MagicMock())
    # Missing name
    resp = client.post('/package', json={"url": "x"})
    assert 400 <= resp.status_code < 500
    # Missing url
    resp = client.post('/package', json={"name": "x"})
    assert 400 <= resp.status_code < 500

def test_search_by_regex_missing_param(monkeypatch):
    client = app.app.test_client()
    monkeypatch.setattr(app, 'get_current_user', lambda: {'username': 'u'})
    monkeypatch.setattr(app, 'storage', MagicMock())
    resp = client.get('/packages/byRegex')
    assert 400 <= resp.status_code < 500

# def test_reset_system_storage_path_not_exists(monkeypatch):
#     client = app.app.test_client()
#     # Patch storage.metadata_dir.exists to False
#     fake_path = MagicMock()
#     fake_path.exists.return_value = False
#     monkeypatch.setattr(app.storage, 'metadata_dir', fake_path)
#     monkeypatch.setattr(app, 'db_manager', MagicMock())
#     monkeypatch.setattr(app, 'init_db', lambda: None)
#     resp = client.delete('/reset')
#     assert resp.status_code == 200

def test_execute_monitoring_script_nonzero(monkeypatch, tmp_path):
    # Simulate node execution with nonzero returncode
    fake_result = types.SimpleNamespace(returncode=1, stdout="", stderr="fail")
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: fake_result)
    success, output = app.execute_monitoring_script(
        script_content='console.log("fail")',
        model_name='m',
        uploader_username='u',
        downloader_username='d',
        zip_file_path=str(tmp_path / 'f.zip')
    )
    assert success is False
    assert output == "fail"
