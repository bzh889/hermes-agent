"""E2E: plain python scripts spawned via the terminal tool must be windowless.

Chain under test (the exact 17:45:59 watchdog shape):
  Hermes TUI -> bash -> python script.py -> subprocess cmd.exe  [flash?]

Uses the REAL _sanitized env (with the new sitecustomize injection) for the
python script child. Delta of visible windows must be 0.
"""
import ctypes, os, subprocess, sys, tempfile, time
from ctypes import wintypes

sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
from tools.environments.local import _sanitize_subprocess_env

def count_visible():
    user32 = ctypes.windll.user32
    n = [0]
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            c = wintypes.DWORD()
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(c), ctypes.sizeof(c)) == 0:
                if c.value == 0 and user32.GetWindow(h, 4) != 0:
                    n[0] += 1
        return True
    user32.EnumWindows(cb, 0)
    return n[0]

SCRIPT = r"""
import subprocess
r = subprocess.run(["cmd.exe", "/c", "ping -n 2 127.0.0.1 > nul"], capture_output=True)
print("patched:", getattr(subprocess.Popen, "_hermes_windowless", False))
print("rc:", r.returncode)
"""

env = _sanitize_subprocess_env(dict(os.environ))
assert "windowless-site" in env.get("PYTHONPATH", ""), f"PYTHONPATH not injected: {env.get('PYTHONPATH')[:120]}"
print("sitecustomize dir on PYTHONPATH:", [p for p in env["PYTHONPATH"].split(os.pathsep) if "windowless-site" in p])

with tempfile.TemporaryDirectory() as td:
    sp = os.path.join(td, "child.py")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    before = count_visible()
    out = subprocess.run([sys.executable, sp], capture_output=True, text=True,
                         timeout=60, env=env,
                         creationflags=0x08000000)
    time.sleep(0.8)
    after = count_visible()

print("child stdout:", out.stdout.strip())
print("visible delta:", after - before)
assert "patched: True" in out.stdout, "sitecustomize not armed inside plain python child"
assert after - before <= 0, "FAIL: plain-python child flashed a window"
print("VERDICT: GREEN — layer-5 plain-python spawns are windowless")
