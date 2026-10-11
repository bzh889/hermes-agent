"""E2E: sandbox child must spawn console subprocesses windowlessly.

Simulates the real execute_code flow: generate script.py WITH the new
preamble (as tools/code_execution_tool.py now writes it), run it in a
scrubbed env from a pythonw-style windowless parent-equivalent context, and
count visible windows while the sandboxed script spawns cmd.exe.
"""
import ctypes, os, subprocess, sys, tempfile, time
from ctypes import wintypes

sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
from tools.code_execution_tool import _SANDBOX_WINDOWLESS_PREAMBLE

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

USER_CODE = r"""
import subprocess, time
r = subprocess.run(["cmd.exe", "/c", "ping -n 2 127.0.0.1 > nul"], capture_output=True)
print("sandbox child rc:", r.returncode)
"""

with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "script.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_SANDBOX_WINDOWLESS_PREAMBLE)   # exactly what the patched tool writes
        f.write(USER_CODE)
    env = {"SYSTEMROOT": os.environ["SYSTEMROOT"], "PATH": os.environ["PATH"],
           "PYTHONIOENCODING": "utf-8"}
    before = count_visible()
    out = subprocess.run([sys.executable.replace("python.exe", "pythonw.exe"), script],
                         capture_output=True, text=True, timeout=60,
                         creationflags=0x08000000,  # parent side windowless like TUI
                         env=env)
    time.sleep(0.8)
    after = count_visible()

print("sandbox stdout:", out.stdout.strip())
print("visible-window delta:", after - before)
assert "sandbox child rc: 0" in out.stdout, f"sandbox script failed: {out.stderr[:300]}"
assert after - before <= 0, "FAIL: sandbox child spawned a VISIBLE window"
print("VERDICT: GREEN — sandboxed spawns are windowless")
