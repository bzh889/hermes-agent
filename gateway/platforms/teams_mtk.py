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

# SDK pure-function HTML stripper (no auth/instance required)
#
# NOTE: the package's installed top-level module is ``teams_skype_sdk``
# (see lib/teams_skype_sdk/pyproject.toml — [tool.setuptools.packages.find]
# include = ["teams_skype_sdk*"]), not ``src``. The original "src.api.*"
# imports below silently failed on every machine (ModuleNotFoundError,
# swallowed by the bare except ImportError), so _SDK_AVAILABLE was always
# False and every code path that branches on it fell through to the regex/
# aiohttp fallback — functionally safe, but the SDK integration from the
# "Phase1 SDK integration" commit was never actually exercised.
try:
    from teams_skype_sdk.api._http import strip_teams_html as _strip_teams_html
except ImportError:
    _strip_teams_html = None  # fallback to regex if SDK not on path

# SDK download_with_auth_url for domain-appropriate attachment downloads
try:
    from teams_skype_sdk.api._http import download_with_auth_url as _sdk_download
except ImportError:
    _sdk_download = None  # fallback to aiohttp when SDK not on path

# SDK MessagesService for normalized message fetching
try:
    from teams_skype_sdk.api._http import HTTPLayer as _SDKHTTPLayer
    from teams_skype_sdk.api._messages import MessagesService as _SDKMessages
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

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
                # Auto-purge corrupted cache so next poll triggers re-auth
                # instead of permanently blocking on every tick.
                logger.warning(
                    "TeamsMTK: token cache corrupted and unrecoverable (%s) — "
                    "deleting cache to force re-authentication on next poll",
                    self.TOKEN_CACHE,
                )
                try:
                    self.TOKEN_CACHE.unlink(missing_ok=True)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Teams token cache was corrupted and has been deleted: "
                    f"{self.TOKEN_CACHE}. Re-authenticate: python ~/.claude/skills/teams/auth_run.py"
                )

    def _save(self, tokens: dict) -> None:
        """Atomic write: write to temp file then rename to prevent corruption
        from concurrent writes or power loss mid-write."""
        self.TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.TOKEN_CACHE.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(tokens, f)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.TOKEN_CACHE)
        except Exception:
            # Clean up temp file on failure
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise

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

    # Graph API scope used by graph_token() — distinct from the Skype scope
    # (_SKYPE_SCOPE) used by _refresh(). Cached separately in the same token
    # cache file under graph_token/graph_token_saved_at/graph_token_expires_in
    # so a Graph refresh never disturbs the Skype token's expiry bookkeeping.
    _GRAPH_SCOPE = "https://graph.microsoft.com/.default offline_access"

    def graph_token(self) -> str:
        """Return a valid Microsoft Graph API access token.

        Used by send_document() (OneDrive upload + share link) and the m365
        skill scripts. Exchanges the cached refresh_token for a Graph-scoped
        access token via the same OAuth client as the Skype token flow, and
        caches the result (graph_token / graph_token_saved_at /
        graph_token_expires_in) alongside the Skype tokens so repeated calls
        within the token lifetime are free.
        """
        import requests

        with self._lock:
            tok = self._load()
            saved_at = tok.get("graph_token_saved_at", 0)
            expires_in = tok.get("graph_token_expires_in", 0)
            if tok.get("graph_token") and time.time() < saved_at + expires_in - 300:
                return tok["graph_token"]

            self._inject_truststore()
            refresh_token = tok.get("refresh_token", "")
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
                    "scope": self._GRAPH_SCOPE,
                },
                verify=False,
                timeout=30,
            )
            resp.raise_for_status()
            new_tok = resp.json()

            tok["graph_token"] = new_tok["access_token"]
            tok["graph_token_saved_at"] = int(time.time())
            tok["graph_token_expires_in"] = new_tok.get("expires_in", 3600)
            if new_tok.get("refresh_token"):
                tok["refresh_token"] = new_tok["refresh_token"]
            self._save(tok)
            return tok["graph_token"]

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


