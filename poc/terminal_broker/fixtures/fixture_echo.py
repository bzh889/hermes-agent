"""Deterministic shell fixture for the Terminal Session Broker POC.

A Python one-liner designed to run under ConPTY with deterministic output:

1. Emits ``START_MARKER:<pid>`` immediately (unbuffered).
2. Reads one line from stdin.
3. Echoes it back as ``RESP:<input>``.
4. Emits ``EXIT_MARKER:0`` and exits.

We use Python (``-u`` for unbuffered) rather than PowerShell because
PowerShell's ConPTY output buffering can delay markers past read timeouts
in the test harness. Python with ``-u`` flushes immediately.

Usage as argv:
    [sys.executable, "-u", "-c", FIXTURE_SCRIPT]
"""

import os
import sys

FIXTURE_SCRIPT = (
    "import sys,os;"
    "sys.stdout.write('START_MARKER:'+str(os.getpid())+'\\n');"
    "sys.stdout.flush();"
    "line=sys.stdin.readline().strip();"
    "sys.stdout.write('RESP:'+line+'\\n');"
    "sys.stdout.flush();"
    "sys.stdout.write('EXIT_MARKER:0\\n');"
    "sys.stdout.flush()"
)


def fixture_argv() -> list[str]:
    """Return the argv list to spawn this fixture with the current Python."""
    return [sys.executable, "-u", "-c", FIXTURE_SCRIPT]
