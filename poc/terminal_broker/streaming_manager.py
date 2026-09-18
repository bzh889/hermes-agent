"""POC Streaming Output Manager — ticket 06.

Manages incremental terminal output delivery through the Teams streaming/edit
path. The key contract (spec Testing Decision 9, ticket 06 checkboxes 1-4):

* Output reaches Teams incrementally — each new chunk extends the visible reply.
* Streaming updates remain **one logical edited reply** — they do not create
  duplicate progress/footer messages. The Teams transport edits the existing
  message; it does not send a new one.
* The accumulated text matches the actual terminal output (read-back fidelity).
* Cursors do not cause missing or duplicate content.

The manager is transport-agnostic: it produces ``StreamUpdate`` objects that
contain the full accumulated text and a stable message ID. The caller (Teams
adapter or harness) is responsible for delivering the edit through the existing
transport.

This is NOT production code and must NOT modify the production Teams adapter
or production gateway routing. It lives under ``poc/``.
"""

from __future__ import annotations

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


__all__ = [
    "StreamingOutputManager",
    "StreamUpdate",
    "StreamState",
]


class StreamState(Enum):
    """Lifecycle state of a streaming output session."""
    IDLE = "idle"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StreamUpdate:
    """One incremental update for a streaming session.

    The ``updated_text`` field contains the **full accumulated text** from the
    session start through this update. The Teams transport edits the existing
    message to this new text — it does not send a new message.

    ``message_id`` is stable across all updates for the same session: it is
    the Teams message ID used for edit correlation. The first update creates
    it; subsequent updates reuse it.

    ``is_final`` is True on the last update (COMPLETED or FAILED state).
    """
    session_id: str
    message_id: str
    updated_text: str
    is_final: bool = False
    state: StreamState = StreamState.STREAMING


@dataclass
class _StreamSession:
    """Internal state for one streaming session."""
    message_id: str
    accumulated: str = ""
    state: StreamState = StreamState.STREAMING


class StreamingOutputManager:
    """Manages incremental terminal output for Teams streaming delivery.

    The manager maintains one logical edited reply per session. Each call to
    :meth:`update` appends new output to the session's accumulated text and
    returns a :class:`StreamUpdate` with the full text and a stable message ID.

    Key properties (ticket 06 checkboxes 1-4):

    * **One logical reply**: all updates for a session share the same
      ``message_id``. The Teams transport edits the message; it does not
      create duplicate progress or footer messages.
    * **Incremental delivery**: each update contains the new chunk appended
      to the accumulated text, so the user sees progressively more output.
    * **Read-back fidelity**: the accumulated text is the concatenation of
      all chunks received, preserving the actual terminal output.
    * **No missing or duplicate content**: the manager appends each chunk
      exactly once. The cursor is implicit in the accumulated text length.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _StreamSession] = {}

    def update(self, session_id: str, chunk: str) -> StreamUpdate:
        """Append *chunk* to the session's accumulated output and return
        a :class:`StreamUpdate` with the full text.

        The first update for a session creates a stable message ID (a UUID).
        Subsequent updates reuse the same message ID so the Teams transport
        edits the existing message rather than creating a new one.

        If the session is already COMPLETED or FAILED, the update is ignored
        and a terminal-state update is returned.
        """
        sess = self._sessions.get(session_id)
        if sess is None:
            sess = _StreamSession(
                message_id=uuid.uuid4().hex,
                state=StreamState.STREAMING,
            )
            self._sessions[session_id] = sess

        if sess.state in (StreamState.COMPLETED, StreamState.FAILED):
            return StreamUpdate(
                session_id=session_id,
                message_id=sess.message_id,
                updated_text=sess.accumulated,
                is_final=True,
                state=sess.state,
            )

        sess.accumulated += chunk
        return StreamUpdate(
            session_id=session_id,
            message_id=sess.message_id,
            updated_text=sess.accumulated,
            is_final=False,
            state=StreamState.STREAMING,
        )

    def finalize(self, session_id: str) -> StreamUpdate:
        """Mark a session as completed (child exited normally).

        Returns a final update with ``is_final=True`` and ``COMPLETED`` state.
        If the session does not exist, returns a FAILED update.
        """
        sess = self._sessions.get(session_id)
        if sess is None:
            return StreamUpdate(
                session_id=session_id,
                message_id="",
                updated_text="Session not found",
                is_final=True,
                state=StreamState.FAILED,
            )

        sess.state = StreamState.COMPLETED
        return StreamUpdate(
            session_id=session_id,
            message_id=sess.message_id,
            updated_text=sess.accumulated,
            is_final=True,
            state=StreamState.COMPLETED,
        )

    def fail(self, session_id: str, reason: str) -> StreamUpdate:
        """Mark a session as failed (child exit, PTY failure, gateway restart).

        Returns a final update with ``is_final=True`` and ``FAILED`` state.
        The reason is appended to the accumulated text so it is visible to
        the user through the Teams transport.
        """
        sess = self._sessions.get(session_id)
        if sess is None:
            # Session may have been cleaned up; still report the failure
            return StreamUpdate(
                session_id=session_id,
                message_id="",
                updated_text=f"Session failed: {reason}",
                is_final=True,
                state=StreamState.FAILED,
            )

        sess.state = StreamState.FAILED
        # Append the failure reason so it is visible in the edited reply
        failure_text = f"\n[STREAM FAILED: {reason}]"
        sess.accumulated += failure_text
        return StreamUpdate(
            session_id=session_id,
            message_id=sess.message_id,
            updated_text=sess.accumulated,
            is_final=True,
            state=StreamState.FAILED,
        )

    def get_message_id(self, session_id: str) -> Optional[str]:
        """Return the stable message ID for a session, or None if unknown."""
        sess = self._sessions.get(session_id)
        return sess.message_id if sess else None

    def get_accumulated_text(self, session_id: str) -> str:
        """Return the full accumulated output text for a session."""
        sess = self._sessions.get(session_id)
        return sess.accumulated if sess else ""

    def get_state(self, session_id: str) -> StreamState:
        """Return the current stream state for a session."""
        sess = self._sessions.get(session_id)
        return sess.state if sess else StreamState.IDLE

    def reset(self, session_id: str) -> None:
        """Clear a session's state (useful after gateway restart)."""
        self._sessions.pop(session_id, None)
