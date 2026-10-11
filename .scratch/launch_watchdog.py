"""Launch flash_watchdog.py as a truly-detached, windowless, surviving daemon.

Uses DETACHED_PROCESS | CREATE_NO_WINDOW via a pythonw child so it outlives
this terminal call and never flashes a window. Writes a ready-marker file.
"""
import os
import subprocess
import sys

REPO = r"D:\01_Job\Tool\Hermes Agent"
SCRIPT = os.path.join(REPO, ".scratch", "flash_watchdog.py")
LOG = os.path.join(REPO, ".scratch", "flash_watchdog.log")
READY = os.path.join(REPO, ".scratch", "flash_watchdog.ready")

DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000

p = subprocess.Popen(
    [sys.executable.replace("python.exe", "pythonw.exe"), SCRIPT, LOG],
    cwd=REPO,
    creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
    stdout=open(os.devnull, "w"),
    stderr=open(os.devnull, "w"),
    stdin=subprocess.DEVNULL,
    close_fds=True,
)
with open(READY, "w") as f:
    f.write(f"watchdog_pid={p.pid}\n")
print(f"watchdog launched pid={p.pid} log={LOG}")
