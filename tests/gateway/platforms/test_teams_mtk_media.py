"""Unit tests for TeamsMTKAdapter G-MEDIA: send_image_file, send_image, send_document.

Covers teams-mtk-hermes-native-parity change:
- send_image_file(): AMS 3-step upload flow (create -> upload -> send)
- send_image(): remote URL download -> AMS -> inline, or AMS URL direct embed
- send_document(): OneDrive Graph upload + share link + message
- graph_token(): Graph API token acquisition via refresh_token

Key protocol details (verified E2E against real AMS API):
- Auth header: "Authorization: skype_token {token}" (NOT skypetoken=, NOT Bearer)
- AMS create body: {"type": "pish/image", "permissions": {conv_id: ["read"]}}
- Upload URL: /v1/objects/{id}/content/imgpsh (NOT /content/original)
- User-Agent: "27/1.0.0.0" (Teams desktop UA, required by AMS)
- HTML markup: <div itemscope itemtype="http://schema.skype.com/AMSImage">...
- Message payload includes "amsreferences": [object_id]
- Document upload: Graph API PUT /me/drive/root:/{name}:/content
- Share link: Graph API POST /items/{id}/createLink
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter():
    """Create a TeamsMTKAdapter with auth dependency-injected."""
    from gateway.platforms.teams_mtk import TeamsMTKAdapter, _TeamsAuth

    adapter = TeamsMTKAdapter(config=None)
    mock_auth = MagicMock(spec=_TeamsAuth)
    mock_auth.skype_token.return_value = "fake_skype_token_123"
    mock_auth.graph_token.return_value = "fake_graph_token_456"
    mock_auth.msg_base = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
    mock_auth._inject_truststore = MagicMock()
    adapter._auth = mock_auth
    adapter._reply_throttle_seconds = 0
    from gateway.platforms.helpers import MessageDeduplicator
    adapter._sent_dedup = MessageDeduplicator()
    adapter.send = AsyncMock(return_value=MagicMock(success=True))
    return adapter


def _mock_post_fn(status_code=201, json_data=None):
    """Create a mock function that returns a response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    fn = MagicMock(return_value=resp)
    return fn


def _mock_put_fn(status_code=201, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    fn = MagicMock(return_value=resp)
    return fn


# ---------------------------------------------------------------------------
# graph_token tests
# ---------------------------------------------------------------------------

class TestGraphToken:
    """Test _TeamsAuth.graph_token()."""

    def test_graph_token_uses_refresh_token(self, tmp_path):
        """graph_token() should call the token endpoint with graph scope."""
        import threading, time
        from gateway.platforms.teams_mtk import _TeamsAuth

        auth = _TeamsAuth.__new__(_TeamsAuth)
        auth._lock = threading.Lock()
        auth._inject_truststore = MagicMock()
        auth._load = MagicMock(return_value={
            "refresh_token": "rt_123",
            "graph_token_saved_at": 0,  # expired → force refresh
            "graph_token_expires_in": 0,
        })
        auth._save = MagicMock()

        with patch("requests.post", return_value=MagicMock(
            status_code=200,
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"access_token": "new_graph_at", "expires_in": 3600}),
        )) as mock_post:

            result = auth.graph_token()
            assert result == "new_graph_at"

            body = mock_post.call_args.kwargs.get("data") or mock_post.call_args[1].get("data", {})
            scope_val = body.get("scope", "") if isinstance(body, dict) else ""
            assert "graph.microsoft.com" in scope_val

    def test_graph_token_caches_result(self, tmp_path):
        """graph_token() should use cached result when still valid."""
        import threading, time
        from gateway.platforms.teams_mtk import _TeamsAuth

        auth = _TeamsAuth.__new__(_TeamsAuth)
        auth._lock = threading.Lock()
        auth._inject_truststore = MagicMock()
        auth._load = MagicMock(return_value={
            "graph_token": "cached_graph_at",
            "graph_token_saved_at": time.time(),  # fresh
            "graph_token_expires_in": 3600,
        })

        result = auth.graph_token()
        assert result == "cached_graph_at"


# ---------------------------------------------------------------------------
# send_image_file tests
# ---------------------------------------------------------------------------

