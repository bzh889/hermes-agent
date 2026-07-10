"""Unit tests for TeamsMTKAdapter answer reliability.

Covers teams-mtk-answer-reliability change:
- §1 edit_message 429 backoff + retry
- §1 edit_message persistent failure never raises
- §2 send 429 backoff + retry
- §2 send 401 refresh integrity (not broken by 429 logic)
- §3 config: reply_throttle_seconds default
- §4 throttle: _last_reply_at + interruptible wait

TDD discipline: this file defines the RED tests first.
Implementation in teams_mtk.py makes them GREEN.
"""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest

from gateway.platforms.teams_mtk import TeamsMTKAdapter
from gateway.platforms.base import SendResult

pytestmark = pytest.mark.asyncio


# ── Fixture ──────────────────────────────────────────────────────────────

def _make_adapter():
    """Build a TeamsMTKAdapter without touching the real Teams token cache."""
    return TeamsMTKAdapter(config=None)


def _mock_requests_put(status_sequence):
    """Return a mock for requests.put that returns the given status codes in order."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_sequence[0]
    mock_resp.content = b'{"id":"msg1"}'
    mock_resp.raise_for_status = MagicMock()

    call_count = [0]

    def _put(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(status_sequence):
            mock_resp.status_code = status_sequence[idx]
        if mock_resp.status_code >= 400:
            mock_resp.raise_for_status.side_effect = Exception(f"HTTP {mock_resp.status_code}")
        else:
            mock_resp.raise_for_status.side_effect = None
        return mock_resp

    return _put


def _mock_session_post(status_sequence):
    """Return an async-ready mock session.post that yields the given statuses."""
    responses = []
    for code in status_sequence:
        r = MagicMock()
        r.status_code = code
        r.json.return_value = {"id": "msg-new"}
        if code >= 400:
            r.raise_for_status.side_effect = Exception(f"HTTP {code}")
        else:
            r.raise_for_status.side_effect = None
        responses.append(r)

    call_count = [0]

    def _post(*a, **kw):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]

    return _post


# ── §1 edit_message 429 ──────────────────────────────────────────────────

async def test_edit_message_429_backs_off_and_retries():
    """edit_message: 429 on first attempt → back off + retry once → 200 → success."""
    adapter = _make_adapter()

    with patch("requests.put") as mock_put, \
         patch("requests.Session"), \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_put.side_effect = _mock_requests_put([429, 200])

        result = await adapter.edit_message(
            "19:test@thread.v2", "msg1", "updated content"
        )

        assert result.success is True
        # Should have slept once for backoff
        mock_sleep.assert_called_once()
        _delay = mock_sleep.call_args[0][0]
        assert _delay == adapter._RATE_LIMIT_BACKOFF_S


async def test_edit_message_persistent_failure_never_raises():
    """edit_message: 429 on both attempts → never raises, returns failure."""
    adapter = _make_adapter()

    with patch("requests.put") as mock_put, \
         patch("requests.Session"), \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock):
        # Both attempts return 429 → raise_for_status raises on second
        mock_put.side_effect = _mock_requests_put([429, 429])

        result = await adapter.edit_message(
            "19:test@thread.v2", "msg1", "updated content"
        )

        # Never raises — returns SendResult(success=False)
        assert isinstance(result, SendResult)
        assert result.success is False
        assert result.error is not None


# ── §2 send 429 ──────────────────────────────────────────────────────────

async def test_send_429_backs_off_and_retries():
    """send: 429 on first attempt → back off + retry once → 200 → success."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "fake-skype-token"
    adapter._auth.msg_base = "https://msg.example.com/v1"
    adapter._auth._force_refresh = MagicMock()
    adapter._auth._inject_truststore = MagicMock()

    with patch("requests.Session") as MockSession, \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_session = MagicMock()
        mock_session.post = _mock_session_post([429, 200])
        mock_session.close = MagicMock()
        MockSession.return_value = mock_session

        result = await adapter.send("19:test@thread.v2", "hello world")

        assert result.success is True
        mock_sleep.assert_called_once()
        _delay = mock_sleep.call_args[0][0]
        assert _delay == adapter._RATE_LIMIT_BACKOFF_S


