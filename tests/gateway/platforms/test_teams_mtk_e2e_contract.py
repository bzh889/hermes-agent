"""Behavior contracts for the live Teams MTK E2E runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_e2e_module():
    path = (
        Path(__file__).resolve().parents[3]
        / "openspec"
        / "changes"
        / "teams-mtk-hermes-native-parity"
        / "e2e_teams_mtk.py"
    )
    spec = importlib.util.spec_from_file_location("teams_mtk_e2e_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_streaming_e2e_rejects_new_session_ack_without_marker_reply(monkeypatch):
    """A /new acknowledgment is not evidence that the model turn completed."""
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"

    old_message = {"id": "old", "content": "old message"}
    new_session_ack = {
        "id": "ack",
        "content": '<div style="border-left: 2px solid">New session started 🤖</div>',
    }
    readbacks = iter(
        [
            [old_message],
            [new_session_ack, old_message],
            [new_session_ack, old_message],
        ]
    )

    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args, **kwargs: "sent")
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log",
        0,
        reply_timeout=0,
        settle_seconds=0,
    )

    assert ok is False
    assert "marker" in evidence.lower()


def test_streaming_e2e_accepts_one_marker_matched_message(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {"id": "ack", "content": '<div style="border-left:1px">new 🤖</div>'}
    reply = {
        "id": "reply",
        "content": f'<div style="border-left:1px">{marker} 🤖</div>',
    }
    readbacks = iter(
        [
            [old],
            [ack, old],
            [reply, ack, old],
            [reply, ack, old],
        ]
    )

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args, **kwargs: "sent")
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is True
    assert "exactly one" in evidence.lower()


def test_streaming_e2e_rejects_multiple_bot_message_ids(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {"id": "ack", "content": '<div style="border-left:1px">new 🤖</div>'}
    reply1 = {
        "id": "reply-1",
        "content": f'<div style="border-left:1px">{marker} 🤖</div>',
    }
    reply2 = {
        "id": "reply-2",
        "content": f'<div style="border-left:1px">{marker} 🤖</div>',
    }
    readbacks = iter(
        [
            [old],
            [ack, old],
            [reply1, ack, old],
            [reply2, reply1, ack, old],
        ]
    )

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args, **kwargs: "sent")
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is False
    assert "duplicate" in evidence.lower()
