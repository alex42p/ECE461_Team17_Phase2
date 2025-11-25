import pytest

import src.cognito_middleware as cm


def test_get_token_from_request():
    class R:
        headers = {'X-Authorization': 'Bearer token123'}

    cm.request = R
    assert cm.get_token_from_request() == 'token123'

    R.headers = {'X-Authorization': 'Bad header'}
    assert cm.get_token_from_request() is None


def test_require_auth_decorator(monkeypatch):
    # Simulate verify_token returning None -> should return 401 response
    class R:
        headers = {'X-Authorization': 'Bearer bad'}

    monkeypatch.setattr(cm, 'request', R)

    class FakeCognito:
        def verify_token(self, t):
            return None

    monkeypatch.setattr(cm, 'cognito_auth', FakeCognito())

    @cm.require_auth()
    def f():
        return 'ok'
    from src.app import app as flask_app

    with flask_app.app_context():
        res = f()
    assert isinstance(res, tuple)
    assert res[1] == 401
