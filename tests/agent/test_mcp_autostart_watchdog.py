from __future__ import annotations

import subprocess

from tools.mcp_autostart_watchdog import AutoStartPolicy, should_autostart, start_mcp_server_if_needed


def test_autostart_is_opt_in_and_only_for_connection_failures():
    cfg: dict = {"url": "http://127.0.0.1:19950/mcp"}
    assert should_autostart(cfg, ConnectionRefusedError("down")) is False
    cfg["auto_start"] = True
    assert should_autostart(cfg, ConnectionRefusedError("down")) is False
    cfg["start_command"] = ["mydc", "mcp-start"]
    assert should_autostart(cfg, ConnectionRefusedError("down")) is True
    assert should_autostart(cfg, ValueError("bad config")) is False


def test_start_is_single_flight_and_health_checked(monkeypatch):
    calls: list[tuple[str, ...]] = []
    health_calls: list[str] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="OK", stderr="")

    def fake_health(endpoint, timeout):
        health_calls.append(endpoint)
        return len(health_calls) > 1

    monkeypatch.setattr("tools.mcp_autostart_watchdog.subprocess.run", fake_run)
    monkeypatch.setattr("tools.mcp_autostart_watchdog._probe_endpoint", fake_health)
    cfg = {"url": "http://127.0.0.1:19950/mcp", "auto_start": True,
           "start_command": ["mydc", "mcp-start"], "start_timeout": 2}
    policy = start_mcp_server_if_needed(cfg)
    assert isinstance(policy, AutoStartPolicy)
    assert calls == [("mydc", "mcp-start")]
    assert health_calls == ["http://127.0.0.1:19950/mcp"] * 2


def test_start_command_accepts_config_cli_json_string(monkeypatch):
    monkeypatch.setattr("tools.mcp_autostart_watchdog._probe_endpoint", lambda endpoint, timeout: True)
    cfg = {"url": "http://127.0.0.1:19950/mcp", "auto_start": True,
           "start_command": '["mydc", "mcp-start"]'}
    assert isinstance(start_mcp_server_if_needed(cfg), AutoStartPolicy)


def test_start_failure_has_safe_diagnostic(monkeypatch):
    monkeypatch.setattr("tools.mcp_autostart_watchdog.subprocess.run", lambda *a, **k: (_ for _ in ()).throw(OSError("not found")))
    monkeypatch.setattr("tools.mcp_autostart_watchdog._probe_endpoint", lambda endpoint, timeout: False)
    cfg = {"url": "http://127.0.0.1:19950/mcp", "auto_start": True,
           "start_command": ["missing-mydc", "mcp-start"]}
    assert start_mcp_server_if_needed(cfg) is None
