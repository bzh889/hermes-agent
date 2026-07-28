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
import sys
import threading
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest

from gateway.platforms.teams_mtk import TeamsMTKAdapter, _clean_message_content
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


async def test_connect_dispatches_blocking_startup_work_off_event_loop():
    """Auth and cold-start fetch stay responsive while worker calls are blocked."""
    import gateway.platforms.teams_mtk as teams_mtk

    adapter = _make_adapter()
    adapter._conv_ids = ["conv-a"]
    adapter._last_message_ids = {"conv-a": None}
    adapter._auth = MagicMock()
    event_loop_thread = threading.get_ident()
    auth_entered = threading.Event()
    auth_release = threading.Event()
    fetch_entered = threading.Event()
    fetch_release = threading.Event()
    worker_threads = []

    def blocking_auth():
        worker_threads.append(("auth", threading.get_ident()))
        auth_entered.set()
        if threading.get_ident() != event_loop_thread:
            assert auth_release.wait(timeout=1)
        return "skype-token"

    def blocking_fetch(*, conv_id, limit):
        worker_threads.append(("fetch", threading.get_ident()))
        fetch_entered.set()
        if threading.get_ident() != event_loop_thread:
            assert fetch_release.wait(timeout=1)
        assert (conv_id, limit) == ("conv-a", 20)
        return []

    adapter._auth.skype_token.side_effect = blocking_auth
    adapter._fetch_messages = MagicMock(side_effect=blocking_fetch)
    listener = MagicMock()

    async def completed_poll():
        return None

    connect_task = None
    with patch.object(adapter, "_poll_loop", side_effect=completed_poll), patch.object(
        teams_mtk, "_TrouterListener", return_value=listener
    ), patch.object(adapter, "_mark_connected"):
        try:
            connect_task = asyncio.create_task(adapter.connect())
            assert await asyncio.to_thread(auth_entered.wait, 0.5)

            auth_heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(auth_heartbeat.set)
            await asyncio.wait_for(auth_heartbeat.wait(), timeout=0.5)
            auth_release.set()

            assert await asyncio.to_thread(fetch_entered.wait, 0.5)
            fetch_heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(fetch_heartbeat.set)
            await asyncio.wait_for(fetch_heartbeat.wait(), timeout=0.5)
            fetch_release.set()

            assert await asyncio.wait_for(connect_task, timeout=0.5) is True
        finally:
            auth_release.set()
            fetch_release.set()
            if connect_task is not None and not connect_task.done():
                connect_task.cancel()
                try:
                    await connect_task
                except asyncio.CancelledError:
                    pass

    assert [operation for operation, _ in worker_threads] == ["auth", "fetch"]
    assert all(thread_id != event_loop_thread for _, thread_id in worker_threads)
    adapter._auth.skype_token.assert_called_once_with()
    adapter._fetch_messages.assert_called_once_with(conv_id="conv-a", limit=20)
    listener.start.assert_called_once_with()


async def test_raw_send_acquires_skype_token_off_event_loop():
    """A slow raw-send token refresh must not run on the asyncio thread."""
    import gateway.platforms.teams_mtk as teams_mtk

    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.com/v1"
    event_loop_thread = threading.get_ident()
    token_threads = []

    def acquire_token():
        token_threads.append(threading.get_ident())
        return "fake-skype-token"

    adapter._auth.skype_token.side_effect = acquire_token
    response = MagicMock(status_code=201)
    response.json.return_value = {"OriginalArrivalTime": "raw-message-id"}
    session = MagicMock()
    session.post.return_value = response

    with patch.object(teams_mtk, "_SDK_AVAILABLE", False), patch(
        "requests.Session", return_value=session
    ):
        result = await adapter.send("conv-a", "hello")

    assert result.message_id == "raw-message-id"
    assert token_threads and token_threads[0] != event_loop_thread


