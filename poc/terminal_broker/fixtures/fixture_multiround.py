"""Multi-round deterministic shell fixture for handoff tests.

Like ``fixture_echo`` but loops multiple rounds so mode-switch tests can
verify the same child process survives across several read/write cycles.

Protocol (unbuffered, line-oriented):

1. Emits ``START_MARKER:<pid>`` immediately.
2. For each round N (0-based):
   a. Reads one line from stdin.
   b. Echoes ``ROUND:<N>:<pid>:<input>`` — includes the fixture's own PID
      on every round so tests can verify process continuity across mode
      switches.
3. When the input is ``QUIT``, emits ``EXIT_MARKER:0`` and exits.

Usage as argv:
    [sys.executable, "-u", "-c", FIXTURE_SCRIPT]
"""

import sys

FIXTURE_SCRIPT = r"""
import sys, os
_pid = str(os.getpid())
sys.stdout.write('START_MARKER:' + _pid + '\n')
sys.stdout.flush()
_round = 0
while True:
    _line = sys.stdin.readline()
    if not _line:
        break
    _line = _line.strip()
    if not _line:
        continue
    if _line == 'QUIT':
        sys.stdout.write('EXIT_MARKER:0\n')
        sys.stdout.flush()
        break
    sys.stdout.write('ROUND:' + str(_round) + ':' + _pid + ':' + _line + '\n')
    sys.stdout.flush()
    _round += 1
"""


def fixture_argv() -> list[str]:
    """Return the argv list to spawn this fixture with the current Python."""
    return [sys.executable, "-u", "-c", FIXTURE_SCRIPT]
