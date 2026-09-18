"""POC Terminal Session Broker — multi-session management with explicit handoff.

Windows-only throwaway POC for the Teams Terminal Remote Control spec.
This module sits above ``pty_bridge_poc.PtyBridgePOC`` (ticket 01) and adds
the ticket-02 capabilities:

* Multi-session management with unique opaque session IDs.
* Explicit target routing — every command addresses a specific session ID.
* Input authority modes: ``local`` and ``remote`` (exclusive handoff).
* Mode transitions that preserve the child-process identity.
* Output cursors for incremental consumers.
* Close isolation — closing one session does not affect another.

This is NOT production code and must NOT modify the production Teams adapter
or production gateway routing. It lives under ``poc/`` for that reason.

Key design decisions (from spec §Implementation Decisions):
  - Decision 4: The public broker contract is narrow — create, list/status,
    read output, write input, set control mode, resize, and close.
  - Decision 5: Every session has an opaque stable session ID.
  - Decision 6: Control mode is explicit. Remote input is accepted only in
    ``remote`` mode; local input is accepted only in ``local`` mode for
    exclusive handoff tests. Output remains observable in both modes.
  - Decision 7: Input is serialized through one broker-owned writer.
"""

from __future__ import annotations

import os
import uuid
from enum import Enum
from typing import Optional, Sequence

from poc.terminal_broker.pty_bridge_poc import (
    PtyBridgePOC,
    PtyUnavailableError,
    SessionState,
)


__all__ = [
    "SessionBroker",
    "BrokerError",
    "ControlMode",
]


class BrokerError(RuntimeError):
    """Raised when a broker operation fails (unknown session, wrong mode, etc.)."""


class ControlMode(Enum):
    """Input authority modes (spec Decision 6)."""
    LOCAL = "local"
    REMOTE = "remote"


class _Session:
    """Internal wrapper that tracks a session's control mode on top of the
    PtyBridgePOC.  We store the mode here rather than on the bridge so the
    broker owns the control-plane state.
    """

    __slots__ = ("bridge", "mode")

    def __init__(self, bridge: PtyBridgePOC, mode: ControlMode = ControlMode.LOCAL) -> None:
        self.bridge = bridge
        self.mode = mode


