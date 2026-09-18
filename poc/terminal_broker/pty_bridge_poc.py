"""POC Terminal Session Broker — PTY Bridge Seam.

Windows-only throwaway POC for the Teams Terminal Remote Control spec.
This module exercises the *broker-owned* PTY lifecycle through a narrow
public contract: spawn, read, write, resize, status, close.

It wraps pywinpty (already a declared dependency) and adds the POC-specific
requirements from ticket 01:

* Explicit diagnostic when pywinpty / ConPTY is missing or unusable, so the
  POC never silently reports pipe mode as PTY success.
* No foreground window is created or raised — pywinpty spawns ConPTY sessions
  without a visible window by default, and we verify this in tests.
* Deterministic shell fixture support via ``fixture_echo.ps1``.

This is NOT production code and must NOT modify the production Teams adapter
or production gateway routing. It lives under ``poc/`` for that reason.

Key design decisions (from spec §Implementation Decisions):
  - Decision 2: The broker creates the PTY *before* starting the child process
    and retains ownership of the I/O boundary for the lifetime of the session.
  - Decision 7: Input is serialized through one broker-owned writer; concurrent
    writes that can interleave bytes are rejected.
  - Decision 8: Output is read once from the PTY and assigned a monotonic
    sequence/cursor before any fan-out.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional, Sequence

try:
    from winpty import PtyProcess  # type: ignore
    _PTY_AVAILABLE = sys.platform.startswith("win")
except ImportError:
    PtyProcess = None  # type: ignore
    _PTY_AVAILABLE = False


__all__ = [
    "PtyBridgePOC",
    "PtyUnavailableError",
    "SessionState",
]


# --- dimension clamping (parity with hermes_cli.win_pty_bridge) ------------

_MIN_DIMENSION = 1
_MAX_COLS = 2000
_MAX_ROWS = 1000


def _clamp(value: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return _MIN_DIMENSION
    if n < _MIN_DIMENSION:
        return _MIN_DIMENSION
    if n > maximum:
        return maximum
    return n


class PtyUnavailableError(RuntimeError):
    """Raised when a Windows PTY / ConPTY session cannot be created.

    This is an *explicit diagnostic*: the POC must not silently fall back
    to pipe mode and report it as PTY success (spec ticket 01, checkbox 6).
    """


class SessionState:
    """Snapshot of a session's lifecycle state (spec Decision 5).

    Fields are intentionally narrow — no raw credentials or secrets.

    Ticket 02 additions (backward-compatible defaults):
      * ``control_mode`` — ``"local"`` or ``"remote"`` (default ``"local"``).
      * ``uptime`` — seconds since session creation (default ``0.0``).
      * ``last_output`` — a short tail of the most recent output (default ``""``).
    """

    def __init__(
        self,
        *,
        session_id: str,
        pid: int,
        running: bool,
        cols: int,
        rows: int,
        cwd: str,
        output_cursor: int,
        control_mode: str = "local",
        uptime: float = 0.0,
        last_output: str = "",
    ) -> None:
        self.session_id = session_id
        self.pid = pid
        self.running = running
        self.cols = cols
        self.rows = rows
        self.cwd = cwd
        self.output_cursor = output_cursor
        self.control_mode = control_mode
        self.uptime = uptime
        self.last_output = last_output

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "pid": self.pid,
            "running": self.running,
            "cols": self.cols,
            "rows": self.rows,
            "cwd": self.cwd,
            "output_cursor": self.output_cursor,
            "control_mode": self.control_mode,
            "uptime": self.uptime,
            "last_output": self.last_output,
        }

    def __repr__(self) -> str:
        return (
            f"SessionState(session_id={self.session_id!r}, pid={self.pid}, "
            f"running={self.running}, cols={self.cols}, rows={self.rows}, "
            f"cwd={self.cwd!r}, output_cursor={self.output_cursor}, "
            f"control_mode={self.control_mode!r}, uptime={self.uptime:.1f}, "
            f"last_output={self.last_output!r})"
        )


class PtyBridgePOC:
    """Broker-owned Windows ConPTY session wrapper.

    Same pywinpty backend as ``hermes_cli.win_pty_bridge.WinPtyBridge``,
    with the additional POC contract:
      * Explict ``PtyUnavailableError`` diagnostic — no silent pipe fallback.
      * Monotonic output cursor (spec Decision 8).
      * Serialized writer (spec Decision 7): a lock guards ``write`` so
        concurrent callers can't interleave bytes.
      * ``status()`` returning a ``SessionState`` snapshot.
    """

    def __init__(self, proc: "PtyProcess", *, session_id: str, cwd: str, cols: int, rows: int) -> None:
        self._proc = proc
        self._session_id = session_id
        self._cwd = cwd
        self._cols = cols
        self._rows = rows
        self._closed = False
        self._output_cursor = 0
        self._write_lock = threading.Lock()
        self._start_time = time.monotonic()
        self._control_mode = "local"
        self._last_output = ""

    # -- lifecycle --------------------------------------------------------

    @classmethod
    def is_available(cls) -> bool:
        """True if pywinpty + ConPTY can be used on this platform."""
        return bool(_PTY_AVAILABLE)

    @classmethod
    def spawn(
        cls,
        argv: Sequence[str],
        *,
        session_id: str = "default",
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        cols: int = 80,
        rows: int = 24,
    ) -> "PtyBridgePOC":
        """Spawn ``argv`` behind a new Windows ConPTY session.

        Raises ``PtyUnavailableError`` with an explicit diagnostic if
        pywinpty is missing or the platform is not Windows. This is the
        gate that prevents silent pipe fallback (ticket 01, checkbox 6).
        """
        if not _PTY_AVAILABLE:
            if PtyProcess is None:
                raise PtyUnavailableError(
                    "pywinpty is not installed — ConPTY is required for the POC. "
                    "Install with: pip install pywinpty"
                )
            raise PtyUnavailableError(
                "ConPTY is unavailable on this platform — the POC requires Windows."
            )

        spawn_env = os.environ.copy() if env is None else dict(env)
        if not spawn_env.get("TERM"):
            spawn_env["TERM"] = "xterm-256color"

        try:
            proc = PtyProcess.spawn(
                list(argv),
                cwd=cwd,
                env=spawn_env,
                dimensions=(rows, cols),
            )
        except Exception as exc:
            raise PtyUnavailableError(
                f"ConPTY spawn failed for {argv!r}: {exc}"
            ) from exc

        return cls(proc, session_id=session_id, cwd=cwd or os.getcwd(), cols=cols, rows=rows)

    # -- identity --------------------------------------------------------

    @property
    def pid(self) -> int:
        return int(self._proc.pid)

    @property
    def session_id(self) -> str:
        return self._session_id

    def is_alive(self) -> bool:
        if self._closed:
            return False
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    # -- I/O -------------------------------------------------------------

    def read(self, timeout: float = 0.2) -> Optional[bytes]:
        """Read up to 64 KiB of child output. Increments the output cursor.

        Returns:
          * bytes — zero or more bytes of child output
          * empty bytes (``b""``) — no data available within ``timeout``
          * None — child has exited and the PTY is at EOF
        """
        if self._closed:
            return None
        try:
            data = self._proc.read(65536)
        except EOFError:
            return None
        except Exception:
            return None

        if not data:
            time.sleep(min(timeout, 0.02))
            return b""

        if isinstance(data, bytes):
            chunk = data
        else:
            chunk = data.encode("utf-8", errors="replace")

        self._output_cursor += 1
        self._last_output = chunk.decode("utf-8", errors="replace")[-512:]
        return chunk

    def write(self, data: bytes) -> None:
        """Write raw bytes to the child's stdin. Serialized (spec Decision 7).

        Concurrent writes are rejected — they would interleave bytes and
        corrupt the child's input stream.
        """
        if self._closed or not data:
            return
        if not self._write_lock.acquire(blocking=False):
            raise PtyUnavailableError(
                "Concurrent write rejected — input must be serialized through "
                "one broker-owned writer (spec Decision 7)."
            )
        try:
            self._proc.write(data.decode("utf-8", errors="replace"))
        except Exception:
            return
        finally:
            self._write_lock.release()

    def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        cols = _clamp(cols, _MAX_COLS)
        rows = _clamp(rows, _MAX_ROWS)
        try:
            self._proc.setwinsize(rows, cols)
            self._cols = cols
            self._rows = rows
        except Exception:
            pass

    # -- status ----------------------------------------------------------

    def status(self) -> SessionState:
        return SessionState(
            session_id=self._session_id,
            pid=self.pid,
            running=self.is_alive(),
            cols=self._cols,
            rows=self._rows,
            cwd=self._cwd,
            output_cursor=self._output_cursor,
            control_mode=getattr(self, "_control_mode", "local"),
            uptime=self.uptime(),
            last_output=getattr(self, "_last_output", ""),
        )

    @property
    def output_cursor(self) -> int:
        return self._output_cursor

    # -- teardown --------------------------------------------------------

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # pywinpty's terminate(force=True) can hang if the child is already
        # gone. We give it a short grace and then give up — the OS reaps
        # the ConPTY pseudo-console on process exit anyway.
        import threading
        done = threading.Event()
        def _do_terminate():
            try:
                self._proc.terminate(force=True)
            except Exception:
                pass
            done.set()
        t = threading.Thread(target=_do_terminate, daemon=True)
        t.start()
        done.wait(timeout=2.0)
        if not done.is_set():
            # terminate hung — the zombie child is harmless on Windows;
            # the ConPTY will be cleaned up by the OS.
            pass

    def __enter__(self) -> "PtyBridgePOC":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
