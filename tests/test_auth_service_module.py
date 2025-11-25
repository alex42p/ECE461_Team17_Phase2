import pytest

from src.auth_service import AuthService


def test_password_strength_and_verify():
    assert not AuthService._is_password_strong('weak')
    assert AuthService._is_password_strong('StrongPass123!')

    hashed = AuthService._hash_password('StrongPass123!')
    assert isinstance(hashed, str)
    assert AuthService._verify_password('StrongPass123!', hashed)
    assert not AuthService._verify_password('wrong', hashed)


def test_verify_token_invalid():
    # No valid JWT should return None
    auth = AuthService.__new__(AuthService)
    # Provide minimal session to avoid attribute errors
    auth.session = None
    assert auth.verify_token('not-a-token') is None


def test_create_user_duplicate_and_authenticate_inactive(monkeypatch):
    # Simulate existing user via fake session.query(...).filter_by(...).first()
    class Q:
        def first(self):
            return True

        def filter_by(self, **k):
            return self

    class FakeSession:
        def query(self, model):
            return Q()

        def add(self, obj):
            pass

        def flush(self):
            pass

    svc = AuthService(FakeSession())
    with pytest.raises(ValueError):
        svc.create_user('u', 'StrongPass123!', None)

    # Test authenticate with inactive user by monkeypatching get_user
    class FakeUser:
        username = 'u'
        password_hash = AuthService._hash_password('GoodPass1!')
        is_active = False

    monkeypatch.setattr(AuthService, 'get_user', lambda self, u: FakeUser())
    svc2 = AuthService.__new__(AuthService)
    svc2.session = None # type: ignore
    assert svc2.authenticate('u', 'GoodPass1!') is None


def test_create_user_success(monkeypatch):
    # Fake session where query(...).filter_by(...).first() returns None
    class Q:
        def first(self):
            return None

        def filter_by(self, **k):
            return self

    class FakeSession:
        def __init__(self):
            self.added = []

        def query(self, model):
            return Q()

        def add(self, o):
            self.added.append(o)

        def flush(self):
            return

    sess = FakeSession()
    svc = AuthService(sess)
    user = svc.create_user('newuser', 'StrongPass123!', None)
    assert user.username == 'newuser'
    assert hasattr(user, 'password_hash')
