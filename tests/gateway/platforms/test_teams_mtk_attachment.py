"""Unit tests for TeamsMTKAdapter attachment handling.

Covers:
- _download_attachment(): image/file download → cache, error cases
- _process_new_messages(): attachment extraction from 4 sources
  (<img>, <file>, properties.files, attachments[])
- media_urls / media_types / MessageType assignment
"""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from gateway.platforms.teams_mtk import TeamsMTKAdapter
from gateway.platforms.base import MessageEvent, MessageType

pytestmark = pytest.mark.asyncio


class _ChunkedBody:
    def __init__(self, *chunks):
        self._chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


def _aiohttp_response(*, status=200, body=b"content", headers=None):
    response = AsyncMock()
    response.status = status
    response.headers = headers or {}
    response.content = _ChunkedBody(body)

    response_context = AsyncMock()
    response_context.__aenter__ = AsyncMock(return_value=response)
    response_context.__aexit__ = AsyncMock(return_value=False)
    return response, response_context


def _aiohttp_module(*response_contexts):
    session = AsyncMock()
    session.get = MagicMock(side_effect=response_contexts)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    aiohttp = MagicMock()
    aiohttp.ClientSession = MagicMock(return_value=session)
    aiohttp.ClientTimeout = MagicMock(return_value=object())
    return aiohttp, session


def _make_adapter():
    """Build a TeamsMTKAdapter without touching the real Teams token cache."""
    return TeamsMTKAdapter(config=None)


# ---------------------------------------------------------------------------
# _download_attachment()
# ---------------------------------------------------------------------------


async def test_download_attachment_image():
    """_download_attachment for image: aiohttp get → cache_image_from_bytes."""
    adapter = _make_adapter()
    fake_bytes = bytes.fromhex("89504e470d0a1a0a")

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {}
    mock_resp.content = _ChunkedBody(fake_bytes)

    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_sess_ctx = AsyncMock()
    mock_sess_ctx.get = MagicMock(return_value=mock_get_ctx)
    mock_sess_ctx.__aenter__ = AsyncMock(return_value=mock_sess_ctx)
    mock_sess_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession = MagicMock(return_value=mock_sess_ctx)
    mock_aiohttp.ClientTimeout = MagicMock(return_value=object())

    mock_cache = MagicMock(return_value="/tmp/hermes_cache/img1.jpg")

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}), \
         patch("gateway.platforms.base.cache_image_from_bytes", mock_cache), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"):

        # Need to invalidate the module-level import in teams_mtk
        # by making the local import use our mock
        import gateway.platforms.teams_mtk as _mod
        # The function does `import aiohttp` locally, but with sys.modules
        # patched it will pick up our mock.

        result = await adapter._download_attachment(
            "https://example.com/photo.png", "image", ""
        )

    assert result == "/tmp/hermes_cache/img1.jpg"


async def test_download_attachment_file():
    """_download_attachment for file: aiohttp get → cache_document_from_bytes."""
    adapter = _make_adapter()
    fake_bytes = b"%PDF-1.4"

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {}
    mock_resp.content = _ChunkedBody(fake_bytes)

    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_sess_ctx = AsyncMock()
    mock_sess_ctx.get = MagicMock(return_value=mock_get_ctx)
    mock_sess_ctx.__aenter__ = AsyncMock(return_value=mock_sess_ctx)
    mock_sess_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession = MagicMock(return_value=mock_sess_ctx)
    mock_aiohttp.ClientTimeout = MagicMock(return_value=object())

    mock_cache = MagicMock(return_value="/tmp/hermes_cache/doc1.pdf")

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}), \
         patch("gateway.platforms.base.cache_document_from_bytes", mock_cache), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"):

        result = await adapter._download_attachment(
            "https://example.com/report.pdf", "file", "report.pdf"
        )

    assert result == "/tmp/hermes_cache/doc1.pdf"
    mock_cache.assert_called_once_with(fake_bytes, "report.pdf")


async def test_download_attachment_http_403_returns_none():
    """Non-200 response → returns None."""
    adapter = _make_adapter()

    mock_resp = AsyncMock()
    mock_resp.status = 403

    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_sess_ctx = AsyncMock()
    mock_sess_ctx.get = MagicMock(return_value=mock_get_ctx)
    mock_sess_ctx.__aenter__ = AsyncMock(return_value=mock_sess_ctx)
    mock_sess_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession = MagicMock(return_value=mock_sess_ctx)
    mock_aiohttp.ClientTimeout = MagicMock(return_value=object())

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"):

        result = await adapter._download_attachment(
            "https://example.com/forbidden.png", "image", ""
        )

    assert result is None


