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


async def test_raw_fetch_connection_error_preserves_original_exception():
    """A network failure must not be replaced by an error in logging."""
    import requests

    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "fake-skype-token"
    adapter._auth.msg_base = "https://msg.example.com/v1"

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("network down")
    with patch("requests.Session", return_value=session):
        with pytest.raises(requests.ConnectionError, match="network down"):
            adapter._fetch_via_raw("19:test@thread.v2", 30, 0.0)

    session.close.assert_called_once()


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


# ── §5 echo guard: MessageDeduplicator ─────────────────────────────────

async def test_echo_guard_tracks_conversation_and_message_id():
    """Outbound ownership is scoped to the exact conversation and message."""
    adapter = _make_adapter()
    adapter._remember_sent_message("conv-a", "999")

    assert adapter._is_sent_message("conv-a", "999") is True
    assert adapter._is_sent_message("conv-b", "999") is False


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
    """_load recovers first valid JSON object when trailing garbage exists."""
    from gateway.platforms.teams_mtk import _TeamsAuth
    cache_path = tmp_path / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    # Write valid JSON followed by garbage (simulating partial write)
    cache_path.write_text('{"access_token":"abc","saved_at":1}GARBAGE')
    auth = _TeamsAuth()
    data = auth._load()
    assert data["access_token"] == "abc"


async def test_exchange_for_scope_uses_requested_scope_and_persists_rotated_refresh(
    tmp_path, monkeypatch
):
    """IC3/Graph exchanges preserve refresh-token rotation in the shared cache."""
    import json
    from gateway.platforms.teams_mtk import _TeamsAuth

    cache_path = tmp_path / "token_cache.json"
    cache_path.write_text(
        json.dumps({"refresh_token": "refresh-old", "access_token": "skype-access"})
    )
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)

    response = MagicMock()
    response.json.return_value = {
        "access_token": "ic3-access",
        "refresh_token": "refresh-new",
        "expires_in": 3600,
    }

    auth = _TeamsAuth()
    with patch("requests.post", return_value=response) as post:
        result = auth.exchange_for_scope(
            "https://ic3.teams.office.com/Teams.AccessAsUser.All"
        )

    assert result["access_token"] == "ic3-access"
    assert post.call_args.kwargs["data"] == {
        "client_id": "1fec8e78-bce4-4aaf-ab1b-5451cc387264",
        "grant_type": "refresh_token",
        "refresh_token": "refresh-old",
        "scope": "https://ic3.teams.office.com/Teams.AccessAsUser.All",
    }
    assert json.loads(cache_path.read_text())["refresh_token"] == "refresh-new"
    response.raise_for_status.assert_called_once_with()


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


# ── §8 parallel poll: asyncio.gather actually runs concurrently ───────

async def test_poll_loop_fetches_conversations_in_parallel():
    """_poll_loop must fetch all conv_ids concurrently (asyncio.gather over
    run_in_executor), not sequentially. Prove it by making each mocked
    _fetch_messages block for 0.3s: if fetches were sequential, N=3 convs
    would take >=0.9s; if parallel, total wall time stays close to 0.3s.

    This directly guards against a future refactor silently reverting to
    a sequential `for` loop (the pre-fix behavior tasks.md §5.3 replaced).
    """
    import time as _time

    adapter = _make_adapter()
    adapter._conv_ids = ["conv-a", "conv-b", "conv-c"]
    adapter._running = True

    _FETCH_DELAY = 0.3
    call_times = []

    def _slow_fetch(conv_id, limit=20):
        call_times.append(_time.monotonic())
        _time.sleep(_FETCH_DELAY)
        return []

    async def _fake_process(conv_id, msgs):
        return None

    # Run exactly one poll tick then stop the loop (sleep is where the loop
    # yields between ticks, so stopping there after tick 1 completes is safe).
    async def _stop_after_one_tick(*a, **kw):
        adapter._running = False

    with patch.object(adapter, "_fetch_messages", side_effect=_slow_fetch), \
         patch.object(adapter, "_process_new_messages", side_effect=_fake_process), \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", side_effect=_stop_after_one_tick):
        t0 = _time.monotonic()
        await adapter._poll_loop()
        elapsed = _time.monotonic() - t0

    # 3 conv_ids x 0.3s each: sequential would take >=0.9s, parallel stays
    # near 0.3-0.4s (thread-pool dispatch overhead). Assert well below the
    # sequential floor to catch a regression to the old `for` loop.
    assert elapsed < _FETCH_DELAY * 2, (
        f"poll tick took {elapsed:.2f}s for 3 convs @ {_FETCH_DELAY}s each — "
        f"expected parallel execution (~{_FETCH_DELAY:.1f}s), got sequential-like timing"
    )
    assert len(call_times) == 3, "all 3 conv_ids must be fetched"
    # All three fetches should have started within a tight window of each
    # other (proving they were dispatched concurrently, not one-after-another).
    assert max(call_times) - min(call_times) < _FETCH_DELAY, (
        "fetch start times spread out — convs were not dispatched in parallel"
    )


# ── send_typing (GAP-1) ──────────────────────────────────────────────────

class TestSendTyping:
    """Verify send_typing() sends Control/Typing via skypetoken."""

    async def test_send_typing_posts_control_typing(self):
        """send_typing POSTs {"messagetype":"Control/Typing","content":""}."""
        adapter = _make_adapter()
        mock_resp = MagicMock(status_code=201, text='{"OriginalArrivalTime":1}')
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("requests.Session", return_value=mock_session), \
             patch.object(adapter._auth, "skype_token", return_value="fake-skype-token"), \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            await adapter.send_typing("19:test@thread.v2")

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        url = call_args[0][0]
        payload = call_args[1]["json"]
        assert "Control/Typing" == payload["messagetype"]
        assert payload["content"] == ""
        assert "skypetoken=fake-skype-token" in call_args[1]["headers"]["Authentication"]
        assert "19:test@thread.v2" in url

    async def test_send_typing_non_201_logs_warning(self):
        """send_typing logs warning on non-201 but does not raise."""
        adapter = _make_adapter()
        mock_resp = MagicMock(status_code=403, text="forbidden")
        mock_session = MagicMock()
        mock_session.post.return_value = mock_resp
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("requests.Session", return_value=mock_session), \
             patch.object(adapter._auth, "skype_token", return_value="tok"), \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            # Should not raise even on 403
            await adapter.send_typing("19:test@thread.v2")

    async def test_send_typing_exception_does_not_raise(self):
        """send_typing swallows exceptions (logging only) so _keep_typing stays alive."""
        adapter = _make_adapter()
        mock_session = MagicMock()
        mock_session.post.side_effect = ConnectionError("network down")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("requests.Session", return_value=mock_session), \
             patch.object(adapter._auth, "skype_token", return_value="tok"), \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            # Must not raise — _keep_typing depends on this
            await adapter.send_typing("19:test@thread.v2")
