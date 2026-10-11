"""Flash-window watchdog: catches EVERY window-show event live.

Uses SetWinEventHook(EVENT_OBJECT_SHOW) so even zero-lasting console flashes
are captured (polling would miss them). Each event logs:
  timestamp | hwnd | owner PID | process name | window class | title

Filter: skip existing baseline windows (first 3s quiet period), then log all
new shows. Write to the log file passed as argv[1]; flush per line.

Run: python flash_watchdog.py <logfile>   (kill to stop)
"""
import ctypes
import datetime
import os
import sys
import time
from ctypes import wintypes

LOG = sys.argv[1] if len(sys.argv) > 1 else "flash_watchdog.log"
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32

EVENT_OBJECT_SHOW = 0x8002
WINEVENT_OUTOFCONTEXT = 0x0000
OBJID_WINDOW = 0x00000000

seen_hwnds = set()
started = time.time()

@ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
def on_event(hook, event, hwnd, id_object, id_child, thread, time_ms):
    if id_object != OBJID_WINDOW:
        return
    if time.time() - started < 3.0:  # baseline quiet period
        return
    if not user32.IsWindowVisible(hwnd):
        return
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    # process name
    h = kernel32.OpenProcess(0x0410, False, pid.value)  # QUERY_LIMITED_INFORMATION
    name = "?"
    if h:
        buf = ctypes.create_unicode_buffer(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(wintypes.DWORD(512))):
            name = os.path.basename(buf.value)
        kernel32.CloseHandle(h)
    # class + title
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    ttl = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, ttl, 512)
    line = "{}|hwnd={:x}|pid={}|{}|class={}|title={}".format(
        datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
        hwnd & 0xFFFFFFFF, pid.value, name, cls.value, ttl.value[:80])
    # Ancestry captured LIVE at show-time (parents die fast; post-hoc is too late)
    if cls.value in ("PseudoConsoleWindow", "ConsoleWindowClass") or name.lower() in (
            "cmd.exe", "bash.exe", "conhost.exe", "coding-cli-helper.exe", "pwsh.exe", "powershell.exe"):
        cur = pid.value
        chain = []
        for _ in range(10):
            h2 = kernel32.OpenProcess(0x0410, False, cur)
            if not h2:
                chain.append(f"{cur}(gone)")
                break
            ppid = wintypes.DWORD()
            # NtQueryInformationProcess-free approach: use Windows API via toolhelp snapshot is heavy;
            # reuse GetWindowThreadProcessId won't work for non-windows. Fall back: read via WMI-less? Not available.
            # Simplest reliable: use kernel32.CreateToolhelp32Snapshot lazily below in _ancestry().
            kernel32.CloseHandle(h2)
            break
        line += "|chain=" + _ancestry(pid.value, kernel32)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _ancestry(pid, kernel32):
    """Walk parent chain via Toolhelp32 snapshot (PID + PPID pairs)."""
    TH32CS_SNAPPROCESS = 0x00000002
    class PROCENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1 or snap == 0xFFFFFFFFFFFFFFFF:
        return "snapshot-failed"
    table = {}
    e = PROCENTRY32()
    e.dwSize = ctypes.sizeof(PROCENTRY32)
    ok = kernel32.Process32First(snap, ctypes.byref(e))
    while ok:
        table[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile.decode("mbcs", "replace"))
        ok = kernel32.Process32Next(snap, ctypes.byref(e))
    kernel32.CloseHandle(snap)
    chain, cur, seen = [], pid, set()
    while cur in table and cur not in seen:
        seen.add(cur)
        ppid, exe = table[cur]
        chain.append(f"{exe}({cur})")
        cur = ppid
    if cur not in table:
        chain.append(f"?({cur})")
    return " <- ".join(chain)

ole32.CoInitialize(None)
hook = user32.SetWinEventHook(
    EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0, on_event,
    0, 0, WINEVENT_OUTOFCONTEXT)
if not hook:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("FATAL: SetWinEventHook failed\n")
    sys.exit(1)

msg = wintypes.MSG()
with open(LOG, "a", encoding="utf-8") as f:
    f.write("=== watchdog armed {} ===\n".format(datetime.datetime.now()))
while True:
    if user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) <= 0:
        break
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))