async def test_download_attachment_cache_error_returns_none():
    """If cache helper raises, returns None (no crash)."""
    adapter = _make_adapter()
    fake_bytes = b"\x89PNG"

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.headers = {}
    mock_resp.content = _ChunkedBody(fake_bytes)

    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_sess_ctx = AsyncMock()
    mock_sess_ctx.get = MagicMock(return_value=mock_get_ctx)
    mock_sess_ctx.__aenter__ = AsyncMock(return_value=mock_sess_ctx)
    mock_sess_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession = MagicMock(return_value=mock_sess_ctx)
    mock_aiohttp.ClientTimeout = MagicMock(return_value=object())

    mock_cache = MagicMock(side_effect=RuntimeError("disk full"))

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}), \
         patch("gateway.platforms.base.cache_image_from_bytes", mock_cache), \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"):

        result = await adapter._download_attachment(
            "https://example.com/photo.png", "image", ""
        )

    assert result is None


@pytest.mark.parametrize(
    ("url", "expected_headers"),
    [
        (
            "https://as-api.asm.skype.com/v1/objects/object-id/views/imgpsh_fullsize",
            {"Authorization": "skype_token skype-token"},
        ),
        (
            "https://as-prod.asyncgw.teams.microsoft.com/v1/objects/object-id",
            {"Authentication": "skypetoken=skype-token"},
        ),
        (
            "https://tenant.sharepoint.com/shared/file.txt",
            {"Authorization": "Bearer access-token"},
        ),
    ],
)
async def test_download_attachment_fallback_uses_domain_auth(url, expected_headers):
    """Raw fallback must preserve the SDK's per-domain authentication rules."""
    adapter = _make_adapter()
    response = AsyncMock()
    response.status = 200
    response.headers = {}
    response.content = _ChunkedBody(b"content")

    response_context = AsyncMock()
    response_context.__aenter__ = AsyncMock(return_value=response)
    response_context.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=response_context)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    aiohttp = MagicMock()
    aiohttp.ClientSession = MagicMock(return_value=session)
    aiohttp.ClientTimeout = MagicMock(return_value=object())

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch("tools.url_safety.async_is_safe_url", return_value=True),
        patch("gateway.platforms.base.cache_document_from_bytes", return_value="cached"),
        patch.object(adapter._auth, "skype_token", return_value="skype-token"),
        patch.object(adapter._auth, "access_token", return_value="access-token"),
    ):
        result = await adapter._download_attachment(url, "file", "file.txt")

    assert result == "cached"
    aiohttp.ClientSession.assert_called_once_with()
    assert session.get.call_args.kwargs["headers"] == expected_headers


@pytest.mark.parametrize(
    "url",
    [
        "http://tenant.sharepoint.com/file.txt",
        "https://127.0.0.1/file.txt",
        "https://169.254.169.254/latest/meta-data",
    ],
)
async def test_download_attachment_rejects_unsafe_url_before_reading_tokens(url):
    adapter = _make_adapter()
    aiohttp, _session = _aiohttp_module()

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch.object(adapter._auth, "skype_token") as skype_token,
        patch.object(adapter._auth, "access_token") as access_token,
    ):
        result = await adapter._download_attachment(url, "file", "file.txt")

    assert result is None
    skype_token.assert_not_called()
    access_token.assert_not_called()
    aiohttp.ClientSession.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://public.example/file.txt",
        "https://teams.microsoft.com.attacker.example/file.txt",
        "https://sharepoint.com.attacker.example/file.txt",
    ],
)
async def test_download_attachment_unknown_or_lookalike_host_sends_no_credentials(url):
    adapter = _make_adapter()
    _response, response_context = _aiohttp_response()
    aiohttp, session = _aiohttp_module(response_context)

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch("tools.url_safety.async_is_safe_url", return_value=True),
        patch("gateway.platforms.base.cache_document_from_bytes", return_value="cached"),
        patch.object(adapter._auth, "skype_token") as skype_token,
        patch.object(adapter._auth, "access_token") as access_token,
    ):
        result = await adapter._download_attachment(url, "file", "file.txt")

    assert result == "cached"
    skype_token.assert_not_called()
    access_token.assert_not_called()
    assert session.get.call_args.kwargs["headers"] == {}


