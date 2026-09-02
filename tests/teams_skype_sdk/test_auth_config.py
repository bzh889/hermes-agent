"""Security configuration tests for the vendored Teams SDK."""

import importlib
from pathlib import Path


def test_teams_auth_does_not_default_to_an_organization_tenant(monkeypatch):
    monkeypatch.delenv("TEAMS_TENANT_ID", raising=False)

    import teams_skype_sdk.auth as auth

    auth = importlib.reload(auth)

    assert auth.TeamsAuth.TENANT == "organizations"
    assert auth.TeamsAuth.TOKEN_URL == (
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
    )


def test_teams_cache_default_lives_outside_installed_package(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    import teams_skype_sdk.cache as cache_module

    TeamsCache = cache_module.TeamsCache

    cache = TeamsCache(auto_save_delay=0)
    cache.add_member("19:test@thread.v2", "8:orgid:test", "Test User")

    expected = tmp_path / "cache" / "teams_skype_sdk" / "cache.json"
    assert Path(cache.cache_file) == expected
    assert expected.exists()
    assert not (Path(cache_module.__file__).parent / "cache.json").exists()
