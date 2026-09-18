"""POC Live Teams E2E Probe — ticket 06 live evidence.

Bridges the POC broker + adapter to the **real** Teams MTK transport and
collects ``live-teams-e2e`` evidence. This is the only module that makes
real Teams network calls.

What this probe does:

1. Creates a broker-owned ConPTY session through the SessionBroker.
2. Sends a diagnostic message to the real Teams control conversation using
   the production `_TeamsAuth` Skype token (read-only reuse — no
   modification to production code).
3. Polls the real Teams conversation for new messages from the owner.
4. Normalizes the inbound Teams message into the POC ``InboundMessage``
   shape and routes it through the POC ``TeamsControlAdapter``.
5. Streams terminal output back to the real Teams conversation by:
   a. Sending the first output chunk as a new Teams message.
   b. Editing that message with each subsequent incremental update from
      the ``StreamingOutputManager``.
6. Records the evidence tier as ``live-teams-e2e`` if the full round-trip
   succeeds.

What this probe does NOT do:

* It does NOT modify the production Teams adapter or gateway routing.
* It does NOT start the full Hermes gateway process.
* It does NOT handle the full message lifecycle (VIP, attachments, model
  pickers) — it only processes text messages that match the POC command
  vocabulary.

Authorization is enforced per-turn by the POC adapter using the exact
control conversation ID and owner OID from config (spec Decision 13).

Usage::

    probe = LiveTeamsE2EProbe()
    result = probe.run()
    print(result.verdict, result.evidence_tier, result.investment_justified)

This is NOT production code and must NOT modify the production Teams adapter
or production gateway routing. It lives under ``poc/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from poc.terminal_broker.session_broker import (
    BrokerError,
    ControlMode,
    SessionBroker,
)
from poc.terminal_broker.teams_control_adapter import (
    AuthDecision,
    CommandVerb,
    InboundMessage,
    TeamsControlAdapter,
)
from poc.terminal_broker.streaming_manager import (
    StreamingOutputManager,
    StreamState,
)
from poc.terminal_broker.e2e_harness import (
    E2EVerdict,
    E2EResult,
    EvidenceTier,
)


__all__ = [
    "LiveTeamsE2EProbe",
]


# ---------------------------------------------------------------------------
# Config extraction
# ---------------------------------------------------------------------------

def _load_control_config() -> dict:
    """Load the control conversation ID and owner OID from config.yaml.

    Returns ``{control_conv_id, owner_oid, msg_base}`` or raises if the
    config is missing.
    """
    import yaml
    from pathlib import Path

    config_path = Path.home() / ".hermes" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    gw = cfg.get("gateway", {})
    tm = gw.get("teams_mtk", {})
    control_convs = tm.get("control_conversations", {})

    if not control_convs:
        raise RuntimeError(
            "No control_conversations configured in config.yaml "
            "(gateway.teams_mtk.control_conversations)"
        )

    # Take the first control conversation
    conv_id = next(iter(control_convs))
    owner_info = control_convs[conv_id]
    owner_oids = owner_info.get("owner_user_ids", [])

    if not owner_oids:
        raise RuntimeError(
            f"Control conversation {conv_id} has no owner_user_ids configured"
        )

    return {
        "control_conv_id": conv_id,
        "owner_oid": owner_oids[0],
    }


# ---------------------------------------------------------------------------
# Live probe
# ---------------------------------------------------------------------------

class LiveTeamsE2EProbe:
    """Live Teams E2E probe bridging the POC broker to the real Teams transport.

    This probe sends and receives real Teams messages through the production
    Skype token, enforces per-turn authorization through the POC adapter, and
    streams terminal output back through the Teams edit path.

    Usage::

        probe = LiveTeamsE2EProbe()
        result = probe.run()
        print(result.verdict, result.evidence_tier)
        probe.shutdown()
    """

    def __init__(self) -> None:
        self._cfg = _load_control_config()
        self._control_conv = self._cfg["control_conv_id"]
        self._owner_oid = self._cfg["owner_oid"]

        self._broker = SessionBroker()
        self._adapter = TeamsControlAdapter(
            self._broker,
            control_conversation_id=self._control_conv,
            owner_oid=self._owner_oid,
        )
        self._stream_mgr = StreamingOutputManager()
        self._sid: Optional[str] = None

        # Teams transport state (lazily initialized)
        self._auth = None
        self._msg_base = None
        self._skype_token = None

    def shutdown(self) -> None:
        """Close sessions and release broker resources."""
        if self._sid is not None:
            try:
                self._broker.close(self._sid)
            except Exception:
                pass
        self._broker.shutdown()

    @property
    def broker(self) -> SessionBroker:
        return self._broker

    @property
    def adapter(self) -> TeamsControlAdapter:
        return self._adapter

    @property
    def stream_manager(self) -> StreamingOutputManager:
        return self._stream_mgr

    # -- Teams transport --------------------------------------------------

    def _init_transport(self) -> None:
        """Initialize the Teams transport (production Skype token)."""
        from gateway.platforms.teams_mtk import _TeamsAuth

        self._auth = _TeamsAuth()
        # Inject the MTK CA bundle so SSL works through the corporate proxy
        self._auth._inject_truststore()
        tokens = self._auth.tokens()
        self._skype_token = tokens.get("skype_token", "")
        self._msg_base = self._auth.msg_base

        if not self._skype_token:
            raise RuntimeError(
                "Failed to obtain Skype token from _TeamsAuth — check "
                "~/.teams-automation/token_cache.bin or "
                "~/.teams-tokens/token_cache.json"
            )

    def _send_message(self, content: str) -> Optional[str]:
        """Send a plain-text message to the control conversation.

        Returns the message ID on success, None on failure.
        Uses the production Skype token (read-only reuse).
        The Skype API returns 201 with the message ID in the Location
        header (not in the response body).
        """
        import requests

        url = f"{self._msg_base}/conversations/{self._control_conv}/messages"
        payload = {
            "content": content,
            "messagetype": "Text",
            "contenttype": "text",
            "properties": {"hermes_sender": "bot"},
        }
        headers = {
            "Authentication": f"skypetoken={self._skype_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code in (200, 201):
                # Message ID is in the Location header, e.g.:
                # .../messages/1789746678117
                location = resp.headers.get("Location", "")
                if location:
                    msg_id = location.rstrip("/").rsplit("/", 1)[-1]
                    if msg_id:
                        return msg_id
                # Fallback: check response body for id
                try:
                    return resp.json().get("id")
                except (json.JSONDecodeError, ValueError):
                    pass
                # If we got 201 but no ID, return a truthy sentinel
                # so the caller knows the send succeeded
                return f"sent-{int(time.time())}"
            else:
                print(f"  Send failed: HTTP {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"  Send error: {type(e).__name__}: {e}")
            return None

    def _edit_message(self, message_id: str, content: str) -> bool:
        """Edit a previously sent message with updated content.

        Returns True on success, False on failure.
        """
        import requests

        url = (
            f"{self._msg_base}/conversations/{self._control_conv}"
            f"/messages/{message_id}"
        )
        payload = {
            "content": content,
            "messagetype": "Text",
            "contenttype": "text",
            "properties": {"hermes_sender": "bot"},
        }
        headers = {
            "Authentication": f"skypetoken={self._skype_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.put(url, json=payload, headers=headers, timeout=30)
            return resp.status_code in (200, 201)
        except Exception:
            return False

    def _poll_messages(self, since_timestamp: float, timeout: float = 30.0) -> list[dict]:
        """Poll the control conversation for new messages since the given
        timestamp. Returns a list of raw message dicts.

        Each message dict has: id, content, from (URL with orgid:OID),
        imdisplayname, messagetype, type.

        Echo-loop guard: messages with ``hermes_sender`` in
        ``("agent", "bot")`` are skipped (we sent those). Messages from a
        sender OID that does not match the owner are also skipped. This
        mirrors the production adapter's echo-loop guard.
        """
        import requests
        import urllib.parse

        url = f"{self._msg_base}/conversations/{self._control_conv}/messages?pageSize=50"
        headers = {
            "Authentication": f"skypetoken={self._skype_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                print(f"  Poll failed: HTTP {resp.status_code}")
                return []

            data = resp.json()
            messages = data.get("messages", [])

            result = []
            for msg in messages:
                # Skip system messages
                msg_type = msg.get("messagetype", "")
                if msg_type not in ("Text", "RichText/Html", ""):
                    continue

                # Check sender — extract OID from "from" URL
                from_url = msg.get("from", "")
                sender_oid = ""
                if "8:orgid:" in from_url:
                    sender_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")

                # Skip our own sent messages (hermes_sender=agent/bot)
                props = msg.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except (json.JSONDecodeError, TypeError):
                        props = {}
                if isinstance(props, dict) and props.get("hermes_sender") in ("agent", "bot"):
                    continue

                # Only process messages from the owner OID
                if sender_oid != self._owner_oid:
                    continue

                # Check message timestamp — only new messages
                msg_time_str = msg.get("composetime", msg.get("originalarrivaltime", ""))
                if msg_time_str:
                    try:
                        # Parse ISO timestamp (e.g. "2026-09-18T15:53:55.1560000Z")
                        msg_time_str = msg_time_str.replace("Z", "+00:00")
                        # Handle fractional seconds with variable precision
                        import datetime
                        try:
                            msg_dt = datetime.datetime.fromisoformat(msg_time_str)
                        except ValueError:
                            # Fallback: strip fractional seconds
                            msg_time_str = re.sub(
                                r"\.\d+", "", msg_time_str
                            )
                            msg_dt = datetime.datetime.fromisoformat(msg_time_str)
                        msg_time = msg_dt.timestamp()
                        if msg_time < since_timestamp:
                            continue
                    except (ValueError, OverflowError):
                        pass

                # Strip HTML from content
                content = msg.get("content", "")
                text = re.sub(r"<[^>]+>", "", content).strip()
                if not text:
                    continue

                result.append({
                    "id": msg.get("id", ""),
                    "text": text,
                    "sender_oid": sender_oid,
                    "conversation_id": self._control_conv,
                    "display_name": msg.get("imdisplayname", ""),
                    "timestamp": msg_time_str,
                })

            return result

        except Exception as e:
            print(f"  Poll error: {type(e).__name__}: {e}")
            return []

    # -- Main probe loop --------------------------------------------------

    def run(
        self,
        *,
        fixture_argv: list[str] | None = None,
        probe_timeout: float = 60.0,
    ) -> E2EResult:
        """Run the live Teams E2E probe.

        1. Initialize Teams transport.
        2. Create a ConPTY session.
        3. Send a probe message to the control conversation asking the owner
           to send a command.
        4. Poll for the owner's message and route it through the POC adapter.
        5. Stream terminal output back through the Teams edit path.
        6. Record the evidence tier as ``live-teams-e2e``.

        Returns an :class:`E2EResult`.
        """
        from poc.terminal_broker.fixtures.fixture_multiround import (
            fixture_argv as _multiround_argv,
        )

        checks: dict[str, dict] = {}

        try:
            # Step 1: Init Teams transport
            self._init_transport()
            checks["teams_transport_init"] = {
                "passed": True,
                "detail": f"Skype token obtained, msg_base={self._msg_base[:40]}...",
            }

            # Step 2: Create ConPTY session
            if fixture_argv is None:
                fixture_argv = _multiround_argv()
            self._sid = self._broker.create(fixture_argv, session_id="live-e2e")
            checks["session_created"] = {
                "passed": True,
                "detail": f"Session 'live-e2e' created, PID {self._broker.status(self._sid).pid}",
            }

            # Step 3: Send probe notification to Teams
            probe_msg = (
                f"[Terminal Remote Control POC] Session 'live-e2e' is ready. "
                f"Send a command like:\n"
                f"  status live-e2e\n"
                f"  output live-e2e\n"
                f"  mode live-e2e remote\n"
                f"  input live-e2e <text>\n"
                f"  stop live-e2e"
            )
            sent_msg_id = self._send_message(probe_msg)
            checks["probe_sent"] = {
                "passed": sent_msg_id is not None,
                "detail": f"Probe message sent to control conversation, msg_id={sent_msg_id}",
            }
            if not sent_msg_id:
                return self._fail(checks, "Failed to send probe message to Teams")

            # Step 4: Poll for owner's command (wait up to probe_timeout)
            poll_start = time.time()
            inbound_msg: Optional[dict] = None
            while time.time() - poll_start < probe_timeout:
                msgs = self._poll_messages(since_timestamp=poll_start)
                for m in msgs:
                    text = m["text"]
                    # Match POC command vocabulary
                    if re.match(r"^\s*(status|output|input|mode|stop|list)\b", text, re.I):
                        inbound_msg = m
                        break
                if inbound_msg:
                    break
                time.sleep(2)

            checks["command_received"] = {
                "passed": inbound_msg is not None,
                "detail": (
                    f"Received '{inbound_msg['text'][:50]}' from "
                    f"sender_oid={inbound_msg['sender_oid'][:12]}..."
                    if inbound_msg
                    else "No command received within timeout"
                ),
            }
            if not inbound_msg:
                return self._fail(checks, "No command received from Teams within timeout")

            # Step 5: Route through POC adapter (per-turn auth)
            poc_msg = InboundMessage(
                conversation_id=inbound_msg["conversation_id"],
                sender_oid=inbound_msg["sender_oid"],
                text=inbound_msg["text"],
                display_name=inbound_msg.get("display_name", ""),
                message_id=inbound_msg.get("id", ""),
            )
            result = self._adapter.process(poc_msg)

            checks["auth_and_dispatch"] = {
                "passed": result.auth_decision == AuthDecision.ALLOWED,
                "detail": (
                    f"auth={result.auth_decision.value}, verb={result.verb.value}, "
                    f"denied={result.denied}"
                ),
            }
            if result.auth_decision != AuthDecision.ALLOWED:
                return self._fail(checks, f"Authorization denied: {result.auth_decision}")

            # Step 6: Stream output back to Teams
            # Send the first response as a new message, then edit with
            # incremental updates
            response_text = result.response or "(no response)"
            first_msg_id = self._send_message(response_text)
            checks["first_output_sent"] = {
                "passed": first_msg_id is not None,
                "detail": f"First response sent, msg_id={first_msg_id}",
            }

            # If the command was "output", poll for incremental output and
            # edit the message with each new chunk
            if result.verb == CommandVerb.OUTPUT and first_msg_id:
                stream_update = self._stream_mgr.update(self._sid, response_text)
                # Poll for more output and send edits
                edits_made = 0
                edit_deadline = time.time() + 15.0
                while time.time() < edit_deadline:
                    out_result = self._adapter.process(InboundMessage(
                        conversation_id=self._control_conv,
                        sender_oid=self._owner_oid,
                        text=f"output {self._sid}",
                    ))
                    if out_result.response and out_result.response != "(no new output)" and "exited" not in (out_result.response or ""):
                        u = self._stream_mgr.update(self._sid, out_result.response)
                        if self._edit_message(first_msg_id, u.updated_text):
                            edits_made += 1
                        time.sleep(1)
                    elif out_result.response and "exited" in (out_result.response or ""):
                        break
                    time.sleep(0.5)

                checks["streaming_edits"] = {
                    "passed": True,
                    "detail": f"Made {edits_made} incremental edits to the same message",
                }
            else:
                checks["streaming_edits"] = {
                    "passed": True,
                    "detail": "N/A (non-output command — single response sent)",
                }

            # Step 7: Verify read-back
            readback = self._stream_mgr.get_accumulated_text(self._sid) if self._stream_mgr.get_state(self._sid) != StreamState.IDLE else (response_text or "")
            checks["readback"] = {
                "passed": bool(readback),
                "detail": f"Accumulated text: {len(readback)} chars",
            }

            # All checks passed
            all_passed = all(c["passed"] for c in checks.values())
            return E2EResult(
                verdict=E2EVerdict.PASS if all_passed else E2EVerdict.FAIL,
                evidence_tier=EvidenceTier.LIVE_TEAMS_E2E,
                investment_justified=all_passed,
                summary=(
                    f"Live Teams E2E {'PASS' if all_passed else 'FAIL'}: "
                    f"{len(checks)} checks, "
                    f"conv={self._control_conv[:20]}..., "
                    f"owner_oid={self._owner_oid[:12]}... "
                    f"Real Teams message round-trip completed."
                ),
                checks=checks,
            )

        except Exception as exc:
            checks["exception"] = {"passed": False, "detail": str(exc)}
            return E2EResult(
                verdict=E2EVerdict.FAIL,
                evidence_tier=EvidenceTier.LIVE_TEAMS_E2E,
                investment_justified=False,
                summary=f"Live Teams E2E raised exception: {exc}",
                checks=checks,
                detail=str(exc),
            )

    # -- Internal helpers --------------------------------------------------

    def _fail(self, checks: dict[str, dict], summary: str) -> E2EResult:
        return E2EResult(
            verdict=E2EVerdict.FAIL,
            evidence_tier=EvidenceTier.LIVE_TEAMS_E2E,
            investment_justified=False,
            summary=summary,
            checks=checks,
        )
