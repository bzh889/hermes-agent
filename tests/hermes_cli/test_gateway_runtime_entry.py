"""Behavior tests for the detached gateway runtime entry point."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from hermes_cli import gateway_runtime_entry


def test_main_injects_system_trust_before_importing_gateway(monkeypatch):
    events = []

    monkeypatch.setattr(
        gateway_runtime_entry,
        "restore_venv_identity",
        lambda: events.append("restore-venv"),
    )
    monkeypatch.setitem(
        sys.modules,
        "hermes_bootstrap",
        SimpleNamespace(harden_import_path=lambda: events.append("harden-path")),
    )
    monkeypatch.setitem(
        sys.modules,
        "truststore",
        SimpleNamespace(inject_into_ssl=lambda: events.append("inject-trust")),
    )
    monkeypatch.setitem(
        sys.modules,
        "gateway.run",
        SimpleNamespace(main=lambda: events.append("gateway-main")),
    )

    gateway_runtime_entry.main()

    assert events == [
        "restore-venv",
        "harden-path",
        "inject-trust",
        "gateway-main",
    ]


def test_main_keeps_starting_when_system_trust_injection_is_unavailable(monkeypatch):
    events = []

    monkeypatch.setattr(gateway_runtime_entry, "restore_venv_identity", lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "hermes_bootstrap",
        SimpleNamespace(harden_import_path=lambda: None),
    )

    def fail_to_inject():
        raise RuntimeError("truststore unavailable")

    monkeypatch.setitem(
        sys.modules,
        "truststore",
        SimpleNamespace(inject_into_ssl=fail_to_inject),
    )
    monkeypatch.setitem(
        sys.modules,
        "gateway.run",
        SimpleNamespace(main=lambda: events.append("gateway-main")),
    )

    gateway_runtime_entry.main()

    assert events == ["gateway-main"]
