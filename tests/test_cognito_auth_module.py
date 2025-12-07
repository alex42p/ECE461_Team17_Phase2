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


def test_get_user_info_client_not_initialized():
    svc = CognitoAuthService()
    # Ensure client is None and get_user_info raises a ValueError
    svc.client = None
    try:
        svc.get_user_info('token')
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_mask_and_verify_token_none(monkeypatch):
    svc = CognitoAuthService()
    masked = svc._mask('user@example.com')
    assert 'user@example.com' not in masked

    # If get_user_info raises, verify_token should return None
    monkeypatch.setattr(svc, 'get_user_info', lambda t: (_ for _ in ()).throw(Exception('bad')))
    assert svc.verify_token('x') is None
