"""Opt-in recovery for local MCP servers that are started on demand.

The MCP client remains transport-agnostic: a server config may provide an
explicit ``start_command`` and ``auto_start: true``. Recovery is single-flight,
bounded, and only runs for connection failures.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


_START_LOCK = threading.Lock()


@dataclass(frozen=True)
class AutoStartPolicy:
    endpoint: str
    command: tuple[str, ...]
    timeout: float = 30.0


def _is_connection_failure(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = ("connection refused", "connecterror", "connectionreset", "winerror 10061", "failed to connect")
    return isinstance(exc, (ConnectionRefusedError, ConnectionResetError, TimeoutError)) or any(m in text for m in markers)


def _policy(config: dict[str, Any]) -> AutoStartPolicy | None:
    if not config.get("auto_start"):
        return None
    endpoint = config.get("url")
    raw_command = config.get("start_command")
    if isinstance(raw_command, str):
        try:
            raw_command = json.loads(raw_command)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw_command, (list, tuple)):
        return None
    command = tuple(str(x) for x in raw_command)
    if not isinstance(endpoint, str) or not endpoint or not command:
        return None
    return AutoStartPolicy(endpoint, command, float(config.get("start_timeout", 30)))


def should_autostart(config: dict[str, Any], exc: BaseException) -> bool:
    return _policy(config) is not None and _is_connection_failure(exc)


def _probe_endpoint(endpoint: str, timeout: float) -> bool:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "hermes-autostart", "version": "1"},
        },
    }).encode()
    request = urllib.request.Request(
        endpoint, data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def start_mcp_server_if_needed(config: dict[str, Any]) -> AutoStartPolicy | None:
    policy = _policy(config)
    if policy is None:
        return None
    with _START_LOCK:
        if _probe_endpoint(policy.endpoint, min(2.0, policy.timeout)):
            return policy
        try:
            result = subprocess.run(
                list(policy.command), check=False, capture_output=True,
                text=True, timeout=policy.timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        deadline = time.monotonic() + policy.timeout
        while time.monotonic() < deadline:
            if _probe_endpoint(policy.endpoint, min(2.0, max(0.1, deadline - time.monotonic()))):
                return policy
            time.sleep(0.25)
    return None