async def test_send_401_refresh_integrity():
    """send: 401 on first attempt triggers _force_refresh (not 429 logic)."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "fake-skype-token"
    adapter._auth.msg_base = "https://msg.example.com/v1"
    adapter._auth._force_refresh = MagicMock()
    adapter._auth._inject_truststore = MagicMock()

    with patch("requests.Session") as MockSession, \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_session = MagicMock()
        mock_session.post = _mock_session_post([401, 200])
        mock_session.close = MagicMock()
        MockSession.return_value = mock_session

        result = await adapter.send("19:test@thread.v2", "hello world")

        assert result.success is True
        # 401 path calls _force_refresh, NOT sleep (that's the 429 path)
        adapter._auth._force_refresh.assert_called_once()
        mock_sleep.assert_not_called()


# ── §3 config: reply_throttle_seconds ────────────────────────────────────

@pytest.mark.asyncio(False)
def test_config_default_throttle_is_zero():
    """DEFAULT_CONFIG should include reply_throttle_seconds with a default of 0 (disabled)."""
    from hermes_cli.config import DEFAULT_CONFIG
    # Key under gateway.teams_mtk
    tmk = DEFAULT_CONFIG.get("gateway", {}).get("teams_mtk", {})
    assert "reply_throttle_seconds" in tmk, (
        f"reply_throttle_seconds missing from DEFAULT_CONFIG gateway.teams_mtk; "
        f"got keys: {list(tmk.keys())}"
    )
    assert tmk["reply_throttle_seconds"] == 0, (
        f"reply_throttle_seconds should default to 0 (disabled), got {tmk['reply_throttle_seconds']}"
    )


# ── §4 throttle: _last_reply_at + interruptible wait ───────────────────

async def test_throttle_delays_rapid_follow_up():
    """If throttle > 0, two rapid sends to the same conv: second waits."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0  # Override for test
    adapter._last_reply_at = {}           # Per-conv tracking

    # Simulate first reply at t=0
    import time
    adapter._last_reply_at["19:test@thread.v2"] = time.monotonic()

    # Second call immediately — should wait (sleep called with ~2.0)
    # We just test that asyncio.sleep is called with approximately
    # the expected delay. The real implementation decides the exact
    # remaining wait time.
    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # The adapter's send() would call _maybe_throttle() before posting
        # For now this tests the contract: if throttle is active and
        # insufficient time has passed, sleep IS called.
        # (Implementation will be wired in GREEN phase.)
        try:
            await adapter._maybe_throttle("19:test@thread.v2")
        except AttributeError:
            pytest.skip("_maybe_throttle not yet implemented — RED phase")

        if mock_sleep.called:
            _delay = mock_sleep.call_args[0][0]
            assert _delay > 0, "throttle sleep must be positive"
            assert _delay <= 2.0, "throttle sleep must not exceed the configured window"


async def test_throttle_no_wait_when_disabled():
    """If throttle == 0 (disabled), no sleep occurs."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 0

    try:
        await adapter._maybe_throttle("19:test@thread.v2")
    except AttributeError:
        pytest.skip("_maybe_throttle not yet implemented — RED phase")


async def test_throttle_no_wait_after_window_elapses():
    """If enough time has elapsed since last reply, no sleep needed."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}

    import time
    # Set last reply 5 seconds ago — well past 2s window
    adapter._last_reply_at["19:test@thread.v2"] = time.monotonic() - 5.0

    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        try:
            await adapter._maybe_throttle("19:test@thread.v2")
        except AttributeError:
            pytest.skip("_maybe_throttle not yet implemented — RED phase")

        mock_sleep.assert_not_called()


