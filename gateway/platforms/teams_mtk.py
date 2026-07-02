"""Microsoft Teams gateway adapter for MTK internal environment.

Uses the existing teams skill token cache (~/.teams-tokens/token_cache.json)
for authentication — no separate bot token needed. Polls a configured
conversation for new messages.

Environment variables:
    MTK_TEAMS_CONVERSATION_ID   Conversation ID to monitor (required)
                                Format: 19:xxx@thread.v2  or  8:orgid:xxx
                                or  48:notes (self-chat)

    TEAMS_MTK_REQUIRE_MENTION   "true" (default) — in groups, only respond
                                when message contains @hermes. Set "false"
                                to process all messages.

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

from gateway.platforms.base import BasePlatformAdapter

logger = logging.getLogger(__name__)

# Teams API constants (from teams skill src/config.py)
_CLIENT_ID = "1fec8e78-bce4-4aaf-ab1b-5451cc387264"
_TENANT = "a7687ede-7a6b-4ef6-bace-642f677fbe31"
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
_SKYPE_TOKEN_URL = "https://authsvc.teams.microsoft.com/v1.0/authz"
# Default MSG endpoint; overridden at runtime by region from Skype token exchange.
_DEFAULT_MSG_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
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
    """Manages Teams token refresh using the teams skill cache.

    MTK internal network uses a self-signed SSL proxy, so we inject
    ``truststore`` on first use to make ``requests`` trust the OS cert store.
    """

    TOKEN_CACHE = Path.home() / ".teams-tokens" / "token_cache.json"
    _SKYPE_SCOPE = "https://api.spaces.skype.com/.default offline_access"

    def __init__(self):
        self._lock = threading.Lock()
        self._truststore_injected = False
        self._msg_base: Optional[str] = None  # set from Skype authz region

    def _inject_truststore(self):
        """Inject OS cert store via truststore (MTK SSL proxy compatibility)."""
        if self._truststore_injected:
            return
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        self._truststore_injected = True

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
        import requests
        self._inject_truststore()
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
            timeout=30,
        )
        resp.raise_for_status()
        new_tok = resp.json()

        # Exchange for Skype token — also discovers the regional chat service URL
        sk_resp = requests.post(
            _SKYPE_TOKEN_URL,
            headers={"Authorization": f"Bearer {new_tok['access_token']}"},
            json={},
            timeout=30,
        )
        sk_resp.raise_for_status()
        sk_body = sk_resp.json()

        # Skype token may be nested under "tokens" (newer API) or at top level
        skype_token = (
            sk_body.get("tokens", {}).get("skypeToken")
            or sk_body.get("skypeToken")
            or tokens.get("skype_token", "")
        )

        # Discover regional chat service URL from authz response
        chat_svc = (sk_body.get("regionGtms") or {}).get("chatService", "")
        if chat_svc:
            # chatService is like "https://apac.ng.msg.teams.microsoft.com"
            # MSG_BASE needs "/v1/users/ME" appended
            self._msg_base = chat_svc.rstrip("/") + "/v1/users/ME"
            logger.info("TeamsMTK: regional chat endpoint: %s", self._msg_base)

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
        self._inject_truststore()
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

    def _force_refresh(self) -> None:
        """Force a token refresh regardless of expiry (e.g. on 401)."""
        with self._lock:
            tok = self._load()
            logger.info("TeamsMTK: force-refreshing tokens (401)...")
            self._refresh(tok)

    @property
    def msg_base(self) -> str:
        """Return the regional MSG endpoint (discovered during auth)."""
        return self._msg_base or _DEFAULT_MSG_BASE


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TeamsMTKAdapter(BasePlatformAdapter):
    """Microsoft Teams gateway adapter for MTK environment.

    Polls one conversation for new messages and routes them to the hermes agent.
    Inherits from BasePlatformAdapter but avoids the import at module load time
    to keep startup fast when Teams is not configured.

    Mention gating (``require_mention``):
        - DMs / self-chat (48:notes, 8:orgid): every message is processed.
        - Groups (@thread): only messages containing ``@hermes`` (case-insensitive)
          are processed. Set ``TEAMS_MTK_REQUIRE_MENTION=false`` to disable.
    """

    _MENTION_TAG = "@hermes"

    def __init__(self, config):
        # Lazy import to avoid circular imports at module level
        from gateway.config import Platform, PlatformConfig
        from gateway.platforms.base import BasePlatformAdapter, MessageType, SendResult

        self._Platform = Platform
        self._MessageType = MessageType
        self._SendResult = SendResult

        # Initialise the base adapter so handle_message(), _active_sessions,
        # _process_message_background, _send_with_retry, etc. are all available.
        _cfg = config if config is not None else PlatformConfig()
        BasePlatformAdapter.__init__(self, _cfg, Platform.TEAMS_MTK)

        self.config = _cfg
        self.platform = Platform.TEAMS_MTK

        self._conv_id = os.getenv("MTK_TEAMS_CONVERSATION_ID", "").strip()
        self._auth = _TeamsAuth()
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._message_handler = None
        self._last_message_id: Optional[str] = None
        self._connected = False
        self._user_oid: Optional[str] = None  # set during connect from first poll

        # Mention gating: default on for groups, off for DMs
        _rm = os.getenv("TEAMS_MTK_REQUIRE_MENTION", "true").lower()
        self.require_mention = _rm in ("true", "1", "yes", "on")

        # Fatal-error infrastructure (required by gateway runner)
        self._fatal_error_handler = None
        self._fatal_error_code: Optional[str] = None
        self._fatal_error_message: Optional[str] = None
        self._fatal_error_retryable = True

        # Pending-message queue (gateway calls get_pending_message)
        self._pending_messages: Dict[str, List] = {}

        # Gateway runner settables (stored, minimal usage for polling adapter)
        self._session_store = None
        self._busy_session_handler = None
        self._topic_recovery_fn = None
        self._authorization_check = None
        self._busy_text_mode = None

    # ---- BasePlatformAdapter interface ----

    def set_message_handler(self, handler) -> None:
        self._message_handler = handler

    def set_fatal_error_handler(self, handler) -> None:
        self._fatal_error_handler = handler

    def set_session_store(self, store) -> None:
        self._session_store = store

    def set_busy_session_handler(self, handler) -> None:
        self._busy_session_handler = handler

    def set_topic_recovery_fn(self, fn) -> None:
        self._topic_recovery_fn = fn

    def set_authorization_check(self, check_fn) -> None:
        self._authorization_check = check_fn

    @property
    def fatal_error_code(self) -> Optional[str]:
        return self._fatal_error_code

    @property
    def fatal_error_message(self) -> Optional[str]:
        return self._fatal_error_message

    @property
    def fatal_error_retryable(self) -> bool:
        return self._fatal_error_retryable

    def has_fatal_error(self) -> bool:
        return self._fatal_error_message is not None

    def _set_fatal_error(self, code: str, message: str, *, retryable: bool = True) -> None:
        self._fatal_error_code = code
        self._fatal_error_message = message
        self._fatal_error_retryable = retryable

    def get_pending_message(self, session_key: str):
        return self._pending_messages.pop(session_key, None)

    async def cancel_background_tasks(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    def _mark_connected(self) -> None:
        self._connected = True
        self._fatal_error_code = None
        self._fatal_error_message = None

    def _mark_disconnected(self) -> None:
        self._connected = False

    async def connect(self, is_reconnect: bool = False) -> bool:
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
            msgs = self._fetch_messages(limit=5)
            if msgs:
                self._last_message_id = msgs[-1].get("id")
                # Extract user OID from first message's "from" URL
                for m in msgs:
                    from_url = m.get("from", "")
                    if "8:orgid:" in from_url:
                        self._user_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")
                        logger.info("TeamsMTK: user OID: %s", self._user_oid)
                        break
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
            import requests, re
            self._auth._inject_truststore()
            for attempt in range(2):
                skype_token = self._auth.skype_token()
                url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
                # Convert plain text to Teams-compatible HTML (matches teams skill)
                if re.search(r'<(b|i|a|br|h[1-6]|ul|ol|li|pre|code|strong|em)\b', content):
                    html_content = content.replace('\n', '<br>')
                else:
                    import markdown
                    html_content = markdown.markdown(
                        content,
                        extensions=['fenced_code', 'tables', 'nl2br', 'md_in_html'],
                    )
                payload = {
                    "content": html_content,
                    "messagetype": "RichText/Html",
                    "contenttype": "text",
                }
                resp = requests.post(
                    url,
                    json=payload,
                    headers={
                        "Authentication": f"skypetoken={skype_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                if resp.status_code == 401 and attempt == 0:
                    self._auth._force_refresh()
                    continue
                break
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            logger.info("TeamsMTK: sent message id=%s to %s", msg_id, chat_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.error("TeamsMTK: send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "group" if "@thread" in chat_id else "dm", "chat_id": chat_id}

    async def edit_message(self, chat_id: str, message_id: str, new_content: str) -> bool:
        """Edit a previously sent message (optional — used for progress streaming)."""
        try:
            import requests
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages/{message_id}"
            import markdown
            html = markdown.markdown(new_content, extensions=['fenced_code', 'tables', 'nl2br', 'md_in_html'])
            resp = requests.put(
                url,
                json={"content": html, "messagetype": "RichText/Html", "contenttype": "text"},
                headers={"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.debug("TeamsMTK: edit_message failed: %s", e)
            return False

    # ---- Internal polling ----

    def _fetch_messages(self, limit: int = 20) -> List[dict]:
        """Fetch recent messages from the conversation (sync, called from thread)."""
        import urllib.parse, requests

        self._auth._inject_truststore()
        for attempt in range(2):
            skype_token = self._auth.skype_token()
            encoded_conv_id = urllib.parse.quote(self._conv_id, safe='')
            url = f"{self._auth.msg_base}/conversations/{encoded_conv_id}/messages"
            resp = requests.get(
                url,
                params={"pageSize": limit, "startTime": 0},
                headers={"Authentication": f"skypetoken={skype_token}"},
                timeout=30,
            )
            if resp.status_code == 401 and attempt == 0:
                # Skype token expired — force a full token refresh
                self._auth._force_refresh()
                continue
            resp.raise_for_status()
            break

        data = resp.json()
        # amer.ng.msg returns messages under "messages" key, newest-first
        messages = data.get("messages") or []
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
                logger.warning("TeamsMTK: poll error: %s", e, exc_info=True)

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
            msg_type = msg.get("messagetype", "")
            content = msg.get("content", "")
            # "from" is a URL string, NOT a dict — never call .get() on it
            sender = msg.get("imdisplayname") or msg.get("fromDisplayNameInToken") or "Teams User"

            # Skip system messages
            if msg_type in ("ThreadActivity/MemberJoined", "ThreadActivity/TopicUpdate"):
                self._last_message_id = msg_id
                continue

            # Skip bot's own replies — when we have the user OID, all messages
            # in a 1:1 self-chat have the same orgid.  After we send a reply it
            # gets appended to the conversation; next poll would see it and
            # trigger another agent run.  Guard: skip any message whose from-URL
            # contains OUR orgid AND whose content is empty OR was already seen.
            from_url = msg.get("from", "")
            if self._user_oid and f"8:orgid:{self._user_oid}" in from_url:
                if not content:
                    self._last_message_id = msg_id
                    continue
                # The watermark (_last_message_id) prevents re-processing; only
                # brand-new messages from our own account reach here, which means
                # they are messages WE just sent (outbound bot replies).  Skip them.
                if msg_type == "RichText/Html":
                    logger.debug("TeamsMTK: skipping own bot reply id=%s", msg_id)
                    self._last_message_id = msg_id
                    continue
            elif not content:
                self._last_message_id = msg_id
                continue

            # Strip HTML tags from content
            import re
            text = re.sub(r"<[^>]+>", "", content).strip()
            if not text:
                self._last_message_id = msg_id
                continue

            # Mention gating: in groups, only respond when @hermes is present
            is_group = "@thread" in self._conv_id
            if is_group and self.require_mention:
                if self._MENTION_TAG.lower() not in text.lower():
                    logger.debug(
                        "TeamsMTK: ignoring group message (require_mention=true, no %s): %s",
                        self._MENTION_TAG, text[:60],
                    )
                    self._last_message_id = msg_id
                    continue
                # Strip the @hermes mention so the agent doesn't misinterpret it
                text = re.sub(
                    re.escape(self._MENTION_TAG) + r"\b", "", text, flags=re.IGNORECASE
                ).strip()

            logger.info("TeamsMTK: new message from %s: %s", sender, text[:60])

            try:
                from gateway.platforms.base import MessageEvent, MessageType
                from gateway.config import Platform

                from gateway.session import SessionSource
                user_id = sender  # fallback to display name
                if "8:orgid:" in from_url:
                    user_id = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")

                source = SessionSource(
                    platform=Platform.TEAMS_MTK,
                    chat_id=self._conv_id,
                    user_id=user_id,
                    user_name=sender,
                    chat_type="group" if "@thread" in self._conv_id else "dm",
                )

                event = MessageEvent(
                    text=text,
                    message_type=MessageType.TEXT,
                    source=source,
                    message_id=msg_id,
                )
                # Use handle_message() (not _message_handler directly) so the
                # full base-class pipeline runs: session guard, typing indicator,
                # _process_message_background, and _send_with_retry delivery.
                await self.handle_message(event)
            except Exception as e:
                logger.error("TeamsMTK: handler error for message %s: %s", msg_id, e, exc_info=True)
            finally:
                self._last_message_id = msg_id