class TestSendImageFile:
    """Test send_image_file() - AMS 3-step upload."""

    @pytest.fixture
    def adapter(self):
        return _make_adapter()

    @pytest.fixture
    def img_file(self, tmp_path):
        p = tmp_path / "test.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return p

    def test_ams_create_uses_correct_auth_and_body(self, adapter, img_file):
        """Verify AMS create POST uses skype_token auth + pish/image + permissions."""
        mock_post = _mock_post_fn(201, {"id": "obj_123"})
        # Second call to requests.post = message send
        mock_post_2 = _mock_post_fn(201, {"id": "msg_456"})
        mock_post.side_effect = [mock_post.return_value, mock_post_2.return_value]
        mock_put_upload = _mock_put_fn(201)

        with patch("requests.post", mock_post), \
             patch("requests.put", mock_put_upload):

            result = asyncio.run(adapter.send_image_file("conv1", str(img_file)))
            assert result.success is True

            # AMS create call (first requests.post call)
            create_call = mock_post.call_args_list[0]
            headers = create_call.kwargs.get("headers") or create_call[1].get("headers")
            assert headers["Authorization"] == "skype_token fake_skype_token_123"
            assert headers["User-Agent"] == "27/1.0.0.0"

            body = create_call.kwargs.get("json") or create_call[1].get("json")
            assert body["type"] == "pish/image"
            assert "conv1" in body["permissions"]

    def test_ams_upload_uses_imgpsh_path(self, adapter, img_file):
        """Verify upload PUT uses /content/imgpsh."""
        mock_post = _mock_post_fn(201, {"id": "obj_123"})
        mock_post_2 = _mock_post_fn(201, {"id": "msg_456"})
        mock_post.side_effect = [mock_post.return_value, mock_post_2.return_value]
        mock_put_upload = _mock_put_fn(201)

        with patch("requests.post", mock_post), \
             patch("requests.put", mock_put_upload):

            result = asyncio.run(adapter.send_image_file("conv1", str(img_file)))
            assert result.success is True

            put_call = mock_put_upload.call_args
            url = put_call.args[0] if put_call.args else put_call.kwargs.get("url", "")
            assert "/content/imgpsh" in url

    def test_ams_message_includes_amsreferences(self, adapter, img_file):
        """Verify message includes amsreferences."""
        mock_post = _mock_post_fn(201, {"id": "obj_123"})
        mock_post_2 = _mock_post_fn(201, {"id": "msg_456"})
        mock_post.side_effect = [mock_post.return_value, mock_post_2.return_value]
        mock_put_upload = _mock_put_fn(201)

        with patch("requests.post", mock_post), \
             patch("requests.put", mock_put_upload):

            result = asyncio.run(adapter.send_image_file("conv1", str(img_file)))
            assert result.success is True

            # Second requests.post call = message send
            msg_call = mock_post.call_args_list[1]
            payload = msg_call.kwargs.get("json") or msg_call[1].get("json")
            assert "amsreferences" in payload
            assert payload["amsreferences"] == ["obj_123"]

    def test_ams_message_uses_schema_markup(self, adapter, img_file):
        """Verify HTML uses AMSImage schema markup."""
        mock_post = _mock_post_fn(201, {"id": "obj_123"})
        mock_post_2 = _mock_post_fn(201, {"id": "msg_456"})
        mock_post.side_effect = [mock_post.return_value, mock_post_2.return_value]
        mock_put_upload = _mock_put_fn(201)

        with patch("requests.post", mock_post), \
             patch("requests.put", mock_put_upload):

            result = asyncio.run(adapter.send_image_file("conv1", str(img_file)))
            assert result.success is True

            # Second requests.post call = message send
            msg_call = mock_post.call_args_list[1]
            payload = msg_call.kwargs.get("json") or msg_call[1].get("json")
            html = payload["content"]
            assert "schema.skype.com/AMSImage" in html
            assert 'itemid="obj_123"' in html


# ---------------------------------------------------------------------------
# send_image tests
# ---------------------------------------------------------------------------

