"""Control: WITHOUT the preamble the same sandbox shape MUST flash.

Runs the identical scenario minus the preamble to prove the preamble is the
load-bearing element (and that the E2E loop can go red on the actual bug).
"""
import ctypes, os, subprocess, sys, tempfile, time
from ctypes import wintypes

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

# NO preamble — the pre-fix state, from a pythonw (windowless) parent chain
PARENT = r"""
import subprocess
r = subprocess.run(["cmd.exe", "/c", "ping -n 2 127.0.0.1 > nul"], capture_output=True)
"""
with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "script.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(PARENT)
    env = {"SYSTEMROOT": os.environ["SYSTEMROOT"], "PATH": os.environ["PATH"],
           "PYTHONIOENCODING": "utf-8"}
    # windowless pythonw parent, NO CREATE_NO_WINDOW on the grandchild path
    proc = subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), script],
                            creationflags=0x08000000 | 0x00000008, env=env)
    time.sleep(1.5)
    # note: this control's pythonw child spawns cmd.exe bare — the flash is
    # EXPECTED; we only verify the loop's sensitivity by it.
    d = count_visible()
    proc.wait(timeout=30)
print("control visible count during bare spawn:", d)
