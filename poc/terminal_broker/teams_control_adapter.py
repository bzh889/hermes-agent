"""POC Teams Control-Channel Adapter Integration — ticket 05.

Windows-only throwaway POC for the Teams Terminal Remote Control spec.
This module sits above ``session_broker.SessionBroker`` (ticket 02) and
bridges Teams-format inbound messages to the broker's terminal control
contract, enforcing per-turn authorization against the exact configured
control conversation and the owner's immutable sender OID.

What this module does:

* Accepts an :class:`InboundMessage` that mirrors the shape a Teams MTK
  gateway adapter would deliver (conversation_id, sender_oid, text).
* Authorizes every turn by checking ``conversation_id == control_conversation_id``
  AND ``sender_oid == owner_oid``. Nothing else is an authorization input
  (spec Decision 13: display names, message text, prior turns, and cached
  agent identity cannot grant authorization).
* Parses a narrow command vocabulary (spec Decision 14): status, output,
  input, mode switch, and stop — each targeting an explicit session ID.
* Routes authorized commands to the :class:`SessionBroker` and returns a
  :class:`CommandResult` with the text that would be sent back through the
  existing Teams streaming/edit transport.
* Tags every result with an evidence label making clear this is local
  harness evidence, not live Teams E2E evidence (spec Decision 15).

What this module does NOT do:

* It does NOT modify the production Teams adapter (``gateway/platforms/teams_mtk.py``)
  or production gateway routing (spec Decision 1, Out of Scope).
* It does NOT introduce a second Teams authentication or message pipeline
  (spec Decision 12). The adapter reuses the Teams MTK transport shape —
  the inbound message dict mirrors what the real adapter normalizes.
* It does NOT perform live Teams network calls. That is ticket 06.

Authorization model (spec Decision 13, ADR 0003):

  allowed = (conversation_id == control_conversation_id)
         AND (sender_oid == owner_oid)

  Denied inputs: different conversation, different sender OID, display
  name, message text, prior turn history, cached agent identity.

  A denied request causes NO terminal input and NO state mutation.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from poc.terminal_broker.session_broker import (
    BrokerError,
    ControlMode,
    SessionBroker,
)


__all__ = [
    "TeamsControlAdapter",
    "InboundMessage",
    "CommandResult",
    "CommandVerb",
    "AuthDecision",
]


# ---------------------------------------------------------------------------
# Evidence labels (spec Decision 15)
# ---------------------------------------------------------------------------

EVIDENCE_LABEL = "local harness evidence — not Teams E2E evidence"
SOURCE_CONFIRMED = "source-confirmed"
HARNESS_VERIFIED = "harness-verified"
LIVE_TEAMS_E2E = "live-teams-e2e"
UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class CommandVerb(Enum):
    """The narrow remote command vocabulary (spec Decision 14).

    Every command targets an explicit session ID — there is no implicit
    "current session" (spec User Story 17, Implementation Decision 5).
    """
    STATUS = "status"
    OUTPUT = "output"
    INPUT = "input"
    MODE = "mode"
    STOP = "stop"
    LIST = "list"       # bonus: list session IDs — read-only, safe
    UNKNOWN = "unknown"


class AuthDecision(Enum):
    """Outcome of per-turn authorization."""
    ALLOWED = "allowed"
    DENIED_CONVERSATION = "denied_conversation"
    DENIED_SENDER = "denied_sender"


@dataclass(frozen=True)
class InboundMessage:
    """Simulated Teams inbound message — mirrors the normalized shape that
    the production Teams MTK adapter delivers to its message dispatcher.

    Fields:
      conversation_id: the exact Teams conversation ID (e.g. ``19:foo@thread``)
      sender_oid: the sender's immutable AAD org object ID
      text: the plain-text message body (after HTML stripping)
      display_name: the sender's display name — explicitly NOT an auth input
      message_id: the Teams message ID for dedup / edit correlation

    The production adapter's ``_teams_sender_id()`` normalizes the ``from``
    URL to the orgid OID; we accept the already-normalized value here.
    """
    conversation_id: str
    sender_oid: str
    text: str
    display_name: str = ""
    message_id: str = ""


@dataclass
class CommandResult:
    """Result of processing one inbound message through the adapter.

    The ``response`` field is the text that would be sent back through the
    existing Teams streaming/edit transport. It is ``None`` when there is
    no reply (e.g. an empty message that should be ignored silently).
    """
    auth_decision: AuthDecision
    verb: CommandVerb
    session_id: str
    response: Optional[str]
    evidence_label: str = EVIDENCE_LABEL
    denied: bool = False
    detail: str = ""


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

# Command format (line-oriented, whitespace-delimited):
#   status <session_id>
#   output <session_id>
#   input <session_id> <text...>
#   mode <session_id> <local|remote>
#   stop <session_id>
#   list
#
# Commands are case-insensitive for the verb. Session IDs are case-sensitive
# opaque tokens (UUIDs or custom strings from the broker).

_VERB_PATTERN = re.compile(r"^\s*(\w+)\s*(.*)$", re.DOTALL)


def _parse_command(text: str) -> tuple[CommandVerb, str, str]:
    """Parse a command line into (verb, session_id, remainder).

    Returns ``(CommandVerb.UNKNOWN, "", "")`` for empty or unparseable input.
    The remainder is the text after the session ID (used by ``input``).
    """
    if not text or not text.strip():
        return CommandVerb.UNKNOWN, "", ""

    m = _VERB_PATTERN.match(text.strip())
    if not m:
        return CommandVerb.UNKNOWN, "", ""

    verb_str = m.group(1).lower()
    rest = m.group(2).strip()

    # Map the verb token
    verb_map = {
        "status": CommandVerb.STATUS,
        "output": CommandVerb.OUTPUT,
        "input": CommandVerb.INPUT,
        "mode": CommandVerb.MODE,
        "stop": CommandVerb.STOP,
        "list": CommandVerb.LIST,
    }
    verb = verb_map.get(verb_str, CommandVerb.UNKNOWN)

    if verb == CommandVerb.UNKNOWN:
        return CommandVerb.UNKNOWN, "", ""

    if verb == CommandVerb.LIST:
        # No session ID needed
        return verb, "", ""

    # Extract session_id (first whitespace-delimited token)
    parts = rest.split(None, 1)
    if not parts:
        return verb, "", ""  # missing session ID

    session_id = parts[0]
    remainder = parts[1] if len(parts) > 1 else ""
    return verb, session_id, remainder


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TeamsControlAdapter:
    """Bridges Teams-format inbound messages to the Session Broker.

    Enforces per-turn authorization (spec Decision 13):
      * ``conversation_id`` must equal the configured ``control_conversation_id``.
      * ``sender_oid`` must equal the configured ``owner_oid``.
      * Nothing else can grant authorization.

    The adapter does NOT create sessions — session creation is a local
    operation (the PC owner starts the broker session from the local
    side). The remote Teams surface is limited to observing and controlling
    existing sessions (spec Decision 14, User Story 25).
    """

    def __init__(
        self,
        broker: SessionBroker,
        *,
        control_conversation_id: str,
        owner_oid: str,
    ) -> None:
        self._broker = broker
        self._control_conv_id = control_conversation_id
        self._owner_oid = owner_oid

    # -- authorization ---------------------------------------------------

    def authorize(self, msg: InboundMessage) -> AuthDecision:
        """Evaluate per-turn authorization (spec Decision 13).

        This is the *only* authorization gate. Display name, message text,
        prior turns, and cached agent identity are explicitly NOT inputs.

        Returns:
          * ``AuthDecision.ALLOWED`` — both conversation and sender match.
          * ``AuthDecision.DENIED_CONVERSATION`` — wrong conversation.
          * ``AuthDecision.DENIED_SENDER`` — right conversation, wrong sender
            (or wrong conversation AND wrong sender — the conversation is
            checked first per the spec's "exact control conversation" wording).
        """
        if msg.conversation_id != self._control_conv_id:
            return AuthDecision.DENIED_CONVERSATION
        if msg.sender_oid != self._owner_oid:
            return AuthDecision.DENIED_SENDER
        return AuthDecision.ALLOWED

    # -- dispatch --------------------------------------------------------

    def process(self, msg: InboundMessage) -> CommandResult:
        """Process one inbound message end-to-end.

        1. Authorize (per-turn).
        2. Parse the command.
        3. If authorized, dispatch to the broker.
        4. Return the response text for Teams delivery.

        A denied request causes no terminal input or state mutation
        (ticket 05 checkbox 6).
        """
        # Step 1: Authorize
        auth = self.authorize(msg)

        # Parse the command even for denied requests so the result reports
        # what the attempted verb was — but do NOT dispatch to the broker.
        verb, session_id, remainder = _parse_command(msg.text)

        if auth != AuthDecision.ALLOWED:
            detail = (
                f"Denied: conversation={msg.conversation_id != self._control_conv_id}, "
                f"sender={msg.sender_oid != self._owner_oid}"
            )
            return CommandResult(
                auth_decision=auth,
                verb=verb,
                session_id=session_id,
                response=self._denied_response(auth),
                evidence_label=EVIDENCE_LABEL,
                denied=True,
                detail=detail,
            )

        # Step 2: Dispatch to broker
        return self._dispatch(verb, session_id, remainder)

    # -- command handlers ------------------------------------------------

    def _dispatch(
        self,
        verb: CommandVerb,
        session_id: str,
        remainder: str,
    ) -> CommandResult:
        """Route a parsed, authorized command to the broker."""
        if verb == CommandVerb.STATUS:
            return self._cmd_status(session_id)
        if verb == CommandVerb.OUTPUT:
            return self._cmd_output(session_id)
        if verb == CommandVerb.INPUT:
            return self._cmd_input(session_id, remainder)
        if verb == CommandVerb.MODE:
            return self._cmd_mode(session_id, remainder)
        if verb == CommandVerb.STOP:
            return self._cmd_stop(session_id)
        if verb == CommandVerb.LIST:
            return self._cmd_list()
        # Should not reach here — _parse_command returns UNKNOWN for bad verbs
        return CommandResult(
            auth_decision=AuthDecision.ALLOWED,
            verb=CommandVerb.UNKNOWN,
            session_id=session_id,
            response=(
                "Unknown command. Supported: "
                "status <sid>, output <sid>, input <sid> <text>, "
                "mode <sid> <local|remote>, stop <sid>, list"
            ),
            evidence_label=EVIDENCE_LABEL,
        )

    def _cmd_status(self, session_id: str) -> CommandResult:
        """status <session_id> — report session state."""
        try:
            state = self._broker.status(session_id)
            d = state.to_dict()
            lines = [
                f"Session: {d['session_id']}",
                f"  PID: {d['pid']}",
                f"  Running: {d['running']}",
                f"  Mode: {d['control_mode']}",
                f"  Cols×Rows: {d['cols']}×{d['rows']}",
                f"  Uptime: {d['uptime']:.1f}s",
                f"  CWD: {d['cwd']}",
                f"  Output cursor: {d['output_cursor']}",
                f"  Last output: {d['last_output'][:200]!r}",
            ]
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.STATUS,
                session_id=session_id,
                response="\n".join(lines),
            )
        except BrokerError as exc:
            return self._broker_error(verb=CommandVerb.STATUS, sid=session_id, exc=exc)

    def _cmd_output(self, session_id: str) -> CommandResult:
        """output <session_id> — retrieve incremental output.

        Uses the adapter's per-session cursor to avoid duplicate delivery
        (spec Decision 8: output is read once and assigned a monotonic
        cursor before fan-out; consumers use the cursor to avoid duplicates).

        Uses a non-blocking read (``try_read_output``) so the adapter never
        blocks waiting for data — the Teams transport expects a prompt
        response, not a blocking wait.
        """
        try:
            # Non-blocking read: returns data, empty bytes, or None (EOF)
            data = self._broker.try_read_output(session_id)

            if data is None:
                return CommandResult(
                    auth_decision=AuthDecision.ALLOWED,
                    verb=CommandVerb.OUTPUT,
                    session_id=session_id,
                    response="(session has exited)",
                )

            if not data:
                return CommandResult(
                    auth_decision=AuthDecision.ALLOWED,
                    verb=CommandVerb.OUTPUT,
                    session_id=session_id,
                    response="(no new output)",
                )

            text = data.decode("utf-8", errors="replace")
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.OUTPUT,
                session_id=session_id,
                response=text,
            )
        except BrokerError as exc:
            return self._broker_error(verb=CommandVerb.OUTPUT, sid=session_id, exc=exc)

    def _cmd_input(self, session_id: str, text: str) -> CommandResult:
        """input <session_id> <text...> — write text input to the session.

        The adapter enforces remote-source mode: the session must be in
        ``remote`` mode for remote input to be accepted (spec Decision 6).
        A newline is appended so the child receives a complete line.
        """
        if not text:
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.INPUT,
                session_id=session_id,
                response="Error: input command requires text after the session ID.",
            )
        try:
            # Append a newline if the text doesn't already end with one
            payload = text if text.endswith("\n") else text + "\n"
            self._broker.write_input(
                session_id, payload.encode("utf-8"),
                source="remote",
            )
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.INPUT,
                session_id=session_id,
                response=f"Input sent to session '{session_id}'.",
            )
        except BrokerError as exc:
            # Mode mismatch or concurrent write — report clearly
            return self._broker_error(verb=CommandVerb.INPUT, sid=session_id, exc=exc)

    def _cmd_mode(self, session_id: str, mode_str: str) -> CommandResult:
        """mode <session_id> <local|remote> — switch input authority."""
        mode_str = mode_str.strip().lower()
        if mode_str not in ("local", "remote"):
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.MODE,
                session_id=session_id,
                response="Error: mode must be 'local' or 'remote'.",
            )
        try:
            mode = ControlMode.LOCAL if mode_str == "local" else ControlMode.REMOTE
            self._broker.set_mode(session_id, mode)
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.MODE,
                session_id=session_id,
                response=f"Session '{session_id}' switched to {mode_str} mode.",
            )
        except BrokerError as exc:
            return self._broker_error(verb=CommandVerb.MODE, sid=session_id, exc=exc)

    def _cmd_stop(self, session_id: str) -> CommandResult:
        """stop <session_id> — close the named session.

        Closing one session does not affect another (ticket 02 checkbox 8).
        """
        try:
            self._broker.close(session_id)
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.STOP,
                session_id=session_id,
                response=f"Session '{session_id}' stopped.",
            )
        except BrokerError as exc:
            return self._broker_error(verb=CommandVerb.STOP, sid=session_id, exc=exc)

    def _cmd_list(self) -> CommandResult:
        """list — enumerate session IDs. Read-only, safe."""
        ids = self._broker.list_sessions()
        if not ids:
            return CommandResult(
                auth_decision=AuthDecision.ALLOWED,
                verb=CommandVerb.LIST,
                session_id="",
                response="(no active sessions)",
            )
        return CommandResult(
            auth_decision=AuthDecision.ALLOWED,
            verb=CommandVerb.LIST,
            session_id="",
            response="Active sessions:\n" + "\n".join(f"  {sid}" for sid in ids),
        )

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _denied_response(auth: AuthDecision) -> str:
        """Response text for a denied request.

        The denial message does not reveal which check failed — a generic
        "unauthorized" avoids leaking information about the authorization
        model to a potential attacker.
        """
        return "Unauthorized: this conversation or sender is not permitted to control the terminal."

    @staticmethod
    def _broker_error(
        *, verb: CommandVerb, sid: str, exc: BrokerError,
    ) -> CommandResult:
        return CommandResult(
            auth_decision=AuthDecision.ALLOWED,
            verb=verb,
            session_id=sid,
            response=f"Error: {exc}",
            evidence_label=EVIDENCE_LABEL,
            detail=str(exc),
        )