class _SDKAuthAdapter:
    """Duck-typing adapter so gateway _TeamsAuth works with SDK HTTPLayer.

    SDK expects auth.get_skype_token() and auth.get_access_token();
    gateway has auth.skype_token() and auth.access_token().
    This thin wrapper bridges the naming gap.
    """
    def __init__(self, gw_auth: _TeamsAuth):
        self._gw = gw_auth

    def get_skype_token(self) -> str:
        return self._gw.skype_token()

    def get_access_token(self) -> str:
        return self._gw.access_token()


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
        # TTL-based echo-guard cache — replaces a raw growing set() so sent
        # message ids expire instead of accumulating forever across a
        # long-lived gateway process. See gateway/platforms/helpers.py.
        from gateway.platforms.helpers import MessageDeduplicator
        self._sent_dedup = MessageDeduplicator()

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

        # Reply throttle: minimum seconds between consecutive sends to the
        # same conversation. 0 = disabled. Read from
        # gateway.teams_mtk.reply_throttle_seconds in config.yaml.
        try:
            from hermes_cli.config import load_config_readonly
            _cfg_throttle = (
                load_config_readonly()
                .get("gateway", {})
                .get("teams_mtk", {})
                .get("reply_throttle_seconds", 0)
            )
            self._reply_throttle_seconds: float = float(_cfg_throttle)
        except Exception:
            self._reply_throttle_seconds: float = 0.0
        self._last_reply_at: Dict[str, float] = {}

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
            # Reply throttle: wait if this conversation was answered too
            # recently (prevents rapid-fire flooding).
            await self._maybe_throttle(chat_id)

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
                self._sent_dedup.is_duplicate(str(msg_id))  # register as seen
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

    async def _maybe_throttle(self, chat_id: str):
        """If reply_throttle_seconds > 0 and this conv was answered recently,
        sleep for the remaining window so we don't flood the channel.

        Per-conv tracking: a reply to conv A doesn't delay conv B.
        """
        if self._reply_throttle_seconds <= 0:
            return
        import time
        now = time.monotonic()
        last = self._last_reply_at.get(chat_id)
        if last is not None:
            elapsed = now - last
            remaining = self._reply_throttle_seconds - elapsed
            if remaining > 0:
                logger.info(
                    "TeamsMTK: throttling conv=%s — %.1fs since last reply, waiting %.1fs",
                    chat_id[:30], elapsed, remaining,
                )
                await asyncio.sleep(remaining)
        # Record the *intended* send time (before the actual POST) so
        # the next call measures from this point.
        self._last_reply_at[chat_id] = time.monotonic()

    async def edit_message(self, chat_id: str, message_id: str, content: str, *, finalize: bool = False) -> "SendResult":
        """Edit a previously sent message (optional — used for progress streaming).

        Never raises: any failure (429 after one backoff-retry, other HTTP
        errors, transport errors) degrades to ``SendResult(success=False)``
        so a dropped mid-stream edit or failed finalize never crashes the
        progress sender or the stream consumer.
        """
        from gateway.platforms.base import SendResult
        try:
            # Respect per-conv throttle to avoid hitting 429 on rapid edits
            await self._maybe_throttle(chat_id)

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

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Send a one-shot typing indicator via the Skype chat service.

        Posts {"messagetype": "Control/Typing", "content": ""} — the Skype
        consumer messaging protocol's typing-indicator message type. Callers
        (BasePlatformAdapter._keep_typing) invoke this on a repeating timer
        while an agent turn is in flight, so any failure here (network,
        auth, rate limit) must be swallowed rather than raised — a dropped
        typing ping is invisible to the user, but an unhandled exception
        would kill the keep-typing loop for the rest of the turn.
        """
        try:
            self._auth._inject_truststore()
            import requests
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            payload = {"messagetype": "Control/Typing", "content": ""}
            headers = {"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"}
            with requests.Session() as session:
                resp = session.post(url, json=payload, headers=headers, verify=False, timeout=10)
            if resp.status_code != 201:
                logger.warning(
                    "TeamsMTK: send_typing got status %s for conv=%s: %s",
                    resp.status_code, chat_id[:30], (resp.text or "")[:200],
                )
        except Exception as e:
            logger.debug("TeamsMTK: send_typing failed (non-fatal): %s", e)

    # ---- G-MEDIA: image / document / adaptive card sending ----

    # AMS (Async Media Service) endpoints — reverse-engineered from the teams
    # skill's src/api/_files.py + src/api/_constants.py. AMS uses a DIFFERENT
    # auth header format than the chat service ("skype_token {token}", not
    # "skypetoken={token}") and requires the Teams desktop User-Agent.
    _AMS_BASE_URL = "https://api.asm.skype.com/v1/objects"
    _AMS_USER_AGENT = "27/1.0.0.0"

    async def send_image_file(self, chat_id: str, path: str, caption: str = "") -> "SendResult":
        """Upload a local image to AMS and send it inline (AMS 3-step flow).

        Step 1: POST /v1/objects — create an AMS object with read permission
                scoped to this conversation ({"type": "pish/image",
                "permissions": {chat_id: ["read"]}}).
        Step 2: PUT /v1/objects/{id}/content/imgpsh — upload the raw image
                bytes (NOT /content/original — that path 404s for this object
                type).
        Step 3: POST .../messages with an <img> tag using the AMSImage schema
                markup and "amsreferences": [object_id] so Teams renders it
                as a native inline image instead of a plain link.
        """
        from gateway.platforms.base import SendResult
        import mimetypes, requests
        try:
            with open(path, "rb") as f:
                image_data = f.read()
        except OSError as e:
            return SendResult(success=False, error=f"Cannot read image file: {e}")

        content_type = mimetypes.guess_type(path)[0] or "image/png"

        try:
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            ams_headers = {
                "Authorization": f"skype_token {skype_token}",
                "User-Agent": self._AMS_USER_AGENT,
            }

            # Step 1: create AMS object
            create_resp = requests.post(
                self._AMS_BASE_URL,
                headers={**ams_headers, "Content-Type": "application/json"},
                json={"type": "pish/image", "permissions": {chat_id: ["read"]}},
                verify=False,
                timeout=30,
            )
            create_resp.raise_for_status()
            ams_id = create_resp.json()["id"]

            # Step 2: upload image binary
            upload_resp = requests.put(
                f"{self._AMS_BASE_URL}/{ams_id}/content/imgpsh",
                headers={**ams_headers, "Content-Type": content_type},
                data=image_data,
                verify=False,
                timeout=(10, 120),
            )
            upload_resp.raise_for_status()

            # Step 3: send message referencing the AMS object
            img_url = f"{self._AMS_BASE_URL}/{ams_id}/views/imgo"
            img_html = (
                f'<div itemscope itemtype="http://schema.skype.com/AMSImage">'
                f'<img src="{img_url}" itemid="{ams_id}" '
                f'itemtype="http://schema.skype.com/AMSImage">'
                f'</div>'
            )
            html_content = f"{caption}<br>{img_html}" if caption else img_html

            await self._maybe_throttle(chat_id)
            msg_url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            payload = {
                "content": html_content,
                "messagetype": "RichText/Html",
                "contenttype": "text",
                "amsreferences": [ams_id],
            }
            msg_resp = requests.post(
                msg_url,
                json=payload,
                headers={
                    "Authentication": f"skypetoken={skype_token}",
                    "Content-Type": "application/json",
                },
                verify=False,
                timeout=15,
            )
            msg_resp.raise_for_status()
            msg_id = msg_resp.json().get("id")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_image_file failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def send_image(self, chat_id: str, image_url_or_path: str, caption: str = "") -> "SendResult":
        """Send an image from an AMS URL (direct embed) or any other source.

        AMS URLs (api.asm.skype.com/v1/objects/...) are embedded directly
        with the AMSImage schema markup — no re-upload needed, the object
        already exists and this conversation may already have read access
        (or will be granted it via the message send). Any other URL is
        downloaded to a temp file and delegated to send_image_file() so it
        goes through the full AMS upload pipeline. A local filesystem path
        is treated the same way (delegated to send_image_file() directly).
        """
        from gateway.platforms.base import SendResult
        import re as _re, requests

        if _re.match(r"^https?://", image_url_or_path) and "asm.skype.com" in image_url_or_path:
            ams_id_match = _re.search(r"/objects/([^/]+)/", image_url_or_path)
            ams_id = ams_id_match.group(1) if ams_id_match else ""
            img_html = (
                f'<div itemscope itemtype="http://schema.skype.com/AMSImage">'
                f'<img src="{image_url_or_path}" itemid="{ams_id}" '
                f'itemtype="http://schema.skype.com/AMSImage">'
                f'</div>'
            )
            html_content = f"{caption}<br>{img_html}" if caption else img_html
            try:
                await self._maybe_throttle(chat_id)
                self._auth._inject_truststore()
                skype_token = self._auth.skype_token()
                msg_url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
                payload = {
                    "content": html_content,
                    "messagetype": "RichText/Html",
                    "contenttype": "text",
                }
                if ams_id:
                    payload["amsreferences"] = [ams_id]
                resp = requests.post(
                    msg_url,
                    json=payload,
                    headers={
                        "Authentication": f"skypetoken={skype_token}",
                        "Content-Type": "application/json",
                    },
                    verify=False,
                    timeout=15,
                )
                resp.raise_for_status()
                msg_id = resp.json().get("id")
                if msg_id:
                    self._last_sent_message_id = str(msg_id)
                return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
            except Exception as e:
                logger.warning("TeamsMTK: send_image (AMS direct embed) failed: %s", e)
                return SendResult(success=False, error=str(e))

        if _re.match(r"^https?://", image_url_or_path):
            # Remote (non-AMS) URL — download then delegate to send_image_file.
            import tempfile, os as _os
            try:
                dl_resp = requests.get(image_url_or_path, timeout=30, verify=False)
                dl_resp.raise_for_status()
                content_type = dl_resp.headers.get("Content-Type", "image/png")
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                       "image/webp": ".webp"}.get(content_type.split(";")[0].strip(), ".png")
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
                    for chunk in dl_resp.iter_content(65536):
                        tf.write(chunk)
                    tmp_path = tf.name
                try:
                    return await self.send_image_file(chat_id, tmp_path, caption=caption)
                finally:
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning("TeamsMTK: send_image (remote download) failed: %s", e)
                return SendResult(success=False, error=str(e))

        # Local filesystem path.
        return await self.send_image_file(chat_id, image_url_or_path, caption=caption)

    async def send_document(self, chat_id: str, path: str, caption: str = "") -> "SendResult":
        """Upload a local file to OneDrive and share a clickable link.

        Flow: Graph API PUT (simple upload for the file sizes Hermes deals
        with) -> Graph API POST createLink (organization-scoped view link)
        -> a plain HTML message with the filename + link. Falls back to a
        text notice via send() if the Graph upload fails (e.g. Graph scope
        not granted) rather than raising and losing the whole turn's reply.
        """
        from gateway.platforms.base import SendResult
        import os as _os, requests

        filename = _os.path.basename(path)
        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
        except OSError as e:
            return SendResult(success=False, error=f"Cannot read file: {e}")

        try:
            self._auth._inject_truststore()
            graph_token = self._auth.graph_token()
            headers = {
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/octet-stream",
            }
            # Simple upload — Graph's simple-PUT path caps at 4MB; larger
            # files would need the upload-session flow, but Hermes-generated
            # attachments (skill outputs, screenshots, docs) are well under
            # that in practice, so the session flow is left as a follow-up.
            import time as _time, uuid as _uuid
            unique_name = f"{int(_time.time())}_{_uuid.uuid4().hex[:8]}{_os.path.splitext(filename)[1]}"
            target_path = f"/Microsoft Teams Chat Files/TeamsMCP/{unique_name}"
            upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:{target_path}:/content"
            upload_resp = requests.put(
                upload_url, headers=headers, data=file_bytes, verify=False, timeout=(10, 120),
            )
            if upload_resp.status_code not in (200, 201):
                logger.warning(
                    "TeamsMTK: send_document upload failed (%s): %s",
                    upload_resp.status_code, upload_resp.text[:300],
                )
                fallback_text = f"{caption}\n\n[Could not upload {filename} — Graph API error]".strip()
                await self.send(chat_id=chat_id, content=fallback_text)
                return SendResult(success=False, error=f"Graph upload failed: {upload_resp.status_code}")
            upload_resp.raise_for_status()
            item = upload_resp.json()
            item_id = item["id"]
            web_url = item.get("webUrl", "")

            share_url = web_url
            try:
                share_resp = requests.post(
                    f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink",
                    headers={"Authorization": f"Bearer {graph_token}", "Content-Type": "application/json"},
                    json={"type": "view", "scope": "organization"},
                    verify=False,
                    timeout=30,
                )
                share_resp.raise_for_status()
                share_url = share_resp.json().get("link", {}).get("webUrl", "") or web_url
            except Exception:
                pass  # Non-fatal — fall back to the plain webUrl.

            html_content = (
                f'{caption}<br>' if caption else ""
            ) + f'📎 <a href="{share_url}">{item.get("name", filename)}</a>'

            await self._maybe_throttle(chat_id)
            skype_token = self._auth.skype_token()
            msg_url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            html_wrapped, _ = self._build_html(html_content, _skip_footer_extract=True)
            payload = {"content": html_wrapped, "messagetype": "RichText/Html", "contenttype": "text"}
            msg_resp = requests.post(
                msg_url,
                json=payload,
                headers={"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"},
                verify=False,
                timeout=15,
            )
            msg_resp.raise_for_status()
            msg_id = msg_resp.json().get("id")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_document failed: %s", e)
            try:
                await self.send(chat_id=chat_id, content=f"{caption}\n\n[Could not send document {filename}: {e}]".strip())
            except Exception:
                pass
            return SendResult(success=False, error=str(e))

    async def send_adaptive_card(
        self, chat_id: str, card: Dict[str, Any], fallback_text: str = "",
    ) -> "SendResult":
        """Send an Adaptive Card (static, read-only display) — G-MEDIA-4.

        Disabled by default (gateway.teams_mtk.adaptive_cards.enabled) because
        this polling architecture has no invoke-callback endpoint — any card
        with Action.Submit/Action.OpenUrl buttons would render but silently
        do nothing when clicked, which is worse than not sending a card at
        all. When enabled, the card must be purely informational.

        Encoding note: the top-level "attachments" array (the Bot
        Framework / Graph convention for adaptive cards) is silently dropped
        by the Skype consumer messaging endpoint — verified via a real
        POST+GET readback. ``properties.cards`` (a JSON-stringified list) is
        the encoding that actually persists and renders server-side.
        """
        from gateway.platforms.base import SendResult
        from hermes_cli.config import load_config_readonly
        import requests

        try:
            cfg = load_config_readonly()
        except Exception:
            cfg = {}
        enabled = bool(
            (cfg.get("gateway", {}) or {})
            .get("teams_mtk", {})
            .get("adaptive_cards", {})
            .get("enabled", False)
        )
        if not enabled:
            if fallback_text:
                return await self.send(chat_id=chat_id, content=fallback_text, metadata=None)
            return SendResult(success=False, error="Adaptive cards are disabled (gateway.teams_mtk.adaptive_cards.enabled=false) and no fallback_text was provided")

        try:
            await self._maybe_throttle(chat_id)
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            msg_url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            cards_json = json.dumps([{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }])
            payload = {
                "content": "",
                "messagetype": "RichText/Html",
                "contenttype": "text",
                "properties": {"cards": cards_json},
            }
            resp = requests.post(
                msg_url,
                json=payload,
                headers={"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"},
                verify=False,
                timeout=15,
            )
            resp.raise_for_status()
            msg_id = resp.json().get("id")
            if msg_id:
                self._last_sent_message_id = str(msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_adaptive_card failed (%s) — falling back to text", e)
            if fallback_text:
                return await self.send(chat_id=chat_id, content=fallback_text, metadata=None)
            return SendResult(success=False, error=str(e))

    # ---- G13-A: read-only contact / conversation lookup ----

    def list_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List conversations visible to this account via the Skype chat service.

        Read-only, no new OAuth scope needed (chatSvc GET /conversations is
        already covered by the Skype token this adapter uses for send/poll).
        Returns a flat list of {id, title, type, member_names} dicts so
        _find_conv_by_display_name() can do a simple substring match without
        each caller re-parsing the raw Skype response shape.
        """
        import requests
        try:
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations"
            session = requests.Session()
            resp = session.get(
                url,
                headers={"Authentication": f"skypetoken={skype_token}"},
                verify=False,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("TeamsMTK: list_conversations failed: %s", e)
            return []

        results: List[Dict[str, Any]] = []
        for conv in (data.get("conversations") or [])[:limit]:
            thread_props = conv.get("threadProperties") or {}
            title = thread_props.get("topic", "")
            conv_type = thread_props.get("threadType", "")
            members = conv.get("members") or []
            member_names = ", ".join(
                m.get("imdisplayname") or m.get("friendlyName") or ""
                for m in members
                if m.get("imdisplayname") or m.get("friendlyName")
            )
            results.append({
                "id": conv.get("id", ""),
                "title": title,
                "type": conv_type,
                "member_names": member_names,
            })
        return results

    def _find_conv_by_display_name(self, name: str) -> Optional[str]:
        """Case-insensitive substring match on conversation title or member names.

        Returns the conversation id of the first match, or None if *name*
        is blank or no existing conversation matches. Deliberately does NOT
        create a new chat — Hermes can only message people/groups it has
        already talked to (Chat.Create Graph scope is unavailable), which is
        the safety property G13 relies on: an unknown contact is simply
        unreachable via this path, no separate authorization gate needed.
        """
        name = (name or "").strip()
        if not name:
            return None
        needle = name.lower()
        for conv in self.list_conversations(limit=200):
            if needle in (conv.get("title") or "").lower():
                return conv.get("id")
            if needle in (conv.get("member_names") or "").lower():
                return conv.get("id")
        return None

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

        When the SDK is available, delegates to ``MessagesService.get_page()``
        which handles auth retry, HTML normalisation via ``strip_teams_html``,
        attachment extraction, and sender resolution automatically — and uses
        the gateway's **regional** ``msg_base`` (discovered from Skype authz).

        Falls back to raw ``requests`` when the SDK is not importable.
        """
        if conv_id is None:
            conv_id = self._conv_id

        self._auth._inject_truststore()
        import time as _t
        _t0 = _t.time()

        try:
            if _SDK_AVAILABLE:
                return self._fetch_via_sdk(conv_id, limit, _t0)

            # --- Fallback: raw requests (SDK not importable) ---
            return self._fetch_via_raw(conv_id, limit, _t0)
        finally:
            logger.info("TeamsMTK: _fetch_messages done in %.1fs", _t.time() - _t0)

    def _fetch_via_sdk(self, conv_id: str, limit: int, _t0: float) -> List[dict]:
        """Fetch messages using SDK MessagesService (normalised, with attachments)."""
        adapter = _SDKAuthAdapter(self._auth)
        http_layer = _SDKHTTPLayer(adapter, verify_ssl=False)
        svc = _SDKMessages(http_layer)
        try:
            norm_msgs = svc.get_page(conv_id, page_size=limit,
                                     msg_base=self._auth.msg_base)
            # Back-fill raw-compatible fields so _process_new_messages works
            # unchanged across both SDK-normalised and raw-fetch messages.
            for m in norm_msgs:
                m.setdefault("imdisplayname", m.get("sender", ""))
                m.setdefault("messagetype", m.get("type", "RichText/Html"))
                m.setdefault("properties", m.get("_raw_properties") or {})
                # Convert SDK attachments to raw-API-compatible format so
                # _process_new_messages layer-4 (top-level array) picks them up.
                sdk_atts = m.get("attachments")
                if isinstance(sdk_atts, list) and sdk_atts:
                    raw_atts = []
                    for a in sdk_atts:
                        if isinstance(a, dict):
                            raw_atts.append({
                                "contentUrl": a.get("url", ""),
                                "name": a.get("name", ""),
                                "contentType": (
                                    "image/" + a.get("kind", "image")
                                    if a.get("kind") == "image"
                                    else "application/octet-stream"
                                ),
                            })
                    if raw_atts:
                        m["attachments"] = raw_atts
            # SDK returns newest-first; gateway expects oldest-first
            norm_msgs.reverse()
            return norm_msgs
        except Exception as e:
            logger.warning("TeamsMTK: SDK fetch failed (%s), falling back to raw", e)
            return self._fetch_via_raw(conv_id, limit, _t0)

    def _fetch_via_raw(self, conv_id: str, limit: int, _t0: float) -> List[dict]:
        """Fetch messages using raw requests (legacy, SDK unavailable)."""
        import urllib.parse, requests
        from requests.adapters import HTTPAdapter

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
            logger.warning("TeamsMTK: _fetch_messages ConnectionError after %.1fs", _t.time() - _t0)
            raise
        finally:
            session.close()

        data = resp.json()
        messages = data.get("messages") or []
        # Preserve raw fields for echo guard (matches SDK _normalize_raw)
        for _m in messages:
            _m["_raw_content"] = _m.get("content", "")
            _m["_raw_properties"] = _m.get("properties")
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
                # Fetch all conversations in parallel so N convs take ~1
                # round-trip instead of N×round-trip.
                fetch_tasks = {
                    _conv_id: loop.run_in_executor(
                        executor, lambda _c=_conv_id: self._fetch_messages(_c, 20)
                    )
                    for _conv_id in self._conv_ids
                }
                fetch_results = await asyncio.gather(*fetch_tasks.values())
                for _conv_id, msgs in zip(fetch_tasks, fetch_results):
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

        When the SDK is available, delegates to ``download_with_auth_url()``
        which picks the correct auth strategy per domain (skype_token for
        Skype/Teams, Bearer for SharePoint/OneDrive).  Runs in a thread
        pool via ``asyncio.to_thread`` to avoid blocking the event loop.

        Falls back to ``aiohttp`` with a single ``Bearer skype_token`` header
        when the SDK is not importable — the legacy behaviour.
        """
        from gateway.platforms.base import cache_image_from_bytes, cache_document_from_bytes

        # --- SDK path: domain-appropriate auth, thread-pooled ---
        if _sdk_download is not None:
            try:
                _sk = self._auth.skype_token()
                _at = self._auth.access_token()
                data = await asyncio.to_thread(
                    _sdk_download, url, _sk, _at, False, 30,
                )
            except Exception as exc:
                logger.warning("TeamsMTK: SDK download failed (%s), falling back to aiohttp url=%.60s", exc, url)
                # Fall through to aiohttp below
                data = None
            if data is not None:
                try:
                    if kind == "image":
                        _ext = ".jpg"
                        if ".png" in url.lower():
                            _ext = ".png"
                        elif ".gif" in url.lower():
                            _ext = ".gif"
                        elif ".webp" in url.lower():
                            _ext = ".webp"
                        return cache_image_from_bytes(data, _ext)
                    else:
                        if not filename:
                            _parts = url.rsplit("/", 1)
                            filename = _parts[-1].split("?", 1)[0] if len(_parts) > 1 else "document.bin"
                        return cache_document_from_bytes(data, filename)
                except Exception as exc:
                    logger.warning("TeamsMTK: attachment cache error: %s", exc)
                    return None

        # --- Fallback: aiohttp with single Bearer header (legacy) ---
        import aiohttp
        headers = {"Authorization": f"Bearer {self._auth.skype_token()}"}
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
                _ext = ".jpg"
                if ".png" in url.lower():
                    _ext = ".png"
                elif ".gif" in url.lower():
                    _ext = ".gif"
                elif ".webp" in url.lower():
                    _ext = ".webp"
                return cache_image_from_bytes(data, _ext)
            else:
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
            #   1. properties.hermes_sender in ("agent", "bot")  (tag on send)
            #      Gateway sends "agent"; SDK-normalized messages carry "bot"
            #   2. clientmessageid matches our sent id  (id-match fallback)
            #   3. composetime is within 2s and content matches last sent
            #      (catches cases where Teams API strips properties)
            is_own = False
            # Check hermes_sender from both msg.properties and _raw_properties
            props = msg.get("properties", {}) or {}
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            _raw_props = msg.get("_raw_properties") or {}
            if isinstance(_raw_props, str):
                try:
                    _raw_props = json.loads(_raw_props)
                except (json.JSONDecodeError, TypeError):
                    _raw_props = {}
            _sender_val = props.get("hermes_sender") or _raw_props.get("hermes_sender")
            if _sender_val in ("agent", "bot"):
                is_own = True
            if self._last_sent_message_id and str(msg_id) == str(self._last_sent_message_id):
                is_own = True
            if self._sent_dedup.is_duplicate(str(msg_id)):
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

            # HTML stripping: use SDK strip_teams_html when available
            # (handles <at>, <blockquote>, <img> emoji, <file>, <a> truncated URLs)
            # Falls back to regex for environments where SDK is not on sys.path.
            if _strip_teams_html is not None:
                text, _extra_imgs = _strip_teams_html(content)
            else:
                import re
                content = re.sub(r"<at\s[^>]*>([^<]*)</at>", r"\1", content)
                text = re.sub(r"<[^>]+>", "", content).strip()
                text = re.sub(r"\s+", " ", text).strip()
                _extra_imgs = []
            # Merge any additional inline images from SDK extraction
            if _extra_imgs:
                for _ei in _extra_imgs:
                    _eurl = _ei.get("src", "")
                    if _eurl and _eurl not in _att_urls:
                        _att_urls.append(_eurl)
                        _att_names.append(_ei.get("alt", ""))
                        _att_kinds.append(_ei.get("kind", "image"))
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


# ---------------------------------------------------------------------------
# Out-of-process standalone sender + platform_registry registration
# ---------------------------------------------------------------------------
#
# teams_mtk historically lived entirely outside gateway.platform_registry —
# the adapter was only ever constructed via the hardcoded if/elif chain in
# gateway/run.py's _create_adapter(). That works fine while the gateway
# process itself is alive and holding a live adapter instance, but it means
# tools/send_message_tool._send_via_adapter() has no fallback path when the
# caller (cron, running in-process alongside the gateway but hitting the
# runner weakref before it's bound, or a genuinely separate process) can't
# get a live adapter reference: "No live adapter for platform 'teams_mtk'...
# the platform plugin must register a standalone_sender_fn on its
# PlatformEntry." Registering here (even though teams_mtk is a built-in, not
# a plugin) gives every out-of-process caller — cron deliver=teams_mtk being
# the concrete case that surfaced this — the same fallback plugin platforms
# already have.

async def _standalone_send(
    pconfig,
    chat_id,
    message,
    *,
    thread_id=None,
    media_files=None,
    force_document=False,
):
    """Out-of-process TeamsMTK delivery — builds a transient adapter and sends.

    Implements the standalone_sender_fn contract (see
    gateway/platform_registry.py::PlatformEntry.standalone_sender_fn) so
    ``deliver=teams_mtk`` cron jobs succeed even when the caller can't reach
    the gateway's live adapter instance. Auth is self-contained (the
    ~/.teams-tokens/token_cache.json cache _TeamsAuth reads from), so no
    pconfig fields are required beyond what TeamsMTKAdapter.__init__ already
    reads from the MTK_TEAMS_CONVERSATION_ID env var.

    MEDIA: tags are handled by the caller (BasePlatformAdapter.extract_media
    splits them out of *message* before this is invoked) — media_files here
    are delivered natively via send_image_file/send_document based on file
    extension, mirroring the live adapter's in-band capability.
    """
    media_files = media_files or []
    try:
        adapter = TeamsMTKAdapter(pconfig)
    except Exception as e:
        return {"error": f"TeamsMTK standalone send: failed to construct adapter: {e}"}

    try:
        last_result = None
        if message and message.strip():
            last_result = await adapter.send(chat_id, message)
            if not last_result.success:
                return {"error": f"TeamsMTK send failed: {last_result.error}"}

        _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        for media_path, _is_voice in media_files:
            if not os.path.exists(media_path):
                return {"error": f"Media file not found: {media_path}"}
            ext = os.path.splitext(media_path)[1].lower()
            if ext in _IMAGE_EXTS:
                last_result = await adapter.send_image_file(chat_id, media_path)
            else:
                last_result = await adapter.send_document(chat_id, media_path)
            if not last_result.success:
                return {"error": f"TeamsMTK media send failed: {last_result.error}"}

        if last_result is None:
            return {"error": "No deliverable text or media remained after processing MEDIA tags"}
        return {
            "success": True,
            "platform": "teams_mtk",
            "chat_id": chat_id,
            "message_id": last_result.message_id,
        }
    except Exception as e:
        return {"error": f"TeamsMTK standalone send failed: {e}"}


def _is_connected(config) -> bool:
    """TeamsMTK is connected when MTK_TEAMS_CONVERSATION_ID is set and the
    skypetoken cache exists — mirrors check_teams_mtk_requirements()."""
    return check_teams_mtk_requirements()


def _register_teams_mtk_platform() -> None:
    """Register teams_mtk with platform_registry so out-of-process callers
    (cron, standalone send_message) get the standalone_sender_fn fallback.

    This does NOT change how the live gateway constructs its adapter —
    gateway/run.py's _create_adapter() checks platform_registry first (see
    GatewayRunner._create_adapter), so this registration becomes the live
    construction path too, but with the identical factory (TeamsMTKAdapter)
    and identical check_fn (check_teams_mtk_requirements) it previously used
    in the hardcoded if/elif branch. No behavior change for the live path;
    the new capability is purely the standalone_sender_fn fallback.
    """
    from gateway.platform_registry import platform_registry, PlatformEntry

    platform_registry.register(PlatformEntry(
        name="teams_mtk",
        label="Microsoft Teams (MTK)",
        adapter_factory=lambda cfg: TeamsMTKAdapter(cfg),
        check_fn=check_teams_mtk_requirements,
        is_connected=_is_connected,
        source="builtin",
        standalone_sender_fn=_standalone_send,
        emoji="👥",
    ))


_register_teams_mtk_platform()
