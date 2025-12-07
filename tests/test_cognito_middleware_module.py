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


def test_require_auth_allows_and_denies_roles(monkeypatch):
    import src.app as appmod
    class R:
        headers = {'X-Authorization': 'Bearer good'}

    monkeypatch.setattr(cm, 'request', R)

    class FakeCognito:
        def verify_token(self, t):
            return {'username': 'u', 'role': 'uploader'}

    monkeypatch.setattr(cm, 'cognito_auth', FakeCognito())

    @cm.require_auth(['uploader'])
    def g():
        return 'ok'

    from src.app import app as flask_app
    with flask_app.app_context():
        res = g()
    assert res == 'ok'

    # Now require admin role -> should be 403
    @cm.require_auth(['admin'])
    def h():
        return 'no'

    with flask_app.app_context():
        res2 = h()
    assert isinstance(res2, tuple)
    assert res2[1] == 403


def test_optional_auth_attaches_user_when_present(monkeypatch):
    class R:
        headers = {'X-Authorization': 'Bearer t'}

    monkeypatch.setattr(cm, 'request', R)

    class FakeCognito:
        def verify_token(self, t):
            return {'username': 'x'}

    monkeypatch.setattr(cm, 'cognito_auth', FakeCognito())

    @cm.optional_auth
    def f():
        return cm.get_current_user()

    # When called, should return user dict
    res = f()
    assert isinstance(res, dict) and res['username'] == 'x'
