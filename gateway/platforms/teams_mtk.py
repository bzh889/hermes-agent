"""Microsoft Teams gateway adapter for MTK internal environment.

Uses the existing teams skill token cache (~/.teams-tokens/token_cache.json)
for authentication — no separate bot token needed. Polls a configured
conversation for new messages.

Environment variables:
    MTK_TEAMS_CONVERSATION_ID   Conversation ID to monitor (required)
                                Format: 19:xxx@thread.v2  or  8:orgid:xxx

Setup:
    1. Run teams skill auth: python ~/.claude/skills/teams/auth_run.py
    2. hermes setup gateway  → select "Microsoft Teams (MTK)"
    3. Enter your conversation ID
    4. hermes gateway
"""

import asyncio
import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Teams API constants (from teams skill src/config.py)
_CLIENT_ID = "1fec8e78-bce4-4aaf-ab1b-5451cc387264"
_TENANT = "a7687ede-7a6b-4ef6-bace-642f677fbe31"
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
_SKYPE_TOKEN_URL = "https://authsvc.teams.microsoft.com/v1.0/authz"
_MSG_BASE = "https://chatsvc.teams.microsoft.com/api/ckt"
_POLL_INTERVAL = 30  # seconds


def check_teams_mtk_requirements() -> bool:
    """Return True if Teams MTK adapter can start."""
    token_cache = Path.home() / ".teams-tokens" / "token_cache.json"
    conv_id = os.getenv("MTK_TEAMS_CONVERSATION_ID", "").strip()
    return bool(conv_id and token_cache.exists())


# ---------------------------------------------------------------------------
# Minimal auth — reuses token cache written by teams skill auth_run.py
# ---------------------------------------------------------------------------

