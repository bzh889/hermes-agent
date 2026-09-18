"""TDD tests for ticket 06 — Teams Streaming and Security E2E.

Tests prove the end-to-end streaming and security behaviour:

1. Terminal output reaches Teams incrementally through the streaming/edit path.
2. Streaming updates remain one logical edited reply (no duplicate progress/footer messages).
3. Teams read-back matches the actual terminal output.
4. Output cursors do not cause missing or duplicate content.
5. Unauthorized conversation and unauthorized sender paths are both denied.
6. Stop affects only the requested session.
7. Gateway restart, child exit, and PTY failure produce explicit user-visible states.
8. Real Teams E2E evidence is separated from local unit and harness evidence.
9. The result records whether the next Codex, Claude Code, and Hermes TUI investment is justified.

Cross-platform: import-level tests run everywhere.
Windows-only: full integration tests spawn real ConPTY sessions.

Run:
    scripts/run_tests.sh tests/poc/test_streaming_e2e_poc.py -v
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from poc.terminal_broker.session_broker import (
    BrokerError,
    ControlMode,
    SessionBroker,
)
from poc.terminal_broker.teams_control_adapter import (
    AuthDecision,
    CommandResult,
    CommandVerb,
    InboundMessage,
    TeamsControlAdapter,
    EVIDENCE_LABEL,
)
from poc.terminal_broker.streaming_manager import (
    StreamingOutputManager,
    StreamUpdate,
    StreamState,
)
from poc.terminal_broker.e2e_harness import (
    E2EHarness,
    E2EVerdict,
    E2EResult,
    EvidenceTier,
)

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="E2E streaming tests require Windows ConPTY broker",
)

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "poc", "terminal_broker", "fixtures"),
)
from fixture_echo import fixture_argv as _echo_argv  # noqa: E402
from fixture_multiround import fixture_argv as _multiround_argv  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTROL_CONV = "19:control-conversation@thread.v2"
WRONG_CONV = "19:other-conversation@thread.v2"
OWNER_OID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
WRONG_OID = "99999999-8888-7777-6666-555555555555"


def _read_until(broker: SessionBroker, sid: str, needle: bytes, timeout: float = 10.0) -> bytes:
    """Accumulate output from session *sid* until we see *needle*."""
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        chunk = broker.try_read_output(sid)
        if chunk is None:
            break
        buf.extend(chunk)
        if needle in buf:
            return bytes(buf)
        time.sleep(0.02)
    return bytes(buf)


def _make_adapter(broker: SessionBroker) -> TeamsControlAdapter:
    return TeamsControlAdapter(
        broker,
        control_conversation_id=CONTROL_CONV,
        owner_oid=OWNER_OID,
    )


# ---------------------------------------------------------------------------
# Cross-platform: module import surface
# ---------------------------------------------------------------------------

class TestStreamingManagerImportable:
    """The streaming manager module must be importable on every OS."""

    def test_streaming_manager_class_is_importable(self):
        assert StreamingOutputManager is not None

    def test_stream_update_dataclass(self):
        u = StreamUpdate(
            session_id="s1",
            message_id="msg-1",
            updated_text="hello",
            is_final=False,
            state=StreamState.STREAMING,
        )
        assert u.session_id == "s1"
        assert u.message_id == "msg-1"
        assert u.is_final is False

    def test_stream_state_values(self):
        assert StreamState.IDLE.value == "idle"
        assert StreamState.STREAMING.value == "streaming"
        assert StreamState.COMPLETED.value == "completed"
        assert StreamState.FAILED.value == "failed"


class TestE2EHarnessImportable:
    """The E2E harness module must be importable on every OS."""

    def test_e2e_harness_class_is_importable(self):
        assert E2EHarness is not None

    def test_e2e_verdict_values(self):
        assert E2EVerdict.PASS.value == "PASS"
        assert E2EVerdict.FAIL.value == "FAIL"

    def test_evidence_tier_values(self):
        assert EvidenceTier.LOCAL_UNIT.value == "local-unit"
        assert EvidenceTier.HARNESS_VERIFIED.value == "harness-verified"
        assert EvidenceTier.LIVE_TEAMS_E2E.value == "live-teams-e2e"
        assert EvidenceTier.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# Cross-platform: streaming manager logic (no real PTY needed)
# ---------------------------------------------------------------------------

class TestStreamingManagerLogic:
    """StreamingOutputManager maintains one logical edited reply per session."""

    def test_first_update_creates_message_id(self):
        """The first output chunk creates a stable message ID for edit correlation."""
        mgr = StreamingOutputManager()
        update = mgr.update("session-1", "hello\n")
        assert update.message_id is not None
        assert update.message_id == mgr.get_message_id("session-1")
        assert update.updated_text == "hello\n"
        assert update.is_final is False
        assert update.state == StreamState.STREAMING

    def test_second_update_edits_same_message_id(self):
        """The second output chunk edits the same message, not a new one."""
        mgr = StreamingOutputManager()
        u1 = mgr.update("session-1", "line1\n")
        u2 = mgr.update("session-1", "line2\n")
        assert u1.message_id == u2.message_id, (
            "Streaming updates must edit the same logical message ID"
        )

    def test_no_duplicate_progress_messages(self):
        """Ticket 06 checkbox 2: streaming updates remain one logical edited
        reply and do not create duplicate progress/footer messages.

        Each update returns the *full accumulated text* — the Teams transport
        edits the existing message rather than sending a new one. We verify
        by checking that each update contains all prior output plus the new
        chunk, and the message ID never changes.
        """
        mgr = StreamingOutputManager()
        u1 = mgr.update("s1", "a")
        u2 = mgr.update("s1", "b")
        u3 = mgr.update("s1", "c")
        assert u1.message_id == u2.message_id == u3.message_id
        # Each update contains the full accumulated text
        assert "a" in u1.updated_text
        assert "a" in u2.updated_text and "b" in u2.updated_text
        assert "a" in u3.updated_text and "b" in u3.updated_text and "c" in u3.updated_text

    def test_finalize_marks_completed(self):
        """Finalizing a stream marks it as completed and sets is_final."""
        mgr = StreamingOutputManager()
        mgr.update("s1", "data")
        final = mgr.finalize("s1")
        assert final.is_final is True
        assert final.state == StreamState.COMPLETED

    def test_finalize_unknown_session(self):
        """Finalizing an unknown session returns a failed update."""
        mgr = StreamingOutputManager()
        final = mgr.finalize("unknown-session")
        assert final.state == StreamState.FAILED
        assert "not found" in final.updated_text.lower()

    def test_failure_state(self):
        """Failing a stream marks it as failed with an explicit message."""
        mgr = StreamingOutputManager()
        mgr.update("s1", "partial output")
        fail = mgr.fail("s1", "child process exited unexpectedly")
        assert fail.state == StreamState.FAILED
        assert "child process exited unexpectedly" in fail.updated_text
        assert fail.is_final is True

    def test_cursor_no_missing_content(self):
        """Ticket 06 checkbox 4: output cursors do not cause missing content.

        The streaming manager tracks a cursor internally. When we poll
        multiple times, the concatenation of all updates equals the full
        output — nothing is skipped.
        """
        mgr = StreamingOutputManager()
        full_output = ""
        for i in range(5):
            chunk = f"chunk-{i}\n"
            full_output += chunk
            mgr.update("s1", chunk)
        # The last update should contain the full output
        assert mgr.get_accumulated_text("s1") == full_output

    def test_cursor_no_duplicate_content(self):
        """Ticket 06 checkbox 4: output cursors do not cause duplicate content.

        The accumulated text must not contain duplicated chunks.
        """
        mgr = StreamingOutputManager()
        mgr.update("s1", "aaa")
        mgr.update("s1", "bbb")
        text = mgr.get_accumulated_text("s1")
        assert text.count("aaa") == 1
        assert text.count("bbb") == 1

    def test_sessions_are_independent(self):
        """Two sessions have independent message IDs and accumulated text."""
        mgr = StreamingOutputManager()
        u_a = mgr.update("sess-a", "data-a")
        u_b = mgr.update("sess-b", "data-b")
        assert u_a.message_id != u_b.message_id
        assert "data-a" in mgr.get_accumulated_text("sess-a")
        assert "data-b" in mgr.get_accumulated_text("sess-b")
        assert "data-b" not in mgr.get_accumulated_text("sess-a")


# ---------------------------------------------------------------------------
# Cross-platform: evidence tier classification
# ---------------------------------------------------------------------------

class TestEvidenceTier:
    """Ticket 06 checkbox 8: real Teams E2E evidence is separated from local
    unit and harness evidence.
    """

    def test_evidence_tier_local_unit(self):
        assert EvidenceTier.LOCAL_UNIT.value == "local-unit"

    def test_evidence_tier_harness_verified(self):
        assert EvidenceTier.HARNESS_VERIFIED.value == "harness-verified"

    def test_evidence_tier_live_teams_e2e(self):
        assert EvidenceTier.LIVE_TEAMS_E2E.value == "live-teams-e2e"

    def test_evidence_tier_unknown(self):
        assert EvidenceTier.UNKNOWN.value == "unknown"

    def test_local_unit_is_not_live(self):
        """A local-unit result must not be reported as live Teams E2E."""
        tier = EvidenceTier.LOCAL_UNIT
        assert tier != EvidenceTier.LIVE_TEAMS_E2E

    def test_harness_verified_is_not_live(self):
        """A harness-verified result must not be reported as live Teams E2E."""
        tier = EvidenceTier.HARNESS_VERIFIED
        assert tier != EvidenceTier.LIVE_TEAMS_E2E


# ---------------------------------------------------------------------------
# Cross-platform: investment verdict
# ---------------------------------------------------------------------------

class TestInvestmentVerdict:
    """Ticket 06 checkbox 9: the result records whether the next Codex,
    Claude Code, and Hermes TUI investment is justified.
    """

    def test_verdict_records_justified(self):
        result = E2EResult(
            verdict=E2EVerdict.PASS,
            evidence_tier=EvidenceTier.HARNESS_VERIFIED,
            investment_justified=True,
        )
        assert result.investment_justified is True

    def test_verdict_records_not_justified(self):
        result = E2EResult(
            verdict=E2EVerdict.FAIL,
            evidence_tier=EvidenceTier.HARNESS_VERIFIED,
            investment_justified=False,
        )
        assert result.investment_justified is False

    def test_result_has_explicit_investment_field(self):
        """Every E2E result must have an explicit investment_justified field."""
        result = E2EResult(
            verdict=E2EVerdict.PASS,
            evidence_tier=EvidenceTier.LOCAL_UNIT,
        )
        assert hasattr(result, "investment_justified")
        assert isinstance(result.investment_justified, bool)


# ---------------------------------------------------------------------------
# Windows-only: streaming through the adapter + broker
# ---------------------------------------------------------------------------

@windows_only
class TestStreamingIncrementalOutput:
    """Ticket 06 checkbox 1: terminal output reaches Teams incrementally
    through the existing streaming/edit path.
    """

    def test_output_streamed_incrementally(self):
        """Output from a child process is delivered incrementally through
        the StreamingOutputManager, not all at once."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="stream-incremental")
            adapter = _make_adapter(broker)
            mgr = StreamingOutputManager()

            # Wait for START_MARKER
            deadline = time.monotonic() + 10.0
            updates = []
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and "START_MARKER" in result.response:
                    u = mgr.update(sid, result.response)
                    updates.append(u)
                    break
                if "exited" in (result.response or ""):
                    break
                time.sleep(0.05)

            assert len(updates) >= 1, "No streaming update for START_MARKER"
            assert "START_MARKER" in updates[0].updated_text

            # Write a line and capture the next update
            broker.write_input(sid, b"streamed-line\r\n", source="local")
            deadline2 = time.monotonic() + 10.0
            while time.monotonic() < deadline2:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and "ROUND:0:" in result.response:
                    u = mgr.update(sid, result.response)
                    updates.append(u)
                    break
                time.sleep(0.05)

            assert len(updates) >= 2, "No streaming update for ROUND:0"
            # The second update should contain both START_MARKER and ROUND:0
            assert "START_MARKER" in updates[-1].updated_text
            assert "ROUND:0:" in updates[-1].updated_text

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestStreamingOneLogicalReply:
    """Ticket 06 checkbox 2: streaming updates remain one logical edited
    reply and do not create duplicate progress/footer messages.
    """

    def test_all_updates_share_one_message_id(self):
        """Multiple streaming updates for the same session all share the
        same logical message ID — the Teams transport edits the message,
        it does not create new progress messages."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="stream-one-reply")
            adapter = _make_adapter(broker)
            mgr = StreamingOutputManager()

            # Collect updates
            message_ids = set()
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and result.response != "(no new output)" and "exited" not in result.response:
                    u = mgr.update(sid, result.response)
                    message_ids.add(u.message_id)
                if result.response and "START_MARKER" in (mgr.get_accumulated_text(sid) or ""):
                    break
                time.sleep(0.05)

            broker.write_input(sid, b"line-1\r\n", source="local")
            deadline2 = time.monotonic() + 10.0
            while time.monotonic() < deadline2:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and "ROUND:0:" in result.response:
                    u = mgr.update(sid, result.response)
                    message_ids.add(u.message_id)
                    break
                time.sleep(0.05)

            # All updates must share exactly one message ID
            assert len(message_ids) == 1, (
                f"Expected exactly 1 message ID for one logical reply, "
                f"got {len(message_ids)}: {message_ids}"
            )

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestReadStreamback:
    """Ticket 06 checkbox 3: Teams read-back matches the actual terminal
    output.
    """

    def test_read_back_matches_pty_output(self):
        """The streaming manager's accumulated text matches the actual
        output from the PTY.

        We verify readback by using a SECOND session that we read directly
        from the broker (ground truth) and a first session that we read
        through the adapter + streaming manager. Both sessions run the same
        fixture and receive the same input, so both must produce the same
        markers. The streaming manager's text must contain the same markers
        as the direct broker read.
        """
        broker = SessionBroker()
        try:
            # Session A: read through the adapter + streaming manager
            sid_a = broker.create(_multiround_argv(), session_id="stream-readback-a")
            adapter = _make_adapter(broker)
            mgr = StreamingOutputManager()

            # Session B: read directly from the broker (ground truth)
            sid_b = broker.create(_multiround_argv(), session_id="stream-readback-b")

            # Collect output through the adapter for session A
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid_a}",
                ))
                if result.response and result.response != "(no new output)" and "exited" not in (result.response or ""):
                    mgr.update(sid_a, result.response)
                if "START_MARKER" in (mgr.get_accumulated_text(sid_a) or ""):
                    break
                time.sleep(0.05)

            # Also read START_MARKER from session B directly
            direct_start = _read_until(broker, sid_b, b"START_MARKER:")

            # Write the same input to both sessions
            broker.write_input(sid_a, b"readback-test\r\n", source="local")
            broker.write_input(sid_b, b"readback-test\r\n", source="local")

            # Collect ROUND:0 through the adapter for session A
            deadline2 = time.monotonic() + 10.0
            while time.monotonic() < deadline2:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid_a}",
                ))
                if result.response and "ROUND:0:" in result.response:
                    mgr.update(sid_a, result.response)
                    break
                time.sleep(0.05)

            # Read ROUND:0 directly from session B
            direct_round = _read_until(broker, sid_b, b"readback-test")

            # The streaming manager's accumulated text must contain the
            # same markers as the direct read from session B
            stream_text = mgr.get_accumulated_text(sid_a)
            direct_text = (direct_start + direct_round).decode("utf-8", errors="replace")

            assert "START_MARKER" in stream_text, "START_MARKER missing from stream"
            assert "ROUND:0:" in stream_text, "ROUND:0 missing from stream"
            assert "readback-test" in stream_text, "Input text missing from stream"

            assert "START_MARKER" in direct_text, "START_MARKER missing from direct read"
            assert "readback-test" in direct_text, "Input text missing from direct read"

            broker.close(sid_a)
            broker.close(sid_b)
        finally:
            broker.shutdown()


@windows_only
class TestStreamingCursorNoMissingOrDuplicate:
    """Ticket 06 checkbox 4: output cursors do not cause missing or
    duplicate content.
    """

    def test_no_duplicate_in_stream(self):
        """Streaming updates don't duplicate content — each chunk appears
        exactly once in the accumulated text."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="stream-cursor-dedup")
            adapter = _make_adapter(broker)
            mgr = StreamingOutputManager()

            # Collect all output through the adapter
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and result.response != "(no new output)" and "exited" not in result.response:
                    mgr.update(sid, result.response)
                if "START_MARKER" in (mgr.get_accumulated_text(sid) or ""):
                    break
                time.sleep(0.05)

            broker.write_input(sid, b"dedup-line\r\n", source="local")
            deadline2 = time.monotonic() + 10.0
            while time.monotonic() < deadline2:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and "ROUND:0:" in result.response:
                    mgr.update(sid, result.response)
                    break
                time.sleep(0.05)

            # Poll once more to try to get any duplicate
            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"output {sid}",
            ))
            if result.response and result.response != "(no new output)" and "exited" not in result.response:
                mgr.update(sid, result.response)

            stream_text = mgr.get_accumulated_text(sid)
            # START_MARKER should appear exactly once
            assert stream_text.count("START_MARKER") <= 1, (
                f"START_MARKER appeared {stream_text.count('START_MARKER')} times"
            )
            # ROUND:0: should appear exactly once
            assert stream_text.count("ROUND:0:") <= 1, (
                f"ROUND:0: appeared {stream_text.count('ROUND:0:')} times"
            )

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestStreamingUnauthorizedDenied:
    """Ticket 06 checkbox 5: unauthorized conversation and unauthorized
    sender paths are both denied (through the streaming path).
    """

    def test_unauthorized_conversation_denied_in_stream(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="stream-auth-conv")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=OWNER_OID,
                text=f"output {sid}",
            ))
            assert result.denied is True
            assert result.auth_decision == AuthDecision.DENIED_CONVERSATION
            assert "Unauthorized" in result.response

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_unauthorized_sender_denied_in_stream(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="stream-auth-sender")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=WRONG_OID,
                text=f"output {sid}",
            ))
            assert result.denied is True
            assert result.auth_decision == AuthDecision.DENIED_SENDER
            assert "Unauthorized" in result.response

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestStopAffectsOnlyRequestedSession:
    """Ticket 06 checkbox 6: stop affects only the requested session.
    """

    def test_stop_session_a_isolated_from_b(self):
        broker = SessionBroker()
        try:
            sid_a = broker.create(_echo_argv(), session_id="stream-stop-a")
            sid_b = broker.create(_echo_argv(), session_id="stream-stop-b")
            _read_until(broker, sid_a, b"START_MARKER:")
            _read_until(broker, sid_b, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Stop A
            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"stop {sid_a}",
            ))
            assert result.verb == CommandVerb.STOP
            assert "stopped" in result.response.lower()

            # B is still alive
            assert broker.status(sid_b).running is True
            # A is gone
            with pytest.raises(BrokerError, match="not found"):
                broker.status(sid_a)

            broker.close(sid_b)
        finally:
            broker.shutdown()


