import os
import pytest

from src.cognito_auth import CognitoAuthService


def test_cognito_disabled_by_default(monkeypatch):
    # Ensure no env vars -> disabled
    monkeypatch.delenv('AWS_COGNITO_USER_POOL_ID', raising=False)
    monkeypatch.delenv('AWS_COGNITO_CLIENT_ID', raising=False)
    monkeypatch.delenv('AWS_COGNITO_CLIENT_SECRET', raising=False)

    svc = CognitoAuthService()
    assert svc.enabled is False


def test_get_secret_hash(monkeypatch):
    svc = CognitoAuthService()
    svc.client_id = 'cid123'
    svc.client_secret = 'secret'
    h = svc._get_secret_hash('user')
    assert isinstance(h, str)
    # Base64 contains '=' padding or characters
    assert len(h) > 0
