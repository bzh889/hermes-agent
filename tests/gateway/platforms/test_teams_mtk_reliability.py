"""Unit tests for TeamsMTKAdapter reliability (429 handling)."""
from unittest.mock import patch, MagicMock

import pytest
from requests import RequestException, Response

from gateway.platforms.teams_mtk import TeamsMTKAdapter

pytestmark = pytest.mark.asyncio


def _make_adapter():
    """Build a TeamsMTKAdapter without touching the real Teams token cache."""
    return TeamsMTKAdapter(config=None)


def _make_resp(status_code: int, json_body: dict = None) -> Response:
    resp = Response()
    resp.status_code = status_code
    import json as _json
    resp._content = _json.dumps(json_body or {}).encode("utf-8")
    return resp


# ---------------------------------------------------------------------------
# edit_message() 429 handling
# ---------------------------------------------------------------------------


@patch("requests.put")
async def test_edit_message_429_backs_off_and_retries(mock_put):
    """A 429 mid-stream must back off once and retry, returning success if the retry passes."""
    adapter = _make_adapter()
    mock_put.side_effect = [_make_resp(429), _make_resp(200)]

    with patch("gateway.platforms.teams_mtk.asyncio.sleep") as mock_sleep, \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"):

        result = await adapter.edit_message("chat1", "msg1", "<p>content</p>")

        assert result.success is True
        assert mock_put.call_count == 2
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 5.0


@patch("requests.put")
async def test_edit_message_persistent_failure_never_raises(mock_put):
    """If the retry also fails (or a transport error occurs), it must return SendResult(success=False), NEVER raise."""
    adapter = _make_adapter()

    # 1. Persistent 429
    mock_put.side_effect = [_make_resp(429), _make_resp(429)]
    with patch("gateway.platforms.teams_mtk.asyncio.sleep"), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"):
        result1 = await adapter.edit_message("chat1", "msg1", "<p>content</p>")
        assert result1.success is False

    # 2. Transport error (ConnectionError)
    mock_put.side_effect = RequestException("Network down")
    with patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"):
        result2 = await adapter.edit_message("chat1", "msg1", "<p>content</p>")
        assert result2.success is False


def test_edit_message_signature_matches_base():
    """Ensure the signature matches BasePlatformAdapter exactly."""
    import inspect

    adapter_params = list(inspect.signature(TeamsMTKAdapter.edit_message).parameters.keys())

    for p in ["self", "chat_id", "message_id", "content"]:
        assert p in adapter_params, f"edit_message missing '{p}'. Has: {adapter_params}"
    assert "finalize" in adapter_params


# ---------------------------------------------------------------------------
# send() 429 handling
# ---------------------------------------------------------------------------


def _make_session_mock(put_or_post_responses):
    """Build a mock requests.Session() whose .post() yields the given responses in order."""
    session = MagicMock()
    session.post.side_effect = put_or_post_responses
    return session


@patch("requests.Session")
async def test_send_429_backs_off_and_retries(mock_session_cls):
    """send() must back off once on 429 and retry, succeeding if the retry is 200."""
    adapter = _make_adapter()
    mock_session_cls.return_value = _make_session_mock([
        _make_resp(429),
        _make_resp(200, {"id": "msg-123"}),
    ])

    with patch("gateway.platforms.teams_mtk.asyncio.sleep") as mock_sleep, \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"):

        result = await adapter.send("chat1", "hello world")

        assert result.success is True
        assert result.message_id == "msg-123"
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 5.0


@patch("requests.Session")
async def test_send_persistent_429_returns_failure_not_raises(mock_session_cls):
    """Persistent 429 across both attempts must return SendResult(success=False), never raise."""
    adapter = _make_adapter()
    mock_session_cls.return_value = _make_session_mock([
        _make_resp(429),
        _make_resp(429),
    ])

    with patch("gateway.platforms.teams_mtk.asyncio.sleep"), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"):

        result = await adapter.send("chat1", "hello world")
        assert result.success is False


@patch("requests.Session")
async def test_send_401_refresh_still_works(mock_session_cls):
    """401 -> force_refresh -> retry flow must remain unaffected by 429 handling."""
    adapter = _make_adapter()
    mock_session_cls.return_value = _make_session_mock([
        _make_resp(401),
        _make_resp(200, {"id": "msg-456"}),
    ])

    with patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"), \
         patch.object(adapter._auth, "_force_refresh") as mock_refresh:

        result = await adapter.send("chat1", "hello world")

        assert result.success is True
        mock_refresh.assert_called_once()