async def test_download_attachment_redirect_revalidates_and_drops_credentials():
    adapter = _make_adapter()
    _redirect, redirect_context = _aiohttp_response(
        status=302,
        body=b"",
        headers={"Location": "https://public.example/download.txt"},
    )
    _final, final_context = _aiohttp_response(body=b"safe")
    aiohttp, session = _aiohttp_module(redirect_context, final_context)

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch("tools.url_safety.async_is_safe_url", return_value=True),
        patch("gateway.platforms.base.cache_document_from_bytes", return_value="cached"),
        patch.object(adapter._auth, "access_token", return_value="access-token"),
    ):
        result = await adapter._download_attachment(
            "https://tenant.sharepoint.com/file.txt", "file", "file.txt"
        )

    assert result == "cached"
    assert session.get.call_count == 2
    first, second = session.get.call_args_list
    assert first.kwargs["headers"] == {"Authorization": "Bearer access-token"}
    assert first.kwargs["allow_redirects"] is False
    assert second.args[0] == "https://public.example/download.txt"
    assert second.kwargs["headers"] == {}


async def test_download_attachment_blocks_unsafe_redirect_before_request():
    adapter = _make_adapter()
    _redirect, redirect_context = _aiohttp_response(
        status=302,
        body=b"",
        headers={"Location": "https://169.254.169.254/latest/meta-data"},
    )
    aiohttp, session = _aiohttp_module(redirect_context)

    async def safe_initial_only(candidate):
        return candidate.startswith("https://tenant.sharepoint.com/")

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch("tools.url_safety.async_is_safe_url", side_effect=safe_initial_only),
        patch.object(adapter._auth, "access_token", return_value="access-token"),
    ):
        result = await adapter._download_attachment(
            "https://tenant.sharepoint.com/file.txt", "file", "file.txt"
        )

    assert result is None
    assert session.get.call_count == 1


async def test_download_attachment_rejects_oversized_stream_before_cache():
    adapter = _make_adapter()
    _response, response_context = _aiohttp_response(body=b"1234")
    aiohttp, _session = _aiohttp_module(response_context)

    with (
        patch.dict("sys.modules", {"aiohttp": aiohttp}),
        patch("tools.url_safety.async_is_safe_url", return_value=True),
        patch("gateway.platforms.base.get_inbound_media_max_bytes", return_value=3),
        patch("gateway.platforms.base.cache_document_from_bytes") as cache,
    ):
        result = await adapter._download_attachment(
            "https://public.example/file.txt", "file", "file.txt"
        )

    assert result is None
    cache.assert_not_called()


# ---------------------------------------------------------------------------
# _process_new_messages() – attachment extraction
# ---------------------------------------------------------------------------


async def _run_process(adapter, conv_id, messages, download_side_effect=None):
    """Call _process_new_messages with everything mocked.

    Returns the MessageEvent passed to handle_message (or None if not called).
    """
    if download_side_effect is None:
        download_side_effect = AsyncMock(return_value="/tmp/cached")

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as mock_handle, \
         patch.object(adapter._auth, "skype_token", return_value="fake_token"), \
         patch.object(adapter._auth, "_inject_truststore"), \
         patch.object(adapter, "_download_attachment", download_side_effect), \
         patch.object(adapter, "_message_handler", create=True, new=AsyncMock()):

        await adapter._process_new_messages(conv_id, messages)

    if mock_handle.called:
        return mock_handle.call_args[0][0]
    return None


async def test_process_new_messages_inline_image():
    """HTML <img src=...> should be extracted as an image attachment."""
    adapter = _make_adapter()
    conv_id = "19:dm123@unq.gbl.spaces"  # DM — no mention gate
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg1",
        "messagetype": "Text",
        "content": '<p>Hello</p><img src="https://example.com/img.png" alt="photo">',
        "imdisplayname": "Alice",
        "from": "8:orgid:12345",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert isinstance(event, MessageEvent)
    assert event.media_urls == ["/tmp/cached"]
    assert event.media_types == ["image"]
    assert event.message_type == MessageType.PHOTO


async def test_process_new_messages_file_tag():
    """HTML <file src=... name=...> should be extracted as a file attachment."""
    adapter = _make_adapter()
    conv_id = "19:dm456@unq.gbl.spaces"  # DM — no mention gate
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg2",
        "messagetype": "Text",
        "content": '<p>See report</p><file src="https://example.com/report.pdf" name="Q2 Report.pdf">',
        "imdisplayname": "Bob",
        "from": "8:orgid:67890",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert event.media_urls == ["/tmp/cached"]
    assert event.media_types == ["file"]
    assert event.message_type == MessageType.DOCUMENT


