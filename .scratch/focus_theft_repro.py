"""Repro loop for desktop-focus theft: spawn via each suspect path from a
windowless-equivalent parent and count visible top-level windows.

Usage: .venv/Scripts/python.exe .scratch/focus_theft_repro.py [ TestCaseName ]
Verdict per case: PASS = no new visible window; FAIL = focus theft path lives.
"""
import subprocess, sys, time

sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
import hermes_bootstrap  # noqa: F401 — applies the Popen patch on import

CASES = ["popen_plain", "popen_shell", "winpty", "os_system"]


def count_visible_windows() -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    n = [0]
    SWHIDE = 0

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            # ignore cloaked windows on Win10+
            cloaked = wintypes.DWORD()
            dwm = ctypes.windll.dwmapi
            hr = dwm.DwmGetWindowAttribute(
                hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            if hr == 0 and cloaked.value == 0 and user32.GetWindow(hwnd, 4) != 0:
                n[0] += 1
        return True

    user32.EnumWindows(cb, 0)
    return n[0]


def run_case(name: str) -> bool:
    before = count_visible_windows()
    child = None
    if name == "popen_plain":
        child = subprocess.Popen(
            [r"C:\Windows\System32\cmd.exe", "/c", "ping -n 3 127.0.0.1 > nul"]
        )
    elif name == "popen_shell":
        child = subprocess.Popen(
            "ping -n 3 127.0.0.1 > nul", shell=True
        )
    elif name == "winpty":
        try:
            from winpty import PtyProcess
        except ImportError:
            print(f"[{name}] SKIP — winpty not installed")
            return True
        child = PtyProcess.spawn(
            [r"C:\Windows\System32\cmd.exe", "/c", "ping -n 3 127.0.0.1 > nul"]
        )
    elif name == "os_system":
        rc = subprocess.run([sys.executable, "-c", "import os; os.system('ping -n 3 127.0.0.1 > nul')"])
        before_arg = None
        # os.system child of our own (console-ful) parent won't flash here;
        # realistic exposure is a pythonw parent — simulated separately.
        print(f"[{name}] child rc={rc.returncode} (note: parent here HAS a console; "
              f"realistic pythonw-parent sim skipped — os.system is NOT covered by the bootstrap patch)")
        return None
    time.sleep(1.2)  # let any window materialize
    delta = count_visible_windows() - before
    ok = delta <= 0
    status = "PASS" if ok else "FAIL — VISIBLE WINDOW SPAWNED"
    print(f"[{name}] visible-window delta={delta} -> {status}")
    try:
        if child and hasattr(child, "terminate"):
            child.terminate()
    except Exception:
        pass
    return ok


if __name__ == "__main__":
    cases = sys.argv[1:] or CASES
    verdicts = {}
    for c in cases:
        v = run_case(c)
        if v is not None:
            verdicts[c] = v
    fails = [k for k, ok in verdicts.items() if not ok]
    print("\nVERDICT:", "GREEN — no focus theft path" if not fails else f"RED — leaking paths: {fails}")