class TestSendImage:
    """Test send_image() - remote URL and AMS URL."""

    @pytest.fixture
    def adapter(self):
        return _make_adapter()

    def test_ams_url_direct_embed_uses_schema(self, adapter):
        """AMS URLs should embed with schema markup."""
        mock_post = _mock_post_fn(201, {"id": "msg_789"})

        with patch("requests.post", mock_post):

            result = asyncio.run(adapter.send_image(
                "conv1",
                "https://api.asm.skype.com/v1/objects/abc/views/imgo",
            ))
            assert result.success is True

            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            html = payload["content"]
            assert "schema.skype.com/AMSImage" in html

    def test_remote_url_calls_send_image_file(self, adapter):
        """Non-AMS URLs should download and delegate to send_image_file."""
        mock_dl = MagicMock()
        mock_dl.status_code = 200
        mock_dl.headers = {"Content-Type": "image/png"}
        mock_dl.iter_content = MagicMock(return_value=[b"\x89PNG\r\n\x1a\n"])

        adapter.send_image_file = AsyncMock(return_value=MagicMock(success=True))

        with patch("requests.get", return_value=mock_dl):
            result = asyncio.run(adapter.send_image(
                "conv1",
                "https://example.com/photo.png",
                caption="Test caption",
            ))
            assert result.success is True
            adapter.send_image_file.assert_called_once()


# ---------------------------------------------------------------------------
# send_document tests
# ---------------------------------------------------------------------------

