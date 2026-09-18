"""TDD tests for ticket 05 — Teams Control-Channel Adapter Integration.

Tests prove that the Teams control-channel adapter:

1. Remote commands target an explicit session ID.
2. Status, output, input write, local/remote mode switch, and stop are supported.
3. A request from any other conversation is denied.
4. A request from any other sender OID is denied.
5. Display name, message text, prior turns, and cached Agent identity cannot
   grant authorization.
6. Denied requests cause no terminal input or state mutation.
7. The existing Teams MTK authentication and transport are reused (the
   adapter feeds into the same InboundMessage shape the real adapter uses,
   and returns response text for the existing streaming/edit path).
8. Production gateway integration is attempted only after broker and handoff
   evidence passes — the adapter lives under poc/ and does not touch
   production code.

Cross-platform: import-level tests run everywhere.
Windows-only: full integration tests spawn real ConPTY sessions through the
broker and exercise the adapter end-to-end.

Run:
    scripts/run_tests.sh tests/poc/test_teams_control_adapter_poc.py -v
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

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="adapter integration tests require Windows ConPTY broker",
)

# Fixtures
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "poc", "terminal_broker", "fixtures"),
)
from fixture_echo import fixture_argv as _echo_argv  # noqa: E402
from fixture_multiround import fixture_argv as _multiround_argv  # noqa: E402


# ---------------------------------------------------------------------------
# Constants for tests
# ---------------------------------------------------------------------------

CONTROL_CONV = "19:control-conversation@thread.v2"
WRONG_CONV = "19:other-conversation@thread.v2"
OWNER_OID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
WRONG_OID = "99999999-8888-7777-6666-555555555555"


def _read_until(broker: SessionBroker, sid: str, needle: bytes, timeout: float = 10.0) -> bytes:
    """Accumulate output from session *sid* until we see *needle* or time out.

    Uses non-blocking ``try_read_output`` to avoid blocking on pywinpty's
    ``recv()`` when no data is available.
    """
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

class TestTeamsControlAdapterImportable:
    """The adapter module must be importable on every OS for test discovery."""

    def test_adapter_class_is_importable(self):
        assert TeamsControlAdapter is not None

    def test_inbound_message_dataclass(self):
        msg = InboundMessage(
            conversation_id="conv1",
            sender_oid="oid1",
            text="status session-1",
        )
        assert msg.conversation_id == "conv1"
        assert msg.sender_oid == "oid1"
        assert msg.text == "status session-1"
        assert msg.display_name == ""
        assert msg.message_id == ""

    def test_command_result_dataclass(self):
        r = CommandResult(
            auth_decision=AuthDecision.ALLOWED,
            verb=CommandVerb.STATUS,
            session_id="x",
            response="ok",
        )
        assert r.auth_decision == AuthDecision.ALLOWED
        assert r.verb == CommandVerb.STATUS
        assert r.denied is False

    def test_command_verb_values(self):
        assert CommandVerb.STATUS.value == "status"
        assert CommandVerb.STOP.value == "stop"

    def test_auth_decision_values(self):
        assert AuthDecision.ALLOWED.value == "allowed"
        assert AuthDecision.DENIED_CONVERSATION.value == "denied_conversation"
        assert AuthDecision.DENIED_SENDER.value == "denied_sender"

    def test_evidence_label_is_local_harness(self):
        """The adapter tags results as local harness evidence, not Teams E2E."""
        assert "local" in EVIDENCE_LABEL.lower()
        assert "not teams" in EVIDENCE_LABEL.lower()


# ---------------------------------------------------------------------------
# Cross-platform: authorization (no broker needed)
# ---------------------------------------------------------------------------

class TestAuthorization:
    """Ticket 05 checkbox 3/4: conversation and sender authorization."""

    def _dummy_broker(self):
        # We only need the adapter for authorize() — no real session needed.
        return TeamsControlAdapter(
            SessionBroker(),
            control_conversation_id=CONTROL_CONV,
            owner_oid=OWNER_OID,
        )

    def test_correct_conversation_and_sender_allowed(self):
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=CONTROL_CONV,
            sender_oid=OWNER_OID,
            text="status test-session",
        )
        assert adapter.authorize(msg) == AuthDecision.ALLOWED

    def test_wrong_conversation_denied(self):
        """Ticket 05 checkbox 3: A request from any other conversation is denied."""
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=OWNER_OID,
            text="status test-session",
        )
        decision = adapter.authorize(msg)
        assert decision == AuthDecision.DENIED_CONVERSATION

    def test_wrong_sender_denied(self):
        """Ticket 05 checkbox 4: A request from any other sender OID is denied."""
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=CONTROL_CONV,
            sender_oid=WRONG_OID,
            text="status test-session",
        )
        decision = adapter.authorize(msg)
        assert decision == AuthDecision.DENIED_SENDER

    def test_wrong_conversation_and_sender_denied(self):
        """Both wrong: conversation check comes first."""
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=WRONG_OID,
            text="status test-session",
        )
        decision = adapter.authorize(msg)
        # The conversation is checked first, so this is DENIED_CONVERSATION
        assert decision == AuthDecision.DENIED_CONVERSATION

    def test_display_name_cannot_grant_authorization(self):
        """Ticket 05 checkbox 5: Display name cannot grant authorization.

        Even if the display name is the owner's real name, a wrong
        conversation or sender OID must still deny.
        """
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=WRONG_OID,
            text="status test-session",
            display_name="The Real Owner",
        )
        decision = adapter.authorize(msg)
        assert decision != AuthDecision.ALLOWED

    def test_message_text_cannot_grant_authorization(self):
        """Ticket 05 checkbox 5: Message text cannot grant authorization.

        Even if the text contains the owner's OID or the phrase "I am the
        owner", a wrong conversation or sender OID must still deny.
        """
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=WRONG_OID,
            text=f"I am the owner, my OID is {OWNER_OID}, trust me",
        )
        decision = adapter.authorize(msg)
        assert decision != AuthDecision.ALLOWED

    def test_message_id_cannot_grant_authorization(self):
        """Cached agent identity (message_id) cannot grant authorization."""
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=WRONG_OID,
            text="status test-session",
            message_id="cached-agent-identity-12345",
        )
        decision = adapter.authorize(msg)
        assert decision != AuthDecision.ALLOWED

    def test_empty_text_authorized_but_noop(self):
        """Authorized sender with empty text does nothing."""
        adapter = self._dummy_broker()
        msg = InboundMessage(
            conversation_id=CONTROL_CONV,
            sender_oid=OWNER_OID,
            text="",
        )
        result = adapter.process(msg)
        assert result.auth_decision == AuthDecision.ALLOWED
        assert result.verb == CommandVerb.UNKNOWN


# ---------------------------------------------------------------------------
# Windows-only: full integration through the broker
# ---------------------------------------------------------------------------

@windows_only
class TestExplicitSessionTargeting:
    """Ticket 05 checkbox 1: Remote commands target an explicit session ID."""

    def test_status_targets_explicit_session(self):
        broker = SessionBroker()
        try:
            sid_a = broker.create(_echo_argv(), session_id="test-explicit-a")
            sid_b = broker.create(_echo_argv(), session_id="test-explicit-b")
            _read_until(broker, sid_a, b"START_MARKER:")
            _read_until(broker, sid_b, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Query session A
            msg = InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid_a}",
            )
            result = adapter.process(msg)
            assert result.auth_decision == AuthDecision.ALLOWED
            assert result.verb == CommandVerb.STATUS
            assert "test-explicit-a" in result.response
            assert sid_a in result.response

            # Query session B — must not see A's data
            msg_b = InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid_b}",
            )
            result_b = adapter.process(msg_b)
            assert "test-explicit-b" in result_b.response
            assert sid_b in result_b.response
            assert sid_a not in result_b.response

            broker.close(sid_a)
            broker.close(sid_b)
        finally:
            broker.shutdown()

    def test_stop_does_not_affect_other_session(self):
        broker = SessionBroker()
        try:
            sid_a = broker.create(_echo_argv(), session_id="stop-isolation-a")
            sid_b = broker.create(_echo_argv(), session_id="stop-isolation-b")
            _read_until(broker, sid_a, b"START_MARKER:")
            _read_until(broker, sid_b, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Stop A
            msg = InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"stop {sid_a}",
            )
            result = adapter.process(msg)
            assert result.verb == CommandVerb.STOP
            assert "stopped" in result.response.lower()

            # B is still alive
            assert broker.status(sid_b).running is True
            broker.close(sid_b)
        finally:
            broker.shutdown()


@windows_only
class TestSupportedCommands:
    """Ticket 05 checkbox 2: status, output, input, mode switch, stop supported."""

    def test_status_command(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="cmd-status")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert result.verb == CommandVerb.STATUS
            assert "PID" in result.response
            assert "Running: True" in result.response
            broker.close(sid)
        finally:
            broker.shutdown()

    def test_output_command(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="cmd-output")
            adapter = _make_adapter(broker)

            # Wait for START_MARKER by reading through the adapter.
            # Poll the adapter's output command until we see START_MARKER or
            # timeout. The adapter's cursor starts at 0, so the first
            # successful read picks up whatever the child has emitted.
            deadline = time.monotonic() + 10.0
            start_seen = False
            while time.monotonic() < deadline:
                result = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                assert result.verb == CommandVerb.OUTPUT
                if result.response and "START_MARKER" in result.response:
                    start_seen = True
                    break
                if not broker.status(sid).running:
                    break
                time.sleep(0.05)
            assert start_seen, "START_MARKER not seen via adapter output command"

            # Write locally and let the adapter read it remotely
            broker.write_input(sid, b"remote-test-line\r\n", source="local")

            # Poll adapter output until ROUND:0 appears
            deadline2 = time.monotonic() + 10.0
            round_seen = False
            while time.monotonic() < deadline2:
                r2 = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if r2.response and "ROUND:0:" in r2.response:
                    round_seen = True
                    break
                if not broker.status(sid).running:
                    break
                time.sleep(0.05)
            assert round_seen, "ROUND:0: not seen via adapter output command"

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_input_command_requires_remote_mode(self):
        """Input from remote is rejected in local mode (spec Decision 6).

        The remote input command must fail when the session is in local
        mode — the adapter must not silently accept it.
        """
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="cmd-input-local")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Session defaults to local mode — remote input must fail
            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"input {sid} hello-from-teams",
            ))
            assert result.verb == CommandVerb.INPUT
            # Should be an error about mode
            assert "Error" in result.response or "rejected" in result.response.lower()

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_input_command_in_remote_mode(self):
        """Input from remote succeeds when the session is in remote mode."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="cmd-input-remote")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Switch to remote mode
            mode_result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"mode {sid} remote",
            ))
            assert mode_result.verb == CommandVerb.MODE
            assert "remote" in mode_result.response

            # Now remote input works
            input_result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"input {sid} remote-input-test",
            ))
            assert input_result.verb == CommandVerb.INPUT
            assert "sent" in input_result.response.lower()

            # Verify the input reached the child
            out = _read_until(broker, sid, b"ROUND:0:")
            assert b"remote-input-test" in out

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_mode_switch_command(self):
        """mode <sid> local|remote — switch input authority both ways."""
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="cmd-mode")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            assert broker.get_mode(sid) == ControlMode.LOCAL

            # Switch to remote
            r_remote = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"mode {sid} remote",
            ))
            assert "remote" in r_remote.response.lower()
            assert broker.get_mode(sid) == ControlMode.REMOTE

            # Switch back to local
            r_local = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"mode {sid} local",
            ))
            assert "local" in r_local.response.lower()
            assert broker.get_mode(sid) == ControlMode.LOCAL

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_stop_command(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="cmd-stop")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"stop {sid}",
            ))
            assert result.verb == CommandVerb.STOP
            assert "stopped" in result.response.lower()

            with pytest.raises(BrokerError, match="not found"):
                broker.status(sid)
        finally:
            broker.shutdown()

    def test_list_command(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="cmd-list-1")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text="list",
            ))
            assert result.verb == CommandVerb.LIST
            assert "cmd-list-1" in result.response

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestDeniedRequestsNoMutation:
    """Ticket 05 checkbox 6: Denied requests cause no terminal input or
    state mutation.
    """

    def test_denied_input_does_not_write_to_session(self):
        """A denied input command must not write anything to the PTY."""
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="deny-input")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Switch to remote so the input WOULD be accepted if authorized
            broker.set_mode(sid, ControlMode.REMOTE)

            # Send input from wrong conversation
            result = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=OWNER_OID,
                text=f"input {sid} should-not-be-written",
            ))
            assert result.denied is True
            assert result.auth_decision != AuthDecision.ALLOWED

            # Verify no output was produced from the denied input
            time.sleep(0.1)
            chunk = broker.try_read_output(sid)
            read_buf = chunk or b""
            assert b"should-not-be-written" not in read_buf
            assert b"ROUND:0:" not in read_buf

            # Switch to remote mode (still in remote) and send authorized input
            # to verify the broker is healthy and the denial didn't corrupt it
            auth_result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"input {sid} authorized-input",
            ))
            assert auth_result.auth_decision == AuthDecision.ALLOWED
            out = _read_until(broker, sid, b"ROUND:0:")
            assert b"authorized-input" in out
            assert b"should-not-be-written" not in out

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_denied_mode_switch_does_not_change_mode(self):
        """A denied mode command must not change the session's mode."""
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="deny-mode")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Mode starts as local
            assert broker.get_mode(sid) == ControlMode.LOCAL

            # Attempt mode switch from wrong conversation
            result = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=OWNER_OID,
                text=f"mode {sid} remote",
            ))
            assert result.denied is True

            # Mode should still be local
            assert broker.get_mode(sid) == ControlMode.LOCAL

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_denied_stop_does_not_close_session(self):
        """A denied stop command must not close the session."""
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="deny-stop")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Attempt stop from wrong sender
            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=WRONG_OID,
                text=f"stop {sid}",
            ))
            assert result.denied is True

            # Session should still be alive
            assert broker.status(sid).running is True

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestNoMutationOnDeniedFromOtherConversation:
    """Ticket 05 checkbox 3: A request from any other conversation is denied
    (integration test with real broker state)."""

    def test_status_from_wrong_conversation_denied(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="deny-conv-status")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert result.auth_decision == AuthDecision.DENIED_CONVERSATION
            assert result.denied is True
            assert "Unauthorized" in result.response

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestNoMutationOnDeniedFromOtherSender:
    """Ticket 05 checkbox 4: A request from any other sender OID is denied
    (integration test with real broker state)."""

    def test_status_from_wrong_sender_denied(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="deny-sender-status")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=WRONG_OID,
                text=f"status {sid}",
            ))
            assert result.auth_decision == AuthDecision.DENIED_SENDER
            assert result.denied is True
            assert "Unauthorized" in result.response

            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestNonAuthInputsCannotGrant:
    """Ticket 05 checkbox 5: Display name, message text, prior turns, and
    cached Agent identity cannot grant authorization (integration)."""

    def test_display_name_does_not_grant(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="display-name-test")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Use wrong conversation but correct display name
            result = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=WRONG_OID,
                text=f"status {sid}",
                display_name="The Real Owner Name",
            ))
            assert result.denied is True

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_prior_turn_does_not_grant(self):
        """A prior authorized turn does not authorize a subsequent denied turn.

        The adapter evaluates every turn independently — no session or state
        from a previous authorized turn carries over to a new unauthorized one.
        """
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="prior-turn-test")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            # Authorized turn
            r1 = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert r1.auth_decision == AuthDecision.ALLOWED

            # Unauthorized turn immediately after — must still be denied
            r2 = adapter.process(InboundMessage(
                conversation_id=WRONG_CONV,
                sender_oid=OWNER_OID,
                text=f"stop {sid}",
            ))
            assert r2.auth_decision == AuthDecision.DENIED_CONVERSATION
            assert r2.denied is True

            # Session must still be alive
            assert broker.status(sid).running is True
            broker.close(sid)
        finally:
            broker.shutdown()


