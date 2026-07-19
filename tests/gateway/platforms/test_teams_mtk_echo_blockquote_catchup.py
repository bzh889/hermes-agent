"""Behavior tests for TeamsMTK echo, blockquote, and catchup guards."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gateway.platforms.teams_mtk as teams_mtk_module
from gateway.platforms.teams_mtk import TeamsMTKAdapter, _clean_message_content


class TestEchoGuardOwnership:
    @staticmethod
    def _message(msg_id: str) -> dict:
        return {
            "id": msg_id,
            "messagetype": "RichText/Html",
            "content": "Please explain this quote",
            "_raw_content": (
                '<blockquote><div style="border-left:3px solid #6264A7">'
                "<b>🤖 Hermes</b> quoted text</div></blockquote>"
            ),
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Foreign User",
            "from": "8:orgid:foreign-user",
        }

    @pytest.mark.asyncio
    async def test_foreign_branded_html_is_dispatched(self):
        adapter = TeamsMTKAdapter(config=None)
        adapter._message_handler = AsyncMock()
        conv_id = "48:notes"
        adapter._last_message_ids[conv_id] = "0"

        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
            await adapter._process_new_messages(conv_id, [self._message("1")])

        handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tracked_outbound_id_is_suppressed(self):
        adapter = TeamsMTKAdapter(config=None)
        adapter._message_handler = AsyncMock()
        conv_id = "48:notes"
        adapter._last_message_ids[conv_id] = "0"
        adapter._remember_sent_message(conv_id, "1")

        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
            await adapter._process_new_messages(conv_id, [self._message("1")])

        handle.assert_not_awaited()


class TestBlockquoteForwardedMessage:
    def test_user_text_plus_forwarded_blockquote(self):
        content = (
            '<div><p>Check this out</p>'
            '<blockquote itemscope itemtype="http://schema.org/Quote">'
            '<p>🤖 Hermes found something</p></blockquote></div>'
        )

        text, _ = _clean_message_content(content)

        assert "Check this out" in text
        assert "[forwarded message:" in text

    def test_pure_blockquote_forward_is_empty(self):
        content = (
            '<blockquote itemscope itemtype="http://schema.org/Quote">'
            '<p>🤖 Hermes found something</p></blockquote>'
        )

        text, _ = _clean_message_content(content)

        assert text == ""

    def test_no_blockquote_normal_message(self):
        text, _ = _clean_message_content("<p>Hello world</p>")

        assert text == "Hello world"

    def test_multiple_blockquotes_keeps_user_text(self):
        content = (
            '<div><p>My comment</p>'
            '<blockquote>first fwd</blockquote>'
            '<blockquote>second fwd</blockquote></div>'
        )

        text, _ = _clean_message_content(content)

        assert "My comment" in text
        assert "[forwarded message:" in text

    def test_fallback_without_sdk_preserves_mention_and_forwarded_context(self):
        content = (
            '<at id="28:x">hermes</at> check this'
            '<blockquote>quoted answer</blockquote>'
        )

        with patch.object(teams_mtk_module, "_strip_teams_html", None):
            text, images = _clean_message_content(content)

        assert "@hermes check this" in text
        assert "[forwarded message: quoted answer…]" in text
        assert images == []

    def test_fallback_without_sdk_drops_pure_blockquote(self):
        with patch.object(teams_mtk_module, "_strip_teams_html", None):
            text, images = _clean_message_content("<blockquote>quoted answer</blockquote>")

        assert text == ""
        assert images == []


class TestColdStartCatchup:
    @staticmethod
    def _unanswered_messages() -> list[dict]:
        return [
            {"id": "100", "content": "old conversation", "properties": {"hermes_sender": "agent"}},
            {"id": "200", "content": "unrelated", "properties": {}},
            {"id": "300", "content": '<at id="28:x">@hermes</at> help me', "properties": {}},
        ]

    def test_catchup_seeds_before_unanswered_mention(self):
        adapter = TeamsMTKAdapter(config=None)
        adapter._group_config = lambda _conv_id: {"require_mention": True}

        seed = adapter._cold_start_seed_id(
            "19:group@thread.v2",
            self._unanswered_messages(),
        )

        assert seed == "200"

    def test_existing_hermes_reply_seeds_latest(self):
        messages = [
            {"id": "100", "content": "@hermes help", "properties": {}},
            {"id": "200", "content": "Here is help", "properties": {"hermes_sender": "agent"}},
        ]
        adapter = TeamsMTKAdapter(config=None)
        adapter._group_config = lambda _conv_id: {"require_mention": True}

        assert adapter._cold_start_seed_id("19:group@thread.v2", messages) == "200"

    def test_branded_html_is_not_treated_as_owned(self):
        messages = [
            {"id": "100", "content": "old", "properties": {}},
            {
                "id": "200",
                "content": (
                    '<div style="border-left:3px solid #6264A7">'
                    "<b>🤖 Hermes</b> quoted by a user</div>"
                ),
                "properties": {},
            },
        ]
        adapter = TeamsMTKAdapter(config=None)

        assert adapter._cold_start_seed_id("48:notes", messages) == "100"

    @pytest.mark.asyncio
    async def test_connect_uses_catchup_seed(self):
        adapter = TeamsMTKAdapter(config=None)
        conv_id = "19:group@thread.v2"
        adapter._conv_ids = [conv_id]
        adapter._group_config = lambda _conv_id: {"require_mention": True}
        adapter._auth.skype_token = MagicMock(return_value="token")
        adapter._fetch_messages = MagicMock(return_value=self._unanswered_messages())
        adapter._poll_loop = AsyncMock()
        listener = MagicMock()

        with patch.object(teams_mtk_module, "_TrouterListener", return_value=listener), \
             patch.object(adapter, "_mark_connected"):
            connected = await adapter.connect()

        assert connected is True
        assert adapter._last_message_ids[conv_id] == "200"
        listener.start.assert_called_once()
