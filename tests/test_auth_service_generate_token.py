# from types import SimpleNamespace
# from sqlalchemy.orm import Session
# from src.auth_service import AuthService


# class FakeSession(Session):
#     def __init__(self):
#         self.added = []

#     def add(self, obj):
#         self.added.append(obj)

#     def flush(self):
#         return


# def test_generate_token_creates_token_and_usage():
#     sess = FakeSession()
#     auth = AuthService(sess)

#     class Role:
#         value = 'admin'

#     user = SimpleNamespace(username='alice', role=Role())

#     res = auth.generate_token(user) # type: ignore
#     assert 'token' in res
#     assert 'token_id' in res
#     assert res['username'] == 'alice'