class TestSendDocument:
    """Test send_document() - OneDrive Graph API + share."""

    @pytest.fixture
    def adapter(self):
        return _make_adapter()

    @pytest.fixture
    def doc_file(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("Hello world")
        return p

    def test_document_uploads_via_graph_api(self, adapter, doc_file):
        """Verify file is uploaded via Graph PUT."""
        mock_put_upload = _mock_put_fn(201, {"id": "item_abc", "name": "test.txt"})
        # First requests.post = share link, second = message send
        mock_post = _mock_post_fn(201, {"link": {"webUrl": "https://share.link/test.txt"}})
        mock_post_msg = _mock_post_fn(201, {"id": "msg_doc_1"})
        mock_post.side_effect = [mock_post.return_value, mock_post_msg.return_value]

        with patch("requests.put", mock_put_upload), \
             patch("requests.post", mock_post):

            result = asyncio.run(adapter.send_document("conv1", str(doc_file)))
            assert result.success is True

            put_call = mock_put_upload.call_args
            url = put_call.args[0] if put_call.args else put_call.kwargs.get("url", "")
            assert "graph.microsoft.com" in url
            headers = put_call.kwargs.get("headers") or put_call[1].get("headers")
            assert headers["Authorization"] == "Bearer fake_graph_token_456"

    def test_document_creates_share_link(self, adapter, doc_file):
        """Verify sharing link creation via Graph createLink."""
        mock_put_upload = _mock_put_fn(201, {"id": "item_abc", "name": "test.txt"})
        mock_post = _mock_post_fn(201, {"link": {"webUrl": "https://share.link/test.txt"}})
        mock_post_msg = _mock_post_fn(201, {"id": "msg_doc_1"})
        mock_post.side_effect = [mock_post.return_value, mock_post_msg.return_value]

        with patch("requests.put", mock_put_upload), \
             patch("requests.post", mock_post):

            result = asyncio.run(adapter.send_document("conv1", str(doc_file)))
            assert result.success is True

            # First requests.post call = share link creation
            share_call = mock_post.call_args_list[0]
            url = share_call.args[0] if share_call.args else share_call.kwargs.get("url", "")
            assert "createLink" in url
            body = share_call.kwargs.get("json") or share_call[1].get("json")
            assert body["type"] == "view"

    def test_document_message_has_clickable_link(self, adapter, doc_file):
        """Verify message contains clickable link."""
        mock_put_upload = _mock_put_fn(201, {"id": "item_abc", "name": "test.txt"})
        mock_post = _mock_post_fn(201, {"link": {"webUrl": "https://share.link/test.txt"}})
        mock_post_msg = _mock_post_fn(201, {"id": "msg_doc_1"})
        mock_post.side_effect = [mock_post.return_value, mock_post_msg.return_value]

        with patch("requests.put", mock_put_upload), \
             patch("requests.post", mock_post):

            result = asyncio.run(adapter.send_document("conv1", str(doc_file)))
            assert result.success is True

            # Second requests.post call = message send
            msg_call = mock_post.call_args_list[1]
            payload = msg_call.kwargs.get("json") or msg_call[1].get("json")
            html = payload["content"]
            assert "https://share.link/test.txt" in html
            assert "test.txt" in html

    def test_document_fallback_on_upload_failure(self, adapter, doc_file):
        """If Graph upload fails, fall back to text notice."""
        mock_put_upload = _mock_put_fn(403)
        mock_put_upload.return_value.text = "Forbidden"

        with patch("requests.put", mock_put_upload):
            result = asyncio.run(adapter.send_document("conv1", str(doc_file)))
            adapter.send.assert_called_once()


# ---------------------------------------------------------------------------
# G-MEDIA-4: send_adaptive_card tests
# ---------------------------------------------------------------------------

class TestSendAdaptiveCard:
    """Test TeamsMTKAdapter.send_adaptive_card() — G-MEDIA-4."""

    @pytest.fixture
    def adapter(self):
        return _make_adapter()

    def test_disabled_sends_fallback_text(self, adapter):
        """When adaptive_cards.enabled=False, fallback_text goes via send()."""
        with patch("hermes_cli.config.load_config_readonly",
                   return_value={"gateway": {"teams_mtk": {"adaptive_cards": {"enabled": False}}}}):
            result = asyncio.run(adapter.send_adaptive_card("conv1", {"type": "AdaptiveCard"}, "plain fallback"))
            adapter.send.assert_called_once_with(chat_id="conv1", content="plain fallback", metadata=None)

    def test_disabled_no_fallback_returns_error(self, adapter):
        """When disabled and no fallback, return error."""
        with patch("hermes_cli.config.load_config_readonly",
                   return_value={"gateway": {"teams_mtk": {"adaptive_cards": {"enabled": False}}}}):
            result = asyncio.run(adapter.send_adaptive_card("conv1", {"type": "AdaptiveCard"}))
            assert result.success is False
            assert "disabled" in (result.error or "")

    def test_enabled_sends_card_attachment(self, adapter):
        """When enabled, POST the card via properties.cards (skype-native encoding).

        NOTE: the top-level "attachments" array (Bot Framework/Graph convention)
        is silently dropped by the skype consumer messaging endpoint — verified
        via real POST+GET readback 2026-07-11. properties.cards (JSON-stringified
        list) is the encoding that actually persists server-side.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "msg-ac-1"}
        mock_resp.raise_for_status = MagicMock()
        mock_post = MagicMock(return_value=mock_resp)

        card = {"type": "AdaptiveCard", "version": "1.4", "body": [
            {"type": "TextBlock", "text": "Hello"}]}
        with patch("hermes_cli.config.load_config_readonly",
                   return_value={"gateway": {"teams_mtk": {"adaptive_cards": {"enabled": True}}}}), \
             patch("requests.post", mock_post):
            result = asyncio.run(adapter.send_adaptive_card("conv1", card, "fallback"))

            assert result.success is True
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert payload["messagetype"] == "RichText/Html"
            cards = json.loads(payload["properties"]["cards"])
            assert len(cards) == 1
            assert cards[0]["contentType"] == "application/vnd.microsoft.card.adaptive"
            assert cards[0]["content"]["type"] == "AdaptiveCard"

    def test_send_failure_falls_back_to_text(self, adapter):
        """If card POST fails, send fallback text via send()."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("Server error")
        mock_post = MagicMock(return_value=mock_resp)

        card = {"type": "AdaptiveCard", "version": "1.4", "body": []}
        with patch("hermes_cli.config.load_config_readonly",
                   return_value={"gateway": {"teams_mtk": {"adaptive_cards": {"enabled": True}}}}), \
             patch("requests.post", mock_post):
            result = asyncio.run(adapter.send_adaptive_card("conv1", card, "fallback text"))
            adapter.send.assert_called_once_with(chat_id="conv1", content="fallback text", metadata=None)