async def test_raw_edit_acquires_skype_token_off_event_loop():
    """A slow raw-edit token refresh must not run on the asyncio thread."""
    import gateway.platforms.teams_mtk as teams_mtk

    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.com/v1"
    event_loop_thread = threading.get_ident()
    token_threads = []

    def acquire_token():
        token_threads.append(threading.get_ident())
        return "fake-skype-token"

    adapter._auth.skype_token.side_effect = acquire_token
    response = MagicMock(status_code=200, content=b"")

    with patch.object(teams_mtk, "_SDK_AVAILABLE", False), patch(
        "requests.put", return_value=response
    ):
        result = await adapter.edit_message("conv-a", "msg-a", "updated")

    assert result.success is True
    assert token_threads and token_threads[0] != event_loop_thread


# ── §1 edit_message 429 ──────────────────────────────────────────────────

async def test_edit_message_429_backs_off_and_retries():
    """edit_message: 429 on first attempt → back off + retry once → 200 → success."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "fake-skype-token"
    adapter._auth.msg_base = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"

    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("requests.put") as mock_put, \
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
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "fake-skype-token"
    adapter._auth.msg_base = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"

    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("requests.put") as mock_put, \
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

    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("requests.Session") as MockSession, \
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

    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("requests.Session") as MockSession, \
         patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_session = MagicMock()
        mock_session.post = _mock_session_post([401, 200])
        mock_session.close = MagicMock()
        MockSession.return_value = mock_session

        result = await adapter.send("19:test@thread.v2", "hello world")

        assert result.success is True
        # 401 path calls _force_refresh, NOT sleep (that's the 429 path)
        adapter._auth._force_refresh.assert_called_once()
        mock_sleep.assert_not_awaited()


async def test_send_sdk_rewrites_hardcoded_amer_to_regional_endpoint():
    """SDK message transport must honor the authz-discovered tenant region."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.skype_token.return_value = "regional-skype-token"
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"

    response = MagicMock(status_code=201)
    response.json.return_value = {"OriginalArrivalTime": "regional-message-id"}
    session = MagicMock()
    session.request.return_value = response

    class RecordingMessagesService:
        def __init__(self, http):
            self._http = http

        def send(self, **kwargs):
            conv = kwargs["conversation_id"]
            resp = self._http._request(
                "POST",
                f"https://amer.ng.msg.teams.microsoft.com/v1/users/ME/conversations/{conv}/messages",
                json={"content": kwargs["content"]},
            )
            return {"id": str(resp.json()["OriginalArrivalTime"])}

    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
         patch("gateway.platforms.teams_mtk._SDKMessages", RecordingMessagesService), \
         patch("requests.Session", return_value=session):
        result = await adapter.send("19:test@thread.v2", "hello regional tenant")

    assert result.success is True
    assert result.message_id == "regional-message-id"
    method, sent_url = session.request.call_args.args[:2]
    assert method == "POST"
    assert sent_url.startswith("https://apac.ng.msg.teams.microsoft.com/")
    assert session.request.call_args.kwargs["headers"]["Authentication"] == (
        "skypetoken=regional-skype-token"
    )


