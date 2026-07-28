"""Authentication safety tests for the TeamsMTK adapter."""

import base64
import json
import os
import stat
import sys
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from gateway.platforms.teams_mtk import _TeamsAuth


def test_windows_tls_adapter_uses_configured_ca_bundle(tmp_path, monkeypatch):
    import gateway.platforms.teams_mtk as teams_mtk

    adapter_class = getattr(teams_mtk, "_WindowsTLS12HTTPAdapter", None)
    if adapter_class is None:
        pytest.skip("Teams SDK dependencies are not installed")

    bundle = tmp_path / "combined-ca.pem"
    bundle.write_text("test bundle", encoding="utf-8")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bundle))
    context = MagicMock()

    with patch.object(
        teams_mtk.ssl, "create_default_context", return_value=context
    ) as create_context:
        adapter_class()

    create_context.assert_called_once_with(cafile=str(bundle))


def _jwt_with_claims(**claims) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps(claims).encode("utf-8")
    ).decode().rstrip("=")
    return f"{header}.{payload}."


def test_inject_truststore_applies_configured_ca_bundle(tmp_path, monkeypatch):
    """A configured bundle must reach requests and urllib despite import order."""
    bundle = tmp_path / "combined-ca.pem"
    bundle.write_text("test bundle", encoding="utf-8")
    for key in ("HERMES_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(key, raising=False)

    auth = _TeamsAuth()
    inject = MagicMock()
    with patch(
        "hermes_cli.config.load_config_readonly",
        return_value={"gateway": {"teams_mtk": {"ca_bundle": str(bundle)}}},
    ), patch.dict(sys.modules, {"truststore": MagicMock(inject_into_ssl=inject)}):
        auth._inject_truststore()
        auth._inject_truststore()

    assert os.environ["REQUESTS_CA_BUNDLE"] == str(bundle)
    assert os.environ["SSL_CERT_FILE"] == str(bundle)
    inject.assert_not_called()


def test_inject_truststore_without_bundle_uses_os_store(monkeypatch):
    """OS truststore remains the fallback when no explicit bundle exists."""
    for key in ("HERMES_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(key, raising=False)

    auth = _TeamsAuth()
    inject = MagicMock()
    with patch("hermes_cli.config.load_config_readonly", return_value={}),             patch.dict(sys.modules, {"truststore": MagicMock(inject_into_ssl=inject)}):
        auth._inject_truststore()
        auth._inject_truststore()

    inject.assert_called_once_with()


def test_inject_truststore_falls_back_to_existing_hermes_bundle(tmp_path, monkeypatch):
    """The existing cross-Hermes CA convention remains supported."""
    bundle = tmp_path / "hermes-ca.pem"
    bundle.write_text("test bundle", encoding="utf-8")
    monkeypatch.setenv("HERMES_CA_BUNDLE", str(bundle))
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    auth = _TeamsAuth()
    with patch("hermes_cli.config.load_config_readonly", return_value={}):
        auth._inject_truststore()

    assert os.environ["REQUESTS_CA_BUNDLE"] == str(bundle)
    assert os.environ["SSL_CERT_FILE"] == str(bundle)


def test_oauth_token_url_uses_tenant_from_cached_access_token():
    tenant_id = str(uuid.UUID(int=1))

    url = _TeamsAuth._oauth_token_url(
        {"access_token": _jwt_with_claims(tid=tenant_id)}
    )

    assert url == (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    )


def test_oauth_token_url_falls_back_to_cached_graph_token():
    tenant_id = str(uuid.UUID(int=2))

    url = _TeamsAuth._oauth_token_url(
        {"graph_token": _jwt_with_claims(tid=tenant_id)}
    )

    assert tenant_id in url


def test_oauth_client_id_uses_cached_appid_claim():
    client_id = str(uuid.UUID(int=3))

    resolved = _TeamsAuth._oauth_client_id(
        {"access_token": _jwt_with_claims(appid=client_id)}
    )

    assert resolved == client_id


def test_oauth_client_id_accepts_azp_claim_fallback():
    client_id = str(uuid.UUID(int=4))

    resolved = _TeamsAuth._oauth_client_id(
        {"graph_token": _jwt_with_claims(azp=client_id)}
    )

    assert resolved == client_id


@pytest.mark.parametrize(
    "tokens",
    [
        {},
        {"access_token": "not-a-jwt"},
        {"access_token": _jwt_with_claims(tid="not-a-uuid")},
    ],
)
def test_oauth_token_url_rejects_missing_or_invalid_tenant(tokens):
    with pytest.raises(RuntimeError, match="tenant"):
        _TeamsAuth._oauth_token_url(tokens)


def test_oauth_client_id_rejects_missing_application_claim():
    with pytest.raises(RuntimeError, match="client application"):
        _TeamsAuth._oauth_client_id({})


# ── Token cache is written owner-only (0600) ──────────────────────────
# The cache holds long-lived OAuth access + refresh tokens. On a shared
# machine, a world/group-readable cache leaks them to other users.

@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX mode bits only")
def test_save_creates_cache_owner_only(tmp_path, monkeypatch):
    """A freshly created token cache must be 0600, not umask-default 0644."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    auth = _TeamsAuth()
    prev = os.umask(0o022)  # simulate the common world-readable umask
    try:
        auth._save({"skype_token": "s", "refresh_token": "r"})
    finally:
        os.umask(prev)

    mode = stat.S_IMODE(auth.TOKEN_CACHE.stat().st_mode)
    assert mode == 0o600, oct(mode)
    assert list(cache.parent.glob("token_cache.json.tmp.*")) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX mode bits only")
def test_save_rewrite_keeps_owner_only(tmp_path, monkeypatch):
    """Rewriting an existing 0600 cache must not downgrade it to 0644."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    auth = _TeamsAuth()
    auth._save({"skype_token": "s1"})
    assert stat.S_IMODE(auth.TOKEN_CACHE.stat().st_mode) == 0o600

    prev = os.umask(0o022)
    try:
        auth._save({"skype_token": "s2", "refresh_token": "r2"})
    finally:
        os.umask(prev)

    assert stat.S_IMODE(auth.TOKEN_CACHE.stat().st_mode) == 0o600
    assert json.loads(auth.TOKEN_CACHE.read_text())["skype_token"] == "s2"


def test_save_roundtrips_content(tmp_path, monkeypatch):
    """Cross-platform: content survives the secure write (mode check is POSIX)."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    auth = _TeamsAuth()
    auth._save({"skype_token": "s", "refresh_token": "r"})
    assert json.loads(auth.TOKEN_CACHE.read_text()) == {
        "skype_token": "s",
        "refresh_token": "r",
    }


def test_save_secure_create_contract(tmp_path, monkeypatch):
    """All platforms request exclusive owner-only temp-file creation.

    Windows does not expose POSIX permission semantics, so inspect the actual
    ``os.open`` contract there instead of skipping the security assertion.
    """
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    real_open = os.open
    calls = []

    def tracked_open(path, flags, mode=0o777):
        calls.append((path, flags, mode))
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", tracked_open)
    _TeamsAuth()._save({"refresh_token": "secret"})

    assert len(calls) == 1
    temp_path, flags, mode = calls[0]
    assert str(temp_path).startswith(str(cache) + ".tmp.")
    assert flags & os.O_CREAT
    assert flags & os.O_EXCL
    assert flags & os.O_WRONLY
    assert stat.S_IMODE(mode) == 0o600
    assert list(cache.parent.glob("token_cache.json.tmp.*")) == []


def _valid_cached_tokens(**extra):
    tokens = {
        "access_token": _jwt_with_claims(tid=str(uuid.UUID(int=11)), appid=str(uuid.UUID(int=12))),
        "skype_token": "cached-skype",
        "refresh_token": "cached-refresh",
        "saved_at": int(time.time()),
        "expires_in": 3600,
    }
    tokens.update(extra)
    return tokens


def test_refresh_persists_regional_msg_base(tmp_path, monkeypatch):
    """Authz-discovered region survives the next process cold start."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    auth = _TeamsAuth()
    monkeypatch.setattr(auth, "_inject_truststore", lambda: None)

    oauth = MagicMock()
    oauth.json.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    }
    authz = MagicMock()
    authz.json.return_value = {
        "tokens": {"skypeToken": "new-skype"},
        "regionGtms": {"chatService": "https://apac.ng.msg.teams.microsoft.com"},
    }
    with patch("requests.post", side_effect=[oauth, authz]):
        refreshed = auth._refresh(_valid_cached_tokens())

    expected = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    assert auth.msg_base == expected
    assert refreshed["msg_base"] == expected
    assert json.loads(cache.read_text(encoding="utf-8"))["msg_base"] == expected


def test_valid_cache_cold_start_restores_regional_msg_base(tmp_path, monkeypatch):
    """An unexpired cache must hydrate the regional endpoint without network."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    expected = "https://emea.ng.msg.teams.microsoft.com/v1/users/ME"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_valid_cached_tokens(msg_base=expected)), encoding="utf-8")

    auth = _TeamsAuth()
    monkeypatch.setattr(auth, "_inject_truststore", lambda: None)
    with patch("requests.post", side_effect=AssertionError("cache restore must not call authz")):
        assert auth.tokens()["skype_token"] == "cached-skype"
    assert auth.msg_base == expected


def test_legacy_valid_cache_discovers_and_persists_region(tmp_path, monkeypatch):
    """A pre-fix unexpired cache lacking msg_base migrates via one authz call."""
    cache = tmp_path / ".teams-tokens" / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache)
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_valid_cached_tokens()), encoding="utf-8")

    authz = MagicMock()
    authz.json.return_value = {
        "tokens": {"skypeToken": "discovered-skype"},
        "regionGtms": {"chatService": "https://apac.ng.msg.teams.microsoft.com"},
    }
    auth = _TeamsAuth()
    monkeypatch.setattr(auth, "_inject_truststore", lambda: None)
    with patch("requests.post", return_value=authz) as post:
        tokens = auth.tokens()

    expected = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    post.assert_called_once()
    assert tokens["skype_token"] == "discovered-skype"
    assert auth.msg_base == expected
    assert json.loads(cache.read_text(encoding="utf-8"))["msg_base"] == expected