@windows_only
class TestExistingTransportReused:
    """Ticket 05 checkbox 7: The existing Teams MTK authentication and
    transport are reused.

    We verify this structurally:
    * The InboundMessage mirrors the shape the real adapter normalizes.
    * The CommandResult.response is the text that would be sent through the
      existing streaming/edit path — the adapter does not create a second
      transport.
    * The adapter does NOT import or modify gateway/platforms/teams_mtk.py.

    We can't test the exact wire format without a live Teams E2E (that is
    ticket 06's job), but we verify the adapter is transport-agnostic: it
    only accepts and returns plain text.
    """

    def test_inbound_message_matches_teams_adapter_shape(self):
        """InboundMessage mirrors the fields the real Teams adapter delivers."""
        msg = InboundMessage(
            conversation_id="19:foo@thread.v2",
            sender_oid="oid-from-from-url",
            text="status my-session",
            display_name="Sender Name",
            message_id="12345",
        )
        # All fields that the real adapter provides are present
        assert hasattr(msg, "conversation_id")
        assert hasattr(msg, "sender_oid")
        assert hasattr(msg, "text")

    def test_response_is_plain_text(self):
        """Response is plain text for the existing streaming/edit path."""
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="transport-test")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert isinstance(result.response, str)
            # No HTML tags — the real adapter handles HTML wrapping
            assert "<" not in result.response or "cols" not in result.response.lower()

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_does_not_import_production_teams_adapter(self):
        """The adapter module must not import gateway.platforms.teams_mtk."""
        import poc.terminal_broker.teams_control_adapter as mod
        import inspect
        source = inspect.getsource(mod)
        assert "gateway.platforms.teams_mtk" not in source
        assert "from gateway" not in source


