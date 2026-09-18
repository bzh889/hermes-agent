"""TDD tests for the POC Terminal Session Broker — Session Broker Seam.

Tests for ticket 02: Terminal Session Broker with Explicit Handoff.
All 8 checkboxes from the ticket are covered here.

The broker sits above the PTY bridge (ticket 01) and adds:
  * Multi-session management with unique opaque IDs
  * Explicit target routing (commands address a specific session)
  * Input authority modes: ``local`` and ``remote``
  * Mode transitions preserving child-process identity
  * Output cursors for incremental consumers
  * Close isolation (closing one session does not affect another)

Windows-only: uses the same ConPTY backend as ticket 01.

Run:
    scripts/run_tests.sh tests/poc/test_session_broker_poc.py -v
"""

from __future__ import annotations

import os
import re
import sys
import time

import pytest

from poc.terminal_broker.pty_bridge_poc import (
    PtyBridgePOC,
    PtyUnavailableError,
    SessionState,
)
from poc.terminal_broker.session_broker import (
    BrokerError,
    ControlMode,
    SessionBroker,
)

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="POC ConPTY broker is Windows-only",
)

# Fixtures
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "poc", "terminal_broker", "fixtures"),
)
from fixture_echo import fixture_argv as _echo_argv  # noqa: E402
from fixture_multiround import fixture_argv as _multiround_argv  # noqa: E402


# -- helpers ------------------------------------------------------------------

def _read_until(broker: SessionBroker, sid: str, needle: bytes, timeout: float = 10.0) -> bytes:
    """Accumulate output from session *sid* until we see *needle* or time out."""
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        chunk = broker.read_output(sid)
        if chunk is None:
            break
        buf.extend(chunk)
        if needle in buf:
            return bytes(buf)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Cross-platform: module import surface
# ---------------------------------------------------------------------------

class TestSessionBrokerImportable:
    """Broker module must be importable on every OS; ``is_available`` gates Windows."""

    def test_session_broker_is_importable(self):
        assert SessionBroker is not None
        assert callable(SessionBroker.is_available)

    def test_broker_error_is_importable(self):
        err = BrokerError("bad session")
        assert "bad session" in str(err)

    def test_control_mode_values(self):
        assert ControlMode.LOCAL.value == "local"
        assert ControlMode.REMOTE.value == "remote"


# ---------------------------------------------------------------------------
# Windows-only: ticket 02 checkboxes
# ---------------------------------------------------------------------------

