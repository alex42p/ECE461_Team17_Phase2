# import pytest

# from src.auth_service import AuthService


# def test_password_strength_and_verify():
#     assert not AuthService._is_password_strong('weak')
#     assert AuthService._is_password_strong('StrongPass123!')

#     hashed = AuthService._hash_password('StrongPass123!')
#     assert isinstance(hashed, str)
#     assert AuthService._verify_password('StrongPass123!', hashed)
#     assert not AuthService._verify_password('wrong', hashed)


# def test_verify_token_invalid():
#     # No valid JWT should return None
#     auth = AuthService.__new__(AuthService)
#     # Provide minimal session to avoid attribute errors
#     auth.session = None
#     assert auth.verify_token('not-a-token') is None


# def test_create_user_duplicate_and_authenticate_inactive(monkeypatch):
#     # Simulate existing user via fake session.query(...).filter_by(...).first()
#     class Q:
#         def first(self):
#             return True

#         def filter_by(self, **k):
#             return self

#     class FakeSession:
#         def query(self, model):
#             return Q()

#         def add(self, obj):
#             pass

#         def flush(self):
#             pass

#     svc = AuthService(FakeSession())
#     with pytest.raises(ValueError):
#         svc.create_user('u', 'StrongPass123!', None)

#     # Test authenticate with inactive user by monkeypatching get_user
#     class FakeUser:
#         username = 'u'
#         password_hash = AuthService._hash_password('GoodPass1!')
#         is_active = False

#     monkeypatch.setattr(AuthService, 'get_user', lambda self, u: FakeUser())
#     svc2 = AuthService.__new__(AuthService)
#     svc2.session = None # type: ignore
#     assert svc2.authenticate('u', 'GoodPass1!') is None


# def test_create_user_success(monkeypatch):
#     # Fake session where query(...).filter_by(...).first() returns None
#     class Q:
#         def first(self):
#             return None

#         def filter_by(self, **k):
#             return self

#     class FakeSession:
#         def __init__(self):
#             self.added = []

#         def query(self, model):
#             return Q()

#         def add(self, o):
#             self.added.append(o)

#         def flush(self):
#             return

#     sess = FakeSession()
#     svc = AuthService(sess)
#     user = svc.create_user('newuser', 'StrongPass123!', None)
#     assert user.username == 'newuser'
#     assert hasattr(user, 'password_hash')


# def test_generate_verify_token_and_usage(monkeypatch):
#     from src.auth_service import AuthService
#     from src.database import UserRole
#     import types
#     import datetime

#     # Fake session that records added TokenUsage objects and can be queried
#     class FakeQuery:
#         def __init__(self, session, model):
#             self.session = session
#             self.model = model
#             self._filters = {}

#         def filter_by(self, **k):
#             self._filters.update(k)
#             return self

#         def first(self):
#             # match on token_id or username
#             for o in self.session.added:
#                 if all(getattr(o, k, None) == v for k, v in self._filters.items()):
#                     return o
#             return None

#         def all(self):
#             res = []
#             for o in self.session.added:
#                 if all(getattr(o, k, None) == v for k, v in self._filters.items()):
#                     res.append(o)
#             return res

#     class FakeSession:
#         def __init__(self):
#             self.added = []

#         def add(self, o):
#             self.added.append(o)

#         def flush(self):
#             return

#         def query(self, model):
#             return FakeQuery(self, model)

#     fs = FakeSession()
#     svc = AuthService(fs)

#     # Create a fake user object with expected attributes
#     user = types.SimpleNamespace(username='alice', role=UserRole.SEARCHER)

#     # Generate token (this will add a TokenUsage object to session)
#     out = svc.generate_token(user)
#     assert 'token' in out and 'token_id' in out

#     # Verify token returns payload
#     payload = svc.verify_token(out['token'])
#     assert payload is not None and payload.get('username') == 'alice'

#     # Check token usage retrieval
#     usage = svc.get_token_usage(out['token_id'])
#     assert usage is not None and usage['token_id'] == out['token_id']

#     # get_user_tokens should return list
#     toks = svc.get_user_tokens('alice')
#     assert isinstance(toks, list)


# def test_delete_user_permissions_and_list(monkeypatch):
#     from src.auth_service import AuthService
#     from src.database import UserRole
#     import types

#     # Fake user objects
#     class FakeUser:
#         def __init__(self, username, role, active=True):
#             self.username = username
#             self.role = role
#             self.is_active = active
#         def to_dict(self):
#             return {'username': self.username, 'role': self.role}

#     # Fake session returning specific users
#     class Q:
#         def __init__(self, obj):
#             self.obj = obj
#         def filter_by(self, **k):
#             return self
#         def first(self):
#             return self.obj
#         def all(self):
#             return [self.obj]

#     class FakeSession:
#         def __init__(self, obj):
#             self.obj = obj
#             self.flushed = False
#         def query(self, model):
#             return Q(self.obj)
#         def add(self, o):
#             pass
#         def flush(self):
#             self.flushed = True

#     # Not found case
#     fs_none = FakeSession(None)
#     svc_none = AuthService(fs_none)
#     assert svc_none.delete_user('x', types.SimpleNamespace(username='y', role=UserRole.SEARCHER)) is False

#     # Self delete
#     u = FakeUser('bob', UserRole.SEARCHER)
#     fs = FakeSession(u)
#     svc = AuthService(fs)
#     assert svc.delete_user('bob', u) is True

#     # Admin delete
#     u2 = FakeUser('carol', UserRole.SEARCHER)
#     fs2 = FakeSession(u2)
#     svc2 = AuthService(fs2)
#     admin = types.SimpleNamespace(username='admin', role=UserRole.ADMIN)
#     assert svc2.delete_user('carol', admin) is True

#     # list_users
#     u3 = FakeUser('d', UserRole.SEARCHER)
#     sess3 = FakeSession(u3)
#     svc3 = AuthService(sess3)
#     lst = svc3.list_users()
#     assert isinstance(lst, list) and lst[0]['username'] == 'd'
