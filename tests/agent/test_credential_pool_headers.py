"""Tests for per-credential headers in credential pool."""

from agent.credential_pool import PooledCredential


def test_pooled_credential_has_headers_field():
    cred = PooledCredential(
        provider="aide",
        id="test-1",
        label="test",
        auth_type="api_key",
        priority=0,
        source="manual",
        access_token="fake-token",
        headers={"x-user-id": "MTK12265"},
    )
    assert cred.headers == {"x-user-id": "MTK12265"}


def test_pooled_credential_headers_default_none():
    cred = PooledCredential(
        provider="aide",
        id="test-2",
        label="test",
        auth_type="api_key",
        priority=0,
        source="manual",
        access_token="fake-token",
    )
    assert cred.headers is None