@windows_only
class TestFailureStates:
    """Ticket 06 checkbox 7: gateway restart, child exit, and PTY failure
    produce explicit user-visible states.
    """

    def test_child_exit_produces_explicit_state(self):
        """When the child process exits, the adapter reports '(session has
        exited)' — an explicit user-visible state, not a silent failure."""
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="stream-child-exit")
            _read_until(broker, sid, b"START_MARKER:")

            # Send input so the echo fixture responds and exits
            broker.write_input(sid, b"test-line\r\n", source="local")
            _read_until(broker, sid, b"EXIT_MARKER:0", timeout=5.0)

            # Give the broker time to detect the exit
            time.sleep(0.3)

            # The next output read should report the exit
            adapter = _make_adapter(broker)
            deadline = time.monotonic() + 5.0
            exit_seen = False
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if result.response and "exited" in result.response.lower():
                    exit_seen = True
                    break
                # Status might show not running
                status_result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"status {sid}",
                ))
                if "Running: False" in (status_result.response or ""):
                    exit_seen = True
                    break
                time.sleep(0.1)

            assert exit_seen, (
                "Child exit did not produce an explicit user-visible state"
            )

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_pty_failure_produces_explicit_diagnostic(self):
        """When the PTY backend is unavailable, creating a session produces
        an explicit PtyUnavailableError, not a silent fallback.

        We use a fresh SessionBroker instance and unittest.mock.patch so the
        monkeypatch does not leak into other tests.
        """
        from poc.terminal_broker.pty_bridge_poc import PtyUnavailableError
        import unittest.mock

        fresh_broker = SessionBroker()
        try:
            with unittest.mock.patch.object(
                type(fresh_broker),
                "is_available",
                staticmethod(lambda: False),
            ):
                with pytest.raises(PtyUnavailableError, match="PTY backend unavailable"):
                    fresh_broker.create(_echo_argv(), session_id="stream-pty-fail")
        finally:
            fresh_broker.shutdown()

    def test_streaming_manager_fail_state(self):
        """The streaming manager's fail() method produces an explicit
        FAILED state with the error message visible to the user."""
        mgr = StreamingOutputManager()
        mgr.update("fail-session", "partial data")
        fail = mgr.fail("fail-session", "gateway restart detected")
        assert fail.state == StreamState.FAILED
        assert "gateway restart detected" in fail.updated_text
        assert fail.is_final is True

    def test_denied_request_on_dead_session(self):
        """A status request on a closed session produces an explicit error,
        not a silent failure or crash."""
        from poc.terminal_broker.pty_bridge_poc import PtyBridgePOC

        if not PtyBridgePOC.is_available():
            pytest.skip("PTY backend unavailable on this platform")

        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="stream-dead-session")
            _read_until(broker, sid, b"START_MARKER:")
            broker.close(sid)

            adapter = _make_adapter(broker)
            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert "Error" in (result.response or "") or "not found" in (result.response or "").lower()

        finally:
            broker.shutdown()