class SessionBroker:
    """Broker-owned terminal session manager.

    Manages one or more named ConPTY sessions through the narrow public
    contract defined by the spec.  Each session is identified by an opaque
    stable session ID.  All operations route to an explicit session — there
    is no implicit "current" session.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    # -- availability ---------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """True if the underlying PTY backend can be used on this platform."""
        return PtyBridgePOC.is_available()

    # -- session lifecycle ----------------------------------------------

    def create(
        self,
        argv: Sequence[str],
        *,
        session_id: str | None = None,
        cwd: Optional[str] = None,
        cols: int = 80,
        rows: int = 24,
    ) -> str:
        """Create a new terminal session and return its opaque session ID.

        If *session_id* is ``None`` a UUID4-based ID is generated.  A
        custom ID that already exists raises ``BrokerError``.
        """
        sid = session_id or uuid.uuid4().hex
        if sid in self._sessions:
            raise BrokerError(f"Session '{sid}' already exists")

        if not self.is_available():
            raise PtyUnavailableError(
                "PTY backend unavailable — broker cannot create sessions on "
                "this platform."
            )

        bridge = PtyBridgePOC.spawn(
            argv,
            session_id=sid,
            cwd=cwd,
            cols=cols,
            rows=rows,
        )
        self._sessions[sid] = _Session(bridge, ControlMode.LOCAL)
        return sid

    def close(self, session_id: str) -> None:
        """Close a named session.  Idempotent: closing an already-closed
        or unknown session is silently ignored.
        """
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            raise BrokerError(f"Session '{session_id}' not found")
        sess.bridge.close()

    def shutdown(self) -> None:
        """Close all sessions and release resources."""
        for sid in list(self._sessions):
            sess = self._sessions.pop(sid, None)
            if sess is not None:
                sess.bridge.close()

    # -- queries --------------------------------------------------------

    def list_sessions(self) -> list[str]:
        """Return the session IDs of all live sessions."""
        return list(self._sessions)

    def status(self, session_id: str) -> SessionState:
        """Return a ``SessionState`` snapshot for the named session."""
        sess = self._require(session_id)
        state = sess.bridge.status()
        # Override control_mode from the broker's own tracking
        state.control_mode = sess.mode.value
        return state

    # -- I/O -------------------------------------------------------------

    def read_output(self, session_id: str) -> Optional[bytes]:
        """Read available output from the named session.

        Returns:
          * bytes — zero or more bytes of child output
          * empty bytes (``b""``) — no data available
          * None — child has exited and the PTY is at EOF
        """
        sess = self._require(session_id)
        return sess.bridge.read()

    def read_output_since(self, session_id: str, cursor: int) -> tuple[bytes, int]:
        """Read output accumulated since the given cursor value.

        Returns (data_bytes, new_cursor).  This is the incremental-consumer
        API — callers pass the cursor from a previous ``status()`` call and
        receive only the new output since that point.

        If the child has exited (EOF), returns remaining buffered data (if
        any) and the current cursor.
        """
        sess = self._require(session_id)
        # Read any new output
        chunk = sess.bridge.read()
        new_cursor = sess.bridge.output_cursor
        if chunk is None:
            return b"", new_cursor
        return chunk, new_cursor

    def try_read_output(self, session_id: str) -> Optional[bytes]:
        """Non-blocking read — returns immediately if no data is available.

        Like :meth:`read_output` but never blocks.  Returns:
          * bytes — zero or more bytes of child output
          * empty bytes — no data available right now
          * None — child has exited and the PTY is at EOF
        """
        sess = self._require(session_id)
        return sess.bridge.try_read()

    def write_input(self, session_id: str, data: bytes, *, source: str = "local") -> None:
        """Write input to the named session.

        *source* must match the session's current control mode:
          * ``"local"`` — accepted only in LOCAL mode
          * ``"remote"`` — accepted only in REMOTE mode

        A mismatch raises ``BrokerError`` with a clear message.

        Concurrent writes are rejected at the bridge level (spec Decision 7).
        """
        sess = self._require(session_id)

        # Mode enforcement (spec Decision 6)
        if source == "remote" and sess.mode != ControlMode.REMOTE:
            raise BrokerError(
                f"Remote input rejected — session '{session_id}' is in "
                f"{sess.mode.value} mode. Switch to remote mode first."
            )
        if source == "local" and sess.mode != ControlMode.LOCAL:
            raise BrokerError(
                f"Local input rejected — session '{session_id}' is in "
                f"{sess.mode.value} mode. Switch to local mode first."
            )

        try:
            sess.bridge.write(data)
        except PtyUnavailableError as exc:
            # Concurrent write rejected by the bridge's serialized writer
            if "Concurrent write" in str(exc):
                raise BrokerError(
                    f"Concurrent write rejected — input must be serialized "
                    f"through one broker-owned writer (spec Decision 7)."
                ) from exc
            raise

    # -- control mode ---------------------------------------------------

    def set_mode(self, session_id: str, mode: ControlMode) -> None:
        """Switch input authority for the named session.

        This does *not* restart the child process.  The same ConPTY session
        and child PID survive the transition (spec Decision 6, User Story 6/7).

        The mode is stored only in the broker's ``_Session`` tracker — the
        bridge's ``_control_mode`` attribute is not touched here.  The broker
        owns the control-plane state (Decision 6) and overrides the bridge's
        ``status()`` to reflect it.
        """
        sess = self._require(session_id)
        sess.mode = mode

    def get_mode(self, session_id: str) -> ControlMode:
        """Return the current control mode for the named session."""
        sess = self._require(session_id)
        return sess.mode

    # -- resize ---------------------------------------------------------

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        """Resize the named session's terminal."""
        sess = self._require(session_id)
        sess.bridge.resize(cols, rows)

    # -- internals ------------------------------------------------------

    def _require(self, session_id: str) -> _Session:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise BrokerError(f"Session '{session_id}' not found")
        return sess