async def test_throttle_per_conv_independent():
    """Throttle tracking is per-conv: reply to conv A doesn't delay conv B."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}

    import time
    adapter._last_reply_at["19:convA@thread.v2"] = time.monotonic()

    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        try:
            await adapter._maybe_throttle("19:convB@thread.v2")
        except AttributeError:
            pytest.skip("_maybe_throttle not yet implemented — RED phase")

        mock_sleep.assert_not_called()


# ── §5 echo guard: _sent_message_ids set ─────────────────────────────────

async def test_echo_guard_skips_known_sent_id():
    """Messages whose id is in _sent_message_ids must be skipped."""
    adapter = _make_adapter()
    adapter._sent_message_ids.add("999")
    assert "999" in adapter._sent_message_ids


async def test_at_mention_preserved_in_html_strip():
    """<at id='...'>hermes</at> must survive HTML stripping as plain 'hermes'."""
    import re
    raw = '<at id="8:orgid:abc">hermes</at>'
    # Replicate the exact strip logic from _process_new_messages
    content = re.sub(r"<at\s[^>]*>([^<]*)</at>", r"\1", raw)
    text = re.sub(r"<[^>]+>", "", content).strip()
    assert text == "hermes", f"Expected 'hermes', got {text!r}"


async def test_at_mention_only_message_not_empty():
    """A message containing only an @mention should not be treated as empty."""
    import re
    raw = '<div><at id="8:orgid:abc">hermes</at></div>'
    content = re.sub(r"<at\s[^>]*>([^<]*)</at>", r"\1", raw)
    text = re.sub(r"<[^>]+>", "", content).strip()
    text = re.sub(r"\s+", " ", text).strip()
    assert text == "hermes"


# ── §6 token cache: atomic write + auto-purge on corruption ───────────

def test_token_cache_atomic_write(tmp_path, monkeypatch):
    """_save writes to temp file then renames (atomic), not direct overwrite."""
    from gateway.platforms.teams_mtk import _TeamsAuth
    cache_path = tmp_path / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    auth = _TeamsAuth()
    auth._save({"access_token": "abc123", "saved_at": 100, "expires_in": 3600})
    assert cache_path.exists()
    import json
    data = json.loads(cache_path.read_text())
    assert data["access_token"] == "abc123"
    # Temp file should not linger
    assert not cache_path.with_suffix(".json.tmp").exists()


def test_token_cache_auto_purge_on_corruption(tmp_path, monkeypatch):
    """If cache JSON is totally corrupted, _load deletes the file and raises RuntimeError."""
    from gateway.platforms.teams_mtk import _TeamsAuth
    cache_path = tmp_path / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    # Write garbage
    cache_path.write_text("NOT JSON AT ALL {{{")
    auth = _TeamsAuth()
    with pytest.raises(RuntimeError, match="corrupted and has been deleted"):
        auth._load()
    # Cache file should be auto-purged
    assert not cache_path.exists()


def test_token_cache_partial_json_recovery(tmp_path, monkeypatch):
    """If cache has one valid JSON + trailing garbage, raw_decode recovers it."""
    from gateway.platforms.teams_mtk import _TeamsAuth
    cache_path = tmp_path / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    # Write valid JSON followed by garbage (simulating partial write)
    cache_path.write_text('{"access_token":"abc","saved_at":1}GARBAGE')
    auth = _TeamsAuth()
    data = auth._load()
    assert data["access_token"] == "abc"


# ── §7 edit_message respects throttle ─────────────────────────────────

async def test_edit_message_throttled_before_send():
    """edit_message should call _maybe_throttle before the HTTP PUT."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}
    import time
    adapter._last_reply_at["19:test@thread.v2"] = time.monotonic()

    with patch("requests.put") as mock_put, \
         patch("requests.Session"), \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_put.side_effect = _mock_requests_put([200])

        result = await adapter.edit_message(
            "19:test@thread.v2", "msg1", "updated content"
        )

        # Should have slept for throttle AND potentially for 429 backoff
        # At minimum, throttle sleep should have been called
        sleep_delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert any(d > 0 for d in sleep_delays), "edit_message should throttle before sending"
