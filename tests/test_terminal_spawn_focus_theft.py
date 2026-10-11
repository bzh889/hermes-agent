"""Focus-theft regression: terminal spawn paths must not create visible windows.

Covers the paths the agent's terminal tool actually uses on Windows, beyond
the plain-Popen guarantee in test_windowless_subprocess_bootstrap.py:

- popen_shell       — shell=True spawns (cmd /c shims)
- winpty            — PTY background sessions (tools/process_registry.py spawn
                     path); pywinpty calls CreateProcess directly, bypassing the
                     Popen patch, but ConPTY/agent must not turn into a visible
                      window under the user's terminal setting

Each case counts visible top-level windows (EnumWindows + DWM cloaked filter)
before/after the spawn. Delta must be 0. Windows-only; skips if winpty missing.
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows-only focus-theft regression")


def _count_visible_windows() -> int:
    user32 = ctypes.windll.user32
    n = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        cloaked = wintypes.DWORD()
        # DWMWA_CLOAKED = 14
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        # count only real, un-cloaked top-level windows (owner check filters
        # transient helper windows)
        if hr == 0 and cloaked.value == 0 and user32.GetWindow(hwnd, 4) != 0:
            n[0] += 1
        return True

    user32.EnumWindows(cb, 0)
    return n[0]


def _spawn_and_count(spawner) -> int:
    before = _count_visible_windows()
    child = spawner()
    time.sleep(1.0)  # let any window materialize
    delta = _count_visible_windows() - before
    try:
        if hasattr(child, "terminate"):
            child.terminate()
        elif hasattr(child, "kill"):
            child.kill()
    except Exception:
        pass
    return delta


def _cmd():
    return [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"),
            "/c", "ping -n 3 127.0.0.1 > nul"]


def test_popen_shell_true_spawns_no_visible_window():
    import hermes_bootstrap  # noqa: F401 — ensure patch is live in this process
    delta = _spawn_and_count(lambda: subprocess.Popen("ping -n 3 127.0.0.1 > nul", shell=True))
    assert delta <= 0, "shell=True child created a visible console window"


def test_winpty_spawn_no_visible_window():
    pytest.importorskip("winpty")
    import hermes_bootstrap  # noqa: F401

    from winpty import PtyProcess
    delta = _spawn_and_count(lambda: PtyProcess.spawn(_cmd()))
    assert delta <= 0, "winpty PTY session created a visible console window"
