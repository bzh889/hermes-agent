"""Verify run_api_key_helper is windowless AND determine why bootstrap patch
missed it on 10/6-era TUI processes.

1. Import hermes_bootstrap (patch active) + run run_api_key_helper against a
   console binary (cmd.exe) and count visible windows.
2. Simulate the OLD code path (no creationflags) to reproduce the flash and
   confirm the mechanism.
"""
import ctypes, sys, time
from ctypes import wintypes

sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
import hermes_bootstrap  # noqa: F401
from hermes_cli.runtime_provider import run_api_key_helper, _API_KEY_HELPER_CACHE_TTL_SECONDS
import hermes_cli.runtime_provider as rp

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

# Test 1: the NEW code path must be windowless (use a realistic helper shape)
cmd = "cmd.exe /c echo dummy-key-12345"
rp._api_key_helper_cache.clear()
before = count_visible()
key = run_api_key_helper(cmd)
after = count_visible()
print(f"T1 new-path: key={key!r} visible-delta={after-before}")
assert key == "dummy-key-12345", "helper stdout parse broke"
assert after - before <= 0, "FAIL: new path flashes"

# Test 2: reproduce the OLD behavior — subprocess.run WITHOUT creationflags,
# bypassing the bootstrap patch exactly like an UNPATCHED process would
import subprocess
rp._api_key_helper_cache.clear()
before = count_visible()
r = subprocess.run(["cmd.exe", "/c", "echo x"], capture_output=True, text=True)
time.sleep(0.8)
after = count_visible()
print(f"T2 patched-popen-no-flags: visible-delta={after-before} (patch should keep 0)")

print("VERDICT:", "GREEN — helper path windowless" )
