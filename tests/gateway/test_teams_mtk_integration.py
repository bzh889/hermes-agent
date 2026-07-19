"""Integration contracts for the TeamsMTK platform wiring."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import yaml


def test_gateway_factory_creates_teams_mtk_adapter(monkeypatch, tmp_path):
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.teams_mtk import TeamsMTKAdapter
    from gateway.run import GatewayRunner

    token_cache = tmp_path / ".teams-tokens" / "token_cache.json"
    token_cache.parent.mkdir(parents=True)
    token_cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("MTK_TEAMS_CONVERSATION_ID", raising=False)
    runner = object.__new__(GatewayRunner)
    runner.config = SimpleNamespace(
        group_sessions_per_user=False,
        thread_sessions_per_user=False,
    )

    platform_config = PlatformConfig(
        enabled=True,
        extra={"conversation_ids": ["19:example@thread.v2"]},
    )
    adapter = runner._create_adapter(Platform.TEAMS_MTK, platform_config)

    assert isinstance(adapter, TeamsMTKAdapter)
    assert adapter._conv_ids == ["19:example@thread.v2"]


def test_setup_catalog_includes_teams_mtk():
    from hermes_cli.gateway import _all_platforms

    entries = {entry["key"]: entry for entry in _all_platforms()}

    conversation_var = entries["teams_mtk"]["vars"][0]
    assert conversation_var["config_field"] == "conversation_ids"


def test_setup_persists_teams_conversations_in_config(monkeypatch):
    from hermes_cli import gateway as gateway_cli

    platform = next(
        entry
        for entry in gateway_cli._all_platforms()
        if entry["key"] == "teams_mtk"
    )
    answers = iter(["19:first@thread.v2,19:second@thread.v2", ""])
    writes = []
    monkeypatch.setattr(gateway_cli, "read_raw_config", lambda: {})
    monkeypatch.setattr(gateway_cli, "get_env_value", lambda _name: None)
    monkeypatch.setattr(gateway_cli, "prompt", lambda *_a, **_kw: next(answers))
    monkeypatch.setattr(
        gateway_cli,
        "write_platform_config_field",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )
    monkeypatch.setattr(
        gateway_cli,
        "save_env_value",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("Teams routing config must not be written to .env")
        ),
    )

    gateway_cli._setup_standard_platform(platform)

    assert (
        (
            "teams_mtk",
            "conversation_ids",
            ["19:first@thread.v2", "19:second@thread.v2"],
        ),
        {"raw": True},
    ) in writes
    assert (("teams_mtk", "enabled", True), {"raw": True}) in writes


def test_cron_teams_mtk_home_uses_first_configured_conversation(monkeypatch):
    from gateway.config import Platform, PlatformConfig
    from cron.scheduler import _get_home_target_chat_id, _KNOWN_DELIVERY_PLATFORMS

    monkeypatch.delenv("MTK_TEAMS_CONVERSATION_ID", raising=False)
    config = SimpleNamespace(
        platforms={
            Platform.TEAMS_MTK: PlatformConfig(
                enabled=True,
                extra={
                    "conversation_ids": [
                        "19:first@thread.v2",
                        "19:second@thread.v2",
                    ]
                },
            )
        }
    )
    monkeypatch.setattr("gateway.config.load_gateway_config", lambda: config)

    assert "teams_mtk" in _KNOWN_DELIVERY_PLATFORMS
    assert _get_home_target_chat_id("teams_mtk") == "19:first@thread.v2"


def test_standalone_send_cold_start_loads_teams_registry_entry(tmp_path):
    """A cron-only cold process executes the real regional standalone sender."""
    script = textwrap.dedent(
        """
        import asyncio
        import json
        import sys
        import types
        from pathlib import Path

        import requests

        sys.modules["gateway.run"] = types.SimpleNamespace(
            _gateway_runner_ref=lambda: None,
        )

        calls = []

        class Response:
            def __init__(self, payload, status=201):
                self._payload = payload
                self.status_code = status
                self.text = json.dumps(payload)

            def json(self):
                return self._payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"HTTP {self.status_code}")

        def authz_post(url, **kwargs):
            calls.append(("AUTHZ", url, kwargs.get("headers", {})))
            assert url == "https://authsvc.teams.microsoft.com/v1.0/authz"
            return Response({
                "tokens": {"skypeToken": "regional-skype"},
                "regionGtms": {
                    "chatService": "https://apac.ng.msg.teams.microsoft.com"
                },
            })

        class Session:
            def mount(self, *args, **kwargs):
                pass

            def request(self, method, url, **kwargs):
                calls.append((method, url, kwargs.get("headers", {})))
                return Response({"OriginalArrivalTime": "cold-start-message"})

            def post(self, url, **kwargs):
                return self.request("POST", url, **kwargs)

            def close(self):
                pass

        requests.post = authz_post
        requests.Session = Session

        from gateway.config import Platform, PlatformConfig
        from tools.send_message_tool import _send_via_adapter

        assert "gateway.platforms.teams_mtk" not in sys.modules
        result = asyncio.run(
            _send_via_adapter(
                Platform.TEAMS_MTK,
                PlatformConfig(enabled=True),
                "19:example@thread.v2",
                "cold-start probe",
            )
        )
        assert "gateway.platforms.teams_mtk" in sys.modules
        assert result == {
            "success": True,
            "platform": "teams_mtk",
            "chat_id": "19:example@thread.v2",
            "message_id": "cold-start-message",
        }
        sends = [call for call in calls if "/messages" in call[1]]
        assert len(sends) == 1, calls
        method, url, headers = sends[0]
        assert method == "POST"
        assert url.startswith("https://apac.ng.msg.teams.microsoft.com/")
        assert "https://amer.ng.msg.teams.microsoft.com/" not in url
        assert headers["Authentication"] == "skypetoken=regional-skype"
        cache = json.loads(
            (Path.home() / ".teams-tokens" / "token_cache.json").read_text()
        )
        assert cache["msg_base"] == (
            "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
        )
        """
    )
    isolated_home = str(tmp_path)
    token_dir = tmp_path / ".teams-tokens"
    token_dir.mkdir()
    (token_dir / "token_cache.json").write_text(
        json.dumps({
            "access_token": "cached-access",
            "skype_token": "cached-skype",
            "refresh_token": "cached-refresh",
            "saved_at": int(time.time()),
            "expires_in": 3600,
        }),
        encoding="utf-8",
    )
    env = {
        key: os.environ[key]
        for key in (
            "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
            "TEMP", "TMP", "TMPDIR",
        )
        if key in os.environ
    }
    env.update({
        "HOME": isolated_home,
        "USERPROFILE": isolated_home,
        "LOCALAPPDATA": isolated_home,
        "APPDATA": isolated_home,
        "HERMES_HOME": str(tmp_path / ".hermes"),
        "PYTHONIOENCODING": "utf-8",
    })

    from hermes_cli._subprocess_compat import windows_hidden_console_popen_kwargs
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        **windows_hidden_console_popen_kwargs(),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_gateway_config_bridges_teams_conversation_ids(tmp_path, monkeypatch):
    from gateway.config import Platform, load_gateway_config

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "platforms": {
                    "teams_mtk": {
                        "enabled": True,
                        "conversation_ids": ["19:example@thread.v2"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("MTK_TEAMS_CONVERSATION_ID", raising=False)

    config = load_gateway_config()

    assert config.platforms[Platform.TEAMS_MTK].extra["conversation_ids"] == [
        "19:example@thread.v2"
    ]


def test_status_detects_configured_teams_conversations(tmp_path, monkeypatch):
    from hermes_cli import status

    token_cache = tmp_path / ".teams-tokens" / "token_cache.json"
    token_cache.parent.mkdir(parents=True)
    token_cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("MTK_TEAMS_CONVERSATION_ID", raising=False)
    monkeypatch.setattr(
        status,
        "load_config",
        lambda: {
            "platforms": {
                "teams_mtk": {
                    "conversation_ids": ["19:example@thread.v2"],
                }
            }
        },
    )

    configured, detail = status._check_teams_mtk()

    assert configured is True
    assert "1 conversation" in detail


def test_adapter_keeps_legacy_conversation_env_fallback(monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    monkeypatch.setenv("MTK_TEAMS_CONVERSATION_ID", "19:example@thread.v2")

    adapter = TeamsMTKAdapter(PlatformConfig(enabled=True))

    assert adapter._conv_ids == ["19:example@thread.v2"]