async def test_process_new_messages_properties_files():
    """properties.files array should be extracted as file attachments."""
    adapter = _make_adapter()
    conv_id = "19:dm789@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg3",
        "messagetype": "Text",
        "content": "<p>Shared a file</p>",
        "imdisplayname": "Carol",
        "from": "8:orgid:11111",
        "properties": {
            "files": [
                {"contentUrl": "https://example.com/data.xlsx", "name": "data.xlsx"}
            ],
        },
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert event.media_urls == ["/tmp/cached"]
    assert event.media_types == ["file"]


async def test_process_new_messages_top_level_attachments_image():
    """Top-level 'attachments' array with contentType image/* should be image."""
    adapter = _make_adapter()
    conv_id = "19:dm000@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg4",
        "messagetype": "Text",
        "content": "<p>Diagram</p>",
        "imdisplayname": "Dave",
        "from": "8:orgid:22222",
        "properties": {},
        "attachments": [
            {"contentUrl": "https://example.com/diagram.png", "name": "diagram.png", "contentType": "image/png"}
        ],
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert event.media_types == ["image"]
    assert event.message_type == MessageType.PHOTO


async def test_process_new_messages_attachment_only_no_text():
    """Message with only an <img> (no visible text) should get '[attachment]' placeholder."""
    adapter = _make_adapter()
    conv_id = "19:dm001@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg5",
        "messagetype": "Text",
        "content": '<img src="https://example.com/photo.jpg">',
        "imdisplayname": "Eve",
        "from": "8:orgid:33333",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert event.text == "[attachment]"
    assert event.media_urls == ["/tmp/cached"]


async def test_process_new_messages_multiple_attachments():
    """Multiple attachments: 2 images + 1 file = 3 media_urls."""
    adapter = _make_adapter()
    conv_id = "19:dm002@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg6",
        "messagetype": "Text",
        "content": '<p>See these</p><img src="https://a.com/1.png"><img src="https://b.com/2.gif">',
        "imdisplayname": "Frank",
        "from": "8:orgid:44444",
        "properties": {
            "files": [
                {"contentUrl": "https://c.com/doc.pdf", "name": "doc.pdf"}
            ],
        },
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert len(event.media_urls) == 3
    assert event.media_types == ["image", "image", "file"]


async def test_process_new_messages_download_failure_skips():
    """If _download_attachment returns None, that attachment is skipped."""
    adapter = _make_adapter()
    conv_id = "19:dm003@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg7",
        "messagetype": "Text",
        "content": '<img src="https://bad.com/404.png"><p>text</p>',
        "imdisplayname": "Grace",
        "from": "8:orgid:55555",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages,
                               download_side_effect=AsyncMock(return_value=None))

    # No successful download → media_urls is None (empty list coerced)
    assert event.media_urls is None or event.media_urls == []
    assert event.media_types is None or event.media_types == []
    assert event.message_type == MessageType.TEXT


async def test_process_new_messages_no_attachments():
    """Plain text message with no attachments should have no media_urls."""
    adapter = _make_adapter()
    conv_id = "19:dm004@unq.gbl.spaces"
    adapter._last_message_ids[conv_id] = "msg0"

    messages = [{
        "id": "msg8",
        "messagetype": "Text",
        "content": "<p>Just a plain message</p>",
        "imdisplayname": "Hank",
        "from": "8:orgid:66666",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages)

    assert event.media_urls is None or event.media_urls == []
    assert event.media_types is None or event.media_types == []
    assert event.message_type == MessageType.TEXT


async def test_process_new_messages_group_require_mention_with_attachment():
    """In a group with require_mention, an attachment-only message without
    @hermes should be skipped (not passed to handle_message)."""
    adapter = _make_adapter()
    conv_id = "19:meeting@thread.v2"
    adapter._last_message_ids[conv_id] = "msg0"
    adapter.require_mention = True  # global default

    messages = [{
        "id": "msg9",
        "messagetype": "Text",
        "content": '<img src="https://example.com/pic.jpg">',
        "imdisplayname": "Ivan",
        "from": "8:orgid:77777",
        "properties": {},
    }]

    event = await _run_process(adapter, conv_id, messages)

    # Message should be skipped (no @hermes in a require_mention group)
    assert event is None
