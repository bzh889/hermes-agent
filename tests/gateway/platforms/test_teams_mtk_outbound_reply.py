"""Behavior contracts for Teams MTK outbound native replies."""

import json

from unittest.mock import MagicMock, patch

import pytest

from gateway.platforms import teams_mtk as teams_mtk_module
from gateway.platforms.teams_mtk import TeamsMTKAdapter

pytestmark = pytest.mark.asyncio


def _adapter() -> TeamsMTKAdapter:
    """Build an adapter without reading live Teams credentials."""
    return TeamsMTKAdapter(config=None)


def _raw_send_session(message_id: str) -> MagicMock:
    response = MagicMock(status_code=201)
    response.json.return_value = {"OriginalArrivalTime": message_id}
    session = MagicMock()
    session.post.return_value = response
    return session


def _reply_sdk_layer(source_id: str) -> MagicMock:
    layer = MagicMock()
    layer._session = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "id": source_id,
        "content": "<p>exact reply source</p>",
        "from": "https://msg.example.invalid/contacts/source-alias",
    }
    layer._request.return_value = response
    return layer


async def test_reply_target_uses_native_sdk_reply_and_records_ownership():
    adapter = _adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.invalid/v1/users/ME"
    layer = _reply_sdk_layer("target-message-alias")
    service = MagicMock()
    service.reply.return_value = {"OriginalArrivalTime": "reply-message-alias"}

    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer),
        patch("gateway.platforms.teams_mtk._SDKMessages", return_value=service),
    ):
        result = await adapter.send(
            "conversation-alias",
            "native reply marker",
            reply_to="target-message-alias",
        )

    assert result.success is True
    assert result.message_id == "reply-message-alias"
    assert result.raw_response == {
        "native_reply": {
            "status": "preserved",
            "relation_preserved": True,
        }
    }
    service.send.assert_not_called()
    service.reply.assert_called_once()
    service.reply.assert_called_once_with(
        conversation_id="conversation-alias",
        message_id="target-message-alias",
        content="native reply marker",
        return_context=False,
    )
    assert adapter._is_sent_message(
        "conversation-alias", "reply-message-alias"
    ) is True
    assert adapter._is_sent_message(
        "other-conversation", "reply-message-alias"
    ) is False


async def test_native_reply_pins_exact_source_before_sdk_bounded_lookup():
    adapter = _adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.invalid/v1/users/ME"

    class Response:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class Http:
        def __init__(self):
            self.exact_fetches = 0
            self.regional_page_fetches = 0
            self.bounded_fetches = 0
            self.post_urls = []
            self._session = MagicMock()

        def _request(self, method, url, **kwargs):
            if method == "GET" and url.endswith(
                "/conversations/conversation-alias/messages/target-message-alias"
            ):
                self.exact_fetches += 1
                return Response(
                    {
                        "id": "target-message-alias",
                        "content": "",
                        "from": "https://msg.example.invalid/contacts/source-alias",
                    }
                )
            if (
                method == "GET"
                and url.endswith("/conversations/conversation-alias/messages")
                and kwargs.get("params", {}).get("pageSize") == 100
            ):
                self.regional_page_fetches += 1
                return Response(
                    {
                        "messages": [
                            {
                                "id": "target-message-alias",
                                "content": "<p>complete canonical source</p>",
                                "from": (
                                    "https://msg.example.invalid/contacts/source-alias"
                                ),
                            }
                        ]
                    }
                )
            if method == "GET":
                self.bounded_fetches += 1
                return Response({"messages": [{"id": "unrelated-recent-message"}]})
            if method == "POST":
                self.post_urls.append(url)
                return Response({"OriginalArrivalTime": "reply-message-alias"})
            raise AssertionError("unexpected direct transport call")

    observed_sources = []

    class BusyHistoryMessagesService:
        def __init__(self, http):
            self._http = http

        def reply(self, *, conversation_id, message_id, content, return_context):
            del content, return_context
            page = self._http._request(
                "GET",
                (
                    "https://amer.ng.msg.teams.microsoft.com/v1/users/ME/conversations/"
                    f"{conversation_id}/messages"
                ),
                params={"pageSize": 5},
            ).json()
            observed_sources.extend(page["messages"])
            observed_source_ids = {
                str(message.get("id") or "") for message in observed_sources
            }
            if message_id not in observed_source_ids:
                raise RuntimeError("SDK bounded lookup missed exact reply source")
            if not any(message.get("content") for message in observed_sources):
                raise RuntimeError("SDK reply source content remained partial")
            return self._http._request(
                "POST",
                (
                    "https://amer.ng.msg.teams.microsoft.com/v1/users/ME/conversations/"
                    f"{conversation_id}/messages"
                ),
                json={"content": "native reply"},
            ).json()

    http = Http()
    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=http),
        patch(
            "gateway.platforms.teams_mtk._SDKMessages",
            BusyHistoryMessagesService,
        ),
    ):
        result = await adapter.send(
            "conversation-alias",
            "native reply marker",
            reply_to="target-message-alias",
        )

    assert result.success is True
    assert [source["id"] for source in observed_sources] == [
        "target-message-alias"
    ]
    assert http.exact_fetches == 1
    assert http.regional_page_fetches == 1
    assert http.bounded_fetches == 0
    assert http.post_urls == [
        "https://msg.example.invalid/v1/users/ME/conversations/"
        "conversation-alias/messages"
    ]


