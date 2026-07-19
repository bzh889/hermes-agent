"""Unit tests for TeamsMTKAdapter S7 (Reactions) and S9 (Message Deletion)."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import requests

from gateway.platforms.teams_mtk import (
    TeamsMTKAdapter,
    _SDKGraphAdapter,
    _VALID_REACTIONS,
)


_EXPECTED_REACTION_EMOJI = {
    "like": "👍",
    "heart": "❤️",
    "laugh": "😄",
    "surprised": "😮",
    "sad": "😢",
    "angry": "😡",
}


def _make_adapter():
    return TeamsMTKAdapter(config=None)


def test_graph_request_adds_auth_and_checks_status():
    adapter = _make_adapter()
    response = MagicMock()
    with patch.object(adapter._auth, "_inject_truststore"), \
         patch.object(adapter._auth, "graph_token", return_value="graph-token"), \
         patch("requests.request", return_value=response) as request:
        result = adapter._auth._graph_request(
            "POST", "https://graph.microsoft.com/beta/example", json={"x": 1}
        )

    assert result is response
    response.raise_for_status.assert_called_once_with()
    request.assert_called_once_with(
        "POST",
        "https://graph.microsoft.com/beta/example",
        headers={
            "Authorization": "Bearer graph-token",
            "Content-Type": "application/json",
        },
        verify=True,
        timeout=30,
        json={"x": 1},
    )


def test_sdk_graph_adapter_request_delegates_to_gateway_graph_transport():
    gateway_auth = MagicMock()
    response = MagicMock()
    gateway_auth._graph_request.return_value = response

    transport = _SDKGraphAdapter(gateway_auth)
    assert transport.verify_ssl is True
    result = transport._request(
        "POST", "https://graph.microsoft.com/beta/test", json={"x": 1}
    )

    assert result is response
    gateway_auth._graph_request.assert_called_once_with(
        "POST", "https://graph.microsoft.com/beta/test", json={"x": 1}
    )


# ── S7: Reactions ──────────────────────────────────────────────────────

class TestSendReaction:
    @pytest.mark.asyncio
    async def test_invalid_reaction(self):
        adapter = _make_adapter()
        result = await adapter.send_reaction("conv1", "msg1", "invalid_emoji")
        assert result["status"] == "error"
        assert "Invalid reaction" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_reaction_sdk_path(self):
        adapter = _make_adapter()
        mock_result = {"status": "reacted", "reaction": "like", "message_id": "msg1"}
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKReactions") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKGraphAdapter") as MockGraph, \
             patch.object(adapter._auth, "graph_token", return_value="fake-token"):
            graph_transport = MagicMock()
            MockGraph.return_value = graph_transport
            mock_svc_instance = MagicMock()
            mock_svc_instance.send.return_value = mock_result
            MockSvc.return_value = mock_svc_instance
            result = await adapter.send_reaction("conv1", "msg1", "like")
            assert result["status"] == "reacted"
            MockSvc.assert_called_once_with(graph_transport)

    @pytest.mark.asyncio
    async def test_valid_reaction_raw_fallback(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request") as request:
            result = await adapter.send_reaction("conv1", "msg1", "like")

        assert result == {"status": "reacted", "reaction": "like", "message_id": "msg1"}
        request.assert_called_once_with(
            "POST",
            "https://graph.microsoft.com/beta/chats/conv1/messages/msg1/setReaction",
            json={"reactionType": "👍"},
        )

    @pytest.mark.asyncio
    async def test_raw_duplicate_reaction_is_idempotent(self):
        adapter = _make_adapter()
        response = MagicMock(status_code=409)
        error = requests.HTTPError(response=response)
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request", side_effect=error):
            result = await adapter.send_reaction("conv1", "msg1", "like")

        assert result == {
            "status": "reacted",
            "reaction": "like",
            "message_id": "msg1",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reaction,emoji", sorted(_EXPECTED_REACTION_EMOJI.items()))
    async def test_all_valid_reactions_use_real_graph_payload(self, reaction, emoji):
        """Every supported name must execute production code and send its emoji."""
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request") as request:
            result = await adapter.send_reaction("conv1", "msg1", reaction)

        assert result == {
            "status": "reacted",
            "reaction": reaction,
            "message_id": "msg1",
        }
        request.assert_called_once_with(
            "POST",
            "https://graph.microsoft.com/beta/chats/conv1/messages/msg1/setReaction",
            json={"reactionType": emoji},
        )


class TestRemoveReaction:
    @pytest.mark.asyncio
    async def test_invalid_reaction(self):
        adapter = _make_adapter()
        result = await adapter.remove_reaction("conv1", "msg1", "notreal")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_valid_reaction_sdk_path(self):
        adapter = _make_adapter()
        mock_result = {"status": "removed", "reaction": "heart", "message_id": "msg1"}
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKReactions") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKGraphAdapter") as MockGraph, \
             patch.object(adapter._auth, "graph_token", return_value="fake-token"):
            graph_transport = MagicMock()
            MockGraph.return_value = graph_transport
            mock_svc_instance = MagicMock()
            mock_svc_instance.remove.return_value = mock_result
            MockSvc.return_value = mock_svc_instance
            result = await adapter.remove_reaction("conv1", "msg1", "heart")
            assert result["status"] == "removed"
            MockSvc.assert_called_once_with(graph_transport)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reaction,emoji", sorted(_EXPECTED_REACTION_EMOJI.items()))
    async def test_all_valid_reactions_remove_real_graph_payload(self, reaction, emoji):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request") as request:
            result = await adapter.remove_reaction("conv1", "msg1", reaction)

        assert result == {
            "status": "removed",
            "reaction": reaction,
            "message_id": "msg1",
        }
        request.assert_called_once_with(
            "POST",
            "https://graph.microsoft.com/beta/chats/conv1/messages/msg1/unsetReaction",
            json={"reactionType": emoji},
        )

    @pytest.mark.asyncio
    async def test_raw_missing_reaction_is_idempotent(self):
        adapter = _make_adapter()
        response = MagicMock(status_code=404)
        error = requests.HTTPError(response=response)
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request", side_effect=error):
            result = await adapter.remove_reaction("conv1", "msg1", "like")

        assert result == {
            "status": "removed",
            "reaction": "like",
            "message_id": "msg1",
        }

    @pytest.mark.asyncio
    async def test_error_handling(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "_graph_request", side_effect=RuntimeError("boom")):
            result = await adapter.remove_reaction("conv1", "msg1", "like")
            assert result == {"status": "error", "error": "boom"}


# ── S9: Message Deletion ──────────────────────────────────────────────

class TestDeleteMessage:
    @pytest.mark.asyncio
    async def test_sdk_path(self):
        adapter = _make_adapter()
        adapter._auth._skype_token = "fake-skype"
        mock_result = {"id": "msg1", "status": "deleted"}
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKMessages") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            mock_svc_instance = MagicMock()
            mock_svc_instance.delete.return_value = mock_result
            MockSvc.return_value = mock_svc_instance
            result = await adapter.delete_message("conv1", "msg1")
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False):
            result = await adapter.delete_message("conv1", "msg1")
            assert "status" in result

    @pytest.mark.asyncio
    async def test_raw_path_uses_regional_msg_base_and_skypetoken_header(self):
        """Raw delete must hit the regional MSG endpoint with the MSG-API auth
        header — NOT hardcoded amer + ``Authorization: skype_token``.

        The Teams MSG API authenticates with ``Authentication: skypetoken=<t>``
        (same header ``send``/``edit_message``/``send_typing`` already use), and
        the endpoint is the region discovered at auth time (``_auth.msg_base``),
        not a hardcoded amer host. The previous fallback sent the Skype token as
        an ``Authorization: skype_token`` bearer against amer, which 401s / hits
        the wrong region for non-amer tenants.
        """
        adapter = _make_adapter()
        adapter._auth._msg_base = "https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
        response = MagicMock()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "skype_token", return_value="fake-skype") as token, \
             patch("requests.delete", return_value=response) as delete:
            result = await adapter.delete_message("conv1", "msg1")

        assert result == {"id": "msg1", "status": "deleted"}
        token.assert_called_once_with()
        response.raise_for_status.assert_called_once_with()
        delete.assert_called_once_with(
            "https://apac.ng.msg.teams.microsoft.com/v1/users/ME/conversations/conv1/messages/msg1",
            headers={"Authentication": "skypetoken=fake-skype"},
            verify=True,
            timeout=30,
        )


# ── S10: Message Forwarding (raw fallback auth) ───────────────────────

class TestForwardMessageRawFallback:
    @pytest.mark.asyncio
    async def test_raw_fetch_uses_regional_msg_base_and_skypetoken_header(self):
        """Raw forward fetch must call skype_token() (not pass the bound method)
        and use the regional MSG endpoint + ``Authentication: skypetoken=`` header.

        The old fallback formatted ``self._auth.skype_token`` (the METHOD object,
        not its return value) into an ``Authorization: skype_token`` header against
        a hardcoded amer host — so the fetch authenticated with garbage and hit the
        wrong region. It must mirror delete/send: regional ``msg_base`` +
        ``Authentication: skypetoken=<token>``.
        """
        adapter = _make_adapter()
        adapter._auth._msg_base = "https://emea.ng.msg.teams.microsoft.com/v1/users/ME"
        fetch_resp = MagicMock()
        fetch_resp.json.return_value = {
            "messages": [{"id": "msg1", "imdisplayname": "Alice", "content": "hi"}]
        }
        adapter.send = AsyncMock(return_value={"status": "sent"})
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
             patch.object(adapter._auth, "skype_token", return_value="fake-skype") as token, \
             patch("requests.get", return_value=fetch_resp) as get:
            result = await adapter.forward_message("src", "msg1", "dst")

        assert result == {"status": "sent"}
        # Token accessor was actually CALLED (not passed as a bound method).
        assert token.call_count >= 1
        get.assert_called_once_with(
            "https://emea.ng.msg.teams.microsoft.com/v1/users/ME/conversations/src/messages",
            headers={"Authentication": "skypetoken=fake-skype"},
            params={"pageSize": 50},
            verify=True,
            timeout=30,
        )
        adapter.send.assert_awaited_once()


# ── VALID_REACTIONS constant ──────────────────────────────────────────

class TestValidReactions:
    def test_standard_six(self):
        assert _VALID_REACTIONS == {"like", "heart", "laugh", "surprised", "sad", "angry"}

    def test_no_empty(self):
        for r in _VALID_REACTIONS:
            assert len(r) > 0
