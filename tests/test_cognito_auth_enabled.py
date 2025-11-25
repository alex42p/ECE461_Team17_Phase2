import os
import types
import pytest

import src.cognito_auth as ca


class FakeClient:
    def admin_initiate_auth(self, **k):
        return {'AuthenticationResult': {'AccessToken': 'A', 'IdToken': 'I', 'RefreshToken': 'R', 'ExpiresIn': 3600}}

    def get_user(self, AccessToken):
        return {'Username': 'u', 'UserAttributes': [{'Name': 'email', 'Value': 'u@example.com'}]}

    def admin_create_user(self, **k):
        return {'User': {'Username': k.get('Username')}}

    def admin_set_user_password(self, **k):
        return {}

    def admin_delete_user(self, **k):
        return {}

    def list_users(self, **k):
        return {'Users': [{'Username': 'u', 'Attributes': [{'Name': 'email', 'Value': 'u@example.com'}], 'UserStatus': 'CONFIRMED', 'UserCreateDate': __import__('datetime').datetime.utcnow(), 'Enabled': True}]}


def test_cognito_enabled_and_methods(monkeypatch):
    monkeypatch.setenv('AWS_COGNITO_USER_POOL_ID', 'pool')
    monkeypatch.setenv('AWS_COGNITO_CLIENT_ID', 'cid')
    monkeypatch.setenv('AWS_COGNITO_CLIENT_SECRET', 'secret')

    monkeypatch.setattr('boto3.client', lambda *a, **k: FakeClient())

    svc = ca.CognitoAuthService()
    assert svc.enabled

    res = svc.authenticate('u', 'p')
    assert res['access_token'] == 'A'

    info = svc.get_user_info('A')
    assert info['username'] == 'u'

    created = svc.create_user('u', 'u@example.com', 'pw')
    assert created['username'] == 'u@example.com'

    assert svc.delete_user('u') is True

    users = svc.list_users()
    assert isinstance(users, list) and users[0]['username'] == 'u'
