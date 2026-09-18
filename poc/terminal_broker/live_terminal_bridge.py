"""POC Live Terminal Bridge — real two-way Teams ↔ ConPTY terminal control.

This is the REAL E2E proof: the user types on their phone in Teams, and
that input goes directly into a ConPTY terminal session running on the PC.
Terminal output is streamed back to Teams and edited into one message so
the user sees the terminal updating live on their phone.

Flow:
1. Create a ConPTY session (interactive Python shell).
2. Send terminal output to Teams as a new message.
3. Poll Teams for user input → write each line directly to ConPTY stdin.
4. Read ConPTY stdout → edit the same Teams message with new output.
5. The user sees the terminal "running" on their phone, and can type into it.

This is NOT a query-response API. It's a live terminal session bridged
to Teams. What you type in Teams shows up in the terminal. What the
terminal outputs shows up in Teams.

Usage::

    bridge = LiveTerminalBridge()
    bridge.run()
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time
from typing import Optional

import requests

from gateway.platforms.teams_mtk import _TeamsAuth
from poc.terminal_broker.session_broker import SessionBroker
from poc.terminal_broker.teams_control_adapter import (
    AuthDecision,
    InboundMessage,
    TeamsControlAdapter,
    CommandVerb,
)


__all__ = ["LiveTerminalBridge"]


# An interactive Python shell as the ConPTY child process.
# It reads a line, evaluates it, and writes the result — perfect for
# demonstrating that user input from Teams reaches the terminal and
# terminal output reaches Teams.
_INTERACTIVE_SHELL = r"""
import sys, os
_pid = str(os.getpid())
sys.stdout.write(f'START_MARKER:{_pid}\n')
sys.stdout.flush()
while True:
    sys.stdout.write('> ')
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    if line.lower() in ('quit', 'exit'):
        sys.stdout.write('EXIT_MARKER:0\n')
        sys.stdout.flush()
        break
    try:
        result = eval(line, {'__builtins__': __builtins__}, {'os': os, 'sys': sys})
        sys.stdout.write(f'OUT:{result}\n')
    except Exception as e:
        sys.stdout.write(f'ERR:{type(e).__name__}: {e}\n')
    sys.stdout.flush()