@pytest.mark.parametrize("sdk_available", [False, True])
async def test_pre_send_native_reply_unavailable_degrades_once(
    sdk_available, caplog
):
    adapter = _adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.invalid/v1/users/ME"
    adapter._auth.skype_token.return_value = "token"
    session = _raw_send_session("flat-message-alias")

    class SendOnlyMessagesService:
        """An older SDK shape whose class has no native reply operation."""

        init_count = 0

        def __init__(self, _http):
            type(self).init_count += 1

        def send(self, **_kwargs):
            raise AssertionError("pre-send capability gate must choose raw fallback")

    with (
        patch(
            "gateway.platforms.teams_mtk._SDK_AVAILABLE", sdk_available
        ),
        patch(
            "gateway.platforms.teams_mtk._SDKMessages",
            SendOnlyMessagesService,
        ),
        patch("requests.Session", return_value=session),
        caplog.at_level("WARNING", logger="gateway.platforms.teams_mtk"),
    ):
        result = await adapter.send(
            "private-conversation-alias",
            "flat fallback marker",
            reply_to="private-target-alias",
        )

    assert result.success is True
    assert result.message_id == "flat-message-alias"
    assert result.raw_response == {
        "native_reply": {
            "status": "degraded",
            "relation_preserved": False,
            "reason": "sdk_unavailable",
        }
    }
    session.post.assert_called_once()
    payload = session.post.call_args.kwargs["json"]
    assert payload["content"]
    assert payload["properties"] == {"hermes_sender": "agent"}
    assert SendOnlyMessagesService.init_count == 0
    assert "native reply unavailable before send" in caplog.text.lower()
    assert "private-conversation-alias" not in caplog.text
    assert "private-target-alias" not in caplog.text


