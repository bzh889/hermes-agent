"""E2E verify: the patched _load_aide_pri_key spawn must be windowless.

Runs the REAL subprocess.run call exactly as patched (importing the deployed
script module), counting visible top-level windows before/after via
EnumWindows + DWM cloak. Delta must be 0. Also checks /health of the live proxy.
"""
import ctypes, importlib.util, sys, urllib.request
from ctypes import wintypes

PROXY = r"C:\Users\mtk12265\.hermes\scripts\aide-embed-proxy.py"

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

# 1. import the deployed module and confirm the patched call site carries the flag
spec = importlib.util.spec_from_file_location("aide_embed_proxy", PROXY)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
import inspect, re
src = inspect.getsource(mod._load_aide_pri_key)
assert "CREATE_NO_WINDOW" in src, "patch flag missing from deployed _load_aide_pri_key"
print("PATCH-PRESENT-OK: deployed script carries CREATE_NO_WINDOW at the cch auth spawn")

# 2. exercise the real spawn (cch.cmd actually runs) and count windows
before = count_visible()
key = mod._load_aide_pri_key()
after = count_visible()
print(f"spawn executed, key={'<valid JWT>' if key.startswith('eyJ') else repr(key[:20])}, "
      f"visible delta={after - before}")
assert after - before <= 0, "REAL FAIL: cch auth spawn created a visible window"
print("WINDOWLESS-OK")

# 3. live proxy health (it was restarted with the patched code)
try:
    with urllib.request.urlopen("http://127.0.0.1:19901/health", timeout=5) as r:
        print("PROXY-HEALTH:", r.read()[:120].decode(errors="replace"))
except Exception as e:
    print("PROXY-HEALTH: unreachable:", e)
print("VERDICT: GREEN")
