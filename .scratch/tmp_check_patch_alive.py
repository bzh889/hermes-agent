"""Check whether a running python process has the windowless Popen patch live.

Uses EnumWindows + DWM cloak to see if a spawn from a target process creates
a visible window. Non-invasive; diagnostic only.

Usage: python tmp_check_patch_alive.py <pid>
"""
import ctypes, subprocess, sys, time, os
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

if __name__ == "__main__":
    print("baseline visible:", count_visible())
    time.sleep(2)
    print("after 2s:", count_visible())
