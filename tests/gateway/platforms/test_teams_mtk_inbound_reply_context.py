"""Behavior contracts for complete Teams native-reply context."""

import json
from unittest.mock import AsyncMock, patch

import pytest

import gateway.platforms.teams_mtk as teams_mtk


@pytest.mark.parametrize(
    ("properties", "expected_quoted_messages"),
    [
        (
            {
                "replyChainMessageId": "source-message",
                "qtdMsgs": [{"messageId": "source-message"}],
            },
            [{"messageId": "source-message"}],
        ),
        (
            json.dumps(
                {
                    "replyChainMessageId": "source-message",
                    "qtdMsgs": json.dumps([{"messageId": "source-message"}]),
                }
            ),
            [{"messageId": "source-message"}],
        ),
    ],
)
def test_sdk_normalized_output_retains_compatible_reply_metadata_without_rewriting_body(
    properties,
    expected_quoted_messages,
):
    reply_body = "Use the revised requirement from my reply."
    normalized = teams_mtk.normalize_teams_sdk_message(
        {
            "id": "reply-message",
            "content": (
                '<blockquote itemtype="http://schema.skype.com/Reply" '
                'itemid="source-message"><p itemprop="preview">short preview</p>'
                f"</blockquote><p>{reply_body}</p>"
            ),
            "properties": properties,
        },
        {
            "id": "reply-message",
            "content": reply_body,
            "sender": "Test User",
        },
    )

    assert normalized["content"] == reply_body
    assert normalized["reply_to_message_id"] == "source-message"
    assert normalized["_reply_chain_message_id"] == "source-message"
    assert normalized["_quoted_messages"] == expected_quoted_messages
    assert normalized["_blockquote_message_id"] == "source-message"


def _normalize_reply(*, reply_chain=None, quoted_ids=(), blockquote_id=None):
    properties = {
        "qtdMsgs": [{"messageId": message_id} for message_id in quoted_ids],
    }
    if reply_chain is not None:
        properties["replyChainMessageId"] = reply_chain
    blockquote = (
        '<blockquote itemtype="http://schema.skype.com/Reply" '
        f'itemid="{blockquote_id}"><p itemprop="preview">preview</p></blockquote>'
        if blockquote_id is not None
        else ""
    )
    return teams_mtk.normalize_teams_sdk_message(
        {
            "id": "reply-message",
            "content": f"{blockquote}<p>current reply body</p>",
            "properties": properties,
        },
        {"id": "reply-message", "content": "current reply body"},
    )


def test_reply_relation_corroboration_selects_the_common_source():
    normalized = _normalize_reply(
        reply_chain="common-source",
        quoted_ids=("common-source",),
        blockquote_id="common-source",
    )

    assert normalized["reply_to_message_id"] == "common-source"
    assert normalized["_reply_relation_status"] == "corroborated"


def test_secondary_relations_corroborate_when_blockquote_id_is_on_time_element():
    normalized = teams_mtk.normalize_teams_sdk_message(
        {
            "id": "reply-message",
            "content": (
                '<blockquote itemtype="http://schema.skype.com/Reply">'
                '<span itemprop="time" itemid="common-source"></span>'
                '<p itemprop="preview">short preview</p></blockquote>'
                "<p>current reply body</p>"
            ),
            "properties": {
                "qtdMsgs": [{"messageId": "common-source"}],
            },
        },
        {"id": "reply-message", "content": "current reply body"},
    )

    assert normalized["reply_to_message_id"] == "common-source"
    assert normalized["_blockquote_message_id"] == "common-source"
    assert normalized["_reply_relation_status"] == "corroborated"


def test_reply_chain_remains_authoritative_when_other_relations_disagree(caplog):
    with caplog.at_level("WARNING", logger="gateway.platforms.teams_mtk"):
        normalized = _normalize_reply(
            reply_chain="chain-source-private",
            quoted_ids=("quoted-source-private",),
            blockquote_id="blockquote-source-private",
        )

    assert normalized["reply_to_message_id"] == "chain-source-private"
    assert normalized["_reply_relation_status"] == "disagreed"
    assert "relation disagreement" in caplog.text
    assert "sha256:" in caplog.text
    assert "chain-source-private" not in caplog.text
    assert "quoted-source-private" not in caplog.text
    assert "blockquote-source-private" not in caplog.text


def test_conflicting_secondary_relations_without_reply_chain_fail_closed(caplog):
    with caplog.at_level("WARNING", logger="gateway.platforms.teams_mtk"):
        normalized = _normalize_reply(
            quoted_ids=("quoted-source-private",),
            blockquote_id="blockquote-source-private",
        )

    assert "reply_to_message_id" not in normalized
    assert normalized["_reply_relation_status"] == "disagreed"


