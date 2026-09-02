"""User-defined provider model discovery for picker inventory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


def _write_config(home: Path, providers: dict) -> None:
    home.mkdir(exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"providers": providers}), encoding="utf-8")


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_always_discover_user_provider_reads_key_from_dotenv(hermes_home):
    """A configured provider can force live discovery on normal picker open.

    ``key_env`` must be resolved through Hermes' .env loader, not only
    ``os.environ``; otherwise a running TUI misses keys rotated in .env.
    """
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    _write_config(
        hermes_home,
        {
            "aide-like": {
                "name": "AIDE Like",
                "base_url": "https://aide.example/v1",
                "key_env": "AIDE_LIKE_KEY",
                "discover_models": True,
                "always_discover_models": True,
                "default_headers": {"x-user-id": "tester"},
                "models": ["static-a"],
            }
        },
    )
    (hermes_home / ".env").write_text("AIDE_LIKE_KEY=dot-env-key\n", encoding="utf-8")

    seen = {}

    def fake_fetch(api_key, base_url, **kwargs):
        seen["api_key"] = api_key
        seen["base_url"] = base_url
        seen["headers"] = kwargs.get("headers")
        return ["live-a", "live-b"]

    with patch("hermes_cli.models.fetch_api_models", side_effect=fake_fetch):
        payload = build_model_options_payload(load_picker_context(), refresh=False)

    row = next(p for p in payload["providers"] if p["slug"] == "aide-like")
    assert row["models"] == ["live-a", "live-b"]
    assert row["total_models"] == 2
    assert seen == {
        "api_key": "dot-env-key",
        "base_url": "https://aide.example/v1",
        "headers": {"x-user-id": "tester"},
    }


def test_always_discover_user_provider_supports_api_key_helper(hermes_home):
    """Dynamic picker discovery must support providers whose token is helper-backed."""
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    _write_config(
        hermes_home,
        {
            "helper-backed": {
                "name": "Helper Backed",
                "base_url": "https://helper.example/v1",
                "api_key_helper": "helper-tool key",
                "discover_models": True,
                "always_discover_models": True,
                "default_headers": {"x-api-key": "${_API_KEY}"},
                "models": ["static-a"],
            }
        },
    )

    seen = {}

    def fake_fetch(api_key, base_url, **kwargs):
        seen["api_key"] = api_key
        seen["base_url"] = base_url
        seen["headers"] = kwargs.get("headers")
        return ["live-helper"]

    with (
        patch("hermes_cli.runtime_provider.run_api_key_helper", return_value="helper-token"),
        patch("hermes_cli.models.fetch_api_models", side_effect=fake_fetch),
    ):
        payload = build_model_options_payload(load_picker_context(), refresh=False)

    row = next(p for p in payload["providers"] if p["slug"] == "helper-backed")
    assert row["models"] == ["live-helper"]
    assert row["total_models"] == 1
    assert seen == {
        "api_key": "helper-token",
        "base_url": "https://helper.example/v1",
        "headers": {"x-api-key": "helper-token"},
    }