"""


class LiveTerminalBridge:
    """Bridges a real ConPTY terminal session to Teams for two-way control.

    What this does that the previous probe didn't:
    - User input from Teams goes DIRECTLY into ConPTY stdin (not parsed as
      a command vocabulary).
    - ConPTY stdout is streamed back to Teams by editing one message
      repeatedly — the user sees the terminal "updating" on their phone.
    - The user can type arbitrary Python expressions and see the result
      on their phone, proving the terminal is really running.
    """

    def __init__(self) -> None:
        self._auth: Optional[_TeamsAuth] = None
        self._skype_token: str = ""
        self._msg_base: str = ""
        self._conv_id: str = ""
        self._owner_oid: str = ""
        self._broker: Optional[SessionBroker] = None
        self._sid: Optional[str] = None
        self._teams_msg_id: Optional[str] = None  # the message we keep editing
        self._accumulated_output: str = ""  # what we've shown on Teams so far

    def _load_config(self) -> None:
        """Load control conversation + owner OID from config.yaml."""
        import yaml
        from pathlib import Path

        config_path = Path.home() / ".hermes" / "config.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        gw = cfg.get("gateway", {})
        tm = gw.get("teams_mtk", {})
        control_convs = tm.get("control_conversations", {})
        if not control_convs:
            raise RuntimeError("No control_conversations in config.yaml")

        self._conv_id = next(iter(control_convs))
        owner_oids = control_convs[self._conv_id].get("owner_user_ids", [])
        if not owner_oids:
            raise RuntimeError("No owner_user_ids configured")
        self._owner_oid = owner_oids[0]

    def _init_transport(self) -> None:
        """Initialize Teams transport with Skype token + CA bundle."""
        self._auth = _TeamsAuth()
        self._auth._inject_truststore()
        tokens = self._auth.tokens()
        self._skype_token = tokens["skype_token"]
        self._msg_base = self._auth.msg_base

    def _send_message(self, content: str) -> str:
        """Send a new message to Teams. Returns the message ID."""
        url = f"{self._msg_base}/conversations/{self._conv_id}/messages"
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
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        location = resp.headers.get("Location", "")
        return location.rstrip("/").rsplit("/", 1)[-1] if location else ""

    def _edit_message(self, message_id: str, content: str) -> bool:
        """Edit an existing Teams message with new content."""
        url = (
            f"{self._msg_base}/conversations/{self._conv_id}"
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
            resp = requests.put(url, json=payload, headers=headers, timeout=20)
            return resp.status_code in (200, 201)
        except Exception:
            return False

    def _poll_user_input(self, since_ts: float, timeout: float = 5.0) -> list[dict]:
        """Poll Teams for new messages from the owner (non-bot)."""
        url = f"{self._msg_base}/conversations/{self._conv_id}/messages"
        headers = {
            "Authentication": f"skypetoken={self._skype_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(
                f"{url}?pageSize=50", headers=headers, timeout=20
            )
            if resp.status_code != 200:
                return []
            msgs = resp.json().get("messages", [])
            result = []
            for m in msgs:
                # Skip bot messages
                props = m.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except (json.JSONDecodeError, TypeError):
                        props = {}
                if isinstance(props, dict) and props.get("hermes_sender") in ("agent", "bot"):
                    continue
                # Only owner
                from_url = m.get("from", "")
                sender_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/") if "8:orgid:" in from_url else ""
                if sender_oid != self._owner_oid:
                    continue
                # Only new messages
                ct = m.get("composetime", "").replace("Z", "+00:00")
                try:
                    msg_ts = datetime.datetime.fromisoformat(ct).timestamp()
                    if msg_ts < since_ts:
                        continue
                except (ValueError, TypeError):
                    continue
                # Get text
                text = re.sub(r"<[^>]+>", "", m.get("content", "")).strip()
                if text:
                    result.append({"text": text, "sender_oid": sender_oid, "id": m.get("id", "")})
            return result
        except Exception:
            return []

    def _read_terminal_output(self, timeout: float = 0.5) -> str:
        """Read available output from the ConPTY session."""
        assert self._broker is not None and self._sid is not None
        data = self._broker.try_read_output(self._sid)
        if data and data != b"":
            return data.decode("utf-8", errors="replace")
        return ""

    def _update_teams_display(self, new_output: str) -> None:
        """Append new output to the Teams display message (edit-in-place)."""
        assert self._teams_msg_id is not None
        self._accumulated_output += new_output
        # Truncate to the last ~2000 chars to stay within Teams limits
        display = self._accumulated_output[-2000:]
        display = f"```\n{display}\n```"
        self._edit_message(self._teams_msg_id, display)

    def run(self, duration: float = 120.0) -> None:
        """Run the live terminal bridge for ``duration`` seconds.

        Steps:
        1. Create ConPTY session with interactive Python shell.
        2. Send initial terminal output to Teams as a new message.
        3. Loop: poll Teams for user input → write to ConPTY → read output → edit Teams message.
        4. When user types "quit" or timeout, shut down.
        """
        self._load_config()
        self._init_transport()

        # Create ConPTY session
        self._broker = SessionBroker()
        argv = [os.sys.executable if hasattr(os, 'sys') else __import__('sys').executable,
                "-u", "-c", _INTERACTIVE_SHELL]
        self._sid = self._broker.create(argv, session_id="live-terminal")
        pid = self._broker.status(self._sid).pid

        # Wait for START_MARKER
        start_deadline = time.time() + 10.0
        start_output = ""
        while time.time() < start_deadline:
            chunk = self._read_terminal_output()
            if chunk:
                start_output += chunk
                if "START_MARKER" in start_output:
                    break
            time.sleep(0.1)

        # Send initial message to Teams with terminal output
        initial_display = f"```\n{start_output}\n```"
        self._teams_msg_id = self._send_message(initial_display)
        self._accumulated_output = start_output

        # Also send a prompt
        self._send_message(
            f"📱 終端已就绪 (PID {pid})。\n"
            f"在上面那則訊息旁，直接打 Python 運算式（例如 2+3 或 'hello'*3）。\n"
            f"你的輸入會直接送進 PC 上的終端，終端的輸出會即時更新顯示在上面那則訊息。\n"
            f"打 quit 結束。"
        )

        print(f"Session PID: {pid}")
        print(f"Teams display msg: {self._teams_msg_id}")
        print("Bridge running — waiting for Teams input...")

        # Main loop
        poll_ts = time.time()
        deadline = time.time() + duration
        last_output_time = time.time()

        while time.time() < deadline:
            # 1. Check for user input from Teams
            msgs = self._poll_user_input(poll_ts, timeout=1.0)
            for m in msgs:
                poll_ts = time.time()  # advance cursor
                text = m["text"]
                print(f"  Teams input: \"{text}\"")

                # Write directly to ConPTY stdin
                if self._broker and self._sid:
                    self._broker.write_input(
                        self._sid,
                        (text + "\r\n").encode("utf-8"),
                        source="local",  # accept in local mode
                    )
                    print(f"  → Written to ConPTY stdin")

                if text.lower().strip() in ("quit", "exit"):
                    # Read final output
                    time.sleep(0.5)
                    final = self._read_terminal_output(timeout=1.0)
                    if final:
                        self._update_teams_display(final)
                    self._send_message("📱 終端已關閉。")
                    print("User typed quit — shutting down")
                    self._broker.close(self._sid)
                    self._broker.shutdown()
                    return

            # 2. Read terminal output and update Teams
            output = self._read_terminal_output(timeout=0.1)
            if output:
                print(f"  Terminal output: {repr(output[:80])}")
                self._update_teams_display(output)
                last_output_time = time.time()

            time.sleep(0.3)

        # Timeout
        self._send_message("⏱ 時間到，終端 session 自動關閉。")
        if self._broker and self._sid:
            self._broker.close(self._sid)
            self._broker.shutdown()
        print("Timeout — session closed")