def _native_reply_message():
    properties = {
        "replyChainMessageId": "100",
        "qtdMsgs": [{"messageId": "100"}],
    }
    message = teams_mtk.normalize_teams_sdk_message(
        {
            "id": "200",
            "content": (
                '<blockquote itemtype="http://schema.skype.com/Reply" '
                'itemid="100"><p itemprop="preview">short preview</p></blockquote>'
                "<p>apply the revised request</p>"
            ),
            "properties": properties,
        },
        {
            "id": "200",
            "content": "apply the revised request",
            "sender": "Reply Author",
        },
    )
    message.update(
        {
            "messagetype": "RichText/Html",
            "imdisplayname": "Reply Author",
            "from": "8:orgid:reply-author-alias",
            "properties": properties,
        }
    )
    return message


@pytest.mark.asyncio
async def test_native_reply_dispatch_populates_complete_exact_source_context():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._last_message_ids["conversation-alias"] = "0"
    exact_calls = []

    class Response:
        def json(self):
            return {
                "id": "100",
                "content": "<p>complete source body including terminal sentinel</p>",
                "from": "https://msg.example/contacts/8:orgid:source-author-alias",
                "imdisplayname": "Source Author",
                "properties": {},
            }

    class Http:
        _session = None

        def _request(self, method, url):
            exact_calls.append((method, url))
            return Response()

    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=Http()),
        patch.object(adapter._auth, "_inject_truststore"),
        patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle,
    ):
        await adapter._process_new_messages(
            "conversation-alias",
            [_native_reply_message()],
        )

    assert handle.await_args is not None
    event = handle.await_args.args[0]
    assert event.text == "apply the revised request"
    assert event.reply_to_message_id == "100"
    assert event.reply_to_text == "complete source body including terminal sentinel"
    assert event.reply_to_author_id == "source-author-alias"
    assert event.reply_to_author_name == "Source Author"
    assert event.reply_to_is_own_message is False
    assert event.reply_to_text_complete is True
    assert event.metadata == {}
    assert exact_calls == [
        (
            "GET",
            f"{adapter._auth.msg_base}/conversations/"
            "conversation-alias/messages/100",
        )
    ]


@pytest.mark.asyncio
async def test_native_reply_dispatch_uses_exact_raw_fallback_when_sdk_unavailable():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._last_message_ids["conversation-alias"] = "0"
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "id": "100",
                "from": "source-author-alias",
                "imdisplayname": "Source Author",
                "content": (
                    "<p>misleading preview "
                    + ("padding " * 80)
                    + "terminal requirement: use blue</p>"
                ),
                "properties": {},
            }

    class Session:
        def mount(self, *_args, **_kwargs):
            return None

        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        def close(self):
            calls.append(("closed", {}))

    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False),
        patch("requests.Session", return_value=Session()),
        patch.object(adapter._auth, "_inject_truststore"),
        patch.object(adapter._auth, "skype_token", return_value="token-alias"),
        patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle,
    ):
        await adapter._process_new_messages(
            "conversation-alias",
            [_native_reply_message()],
        )

    assert handle.await_args is not None
    event = handle.await_args.args[0]
    assert event.reply_to_message_id == "100"
    assert event.reply_to_text.endswith("terminal requirement: use blue")
    assert event.reply_to_text_complete is True
    assert event.metadata == {}
    url, kwargs = calls[0]
    assert url.endswith("/conversations/conversation-alias/messages/100")
    assert kwargs["headers"] == {"Authentication": "skypetoken=token-alias"}
    assert kwargs["verify"] is True
    assert kwargs["timeout"] == 15
    assert calls[-1] == ("closed", {})


@pytest.mark.asyncio
async def test_native_reply_exact_fetch_failure_never_promotes_preview_to_context(caplog):
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._last_message_ids["conversation-alias"] = "0"

    class FailingHttp:
        _session = None

        def _request(self, _method, _url):
            raise RuntimeError(
                "source-id-private short preview private terminal sentinel private"
            )

    class FailingSession:
        def mount(self, *_args, **_kwargs):
            return None

        def get(self, _url, **_kwargs):
            raise RuntimeError(
                "source-id-private short preview private terminal sentinel private"
            )

        def close(self):
            return None

    with (
        caplog.at_level("WARNING", logger="gateway.platforms.teams_mtk"),
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=FailingHttp()),
        patch("requests.Session", return_value=FailingSession()),
        patch.object(adapter._auth, "_inject_truststore"),
        patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle,
    ):
        await adapter._process_new_messages(
            "conversation-alias",
            [_native_reply_message()],
        )

    assert handle.await_args is not None
    event = handle.await_args.args[0]
    assert event.text == "apply the revised request"
    assert event.reply_to_message_id == "100"
    assert event.reply_to_text is None
    assert event.reply_to_author_id is None
    assert event.reply_to_author_name is None
    assert event.reply_to_is_own_message is False
    assert event.reply_to_text_complete is False
    assert event.metadata == {}
    assert "reply source fetch failed" in caplog.text
    assert "source-id-private" not in caplog.text
    assert "short preview private" not in caplog.text
    assert "terminal sentinel private" not in caplog.text