async def test_native_reply_indeterminate_outcome_never_flat_resends(caplog):
    adapter = _adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.invalid/v1/users/ME"
    layer = _reply_sdk_layer("uncertain-target-alias")
    service = MagicMock()
    service.reply.side_effect = ConnectionError("response lost after POST")
    session = _raw_send_session("must-not-be-sent")

    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer),
        patch("gateway.platforms.teams_mtk._SDKMessages", return_value=service),
        patch("requests.Session", return_value=session),
        caplog.at_level("ERROR", logger="gateway.platforms.teams_mtk"),
    ):
        result = await adapter.send(
            "uncertain-conversation-alias",
            "uncertain native marker",
            reply_to="uncertain-target-alias",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.error is not None
    assert "native reply delivery uncertain" in result.error.lower()
    assert result.raw_response == {
        "native_reply": {
            "status": "uncertain",
            "relation_preserved": None,
        }
    }
    service.reply.assert_called_once()
    service.send.assert_not_called()
    session.post.assert_not_called()
    assert adapter._is_sent_message(
        "uncertain-conversation-alias", "must-not-be-sent"
    ) is False
    assert "native reply failed" in caplog.text.lower()
    assert "raw fallback suppressed" in caplog.text.lower()
    assert "uncertain-conversation-alias" not in caplog.text
    assert "uncertain-target-alias" not in caplog.text


async def test_native_reply_missing_id_recovers_only_matching_relation():
    adapter = _adapter()
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://msg.example.invalid/v1/users/ME"
    layer = _reply_sdk_layer("target-message-alias")
    service = MagicMock()
    service.reply.return_value = {"id": ""}
    reply_content = "recover native reply marker"

    readback = [
        {
            "id": "unrelated-reply-alias",
            "_raw_content": f"<blockquote>other relation</blockquote>{reply_content}",
            "_raw_properties": {
                "hermes_sender": "bot",
                "replyChainMessageId": "other-target-alias",
            },
        },
        {
            "id": "recovered-reply-alias",
            "_raw_content": (
                "<blockquote>matching native relation</blockquote>"
                f"{reply_content}"
            ),
            "_raw_properties": {
                "hermes_sender": "bot",
                "replyChainMessageId": "target-message-alias",
            },
        },
    ]

    with (
        patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True),
        patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=layer),
        patch("gateway.platforms.teams_mtk._SDKMessages", return_value=service),
        patch.object(adapter, "_fetch_messages", return_value=readback),
    ):
        result = await adapter.send(
            "conversation-alias",
            "recover native reply marker",
            reply_to="target-message-alias",
        )

    assert result.success is True
    assert result.message_id == "recovered-reply-alias"
    assert adapter._is_sent_message(
        "conversation-alias", "recovered-reply-alias"
    ) is True
    assert adapter._is_sent_message(
        "conversation-alias", "unrelated-reply-alias"
    ) is False


async def test_sdk_native_reply_preserves_pre_rendered_html_and_relations():
    class Response:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    class Http:
        def __init__(self):
            self.calls = []
            self.converted = []

        def _request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if method == "GET":
                return Response(
                    {
                        "messages": [
                            {
                                "id": "100",
                                "imdisplayname": "Source Author",
                                "from": (
                                    "https://msg.example.invalid/contacts/"
                                    "8:orgid:source-author-alias"
                                ),
                                "content": "<p>source preview</p>",
                            }
                        ]
                    }
                )
            return Response({"OriginalArrivalTime": "200"})

        def _markdown_to_teams_html(self, content):
            self.converted.append(content)
            return content

        @staticmethod
        def _extract_text_content(content):
            return content

        @staticmethod
        def _format_timestamp(_value):
            return ""

    http = Http()
    rendered = '<div data-hermes="marker"><p>native body</p></div>'
    messages_service_type = teams_mtk_module._SDKMessages
    assert messages_service_type is not None
    result = messages_service_type(http).reply(
        "conversation-alias",
        "100",
        rendered,
        return_context=False,
    )

    assert result["id"] == "200"
    assert http.converted == [rendered]
    assert [method for method, _url, _kwargs in http.calls] == ["GET", "POST"]
    payload = http.calls[-1][2]["json"]
    assert payload["content"].endswith(rendered)
    assert 'itemtype="http://schema.skype.com/Reply"' in payload["content"]
    assert payload["properties"]["replyChainMessageId"] == "100"
    assert payload["properties"]["hermes_sender"] == "bot"
    assert json.loads(payload["properties"]["qtdMsgs"])[0]["messageId"] == "100"