async def test_sdk_send_reuses_shared_transport_without_blocking_event_loop():
    """Outbound sends must reuse polling keep-alive from a worker thread."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    layer = MagicMock()
    layer._session = MagicMock()
    service = MagicMock()
    service.send.side_effect = [{"id": "msg-1"}, {"id": "msg-2"}]
    thread_calls = []

    async def run_in_worker(func, *args, **kwargs):
        thread_calls.append(func)
        return func(*args, **kwargs)

    with patch(
        "gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer
    ) as make_layer, patch(
        "gateway.platforms.teams_mtk._SDKMessages", return_value=service
    ), patch(
        "gateway.platforms.teams_mtk.asyncio.to_thread", side_effect=run_in_worker
    ):
        first = await adapter.send("conv-a", "first")
        second = await adapter.send("conv-a", "second")

    assert first.message_id == "msg-1"
    assert second.message_id == "msg-2"
    make_layer.assert_called_once()
    assert service.send.call_count == 2
    assert len(thread_calls) == 2
    assert adapter._sdk_http_layer is layer


async def test_sdk_send_does_not_raw_retry_when_delivery_is_uncertain():
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    adapter._auth.skype_token.return_value = "token"
    adapter._auth._inject_truststore = MagicMock()
    layer = MagicMock()
    layer._session = MagicMock()
    service = MagicMock()
    service.send.side_effect = ConnectionError("dead TLS pool")
    raw_response = MagicMock(status_code=201)
    raw_response.json.return_value = {"OriginalArrivalTime": "raw-msg"}

    with patch(
        "gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer
    ), patch(
        "gateway.platforms.teams_mtk._SDKMessages", return_value=service
    ), patch("requests.Session") as make_session:
        make_session.return_value.post.return_value = raw_response
        result = await adapter.send("conv-a", "fallback")

    assert result.success is False
    assert "delivery uncertain" in result.error.lower()
    make_session.return_value.post.assert_not_called()
    layer._session.close.assert_called_once_with()
    assert adapter._sdk_http_layer is None


async def test_sdk_missing_id_readback_is_correlated_and_off_event_loop():
    """Never assign an unrelated bot ID when a successful SDK response lacks one."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    service = MagicMock()
    service.send.return_value = {"id": ""}
    html_content, _ = adapter._build_html("recover this message")
    event_loop_thread = threading.get_ident()
    fetch_threads = []

    def fetch_messages(*_args, **_kwargs):
        fetch_threads.append(threading.get_ident())
        return [
            {
                "id": "wrong-id",
                "_raw_content": "<div>unrelated bot message</div>",
                "_raw_properties": {"hermes_sender": "bot"},
            },
            {
                "id": "matching-id",
                "_raw_content": html_content,
                "_raw_properties": {"hermes_sender": "bot"},
            },
        ]

    with patch(
        "gateway.platforms.teams_mtk._SDKMessages", return_value=service
    ), patch.object(adapter, "_fetch_messages", side_effect=fetch_messages):
        result = await adapter.send("conv-a", "recover this message")

    assert result.success is True
    assert result.message_id == "matching-id"
    assert fetch_threads and fetch_threads[0] != event_loop_thread


def test_sdk_http_layer_uses_verified_tls12_on_windows():
    """The Windows MSG transport must avoid the observed TLS negotiation EOF."""
    import requests
    import ssl
    from types import SimpleNamespace
    import gateway.platforms.teams_mtk as teams_mtk

    assert teams_mtk._SDKHTTPLayer is not None
    with patch.object(sys, "platform", "win32"):
        layer = teams_mtk._SDKHTTPLayer(MagicMock(), verify_ssl=True)
    try:
        assert layer._session.trust_env is False
        https_adapter = layer._session.get_adapter("https://msg.example.test")
        context = https_adapter.poolmanager.connection_pool_kw.get("ssl_context")
        assert context is not None
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
        assert context.maximum_version == ssl.TLSVersion.TLSv1_2
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        prepared = requests.Request(
            "GET", "https://msg.example.test"
        ).prepare()
        _, request_pool_kwargs = https_adapter.build_connection_pool_key_attributes(
            prepared, verify=True, cert=None
        )
        assert request_pool_kwargs["ssl_context"] is context
        connection = SimpleNamespace(
            cert_reqs="context-owned",
            ca_certs="context-owned",
            ca_cert_dir="context-owned",
            cert_file=None,
            key_file=None,
        )
        https_adapter.cert_verify(
            connection,
            "https://msg.example.test",
            verify=True,
            cert=None,
        )
        assert connection.cert_reqs == "context-owned"
        assert connection.ca_certs == "context-owned"
        assert connection.ca_cert_dir == "context-owned"
    finally:
        layer._session.close()


def test_sdk_fetch_reuses_one_http_transport_across_conversations():
    """Polling must reuse keep-alive instead of repeating flaky TLS handshakes."""
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    layer = MagicMock()
    layer._session = MagicMock()
    service = MagicMock()
    service.get_page.return_value = []

    with patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer) as make_layer, \
         patch("gateway.platforms.teams_mtk._SDKMessages", return_value=service):
        adapter._fetch_via_sdk("conv-a", 1, 0.0)
        adapter._fetch_via_sdk("conv-b", 1, 0.0)

    make_layer.assert_called_once()
    assert service.get_page.call_count == 2
    assert adapter._sdk_http_layer is layer


