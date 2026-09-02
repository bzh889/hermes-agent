"""[API] Core HTTP infrastructure shared by all Service classes.

Contains constructor, HTTP layer, authentication helpers, data transformation
utilities, and content processing pipeline.
"""

import base64
import json
import re
import urllib.parse
from datetime import datetime
from typing import Optional

import markdown
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert

from teams_skype_sdk.auth import TeamsAuth
from teams_skype_sdk.config import VERIFY_SSL, DEFAULT_TIMEOUT
from teams_skype_sdk.utils import retry_with_backoff

from ._constants import CHATSVC_BASE, MSG_BASE, AMS_BASE_URL


class HTTPLayer:
    """Core HTTP infrastructure — constructor, HTTP, helpers."""

    def __init__(self, auth: TeamsAuth, verify_ssl: bool = VERIFY_SSL):
        self.auth = auth
        self.verify_ssl = verify_ssl
        self._my_oid: Optional[str] = None
        self._session = requests.Session()

    # ---- Identity -----------------------------------------------------------

    def _get_my_oid(self) -> str:
        """Get current user's OID from access token."""
        if self._my_oid:
            return self._my_oid

        access_token = self.auth.get_access_token()
        parts = access_token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            payload += "=" * (4 - len(payload) % 4)
            try:
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                self._my_oid = decoded.get("oid", "")
            except Exception:
                self._my_oid = ""

        return self._my_oid or ""

    def _get_other_person_oid(self, conversation_id: str) -> Optional[str]:
        """Extract the other person's OID from a one-on-one conversation ID."""
        match = re.search(r"19:([a-f0-9-]+)_([a-f0-9-]+)@", conversation_id)
        if not match:
            return None

        guid1, guid2 = match.groups()
        my_oid = self._get_my_oid()

        if guid1 == my_oid:
            return guid2
        elif guid2 == my_oid:
            return guid1
        else:
            return guid1  # fallback

    # ---- HTTP ---------------------------------------------------------------

    def _get_headers(self) -> dict:
        """Get headers with valid Skype token."""
        skype_token = self.auth.get_skype_token()
        return {
            "Authentication": f"skypetoken={skype_token}",
            "Content-Type": "application/json",
        }

    @retry_with_backoff(max_retries=3)
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Centralized HTTP request with retry, timeout, and session pooling."""
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        kwargs.setdefault("verify", self.verify_ssl)
        if "headers" not in kwargs:
            kwargs["headers"] = self._get_headers()

        response = self._session.request(method, url, **kwargs)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            body = response.text[:500] if response.text else "(empty)"
            raise requests.HTTPError(
                f"{e} | Response body: {body}",
                response=response,
            ) from e
        return response

    # ---- Data helpers -------------------------------------------------------

    def _format_timestamp(self, timestamp: str) -> str:
        """Format ISO timestamp to readable format."""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            return timestamp or "Unknown"

    def _extract_mri_from_url(self, url_or_mri: str) -> str:
        """Extract MRI from URL or return as-is if already MRI."""
        if not url_or_mri:
            return ""

        if url_or_mri.startswith("http"):
            parts = url_or_mri.split("/")
            for part in reversed(parts):
                if part.startswith("8:") or part.startswith("28:"):
                    return part
            return ""

        return url_or_mri

    @staticmethod
    def _is_emoji_image(img_tag) -> bool:
        """Determine if an <img> tag is an emoji (vs a real image)."""
        itemtype = img_tag.get("itemtype", "")
        if "Emoji" in itemtype:
            return True

        src = img_tag.get("src", "")
        if "statics.teams.cdn" in src or "/emoticons/" in src:
            return True

        return False

    def _process_message_content(self, content: str) -> tuple[str, list[dict]]:
        """Preprocess HTML: convert to markdown and extract inline images.

        Delegates to module-level strip_teams_html() — see its docstring
        for details on what is handled.
        """
        return strip_teams_html(content)

    def _extract_message_attachments(self, msg: dict, content: str = "") -> list[dict]:
        """Extract all attachments from a raw message dict.

        Sources (4 layers, matching gateway teams_mtk.py L2199-2250):
        1. <img src> from HTML content — inline images
        2. <file src name> from HTML content — file shares (Skype format)
        3. properties.files[] from message JSON — file shares (PDF/DOCX etc.)
        4. attachments[] from message JSON — rare but valid

        Returns list of dicts: {"url": str, "name": str, "kind": "image"|"file"}
        """
        attachments = []
        seen_urls = set()

        def _add(url: str, name: str, kind: str):
            if url and url.startswith("http") and url not in seen_urls:
                seen_urls.add(url)
                attachments.append({"url": url, "name": name, "kind": kind})

        # Layer 1 & 2: HTML-based extraction
        if content:
            for m in re.finditer(r'<img\s[^>]*?src="([^"]+)"', content, re.IGNORECASE):
                _add(m.group(1), "", "image")
            for m in re.finditer(
                r'<file\s[^>]*?src="([^"]+)"[^>]*?(?:name="([^"]*)")?',
                content, re.IGNORECASE,
            ):
                _add(m.group(1), (m.group(2) or "").strip(), "file")

        # Layer 3: properties.files array
        props = msg.get("properties", {})
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if isinstance(props, dict):
            files = props.get("files")
            if isinstance(files, list):
                for fi in files:
                    if isinstance(fi, dict):
                        furl = fi.get("contentUrl") or fi.get("contenturl") or ""
                        fname = fi.get("name") or fi.get("fileName") or ""
                        _add(furl, fname, "file")

        # Layer 4: top-level attachments array
        attach_arr = msg.get("attachments")
        if isinstance(attach_arr, list):
            for att in attach_arr:
                if isinstance(att, dict):
                    aurl = att.get("contentUrl") or att.get("contenturl") or ""
                    aname = att.get("name") or ""
                    act = (att.get("contentType") or "").lower()
                    if aurl:
                        _add(aurl, aname, "image" if act.startswith("image/") else "file")

        return attachments

    def _extract_text_content(self, content: str) -> str:
        """Convert HTML message content to readable markdown."""
        text, _ = self._process_message_content(content)
        return text

    # ---- Content conversion -------------------------------------------------

    def _markdown_to_teams_html(self, content: str) -> str:
        """Convert markdown content to Teams-compatible HTML."""
        if re.search(
            r'<(b|i|a|br|h[1-6]|ul|ol|li|pre|code|strong|em)\b', content
        ):
            return content.replace('\n', '<br>')

        html = markdown.markdown(
            content,
            extensions=['fenced_code', 'tables', 'nl2br', 'md_in_html'],
        )
        return html

    # ---- Auth-aware download -------------------------------------------------

    def download_with_auth(self, url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
        """Download a URL using auth headers appropriate for its domain.

        Auth strategy by domain:
        - api.asm.skype.com → Authorization: skype_token ***
        - teams.microsoft.com / skype.com → Authentication: skypetoken={token}
        - sharepoint.com / onedrive.com → Authorization: Bearer ***
          (fallback: Graph /shares API if Bearer 401s)
        - other → Authorization: Bearer ***

        Args:
            url: The URL to download
            timeout: Request timeout in seconds

        Returns:
            Response content as bytes
        """
        from teams_skype_sdk.config import DEFAULT_TIMEOUT as _DT
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()

        if "api.asm.skype.com" in netloc:
            skype_token = self.auth.get_skype_token()
            headers = {"Authorization": f"skype_token {skype_token}"}
        elif "teams.microsoft.com" in netloc or "skype.com" in netloc:
            headers = self._get_headers()
        else:
            access_token = self.auth.get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}

        response = self._session.get(
            url, headers=headers,
            verify=self.verify_ssl, timeout=timeout,
        )

        # SharePoint/OneDrive file paths 401 against the regular access_token —
        # they need a resource-scoped token. Retry via Microsoft Graph /shares
        # API using a Graph-audience token (which our refresh_token is
        # provisioned for: Sites.FullControl.All observed).
        if (response.status_code == 401
                and ("sharepoint.com" in netloc or "1drv.ms" in netloc
                     or "sharepoint" in netloc)):
            resp = self.auth.exchange_for_scope(
                "https://graph.microsoft.com/.default offline_access")
            _at = resp.get("access_token", "")
            _b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
            _encoded = f"u!{_b64}"
            _graph_url = f"https://graph.microsoft.com/v1.0/shares/{_encoded}/driveItem/content"
            r = self._session.get(
                _graph_url, headers={"Authorization": f"Bearer {_at}"},
                verify=self.verify_ssl, timeout=timeout, allow_redirects=True,
            )
            r.raise_for_status()
            return r.content

        response.raise_for_status()
        return response.content


# ---------------------------------------------------------------------------
# Module-level pure functions (no self, no auth) for downstream consumers
# like the Hermes gateway adapter.  These extract the core logic from the
# instance methods above so they can be called without constructing an
# HTTPLayer / TeamsAuth stack.
# ---------------------------------------------------------------------------

def _is_emoji_img(img_tag) -> bool:
    """Determine if a BeautifulSoup <img> tag is a Teams emoji."""
    itemtype = img_tag.get("itemtype", "")
    if "Emoji" in itemtype:
        return True
    src = img_tag.get("src", "")
    return "statics.teams.cdn" in src or "/emoticons/" in src


def strip_teams_html(content: str) -> tuple[str, list[dict]]:
    """Pure-function version of HTTPLayer._process_message_content.

    Converts Teams HTML to clean markdown text and extracts inline images.
    Does NOT require an HTTPLayer instance — safe to import from gateway code.

    Handles:
    - <at> tags: preserve @ prefix (Teams mention format)
    - <blockquote> forwarded content: keep user text, strip forwarded
    - <img> tags: emoji → alt text, real images → inline_images list
    - <file> tags: extract src/name into inline_images as file entries
    - <a> tags: restore truncated URLs
    - General HTML → markdown conversion

    Returns:
        (text, inline_images) — text is str, inline_images is list[dict]
    """
    if not content:
        return "", []

    soup = BeautifulSoup(content, "html.parser")
    inline_images = []

    # <at> tags: preserve @ prefix
    for at_tag in soup.find_all("at"):
        at_name = at_tag.get_text() or ""
        at_tag.replace_with(f"@{at_name}")

    # <blockquote> forwarded content
    for bq in soup.find_all("blockquote"):
        rest = str(soup).replace(str(bq), "").strip()
        bq_text = bq.get_text().strip()[:80] if bq.get_text() else ""
        if rest and rest != "<html><body></body></html>":
            bq.replace_with(f"[forwarded message: {bq_text}…]")
        else:
            bq.decompose()

    # <file> tags: extract file attachment info
    for file_tag in soup.find_all("file"):
        src = file_tag.get("src", "")
        name = file_tag.get("name", "")
        if src and src.startswith("http"):
            inline_images.append({"src": src, "alt": name, "kind": "file"})
            file_tag.replace_with(f"[📎 {name or src.split('/')[-1]}]")
        else:
            file_tag.decompose()

    # <img> tags: emoji vs real images
    for img in soup.find_all("img"):
        if _is_emoji_img(img):
            alt = img.get("alt", "")
            img.replace_with(alt)
        else:
            src = img.get("src", "")
            alt = img.get("alt", "image")
            if src:
                inline_images.append({"src": src, "alt": alt, "kind": "image"})

    # Restore truncated URLs
    for a in soup.find_all("a"):
        href = a.get("href", "")
        link_text = a.get_text().strip()
        if href and link_text and link_text.endswith("\u2026") and href.startswith("http"):
            a.replace_with(href)

    text = md_convert(str(soup), strip=["div", "span"])
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text, inline_images


def download_with_auth_url(url: str, skype_token: str, access_token: str = "",
                           verify_ssl: bool = False, timeout: int = 30,
                           graph_token: str = "") -> bytes:
    """Download a URL using domain-appropriate auth headers.

    Module-level pure function (no class dependency) for downstream consumers
    like the Hermes gateway adapter.  Mirrors the auth strategy of
    ``HTTPLayer.download_with_auth`` but takes raw credential strings.

    Auth strategy by domain:
    - api.asm.skype.com → Authorization: skype_token ***
    - teams.microsoft.com / skype.com → Authentication: skypetoken={skype_token}
    - sharepoint.com / onedrive.com → Authorization: Bearer ***
      (fallback: Graph /shares API with graph_token if Bearer 401s)
    - other → Authorization: Bearer ***

    Args:
        url: The URL to download
        skype_token: Skype token for Skype/Teams domains
        access_token: Azure AD token for SharePoint/OneDrive/other domains
        verify_ssl: Whether to verify SSL certificates
        timeout: Request timeout in seconds
        graph_token: Graph-audience token for /shares fallback on SharePoint 401

    Returns:
        Response content as bytes

    Raises:
        requests.HTTPError: On non-2xx response
        requests.RequestException: On network error
    """
    import urllib.parse as _up
    parsed = _up.urlparse(url)
    netloc = parsed.netloc.lower()

    if "api.asm.skype.com" in netloc:
        headers = {"Authorization": f"skype_token {skype_token}"}
    elif "teams.microsoft.com" in netloc or "skype.com" in netloc:
        headers = {"Authentication": f"skypetoken={skype_token}"}
    else:
        headers = {"Authorization": f"Bearer {access_token}"}

    session = requests.Session()
    try:
        response = session.get(url, headers=headers, verify=verify_ssl, timeout=timeout)

        # SharePoint/OneDrive file paths 401 against the regular access_token —
        # retry via Microsoft Graph /shares API if we have a graph_token.
        if (response.status_code == 401
                and ("sharepoint.com" in netloc or "1drv.ms" in netloc
                     or "sharepoint" in netloc)
                and graph_token):
            _b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
            _encoded = f"u!{_b64}"
            _graph_url = f"https://graph.microsoft.com/v1.0/shares/{_encoded}/driveItem/content"
            r = session.get(
                _graph_url, headers={"Authorization": f"Bearer {graph_token}"},
                verify=verify_ssl, timeout=timeout, allow_redirects=True,
            )
            r.raise_for_status()
            return r.content

        response.raise_for_status()
        return response.content
    finally:
        session.close()