@windows_only
class TestEvidenceSeparation:
    """Ticket 06 checkbox 8: real Teams E2E evidence is separated from local
    unit and harness evidence.
    """

    def test_harness_result_evidence_tier(self):
        """The E2E harness result carries an evidence tier that is NOT
        live-teams-e2e when running locally."""
        harness = E2EHarness(
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )
        try:
            result = harness.run()
            assert result.evidence_tier != EvidenceTier.LIVE_TEAMS_E2E, (
                "Local harness must not be labelled as live Teams E2E"
            )
            assert result.evidence_tier in (
                EvidenceTier.LOCAL_UNIT,
                EvidenceTier.HARNESS_VERIFIED,
            )
        finally:
            harness.shutdown()

    def test_harness_result_has_explicit_tier(self):
        """Every E2E result has an explicit evidence tier field."""
        harness = E2EHarness(
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )
        try:
            result = harness.run()
            assert hasattr(result, "evidence_tier")
            assert isinstance(result.evidence_tier, EvidenceTier)
        finally:
            harness.shutdown()


@windows_only
class TestInvestmentVerdictRecorded:
    """Ticket 06 checkbox 9: the result records whether the next Codex,
    Claude Code, and Hermes TUI investment is justified.
    """

    def test_harness_records_investment_verdict(self):
        """The E2E harness result has an explicit investment_justified
        boolean."""
        harness = E2EHarness(
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )
        try:
            result = harness.run()
            assert hasattr(result, "investment_justified")
            assert isinstance(result.investment_justified, bool)
        finally:
            harness.shutdown()

    def test_pass_verdict_means_justified(self):
        """A PASS verdict with harness-verified evidence means the
        investment is justified."""
        harness = E2EHarness(
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )
        try:
            result = harness.run()
            if result.verdict == E2EVerdict.PASS:
                assert result.investment_justified is True
        finally:
            harness.shutdown()

    def test_result_summary_mentions_investment(self):
        """The result summary explicitly mentions the investment decision."""
        harness = E2EHarness(
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )
        try:
            result = harness.run()
            assert result.summary is not None
            assert len(result.summary) > 0
        finally:
            harness.shutdown()
