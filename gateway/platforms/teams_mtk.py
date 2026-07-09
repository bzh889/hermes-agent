"""Microsoft Teams gateway adapter for MTK internal environment.

Uses the existing teams skill token cache (~/.teams-tokens/token_cache.json)
for authentication — no separate bot token needed. Polls a configured
conversation for new messages.

Environment variables:
    MTK_TEAMS_CONVERSATION_ID   Conversation ID to monitor (required)
                                Format: 19:xxx@thread.v2  or  8:orgid:xxx
                                or 48:notes (self-chat)

    MTK_TEAMS_POLL_INTERVAL     Poll interval in seconds (default: 3)

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
_POLL_INTERVAL = int(os.getenv("MTK_TEAMS_POLL_INTERVAL", "2"))  # seconds


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
    _my_oid: Optional[str] = None

    def _get_my_oid(self) -> str:
        """Extract current user OID from the access token JWT (matches teams skill)."""
        if self._my_oid:
            return self._my_oid
        try:
            import base64
            tok = self._load()
            parts = tok.get("access_token", "").split(".")
            if len(parts) >= 2:
                payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                self._my_oid = decoded.get("oid", "")
        except Exception:
            self._my_oid = ""
        return self._my_oid or ""

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
            raw = f.read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Corrupted cache (e.g. partial write from another process).
            # Try to recover the first valid JSON object.
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(raw)
                return obj
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"Teams token cache is corrupted: {self.TOKEN_CACHE}. "
                    "Re-authenticate: python ~/.claude/skills/teams/auth_run.py"
                )

    def _save(self, tokens: dict) -> None:
        self.TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.TOKEN_CACHE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)

    def _expired(self, tokens: dict, buffer: int = 300) -> bool:
        saved_at = tokens.get("saved_at", 0)
        expires_in = tokens.get("expires_in", 3600)
        return time.time() > saved_at + expires_in - buffer

    def _refresh(self, tokens: dict) -> dict:
        import requests, urllib3
        urllib3.disable_warnings()
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
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        new_tok = resp.json()

        # Exchange for Skype token — also discovers the regional chat service URL
        sk_resp = requests.post(
            _SKYPE_TOKEN_URL,
            headers={"Authorization": f"Bearer {new_tok['access_token']}"},
            json={},
            verify=False,
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
    Inherits from BasePlatformAdapter for the standard session guard,
    background processing, and _send_with_retry delivery pipeline.

    Mention gating (``require_mention``):
        - DMs / self-chat (48:notes, 8:orgid): every message is processed.
        - Groups (@thread): only messages containing ``@hermes`` (case-insensitive)
          are processed. Set ``TEAMS_MTK_REQUIRE_MENTION=false`` to disable.
    """

    _MENTION_TAG = "@hermes"

    # Fixed refusal notice for blocked_keywords hits (inbound and outbound).
    # Single global string, not per-group customizable — see design.md
    # "Open Questions" for the rationale (kept simple until a concrete
    # per-group wording need shows up).
    _BLOCKED_KEYWORD_NOTICE = "這個問題涉及此群組的限制詞，已被攔截。"

    def _find_blocked_keyword(self, text: str, patterns: List[str]) -> Optional[str]:
        """Return the first pattern in *patterns* that matches *text*, or None.

        Patterns are treated as case-insensitive regex. A malformed pattern
        is skipped (logged) rather than raising, so one bad regex in a
        group's config doesn't take down the whole keyword filter.
        """
        if not text or not patterns:
            return None
        import re as _re
        for pattern in patterns:
            try:
                if _re.search(pattern, text, _re.IGNORECASE):
                    return pattern
            except _re.error as e:
                logger.warning("TeamsMTK: invalid blocked_keywords pattern %r: %s", pattern, e)
        return None

    # Teams Skype API supports large HTML payloads (100k+ chars in practice).
    # The stream consumer uses this as the per-message budget before splitting.
    MAX_MESSAGE_LENGTH = 30000

    # The adapter splits long messages via send() so the stream consumer
    # delivers the full payload instead of truncating at MAX_MESSAGE_LENGTH.
    splits_long_messages = True

    def __init__(self, config):
        from gateway.config import Platform, PlatformConfig

        _cfg = config if config is not None else PlatformConfig()
        super().__init__(_cfg, Platform.TEAMS_MTK)

        _raw = os.getenv("MTK_TEAMS_CONVERSATION_ID", "").strip()
        self._conv_ids: List[str] = [c.strip() for c in _raw.split(",") if c.strip()]
        self._conv_id: Optional[str] = self._conv_ids[0] if self._conv_ids else None  # back-compat
        self._auth = _TeamsAuth()
        self._poll_task: Optional[asyncio.Task] = None
        self._connected = False
        self._user_oid: Optional[str] = None  # set during connect from first poll
        self._last_sent_message_id: Optional[str] = None  # id of last message WE sent (echo guard)
        self._last_sent_message_html: Optional[str] = None  # HTML cache for trailing-footer merge

        # Per-conversation last-seen message id (avoids replay on startup).
        self._last_message_ids: Dict[str, str] = {cid: None for cid in self._conv_ids}
        # Legacy single-conversation alias (kept so other call sites compile;
        # the active value now lives in _last_message_ids).
        self._last_message_id: Optional[str] = None

        # Mention gating: default on for groups, off for DMs.
        # A comma-separated list of conv IDs that should be treated as DMs
        # (no @mention required) even though they contain @thread in the ID.
        _no_mention_raw = os.getenv("MTK_TEAMS_NO_MENTION_CONVS", "").strip()
        self._no_mention_convs: set = {c.strip() for c in _no_mention_raw.split(",") if c.strip()}
        _rm = os.getenv("TEAMS_MTK_REQUIRE_MENTION", "true").lower()
        self.require_mention = _rm in ("true", "1", "yes", "on")

        # Model picker state — when a picker is active, short numeric replies
        # are intercepted and routed to the on_model_selected callback.
        # Keyed by conversation id so multiple conversations can each have
        # an active picker independently.
        self._model_picker_states: Dict[str, Optional[Dict[str, Any]]] = {
            cid: None for cid in self._conv_ids
        }
        # Legacy alias (None — use _model_picker_states[conv_id] instead).
        self._model_picker_state: Optional[Dict[str, Any]] = None

    # ---- Per-group config (gateway.teams_mtk.groups in config.yaml) ----

    def _group_config(self, conv_id: str) -> Dict[str, Any]:
        """Return the config.yaml entry for *conv_id*, or {} if unconfigured.

        Reads ``gateway.teams_mtk.groups.<conv_id>`` fresh on every call
        (no caching) so `hermes teams-mtk group set` changes are picked up
        after the next gateway restart without extra plumbing. See
        `hermes teams-mtk group add/list/set/remove` and
        openspec/changes/teams-mtk-group-whitelist/design.md.
        """
        try:
            from hermes_cli.config import load_config_readonly
            groups = (
                load_config_readonly()
                .get("gateway", {})
                .get("teams_mtk", {})
                .get("groups", {})
            )
        except Exception:
            return {}
        if not isinstance(groups, dict):
            return {}
        entry = groups.get(conv_id, {})
        return entry if isinstance(entry, dict) else {}

    def _group_blocked_toolsets(self, conv_id: str, user_id: Optional[str]) -> List[str]:
        """Union of group-level and per-user blocked_toolsets for *conv_id*/*user_id*."""
        group_cfg = self._group_config(conv_id)
        blocked = set(group_cfg.get("blocked_toolsets") or [])
        if user_id:
            per_user = group_cfg.get("per_user") or {}
            user_cfg = per_user.get(user_id) or {}
            blocked |= set(user_cfg.get("blocked_toolsets") or [])
        return sorted(blocked)

    def _group_blocked_keyword_patterns(self, conv_id: str) -> List[str]:
        """Raw regex patterns configured for *conv_id*'s blocked_keywords."""
        patterns = self._group_config(conv_id).get("blocked_keywords") or []
        return [p for p in patterns if isinstance(p, str) and p.strip()]

    # ---- BasePlatformAdapter required overrides ----

    async def connect(self, is_reconnect: bool = False) -> bool:
        if not self._conv_ids:
            logger.error("TeamsMTK: MTK_TEAMS_CONVERSATION_ID not set")
            return False

        try:
            # Validate token on startup
            self._auth.skype_token()
        except Exception as e:
            logger.error("TeamsMTK: auth failed — %s", e)
            return False

        # Seed last_message_ids per conversation to avoid replaying old messages
        for _conv_id in self._conv_ids:
            try:
                msgs = self._fetch_messages(conv_id=_conv_id, limit=5)
                if msgs:
                    self._last_message_ids[_conv_id] = msgs[-1].get("id")
                    # Extract user OID from first message's "from" URL
                    for m in msgs:
                        from_url = m.get("from", "")
                        if "8:orgid:" in from_url:
                            self._user_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")
                            logger.info("TeamsMTK: user OID: %s", self._user_oid)
                            break
                    logger.debug("TeamsMTK: seeded last_message_id=%s for conv=%s", self._last_message_ids[_conv_id], _conv_id[:30])
            except Exception as e:
                logger.warning("TeamsMTK: could not seed last message id for conv=%s: %s", _conv_id[:30], e)

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._mark_connected()
        logger.info(
            "TeamsMTK: connected — polling %d conversation(s) every %ds: %s",
            len(self._conv_ids), _POLL_INTERVAL,
            ", ".join(c[:40] for c in self._conv_ids),
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
        from gateway.platforms.base import SendResult
        if not content:
            return SendResult(success=True)

        # Outbound keyword blocking: if this group has blocked_keywords and
        # the agent's composed reply matches one, refuse to deliver the
        # original text and send the fixed notice instead. Skip the check
        # for the notice itself (avoids a pointless self-match) and for
        # metadata-flagged internal sends (skip_footer_extract covers
        # streaming footer merges, which are never a first-class reply).
        if content != self._BLOCKED_KEYWORD_NOTICE:
            _out_patterns = self._group_blocked_keyword_patterns(chat_id)
            _out_hit = self._find_blocked_keyword(content, _out_patterns)
            if _out_hit:
                logger.warning(
                    "TeamsMTK: blocked outbound reply in conv=%s (matched keyword pattern=%r)",
                    chat_id[:30], _out_hit,
                )
                content = self._BLOCKED_KEYWORD_NOTICE

        _skip_footer_extract = bool(metadata and metadata.get("skip_footer_extract"))
        try:
            import re, requests
            from requests.adapters import HTTPAdapter
            self._auth._inject_truststore()

            # Fresh session to avoid stale pooled connections through the proxy
            session = requests.Session()
            session.mount("https://", HTTPAdapter(pool_connections=0, pool_maxsize=0, max_retries=0))
            try:
                for attempt in range(2):
                    skype_token = self._auth.skype_token()
                    url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
                    # Build HTML using the shared template builder so send/edit
                    # always produce the same branded output.
                    html_content, runtime_footer = self._build_html(content, _skip_footer_extract)

                    # Trailing-footer-only message (streaming mode):
                    # Merge into the last body message instead of sending
                    # a separate mini-card.
                    from datetime import datetime
                    if not html_content or (runtime_footer and not content.strip()):
                        if self._last_sent_message_id and runtime_footer and self._last_sent_message_html:
                            _existing = self._last_sent_message_html
                            # Find the footer span in the cached HTML and
                            # replace it with the updated version that
                            # includes runtime_footer.
                            _old_footer_pat = re.compile(
                                r'(<span style="color:#888;font-size:0\.85em">)(.*?)(</span>)',
                                re.DOTALL,
                            )
                            _merged = f"— Hermes · {datetime.now().strftime('%Y-%m-%d %H:%M')} · {runtime_footer}"
                            _new_footer = f'<span style="color:#888;font-size:0.85em">{_merged}</span>'
                            _patched = _old_footer_pat.sub(
                                lambda m: m.group(1) + _merged + m.group(3),
                                _existing,
                                count=1,
                            )
                            if _patched == _existing:
                                # Fallback: append footer span if none found
                                _patched = _existing.replace(
                                    "</div>",
                                    f"{_new_footer}</div>",
                                    1,
                                )
                            try:
                                _edit_res = await self.edit_message(
                                    chat_id,
                                    self._last_sent_message_id,
                                    _patched,
                                    finalize=True,
                                )
                                if _edit_res.success:
                                    logger.info(
                                        "TeamsMTK: merged trailing footer into msg %s: %s",
                                        self._last_sent_message_id, runtime_footer,
                                    )
                                    # _last_sent_message_html is already updated
                                    # by edit_message() above (same id → cache sync).
                                    return SendResult(success=True)
                            except Exception as _ee:
                                logger.debug("TeamsMTK: footer edit failed, falling back to send: %s", _ee)
                        # Fall back: send as separate mini-card
                        # Re-generate with the footer-only template from _build_html
                        html_content, _ = self._build_html(runtime_footer, _skip_footer_extract=True)
                    payload = {
                        "content": html_content,
                        "messagetype": "RichText/Html",
                        "contenttype": "text",
                        "properties": {"hermes_sender": "agent"},
                    }
                    resp = session.post(
                        url,
                        json=payload,
                        headers={
                            "Authentication": f"skypetoken={skype_token}",
                            "Content-Type": "application/json",
                        },
                        verify=False,
                        timeout=15,
                    )
                    if resp.status_code == 401 and attempt == 0:
                        self._auth._force_refresh()
                        continue
                    if resp.status_code == 429 and attempt == 0:
                        logger.warning(
                            "TeamsMTK: send hit 429 rate limit for conv=%s — backing off %.1fs then retrying once",
                            chat_id[:30], self._RATE_LIMIT_BACKOFF_S,
                        )
                        await asyncio.sleep(self._RATE_LIMIT_BACKOFF_S)
                        continue
                    break
            finally:
                session.close()

            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
                # Cache the HTML for potential trailing-footer merge
                if html_content:
                    self._last_sent_message_html = html_content
            logger.info("TeamsMTK: sent message id=%s to %s (html=%d chars)", msg_id, chat_id, len(html_content) if html_content else 0)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.error("TeamsMTK: send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "group" if "@thread" in chat_id else "dm", "chat_id": chat_id}

    def _build_html(self, content: str, _skip_footer_extract: bool = False) -> tuple:
        """Shared HTML builder for send() and edit_message().

        Returns (html_content, runtime_footer) — the same branded template
        with purple left-border, emoji header, and footer span.
        """
        import re, markdown
        from datetime import datetime

        runtime_footer = ""

        if not _skip_footer_extract:
            # --- Case 1: trailing footer (streaming mode) ---
            # Must contain " · " to avoid eating normal single-line body content
            # (e.g. a streaming delta that happens to be one short sentence).
            _trailing = re.match(r'^([^\n]{3,80} · [^\n]{1,80})$', content)
            if _trailing:
                runtime_footer = _trailing.group(1).strip()
                content = ""  # nothing to render as body
            else:
                # --- Case 2: footer appended after \n\n (non-streaming) ---
                _footer_pat = re.compile(r'\n\n((?:[^\n]+ · )?[^\n]+%[^\n]*)$')
                _fm = _footer_pat.search(content)
                if _fm:
                    runtime_footer = _fm.group(1).strip()
                    content = content[:_fm.start()].rstrip()
                else:
                    # Broader: last \n\n paragraph with " · "
                    _broad_pat = re.compile(r'\n\n([^\n]{3,80})$')
                    _bm = _broad_pat.search(content)
                    if _bm:
                        _candidate = _bm.group(1).strip()
                        if ' · ' in _candidate and not re.search(r'[`#*]|^[-*>]', _candidate):
                            runtime_footer = _candidate
                            content = content[:_bm.start()].rstrip()
                    # Inline fallback
                    if not runtime_footer:
                        _inline = re.search(r'([^\n]{3,60} · \d+%[^\n]*)$', content)
                        if _inline:
                            runtime_footer = _inline.group(1).strip()
                            content = content[:_inline.start()].rstrip()

        # Convert (footer-stripped) content to Teams-compatible HTML
        if re.search(r'<(b|i|a|br|h[1-6]|ul|ol|li|pre|code|strong|em)\b', content):
            body_html = content.replace('\n', '<br>')
        else:
            body_html = markdown.markdown(
                content,
                extensions=['fenced_code', 'tables', 'nl2br', 'md_in_html'],
            )

        # Wrap in branded template: purple left-border + emoji header + footer
        agent_name = "Hermes"
        accent = "#6264A7"  # Teams purple
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        footer_parts = f"— {agent_name} · {ts}"
        if runtime_footer:
            footer_parts = f"{footer_parts} · {runtime_footer}"

        if body_html.strip():
            html_content = (
                f'<div style="border-left:3px solid {accent};'
                f'padding-left:10px;margin:6px 0">'
                f'<b>🤖 {agent_name}</b><br><br>'
                f'{body_html}<br>'
                f'<span style="color:#888;font-size:0.85em">{footer_parts}</span>'
                f'</div>'
            )
        else:
            # Footer-only — will be handled by caller (merge or mini-card)
            html_content = (
                f'<div style="border-left:3px solid {accent};'
                f'padding-left:10px;margin:6px 0">'
                f'<span style="color:#888;font-size:0.85em">{footer_parts}</span>'
                f'</div>'
            )

        return html_content, runtime_footer

    # Teams chat-service rate limit is documented as "3 calls / 5s"
    # (429 body: "API calls quota exceeded! 3Per05Secs"). Back off just past
    # that window before the single retry.
    _RATE_LIMIT_BACKOFF_S = 5.5

    async def edit_message(self, chat_id: str, message_id: str, content: str, *, finalize: bool = False) -> "SendResult":
        """Edit a previously sent message (optional — used for progress streaming).

        Never raises: any failure (429 after one backoff-retry, other HTTP
        errors, transport errors) degrades to ``SendResult(success=False)``
        so a dropped mid-stream edit or failed finalize never crashes the
        progress sender or the stream consumer.
        """
        from gateway.platforms.base import SendResult
        try:
            import re, requests
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages/{message_id}"

            # If content is already a branded-template HTML (e.g. from the
            # trailing-footer merge path), use it as-is to avoid double-wrapping.
            is_already_html = bool(re.search(r'<div\s+style="border-left:', content))
            if is_already_html:
                html_content = content
                runtime_footer = ""
            else:
                # Use the same branded template as send()
                html_content, runtime_footer = self._build_html(content)

            logger.info(
                "TeamsMTK: editing message %s — content=%d chars, html=%d chars, finalize=%s",
                message_id, len(content), len(html_content), finalize,
            )
            payload = {"content": html_content, "messagetype": "RichText/Html", "contenttype": "text"}
            headers = {"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"}
            resp = requests.put(url, json=payload, headers=headers, verify=False, timeout=30)
            if resp.status_code == 429:
                logger.warning(
                    "TeamsMTK: edit hit 429 rate limit for msg %s — backing off %.1fs then retrying once",
                    message_id, self._RATE_LIMIT_BACKOFF_S,
                )
                await asyncio.sleep(self._RATE_LIMIT_BACKOFF_S)
                resp = requests.put(url, json=payload, headers=headers, verify=False, timeout=30)
            resp.raise_for_status()
            logger.info("TeamsMTK: edited message %s (resp=%d bytes)", message_id, len(resp.content))
            # Keep the HTML cache in sync so the trailing-footer merge
            # operates on the latest content, not a stale snapshot.
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.warning("TeamsMTK: edit failed (%s) — streaming will fall back to new message", e)
            return SendResult(success=False, error=str(e))

    async def cancel_background_tasks(self) -> None:
        """Cancel poll task, then delegate to base for in-flight message tasks."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await super().cancel_background_tasks()

    # ---- Interactive model picker ----

    async def send_model_picker(
        self,
        chat_id: str,
        providers: list,
        current_model: str,
        current_provider: str,
        session_key: str,
        on_model_selected,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SendResult":
        """Send a two-step model picker: pick provider, then pick model.

        Since TeamsMTK uses polling (not a bot webhook), Adaptive Card
        Action.Submit callbacks are not available. Instead, we use a
        two-step flow:

        Step 1 (this method): Show numbered provider list.
        Step 2 (_send_model_sub_picker, triggered by interceptor): Show
          the chosen provider's models.

        The poll loop interceptor handles both steps.
        """
        from gateway.platforms.base import SendResult

        try:
            from hermes_cli.providers import get_label
        except ImportError:
            def get_label(slug):
                return slug

        provider_label = get_label(current_provider)
        accent = "#6264A7"
        btn_style = (
            "display:inline-block;min-width:20px;height:20px;"
            "border-radius:10px;text-align:center;line-height:20px;"
            f"background:{accent};color:#fff;font-size:0.75em;"
            "font-weight:bold;margin-right:5px;padding:0 3px;"
        )

        # Deduplicate providers by slug (same slug = same endpoint)
        seen_slugs = set()
        deduped_providers = []
        for prov in providers:
            slug = prov.get("slug", "")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            deduped_providers.append(prov)

        # Build provider list
        prov_entries = []  # (prov_slug, prov_name, model_count, is_current)
        for prov in deduped_providers:
            prov_name = prov.get("name") or prov.get("slug", "?")
            prov_slug = prov.get("slug", "")
            models = prov.get("models", [])
            is_current = prov.get("is_current", False)
            prov_entries.append((prov_slug, prov_name, len(models), is_current))

        lines = [
            f'<div style="font-weight:bold;margin-bottom:4px">'
            f'⚙️ Select Provider</div>',
            f'<div style="margin-bottom:8px;font-size:0.9em">'
            f'Current: <b>{current_model or "unknown"}</b> via {provider_label}</div>',
        ]

        for idx, (prov_slug, prov_name, model_count, is_current) in enumerate(prov_entries, 1):
            cur_tag = ' ←' if is_current else ''
            cnt_tag = f'<span style="color:#888;font-size:0.8em">({model_count})</span>' if model_count else ''
            lines.append(
                f'<div style="margin:1px 0">'
                f'<span style="{btn_style}">{idx}</span>'
                f'<span style="font-size:0.9em">{prov_name}{cur_tag}</span> {cnt_tag}'
                f'</div>'
            )

        lines.append(
            f'<div style="margin-top:8px;padding:4px 6px;'
            f'background:#f0f0f0;border-radius:4px;font-size:0.85em">'
            f'💬 Reply provider number · <code>/model <name></code> for exact match</div>'
        )

        body_html = "".join(lines)
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = (
            f'<div style="border-left:3px solid {accent};'
            f'padding:8px 10px;margin:6px 0;background:#fafafa;'
            f'border-radius:0 6px 6px 0">'
            f'{body_html}'
            f'<div style="color:#888;font-size:0.8em;margin-top:6px">'
            f'— Hermes · {ts}</div>'
            f'</div>'
        )

        # Send provider list via Skype API
        try:
            self._auth._inject_truststore()
            import requests as _req
            from requests.adapters import HTTPAdapter
            sess = _req.Session()
            sess.mount("https://", HTTPAdapter(pool_connections=0, pool_maxsize=0, max_retries=0))
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            payload = {
                "content": html_content,
                "messagetype": "RichText/Html",
                "contenttype": "text",
            }
            resp = sess.post(
                url,
                json=payload,
                headers={
                    "Authentication": f"skypetoken={skype_token}",
                    "Content-Type": "application/json",
                },
                verify=False,
                timeout=15,
            )
            resp.raise_for_status()
            sess.close()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
            logger.info("TeamsMTK: model picker step 1 (providers) sent (id=%s)", msg_id)
        except Exception as e:
            logger.error("TeamsMTK: model picker step 1 send failed: %s", e)
            return SendResult(success=False, error=str(e))

        # Store picker state — step 1: waiting for provider selection
        # prov_list carries the deduped provider objects for step 2
        self._model_picker_states[chat_id] = {
            "step": "provider",
            "prov_entries": prov_entries,  # list of (slug, name, count, is_cur)
            "prov_objects": deduped_providers,  # original provider dicts
            "on_model_selected": on_model_selected,
            "current_model": current_model,
            "current_provider": current_provider,
        }

        return SendResult(success=True, message_id=str(msg_id) if msg_id else None)

    async def _send_model_sub_picker(
        self,
        chat_id: str,
        chosen_prov_idx: int,
    ) -> None:
        """Step 2: send the model list for the chosen provider.

        Called by the interceptor after the user picks a provider number.
        """
        picker = self._model_picker_states.get(chat_id)
        if picker is None or picker.get("step") != "provider":
            return

        prov_entries = picker["prov_entries"]
        if not (1 <= chosen_prov_idx <= len(prov_entries)):
            return

        chosen_slug, chosen_name, _, _ = prov_entries[chosen_prov_idx - 1]

        # Find the provider object to get its model list
        chosen_prov_obj = None
        for prov in picker["prov_objects"]:
            if prov.get("slug", "") == chosen_slug:
                chosen_prov_obj = prov
                break
        if chosen_prov_obj is None:
            return

        models = chosen_prov_obj.get("models", [])
        accent = "#6264A7"
        btn_style = (
            "display:inline-block;min-width:20px;height:20px;"
            "border-radius:10px;text-align:center;line-height:20px;"
            f"background:{accent};color:#fff;font-size:0.75em;"
            "font-weight:bold;margin-right:5px;padding:0 3px;"
        )

        current_model = picker.get("current_model", "")
        is_current_prov = chosen_prov_obj.get("is_current", False)

        lines = [
            f'<div style="font-weight:bold;margin-bottom:4px">'
            f'⚙️ {chosen_name} — Select Model</div>',
        ]

        if not models:
            # Provider has no model list — user picks "(auto)"
            lines.append(
                f'<div style="margin:1px 0">'
                f'<span style="{btn_style}">1</span>'
                f'<span style="font-family:monospace;font-size:0.85em">(auto)</span>'
                f'</div>'
            )
            model_entries = [(chosen_slug, "(auto)", chosen_name)]
        else:
            model_entries = []
            ENTRIES_PER_PAGE = 40
            shown = models[:ENTRIES_PER_PAGE]
            remaining = len(models) - ENTRIES_PER_PAGE
            for m in shown:
                is_cur = (m == current_model and is_current_prov)
                cur_badge = (
                    '<span style="background:#4CAF50;color:#fff;'
                    'border-radius:3px;padding:0 3px;font-size:0.7em;'
                    'margin-left:3px">✓</span>' if is_cur else ''
                )
                idx = len(model_entries) + 1
                lines.append(
                    f'<div style="margin:1px 0">'
                    f'<span style="{btn_style}">{idx}</span>'
                    f'<span style="font-family:monospace;font-size:0.85em">{m}</span>'
                    f'{cur_badge}'
                    f'</div>'
                )
                model_entries.append((chosen_slug, m, chosen_name))
            if remaining > 0:
                lines.append(
                    f'<div style="margin:4px 0;font-size:0.85em;color:#888">'
                    f'…+{remaining} more — use <code>/model <name></code> for full list</div>'
                )

        lines.append(
            f'<div style="margin-top:8px;padding:4px 6px;'
            f'background:#f0f0f0;border-radius:4px;font-size:0.85em">'
            f'💬 Reply model number · <code>/model <name></code> for exact match</div>'
        )

        body_html = "".join(lines)
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = (
            f'<div style="border-left:3px solid {accent};'
            f'padding:8px 10px;margin:6px 0;background:#fafafa;'
            f'border-radius:0 6px 6px 0">'
            f'{body_html}'
            f'<div style="color:#888;font-size:0.8em;margin-top:6px">'
            f'— Hermes · {ts}</div>'
            f'</div>'
        )

        # Send model list via Skype API
        try:
            self._auth._inject_truststore()
            import requests as _req
            from requests.adapters import HTTPAdapter
            sess = _req.Session()
            sess.mount("https://", HTTPAdapter(pool_connections=0, pool_maxsize=0, max_retries=0))
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            payload = {
                "content": html_content,
                "messagetype": "RichText/Html",
                "contenttype": "text",
            }
            resp = sess.post(
                url,
                json=payload,
                headers={
                    "Authentication": f"skypetoken={skype_token}",
                    "Content-Type": "application/json",
                },
                verify=False,
                timeout=15,
            )
            resp.raise_for_status()
            sess.close()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
            logger.info(
                "TeamsMTK: model picker step 2 (models for %s) sent (id=%s)",
                chosen_name, msg_id,
            )
        except Exception as e:
            logger.error("TeamsMTK: model picker step 2 send failed: %s", e)
            return

        # Update picker state — step 2: waiting for model selection
        self._model_picker_states[chat_id] = {
            "step": "model",
            "entries": model_entries,  # list of (prov_slug, model_id, prov_name)
            "on_model_selected": picker["on_model_selected"],
            "current_model": picker.get("current_model"),
            "current_provider": picker.get("current_provider"),
        }

    def _fetch_messages(self, conv_id: str = None, limit: int = 20) -> List[dict]:
        """Fetch recent messages from a conversation (sync, called from thread).

        Args:
            conv_id: Conversation ID to fetch.  Defaults to ``self._conv_id``
                     (first / back-compat conversation).

        Uses a fresh ``requests.Session`` each call to avoid stale pooled
        connections — the MTK SSL proxy can silently drop idle TCP connections
        after ~20 min, causing ConnectTimeout on reused sockets.
        """
        if conv_id is None:
            conv_id = self._conv_id
        import urllib.parse, requests
        from requests.adapters import HTTPAdapter

        self._auth._inject_truststore()
        import time as _t
        _t0 = _t.time()
        session = requests.Session()
        session.mount("https://", HTTPAdapter(pool_connections=0, pool_maxsize=0, max_retries=0))

        try:
            for attempt in range(2):
                skype_token = self._auth.skype_token()
                encoded_conv_id = urllib.parse.quote(conv_id, safe='')
                url = f"{self._auth.msg_base}/conversations/{encoded_conv_id}/messages"
                resp = session.get(
                    url,
                    params={"pageSize": limit, "startTime": 0},
                    headers={"Authentication": f"skypetoken={skype_token}"},
                    verify=False,
                    timeout=15,
                )
                if resp.status_code == 401 and attempt == 0:
                    self._auth._force_refresh()
                    continue
                resp.raise_for_status()
                break
            else:
                raise RuntimeError("_fetch_messages: all attempts exhausted")
        except requests.ConnectionError:
            logger.warning("TeamsMTK: _fetch_messages ConnectionError after %.1fs", _t.time()-_t0)
            # Timeout / reset — retry once with fresh token then give up this poll
            raise
        finally:
            session.close()
            logger.info("TeamsMTK: _fetch_messages done in %.1fs", _t.time()-_t0)

        data = resp.json()
        messages = data.get("messages") or []
        return list(reversed(messages))  # oldest-first for processing

    async def _poll_loop(self) -> None:
        """Poll all monitored conversations for new messages every _POLL_INTERVAL seconds.

        On consecutive errors, backs off up to 5× the normal interval to avoid
        hammering a downed proxy. Resets on first successful fetch.
        """
        import concurrent.futures
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(len(self._conv_ids), 1))
        _backoff = 1  # multiplier for _POLL_INTERVAL on errors

        while self._running:
            try:
                logger.info("TeamsMTK: poll tick (backoff=%dx, convs=%d)", _backoff, len(self._conv_ids))
                for _conv_id in self._conv_ids:
                    msgs = await loop.run_in_executor(executor, lambda _c=_conv_id: self._fetch_messages(_c, 20))
                    logger.info("TeamsMTK: poll conv=%s got %d messages", _conv_id[:40], len(msgs) if msgs else 0)
                    await self._process_new_messages(_conv_id, msgs)
                _backoff = 1  # reset backoff on success
            except asyncio.CancelledError:
                break
            except Exception as e:
                _backoff = min(_backoff * 2, 5)
                logger.warning("TeamsMTK: poll error (backoff=%dx): %s", _backoff, e, exc_info=True)

            try:
                await asyncio.sleep(_POLL_INTERVAL * _backoff)
            except asyncio.CancelledError:
                break

        executor.shutdown(wait=False)

    async def _download_attachment(self, url: str, kind: str, filename: str) -> Optional[str]:
        """Download a Teams attachment and cache it locally.

        Returns the local file path, or None on failure.
        """
        from gateway.platforms.base import cache_image_from_bytes, cache_document_from_bytes
        import aiohttp

        headers = {"Authorization": f"Bearer {self._auth.skype_token}"}
        try:
            async with aiohttp.ClientSession(headers=headers) as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as resp:
                    if resp.status != 200:
                        logger.warning("TeamsMTK: attachment download failed status=%d url=%.60s", resp.status, url)
                        return None
                    data = await resp.read()
        except Exception as exc:
            logger.warning("TeamsMTK: attachment download error: %s url=%.60s", exc, url)
            return None

        try:
            if kind == "image":
                # Determine extension from URL or default to .jpg
                _ext = ".jpg"
                if ".png" in url.lower():
                    _ext = ".png"
                elif ".gif" in url.lower():
                    _ext = ".gif"
                elif ".webp" in url.lower():
                    _ext = ".webp"
                return cache_image_from_bytes(data, _ext)
            else:
                # Document / file — derive filename from URL if missing
                if not filename:
                    _parts = url.rsplit("/", 1)
                    filename = _parts[-1].split("?", 1)[0] if len(_parts) > 1 else "document.bin"
                return cache_document_from_bytes(data, filename)
        except Exception as exc:
            logger.warning("TeamsMTK: attachment cache error: %s", exc)
            return None

    async def _process_new_messages(self, conv_id: str, messages: List[dict]) -> None:
        """Dispatch messages newer than last_message_id for *conv_id* to the hermes agent."""
        if not messages or not self._message_handler:
            return

        _last_id = self._last_message_ids.get(conv_id)
        new_messages = []
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue
            if _last_id is None or msg_id > _last_id:
                new_messages.append(msg)
            else:
                logger.debug("TeamsMTK: skipping old msg id=%s (<= last=%s)", msg_id, _last_id)

        if new_messages:
            logger.info("TeamsMTK: %d new messages to process", len(new_messages))

        for msg in new_messages:
            msg_id = msg.get("id", "")
            msg_type = msg.get("messagetype", "")
            content = msg.get("content", "")
            sender = msg.get("imdisplayname") or msg.get("fromDisplayNameInToken") or "Teams User"

            logger.info(
                "TeamsMTK: inspecting msg id=%s type=%s conv=%s last_sent=%s text=%.40r",
                msg_id, msg_type, conv_id[:30], self._last_sent_message_id,
                content.strip()[:40] if content else "<empty>",
            )

            # Skip system messages
            if msg_type in ("ThreadActivity/MemberJoined", "ThreadActivity/TopicUpdate"):
                self._last_message_ids[conv_id] = msg_id
                continue

            # Skip empty messages
            if not content:
                self._last_message_ids[conv_id] = msg_id
                continue

            # Echo-loop guard: in a self-chat (48:notes), every message
            # comes from the same OID.  We use three signals to decide
            # whether a message is our own output:
            #   1. properties.hermes_sender == "agent"  (tag on send)
            #   2. clientmessageid matches our sent id  (id-match fallback)
            #   3. composetime is within 2s and content matches last sent
            #      (catches cases where Teams API strips properties)
            is_own = False
            props = msg.get("properties", {})
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            if props.get("hermes_sender") == "agent":
                is_own = True
            if self._last_sent_message_id and str(msg_id) == str(self._last_sent_message_id):
                is_own = True
            if is_own:
                logger.info("TeamsMTK: skipping own sent message id=%s", msg_id)
                self._last_message_ids[conv_id] = msg_id
                continue

            # ---- Attachment extraction (before HTML stripping) ----
            # Skype API messages embed attachments in HTML <img>/<file> tags
            # and/or in the top-level 'attachments' / properties.files arrays.
            import re as _re
            _att_urls: List[str] = []      # remote URLs to download
            _att_names: List[str] = []     # filenames (for documents)
            _att_kinds: List[str] = []     # "image" | "file" per attachment

            # 1) Inline images from HTML <img src="...">
            for m in _re.finditer(r'<img\s[^>]*?src="([^"]+)"', content or "", _re.IGNORECASE):
                url = m.group(1)
                if url.startswith("http"):
                    _att_urls.append(url)
                    _att_names.append("")
                    _att_kinds.append("image")

            # 2) File attachments from HTML <file> tags (Skype format)
            #    <file src="..." name="..." ...>
            for m in _re.finditer(r'<file\s[^>]*?src="([^"]+)"[^>]*?(?:name="([^"]*)")?', content or "", _re.IGNORECASE):
                url = m.group(1)
                name = (m.group(2) or "").strip()
                if url.startswith("http"):
                    _att_urls.append(url)
                    _att_names.append(name)
                    _att_kinds.append("file")

            # 3) properties.files array (file shares like PDF/DOCX)
            if isinstance(props, dict):
                _files = props.get("files")
                if isinstance(_files, list):
                    for fi in _files:
                        if isinstance(fi, dict):
                            furl = fi.get("contentUrl") or fi.get("contenturl") or ""
                            fname = fi.get("name") or fi.get("fileName") or ""
                            if furl.startswith("http"):
                                _att_urls.append(furl)
                                _att_names.append(fname)
                                _att_kinds.append("file")

            # 4) Top-level 'attachments' array (rare in Skype API but safe to check)
            _attach_arr = msg.get("attachments")
            if isinstance(_attach_arr, list):
                for att in _attach_arr:
                    if isinstance(att, dict):
                        aurl = att.get("contentUrl") or att.get("contenturl") or ""
                        aname = att.get("name") or ""
                        act = (att.get("contentType") or "").lower()
                        if aurl.startswith("http"):
                            _att_urls.append(aurl)
                            _att_names.append(aname)
                            _att_kinds.append("image" if act.startswith("image/") else "file")

            if _att_urls:
                logger.info(
                    "TeamsMTK: msg id=%s has %d attachment(s): %s",
                    msg_id, len(_att_urls),
                    [f"{k}:{n or u[:40]}" for k, n, u in zip(_att_kinds, _att_names, _att_urls)],
                )

            # Better HTML stripping (matches teams skill _process_message_content)
            import re
            text = re.sub(r"<[^>]+>", "", content).strip()
            # Collapse multiple whitespace/newlines from HTML
            text = re.sub(r"\s+", " ", text).strip()
            # For messages with only attachments and no text, keep a placeholder
            # so the message isn't discarded as "empty"
            if not text and _att_urls:
                text = "[attachment]"
            if not text:
                self._last_message_ids[conv_id] = msg_id
                continue

            # Mention gating: in groups, only respond when @hermes is present.
            # Resolution order: gateway.teams_mtk.groups.<id>.require_mention
            # (config.yaml, set via `hermes teams-mtk group add/set`) → the
            # legacy MTK_TEAMS_NO_MENTION_CONVS env var (back-compat) →
            # self.require_mention (global TEAMS_MTK_REQUIRE_MENTION default).
            is_group = "@thread" in conv_id
            _group_cfg = self._group_config(conv_id) if is_group else {}
            _cfg_require_mention = _group_cfg.get("require_mention")
            if _cfg_require_mention is not None:
                effective_require_mention = bool(_cfg_require_mention)
            elif conv_id in self._no_mention_convs:
                effective_require_mention = False
            else:
                effective_require_mention = self.require_mention
            if is_group and effective_require_mention:
                if self._MENTION_TAG.lower() not in text.lower():
                    logger.debug(
                        "TeamsMTK: ignoring group message (require_mention=true, no %s): %s",
                        self._MENTION_TAG, text[:60],
                    )
                    self._last_message_ids[conv_id] = msg_id
                    continue
                # Strip the @hermes mention so the agent doesn't misinterpret it
                text = re.sub(
                    re.escape(self._MENTION_TAG) + r"\b", "", text, flags=re.IGNORECASE
                ).strip()

            # Per-group keyword blocking (inbound): a match blocks the
            # message from reaching the agent entirely, replying with a
            # fixed refusal notice instead. Checked after mention-tag
            # stripping so the pattern only sees the actual question text.
            if is_group:
                _blocked_patterns = self._group_blocked_keyword_patterns(conv_id)
                _hit = self._find_blocked_keyword(text, _blocked_patterns)
                if _hit:
                    logger.warning(
                        "TeamsMTK: blocked inbound message in conv=%s (matched keyword pattern=%r): %s",
                        conv_id[:30], _hit, text[:60],
                    )
                    self._last_message_ids[conv_id] = msg_id
                    try:
                        await self.send(conv_id, self._BLOCKED_KEYWORD_NOTICE)
                    except Exception as e:
                        logger.error("TeamsMTK: failed to send blocked-keyword notice: %s", e)
                    continue

            logger.info("TeamsMTK: new message from %s: %s", sender, text[:60])

            # ---- Model picker interception (two-step) ----
            # Per-conversation picker state so multiple conversations
            # can each have an active picker independently.
            _picker = self._model_picker_states.get(conv_id)
            if _picker is not None and len(text) <= 40:
                import re as _nre
                _m = _nre.search(r"\b(\d{1,3})\b", text)
                if _m:
                    choice = int(_m.group(1))
                    step = _picker.get("step", "model")

                    if step == "provider":
                        # Step 1: provider selection
                        prov_entries = _picker.get("prov_entries", [])
                        if 1 <= choice <= len(prov_entries):
                            prov_slug, prov_name, _, _ = prov_entries[choice - 1]
                            logger.info(
                                "TeamsMTK: model picker provider selection: %d → %s (conv=%s)",
                                choice, prov_name, conv_id[:30],
                            )
                            # Don't clear state — transition to step 2
                            # (sub-picker will update it)
                            try:
                                await self._send_model_sub_picker(
                                    conv_id, choice,
                                )
                            except Exception as e:
                                logger.error(
                                    "TeamsMTK: model sub-picker send error: %s", e
                                )
                            self._last_message_ids[conv_id] = msg_id
                            continue

                    elif step == "model":
                        # Step 2: model selection
                        entries = _picker.get("entries", [])
                        if 1 <= choice <= len(entries):
                            prov_slug, model_id, prov_name = entries[choice - 1]
                            logger.info(
                                "TeamsMTK: model picker model selection: %d → %s/%s (conv=%s)",
                                choice, prov_slug, model_id, conv_id[:30],
                            )
                            cb = _picker.get("on_model_selected")
                            # Clear picker state *before* the callback to
                            # prevent re-triggering on the confirmation reply.
                            self._model_picker_states[conv_id] = None
                            if cb is not None:
                                try:
                                    confirm = await cb(
                                        conv_id, model_id or prov_slug, prov_slug,
                                    )
                                    # Send confirmation back to the conversation
                                    if confirm:
                                        await self.send(conv_id, confirm)
                                except Exception as e:
                                    logger.error("TeamsMTK: model picker callback error: %s", e)
                                    await self.send(conv_id, f"⚠ Model switch failed: {e}")
                            self._last_message_ids[conv_id] = msg_id
                            continue

            try:
                from gateway.platforms.base import MessageEvent, MessageType
                from gateway.config import Platform

                from gateway.session import SessionSource
                _from_url = msg.get("from", "")
                user_id = sender  # fallback to display name
                if "8:orgid:" in _from_url:
                    user_id = _from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")

                source = SessionSource(
                    platform=Platform.TEAMS_MTK,
                    chat_id=conv_id,
                    user_id=user_id,
                    user_name=sender,
                    # chat_type reflects the actual platform conversation
                    # type (@thread = group) independent of mention policy.
                    # Previously this conflated "@thread AND not in
                    # _no_mention_convs" — which meant a mention-exempt
                    # group was misclassified as "dm" and fell through to
                    # the individual GATEWAY_ALLOWED_USERS allowlist
                    # instead of the group whitelist (authz_mixin.py
                    # _teams_mtk_group_is_whitelisted). Mention exemption
                    # and chat classification are independent concerns.
                    chat_type="group" if "@thread" in conv_id else "dm",
                )

                # Download & cache attachments
                _media_urls: List[str] = []
                _media_types: List[str] = []
                _dominant_type = MessageType.TEXT
                for _i, (_aurl, _aname, _akind) in enumerate(zip(_att_urls, _att_names, _att_kinds)):
                    _local = await self._download_attachment(_aurl, _akind, _aname)
                    if _local:
                        _media_urls.append(_local)
                        _media_types.append(_akind)
                        # First attachment determines the overall message_type
                        if _i == 0:
                            _dominant_type = MessageType.PHOTO if _akind == "image" else MessageType.DOCUMENT
                    else:
                        logger.warning("TeamsMTK: skipping failed attachment %d/%d", _i + 1, len(_att_urls))

                event = MessageEvent(
                    text=text,
                    message_type=_dominant_type,
                    source=source,
                    message_id=msg_id,
                    media_urls=_media_urls or None,
                    media_types=_media_types or None,
                )
                # Use handle_message() (not _message_handler directly) so the
                # full base-class pipeline runs: session guard, typing indicator,
                # _process_message_background, and _send_with_retry delivery.
                await self.handle_message(event)
            except Exception as e:
                logger.error("TeamsMTK: handler error for message %s: %s", msg_id, e, exc_info=True)
            finally:
                self._last_message_ids[conv_id] = msg_id
