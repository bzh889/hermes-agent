"""Behavior contracts for same-identity Teams inbound revisions."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

import gateway.platforms.teams_mtk as teams_mtk


def test_sdk_normalized_output_preserves_raw_revision_inputs():
    raw_properties = json.dumps({"edittime": 1720000000123, "custom": True})
    raw_message = {
        "id": 1720000000000,
        "content": "<p>complete corrected body</p>",
        "properties": raw_properties,
        "version": 1720000000456,
    }
    sdk_normalized = {
        "id": 1720000000000,
        "content": "complete corrected body",
        "sender": "User",
    }

    normalized = teams_mtk.normalize_teams_sdk_message(
        raw_message,
        sdk_normalized,
    )

    assert normalized["_raw_id"] == raw_message["id"]
    assert normalized["_raw_content"] == raw_message["content"]
    assert normalized["_raw_properties"] == raw_properties
    assert normalized["_raw_version"] == raw_message["version"]
    assert normalized["_raw_edit_time"] == 1720000000123
    assert isinstance(normalized["_raw_id"], int)
    assert isinstance(normalized["_raw_properties"], str)
    assert isinstance(normalized["_raw_version"], int)
    assert isinstance(normalized["_raw_edit_time"], int)


def _inbound_message(
    *,
    message_id: str = "100",
    body: str,
    version=None,
    edit_time=None,
    properties=None,
) -> dict:
    raw_properties = properties if properties is not None else {}
    if edit_time is not None:
        raw_properties = {**raw_properties, "edittime": edit_time}
    return {
        "id": message_id,
        "messagetype": "Text",
        "content": body,
        "_raw_content": body,
        "properties": raw_properties,
        "_raw_properties": raw_properties,
        "version": version,
        "_raw_version": version,
        "_raw_edit_time": edit_time,
        "imdisplayname": "Test User",
        "from": "8:orgid:test-user",
    }


@pytest.mark.asyncio
async def test_same_identity_dispatches_one_complete_changed_revision_only():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"
    original = _inbound_message(
        body="original body",
        version=1,
        edit_time=1000,
    )
    revised = _inbound_message(
        body="complete corrected body",
        version="2",
        edit_time="2000",
    )

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [revised])
        await adapter._process_new_messages(conversation_id, [revised])

    assert handle.await_count == 2
    dispatched_events = [call.args[0] for call in handle.await_args_list]
    assert [event.text for event in dispatched_events] == [
        "original body",
        "complete corrected body",
    ]


@pytest.mark.asyncio
async def test_content_hash_detects_revision_when_explicit_metadata_is_absent():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(
            conversation_id,
            [_inbound_message(body="first complete body")],
        )
        await adapter._process_new_messages(
            conversation_id,
            [_inbound_message(body="revised complete body")],
        )

    assert [call.args[0].text for call in handle.await_args_list] == [
        "first complete body",
        "revised complete body",
    ]


@pytest.mark.asyncio
async def test_explicit_revision_change_dispatches_even_when_content_is_unchanged():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(
            conversation_id,
            [_inbound_message(body="same body", version=1)],
        )
        await adapter._process_new_messages(
            conversation_id,
            [_inbound_message(body="same body", version="2")],
        )

    assert handle.await_count == 2


@pytest.mark.asyncio
async def test_overlapping_sources_dispatch_the_same_revision_once():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"
    original = _inbound_message(body="original body", version=1)
    revised = _inbound_message(body="revised body", version=2)

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(conversation_id, [original])
        await asyncio.gather(
            adapter._process_new_messages(conversation_id, [revised]),
            adapter._process_new_messages(conversation_id, [revised]),
        )

    assert [call.args[0].text for call in handle.await_args_list] == [
        "original body",
        "revised body",
    ]


@pytest.mark.asyncio
async def test_older_revised_query_dispatches_without_rewinding_latest_cursor():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"
    original = _inbound_message(message_id="100", body="original query", version=1)
    bot_reply = _inbound_message(
        message_id="200",
        body="agent reply",
        version=1,
        properties={"hermes_sender": "bot"},
    )
    revised = _inbound_message(
        message_id="100",
        body="complete revised query",
        version=2,
    )

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [bot_reply])
        await adapter._process_new_messages(conversation_id, [revised])
        await adapter._process_new_messages(conversation_id, [revised])

    assert [call.args[0].text for call in handle.await_args_list] == [
        "original query",
        "complete revised query",
    ]
    assert adapter._last_message_ids[conversation_id] == "200"


@pytest.mark.asyncio
async def test_same_message_id_is_independent_between_conversations():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    first_conversation = "48:first"
    second_conversation = "48:second"

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(
            first_conversation,
            [_inbound_message(body="first conversation")],
        )
        await adapter._process_new_messages(
            second_conversation,
            [_inbound_message(body="second conversation")],
        )

    assert [
        (call.args[0].source.chat_id, call.args[0].text)
        for call in handle.await_args_list
    ] == [
        (first_conversation, "first conversation"),
        (second_conversation, "second conversation"),
    ]


@pytest.mark.asyncio
async def test_bounded_state_silently_rebaselines_an_evicted_old_identity(monkeypatch):
    monkeypatch.setattr(teams_mtk, "_REVISION_STATE_MAX_ENTRIES", 2)
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        for message_id in ("100", "200", "300"):
            await adapter._process_new_messages(
                conversation_id,
                [_inbound_message(message_id=message_id, body=f"body {message_id}")],
            )
        await adapter._process_new_messages(
            conversation_id,
            [_inbound_message(message_id="100", body="late edited old history")],
        )

    assert [call.args[0].text for call in handle.await_args_list] == [
        "body 100",
        "body 200",
        "body 300",
    ]


@pytest.mark.asyncio
async def test_outbound_ownership_survives_revision_without_sender_property():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "48:notes"
    adapter._last_message_ids[conversation_id] = "0"
    adapter._remember_sent_message(conversation_id, "100")
    original = _inbound_message(
        body="agent response",
        version=1,
        properties={"hermes_sender": "bot"},
    )
    revised = _inbound_message(
        body="edited agent response",
        version=2,
        properties={},
    )

    with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [revised])

    handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_revision_still_passes_group_mention_gate_before_dispatch():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "19:group@thread.v2"
    adapter._last_message_ids[conversation_id] = "0"
    original = _inbound_message(body="@hermes original body", version=1)
    revised = _inbound_message(body="revised body without mention", version=2)

    with (
        patch.object(
            adapter,
            "_group_config",
            return_value={"require_mention": True},
        ),
        patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle,
    ):
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [revised])

    assert handle.await_count == 1
    assert handle.await_args.args[0].text == "original body"


@pytest.mark.asyncio
async def test_revision_still_passes_blocked_keyword_gate_before_dispatch():
    adapter = teams_mtk.TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    conversation_id = "19:group@thread.v2"
    adapter._last_message_ids[conversation_id] = "0"
    original = _inbound_message(body="allowed question?", version=1)
    revised = _inbound_message(body="contains forbidden phrase?", version=2)

    with (
        patch.object(
            adapter,
            "_group_config",
            return_value={
                "require_mention": False,
                "blocked_keywords": ["forbidden"],
            },
        ),
        patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle,
        patch.object(adapter, "send", new_callable=AsyncMock) as send,
    ):
        await adapter._process_new_messages(conversation_id, [original])
        await adapter._process_new_messages(conversation_id, [revised])

    assert handle.await_count == 1
    assert handle.await_args.args[0].text == "allowed question?"
    send.assert_awaited_once_with(conversation_id, adapter._BLOCKED_KEYWORD_NOTICE)