@windows_only
class TestUniqueSessionID:
    """Ticket 02 checkbox 1: Every session receives a unique opaque session ID."""

    def test_create_returns_unique_ids(self):
        broker = SessionBroker()
        try:
            sid1 = broker.create(_echo_argv())
            sid2 = broker.create(_echo_argv())
            sid3 = broker.create(_echo_argv())
            ids = {sid1, sid2, sid3}
            assert len(ids) == 3, f"Session IDs are not unique: {ids}"
            # Opaque: at least nontrivial length, non-empty
            for sid in ids:
                assert isinstance(sid, str)
                assert len(sid) >= 8
            broker.close(sid1)
            broker.close(sid2)
            broker.close(sid3)
        finally:
            broker.shutdown()

    def test_create_with_custom_id(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="my-custom-id")
            assert sid == "my-custom-id"
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_duplicate_custom_id_rejected(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="dup-id")
            with pytest.raises(BrokerError, match="already exists"):
                broker.create(_echo_argv(), session_id="dup-id")
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestStatusExposesFields:
    """Ticket 02 checkbox 2: Status exposes running/exited, PID, uptime,
    working directory, dimensions, and last-output information.
    """

    def test_status_has_all_required_fields(self):
        broker = SessionBroker()
        try:
            sid = broker.create(
                _echo_argv(),
                cwd=os.getcwd(),
                cols=100,
                rows=30,
            )
            # Wait for the start marker so we have some output.
            _read_until(broker, sid, b"START_MARKER:")
            state = broker.status(sid)
            assert isinstance(state, SessionState)
            assert state.session_id == sid
            assert state.pid > 0
            assert state.running is True
            assert state.cols == 100
            assert state.rows == 30
            assert state.cwd  # non-empty cwd
            assert state.uptime >= 0.0
            assert state.last_output  # should have the START_MARKER output
            assert "START_MARKER" in state.last_output
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_status_after_exit(self):
        broker = SessionBroker()
        try:
            sid = broker.create(["cmd.exe", "/c", "exit 0"])
            # Wait for exit
            deadline = time.monotonic() + 5.0
            while broker.status(sid).running and time.monotonic() < deadline:
                broker.read_output(sid)
                time.sleep(0.05)
            state = broker.status(sid)
            assert state.running is False
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestSerializedInput:
    """Ticket 02 checkbox 3: Input is serialized so concurrent writers
    cannot interleave bytes.
    """

    def test_concurrent_write_rejected(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv())
            # Hold the underlying bridge lock to simulate concurrent access
            sess = broker._require(sid)
            sess.bridge._write_lock.acquire()
            try:
                with pytest.raises(BrokerError, match="concurrent|serialized|busy"):
                    broker.write_input(sid, b"sneaky\r\n")
            finally:
                sess.bridge._write_lock.release()
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_sequential_writes_work(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            _read_until(broker, sid, b"START_MARKER:")
            broker.write_input(sid, b"first\r\n")
            _read_until(broker, sid, b"ROUND:0:")
            broker.write_input(sid, b"second\r\n")
            _read_until(broker, sid, b"ROUND:1:")
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestLocalMode:
    """Ticket 02 checkbox 4: Local mode accepts local input and rejects
    remote input.
    """

    def test_local_mode_accepts_local_input(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv())
            _read_until(broker, sid, b"START_MARKER:")
            # Default mode is local
            assert broker.get_mode(sid) == ControlMode.LOCAL
            broker.write_input(sid, b"hello-local\r\n", source="local")
            out = _read_until(broker, sid, b"RESP:hello-local")
            assert b"RESP:hello-local" in out
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_local_mode_rejects_remote_input(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv())
            _read_until(broker, sid, b"START_MARKER:")
            assert broker.get_mode(sid) == ControlMode.LOCAL
            with pytest.raises(BrokerError, match="remote.*not.*allowed|rejected|mode"):
                broker.write_input(sid, b"hello-remote\r\n", source="remote")
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestRemoteMode:
    """Ticket 02 checkbox 5: Remote mode accepts remote input and rejects
    local input.
    """

    def test_remote_mode_accepts_remote_input(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv())
            _read_until(broker, sid, b"START_MARKER:")
            broker.set_mode(sid, ControlMode.REMOTE)
            assert broker.get_mode(sid) == ControlMode.REMOTE
            broker.write_input(sid, b"hello-remote\r\n", source="remote")
            out = _read_until(broker, sid, b"RESP:hello-remote")
            assert b"RESP:hello-remote" in out
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_remote_mode_rejects_local_input(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv())
            _read_until(broker, sid, b"START_MARKER:")
            broker.set_mode(sid, ControlMode.REMOTE)
            with pytest.raises(BrokerError, match="local.*not.*allowed|rejected|mode"):
                broker.write_input(sid, b"hello-local\r\n", source="local")
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestModeSwitchPreservesChild:
    """Ticket 02 checkbox 6: Switching modes preserves the same child
    process identity.
    """

    def test_pid_unchanged_through_mode_switches(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            _read_until(broker, sid, b"START_MARKER:")

            pid_before = broker.status(sid).pid

            # local → remote
            broker.set_mode(sid, ControlMode.REMOTE)
            pid_after_remote = broker.status(sid).pid
            assert pid_after_remote == pid_before, (
                f"PID changed on local→remote: {pid_before} → {pid_after_remote}"
            )

            # Remote write
            broker.write_input(sid, b"round-remote\r\n", source="remote")
            _read_until(broker, sid, b"ROUND:0:")

            # remote → local
            broker.set_mode(sid, ControlMode.LOCAL)
            pid_after_local = broker.status(sid).pid
            assert pid_after_local == pid_before, (
                f"PID changed on remote→local: {pid_before} → {pid_after_local}"
            )

            # Local write
            broker.write_input(sid, b"round-local\r\n", source="local")
            _read_until(broker, sid, b"ROUND:1:")

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_child_identity_marker_survives_handoff(self):
        """Use the fixture's START_MARKER PID to verify the same child
        process is alive throughout the mode transitions.

        The multiround fixture includes its PID in every ROUND response,
        so we verify the PID in ROUND:0 (remote) and ROUND:1 (local) matches
        the START_MARKER PID — proving the child was not restarted.
        """
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            out = _read_until(broker, sid, b"START_MARKER:")
            m = re.search(rb"START_MARKER:(\d+)", out)
            assert m is not None
            fixture_pid = int(m.group(1))

            # remote write
            broker.set_mode(sid, ControlMode.REMOTE)
            broker.write_input(sid, b"after-remote\r\n", source="remote")
            out_r = _read_until(broker, sid, b"ROUND:0:")
            m_r = re.search(rb"ROUND:0:(\d+):", out_r)
            assert m_r is not None, f"ROUND:0 PID not found in: {out_r!r}"
            assert int(m_r.group(1)) == fixture_pid, (
                f"Round 0 PID {int(m_r.group(1))} != START_MARKER PID {fixture_pid}"
            )

            # remote → local
            broker.set_mode(sid, ControlMode.LOCAL)
            broker.write_input(sid, b"after-local\r\n", source="local")
            out_l = _read_until(broker, sid, b"ROUND:1:")
            m_l = re.search(rb"ROUND:1:(\d+):", out_l)
            assert m_l is not None, f"ROUND:1 PID not found in: {out_l!r}"
            assert int(m_l.group(1)) == fixture_pid, (
                f"Round 1 PID {int(m_l.group(1))} != START_MARKER PID {fixture_pid}"
            )

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestOutputCursor:
    """Ticket 02 checkbox 7: Output has monotonic cursor/sequence metadata
    for incremental consumers.
    """

    def test_cursor_increments_across_reads(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            _read_until(broker, sid, b"START_MARKER:")
            cursor_1 = broker.status(sid).output_cursor
            assert cursor_1 >= 1

            broker.write_input(sid, b"line1\r\n", source="local")
            _read_until(broker, sid, b"ROUND:0:")
            cursor_2 = broker.status(sid).output_cursor
            assert cursor_2 >= cursor_1

            broker.write_input(sid, b"line2\r\n", source="local")
            _read_until(broker, sid, b"ROUND:1:")
            cursor_3 = broker.status(sid).output_cursor
            assert cursor_3 >= cursor_2

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_read_from_cursor_returns_incremental(self):
        """read_output_since a given cursor should return only new data."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            _read_until(broker, sid, b"START_MARKER:")
            cursor_after_start = broker.status(sid).output_cursor

            broker.write_input(sid, b"delayed\r\n", source="local")
            data, new_cursor = broker.read_output_since(sid, cursor_after_start)
            assert b"ROUND:0:" in data
            assert new_cursor > cursor_after_start

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestCloseIsolation:
    """Ticket 02 checkbox 8: Closing one session does not affect another
    session.
    """

    def test_close_one_does_not_affect_other(self):
        broker = SessionBroker()
        try:
            sid_a = broker.create(_echo_argv(), session_id="iso-A")
            sid_b = broker.create(_echo_argv(), session_id="iso-B")

            _read_until(broker, sid_a, b"START_MARKER:")
            _read_until(broker, sid_b, b"START_MARKER:")

            assert broker.status(sid_a).running
            assert broker.status(sid_b).running

            broker.close(sid_a)

            # Session A is gone
            with pytest.raises(BrokerError, match="not found|unknown|closed"):
                broker.status(sid_a)

            # Session B is unaffected
            assert broker.status(sid_b).running
            broker.write_input(sid_b, b"still_alive\r\n", source="local")
            out = _read_until(broker, sid_b, b"RESP:still_alive")
            assert b"RESP:still_alive" in out

            broker.close(sid_b)
        finally:
            broker.shutdown()

    def test_list_sessions_after_close(self):
        broker = SessionBroker()
        try:
            sid1 = broker.create(_echo_argv(), session_id="list-1")
            sid2 = broker.create(_echo_argv(), session_id="list-2")
            assert set(broker.list_sessions()) == {sid1, sid2}

            broker.close(sid1)
            assert set(broker.list_sessions()) == {sid2}

            broker.close(sid2)
            assert broker.list_sessions() == []
        finally:
            broker.shutdown()


@windows_only
class TestModeSwitchNoForegroundWindow:
    """Testing Decision 6: control-mode transitions do not create a new
    foreground window or restart the child process.
    """

    def test_no_new_window_during_mode_switch(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv())
            _read_until(broker, sid, b"START_MARKER:")
            pid = broker.status(sid).pid

            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            def _has_visible_window(target_pid: int) -> bool:
                found = False
                def _cb(hwnd, lparam):
                    nonlocal found
                    if user32.IsWindowVisible(hwnd):
                        pd = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pd))
                        if pd.value == target_pid:
                            found = True
                    return True
                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
                )
                user32.EnumWindows(EnumWindowsProc(_cb), 0)
                return found

            # Before any mode switch
            assert not _has_visible_window(pid), "window before switch"

            # local → remote
            broker.set_mode(sid, ControlMode.REMOTE)
            assert not _has_visible_window(pid), "window after local→remote"

            # remote → local
            broker.set_mode(sid, ControlMode.LOCAL)
            assert not _has_visible_window(pid), "window after remote→local"

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestExplicitTargetRouting:

    def test_write_to_nonexistent_session_rejected(self):
        broker = SessionBroker()
        try:
            with pytest.raises(BrokerError, match="not found|unknown"):
                broker.write_input("no-such-session", b"data\r\n")
        finally:
            broker.shutdown()

    def test_read_from_nonexistent_session_rejected(self):
        broker = SessionBroker()
        try:
            with pytest.raises(BrokerError, match="not found|unknown"):
                broker.read_output("no-such-session")
        finally:
            broker.shutdown()

    def test_set_mode_on_nonexistent_session_rejected(self):
        broker = SessionBroker()
        try:
            with pytest.raises(BrokerError, match="not found|unknown"):
                broker.set_mode("no-such-session", ControlMode.REMOTE)
        finally:
            broker.shutdown()
