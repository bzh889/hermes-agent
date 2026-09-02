"""Shared utilities for Teams MCP server."""

import time
from functools import wraps
from html.parser import HTMLParser

import requests

# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    safe_methods: frozenset = frozenset({"GET", "PUT", "DELETE", "HEAD", "OPTIONS"}),
):
    """Retry with exponential backoff, idempotency-aware.

    For safe methods (GET, PUT, DELETE): retries on all transient errors.
    For non-safe methods (POST, PATCH):
    - ConnectionError/ConnectTimeout: RETRY (request never reached server)
    - ReadTimeout: NO RETRY (server may have processed it)
    - HTTPError 429/503: RETRY (server says "try again")
    - Other errors: NO RETRY

    Designed for ``_request(self, method, url, **kwargs)`` signature.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract HTTP method from (self, method, url, ...) signature
            request_method = "GET"
            if len(args) > 1 and isinstance(args[1], str):
                request_method = args[1].upper()
            elif "method" in kwargs:
                request_method = str(kwargs["method"]).upper()

            is_safe = request_method in safe_methods
            delay = base_delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, ValueError) as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise

                    if not is_safe:
                        # POST/PATCH: fine-grained retry decisions
                        if isinstance(e, requests.ReadTimeout):
                            raise  # Server may have processed — NEVER retry
                        if isinstance(e, (requests.ConnectionError, requests.ConnectTimeout)):
                            pass  # Safe to retry — request never reached server
                        elif isinstance(e, requests.HTTPError):
                            status = e.response.status_code if e.response is not None else 0
                            if status not in (429, 503):
                                raise  # Only retry rate-limit / service-unavailable
                        else:
                            raise  # Unknown error — don't retry POST

                    time.sleep(min(delay, max_delay))
                    delay *= 2
            raise last_exception  # pragma: no cover
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Safe HTML truncation
# ---------------------------------------------------------------------------


class SafeTruncator(HTMLParser):
    """SAX-style HTML truncator that counts visible text only.

    Truncates HTML content based on visible character count (not raw HTML
    length) and automatically closes all open tags, producing valid HTML.
    """

    VOID_TAGS = frozenset(["br", "img", "hr", "input", "meta", "link"])

    def __init__(self, limit: int):
        super().__init__(convert_charrefs=False)
        self._limit = limit
        self._text_len = 0
        self._parts: list[str] = []
        self._stack: list[str] = []
        self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        attr_str = "".join(
            f' {k}="{v}"' if v is not None else f" {k}"
            for k, v in attrs
        )
        self._parts.append(f"<{tag}{attr_str}>")
        if tag.lower() not in self.VOID_TAGS:
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if self._done:
            return
        self._parts.append(f"</{tag}>")
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._done:
            return
        remaining = self._limit - self._text_len
        if len(data) > remaining:
            self._parts.append(data[:remaining])
            self._text_len = self._limit
            self._done = True
        else:
            self._parts.append(data)
            self._text_len += len(data)

    def handle_entityref(self, name):
        if self._done:
            return
        self._parts.append(f"&{name};")
        self._text_len += 1

    def handle_charref(self, name):
        if self._done:
            return
        self._parts.append(f"&#{name};")
        self._text_len += 1

    def get_result(self) -> str:
        """Return truncated HTML with all open tags closed."""
        while self._stack:
            self._parts.append(f"</{self._stack.pop()}>")
        return "".join(self._parts)

    @property
    def was_truncated(self) -> bool:
        return self._done


def safe_truncate(html: str, limit: int, suffix: str = "...") -> str:
    """Truncate HTML by visible text length, preserving valid structure.

    Args:
        html: HTML string to truncate.
        limit: Maximum visible characters.
        suffix: Appended after truncation (default ``...``).

    Returns:
        Truncated HTML with all tags properly closed.
    """
    truncator = SafeTruncator(limit)
    truncator.feed(html)
    result = truncator.get_result()
    if truncator.was_truncated:
        result += suffix
    return result


# ---------------------------------------------------------------------------
# Content type detection (magic bytes)
# ---------------------------------------------------------------------------

# (prefix_bytes, mime_type, extension)
MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF8", "image/gif", ".gif"),
    (b"RIFF", "image/webp", ".webp"),  # extra WEBP check below
    (b"%PDF", "application/pdf", ".pdf"),
    (b"PK\x03\x04", "application/zip", ".zip"),
    (b"\xd0\xcf\x11\xe0", "application/msoffice", ".doc"),
]


def detect_content_type(content: bytes) -> tuple[str, str]:
    """Detect content type from magic bytes.

    Args:
        content: Raw file content bytes.

    Returns:
        Tuple of ``(mime_type, file_extension)``.
    """
    if len(content) < 12:
        return "application/octet-stream", ".bin"

    for sig, mime, ext in MAGIC_SIGNATURES:
        if content[: len(sig)] == sig:
            # RIFF header requires extra validation for WEBP
            if sig == b"RIFF" and content[8:12] != b"WEBP":
                continue
            return mime, ext

    return "application/octet-stream", ".bin"


# ---------------------------------------------------------------------------
# Semantic error builder
# ---------------------------------------------------------------------------


def agent_error(action: str, reason: str, suggestion: str) -> str:
    """Build an actionable error message for Agent self-correction.

    Args:
        action: Tool or operation name.
        reason: What went wrong.
        suggestion: What the Agent should do next.

    Returns:
        Formatted error string with suggestion.
    """
    return f"Error ({action}): {reason}\nSuggestion: {suggestion}"
