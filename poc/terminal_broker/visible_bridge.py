"""Interactive terminal that bridges to Teams — visible on PC + phone.

This script runs IN a visible Windows Terminal window. It does two things
at once:

1. Shows an interactive Python REPL on the PC screen (you can see it).
2. Bridges to Teams: reads input from Teams and writes it into the same
   REPL, and sends the REPL's output back to Teams by editing one message.

So when the user types on their phone in Teams, that text appears on the
PC terminal window AND gets evaluated. The result appears on the PC
terminal AND on the phone in Teams. Both sides see the same thing.

Uses the TEST_ONLY group (19:cbdcf6224c48469ea048147752ed92d9@thread.v2)
so it doesn't interfere with the control channel's normal Q&A.
Messages must be prefixed with [POC] to be picked up by the bridge
(e.g. "[POC] 2+3"), so the Hermes gateway can still operate in the same
group without collision.

Launch with:
    wt.exe python -u poc/terminal_broker/visible_bridge.py
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
import requests
from pathlib import Path
from urllib3.util.ssl_ import create_urllib3_context


# ─── Config ──────────────────────────────────────────────────────────────

# TEST_ONLY group — separate from the control channel
TEST_ONLY_CONV = "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"

# Prefix filter: only messages starting with [POC] are processed by the bridge
POC_PREFIX = "[POC]"


def _load_config():
    """Load the owner OID from config.yaml (the conversation ID is fixed)."""
    import yaml
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
    ca = Path.home() / ".hermes" / "certs" / "mtk-combined-ca.pem"
    if ca.exists():
        os.environ["REQUESTS_CA_BUNDLE"] = str(ca)
        os.environ["SSL_CERT_FILE"] = str(ca)
    from gateway.platforms.teams_mtk import _TeamsAuth
    auth = _TeamsAuth()
    auth._inject_truststore()
    tokens = auth.tokens()
    return tokens["skype_token"], auth.msg_base


# ─── Teams send/edit/poll ────────────────────────────────────────────────

class TeamsBridge:
    def __init__(self, skype_token, msg_base, conv_id, owner_oid):
        self.skype_token = skype_token
        self.msg_base = msg_base
        self.conv_id = conv_id
        self.owner_oid = owner_oid
        self.display_msg_id = None
        self.accumulated = ""
        self.seen_msg_ids: set[str] = set()
        self._ca_path = str(Path.home() / ".hermes" / "certs" / "mtk-combined-ca.pem")
        if not Path(self._ca_path).exists():
            self._ca_path = None

    def _make_session(self):
        """Build a fresh requests.Session with a per-request SSL context."""
        s = requests.Session()
        if self._ca_path:
            ctx = create_urllib3_context()
            ctx.load_verify_locations(self._ca_path)
            s.verify = self._ca_path
            os.environ["REQUESTS_CA_BUNDLE"] = self._ca_path
            os.environ["SSL_CERT_FILE"] = self._ca_path
        return s

    def _request_with_retry(self, method, url, **kwargs):
        """Execute an HTTP request with 1 retry on SSL EOF."""
        for attempt in range(2):
            session = self._make_session()
            try:
                resp = session.request(method, url, timeout=15, **kwargs)
                session.close()
                return resp
            except requests.exceptions.SSLError:
                session.close()
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise
        raise requests.exceptions.SSLError("Max retries exceeded")

    def send(self, text):
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages"
        try:
            resp = self._request_with_retry("POST", url, json={
                "content": text, "messagetype": "Text", "contenttype": "text",
                "properties": {"hermes_sender": "bot"},
            }, headers={
                "Authentication": f"skypetoken={self.skype_token}",
                "Content-Type": "application/json",
            })
            loc = resp.headers.get("Location", "")
            return loc.rstrip("/").rsplit("/", 1)[-1] if loc else ""
        except Exception:
            return ""

    def edit(self, msg_id, text):
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages/{msg_id}"
        try:
            resp = self._request_with_retry("PUT", url, json={
                "content": text, "messagetype": "Text", "contenttype": "text",
                "properties": {"hermes_sender": "bot"},
            }, headers={
                "Authentication": f"skypetoken={self.skype_token}",
                "Content-Type": "application/json",
            })
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

    def poll_input(self, since_ts):
        """Poll Teams for new messages starting with [POC] from the owner."""
        url = f"{self.msg_base}/conversations/{self.conv_id}/messages"
        try:
            resp = self._request_with_retry("GET", f"{url}?pageSize=50", headers={
                "Authentication": f"skypetoken={self.skype_token}",
                "Content-Type": "application/json",
            })
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


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Terminal ↔ Teams Bridge (TEST_ONLY group)")
    print("=" * 60)

    owner_oid = _load_config()
    conv_id = TEST_ONLY_CONV
    print(f"  Conv: {conv_id}")
    print(f"  Owner OID: {owner_oid[:12]}...")

    skype_token, msg_base = _init_transport()
    print(f"  Skype token: OK ({len(skype_token)} chars)")
    print(f"  MSG base: {msg_base}")
    print()

    bridge = TeamsBridge(skype_token, msg_base, conv_id, owner_oid)

    prompt_msg = (
        "📱 [POC] 終端橋接已啟動 (TEST_ONLY 群組)。\n"
        "在這裡打 [POC] 加上 Python 運算式（例如 [POC] 2+3），\n"
        "你的輸入會出現在 PC 上的終端機，結果也會回傳到這裡。\n"
        "打 [POC] quit 結束。\n"
        "注意：不加 [POC] 前綴的訊息不會被 bridge 處理。"
    )
    print(prompt_msg)
    print()
    bridge.send(prompt_msg)
    print("  >>> Waiting for input from phone or keyboard...")
    print(">>> ", end="", flush=True)

    poll_ts = time.time() - 3600
    deadline = time.time() + 600

    while time.time() < deadline:
        try:
            inputs = bridge.poll_input(poll_ts)
        except Exception as e:
            print(f"[poll error] {e}")
            inputs = []
        for text in inputs:
            poll_ts = time.time()
            if text.lower().strip() in ("quit", "exit"):
                print(f"\n[Teams] [POC] {text}")
                print("→ Shutting down...")
                bridge.send("📱 [POC] 終端已關閉。")
                return

            print(f"\n[Teams] [POC] {text}")

            try:
                result = eval(text, {"__builtins__": __builtins__}, {"os": os, "sys": sys})
                output = f">>> {text}\n{result}\n"
            except Exception as e:
                output = f">>> {text}\n{type(e).__name__}: {e}\n"

            print(output, end="")
            bridge.update_display(output)
            print(">>> ", end="", flush=True)

        time.sleep(1)

    print("\nTime's up.")
    bridge.send("⏱ [POC] 時間到，終端已關閉。")


if __name__ == "__main__":
    main()
