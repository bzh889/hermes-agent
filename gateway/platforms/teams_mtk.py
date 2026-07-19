"""Microsoft Teams gateway adapter for MTK internal environment.

Uses the configured Teams authentication provider's token cache
(~/.teams-tokens/token_cache.json)
for authentication — no separate bot token needed. Polls a configured
conversation for new messages.

Configure ``platforms.teams_mtk`` in config.yaml with ``conversation_ids``,
``poll_interval_seconds``, and ``require_mention``. Legacy environment
variables remain supported for backward compatibility.

Setup:
    1. Authenticate with the configured Teams authentication helper
    2. hermes setup gateway  → select "Microsoft Teams (MTK)"
    3. Enter your conversation ID
    4. hermes gateway
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import ssl
import stat
import time
import threading
import uuid
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

# SDK MessagesService for normalized message fetching
try:
    from teams_skype_sdk.api._http import HTTPLayer as _SDKBaseHTTPLayer
    from teams_skype_sdk.api._messages import MessagesService as _SDKMessages
    from teams_skype_sdk.api._files import FilesService as _SDKFiles
    from teams_skype_sdk.api._conversations import ConversationsService as _SDKConvs
    from teams_skype_sdk.api._reactions import ReactionsService as _SDKReactions
    from teams_skype_sdk.api._constants import (
        REACTION_EMOJI_MAP as _REACTION_EMOJI,
        VALID_REACTIONS as _VALID_REACTIONS,
    )
    from teams_skype_sdk.api._activity import ActivityService as _SDKActivity
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    _SDKBaseHTTPLayer = None
    _SDKMessages = None
    _SDKFiles = None
    _SDKConvs = None
    _SDKReactions = None
    _SDKActivity = None
    _VALID_REACTIONS = {"like", "heart", "laugh", "surprised", "sad", "angry"}
    _REACTION_EMOJI = {
        "like": "👍",
        "heart": "❤️",
        "laugh": "😄",
        "surprised": "😮",
        "sad": "😢",
        "angry": "😡",
    }

logger = logging.getLogger(__name__)

# OAuth tenant and client IDs are derived from the authenticated user's cached
# JWT so organization-specific identifiers are never embedded in source.
_SKYPE_TOKEN_URL = "https://authsvc.teams.microsoft.com/v1.0/authz"
# Default MSG endpoint; overridden at runtime by region from Skype token exchange.
_DEFAULT_MSG_BASE = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"

_ATTACHMENT_REDIRECT_LIMIT = 5
_ATTACHMENT_SKYPE_AUTH_HOSTS = ("asm.skype.com",)
_ATTACHMENT_SKYPETOKEN_HOSTS = ("teams.microsoft.com", "skype.com")
_ATTACHMENT_BEARER_HOSTS = (
    "sharepoint.com",
    "sharepoint-df.com",
    "onedrive.com",
    "onedrive.live.com",
    "1drv.ms",
)


def _host_matches_suffix(hostname: str, suffix: str) -> bool:
    """Match a hostname exactly or at a DNS label boundary."""
    return hostname == suffix or hostname.endswith(f".{suffix}")


def _attachment_auth_kind(hostname: str) -> Optional[str]:
    """Return the credential type permitted for an attachment hostname."""
    host = hostname.lower().rstrip(".")
    if any(_host_matches_suffix(host, suffix) for suffix in _ATTACHMENT_SKYPE_AUTH_HOSTS):
        return "skype_authorization"
    if any(_host_matches_suffix(host, suffix) for suffix in _ATTACHMENT_SKYPETOKEN_HOSTS):
        return "skype_authentication"
    if any(_host_matches_suffix(host, suffix) for suffix in _ATTACHMENT_BEARER_HOSTS):
        return "azure_bearer"
    return None


def _message_id_key(value: Any) -> tuple:
    """Sort Teams OriginalArrivalTime IDs numerically, with a text fallback."""
    text = str(value or "")
    if text.isdigit():
        return 1, int(text)
    return 0, text


def _log_ref(value: Any) -> str:
    """Return a non-reversible identifier suitable for log correlation."""
    if value in (None, ""):
        return "<none>"
    digest = hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest[:12]}"


def _log_error(exc: BaseException) -> str:
    """Return exception metadata without leaking URLs or response bodies."""
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status", None) or getattr(response, "status_code", None)
    suffix = f" status={status}" if isinstance(status, int) else ""
    return f"{type(exc).__name__}{suffix}"


def _redact_oid(oid: Optional[str], visible: int = 8) -> str:
    """Return a non-reversible AAD Object ID reference for logging."""
    del visible  # Retained for compatibility with older callers.
    return _log_ref(oid)


def _clean_message_content(content: str) -> tuple[str, List[dict]]:
    """Normalize Teams HTML and preserve only useful forwarded context."""
    if _strip_teams_html is not None:
        return _strip_teams_html(content)

    normalized = content or ""
    normalized = re.sub(
        r"<at\s[^>]*>([^<]*)</at>",
        lambda match: match.group(1) if match.group(1).startswith("@") else f"@{match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    blockquotes = re.findall(
        r"<blockquote[^>]*>.*?</blockquote>",
        normalized,
        flags=re.DOTALL | re.IGNORECASE,
    )
    without_quotes = re.sub(
        r"<blockquote[^>]*>.*?</blockquote>",
        "",
        normalized,
        flags=re.DOTALL | re.IGNORECASE,
    )
    user_text = re.sub(r"<[^>]+>", "", without_quotes)
    user_text = re.sub(r"\s+", " ", user_text).strip()
    if blockquotes and user_text:
        quote_text = re.sub(r"<[^>]+>", "", blockquotes[0])
        quote_text = re.sub(r"\s+", " ", quote_text).strip()[:80]
        if quote_text:
            user_text = f"{user_text}\n[forwarded message: {quote_text}…]"
    return user_text, []


def check_teams_mtk_requirements() -> bool:
    """Return True when the external Teams authentication cache exists."""
    token_cache = Path.home() / ".teams-tokens" / "token_cache.json"
    return token_cache.exists()


def _normalize_conversation_ids(value: Any) -> List[str]:
    """Normalize a scalar or sequence of conversation IDs."""
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        candidates = []
    return [str(item).strip() for item in candidates if str(item).strip()]


def _configured_conversation_ids(config: Any = None) -> List[str]:
    """Resolve config.yaml IDs first, then the legacy environment variable."""
    extra = getattr(config, "extra", None)
    if isinstance(extra, dict):
        configured = extra.get("conversation_ids") or extra.get("conversation_id")
        normalized = _normalize_conversation_ids(configured)
        if normalized:
            return normalized
    return _normalize_conversation_ids(os.getenv("MTK_TEAMS_CONVERSATION_ID", ""))


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

    @staticmethod
    def _jwt_claim(token: str, claim: str) -> str:
        """Read one claim from a cached JWT without logging token content."""
        try:
            import base64

            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            value = decoded.get(claim, "")
            return value if isinstance(value, str) else ""
        except (IndexError, ValueError, TypeError, json.JSONDecodeError):
            return ""

    @classmethod
    def _oauth_uuid_claim(
        cls,
        tokens: dict,
        claims: tuple[str, ...],
        label: str,
    ) -> str:
        value = ""
        for key in ("access_token", "graph_token"):
            for claim in claims:
                value = cls._jwt_claim(tokens.get(key, ""), claim)
                if value:
                    break
            if value:
                break
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError(
                f"Teams token cache does not contain a valid {label} claim; "
                "re-authenticate with the Teams authentication helper"
            ) from None

    @classmethod
    def _oauth_token_url(cls, tokens: dict) -> str:
        """Build the tenant-scoped OAuth URL from an existing cached JWT."""
        tenant_id = cls._oauth_uuid_claim(tokens, ("tid",), "tenant")
        return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    @classmethod
    def _oauth_client_id(cls, tokens: dict) -> str:
        """Return the OAuth client ID recorded in an existing cached JWT."""
        return cls._oauth_uuid_claim(
            tokens,
            ("appid", "azp"),
            "client application",
        )

    def client_id(self) -> str:
        """Return the cached OAuth client ID without exposing token content."""
        return self._oauth_client_id(self._load())

    def _get_my_oid(self) -> str:
        """Extract current user OID from the access token JWT (matches teams skill)."""
        if self._my_oid:
            return self._my_oid
        try:
            tok = self._load()
            self._my_oid = self._jwt_claim(tok.get("access_token", ""), "oid")
        except Exception:
            self._my_oid = ""
        return self._my_oid or ""

    def __init__(self):
        self._lock = threading.Lock()
        self._truststore_injected = False
        self._msg_base: Optional[str] = None  # set from Skype authz region
        self._msg_base_discovery_attempted = False
        # Compatibility/injection seam used by SDK-backed call paths.  Normal
        # production auth leaves this unset and reads the secure token cache;
        # embedders that already supplied an in-memory Skype token must not be
        # forced through an unrelated OAuth refresh first.
        self._skype_token: Optional[str] = None

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
                "Authenticate first with the Teams authentication helper"
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
                    self.TOKEN_CACHE.name,
                )
                try:
                    self.TOKEN_CACHE.unlink(missing_ok=True)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Teams token cache was corrupted and has been deleted: "
                    f"{self.TOKEN_CACHE}. Re-authenticate with the Teams authentication helper"
                )

    def _save(self, tokens: dict) -> None:
        """Atomic, owner-only write of the token cache.

        The cache holds long-lived OAuth access + refresh tokens, so it must
        never be group/world-readable. We create the temp file atomically at
        0o600 via ``O_CREAT | O_EXCL`` (no TOCTOU window where it briefly
        inherits the process umask, commonly 0o644), fsync, then ``replace()``
        onto the destination — which carries the temp's 0o600 mode with it. A
        per-pid + random temp name avoids collisions between concurrent writers
        and stale leftovers from a crashed write. On Windows the mode bits are
        advisory (ACLs govern access), but O_EXCL + replace still gives an
        atomic, corruption-safe write.
        """
        import secrets as _secrets

        self.TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.TOKEN_CACHE.with_suffix(f".json.tmp.{os.getpid()}.{_secrets.token_hex(4)}")
        try:
            fd = os.open(
                str(tmp),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                stat.S_IRUSR | stat.S_IWUSR,  # 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
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

    @staticmethod
    def _normalize_msg_base(value: Any) -> Optional[str]:
        """Validate and canonicalize a Teams regional MSG endpoint.

        This value is persisted beside bearer credentials. Treat the cache as
        untrusted input so a modified file cannot redirect Skype credentials to
        an arbitrary host.
        """
        if not isinstance(value, str) or not value.strip():
            return None
        from urllib.parse import urlparse

        try:
            parsed = urlparse(value.strip())
            host = (parsed.hostname or "").lower().rstrip(".")
            if (
                parsed.scheme.lower() != "https"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or not host.endswith(".ng.msg.teams.microsoft.com")
                or parsed.path.rstrip("/") not in ("", "/v1/users/ME")
                or parsed.query
                or parsed.fragment
            ):
                return None
        except (TypeError, ValueError):
            return None
        return f"https://{host}/v1/users/ME"

    def _apply_skype_authz(self, tokens: dict, body: dict) -> bool:
        """Apply Skype authz token + regional endpoint to *tokens*.

        Returns whether the persisted token dictionary changed.
        """
        before = (tokens.get("skype_token"), tokens.get("msg_base"))
        skype_token = (
            body.get("tokens", {}).get("skypeToken")
            or body.get("skypeToken")
            or tokens.get("skype_token", "")
        )
        if skype_token:
            tokens["skype_token"] = skype_token

        chat_service = (body.get("regionGtms") or {}).get("chatService", "")
        regional_base = self._normalize_msg_base(chat_service)
        if regional_base:
            self._msg_base = regional_base
            tokens["msg_base"] = regional_base
            logger.info("TeamsMTK: regional chat endpoint discovered")
        elif chat_service:
            logger.warning("TeamsMTK: ignored invalid regional chat endpoint")

        return before != (tokens.get("skype_token"), tokens.get("msg_base"))

    def _discover_msg_base(self, tokens: dict) -> None:
        """Migrate a valid legacy cache by querying Skype authz once."""
        import requests

        access_token = tokens.get("access_token", "")
        if not access_token:
            return
        response = requests.post(
            _SKYPE_TOKEN_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={},
            verify=True,
            timeout=30,
        )
        response.raise_for_status()
        if self._apply_skype_authz(tokens, response.json()):
            self._save(tokens)

    def _refresh(self, tokens: dict) -> dict:
        import requests
        self._inject_truststore()
        refresh_token = tokens.get("refresh_token", "")
        if not refresh_token:
            raise RuntimeError(
                "No refresh_token in cache — re-authenticate with the "
                "Teams authentication helper"
            )

        resp = requests.post(
            self._oauth_token_url(tokens),
            data={
                "client_id": self._oauth_client_id(tokens),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": self._SKYPE_SCOPE,
            },
            verify=True,
            timeout=30,
        )
        resp.raise_for_status()
        new_tok = resp.json()

        # Exchange for Skype token — also discovers the regional chat service URL
        sk_resp = requests.post(
            _SKYPE_TOKEN_URL,
            headers={"Authorization": f"Bearer {new_tok['access_token']}"},
            json={},
            verify=True,
            timeout=30,
        )
        sk_resp.raise_for_status()
        sk_body = sk_resp.json()

        self._msg_base_discovery_attempted = True
        self._apply_skype_authz(tokens, sk_body)
        skype_token = tokens.get("skype_token", "")

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
            cached_base = self._normalize_msg_base(tok.get("msg_base"))
            if cached_base:
                self._msg_base = cached_base
            elif tok.get("msg_base"):
                logger.warning("TeamsMTK: ignored invalid cached regional endpoint")
            if self._expired(tok):
                logger.info("TeamsMTK: refreshing tokens...")
                tok = self._refresh(tok)
            elif self._msg_base is None and not self._msg_base_discovery_attempted:
                self._msg_base_discovery_attempted = True
                try:
                    self._discover_msg_base(tok)
                except Exception as exc:
                    # Preserve the established Amer fallback when authz is
                    # temporarily unavailable; do not hammer it on every poll.
                    logger.warning(
                        "TeamsMTK: regional endpoint discovery failed: %s",
                        _log_error(exc),
                    )
            return tok

    def skype_token(self) -> str:
        if self._skype_token:
            return self._skype_token
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
                    "No refresh_token in cache — re-authenticate with the "
                    "Teams authentication helper"
                )
            resp = requests.post(
                self._oauth_token_url(tok),
                data={
                    "client_id": self._oauth_client_id(tok),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": self._GRAPH_SCOPE,
                },
                verify=True,
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

    def exchange_for_scope(self, scope: str) -> dict:
        """Exchange the shared refresh token for an arbitrary OAuth scope.

        Trouter uses an IC3-scoped access token rather than the Graph or
        Skype access tokens. Persist refresh-token rotation so a scope
        exchange cannot invalidate subsequent gateway refreshes.
        """
        import requests

        with self._lock:
            tok = self._load()
            refresh_token = tok.get("refresh_token", "")
            if not refresh_token:
                raise RuntimeError(
                    "No refresh_token in cache — re-authenticate with the "
                    "Teams authentication helper"
                )

            self._inject_truststore()
            response = requests.post(
                self._oauth_token_url(tok),
                data={
                    "client_id": self._oauth_client_id(tok),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": scope,
                },
                verify=True,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            new_refresh = result.get("refresh_token")
            if new_refresh and new_refresh != refresh_token:
                tok["refresh_token"] = new_refresh
                self._save(tok)

            return result

    def _graph_request(self, method: str, url: str, **kwargs):
        """Issue an authenticated Microsoft Graph request."""
        import requests

        self._inject_truststore()
        headers = {
            "Authorization": f"Bearer {self.graph_token()}",
            "Content-Type": "application/json",
        }
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(
            method,
            url,
            headers=headers,
            verify=True,
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        return response

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


if _SDK_AVAILABLE:
    class _SDKHTTPLayer(_SDKBaseHTTPLayer):
        """SDK transport with gateway-discovered regional MSG routing.

        The SDK currently builds message URLs from its Amer constant. Rewrite
        only that exact trusted prefix at the transport boundary; payload,
        retry, TLS, and authentication behavior remain SDK-owned.
        """

        def _request(self, method: str, url: str, **kwargs):
            if url == _DEFAULT_MSG_BASE or url.startswith(_DEFAULT_MSG_BASE + "/"):
                # Hydrates/migrates msg_base before selecting the endpoint.
                self.auth.get_skype_token()
                regional_base = self.auth._gw.msg_base
                url = regional_base + url[len(_DEFAULT_MSG_BASE):]
            return super()._request(method, url, **kwargs)
else:
    _SDKHTTPLayer = None


class _SDKGraphAdapter:
    """Minimal Graph API adapter for SDK FilesService.send_file().

    Provides the duck-typed interface that send_file() expects:
    upload_to_onedrive, create_sharing_link, get_sharepoint_ids,
    delete_onedrive_item.  Delegates to raw Graph HTTP using the
    gateway's graph_token().
    """
    def __init__(self, gw_auth: _TeamsAuth, verify_ssl: bool = True):
        self._gw = gw_auth
        self.verify_ssl = verify_ssl

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._gw.graph_token()}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs):
        """Expose the Graph transport contract used by SDK services."""
        return self._gw._graph_request(method, url, **kwargs)

    def upload_to_onedrive(self, file_bytes: bytes, original_filename: str) -> dict:
        import requests as _req, time as _time, uuid as _uuid, os as _os
        ext = _os.path.splitext(original_filename)[1]
        unique_name = f"{int(_time.time())}_{_uuid.uuid4().hex[:8]}{ext}"
        target_path = f"/Microsoft Teams Chat Files/TeamsMCP/{unique_name}"
        upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:{target_path}:/content"
        read_timeout = max(120, len(file_bytes) / (100 * 1024))
        headers = self._headers()
        headers["Content-Type"] = "application/octet-stream"
        self._gw._inject_truststore()

        if len(file_bytes) <= 4 * 1024 * 1024:
            resp = _req.put(upload_url, headers=headers, data=file_bytes,
                           verify=self.verify_ssl, timeout=(10, read_timeout))
        else:
            sess_url = f"https://graph.microsoft.com/v1.0/me/drive/root:{target_path}:/createUploadSession"
            sess_resp = _req.post(sess_url, headers=self._headers(), json={},
                                  verify=self.verify_ssl, timeout=30)
            sess_resp.raise_for_status()
            upload_url = sess_resp.json()["uploadUrl"]
            sz = len(file_bytes)
            resp = _req.put(upload_url, headers={
                "Content-Length": str(sz),
                "Content-Range": f"bytes 0-{sz - 1}/{sz}",
            }, data=file_bytes, verify=self.verify_ssl, timeout=(10, read_timeout))

        resp.raise_for_status()
        item = resp.json()
        return {
            "id": item["id"],
            "fileName": item.get("name", original_filename),
            "webUrl": item.get("webUrl", ""),
            "downloadUrl": item.get("@microsoft.graph.downloadUrl", ""),
            "size": item.get("size", len(file_bytes)),
        }

    def create_sharing_link(self, item_id: str) -> str:
        import requests as _req
        self._gw._inject_truststore()
        resp = _req.post(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink",
            headers=self._headers(),
            json={"type": "view", "scope": "organization"},
            verify=self.verify_ssl, timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("link", {}).get("webUrl", "")

    def get_sharepoint_ids(self, item_id: str) -> dict:
        import requests as _req
        self._gw._inject_truststore()
        resp = _req.get(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}?$select=sharepointIds",
            headers=self._headers(),
            verify=self.verify_ssl, timeout=15,
        )
        resp.raise_for_status()
        sp = resp.json().get("sharepointIds", {})
        return {
            "listItemUniqueId": sp.get("listItemUniqueId", ""),
            "siteId": sp.get("siteId", ""),
            "siteUrl": sp.get("siteUrl", ""),
        }

    def delete_onedrive_item(self, item_id: str) -> bool:
        import requests as _req
        self._gw._inject_truststore()
        resp = _req.delete(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}",
            headers=self._headers(),
            verify=self.verify_ssl, timeout=15,
        )
        return resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Trouter WebSocket Listener (§9 — WS + Poll dual channel)
# ---------------------------------------------------------------------------

_TROUTER_URL = "https://go.trouter.teams.microsoft.com:443/v4/a"
_WS_MAX_RECONNECT = 5
_WS_BACKOFF_BASE = 1  # seconds; exponential: 1, 2, 4, 8, 16
_WS_HEARTBEAT_TIMEOUT = 30  # seconds without a 2:: ping → consider dead


class _TrouterListener:
    """Async Trouter WebSocket listener (§9 dual-channel: WS + poll).

    Lifecycle:
        1. ``_register()``  — POST to Trouter, get socketio endpoint + params
        2. ``_handshake()``  — GET socket.io/1/ to get session_id
        3. ``_connect()``    — open WSS to Trouter, start receiving
        4. ``_listen()``     — loop reading frames, dispatch events
        5. On close/error   — auto-reconnect up to _WS_MAX_RECONNECT times
        6. ``stop()``       — clean shutdown

    Events are dispatched to ``on_event(event_dict)`` which the gateway
    implements to trigger immediate ``_fetch_messages`` + ``_process_new_messages``.
    """

    def __init__(self, gw_auth: _TeamsAuth, on_event, loop: asyncio.AbstractEventLoop):
        self._auth = gw_auth
        self._on_event = on_event    # async callback(event_dict)
        self._loop = loop
        self._running = False
        self._ws = None              # websockets.WebSocketClientProtocol
        self._task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        self._connected = False
        self._last_heartbeat = 0.0
        # Event type log for REV-5 observation
        self._event_types: List[str] = []

    # ---- Public API ----

    def start(self) -> asyncio.Task:
        """Start the listener as an asyncio Task."""
        self._running = True
        self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        """Signal shutdown and wait for the task to finish."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def event_types_log(self) -> List[str]:
        """REV-5: observed Trouter event names."""
        return list(self._event_types[-50:])

    # ---- Internal ----

    async def _run(self) -> None:
        """Main loop: connect, listen, reconnect on failure."""
        import websockets
        ssl_ctx = ssl.create_default_context()

        while self._running:
            try:
                ic3_token = await asyncio.to_thread(
                    self._auth.exchange_for_scope,
                    "https://ic3.teams.office.com/Teams.AccessAsUser.All",
                )
                ic3_token = ic3_token["access_token"]
                skype_token = self._auth.skype_token()

                trouter_info = await asyncio.to_thread(self._register, ic3_token)
                session_id, params = await asyncio.to_thread(
                    self._handshake, trouter_info, ic3_token, skype_token,
                )
                ws_url = self._build_ws_url(trouter_info, session_id, params)

                async with websockets.connect(
                    ws_url,
                    additional_headers={
                        "Authorization": f"Bearer {ic3_token}",
                        "Authentication": f"skypetoken={skype_token}",
                    },
                    ssl=ssl_ctx,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    self._reconnect_count = 0
                    self._last_heartbeat = time.monotonic()
                    logger.info("TeamsMTK/WS: connected to Trouter")

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_frame(raw)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("TeamsMTK/WS: error (%s), reconnect=%d/%d", _log_error(e), self._reconnect_count, _WS_MAX_RECONNECT)

            self._connected = False
            self._ws = None

            if not self._running:
                break

            self._reconnect_count += 1
            if self._reconnect_count > _WS_MAX_RECONNECT:
                logger.error("TeamsMTK/WS: max reconnect attempts reached — giving up (poll loop will keep working)")
                break

            delay = _WS_BACKOFF_BASE * (2 ** (self._reconnect_count - 1))
            logger.info("TeamsMTK/WS: reconnecting in %ds...", delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

    async def _handle_frame(self, raw: str) -> None:
        """Dispatch a Socket.IO frame."""
        # Heartbeat: respond to server ping
        if raw == "2::":
            if self._ws:
                await self._ws.send("2::")
            self._last_heartbeat = time.monotonic()
            return
        if raw == "1::":
            self._last_heartbeat = time.monotonic()
            return
        # WS-3: heartbeat timeout check
        if time.monotonic() - self._last_heartbeat > _WS_HEARTBEAT_TIMEOUT:
            logger.warning("TeamsMTK/WS: heartbeat timeout — closing connection")
            if self._ws:
                await self._ws.close()
            return

        # Event frame: "5:<N>::<json>"
        if raw.startswith("5:"):
            try:
                evt = self._parse_event(raw)
                if evt:
                    event_name = evt.get("_trouter_name", "unknown")
                    self._event_types.append(event_name)
                    if event_name == "trouter.message":
                        await self._on_event(evt)
                    elif event_name == "trouter.connected":
                        logger.info("TeamsMTK/WS: trouter.connected (ttl=%s)", evt.get("ttl", "?"))
                    elif event_name == "trouter.message_loss":
                        logger.debug("TeamsMTK/WS: message_loss notification")
            except Exception as e:
                logger.debug("TeamsMTK/WS: parse error: %s", _log_error(e))

    @staticmethod
    def _parse_event(message: str) -> Optional[Dict[str, Any]]:
        """Parse a Socket.IO 5: frame into an event dict."""
        parts = message.split("::", 1)
        if len(parts) < 2:
            return None
        json_part = parts[1].lstrip(":")
        if not json_part:
            return None
        data = json.loads(json_part)
        name = data.get("name", "")
        body = data.get("args", [{}])[0]
        if isinstance(body.get("body"), str):
            try:
                body = json.loads(body["body"])
            except (json.JSONDecodeError, TypeError):
                pass
        resource = body.get("resource", {})
        return {
            "_trouter_name": name,
            "sender": resource.get("imdisplayname", ""),
            "content": resource.get("content", ""),
            "conversation": resource.get("conversationLink", "").split("/conversations/")[-1] if "conversationLink" in resource else "",
            "message_id": resource.get("id", ""),
            "type": resource.get("messagetype", ""),
            "timestamp": resource.get("composetime", ""),
            "ttl": body.get("ttl"),
        }

    def _register(self, ic3_token: str) -> dict:
        """POST to Trouter registration endpoint."""
        import urllib.request, certifi
        epid = uuid.uuid4().hex[:32]
        client_id = self._auth.client_id()
        url = f"{_TROUTER_URL}?con_num={client_id}_1&epid={epid}"
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(url, method="POST")
        req.add_header("Authorization", f"Bearer {ic3_token}")
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _handshake(self, trouter_info: dict, ic3_token: str, skype_token: str):
        """Socket.IO handshake to get session_id."""
        import requests

        base_url = trouter_info.get("socketio", "")
        if not base_url.endswith("/"):
            base_url += "/"
        connect_params = {
            k: v for k, v in trouter_info.get("connectparams", {}).items()
            if v != "" and k != "scae"
        }
        params = {
            "v": "v4",
            "tc": json.dumps({"cv": "2024.19.01.3", "ua": "SkypeSpaces", "hr": "", "v": "0.0.0"}),
            "con_num": f"{self._auth.client_id()}_1",
            **connect_params,
        }
        ccid = trouter_info.get("ccid")
        if ccid:
            params["ccid"] = ccid
        r = requests.get(
            f"{base_url}socket.io/1/",
            params=params,
            headers={
                "Authorization": f"Bearer {ic3_token}",
                "Authentication": f"skypetoken={skype_token}",
            },
            verify=True,
            timeout=15,
        )
        r.raise_for_status()
        session_id = r.text.split(":")[0]
        return session_id, params

    @staticmethod
    def _build_ws_url(trouter_info: dict, session_id: str, params: dict) -> str:
        """Build the WSS URL from handshake results."""
        import urllib.parse as _up
        base = trouter_info.get("socketio", "")
        if base.startswith("https://"):
            base = "wss://" + base[8:]
        if not base.endswith("/"):
            base += "/"
        filtered = {k: v for k, v in params.items() if v != "" and k != "scae"}
        qs = "&".join(f"{k}={_up.quote(str(v), safe='')}" for k, v in filtered.items())
        return f"{base}socket.io/1/websocket/{session_id}?{qs}"

    def is_healthy(self) -> bool:
        """Return True while the WebSocket is open and heartbeat is fresh."""
        if not self._ws:
            return False
        if not getattr(self, "_connected", True):
            return False

        closed = getattr(self._ws, "closed", None)
        if closed is True:
            return False

        state = getattr(self._ws, "state", None)
        state_name = getattr(state, "name", state if isinstance(state, str) else None)
        if isinstance(state_name, str):
            return state_name.upper() == "OPEN"

        last_heartbeat = getattr(self, "_last_heartbeat", None)
        if last_heartbeat is not None:
            return (time.monotonic() - last_heartbeat) < (2 * _WS_HEARTBEAT_TIMEOUT)

        # Compatibility for listeners created by the pre-websockets-15
        # implementation, which tracked wall-clock pong timestamps.
        last_pong = getattr(self, "_last_pong_time", None)
        if last_pong is None:
            return False
        timeout = getattr(self, "_heartbeat_timeout", _WS_HEARTBEAT_TIMEOUT)
        return (time.time() - last_pong) < (2 * timeout)


# ---------------------------------------------------------------------------
# G14 VIP Buffer — lightweight detection + buffering + flush-to-notify
# ---------------------------------------------------------------------------

class _VIPBuffer:
    """Per-conversation VIP message buffer.

    Detects messages from VIP OIDs, buffers them, and flushes to
    ``notify_targets`` when:
      1. Immediate flush: message ends with sentence-ending punctuation
         (。！？!?) or exceeds 100 chars (substantive message).
      2. Stale timeout: ``buffer_timeout_seconds`` (default 60s) after
         the first buffered message without a flush trigger.
    """

    _IMMEDIATE_FLUSH_ENDS = tuple("。！？!?")
    _LONG_MSG_THRESHOLD = 100  # chars

    def __init__(self, conv_id: str, oids: List[str], notify_targets: List[str],
                 buffer_timeout_seconds: float = 60.0, on_stale=None):
        self.conv_id = conv_id
        self.oids = set(oids)
        self.notify_targets = notify_targets
        self.buffer_timeout = buffer_timeout_seconds
        self._messages: List[Dict[str, Any]] = []
        self._first_msg_at: Optional[float] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._on_stale = on_stale

    def is_vip(self, sender_oid: str) -> bool:
        return sender_oid in self.oids

    def add(self, msg: Dict[str, Any]) -> str:
        """Buffer a VIP message. Returns 'immediate' | 'buffered'."""
        now = time.time()
        self._messages.append(msg)
        if self._first_msg_at is None:
            self._first_msg_at = now

        text = msg.get("content", "") or ""
        # Immediate flush if ends with sentence-ending punctuation or is long
        if (text.rstrip()[-1:] in self._IMMEDIATE_FLUSH_ENDS
                or len(text) >= self._LONG_MSG_THRESHOLD):
            return "immediate"

        # Pure buffers used outside an adapter have no callback and need no
        # background task. The adapter injects the real flush callback.
        if self._on_stale is not None:
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
            self._flush_task = asyncio.create_task(self._stale_timeout())
        return "buffered"

    async def _stale_timeout(self) -> None:
        try:
            await asyncio.sleep(self.buffer_timeout)
        except asyncio.CancelledError:
            return
        if not self._messages or self._on_stale is None:
            return
        try:
            await self._on_stale()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("TeamsMTK: VIP stale flush failed: %s", _log_error(exc))

    def should_flush(self) -> bool:
        """Check if the stale timeout has expired."""
        if not self._messages or self._first_msg_at is None:
            return False
        return (time.time() - self._first_msg_at) >= self.buffer_timeout

    def drain(self) -> List[Dict[str, Any]]:
        """Return buffered messages and reset state."""
        msgs = self._messages
        self._messages = []
        self._first_msg_at = None
        task = self._flush_task
        self._flush_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
        return msgs

    def cancel(self) -> None:
        """Cancel a pending stale timer during adapter shutdown."""
        task = self._flush_task
        self._flush_task = None
        if task and not task.done():
            task.cancel()


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
                logger.warning(
                    "TeamsMTK: invalid blocked_keywords pattern ref=%s: %s",
                    _log_ref(pattern),
                    _log_error(e),
                )
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

        _extra = _cfg.extra if isinstance(_cfg.extra, dict) else {}
        self._conv_ids = _configured_conversation_ids(_cfg)
        self._conv_id: Optional[str] = self._conv_ids[0] if self._conv_ids else None  # back-compat
        self._auth = _TeamsAuth()
        self._poll_task: Optional[asyncio.Task] = None
        self._ws_listener: Optional[_TrouterListener] = None  # WS-1: Trouter listener
        self._connected = False
        self._user_oid: Optional[str] = None  # set during connect from first poll
        self._last_sent_message_id: Optional[str] = None  # id of last message WE sent (echo guard)
        self._last_sent_message_html: Optional[str] = None  # HTML cache for trailing-footer merge
        # TTL-based outbound ownership registry. Keys include both the
        # conversation and message ID so inbound deduplication can never grant
        # delete ownership or suppress an unrelated chat with the same ID.
        from gateway.platforms.helpers import MessageDeduplicator
        self._sent_dedup = MessageDeduplicator()

        # Per-conversation last-seen message id (avoids replay on startup).
        self._last_message_ids: Dict[str, str] = {cid: None for cid in self._conv_ids}
        # WS and poll can fetch the same conversation concurrently. Serialize
        # cursor read → dispatch → advance per conversation to prevent duplicates.
        self._message_process_locks: Dict[str, asyncio.Lock] = {}
        # Legacy single-conversation alias; the active value now lives in
        # _last_message_ids.
        self._last_message_id: Optional[str] = None

        # Mention gating: default on for groups, off for DMs.
        # A comma-separated list of conv IDs that should be treated as DMs
        # (no @mention required) even though they contain @thread in the ID.
        _no_mention_value = _extra.get("no_mention_conversations")
        if _no_mention_value is None:
            _no_mention_value = os.getenv("MTK_TEAMS_NO_MENTION_CONVS", "")
        self._no_mention_convs = set(_normalize_conversation_ids(_no_mention_value))
        _require_mention = _extra.get("require_mention")
        if _require_mention is None:
            _require_mention = os.getenv("TEAMS_MTK_REQUIRE_MENTION", "true")
        if isinstance(_require_mention, str):
            self.require_mention = _require_mention.strip().lower() in (
                "true", "1", "yes", "on"
            )
        else:
            self.require_mention = bool(_require_mention)

        _poll_interval = _extra.get("poll_interval_seconds")
        if _poll_interval is None:
            _poll_interval = os.getenv("MTK_TEAMS_POLL_INTERVAL", "2")
        try:
            self._poll_interval = max(1, int(_poll_interval))
        except (TypeError, ValueError):
            self._poll_interval = 2

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

        # G14 VIP monitor: per-conversation buffer state keyed by conv_id.
        # Enabled via gateway.teams_mtk.vip_monitor config section.
        self._vip_buffers: Dict[str, Any] = {}
        self._vip_config: Dict[str, Any] = {}
        try:
            _vip_cfg = (
                load_config_readonly()
                .get("gateway", {})
                .get("teams_mtk", {})
                .get("vip_monitor", {})
            )
            if _vip_cfg and _vip_cfg.get("enabled"):
                self._vip_config = _vip_cfg
                logger.info("TeamsMTK: VIP monitor enabled (oids=%s, targets=%s)",
                            [_redact_oid(o) for o in _vip_cfg.get("oids", [])],
                            [_log_ref(t) for t in _vip_cfg.get("notify_targets", [])])
        except Exception:
            pass

    @staticmethod
    def _sent_message_key(chat_id: str, msg_id: Any) -> str:
        return f"{chat_id}\x1f{msg_id}"

    def _remember_sent_message(self, chat_id: str, msg_id: Any) -> Optional[str]:
        """Track a proven outbound message for echo guard and safe delete.

        ``_last_sent_message_id`` is only a convenience pointer and can be
        overwritten by an overlapping send. The chat-scoped TTL registry is
        the authoritative ownership signal.
        """
        if not msg_id:
            return None
        tracked_id = str(msg_id)
        self._last_sent_message_id = tracked_id
        self._sent_dedup.remember(self._sent_message_key(chat_id, tracked_id))
        return tracked_id

    def _is_sent_message(self, chat_id: str, msg_id: Any) -> bool:
        if not msg_id:
            return False
        return self._sent_dedup.contains(self._sent_message_key(chat_id, str(msg_id)))

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

    def _require_mention_for_conv(
        self,
        conv_id: str,
        group_cfg: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Resolve per-group config before legacy and global defaults."""
        if group_cfg is None:
            group_cfg = self._group_config(conv_id)
        configured = group_cfg.get("require_mention")
        if configured is not None:
            return bool(configured)
        if conv_id in self._no_mention_convs:
            return False
        return self.require_mention

    def _cold_start_seed_id(self, conv_id: str, messages: List[dict]) -> str:
        """Choose a replay boundary that preserves one unanswered user turn."""
        ordered = sorted(
            (msg for msg in messages if msg.get("id")),
            key=lambda msg: _message_id_key(msg["id"]),
        )
        if not ordered:
            return ""
        latest_id = str(max(ordered, key=lambda msg: _message_id_key(msg["id"]))["id"])

        is_group = "@thread" in conv_id
        group_cfg = self._group_config(conv_id) if is_group else {}
        require_mention = self._require_mention_for_conv(conv_id, group_cfg)

        for index in range(len(ordered) - 1, -1, -1):
            msg = ordered[index]
            props = msg.get("properties") or {}
            raw_props = msg.get("_raw_properties") or {}
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            if isinstance(raw_props, str):
                try:
                    raw_props = json.loads(raw_props)
                except (json.JSONDecodeError, TypeError):
                    raw_props = {}
            sender_marker = props.get("hermes_sender") or raw_props.get("hermes_sender")
            if sender_marker in ("agent", "bot"):
                return latest_id

            msg_type = msg.get("messagetype", "")
            if msg_type in ("ThreadActivity/MemberJoined", "ThreadActivity/TopicUpdate"):
                continue
            text, _ = _clean_message_content(msg.get("content", "") or "")
            if not text:
                continue
            if is_group and require_mention and self._MENTION_TAG.lower() not in text.lower():
                continue

            if index > 0:
                return str(ordered[index - 1]["id"])
            candidate_id = str(msg["id"])
            if candidate_id.isdigit():
                return str(max(int(candidate_id) - 1, 0))
            return ""
        return latest_id

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

    def _filter_outbound_content(self, chat_id: str, content: str) -> str:
        """Apply the per-group blocked-keyword policy to outbound content."""
        if not content or content == self._BLOCKED_KEYWORD_NOTICE:
            return content
        hit = self._find_blocked_keyword(
            content,
            self._group_blocked_keyword_patterns(chat_id),
        )
        if not hit:
            return content
        logger.warning(
            "TeamsMTK: blocked outbound reply in conv=%s (pattern ref=%s)",
            _log_ref(chat_id),
            _log_ref(hit),
        )
        return self._BLOCKED_KEYWORD_NOTICE

    # ---- BasePlatformAdapter required overrides ----

    async def connect(self, is_reconnect: bool = False) -> bool:
        if not self._conv_ids:
            logger.error("TeamsMTK: MTK_TEAMS_CONVERSATION_ID not set")
            return False

        try:
            # Validate token on startup
            self._auth.skype_token()
        except Exception as e:
            logger.error("TeamsMTK: auth failed — %s", _log_error(e))
            return False

        # Seed each conversation at the latest safe replay boundary. This skips
        # history while allowing one unanswered user turn to survive a restart.
        for _conv_id in self._conv_ids:
            try:
                msgs = self._fetch_messages(conv_id=_conv_id, limit=20)
                if msgs:
                    _max_id = str(max(
                        (m for m in msgs if m.get("id")),
                        key=lambda m: _message_id_key(m["id"]),
                    )["id"])
                    _seed_id = self._cold_start_seed_id(_conv_id, msgs)
                    self._last_message_ids[_conv_id] = _seed_id
                    if _seed_id != _max_id:
                        logger.info(
                            "TeamsMTK: cold-start catchup armed after msg=%s for conv=%s",
                            _log_ref(_seed_id),
                            _log_ref(_conv_id),
                        )
                    # Extract user OID from first message's "from" URL
                    for m in msgs:
                        from_url = m.get("from", "")
                        if "8:orgid:" in from_url:
                            self._user_oid = from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")
                            logger.info("TeamsMTK: user OID: %s", _redact_oid(self._user_oid))
                            break
                    logger.debug(
                        "TeamsMTK: seeded last_message_id=%s for conv=%s",
                        _log_ref(self._last_message_ids[_conv_id]),
                        _log_ref(_conv_id),
                    )
            except Exception as e:
                logger.warning(
                    "TeamsMTK: could not seed last message id for conv=%s: %s",
                    _log_ref(_conv_id),
                    _log_error(e),
                )

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

        # WS-1/5: Start Trouter listener alongside poll loop
        loop = asyncio.get_event_loop()
        self._ws_listener = _TrouterListener(
            self._auth, on_event=self._on_ws_event, loop=loop,
        )
        self._ws_listener.start()
        logger.info("TeamsMTK: Trouter WS listener starting")

        self._mark_connected()
        logger.info(
            "TeamsMTK: connected — polling %d conversation(s) every %ds: %s",
            len(self._conv_ids), self._poll_interval,
            ", ".join(_log_ref(c) for c in self._conv_ids),
        )
        return True

    async def disconnect(self) -> None:
        self._running = False
        # Stop WS listener first (clean WebSocket close)
        if self._ws_listener:
            await self._ws_listener.stop()
            self._ws_listener = None
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

        content = self._filter_outbound_content(chat_id, content)

        _skip_footer_extract = bool(metadata and metadata.get("skip_footer_extract"))
        try:
            await self._maybe_throttle(chat_id)

            import re
            from datetime import datetime
            html_content, runtime_footer = self._build_html(content, _skip_footer_extract)

            # Trailing-footer-only message (streaming mode):
            # Merge into the last body message instead of sending a separate mini-card.
            if not html_content or (runtime_footer and not content.strip()):
                if self._last_sent_message_id and runtime_footer and self._last_sent_message_html:
                    _existing = self._last_sent_message_html
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
                        _patched = _existing.replace("</div>", f"{_new_footer}</div>", 1)
                    try:
                        _edit_res = await self.edit_message(
                            chat_id, self._last_sent_message_id, _patched, finalize=True,
                        )
                        if _edit_res.success:
                            logger.info(
                                "TeamsMTK: merged trailing footer into msg %s",
                                _log_ref(self._last_sent_message_id),
                            )
                            return SendResult(success=True)
                    except Exception as _ee:
                        logger.debug("TeamsMTK: footer edit failed, falling back to send: %s", _log_error(_ee))
                html_content, _ = self._build_html(runtime_footer, _skip_footer_extract=True)

            # SDK-3b: delegate to SDK MessagesService.send() when available.
            # Falls back to raw HTTP on any SDK failure.
            if _SDK_AVAILABLE:
                try:
                    adapter = _SDKAuthAdapter(self._auth)
                    http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
                    svc = _SDKMessages(http_layer)
                    result = svc.send(
                        conversation_id=chat_id,
                        content=html_content,
                        is_html=True,
                        return_context=False,
                    )
                    # SDK now returns OriginalArrivalTime as "id" when MSG API
                    # omits the "id" key (which happens in both 1:1 DMs and
                    # groups).  Fallback: read-back latest messages.
                    msg_id = result.get("id")
                    if not msg_id:
                        try:
                            recent = self._fetch_messages(chat_id, limit=3)
                            for m in recent:
                                _props = m.get("properties", {})
                                _raw = m.get("_raw_properties", {})
                                _sender = _props.get("hermes_sender") or _raw.get("hermes_sender")
                                if _sender in ("agent", "bot"):
                                    msg_id = m.get("id", "")
                                    break
                            if msg_id:
                                logger.info(
                                    "TeamsMTK: recovered msg id=%s from read-back",
                                    _log_ref(msg_id),
                                )
                        except Exception:
                            logger.debug("TeamsMTK: msg-id read-back failed")
                    if msg_id:
                        self._remember_sent_message(chat_id, msg_id)
                        if html_content:
                            self._last_sent_message_html = html_content
                    logger.info(
                        "TeamsMTK: sent message id=%s to %s via SDK (html=%d chars)",
                        _log_ref(msg_id), _log_ref(chat_id), len(html_content) if html_content else 0,
                    )
                    return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
                except Exception as _sdk_err:
                    logger.warning(
                        "TeamsMTK: SDK send failed (%s) — falling back to raw HTTP",
                        _log_error(_sdk_err),
                    )

            # Raw HTTP fallback (SDK unavailable or SDK send failed)
            import requests
            from requests.adapters import HTTPAdapter
            self._auth._inject_truststore()
            session = requests.Session()
            session.mount("https://", HTTPAdapter(pool_connections=0, pool_maxsize=0, max_retries=0))
            try:
                for attempt in range(2):
                    skype_token = self._auth.skype_token()
                    url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
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
                        verify=True,
                        timeout=15,
                    )
                    if resp.status_code == 401 and attempt == 0:
                        self._auth._force_refresh()
                        continue
                    if resp.status_code == 429 and attempt == 0:
                        logger.warning(
                            "TeamsMTK: send hit 429 rate limit for conv=%s — backing off %.1fs then retrying once",
                            _log_ref(chat_id), self._RATE_LIMIT_BACKOFF_S,
                        )
                        await asyncio.sleep(self._RATE_LIMIT_BACKOFF_S)
                        continue
                    break
            finally:
                session.close()

            resp.raise_for_status()
            data = resp.json()
            # MSG API returns the message ID as "OriginalArrivalTime"
            # (not under "id").  This IS the real message ID usable for
            # edit/delete, not a timestamp.
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
                if html_content:
                    self._last_sent_message_html = html_content
            logger.info(
                "TeamsMTK: sent message id=%s to %s via raw HTTP (html=%d chars)",
                _log_ref(msg_id), _log_ref(chat_id), len(html_content) if html_content else 0,
            )
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.error("TeamsMTK: send failed: %s", _log_error(e))
            return SendResult(success=False, error=str(e))

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": chat_id, "type": "group" if "@thread" in chat_id else "dm", "chat_id": chat_id}

    @staticmethod
    def _inline_md_to_html(text: str) -> str:
        """Convert inline markdown (bold/code/bullets/headers) to HTML.

        Runs BEFORE table extraction so bold/code inside table cells also
        gets converted. Safe to run on content that already has real HTML
        tags mixed in — it only targets literal markdown syntax
        (``**``, `` ` ``, leading ``- ``/``# ``), not existing tags.
        """
        # Headers: "### Foo" -> "<b>Foo</b>" (line-anchored, 1-6 #'s)
        text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
        # Bold: **foo** -> <b>foo</b> (non-greedy, single line)
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Inline code: `foo` -> <code>foo</code>
        text = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', text)
        # Markdown links: [text](url) -> <a href="url">text</a>
        text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)
        # Bullet lines: "- foo" / "* foo" -> "• foo" (skip pipe-table rows)
        text = re.sub(r'^[ \t]*[-*][ \t]+(?!\|)(.+)$', r'• \1', text, flags=re.MULTILINE)
        return text

    @staticmethod
    def _md_tables_to_html(text: str) -> str:
        """Convert markdown pipe tables in *text* to HTML <table border="1">.

        Handles mixed content where some sections are already HTML
        (e.g. <h3>, <ul>) and others are markdown pipe-tables.
        Non-table lines just get ``\\n → <br>`` replacement.
        """
        lines = text.split('\n')
        result: list[str] = []
        in_table = False
        table_rows: list[list[str]] = []
        is_header_row = True

        def _flush_table() -> None:
            nonlocal in_table, table_rows, is_header_row
            if not table_rows:
                return
            html = '<table border="1" style="border-collapse:collapse">'
            for ri, row in enumerate(table_rows):
                tag = 'th' if ri == 0 else 'td'
                html += '<tr>' + ''.join(f'<{tag}>{cell.strip()}</{tag}>' for cell in row) + '</tr>'
            html += '</table>'
            result.append(html)
            table_rows = []
            is_header_row = True
            in_table = False

        for ln in lines:
            stripped = ln.strip()
            # Detect pipe-table row: starts and ends with |
            if '|' in stripped and stripped.startswith('|') and stripped.endswith('|'):
                cells = [c for c in stripped.split('|')[1:-1]]
                # Skip separator rows (|---|---|)
                if all(re.fullmatch(r'[-:]+', c.strip()) for c in cells):
                    is_header_row = False
                    continue
                in_table = True
                table_rows.append(cells)
            else:
                if in_table:
                    _flush_table()
                result.append(ln.replace('\n', '<br>') if '\n' in ln else ln)

        _flush_table()
        # Replace remaining newlines (outside tables) with <br>
        return '<br>'.join(result)

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
        has_html_tags = bool(re.search(r'<(b|i|a|br|h[1-6]|ul|ol|li|pre|code|strong|em|table|thead|tbody|tr|th|td)\b', content))
        has_md_tables = bool(re.search(r'^\s*\|.+\|\s*$', content, re.MULTILINE))
        has_inline_md = bool(re.search(r'\*\*.+?\*\*|`[^`\n]+?`|^#{1,6}\s|^[ \t]*[-*][ \t]+(?!\|)|\[[^\]]+\]\(https?://[^\s)]+\)', content, re.MULTILINE))

        if has_html_tags and (has_md_tables or has_inline_md):
            # Mixed mode: content has real HTML tags AND leftover markdown
            # syntax (bold/code/bullets/headers/pipe-tables) that a model
            # emitted alongside them. Convert markdown pieces to HTML first,
            # then collapse remaining newlines.
            body_html = self._md_tables_to_html(self._inline_md_to_html(content))
        elif has_html_tags:
            # Pure HTML-ish content — just replace newlines
            body_html = content.replace('\n', '<br>')
        else:
            # Pure markdown — full conversion
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
                    _log_ref(chat_id), elapsed, remaining,
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
        content = self._filter_outbound_content(chat_id, content)
        try:
            await self._maybe_throttle(chat_id)

            import re
            self._auth._inject_truststore()

            # If content is already a branded-template HTML (e.g. from the
            # trailing-footer merge path), use it as-is to avoid double-wrapping.
            is_already_html = bool(re.search(r'<div\s+style="border-left:', content))
            if is_already_html:
                html_content = content
            else:
                html_content, _ = self._build_html(content)

            logger.info(
                "TeamsMTK: editing message %s — content=%d chars, html=%d chars, finalize=%s",
                _log_ref(message_id), len(content), len(html_content), finalize,
            )

            # SDK-3c: delegate to SDK MessagesService.edit() when available.
            if _SDK_AVAILABLE:
                try:
                    adapter = _SDKAuthAdapter(self._auth)
                    http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
                    svc = _SDKMessages(http_layer)
                    svc.edit(
                        conversation_id=chat_id,
                        message_id=message_id,
                        content=html_content,
                    )
                    logger.info("TeamsMTK: edited message %s via SDK", _log_ref(message_id))
                    return SendResult(success=True, message_id=message_id)
                except Exception as _sdk_err:
                    logger.warning(
                        "TeamsMTK: SDK edit failed (%s) — falling back to raw HTTP",
                        _log_error(_sdk_err),
                    )

            # Raw HTTP fallback
            import requests
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages/{message_id}"
            payload = {"content": html_content, "messagetype": "RichText/Html", "contenttype": "text"}
            headers = {"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"}
            resp = requests.put(url, json=payload, headers=headers, verify=True, timeout=30)
            if resp.status_code == 429:
                logger.warning(
                    "TeamsMTK: edit hit 429 rate limit for msg %s — backing off %.1fs then retrying once",
                    _log_ref(message_id), self._RATE_LIMIT_BACKOFF_S,
                )
                await asyncio.sleep(self._RATE_LIMIT_BACKOFF_S)
                resp = requests.put(url, json=payload, headers=headers, verify=True, timeout=30)
            resp.raise_for_status()
            logger.info(
                "TeamsMTK: edited message %s via raw HTTP (resp=%d bytes)",
                _log_ref(message_id),
                len(resp.content),
            )
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.warning("TeamsMTK: edit failed (%s) — streaming will fall back to new message", _log_error(e))
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata=None) -> bool:
        """Send a one-shot typing indicator via the Skype chat service.

        Posts {"messagetype": "Control/Typing", "content": ""} — the Skype
        consumer messaging protocol's typing-indicator message type. Callers
        (BasePlatformAdapter._keep_typing) invoke this on a repeating timer
        while an agent turn is in flight, so any failure here (network,
        auth, rate limit) must be swallowed rather than raised — a dropped
        typing ping is invisible to the user, but an unhandled exception
        would kill the keep-typing loop for the rest of the turn.

        Returns True if the POST returned 201, False otherwise.
        """
        try:
            self._auth._inject_truststore()
            import requests
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations/{chat_id}/messages"
            payload = {"messagetype": "Control/Typing", "content": ""}
            headers = {"Authentication": f"skypetoken={skype_token}", "Content-Type": "application/json"}
            with requests.Session() as session:
                resp = session.post(url, json=payload, headers=headers, verify=True, timeout=10)
            if resp.status_code != 201:
                logger.warning(
                    "TeamsMTK: send_typing got status %s for conv=%s",
                    resp.status_code,
                    _log_ref(chat_id),
                )
                return False
            else:
                logger.info("TeamsMTK: send_typing ok conv=%s", _log_ref(chat_id))
                return True
        except Exception as e:
            logger.debug("TeamsMTK: send_typing failed (non-fatal): %s", _log_error(e))
            return False

    # ---- G-MEDIA: image / document / adaptive card sending ----

    # AMS (Async Media Service) endpoints — reverse-engineered from the teams
    # skill's src/api/_files.py + src/api/_constants.py. AMS uses a DIFFERENT
    # auth header format than the chat service ("skype_token {token}", not
    # "skypetoken={token}") and requires the Teams desktop User-Agent.
    _AMS_BASE_URL = "https://api.asm.skype.com/v1/objects"
    _AMS_USER_AGENT = "27/1.0.0.0"

    async def send_image_file(self, chat_id: str, path: str, caption: str = "") -> "SendResult":
        """Upload a local image to AMS and send it inline (AMS 3-step flow).

        REPLACE-4: delegates to SDK FilesService.send_image() when available.
        Falls back to raw HTTP if SDK not on sys.path.
        """
        from gateway.platforms.base import SendResult
        import mimetypes
        try:
            with open(path, "rb") as f:
                image_data = f.read()
        except OSError as e:
            return SendResult(success=False, error=f"Cannot read image file: {e}")

        content_type = mimetypes.guess_type(path)[0] or "image/png"

        # REPLACE-4: SDK path
        if _SDK_AVAILABLE and _SDKFiles is not None:
            try:
                self._auth._inject_truststore()
                adapter = _SDKAuthAdapter(self._auth)
                http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
                svc = _SDKFiles(http_layer, _SDKMessages(http_layer))
                result = svc.send_image(chat_id, image_data, content_type, caption=caption)
                msg_id = result.get("id", "")
                if msg_id:
                    self._remember_sent_message(chat_id, msg_id)
                return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
            except Exception as _sdk_err:
                logger.warning(
                    "TeamsMTK: SDK send_image failed (%s) — falling back to raw HTTP",
                    _log_error(_sdk_err),
                )

        # Fallback: raw HTTP AMS 3-step flow
        import requests
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
                verify=True,
                timeout=30,
            )
            create_resp.raise_for_status()
            ams_id = create_resp.json()["id"]

            # Step 2: upload image binary
            upload_resp = requests.put(
                f"{self._AMS_BASE_URL}/{ams_id}/content/imgpsh",
                headers={**ams_headers, "Content-Type": content_type},
                data=image_data,
                verify=True,
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
                verify=True,
                timeout=15,
            )
            msg_resp.raise_for_status()
            msg_id = msg_resp.json().get("id")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_image_file failed: %s", _log_error(e))
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
                    verify=True,
                    timeout=15,
                )
                resp.raise_for_status()
                msg_id = resp.json().get("id")
                if msg_id:
                    self._remember_sent_message(chat_id, msg_id)
                return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
            except Exception as e:
                logger.warning("TeamsMTK: send_image (AMS direct embed) failed: %s", _log_error(e))
                return SendResult(success=False, error=str(e))

        if _re.match(r"^https?://", image_url_or_path):
            # Remote (non-AMS) URL — download then delegate to send_image_file.
            import tempfile, os as _os
            try:
                dl_resp = requests.get(image_url_or_path, timeout=30, verify=True)
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
                logger.warning("TeamsMTK: send_image (remote download) failed: %s", _log_error(e))
                return SendResult(success=False, error=str(e))

        # Local filesystem path.
        return await self.send_image_file(chat_id, image_url_or_path, caption=caption)

    async def send_document(self, chat_id: str, path: str, caption: str = "") -> "SendResult":
        """Upload a local file to OneDrive and share a clickable link.

        REPLACE-5: delegates to SDK FilesService.send_file() when available.
        Falls back to raw HTTP if SDK not on sys.path.
        """
        from gateway.platforms.base import SendResult
        import os as _os

        filename = _os.path.basename(path)
        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
        except OSError as e:
            return SendResult(success=False, error=f"Cannot read file: {e}")

        # REPLACE-5: SDK path
        if _SDK_AVAILABLE and _SDKFiles is not None:
            try:
                self._auth._inject_truststore()
                adapter = _SDKAuthAdapter(self._auth)
                http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
                msg_svc = _SDKMessages(http_layer)
                file_svc = _SDKFiles(http_layer, msg_svc)
                graph_api = _SDKGraphAdapter(self._auth, verify_ssl=True)
                result = file_svc.send_file(chat_id, file_bytes, filename, graph_api, caption=caption)
                msg_id = result.get("id", "")
                if msg_id:
                    self._remember_sent_message(chat_id, msg_id)
                return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
            except Exception as _sdk_err:
                logger.warning(
                    "TeamsMTK: SDK send_file failed (%s) — falling back to raw HTTP", _log_error(_sdk_err),
                )

        # Fallback: raw HTTP Graph upload + Skype send
        import requests
        try:
            self._auth._inject_truststore()
            graph_token = self._auth.graph_token()
            headers = {
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/octet-stream",
            }
            import time as _time, uuid as _uuid
            unique_name = f"{int(_time.time())}_{_uuid.uuid4().hex[:8]}{_os.path.splitext(filename)[1]}"
            target_path = f"/Microsoft Teams Chat Files/TeamsMCP/{unique_name}"
            upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:{target_path}:/content"
            upload_resp = requests.put(
                upload_url, headers=headers, data=file_bytes, verify=True, timeout=(10, 120),
            )
            if upload_resp.status_code not in (200, 201):
                logger.error(
                    "TeamsMTK: send_document upload failed (status=%s)",
                    upload_resp.status_code,
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
                    verify=True,
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
                verify=True,
                timeout=15,
            )
            msg_resp.raise_for_status()
            msg_id = msg_resp.json().get("id")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_document failed: %s", _log_error(e))
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
                verify=True,
                timeout=15,
            )
            resp.raise_for_status()
            msg_id = resp.json().get("id")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
            return SendResult(success=True, message_id=str(msg_id) if msg_id else None)
        except Exception as e:
            logger.warning("TeamsMTK: send_adaptive_card failed (%s) — falling back to text", _log_error(e))
            if fallback_text:
                return await self.send(chat_id=chat_id, content=fallback_text, metadata=None)
            return SendResult(success=False, error=str(e))

    # ---- G13-A: read-only contact / conversation lookup ----

    def list_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List conversations visible to this account via the Skype chat service.

        REPLACE-6: delegates to SDK ConversationsService.list() when available.
        Falls back to raw HTTP if SDK not on sys.path.
        """
        # REPLACE-6: SDK path
        if _SDK_AVAILABLE and _SDKConvs is not None:
            try:
                self._auth._inject_truststore()
                adapter = _SDKAuthAdapter(self._auth)
                http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
                msg_svc = _SDKMessages(http_layer)
                svc = _SDKConvs(http_layer, msg_svc)
                raw = svc.list(limit=limit)
                # Normalize to gateway's expected shape
                results: List[Dict[str, Any]] = []
                for conv in raw:
                    results.append({
                        "id": conv.get("id", ""),
                        "title": conv.get("title", ""),
                        "type": conv.get("type", ""),
                        "member_names": conv.get("title", ""),  # SDK doesn't return members in list()
                    })
                logger.info("TeamsMTK: list_conversations SDK ok, %d convs", len(results))
                return results
            except Exception as _sdk_err:
                logger.warning(
                    "TeamsMTK: SDK list_conversations failed (%s) — falling back to raw HTTP", _log_error(_sdk_err),
                )

        # Fallback: raw HTTP
        import requests
        try:
            self._auth._inject_truststore()
            skype_token = self._auth.skype_token()
            url = f"{self._auth.msg_base}/conversations"
            session = requests.Session()
            resp = session.get(
                url,
                headers={"Authentication": f"skypetoken={skype_token}"},
                verify=True,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("TeamsMTK: list_conversations failed: %s", _log_error(e))
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
        logger.info("TeamsMTK: list_conversations raw HTTP ok, %d convs", len(results))
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

    def _search_users(self, query: str) -> List[Dict[str, Any]]:
        """S3-1: Search AAD/M365 users by display name or email prefix via Graph API.

        Uses the gateway's existing graph_token() so no extra OAuth scope is needed.
        Delegates to Graph /users?$filter=startswith(...), matching the
        configured Teams directory helper's lookup semantics.

        Args:
            query: Name or email prefix to search (e.g. "Alice", "alice@").

        Returns:
            List of {display_name, email, oid} dicts, up to 10 results.
            Returns [] on any error (network, auth, etc.) — non-fatal.
        """
        try:
            import requests as _req
            self._auth._inject_truststore()
            graph_token = self._auth.graph_token()
            filter_str = (
                f"startswith(displayName,'{query}') or "
                f"startswith(mail,'{query}')"
            )
            resp = _req.get(
                "https://graph.microsoft.com/v1.0/users",
                params={"$filter": filter_str, "$top": 10},
                headers={"Authorization": f"Bearer {graph_token}"},
                verify=True,
                timeout=15,
            )
            resp.raise_for_status()
            users = resp.json().get("value", [])
            return [
                {
                    "display_name": u.get("displayName", ""),
                    "email": u.get("mail") or u.get("userPrincipalName", ""),
                    "oid": u.get("id", ""),
                }
                for u in users
            ]
        except Exception as e:
            logger.warning("TeamsMTK: _search_users failed (%s)", _log_error(e))
            return []

    def _get_schedule(
        self, emails: List[str], date_str: Optional[str] = None, interval: int = 30
    ) -> List[Dict[str, Any]]:
        """S3-2: Get free/busy schedule for AAD users via Graph API.

        Args:
            emails:   List of email addresses to check.
            date_str: Target date (YYYY-MM-DD). Defaults to today (CST +8).
            interval: Availability interval in minutes (default 30).

        Returns:
            List of schedule dicts from Graph /me/calendar/getSchedule.
            Each dict has ``availabilityView`` string where
            0=free, 1=tentative, 2=busy, 3=OOF, 4=working elsewhere.
            Returns [] on error (non-fatal).
        """
        try:
            import requests as _req
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            self._auth._inject_truststore()
            graph_token = self._auth.graph_token()
            tz = _tz(_td(hours=8))
            now = _dt.now(tz)
            if date_str:
                target = _dt.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
            else:
                target = now
            start = target.replace(hour=9, minute=0, second=0)
            end = target.replace(hour=18, minute=0, second=0)

            body = {
                "schedules": emails,
                "startTime": {
                    "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "Asia/Shanghai",
                },
                "endTime": {
                    "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "Asia/Shanghai",
                },
                "availabilityViewInterval": interval,
            }
            resp = _req.post(
                "https://graph.microsoft.com/v1.0/me/calendar/getSchedule",
                json=body,
                headers={
                    "Authorization": f"Bearer {graph_token}",
                    "Content-Type": "application/json",
                },
                verify=True,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", [])
        except Exception as e:
            logger.warning("TeamsMTK: _get_schedule failed (%s)", _log_error(e))
            return []

    def _find_common_availability(
        self, user_queries: List[str], date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """S3-3: Find meeting slots where all named participants are free.

        Resolves user names -> emails via _search_users, delegates to
        _get_schedule, then parses availabilityView to compute free slots.

        Args:
            user_queries: List of user name/email strings.
            date_str:     Target date (YYYY-MM-DD). Defaults to today.

        Returns:
            Dict with resolved_users, available_slots, and notes.
            On ambiguity (2+ matches for a name) or error, the slot
            list is empty and notes explain the problem.
        """
        try:
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            tz = _tz(_td(hours=8))
            if date_str:
                target_date = _dt.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
            else:
                target_date = _dt.now(tz)
            start = target_date.replace(hour=9, minute=0, second=0)
            end = target_date.replace(hour=18, minute=0, second=0)

            # Resolve each user with ambiguity guard
            resolved = []
            for query in user_queries:
                query = query.strip()
                if not query:
                    continue
                if "@" in query:
                    resolved.append({"query": query, "email": query, "name": query})
                    continue
                matches = self._search_users(query)
                if len(matches) == 0:
                    return {
                        "resolved_users": resolved,
                        "date": target_date.strftime("%Y-%m-%d"),
                        "available_slots": [],
                        "notes": [f"User '{query}' not found. Try full name or email."],
                    }
                elif len(matches) == 1:
                    u = matches[0]
                    resolved.append({
                        "query": query,
                        "email": u["email"],
                        "name": u["display_name"],
                    })
                else:
                    candidates = [f"  - {u['display_name']} -- {u['email']}" for u in matches[:5]]
                    return {
                        "resolved_users": resolved,
                        "date": target_date.strftime("%Y-%m-%d"),
                        "available_slots": [],
                        "notes": [
                            f"Ambiguous user '{query}'. Found {len(matches)} matches:\n"
                            + "\n".join(candidates)
                            + "\nAsk which person they mean, or provide the full email."
                        ],
                    }
            if not resolved:
                return {
                    "resolved_users": [],
                    "date": target_date.strftime("%Y-%m-%d"),
                    "available_slots": [],
                    "notes": ["No users specified."],
                }

            emails = [r["email"] for r in resolved]
            schedules = self._get_schedule(emails, date_str=date_str, interval=30)
            if not schedules:
                return {
                    "resolved_users": resolved,
                    "date": target_date.strftime("%Y-%m-%d"),
                    "available_slots": [],
                    "notes": ["Schedule API returned no data."],
                }

            status_map = {"1": "tentative", "2": "busy", "3": "OOF", "4": "working elsewhere"}
            slot_count = max((len(s.get("availabilityView", "")) for s in schedules), default=0)
            available_slots = []
            notes = []

            for slot_idx in range(slot_count):
                slot_start = start + _td(minutes=30 * slot_idx)
                slot_end = slot_start + _td(minutes=30)
                all_free = True
                slot_notes = []
                for i, sched in enumerate(schedules):
                    view = sched.get("availabilityView", "")
                    name = resolved[i]["name"] if i < len(resolved) else emails[i]
                    if slot_idx < len(view):
                        status = view[slot_idx]
                        if status != "0":
                            all_free = False
                            slot_notes.append(f"{name}: {status_map.get(status, 'unavailable')}")
                    else:
                        all_free = False
                        slot_notes.append(f"{name}: unknown (no data)")
                if all_free:
                    available_slots.append({
                        "start": slot_start.strftime("%H:%M"),
                        "end": slot_end.strftime("%H:%M"),
                    })
                elif slot_notes:
                    for note in slot_notes:
                        if note not in notes:
                            notes.append(note)

            # Merge adjacent free slots
            merged = []
            for slot in available_slots:
                if merged and merged[-1]["end"] == slot["start"]:
                    merged[-1]["end"] = slot["end"]
                else:
                    merged.append(dict(slot))

            return {
                "resolved_users": resolved,
                "date": target_date.strftime("%Y-%m-%d"),
                "available_slots": merged,
                "notes": notes,
            }
        except Exception as e:
            logger.warning("TeamsMTK: _find_common_availability failed (%s)", _log_error(e))
            return {
                "resolved_users": [],
                "date": date_str or "unknown",
                "available_slots": [],
                "notes": [f"Error: {e}"],
            }

    async def _flush_vip_buffer(self, conv_id: str) -> None:
        """Flush buffered VIP messages to notify_targets."""
        _buf = self._vip_buffers.get(conv_id)
        if not _buf:
            return
        msgs = _buf.drain()
        if not msgs:
            return
        # Compose summary from buffered messages
        _parts = []
        for m in msgs:
            _text = m.get("content", "") or ""
            if _strip_teams_html is not None:
                _text, _ = _strip_teams_html(_text)
            _sender = m.get("imdisplayname") or "VIP"
            _parts.append(f"[{_sender}] {_text.strip()}")
        _summary = "\n".join(_parts)
        # Route to each notify_target
        for _target in _buf.notify_targets:
            try:
                await self.send(_target, f"📋 VIP buffered ({len(msgs)} msg):\n{_summary}")
                logger.info("TeamsMTK: VIP flush %d msgs → %s", len(msgs), _log_ref(_target))
            except Exception as e:
                logger.error("TeamsMTK: VIP flush send error to %s: %s", _log_ref(_target), _log_error(e))

    async def cancel_background_tasks(self) -> None:
        """Cancel poll + WS tasks, then delegate to base for in-flight message tasks."""
        self._running = False
        for vip_buffer in self._vip_buffers.values():
            vip_buffer.cancel()
        if self._ws_listener:
            await self._ws_listener.stop()
            self._ws_listener = None
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await super().cancel_background_tasks()

    # ---- WS event handler (WS-4 + REV-4) ----

    async def _on_ws_event(self, evt: Dict[str, Any]) -> None:
        """Handle Trouter message event — trigger immediate fetch + process.

        WS-4: When WS pushes a message event, immediately fetch the full
        message details (WS events only carry a subset) and process them.
        REV-4: VIP buffer flush is also triggered since WS events arrive
        faster than poll ticks.
        """
        conv_id = evt.get("conversation", "")
        if not conv_id or conv_id not in self._last_message_ids:
            # Not a monitored conversation — ignore
            return
        logger.info(
            "TeamsMTK/WS: message event for conv=%s — triggering immediate fetch",
            _log_ref(conv_id),
        )
        try:
            import concurrent.futures
            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            msgs = await loop.run_in_executor(executor, lambda: self._fetch_messages(conv_id))
            await self._process_new_messages(conv_id, msgs)
            # REV-4: after processing, flush any VIP buffers whose
            # stale timeout has expired (WS arrives faster than poll).
            _vip_buf = self._vip_buffers.get(conv_id)
            if _vip_buf and _vip_buf.should_flush():
                await self._flush_vip_buffer(conv_id)
            executor.shutdown(wait=False)
        except Exception as e:
            logger.warning("TeamsMTK/WS: immediate fetch failed (%s) — poll will catch it", _log_error(e))

    # ---- S7: Reactions (send/remove) ----

    async def send_reaction(self, chat_id: str, message_id: str, reaction: str) -> dict:
        """Send an emoji reaction to a message.

        ``reaction`` must be one of: like, heart, laugh, surprised, sad, angry.
        Uses SDK ReactionsService when available, falls back to raw Graph API.
        """
        if reaction not in _VALID_REACTIONS:
            return {"status": "error", "error": f"Invalid reaction '{reaction}'. "
                    f"Valid: {', '.join(sorted(_VALID_REACTIONS))}"}
        try:
            if _SDK_AVAILABLE and self._auth.graph_token():
                _graph = _SDKGraphAdapter(self._auth, verify_ssl=True)
                _svc = _SDKReactions(_graph)
                result = _svc.send(chat_id, message_id, reaction)
                logger.info("TeamsMTK: sent reaction %s to msg=%s", reaction, _log_ref(message_id))
                return result
            # Raw fallback
            url = (f"https://graph.microsoft.com/beta/chats/{chat_id}"
                   f"/messages/{message_id}/setReaction")
            import requests as _requests
            try:
                self._auth._graph_request(
                    "POST", url, json={"reactionType": _REACTION_EMOJI[reaction]}
                )
            except _requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                if response is None or response.status_code != 409:
                    raise
            logger.info("TeamsMTK: sent reaction %s to msg=%s (raw)", reaction, _log_ref(message_id))
            return {"status": "reacted", "reaction": reaction, "message_id": message_id}
        except Exception as e:
            logger.error("TeamsMTK: send_reaction error: %s", _log_error(e))
            return {"status": "error", "error": str(e)}

    async def remove_reaction(self, chat_id: str, message_id: str, reaction: str) -> dict:
        """Remove an emoji reaction from a message."""
        if reaction not in _VALID_REACTIONS:
            return {"status": "error", "error": f"Invalid reaction '{reaction}'. "
                    f"Valid: {', '.join(sorted(_VALID_REACTIONS))}"}
        try:
            if _SDK_AVAILABLE and self._auth.graph_token():
                _graph = _SDKGraphAdapter(self._auth, verify_ssl=True)
                _svc = _SDKReactions(_graph)
                result = _svc.remove(chat_id, message_id, reaction)
                logger.info("TeamsMTK: removed reaction %s from msg=%s", reaction, _log_ref(message_id))
                return result
            # Raw fallback
            url = (f"https://graph.microsoft.com/beta/chats/{chat_id}"
                   f"/messages/{message_id}/unsetReaction")
            import requests as _requests
            try:
                self._auth._graph_request(
                    "POST", url, json={"reactionType": _REACTION_EMOJI[reaction]}
                )
            except _requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                if response is None or response.status_code != 404:
                    raise
            logger.info("TeamsMTK: removed reaction %s from msg=%s (raw)", reaction, _log_ref(message_id))
            return {"status": "removed", "reaction": reaction, "message_id": message_id}
        except Exception as e:
            logger.error("TeamsMTK: remove_reaction error: %s", _log_error(e))
            return {"status": "error", "error": str(e)}

    # ---- S9: Message deletion ----

    async def delete_message(self, chat_id: str, message_id: str) -> dict:
        """Delete a message from a conversation.

        Only the sender's own messages can be deleted. Uses SDK
        MessagesService.delete() when available, falls back to raw API.
        """
        try:
            if _SDK_AVAILABLE and self._auth.skype_token():
                _adapter = _SDKAuthAdapter(self._auth)
                _http = _SDKHTTPLayer(_adapter, verify_ssl=True)
                _svc = _SDKMessages(_http)
                result = _svc.delete(chat_id, message_id)
                logger.info(
                    "TeamsMTK: deleted msg=%s in conv=%s",
                    _log_ref(message_id),
                    _log_ref(chat_id),
                )
                return result
            # Raw fallback — regional MSG endpoint + MSG-API auth header.
            # NOT hardcoded amer / ``Authorization: skype_token`` (that 401s and
            # targets the wrong region for non-amer tenants). Mirrors send/edit.
            _enc = __import__("urllib.parse", fromlist=["quote"]).quote(chat_id, safe="")
            url = (f"{self._auth.msg_base}"
                   f"/conversations/{_enc}/messages/{message_id}")
            import requests as _req
            _headers = {"Authentication": f"skypetoken={self._auth.skype_token()}"}
            response = _req.delete(url, headers=_headers, verify=True, timeout=30)
            response.raise_for_status()
            logger.info(
                "TeamsMTK: deleted msg=%s in conv=%s (raw)",
                _log_ref(message_id),
                _log_ref(chat_id),
            )
            return {"id": message_id, "status": "deleted"}
        except Exception as e:
            logger.error("TeamsMTK: delete_message error: %s", _log_error(e))
            return {"status": "error", "error": str(e)}

    # ---- S4: Activity feed (spaces, notes, call logs, threads, saved) ----

    async def get_activity(self, kind: str, limit: int = 20, offset: int = 0) -> list:
        """List activity-stream items by kind.

        ``kind`` is one of: spaces, notes, call_logs, threads, saved.
        Uses SDK ActivityService when available.
        """
        valid_kinds = {"spaces", "notes", "call_logs", "threads", "saved"}
        if kind not in valid_kinds:
            return [{"error": f"Unknown activity kind '{kind}'. "
                     f"Valid: {', '.join(sorted(valid_kinds))}"}]
        if not _SDK_AVAILABLE or not self._auth.skype_token():
            return [{"error": "SDK or auth unavailable"}]
        try:
            adapter = _SDKAuthAdapter(self._auth)
            http = _SDKHTTPLayer(adapter, verify_ssl=True)
            service = _SDKActivity(http)
            method_map = {
                "spaces": service.list_spaces,
                "notes": service.list_notes,
                "call_logs": service.list_call_logs,
                "threads": service.list_threads,
                "saved": service.list_saved,
            }
            result = method_map[kind](limit=limit, offset=offset)
            logger.info("TeamsMTK: get_activity kind=%s → %d items", kind, len(result))
            return result
        except Exception as e:
            logger.error("TeamsMTK: get_activity error: %s", _log_error(e))
            return [{"error": str(e)}]

    # ---- S5: Call logs (via ActivityService) ----

    async def get_call_logs(self, limit: int = 20, offset: int = 0) -> list:
        """List call history. Shortcut for get_activity('call_logs')."""
        return await self.get_activity("call_logs", limit, offset)

    # ---- S10: Message forwarding ----

    async def forward_message(self, source_conv: str, message_id: str,
                              target_conv: str, allowed_targets: list = None) -> dict:
        """Forward a message from source to target conversation.

        ``allowed_targets``: optional whitelist of target conversation IDs.
        If set, forward is rejected if target_conv is not in the list.
        """
        # Whitelist check
        if allowed_targets and target_conv not in allowed_targets:
            logger.warning("TeamsMTK: forward rejected — target %s not in whitelist",
                           _log_ref(target_conv))
            return {"status": "error",
                    "error": f"Target conversation not in allowed list"}
        try:
            if _SDK_AVAILABLE and self._auth.skype_token():
                _adapter = _SDKAuthAdapter(self._auth)
                _http = _SDKHTTPLayer(_adapter, verify_ssl=True)
                _svc = _SDKMessages(_http)
                result = _svc.forward(source_conv, message_id, target_conv)
                logger.info(
                    "TeamsMTK: forwarded msg=%s %s→%s",
                    _log_ref(message_id), _log_ref(source_conv), _log_ref(target_conv),
                )
                return result
            # Raw fallback: fetch original then send as blockquote.
            # Regional MSG endpoint + MSG-API auth header; skype_token() is a
            # METHOD — call it (the old code formatted the bound method object).
            _enc = __import__("urllib.parse", fromlist=["quote"]).quote(source_conv, safe="")
            url = (f"{self._auth.msg_base}"
                   f"/conversations/{_enc}/messages")
            import requests as _req
            _headers = {"Authentication": f"skypetoken={self._auth.skype_token()}"}
            resp = _req.get(
                url,
                headers=_headers,
                params={"pageSize": 50},
                verify=True,
                timeout=30,
            )
            raw_msgs = resp.json().get("messages", [])
            original = None
            for m in raw_msgs:
                if str(m.get("id")) == str(message_id):
                    original = m
                    break
            if not original:
                return {"status": "error", "error": f"Message {message_id} not found"}
            sender = original.get("imdisplayname", "Unknown")
            content = original.get("content", "")
            fwd_html = (f'<blockquote itemtype="http://schema.skype.com/Forward">'
                        f'<p><strong>Forwarded from {sender}:</strong></p>'
                        f'{content}</blockquote>')
            return await self.send(target_conv, fwd_html)
        except Exception as e:
            logger.error("TeamsMTK: forward_message error: %s", _log_error(e))
            return {"status": "error", "error": str(e)}

    # ---- S7-3 / S9-2~3: PLATFORM_HINTS injection ----

    def get_platform_hints(self) -> str:
        """Return a text block describing this platform's capabilities.

        Injected into the agent's system prompt so it knows what it can do
        on Teams (reactions, delete, forward, search, activity, etc.).
        """
        hints = [
            "Platform: Microsoft Teams (MTK internal)",
            "Capabilities:",
            "  - send_message, edit_message, delete_message (own messages only)",
            "  - send_reaction / remove_reaction (like/heart/laugh/surprised/sad/angry)",
            "  - forward_message (with optional target whitelist)",
            "  - search_messages (content + date range)",
            "  - get_activity (spaces/notes/call_logs/threads/saved)",
            "  - get_call_logs, list_conversations",
            "  - send_image_file, send_document, send_image",
            "  - Users: _search_users, _get_schedule, _find_common_availability",
            "Mention gating: groups require @hermes unless require_mention=false",
            "Short-msg gating: ≤2 chars ignored in non-mention groups (no ?/!/mention)",
        ]
        if self._vip_config:
            targets = self._vip_config.get("notify_targets", [])
            hints.append(f"  - VIP monitor: buffered → {len(targets)} configured target(s)")
        return "\n".join(hints)

    # ---- S9-2: Enforce delete-only-own ----

    async def delete_message_safe(self, chat_id: str, message_id: str) -> dict:
        """Delete only a chat-scoped outbound or API-verified agent message."""
        if self._is_sent_message(chat_id, message_id):
            return await self.delete_message(chat_id, message_id)
        # Otherwise verify via fetch that sender is us before deleting
        try:
            msgs = self._fetch_messages(chat_id, limit=5)
            for m in (msgs or []):
                if str(m.get("id")) == str(message_id):
                    _props = m.get("properties", {}) or {}
                    if isinstance(_props, str):
                        import json; _props = json.loads(_props)
                    _sender = _props.get("hermes_sender")
                    if _sender in ("agent", "bot"):
                        return await self.delete_message(chat_id, message_id)
                    return {"status": "error", "error": "Cannot delete — not your message"}
            return {"status": "error", "error": f"Message {message_id} not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ---- S1-5: PKB instant-landing hook ----

    async def on_message_processed(self, chat_id: str, msg: dict, response: str = None) -> None:
        """Hook called after a message is fully processed by the agent.

        S1-5: Optionally land the conversation turn into PKB.
        Controlled by gateway.teams_mtk.pkb_instant_landing config.
        """
        _cfg = self._group_config(chat_id) if "@thread" in chat_id else {}
        if not _cfg.get("pkb_instant_landing", False):
            return
        # If PKB landing is enabled, write the turn to PKB
        try:
            _text = msg.get("content", "") or ""
            if _strip_teams_html is not None:
                _text, _ = _strip_teams_html(_text)
            _sender = msg.get("imdisplayname") or "User"
            _ts = msg.get("composetime", "") or msg.get("originalarrivaltime", "")
            _entry = f"[{_ts}] {_sender}: {_text.strip()}"
            if response:
                _entry += f"\n[{_ts}] Hermes: {response[:500]}"
            # Append to PKB file
            _pkb_dir = _cfg.get("pkb_landing_dir", "")
            if _pkb_dir:
                import os
                os.makedirs(_pkb_dir, exist_ok=True)
                _fname = _log_ref(chat_id).replace(":", "_") + ".md"
                with open(os.path.join(_pkb_dir, _fname), "a", encoding="utf-8") as f:
                    f.write(_entry + "\n\n")
                logger.debug("TeamsMTK: PKB landed msg to %s", _fname)
        except Exception as e:
            logger.warning("TeamsMTK: PKB landing error: %s", _log_error(e))

    # ---- S2-4: Cross-conversation global search ----

    async def search_all_conversations(self, query: str, limit: int = 10) -> list:
        """Search messages across all monitored conversations.

        S2-4: Iterates _conv_ids and searches each, merging results.
        """
        all_results = []
        for cid in self._conv_ids:
            try:
                results = self._search_messages(cid, query, limit=limit)
                for r in (results or []):
                    r["_source_conv"] = cid
                all_results.extend(results or [])
            except Exception as e:
                logger.debug("TeamsMTK: search conv=%s error: %s", _log_ref(cid), _log_error(e))
        # Sort by relevance (if timestamp available)
        all_results.sort(key=lambda r: r.get("originalarrivaltime", ""), reverse=True)
        return all_results[:limit]

    # ---- G15: Whitelist visibility ----

    def list_whitelisted_groups(self) -> list:
        """List all group conversation IDs in the TeamsMTK whitelist.

        G15: Lets the agent (and user) query which groups are whitelisted
        without reading config.yaml directly.
        """
        try:
            from hermes_cli.config import load_config_readonly
            groups = (
                load_config_readonly()
                .get("gateway", {})
                .get("teams_mtk", {})
                .get("groups", {})
            )
            if not isinstance(groups, dict):
                return []
            result = []
            for cid, cfg in groups.items():
                if isinstance(cfg, dict):
                    result.append({
                        "chat_id": cid,
                        "require_mention": cfg.get("require_mention", True),
                        "label": cfg.get("label", ""),
                    })
                else:
                    result.append({"chat_id": cid, "require_mention": True, "label": ""})
            return result
        except Exception:
            return []

    # ---- G13-A: Read-only conversation lookup (Phase A) ----

    def find_conversation(self, name: str) -> list:
        """Search known conversations by display name. Read-only (G13 Phase A).

        Only searches conversations Hermes already has in its conversation list.
        This is naturally bounded by the whitelist — if Hermes hasn't talked
        to someone, this won't find them.
        """
        if not _SDK_AVAILABLE or not self._auth.skype_token():
            return []
        try:
            _adapter = _SDKAuthAdapter(self._auth)
            _http = _SDKHTTPLayer(_adapter, verify_ssl=True)
            _msg_svc = _SDKMessages(_http)
            _svc = _SDKConvs(_http, _msg_svc)
            results = _svc.find(name)
            return results if isinstance(results, list) else []
        except Exception:
            return []

    # NOTE 2026-07-13: list_conversations()/_find_conv_by_display_name()
    # were previously ALSO defined here (duplicate of the L1874/L1944
    # definitions above). Python lets a later same-name method silently
    # shadow an earlier one in the same class body, so THIS duplicate
    # (whose SDK path called `_SDKConvs(_http)` — missing the required
    # `messages` arg) was the version that actually ran, while the correct
    # L1874 definition sat dead. Every SDK-path call raised TypeError and
    # silently fell back to raw HTTP — masked because the raw-HTTP
    # fallback also succeeds, so the bug was invisible until real E2E
    # checked which code path actually fired. Removed the duplicate;
    # the L1874/L1944 definitions are now the only implementation.

    # ---- G13-B.3 stub: Proactive chat creation (blocked: Chat.Create scope) ----

    async def create_chat(self, topic: str, members: list) -> dict:
        """Create a new group chat. STUB — requires Chat.Create Graph scope.

        Currently blocked: IT has not granted the Chat.Create application
        permission. When scope is approved, replace this stub with:
          Graph POST /chats {chatType: "group", topic, members}
        """
        return {"status": "error",
                "error": "Chat.Create scope not authorized. "
                         "Request IT to add Chat.Create to the app registration."}

    # ---- G14-2.1 stub: Persona configuration (blocked: P7 incomplete) ----

    def get_persona_config(self) -> dict:
        """Return the current persona configuration. STUB — P7 incomplete.

        When P7 Persona is completed, this will return the active persona
        profile (name, tone, style, system_prompt_delta).
        """
        return {"status": "stub", "error": "P7 Persona not yet available",
                "persona": None}

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
                verify=True,
                timeout=15,
            )
            resp.raise_for_status()
            sess.close()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
            logger.info(
                "TeamsMTK: model picker step 1 (providers) sent (id=%s)",
                _log_ref(msg_id),
            )
        except Exception as e:
            logger.error("TeamsMTK: model picker step 1 send failed: %s", _log_error(e))
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
            "allowed_user_id": (metadata or {}).get(
                "_authorized_picker_user_id"
            ),
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
                verify=True,
                timeout=15,
            )
            resp.raise_for_status()
            sess.close()
            data = resp.json()
            msg_id = data.get("id") or data.get("OriginalArrivalTime")
            if msg_id:
                self._remember_sent_message(chat_id, msg_id)
            logger.info(
                "TeamsMTK: model picker step 2 (models for %s) sent (id=%s)",
                _log_ref(chosen_name), _log_ref(msg_id),
            )
        except Exception as e:
            logger.error("TeamsMTK: model picker step 2 send failed: %s", _log_error(e))
            return

        # Update picker state — step 2: waiting for model selection
        self._model_picker_states[chat_id] = {
            "step": "model",
            "entries": model_entries,  # list of (prov_slug, model_id, prov_name)
            "on_model_selected": picker["on_model_selected"],
            "current_model": picker.get("current_model"),
            "current_provider": picker.get("current_provider"),
            "allowed_user_id": picker.get("allowed_user_id"),
        }
    def _fetch_messages(self, conv_id: str = None, limit: Optional[int] = None) -> List[dict]:
        """Fetch messages from a conversation (sync, called from thread).

        S1-1/S1-2: Full-history fetch with backwardLink pagination.

        Args:
            conv_id: Conversation ID.  Defaults to ``self._conv_id``.
            limit:   Maximum messages to return.  ``None`` (default) = all
                     messages via backwardLink pagination (no cap).
                     Pass an integer for a bounded single-page fetch.

        When SDK is available, delegates to:
          - ``MessagesService.get()``  (limit=None → full history via pagination)
          - ``MessagesService.get_page()``  (limit=N → single page, poll-loop use)

        Falls back to raw ``requests`` when SDK is not importable.
        """
        if conv_id is None:
            conv_id = self._conv_id

        self._auth._inject_truststore()
        import time as _t
        _t0 = _t.time()

        try:
            if _SDK_AVAILABLE:
                return self._fetch_via_sdk(conv_id, limit, _t0)
            return self._fetch_via_raw(conv_id, limit if limit is not None else 30, _t0)
        finally:
            logger.info("TeamsMTK: _fetch_messages done in %.1fs", _t.time() - _t0)

    def _fetch_via_sdk(self, conv_id: str, limit: Optional[int], _t0: float) -> List[dict]:
        """Fetch messages using SDK MessagesService (normalised, with attachments).

        S1-1: When limit is None, uses MessagesService.get() which follows
        backwardLink pagination to retrieve the full history.  When limit is
        an integer, uses get_page() for a single-page bounded fetch (poll loop).
        """
        adapter = _SDKAuthAdapter(self._auth)
        http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
        svc = _SDKMessages(http_layer)
        try:
            if limit is None:
                # Full-history fetch via backwardLink pagination (S1-1)
                # get() returns newest-first; no reversal needed here because
                # we reverse the final list at the end regardless.
                norm_msgs = svc.get(conv_id)
                logger.debug(
                    "TeamsMTK: SDK full-history fetch: %d messages for conv=%s",
                    len(norm_msgs), _log_ref(conv_id),
                )
            else:
                # Bounded single-page fetch (poll loop, S1-2 unchanged path)
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
            logger.warning("TeamsMTK: SDK fetch failed (%s), falling back to raw", _log_error(e))
            return self._fetch_via_raw(conv_id, limit if limit is not None else 30, _t0)

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
                    verify=True,
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
            logger.warning(
                "TeamsMTK: _fetch_messages ConnectionError after %.1fs",
                time.time() - _t0,
            )
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

    def _fetch_messages_by_date(
        self, conv_id: str, date_from: str = None, date_to: str = None, limit: int = 200
    ) -> List[dict]:
        """S1-3: Fetch messages in a date range via SDK get_by_date().

        Args:
            conv_id:    Conversation ID.
            date_from:  Start date inclusive (YYYY-MM-DD), or None for no lower bound.
            date_to:    End date inclusive (YYYY-MM-DD), or None for no upper bound.
            limit:      Max messages to return (default 200).

        Returns oldest-first list of message dicts (same format as _fetch_messages).
        Raises RuntimeError if SDK is not available.
        """
        if not _SDK_AVAILABLE:
            raise RuntimeError(
                "_fetch_messages_by_date requires teams_skype_sdk — SDK not available"
            )
        self._auth._inject_truststore()
        adapter = _SDKAuthAdapter(self._auth)
        http_layer = _SDKHTTPLayer(adapter, verify_ssl=True)
        svc = _SDKMessages(http_layer)

        norm_msgs = svc.get_by_date(
            conv_id, date_from=date_from, date_to=date_to, limit=limit
        )
        logger.debug(
            "TeamsMTK: _fetch_messages_by_date: %d messages for conv=%s [%s → %s]",
            len(norm_msgs), _log_ref(conv_id), date_from, date_to,
        )
        # Back-fill raw-compatible fields (same as _fetch_via_sdk)
        for m in norm_msgs:
            m.setdefault("imdisplayname", m.get("sender", ""))
            m.setdefault("messagetype", m.get("type", "RichText/Html"))
            m.setdefault("properties", m.get("_raw_properties") or {})
        # SDK returns newest-first; return oldest-first for consistency
        norm_msgs.reverse()
        return norm_msgs

    async def _poll_loop(self) -> None:
        """Poll all monitored conversations at the configured interval.

        On consecutive errors, backs off up to 5× the normal interval to avoid
        hammering a downed proxy. Resets on first successful fetch.
        """
        import concurrent.futures
        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(len(self._conv_ids), 1))
        _backoff = 1  # multiplier for the configured poll interval on errors
        _ws_stable_ticks = 0  # consecutive successful ticks with WS healthy
        _ws_stats = {"healthy_ticks": 0, "unhealthy_ticks": 0, "ws_reconnects": 0,
                     "poll_interval_changes": 0}  # WS-8: stability metrics

        while self._running:
            try:
                # WS-7: Adaptive poll interval — when WS listener is healthy
                # and stable, poll less frequently (15s) since WS pushes
                # events in real-time. When WS is down, revert to 2s.
                _active_interval = self._poll_interval
                if self._ws_listener and self._ws_listener.is_healthy():
                    _ws_stable_ticks += 1
                    _ws_stats["healthy_ticks"] += 1
                    if _ws_stable_ticks >= 5:  # 5 consecutive healthy ticks → relax
                        _active_interval = 15  # seconds
                        if _ws_stable_ticks == 5:
                            _ws_stats["poll_interval_changes"] += 1
                    if _ws_stable_ticks >= 20:  # WS-9: very stable → further relax
                        _active_interval = 30  # seconds
                        if _ws_stable_ticks == 20:
                            _ws_stats["poll_interval_changes"] += 1
                            logger.info("TeamsMTK: WS very stable (20 ticks) → poll interval 30s")
                else:
                    _ws_stable_ticks = 0
                    _ws_stats["unhealthy_ticks"] += 1
                    # Track reconnects from listener
                    if self._ws_listener and hasattr(self._ws_listener, '_reconnect_count'):
                        _ws_stats["ws_reconnects"] = self._ws_listener._reconnect_count

                logger.info("TeamsMTK: poll tick (backoff=%dx, interval=%ds, ws_stable=%d, convs=%d)",
                            _backoff, _active_interval, _ws_stable_ticks, len(self._conv_ids))
                # Fetch all conversations in parallel so N convs take ~1
                # round-trip instead of N×round-trip.
                fetch_tasks = {
                    _conv_id: loop.run_in_executor(
                        # S1-2: Poll uses bounded fetch (limit=30) for efficiency.
                        # Full-history (limit=None) is reserved for explicit
                        # search/history queries, not every poll tick.
                        # _process_new_messages skips msgs <= last_message_id,
                        # so 30 recent messages is more than enough.
                        executor, lambda _c=_conv_id: self._fetch_messages(_c, limit=30)
                    )
                    for _conv_id in self._conv_ids
                }
                fetch_results = await asyncio.gather(*fetch_tasks.values())
                for _conv_id, msgs in zip(fetch_tasks, fetch_results):
                    logger.info(
                        "TeamsMTK: poll conv=%s got %d messages",
                        _log_ref(_conv_id),
                        len(msgs) if msgs else 0,
                    )
                    await self._process_new_messages(_conv_id, msgs)
                _backoff = 1  # reset backoff on success
            except asyncio.CancelledError:
                break
            except Exception as e:
                _backoff = min(_backoff * 2, 5)
                logger.warning("TeamsMTK: poll error (backoff=%dx): %s", _backoff, _log_error(e))

            try:
                await asyncio.sleep(_active_interval * _backoff)
            except asyncio.CancelledError:
                break

        executor.shutdown(wait=False)

    async def _download_attachment(self, url: str, kind: str, filename: str) -> Optional[str]:
        """Download a Teams attachment and cache it locally.

        Only HTTPS URLs that pass the shared SSRF guard are fetched. Teams
        credentials are attached solely to boundary-matched Microsoft hosts;
        unknown public hosts are fetched anonymously. Redirects are followed
        manually so every target is revalidated and its auth is recomputed.
        """
        from urllib.parse import urljoin, urlparse

        import aiohttp
        from gateway.platforms.base import (
            cache_document_from_bytes,
            cache_image_from_bytes,
            get_inbound_media_max_bytes,
            validate_inbound_media_size,
        )
        from tools.url_safety import async_is_safe_url

        def _headers_for(candidate_url: str) -> Dict[str, str]:
            hostname = (urlparse(candidate_url).hostname or "").lower().rstrip(".")
            auth_kind = _attachment_auth_kind(hostname)
            if auth_kind == "skype_authorization":
                return {"Authorization": f"skype_token {self._auth.skype_token()}"}
            if auth_kind == "skype_authentication":
                return {"Authentication": f"skypetoken={self._auth.skype_token()}"}
            if auth_kind == "azure_bearer":
                return {"Authorization": f"Bearer {self._auth.access_token()}"}
            return {}

        current_url = str(url or "").strip()
        max_bytes = get_inbound_media_max_bytes()
        data: Optional[bytes] = None
        try:
            initial = urlparse(current_url)
            if (
                initial.scheme.lower() != "https"
                or not initial.hostname
                or initial.username is not None
                or initial.password is not None
                or not await async_is_safe_url(current_url)
            ):
                logger.warning(
                    "TeamsMTK: blocked unsafe attachment url=%s",
                    _log_ref(current_url),
                )
                return None

            async with aiohttp.ClientSession() as sess:
                for redirect_count in range(_ATTACHMENT_REDIRECT_LIMIT + 1):
                    if redirect_count:
                        parsed = urlparse(current_url)
                        redirect_is_safe = (
                            parsed.scheme.lower() == "https"
                            and bool(parsed.hostname)
                            and parsed.username is None
                            and parsed.password is None
                            and await async_is_safe_url(current_url)
                        )
                    else:
                        redirect_is_safe = True
                    if not redirect_is_safe:
                        logger.warning(
                            "TeamsMTK: blocked unsafe attachment url=%s",
                            _log_ref(current_url),
                        )
                        return None

                    async with sess.get(
                        current_url,
                        headers=_headers_for(current_url),
                        timeout=aiohttp.ClientTimeout(total=30),
                        ssl=True,
                        allow_redirects=False,
                    ) as resp:
                        if 300 <= resp.status < 400:
                            location = resp.headers.get("Location") or resp.headers.get("location")
                            if not location or redirect_count >= _ATTACHMENT_REDIRECT_LIMIT:
                                logger.warning(
                                    "TeamsMTK: attachment redirect rejected status=%d url=%s",
                                    resp.status,
                                    _log_ref(current_url),
                                )
                                return None
                            current_url = urljoin(current_url, location)
                            continue

                        if resp.status != 200:
                            logger.warning(
                                "TeamsMTK: attachment download failed status=%d url=%s",
                                resp.status,
                                _log_ref(current_url),
                            )
                            return None

                        content_length = resp.headers.get("Content-Length") or resp.headers.get("content-length")
                        if content_length:
                            try:
                                declared_size = int(content_length)
                            except (TypeError, ValueError):
                                logger.debug("TeamsMTK: ignoring invalid attachment Content-Length")
                            else:
                                validate_inbound_media_size(
                                    declared_size,
                                    media_type=kind or "attachment",
                                    max_bytes=max_bytes,
                                )

                        chunks: List[bytes] = []
                        total = 0
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            total += len(chunk)
                            validate_inbound_media_size(
                                total,
                                media_type=kind or "attachment",
                                max_bytes=max_bytes,
                            )
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        break
        except Exception as exc:
            logger.warning(
                "TeamsMTK: attachment download error: %s url=%s",
                _log_error(exc),
                _log_ref(current_url),
            )
            return None

        if data is None:
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
                local = cache_image_from_bytes(data, _ext)
            else:
                if not filename:
                    _parts = url.rsplit("/", 1)
                    filename = _parts[-1].split("?", 1)[0] if len(_parts) > 1 else "document.bin"
                local = cache_document_from_bytes(data, filename)
            logger.info(
                "TeamsMTK: cached %d bytes from %s -> %s",
                len(data), _log_ref(url), local,
            )
            return local
        except Exception as exc:
            logger.warning("TeamsMTK: attachment cache error: %s", _log_error(exc))
            return None

    async def _process_new_messages(self, conv_id: str, messages: List[dict]) -> None:
        """Serialize and dispatch messages newer than the conversation cursor."""
        if not messages or not self._message_handler:
            return
        lock = self._message_process_locks.setdefault(conv_id, asyncio.Lock())
        async with lock:
            await self._process_new_messages_locked(conv_id, messages)

    async def _process_new_messages_locked(
        self,
        conv_id: str,
        messages: List[dict],
    ) -> None:
        """Dispatch one conversation while holding its cursor lock."""
        if not messages or not self._message_handler:
            return

        _last_id = self._last_message_ids.get(conv_id)
        _last_key = _message_id_key(_last_id) if _last_id is not None else None
        new_by_id = {}
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue
            if _last_key is None or _message_id_key(msg_id) > _last_key:
                new_by_id.setdefault(str(msg_id), msg)
            else:
                logger.debug(
                    "TeamsMTK: skipping old msg id=%s (<= last=%s)",
                    _log_ref(msg_id),
                    _log_ref(_last_id),
                )

        new_messages = sorted(
            new_by_id.values(),
            key=lambda msg: _message_id_key(msg["id"]),
        )

        if new_messages:
            logger.info("TeamsMTK: %d new messages to process", len(new_messages))

        for msg in new_messages:
            msg_id = msg.get("id", "")
            msg_type = msg.get("messagetype", "")
            content = msg.get("content", "")
            sender = msg.get("imdisplayname") or msg.get("fromDisplayNameInToken") or "Teams User"

            logger.info(
                "TeamsMTK: inspecting msg id=%s type=%s conv=%s last_sent=%s content_present=%s",
                _log_ref(msg_id), msg_type, _log_ref(conv_id),
                _log_ref(self._last_sent_message_id), bool(content),
            )

            # ---- G14 VIP interception ----
            # If VIP monitor is enabled and the sender OID is in the VIP list,
            # buffer the message instead of dispatching to the agent.
            _from_url = msg.get("from", "")
            _sender_oid = ""
            if "8:orgid:" in _from_url:
                _sender_oid = _from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")
            if self._vip_config and _sender_oid:
                _vip_buf = self._vip_buffers.get(conv_id)
                if _vip_buf is None:
                    _vip_buf = _VIPBuffer(
                        conv_id,
                        oids=self._vip_config.get("oids", []),
                        notify_targets=self._vip_config.get("notify_targets", []),
                        buffer_timeout_seconds=self._vip_config.get("buffer_timeout_seconds", 60),
                        on_stale=lambda _cid=conv_id: self._flush_vip_buffer(_cid),
                    )
                    self._vip_buffers[conv_id] = _vip_buf
                if _vip_buf.is_vip(_sender_oid):
                    _action = _vip_buf.add(msg)
                    self._last_message_ids[conv_id] = msg_id
                    logger.info(
                        "TeamsMTK: VIP msg id=%s from oid=%s → %s (buf=%d)",
                        _log_ref(msg_id), _redact_oid(_sender_oid), _action, len(_vip_buf._messages),
                    )
                    if _action == "immediate":
                        await self._flush_vip_buffer(conv_id)
                    continue

            # Skip system messages
            if msg_type in ("ThreadActivity/MemberJoined", "ThreadActivity/TopicUpdate"):
                self._last_message_ids[conv_id] = msg_id
                continue

            # Skip empty messages
            if not content:
                self._last_message_ids[conv_id] = msg_id
                continue

            # Echo-loop guard: in a self-chat (48:notes), every message can
            # come from the same OID. Ownership therefore requires one of two
            # trusted signals:
            #   1. properties.hermes_sender in ("agent", "bot")  (tag on send)
            #      Gateway sends "agent"; SDK-normalized messages carry "bot"
            #   2. (conversation, message ID) exists in the outbound registry
            # Presentation HTML is not proof: users can quote or forward it.
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
            if self._is_sent_message(conv_id, msg_id):
                is_own = True
            if is_own:
                logger.info("TeamsMTK: skipping own sent message id=%s", _log_ref(msg_id))
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
                    "TeamsMTK: msg id=%s has %d attachment(s) (kinds=%s)",
                    _log_ref(msg_id), len(_att_urls), sorted(set(_att_kinds)),
                )

            # HTML stripping: use SDK strip_teams_html when available
            # (handles <at>, <blockquote>, <img> emoji, <file>, <a> truncated URLs)
            # Falls back to regex for environments where SDK is not on sys.path.
            text, _extra_imgs = _clean_message_content(content)
            # Merge any additional inline images from SDK extraction
            if _extra_imgs:
                for _ei in _extra_imgs:
                    _eurl = _ei.get("src", "")
                    if _eurl and _eurl not in _att_urls:
                        _att_urls.append(_eurl)
                        _att_names.append(_ei.get("alt", ""))
                        _att_kinds.append(_ei.get("kind", "image"))
            # For messages with only attachments and no text, keep a placeholder
            # so the message isn't discarded as "empty".  Also treat pure
            # markdown image links (from SDK strip_teams_html) as attach-only.
            if not text and _att_urls:
                text = "[attachment]"
            elif text and _att_urls and not re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text).strip():
                text = "[attachment]"
            if not text:
                self._last_message_ids[conv_id] = msg_id
                continue

            # Control commands (/stop, /new, /reset, /approve, /deny, /status, etc.)
            # MUST bypass mention gating — a user typing "/stop" in a group
            # without @hermes should still be able to interrupt the agent.
            # Follows the same bypass list as base adapter's
            # should_bypass_active_session().
            _cmd_name = None
            if text.startswith("/") and len(text.split()) <= 2:
                _raw_cmd = text.split()[0][1:].lower()
                if "@" in _raw_cmd:
                    _raw_cmd = _raw_cmd.split("@", 1)[0]
                _cmd_name = _raw_cmd

            from hermes_cli.commands import should_bypass_active_session
            _is_control_cmd = _cmd_name and should_bypass_active_session(_cmd_name)

            # Mention gating: in groups, only respond when @hermes is present.
            # Resolution order: gateway.teams_mtk.groups.<id>.require_mention
            # (config.yaml, set via `hermes teams-mtk group add/set`) → the
            # legacy MTK_TEAMS_NO_MENTION_CONVS env var (back-compat) →
            # self.require_mention (global TEAMS_MTK_REQUIRE_MENTION default).
            is_group = "@thread" in conv_id
            _group_cfg = self._group_config(conv_id) if is_group else {}
            effective_require_mention = self._require_mention_for_conv(
                conv_id,
                _group_cfg,
            )
            if is_group and effective_require_mention and not _is_control_cmd:
                if self._MENTION_TAG.lower() not in text.lower():
                    logger.debug(
                        "TeamsMTK: ignoring group message id=%s (require_mention=true, no %s)",
                        _log_ref(msg_id), self._MENTION_TAG,
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
            # Control commands bypass keyword blocking (same as mention gating).
            if is_group and not _is_control_cmd:
                _blocked_patterns = self._group_blocked_keyword_patterns(conv_id)
                _hit = self._find_blocked_keyword(text, _blocked_patterns)
                if _hit:
                    logger.warning(
                        "TeamsMTK: blocked inbound message id=%s in conv=%s (pattern ref=%s)",
                        _log_ref(msg_id), _log_ref(conv_id), _log_ref(_hit),
                    )
                    self._last_message_ids[conv_id] = msg_id
                    try:
                        await self.send(conv_id, self._BLOCKED_KEYWORD_NOTICE)
                    except Exception as e:
                        logger.error("TeamsMTK: failed to send blocked-keyword notice: %s", _log_error(e))
                    continue

            logger.info(
                "TeamsMTK: new message id=%s from sender=%s (chars=%d)",
                _log_ref(msg_id), _log_ref(sender), len(text),
            )

            # ---- C-5 Short-message gating (BUG-5) ----
            # In groups where require_mention=false, ultra-short casual
            # messages (e.g. 「好」「OK」「嗯」) waste agent tokens.
            # Ignore ≤2 chars unless they contain ?？！! or @hermes.
            # Per-group config `short_message_ignore: false` disables.
            if is_group and not effective_require_mention and not _is_control_cmd:
                _short_ignore = _group_cfg.get("short_message_ignore", True)
                if _short_ignore and len(text.strip()) <= 2:
                    _has_punct = any(c in text for c in "?？！!？")
                    _has_mention = self._MENTION_TAG.lower() in text.lower()
                    if not _has_punct and not _has_mention:
                        logger.debug(
                            "TeamsMTK: ignoring short message id=%s (%d chars, no ?/!/mention)",
                            _log_ref(msg_id), len(text.strip()),
                        )
                        self._last_message_ids[conv_id] = msg_id
                        continue

            # Resolve the immutable sender id before any adapter-local action.
            # Model-picker replies never reach GatewayRunner authorization, so
            # they must remain bound to the user whose authorized /model command
            # created the picker.
            _from_url = msg.get("from", "")
            user_id = sender  # fallback to display name
            if "8:orgid:" in _from_url:
                user_id = _from_url.rsplit("8:orgid:", 1)[-1].rstrip("/")

            # ---- Model picker interception (two-step) ----
            # Per-conversation picker state so multiple conversations
            # can each have an active picker independently.
            _picker = self._model_picker_states.get(conv_id)
            _picker_user_id = (_picker or {}).get("allowed_user_id")
            _picker_owner_matches = (
                not _picker_user_id
                or str(_picker_user_id).casefold() == str(user_id).casefold()
            )
            if _picker is not None and _picker_owner_matches and len(text) <= 40:
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
                                choice, prov_name, _log_ref(conv_id),
                            )
                            # Don't clear state — transition to step 2
                            # (sub-picker will update it)
                            try:
                                await self._send_model_sub_picker(
                                    conv_id, choice,
                                )
                            except Exception as e:
                                logger.error(
                                    "TeamsMTK: model sub-picker send error: %s", _log_error(e)
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
                                choice, prov_slug, model_id, _log_ref(conv_id),
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
                                    logger.error("TeamsMTK: model picker callback error: %s", _log_error(e))
                                    await self.send(conv_id, f"⚠ Model switch failed: {e}")
                            self._last_message_ids[conv_id] = msg_id
                            continue

            try:
                from gateway.platforms.base import MessageEvent, MessageType
                from gateway.config import Platform

                from gateway.session import SessionSource

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
                logger.error(
                    "TeamsMTK: handler error for message %s: %s",
                    _log_ref(msg_id),
                    _log_error(e),
                )
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
