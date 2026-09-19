"""Visible bridge: Teams ↔ Claude Code CLI (real target).

Launches Claude Code as the ConPTY child process. User types on Teams
phone → input goes into Claude Code stdin → Claude Code output streams
back to Teams. Both PC terminal and phone see the same content.

Usage:
    wt.exe python -u poc/terminal_broker/claude_bridge.py
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
import requests


# ─── Config ──────────────────────────────────────────────────────────────

TEST_ONLY_CONV = "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
POC_PREFIX = "[POC]"

CLAUDE_CMD = ["claude"]


def _load_config():
    import yaml
    from pathlib import Path
    config_path = Path.home() / ".hermes" / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    gw = cfg.get("gateway", {})
    tm = gw.get("teams_mtk", {})
    cc = tm.get("control_conversations", {})
    if not cc:
        raise RuntimeError("No control_conversations configured")
    conv_id = next(iter(cc))
    owner_oid = cc[conv_id].get("owner_user_ids", [""])[0]
    return owner_oid


def _init_transport():
    import os
    from pathlib import Path
    ca = Path.home() / ".hermes" / "certs" / "mtk-combined-ca.pem"
    if ca.exists():
        os.environ["REQUESTS_CA_BUNDLE"] = str(ca)
        os.environ["SSL_CERT_FILE"] = str(ca)
    from gateway.platforms.teams_mtk import _TeamsAuth
    auth = _TeamsAuth()
    auth._inject_truststore()
    tokens = auth.tokens()
    return tokens["skype_token"], auth.msg_base


# ─── Teams bridge ────────────────────────────────────────────────────────

class TeamsBridge:
    def __init__(self, skype_token, msg_base, conv_id, owner_oid):
        self.skype_token = skype_token
        self.msg_base = msg_base
        self.conv_id = conv_id
        self.owner_oid = owner_oid
        self.display_msg_id = None
        self.accumulated = ""
        self.seen_msg_ids: set[str] = set()

    def _ensure_ca_bundle(self):
        """Restore the CA bundle environment variable — Claude Code may have overwritten it."""
        import os
        from pathlib import Path
        ca = Path.home() / ".hermes" / "certs" / "mtk-combined-ca.pem"
        if ca.exists():
            os.environ["REQUESTS_CA_BUNDLE"] = str(ca)
            os.environ["SSL_CERT_FILE"] = str(ca)
            return str(ca)
        return None

    def send(self, text):
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages"
        ca = self._ensure_ca_bundle()
        session = requests.Session()
        session.verify = ca if ca else True
        resp = session.post(url, json={
            "content": text,
            "messagetype": "Text",
            "contenttype": "text",
            "properties": {"hermes_sender": "bot"},
        }, headers={
            "Authentication": f"skypetoken={self.skype_token}",
            "Content-Type": "application/json",
        }, timeout=15)
        loc = resp.headers.get("Location", "")
        return loc.rstrip("/").rsplit("/", 1)[-1] if loc else ""

    def edit(self, msg_id, text):
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages/{msg_id}"
        ca = self._ensure_ca_bundle()
        session = requests.Session()
        session.verify = ca if ca else True
        try:
            resp = session.put(url, json={
                "content": text,
                "messagetype": "Text",
                "contenttype": "text",
                "properties": {"hermes_sender": "bot"},
            }, headers={
                "Authentication": f"skypetoken={self.skype_token}",
                "Content-Type": "application/json",
            }, timeout=15)
            return resp.status_code in (200, 201)
        except Exception:
            return False

    def update_display(self, new_text):
        self.accumulated += new_text
        display = self.accumulated[-1900:]
        display = f"```\n{display}\n```"
        if self.display_msg_id:
            self.edit(self.display_msg_id, display)
        else:
            self.display_msg_id = self.send(display)

    def send_fresh(self, text):
        """Send a new message (not edit)."""
        return self.send(text)

    def poll_input(self, since_ts):
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages"
        ca = self._ensure_ca_bundle()
        session = requests.Session()
        session.verify = ca if ca else True
        try:
            resp = session.get(f"{url}?pageSize=50", headers={
                "Authentication": f"skypetoken={self.skype_token}",
                "Content-Type": "application/json",
            }, timeout=15)
            if resp.status_code != 200:
                return []
            msgs = resp.json().get("messages", [])
            result = []
            for m in msgs:
                msg_id = m.get("id", "")
                if msg_id in self.seen_msg_ids:
                    continue
                props = m.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        props = {}
                if isinstance(props, dict) and props.get("hermes_sender") in ("agent", "bot"):
                    continue
                from_url = m.get("from", "")
                sender_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/") if "8:orgid:" in from_url else ""
                if sender_oid != self.owner_oid:
                    continue
                ct = m.get("composetime", "").replace("Z", "+00:00")
                try:
                    ts = datetime.datetime.fromisoformat(ct).timestamp()
                    if ts < since_ts:
                        continue
                except:
                    continue
                text = re.sub(r"<[^>]+>", "", m.get("content", "")).strip()
                if not text:
                    continue
                if not text.startswith(POC_PREFIX):
                    continue
                expr = text[len(POC_PREFIX):].strip()
                self.seen_msg_ids.add(msg_id)
                result.append(expr)
            return result
        except Exception as e:
            print(f"[poll error] {e}")
            return []


# ─── ConPTY child process ───────────────────────────────────────────────

def _spawn_claude():
    """Spawn Claude Code CLI as a ConPTY child process."""
    from poc.terminal_broker.session_broker import SessionBroker
    broker = SessionBroker()
    sid = broker.create(CLAUDE_CMD, session_id="claude-live")
    return broker, sid


def main():
    print("=" * 60)
    print("  Claude Code ↔ Teams Bridge (TEST_ONLY group)")
    print("=" * 60)

    owner_oid = _load_config()
    conv_id = TEST_ONLY_CONV
    print(f"  Conv: {conv_id}")
    print(f"  Owner OID: {owner_oid[:12]}...")

    skype_token, msg_base = _init_transport()
    print(f"  Skype token: OK ({len(skype_token)} chars)")
    print()
    print("  Spawning Claude Code CLI as ConPTY child...")
    print("  (this may take a few seconds)")
    print()

    # Spawn Claude Code
    from poc.terminal_broker.session_broker import SessionBroker, ControlMode
    broker = SessionBroker()
    sid = broker.create(CLAUDE_CMD, session_id="claude-live", cols=120, rows=40)
    broker.set_mode(sid, ControlMode.LOCAL)
    pid = broker.status(sid).pid
    print(f"  Claude Code PID: {pid}")

    bridge = TeamsBridge(skype_token, msg_base, conv_id, owner_oid)

    # Read initial output from Claude Code (banner, prompt)
    initial_output = ""
    init_deadline = time.time() + 15.0
    while time.time() < init_deadline:
        chunk = broker.try_read_output(sid)
        if chunk and chunk != b"":
            text = chunk.decode("utf-8", errors="replace")
            initial_output += text
            print(text, end="", flush=True)
        time.sleep(0.3)
        # Stop when we see the Claude prompt (usually ">" or "│>")
        if ">" in initial_output and len(initial_output) > 20:
            break

    # Send initial message to Teams
    prompt_msg = (
        "🤖 [POC] Claude Code 已啟動 (TEST_ONLY 群組)。\n"
        "在這裡打 [POC] 加上你的問題（例如 [POC] hello），\n"
        "Claude Code 會收到並回覆，回覆會顯示在 PC 終端和這裡。\n"
        "打 [POC] quit 結束。"
    )
    bridge.send(prompt_msg)
    print()
    print("  Teams notified. Waiting for input...")

    # Keep a display message that gets edited as Claude responds
    poll_ts = time.time() - 60  # Catch messages from last minute
    deadline = time.time() + 900  # 15 minutes

    while time.time() < deadline:
        # 1. Poll Teams for user input
        try:
            inputs = bridge.poll_input(poll_ts)
        except Exception:
            inputs = []
        for text in inputs:
            poll_ts = time.time()
            if text.lower().strip() in ("quit", "exit"):
                print(f"\n[Teams] [POC] {text}")
                bridge.send("🤖 [POC] Claude Code session 已關閉。")
                broker.close(sid)
                broker.shutdown()
                return

            print(f"\n[Teams] [POC] {text}")

            # Write user's input into Claude Code's stdin
            # Claude Code expects a newline at the end of each prompt
            broker.write_input(sid, (text + "\r\n").encode("utf-8"), source="local")

            # Start a fresh display message for this Q&A exchange
            bridge.display_msg_id = None
            bridge.accumulated = f">>> {text}\n"
            bridge.send_fresh(f"```\n>>> {text}\n(等待 Claude Code 回覆...)\n```")

            # Read Claude Code's output and stream to Teams
            read_deadline = time.time() + 60.0  # Wait up to 60s for response
            last_output_time = time.time()
            output_buffer = ""

            while time.time() < read_deadline:
                chunk = broker.try_read_output(sid)
                if chunk and chunk != b"":
                    text_out = chunk.decode("utf-8", errors="replace")
                    output_buffer += text_out
                    print(text_out, end="", flush=True)
                    # Stream to Teams
                    bridge.update_display(text_out)
                    last_output_time = time.time()
                else:
                    # If no output for 5 seconds after last output, consider
                    # the response complete
                    if time.time() - last_output_time > 5.0 and output_buffer:
                        break
                time.sleep(0.5)

            print("\n--- Claude Code response complete ---")
            bridge.send_fresh("✅ [POC] 回覆完成。")

        # 2. Read any unsolicited output from Claude Code
        # (e.g. async notifications, background tasks)
        chunk = broker.try_read_output(sid)
        if chunk and chunk != b"":
            text_out = chunk.decode("utf-8", errors="replace")
            print(text_out, end="", flush=True)

        time.sleep(1)

    print("\nTime's up.")
    bridge.send("⏱ [POC] 時間到，Claude Code session 已關閉。")
    broker.close(sid)
    broker.shutdown()


if __name__ == "__main__":
    main()
