# from types import SimpleNamespace
# import time
# import pytest

# import src.auth_middleware as am
# from src.app import app as flask_app

# def test_extract_token_variants(monkeypatch):
#     class R:
#         headers = {'X-Authorization': 'Bearer tok'}

#     monkeypatch.setattr(am, 'request', R)
#     assert am.extract_token() == 'tok'

#     R.headers = {'X-Authorization': 'justtoken'}
#     assert am.extract_token() == 'justtoken'

#     R.headers = {}
#     assert am.extract_token() is None


# def test_check_permission_and_rate_limiter(monkeypatch):
#     # Test permission logic
#     monkeypatch.setattr(am, 'g', SimpleNamespace())
#     am.g.current_user = {'username': 'alice', 'role': 'uploader'}
#     assert am.check_permission('upload', resource_owner=None) is True
#     assert am.check_permission('download') is False

#     # RateLimiter basic behavior
#     rl = am.RateLimiter()
#     assert rl.check_rate_limit('u', '/x', max_requests=2, window_seconds=1)
#     assert rl.check_rate_limit('u', '/x', max_requests=2, window_seconds=1)
#     # Third call should be rejected
#     assert not rl.check_rate_limit('u', '/x', max_requests=2, window_seconds=1)


# def test_rate_limit_decorator_blocks(monkeypatch):
#     # Decorator should block after exceeding limit
#     # Monkeypatch get_current_user to simulate unauthenticated -> uses remote_addr
#     class R:
#         headers = {}
#         remote_addr = '1.2.3.4'
#         endpoint = None
#         path = '/'

#     monkeypatch.setattr(am, 'request', R)

#     # Ensure same RateLimiter instance is used
#     fn_called = {'ok': 0}

#     @am.rate_limit(max_requests=1, window_seconds=1)
#     def f():
#         fn_called['ok'] += 1
#         return 'ok'

#     # First call allowed
#     from src.app import app as flask_app

#     with flask_app.app_context():
#         assert f() == 'ok'
#         # Second call blocked
#         resp = f()
#     assert isinstance(resp, tuple)
#     assert resp[1] == 429


# def test_require_auth_success(monkeypatch):
#     # Fake request with header
#     class R:
#         headers = {'X-Authorization': 'Bearer tok'}
#         remote_addr = '1.2.3.4'

#     monkeypatch.setattr(am, 'request', R)

#     # Fake auth service that returns payload
#     class FakeAuth:
#         def verify_token(self, t):
#             return {'username': 'alice', 'role': 'admin', 'token_id': 'tid'}

#     monkeypatch.setattr(am, 'get_auth_service', lambda: FakeAuth())

#     @am.require_auth([am.UserRole.ADMIN])
#     def f():
#         return 'ok'

#     with flask_app.app_context():
#         res = f()

#     assert res == 'ok'
