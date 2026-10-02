"""Windowless-subprocess bootstrap guarantee (2026-10-02 focus-theft fix).

The owner's desktop must never receive visible console windows from Hermes
TUI or any gateway/worker process. enforce_windowless_subprocess() patches
subprocess.Popen at the single shared entry point (hermes_bootstrap) so every
spawn gets CREATE_NO_WINDOW unless it explicitly asks for a console.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _reload_bootstrap(monkeypatch):
    import importlib
    import hermes_bootstrap
    monkeypatch.delenv("HERMES_ALLOW_CONSOLE_WINDOWS", raising=False)
    return importlib.reload(hermes_bootstrap)


def test_windowless_default_adds_create_no_window(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only subprocess flag behaviour")
    bs = _reload_bootstrap(monkeypatch)
    captured = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["flags"] = kwargs.get("creationflags", 0)

    orig = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    # re-apply the patch against the fake
    bs.enforce_windowless_subprocess()
    # the patch binds through subprocess.Popen at call time
    subprocess.Popen("cmd /c exit 0", creationflags=None)
    assert captured["flags"] & 0x08000000, "CREATE_NO_WINDOW must be injected"


def test_windowless_respects_explicit_console_flags(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only subprocess flag behaviour")
    bs = _reload_bootstrap(monkeypatch)
    captured = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["flags"] = kwargs.get("creationflags", 0)

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    bs.enforce_windowless_subprocess()
    subprocess.Popen("cmd /c exit 0", creationflags=subprocess.CREATE_NEW_CONSOLE)
    assert captured["flags"] & subprocess.CREATE_NEW_CONSOLE
    assert not captured["flags"] & 0x08000000, "explicit console must NOT be overridden"


def test_windowless_escape_hatch_env(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-only subprocess flag behaviour")
    import importlib
    import hermes_bootstrap
    monkeypatch.setenv("HERMES_ALLOW_CONSOLE_WINDOWS", "1")
    importlib.reload(hermes_bootstrap)
    # escape hatch: Popen NOT patched
    assert not getattr(subprocess.Popen, "_hermes_windowless", False)
    monkeypatch.delenv("HERMES_ALLOW_CONSOLE_WINDOWS", raising=False)
    importlib.reload(hermes_bootstrap)
    assert getattr(subprocess.Popen, "_hermes_windowless", False) or os.name != "nt"


def test_windowless_real_spawn_completes(monkeypatch):
    """The patched Popen must still run a real child (regression: flag
    bookkeeping must never break actual spawns)."""
    bs = _reload_bootstrap(monkeypatch)
    out = subprocess.run(
        [sys.executable, "-c", "print('ok')"],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0 and "ok" in out.stdout