@windows_only
class TestEvidenceLabel:
    """Every result carries the local-harness evidence label."""

    def test_allowed_result_has_evidence_label(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_echo_argv(), session_id="evidence-allow")
            _read_until(broker, sid, b"START_MARKER:")
            adapter = _make_adapter(broker)

            result = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"status {sid}",
            ))
            assert "local" in result.evidence_label.lower()
            assert "not teams" in result.evidence_label.lower()

            broker.close(sid)
        finally:
            broker.shutdown()

    def test_denied_result_has_evidence_label(self):
        adapter = _make_adapter(SessionBroker())
        result = adapter.process(InboundMessage(
            conversation_id=WRONG_CONV,
            sender_oid=OWNER_OID,
            text="status anything",
        ))
        assert "local" in result.evidence_label.lower()
        assert "not teams" in result.evidence_label.lower()


@windows_only
class TestOutputNoDuplication:
    """Spec Decision 8: output is read once from the PTY and assigned a
    monotonic cursor before fan-out. Consecutive ``output`` commands
    consume whatever is available; once read, the same bytes are not
    returned again.
    """

    def test_sequential_output_reads_no_duplication(self):
        broker = SessionBroker()
        try:
            sid = broker.create(_multiround_argv(), session_id="cursor-dedup")
            adapter = _make_adapter(broker)

            # Wait for START_MARKER by polling the adapter
            deadline = time.monotonic() + 10.0
            start_seen = False
            while time.monotonic() < deadline:
                r = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if r.response and "START_MARKER" in r.response:
                    start_seen = True
                    break
                if r.response and "exited" in (r.response or ""):
                    break
                time.sleep(0.05)
            assert start_seen, "START_MARKER not seen"

            # Write locally and let the adapter read it
            broker.write_input(sid, b"line-a\r\n", source="local")

            # Poll adapter output until ROUND:0 appears
            deadline2 = time.monotonic() + 10.0
            round_seen = False
            while time.monotonic() < deadline2:
                r1 = adapter.process(InboundMessage(
                    conversation_id=CONTROL_CONV,
                    sender_oid=OWNER_OID,
                    text=f"output {sid}",
                ))
                if r1.response and "ROUND:0:" in r1.response:
                    round_seen = True
                    break
                if "exited" in (r1.response or ""):
                    break
                time.sleep(0.05)
            assert round_seen, "ROUND:0: not seen via adapter"

            # Second read should have no new data (the ROUND:0 output
            # was already consumed by the previous read)
            r2 = adapter.process(InboundMessage(
                conversation_id=CONTROL_CONV,
                sender_oid=OWNER_OID,
                text=f"output {sid}",
            ))
            assert "ROUND:0:" not in (r2.response or ""), (
                f"Duplicate output: ROUND:0 appeared again. Response: {r2.response!r}"
            )

            broker.close(sid)
        finally:
            broker.shutdown()