class _TeamsAuth:
    """Reads and auto-refreshes tokens from the teams skill token cache."""

    TOKEN_CACHE = Path.home() / ".teams-tokens" / "token_cache.json"
    _SKYPE_SCOPE = "https://api.spaces.skype.com/.default offline_access"

    def __init__(self):
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not self.TOKEN_CACHE.exists():
            raise RuntimeError(
                "Teams token cache not found. "
                "Authenticate first: python ~/.claude/skills/teams/auth_run.py"
            )
        with open(self.TOKEN_CACHE, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, tokens: dict) -> None:
        self.TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.TOKEN_CACHE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)

    def _expired(self, tokens: dict, buffer: int = 300) -> bool:
        saved_at = tokens.get("saved_at", 0)
        expires_in = tokens.get("expires_in", 3600)
        return time.time() > saved_at + expires_in - buffer

    def _refresh(self, tokens: dict) -> dict:
        import requests, certifi
        refresh_token = tokens.get("refresh_token", "")
        if not refresh_token:
            raise RuntimeError(
                "No refresh_token in cache — re-authenticate: "
                "python ~/.claude/skills/teams/auth_run.py"
            )

        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": self._SKYPE_SCOPE,
            },
            verify=certifi.where(),
            timeout=30,
        )
        resp.raise_for_status()
        new_tok = resp.json()

        # Exchange for Skype token
        sk_resp = requests.post(
            _SKYPE_TOKEN_URL,
            headers={"Authorization": f"Bearer {new_tok['access_token']}"},
            json={},
            verify=certifi.where(),
            timeout=30,
        )
        sk_resp.raise_for_status()
        skype_token = sk_resp.json().get("skypeToken", tokens.get("skype_token", ""))

        tokens.update({
            "access_token": new_tok["access_token"],
            "skype_token": skype_token,
            "saved_at": int(time.time()),
            "expires_in": new_tok.get("expires_in", 3600),
        })
        if new_tok.get("refresh_token"):
            tokens["refresh_token"] = new_tok["refresh_token"]

        self._save(tokens)
        return tokens

    def tokens(self) -> dict:
        with self._lock:
            tok = self._load()
            if self._expired(tok):
                logger.info("TeamsMTK: refreshing tokens...")
                tok = self._refresh(tok)
            return tok

    def skype_token(self) -> str:
        return self.tokens()["skype_token"]

    def access_token(self) -> str:
        return self.tokens()["access_token"]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TeamsMTKAdapter:
    """Microsoft Teams gateway adapter for MTK environment.

    Polls one conversation for new messages and routes them to the hermes agent.
    Inherits from BasePlatformAdapter but avoids the import at module load time
    to keep startup fast when Teams is not configured.
    """

    def __init__(self, config):
        # Lazy import to avoid circular imports at module level
        from gateway.config import Platform
        from gateway.platforms.base import BasePlatformAdapter, MessageType, SendResult

        self._Platform = Platform
        self._MessageType = MessageType
        self._SendResult = SendResult

        self.config = config
        self.platform = Platform.TEAMS_MTK

        self._conv_id = os.getenv("MTK_TEAMS_CONVERSATION_ID", "").strip()
        self._auth = _TeamsAuth()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._message_handler = None
        self._last_message_id: Optional[str] = None
        self._connected = False

    # ---- BasePlatformAdapter interface ----

    def set_message_handler(self, handler) -> None:
        self._message_handler = handler

    def _mark_connected(self) -> None:
        self._connected = True

    def _mark_disconnected(self) -> None:
        self._connected = False

    async def connect(self) -> bool:
        if not self._conv_id:
            logger.error("TeamsMTK: MTK_TEAMS_CONVERSATION_ID not set")
            return False

        try:
            # Validate token on startup
            self._auth.skype_token()
        except Exception as e:
            logger.error("TeamsMTK: auth failed — %s", e)
            return False

        # Seed last_message_id to avoid replaying old messages on startup
        try:
            msgs = self._fetch_messages(limit=1)
            if msgs:
                self._last_message_id = msgs[0].get("id")
                logger.debug("TeamsMTK: seeded last_message_id=%s", self._last_message_id)
        except Exception as e:
            logger.warning("TeamsMTK: could not seed last message id: %s", e)

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._mark_connected()
        logger.info(
            "TeamsMTK: connected — polling conversation %s every %ds",
            self._conv_id, _POLL_INTERVAL,
        )
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._mark_disconnected()
        logger.info("TeamsMTK: disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        SendResult = self._SendResult
        if not content:
            return SendResult(success=True)
        try:
            import requests, certifi
            skype_token = self._auth.skype_token()
            url = f"{_MSG_BASE}/conversations/{chat_id}/messages"
            payload = {
                "content": content,
                "messagetype": "Text",
                "contenttype": "text",
            }
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authentication": f"skypetoken={skype_token}",
                    "Content-Type": "application/json",
                },
                verify=certifi.where(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            logger.debug("TeamsMTK: sent message id=%s", msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.error("TeamsMTK: send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "group" if "@thread" in chat_id else "dm", "chat_id": chat_id}

    # ---- Internal polling ----

    def _fetch_messages(self, limit: int = 20) -> List[dict]:
        """Fetch recent messages from the conversation (sync, called from thread)."""
        import requests, certifi
        skype_token = self._auth.skype_token()
        url = f"{_MSG_BASE}/conversations/{self._conv_id}/messages"
        resp = requests.get(
            url,
            params={"pageSize": limit, "startTime": 0},
            headers={"Authentication": f"skypetoken={skype_token}"},
            verify=certifi.where(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Teams returns messages newest-first in 'messages' or 'value'
        messages = data.get("messages") or data.get("value") or []
        return list(reversed(messages))  # oldest-first for processing

    async def _poll_loop(self) -> None:
        """Poll the conversation for new messages every _POLL_INTERVAL seconds."""
        import concurrent.futures
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        while self._running:
            try:
                msgs = await loop.run_in_executor(executor, lambda: self._fetch_messages(20))
                await self._process_new_messages(msgs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("TeamsMTK: poll error: %s", e)

            try:
                await asyncio.sleep(_POLL_INTERVAL)
            except asyncio.CancelledError:
                break

        executor.shutdown(wait=False)

    async def _process_new_messages(self, messages: List[dict]) -> None:
        """Dispatch messages newer than last_message_id to the hermes agent."""
        if not messages or not self._message_handler:
            return

        new_messages = []
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue
            if self._last_message_id is None or msg_id > self._last_message_id:
                new_messages.append(msg)

        for msg in new_messages:
            msg_id = msg.get("id", "")
            # Skip bot's own messages (type "RichText/Html" from API replies, or empty content)
            msg_type = msg.get("messagetype", "")
            content = msg.get("content", "")
            sender = (msg.get("imdisplayname") or msg.get("from", {}).get("user", {}).get("displayName") or "")

            # Skip system messages and messages without text
            if not content or msg_type in ("ThreadActivity/MemberJoined", "ThreadActivity/TopicUpdate"):
                self._last_message_id = msg_id
                continue

            # Strip HTML tags from content
            import re
            text = re.sub(r"<[^>]+>", "", content).strip()
            if not text:
                self._last_message_id = msg_id
                continue

            logger.info("TeamsMTK: new message from %s: %s", sender, text[:60])

            try:
                from gateway.platforms.base import MessageEvent, MessageType
                from gateway.config import Platform

                # Build a minimal SessionSource-like object
                source = _TeamsSessionSource(
                    platform=Platform.TEAMS_MTK,
                    chat_id=self._conv_id,
                    user_id=msg.get("from", {}).get("user", {}).get("id", sender),
                    user_name=sender,
                )

                event = MessageEvent(
                    text=text,
                    message_type=MessageType.TEXT,
                    source=source,
                    message_id=msg_id,
                )
                await self._message_handler(event)
            except Exception as e:
                logger.error("TeamsMTK: handler error for message %s: %s", msg_id, e)
            finally:
                self._last_message_id = msg_id


class _TeamsSessionSource:
    """Minimal SessionSource for Teams messages."""

    def __init__(self, platform, chat_id: str, user_id: str, user_name: str):
        self.platform = platform
        self.chat_id = chat_id
        self.user_id = user_id
        self.user_name = user_name
        self.chat_name = chat_id
        self.chat_type = "group" if "@thread" in chat_id else "dm"
        self.thread_id = None
        self.chat_topic = None
        self.user_id_alt = None
        self.chat_id_alt = None
        self.is_bot = False