def test_sdk_fetch_discards_failed_transport_before_raw_fallback():
    adapter = _make_adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
    layer = MagicMock()
    layer._session = MagicMock()
    service = MagicMock()
    service.get_page.side_effect = ConnectionError("dead TLS pool")

    with patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer), \
         patch("gateway.platforms.teams_mtk._SDKMessages", return_value=service), \
         patch.object(adapter, "_fetch_via_raw", return_value=[]) as raw:
        assert adapter._fetch_via_sdk("conv-a", 1, 0.0) == []

    layer._session.close.assert_called_once_with()
    assert adapter._sdk_http_layer is None
    raw.assert_called_once()


async def test_disconnect_waits_for_shared_sdk_transport_without_blocking_loop():
    """Disconnect must not close a transport while a worker still owns it."""
    adapter = _make_adapter()
    layer = MagicMock()
    layer._session = MagicMock()
    adapter._sdk_http_layer = layer
    entered = threading.Event()
    release = threading.Event()
    service = MagicMock()

    def blocking_send(**_kwargs):
        entered.set()
        assert release.wait(timeout=2)
        return {"id": "msg-a"}

    service.send.side_effect = blocking_send
    with patch(
        "gateway.platforms.teams_mtk._SDKMessages", return_value=service
    ):
        worker = asyncio.create_task(
            asyncio.to_thread(
                adapter._call_sdk_messages,
                "send",
                conversation_id="conv-a",
                content="hello",
            )
        )
        assert await asyncio.to_thread(entered.wait, 0.5)
        disconnect = asyncio.create_task(adapter.disconnect())
        try:
            heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(heartbeat.set)
            await asyncio.wait_for(heartbeat.wait(), timeout=0.5)
            await asyncio.sleep(0.05)
            assert disconnect.done() is False
            layer._session.close.assert_not_called()
        finally:
            release.set()

        await asyncio.wait_for(worker, timeout=1)
        await asyncio.wait_for(disconnect, timeout=1)

    layer._session.close.assert_called_once_with()


async def test_trailing_runtime_footer_edits_streamed_body_instead_of_sending_card():
    """A non-empty footer line must not become a second Teams message ID."""
    from gateway.platforms.base import SendResult

    adapter = _make_adapter()
    adapter._last_sent_message_id = "body-id"
    adapter._last_sent_message_html = (
        '<div style="border-left:3px solid #6264A7;padding-left:10px">'
        '<b>🤖 Hermes</b><br><br>body<br>'
        '<span style="color:#888;font-size:0.85em">— Hermes · old</span>'
        '</div>'
    )
    adapter.edit_message = AsyncMock(
        return_value=SendResult(success=True, message_id="body-id")
    )
    adapter._call_sdk_messages = MagicMock(return_value={"id": "footer-id"})

    result = await adapter.send("conv-a", "gpt-5.6 · openai · 12%")

    assert result.success is True
    adapter.edit_message.assert_awaited_once()
    assert adapter.edit_message.await_args is not None
    assert adapter.edit_message.await_args.kwargs["finalize"] is True
    adapter._call_sdk_messages.assert_not_called()


async def test_trailing_runtime_footer_keeps_final_streamed_body_without_cursor():
    """Footer merge must use the successful final edit, not the first preview."""
    from gateway.platforms.base import SendResult
    import gateway.platforms.teams_mtk as teams_mtk_module

    adapter = _make_adapter()
    adapter._last_sent_message_id = "body-id"
    adapter._last_sent_message_html = (
        '<div style="border-left:3px solid #6264A7;padding-left:10px">'
        '<b>🤖 Hermes</b><br><br>partial answer ▉<br>'
        '<span style="color:#888;font-size:0.85em">— Hermes · old</span>'
        '</div>'
    )
    adapter._call_sdk_messages = MagicMock(return_value={"id": "body-id"})

    with patch.object(teams_mtk_module, "_SDK_AVAILABLE", True):
        final_result = await adapter.edit_message(
            "conv-a",
            "body-id",
            "complete answer with the missing details",
            finalize=True,
        )
        footer_result = await adapter.send(
            "conv-a",
            "gpt-5.6-sol · openai-codex · 12%",
        )

    assert final_result == SendResult(success=True, message_id="body-id")
    assert footer_result.success is True
    final_footer_edit = adapter._call_sdk_messages.call_args_list[-1]
    assert final_footer_edit.args[0] == "edit"
    merged_html = final_footer_edit.kwargs["content"]
    assert "complete answer with the missing details" in merged_html
    assert "partial answer" not in merged_html
    assert "▉" not in merged_html


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
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}

    import time
    adapter._last_reply_at["19:test@thread.v2"] = time.monotonic()

    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await adapter._maybe_throttle("19:test@thread.v2")

        mock_sleep.assert_awaited_once()
        delay = mock_sleep.call_args[0][0]
        assert 0 < delay <= 2.0


async def test_throttle_no_wait_when_disabled():
    """If throttle == 0 (disabled), no sleep occurs."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 0

    await adapter._maybe_throttle("19:test@thread.v2")


async def test_throttle_no_wait_after_window_elapses():
    """If enough time has elapsed since last reply, no sleep needed."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}

    import time
    # Set last reply 5 seconds ago — well past 2s window
    adapter._last_reply_at["19:test@thread.v2"] = time.monotonic() - 5.0

    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await adapter._maybe_throttle("19:test@thread.v2")

        mock_sleep.assert_not_awaited()


async def test_throttle_per_conv_independent():
    """Throttle tracking is per-conv: reply to conv A doesn't delay conv B."""
    adapter = _make_adapter()
    adapter._reply_throttle_seconds = 2.0
    adapter._last_reply_at = {}

    import time
    adapter._last_reply_at["19:convA@thread.v2"] = time.monotonic()

    with patch("gateway.platforms.teams_mtk.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await adapter._maybe_throttle("19:convB@thread.v2")

        mock_sleep.assert_not_awaited()


# ── §5 echo guard: MessageDeduplicator ─────────────────────────────────

async def test_echo_guard_tracks_conversation_and_message_id():
    """Outbound ownership is scoped to the exact conversation and message."""
    adapter = _make_adapter()
    adapter._remember_sent_message("conv-a", "999")

    assert adapter._is_sent_message("conv-a", "999") is True
    assert adapter._is_sent_message("conv-b", "999") is False


async def test_at_mention_preserved_in_html_strip():
    """<at id='...'>hermes</at> must survive HTML stripping as plain 'hermes'."""
    raw = '<at id="8:orgid:abc">hermes</at>'
    text, _ = _clean_message_content(raw)
    assert "hermes" in text.lower()


async def test_at_mention_only_message_not_empty():
    """A message containing only an @mention should not be treated as empty."""
    raw = '<div><at id="8:orgid:abc">hermes</at></div>'
    text, _ = _clean_message_content(raw)
    assert text


# ── §6 token cache: atomic write + preserve corruption evidence ───────

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


@pytest.mark.parametrize(
    ("original", "issue"),
    [
        (b"NOT JSON AT ALL {{{", "corrupted"),
        (b"\xff\xfe\x80", "not valid UTF-8"),
    ],
    ids=["invalid-json", "non-utf8"],
)
def test_token_cache_preserved_when_legacy_and_wam_both_fail(
    tmp_path, monkeypatch, original, issue
):
    """Unrecoverable legacy and WAM failures are clear and preserve evidence."""
    from gateway.platforms.teams_mtk import _TeamsAuth
    cache_path = tmp_path / "token_cache.json"
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    cache_path.write_bytes(original)
    auth = _TeamsAuth()
    wam_load = MagicMock(side_effect=RuntimeError("broker unavailable"))
    monkeypatch.setattr(auth, "_load_wam_tokens", wam_load)

    with pytest.raises(
        RuntimeError,
        match=rf"{issue}.*preserved.*broker authentication is unavailable",
    ):
        auth._load()

    assert cache_path.read_bytes() == original
    wam_load.assert_called_once_with()


@pytest.mark.parametrize(
    "original",
    [b"NOT JSON AT ALL {{{", b"\xff\xfe\x80"],
    ids=["invalid-json", "non-utf8"],
)
def test_unusable_legacy_cache_uses_wam_in_memory_without_rewriting(
    tmp_path, monkeypatch, original
):
    """Invalid JSON and non-UTF-8 caches fall back without touching the file."""
    from gateway.platforms.teams_mtk import _TeamsAuth

    cache_path = tmp_path / "token_cache.json"
    cache_path.write_bytes(original)
    monkeypatch.setattr(_TeamsAuth, "TOKEN_CACHE", cache_path)
    fake_wam = MagicMock()
    fake_wam.ensure_valid_tokens.return_value = {
        "access_token": "wam-access",
        "skype_token": "wam-skype",
        "saved_at": 100,
        "expires_in": 3600,
    }

    auth = _TeamsAuth()
    auth._wam_auth = fake_wam
    monkeypatch.setattr(auth, "_inject_truststore", MagicMock())

    loaded = auth._load()

    assert loaded["access_token"] == "wam-access"
    assert loaded["_auth_method"] == "wam"
    assert auth._wam_tokens is loaded
    assert cache_path.read_bytes() == original
    fake_wam.ensure_valid_tokens.assert_called_once_with()


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


async def test_requirements_accept_silent_wam_cache_without_legacy_json(tmp_path, monkeypatch):
    """Windows broker cache keeps the adapter available after legacy cache loss."""
    from pathlib import Path
    import gateway.platforms.teams_mtk as teams_mtk

    wam_cache = tmp_path / ".teams-automation" / "token_cache.bin"
    wam_cache.parent.mkdir()
    wam_cache.write_text("opaque-msal-cache", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        teams_mtk, "_silent_wam_dependencies_available", lambda: True, raising=False
    )

    assert teams_mtk.check_teams_mtk_requirements() is True


@pytest.mark.asyncio(False)
def test_teams_extra_declares_bounded_windows_broker_runtime():
    """Installing the Teams extra on Windows must provide the WAM broker."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    with pyproject.open("rb") as stream:
        teams_dependencies = tomllib.load(stream)["project"][
            "optional-dependencies"
        ]["teams"]

    assert (
        "pymsalruntime>=0.20.6,<0.22; sys_platform == 'win32'"
        in teams_dependencies
    )


async def test_silent_wam_auth_uses_only_noninteractive_broker_flow(tmp_path, monkeypatch):
    """Background gateway auth must never invoke device flow or an account picker."""
    import gateway.platforms.teams_mtk as teams_mtk

    cache_path = tmp_path / "token_cache.bin"
    cache_path.write_text("{}", encoding="utf-8")
    observed = {}

    class FakeCache:
        has_state_changed = True

        def deserialize(self, serialized):
            observed["serialized"] = serialized

        def serialize(self):
            observed["serialize_called"] = True
            return '{"new":"state"}'

    class FakeApp:
        def get_accounts(self):
            return [{"home_account_id": "account"}]

        def acquire_token_silent(self, scopes, *, account):
            observed["silent"] = (scopes, account)
            return {"access_token": "scope-token", "expires_in": 3600}

    class FakeMsal:
        SerializableTokenCache = FakeCache

        @staticmethod
        def PublicClientApplication(**kwargs):
            observed["app"] = kwargs
            return FakeApp()

    monkeypatch.setattr(
        teams_mtk, "_silent_wam_dependencies_available", lambda: True
    )
    monkeypatch.setitem(sys.modules, "msal", FakeMsal)

    auth = teams_mtk._SilentWamAuth(cache_path)
    result = auth.exchange_for_scope("scope-a offline_access")

    assert result == {"access_token": "scope-token", "expires_in": 3600}
    assert observed["serialized"] == "{}"
    assert observed["app"]["enable_broker_on_windows"] is True
    assert observed["app"]["authority"].endswith("/organizations")
    assert observed["silent"] == (
        ["scope-a"],
        {"home_account_id": "account"},
    )
    assert "serialize_called" not in observed
    assert cache_path.read_text(encoding="utf-8") == "{}"


async def test_silent_wam_pins_skype_account_and_fails_closed_for_later_scopes(
    tmp_path, monkeypatch
):
    """Later scopes must not switch to another cached WAM account."""
    import gateway.platforms.teams_mtk as teams_mtk

    cache_path = tmp_path / "token_cache.bin"
    cache_path.write_text("{}", encoding="utf-8")
    account_a = {"home_account_id": "account-a"}
    account_b = {"home_account_id": "account-b"}
    calls = []

    class FakeCache:
        has_state_changed = False

        def deserialize(self, _serialized):
            pass

    class FakeApp:
        def get_accounts(self):
            return [account_a, account_b]

        def acquire_token_silent(self, scopes, *, account):
            calls.append((scopes, account))
            if scopes == teams_mtk._SilentWamAuth._SKYPE_SCOPE.split():
                return {"access_token": "skype-a"} if account is account_a else None
            # Account B could satisfy Graph, but must never be tried after A is pinned.
            return {"access_token": "graph-b"} if account is account_b else None

    class FakeMsal:
        SerializableTokenCache = FakeCache

        @staticmethod
        def PublicClientApplication(**_kwargs):
            return FakeApp()

    monkeypatch.setattr(
        teams_mtk, "_silent_wam_dependencies_available", lambda: True
    )
    monkeypatch.setitem(sys.modules, "msal", FakeMsal)

    auth = teams_mtk._SilentWamAuth(cache_path)
    skype_result = auth._acquire(auth._SKYPE_SCOPE)
    with pytest.raises(RuntimeError, match="silent WAM token acquisition failed"):
        auth.exchange_for_scope("https://graph.microsoft.com/.default")

    assert skype_result["access_token"] == "skype-a"
    assert auth._pinned_account is account_a
    assert calls == [
        (auth._SKYPE_SCOPE.split(), account_a),
        (["https://graph.microsoft.com/.default"], account_a),
    ]


async def test_missing_json_loads_and_reuses_silent_wam_tokens(tmp_path, monkeypatch):
    """A missing legacy cache falls back to one reusable silent broker session."""
    import gateway.platforms.teams_mtk as teams_mtk

    missing_cache = tmp_path / "token_cache.json"
    fake_wam = MagicMock()
    fake_wam.ensure_valid_tokens.return_value = {
        "access_token": "wam-access",
        "skype_token": "wam-skype",
        "saved_at": 100,
        "expires_in": 3600,
    }
    monkeypatch.setattr(teams_mtk._TeamsAuth, "TOKEN_CACHE", missing_cache)
    monkeypatch.setattr(
        teams_mtk, "_create_silent_wam_auth", lambda: fake_wam, raising=False
    )

    auth = teams_mtk._TeamsAuth()
    first = auth._load()
    second = auth._load()

    assert first["_auth_method"] == "wam"
    assert second is first
    fake_wam.ensure_valid_tokens.assert_called_once_with()


async def test_expired_wam_tokens_refresh_through_broker(tmp_path, monkeypatch):
    """WAM expiry must not fall into the empty refresh-token device-flow path."""
    import gateway.platforms.teams_mtk as teams_mtk

    missing_cache = tmp_path / "token_cache.json"
    old = {
        "access_token": "old",
        "skype_token": "old-skype",
        "saved_at": 1,
        "expires_in": 1,
    }
    new = {
        "access_token": "new",
        "skype_token": "new-skype",
        "saved_at": 200,
        "expires_in": 3600,
    }
    fake_wam = MagicMock()
    fake_wam.ensure_valid_tokens.side_effect = [old, new]
    monkeypatch.setattr(teams_mtk._TeamsAuth, "TOKEN_CACHE", missing_cache)
    monkeypatch.setattr(
        teams_mtk, "_create_silent_wam_auth", lambda: fake_wam, raising=False
    )

    auth = teams_mtk._TeamsAuth()
    monkeypatch.setattr(auth, "_expired", lambda _tokens: True)

    assert auth.tokens()["access_token"] == "new"
    assert fake_wam.ensure_valid_tokens.call_count == 2


async def test_wam_arbitrary_scope_exchange_stays_on_broker(tmp_path, monkeypatch):
    """IC3/Graph scope acquisition must not require a legacy refresh token."""
    import gateway.platforms.teams_mtk as teams_mtk

    fake_wam = MagicMock()
    fake_wam.ensure_valid_tokens.return_value = {
        "access_token": "wam-access",
        "skype_token": "wam-skype",
        "saved_at": 100,
        "expires_in": 3600,
    }
    fake_wam.exchange_for_scope.return_value = {
        "access_token": "scope-token",
        "expires_in": 3600,
    }
    monkeypatch.setattr(
        teams_mtk._TeamsAuth, "TOKEN_CACHE", tmp_path / "missing.json"
    )
    monkeypatch.setattr(
        teams_mtk, "_create_silent_wam_auth", lambda: fake_wam, raising=False
    )

    auth = teams_mtk._TeamsAuth()
    result = auth.exchange_for_scope("scope-a offline_access")

    assert result["access_token"] == "scope-token"
    fake_wam.exchange_for_scope.assert_called_once_with("scope-a offline_access")


async def test_exchange_for_scope_uses_requested_scope_and_persists_rotated_refresh(
    tmp_path, monkeypatch
):
    """IC3/Graph exchanges preserve refresh-token rotation in the shared cache."""
    import base64
    import json
    import uuid
    from gateway.platforms.teams_mtk import _TeamsAuth

    tenant_id = str(uuid.UUID(int=1))
    client_id = str(uuid.UUID(int=2))
    payload = base64.urlsafe_b64encode(
        json.dumps({"tid": tenant_id, "appid": client_id}).encode("utf-8")
    ).decode().rstrip("=")
    cached_access_token = f"header.{payload}.signature"
    cache_path = tmp_path / "token_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "refresh_token": "refresh-old",
                "access_token": cached_access_token,
            }
        )
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
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": "refresh-old",
        "scope": "https://ic3.teams.office.com/Teams.AccessAsUser.All",
    }
    assert tenant_id in post.call_args.args[0]
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

    async def test_send_typing_does_not_block_event_loop(self):
        """A slow typing POST must not delay inbound message dispatch."""
        adapter = _make_adapter()
        entered = threading.Event()
        release = threading.Event()
        mock_resp = MagicMock(status_code=201)

        def _blocking_request(*_args, **_kwargs):
            entered.set()
            release.wait(timeout=1.0)
            return mock_resp

        with patch.object(adapter, "_call_sdk_http", side_effect=_blocking_request), \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            started = asyncio.get_running_loop().time()
            task = asyncio.create_task(adapter.send_typing("19:test@thread.v2"))
            try:
                await asyncio.sleep(0.05)
                elapsed = asyncio.get_running_loop().time() - started
            finally:
                release.set()
                await task

        assert entered.is_set()
        assert elapsed < 0.25, f"typing POST blocked the event loop for {elapsed:.3f}s"

    async def test_send_typing_posts_control_typing(self):
        """send_typing POSTs {"messagetype":"Control/Typing","content":""}."""
        adapter = _make_adapter()
        mock_resp = MagicMock(status_code=201, text='{"OriginalArrivalTime":1}')

        with patch.object(adapter, "_call_sdk_http", return_value=mock_resp) as request, \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            await adapter.send_typing("19:test@thread.v2")

        request.assert_called_once()
        call_args = request.call_args
        assert call_args.args[0] == "POST"
        url = call_args.args[1]
        payload = call_args.kwargs["json"]
        assert "Control/Typing" == payload["messagetype"]
        assert payload["content"] == ""
        assert call_args.kwargs["timeout"] == 10
        assert "19:test@thread.v2" in url

    async def test_send_typing_non_201_logs_warning(self):
        """send_typing logs warning on non-201 but does not raise."""
        adapter = _make_adapter()
        mock_resp = MagicMock(status_code=403, text="forbidden")

        with patch.object(adapter, "_call_sdk_http", return_value=mock_resp) as request, \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            assert await adapter.send_typing("19:test@thread.v2") is False

        request.assert_called_once()

    async def test_send_typing_exception_does_not_raise(self):
        """send_typing swallows exceptions (logging only) so _keep_typing stays alive."""
        adapter = _make_adapter()

        with patch.object(adapter, "_call_sdk_http", side_effect=ConnectionError("network down")) as request, \
             patch.object(adapter._auth, "_msg_base", "https://apac.ng.msg.teams.microsoft.com/v1/users/ME", create=True), \
             patch.object(adapter._auth, "_inject_truststore"):
            assert await adapter.send_typing("19:test@thread.v2") is False

        request.assert_called_once()
