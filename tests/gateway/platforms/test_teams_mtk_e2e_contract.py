"""Behavior contracts for the live Teams MTK E2E runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _branded_bot_html(body: str) -> str:
    return (
        '<div style="border-left:3px solid #6264A7;padding-left:10px">'
        '<b>🤖 Hermes</b><br><br>'
        f"<p>{body}</p><br>"
        '<span style="color:#888;font-size:0.85em">'
        "— Hermes · 2026-07-25 12:00</span></div>"
    )


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
    reset_marker = "E2ERESETABCDEF123456"

    old_message = {"id": "old", "content": "old message"}
    new_session_ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": (
            f'<div style="border-left: 2px solid">'
            f"新的工作階段「{reset_marker}」已啟動 🤖</div>"
        ),
    }
    readbacks = iter(
        [
            [old_message],
            [new_session_ack, old_message],
            [new_session_ack, old_message],
        ]
    )

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args, **kwargs: "sent")
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(e2e, "delete_msg_message", lambda *args, **kwargs: None)
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
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": f'<div style="border-left:1px">{reset_marker} 🤖</div>',
    }
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(f"&#8203;{marker}&nbsp;"),
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
    sent_ids = iter(["graph-new", "graph-query"])
    sent_contents = []
    deleted_graph = []
    deleted_msg = []

    def send_message(_chat, content):
        sent_contents.append(content)
        return next(sent_ids)

    monkeypatch.setattr(e2e, "send_chat_message", send_message)
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda _chat, message_id: deleted_graph.append(message_id),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is True
    assert "exactly one" in evidence.lower()
    assert sent_contents[0] == f"/new {reset_marker}"
    assert marker in sent_contents[1]
    assert deleted_graph == ["graph-new", "graph-query"]
    assert set(deleted_msg) == {"ack", "reply"}


@pytest.mark.parametrize(
    "extra_after_exact",
    [False, True],
    ids=["initial-readback", "settled-readback"],
)
def test_streaming_e2e_rejects_marker_with_extra_visible_text_and_keeps_failure(
    monkeypatch,
    extra_after_exact,
):
    """Substring matches must fail, even when cleanup also fails."""
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": f'<div style="border-left:1px">{reset_marker} 🤖</div>',
    }
    exact_reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    extra_reply = {
        "id": "reply",
        "content": (
            f"**🤖 Hermes**\n\nprefix {marker} suffix\n\n"
            "— Hermes · 2026-07-25 12:00"
        ),
        "_raw_content": _branded_bot_html(f"prefix {marker} suffix"),
    }
    reply_readbacks = (
        [[exact_reply, ack, old], [extra_reply, ack, old]]
        if extra_after_exact
        else [[extra_reply, ack, old]]
    )
    readbacks = iter(
        [
            [old],
            [ack, old],
            *reply_readbacks,
        ]
    )
    sent_ids = iter(["graph-new", "graph-query"])
    graph_cleanup_attempts = []
    deleted_msg = []

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args, **_kwargs: next(sent_ids),
    )

    def fail_graph_cleanup(_chat, message_id):
        graph_cleanup_attempts.append(message_id)
        raise RuntimeError("cleanup unavailable")

    monkeypatch.setattr(e2e, "delete_graph_message", fail_graph_cleanup)
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log",
        0,
        reply_timeout=0,
        settle_seconds=0,
    )

    assert ok is False
    assert "marker" in evidence.lower()
    assert graph_cleanup_attempts == ["graph-new", "graph-query"]
    assert set(deleted_msg) == {"ack", "reply"}


def test_streaming_e2e_cleanup_failure_overrides_success(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": f'<div style="border-left:1px">{reset_marker} 🤖</div>',
    }
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    readbacks = iter(
        [
            [old],
            [ack, old],
            [reply, ack, old],
            [reply, ack, old],
        ]
    )
    sent_ids = iter(["graph-new", "graph-query"])
    graph_cleanup_attempts = []
    deleted_msg = []

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args, **_kwargs: next(sent_ids),
    )

    def fail_graph_cleanup(_chat, message_id):
        graph_cleanup_attempts.append(message_id)
        raise RuntimeError("cleanup unavailable")

    monkeypatch.setattr(e2e, "delete_graph_message", fail_graph_cleanup)
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="cleanup failed after a successful result"):
        e2e.test_streaming_no_echo_duplication(
            "unused.log", 0, settle_seconds=0
        )

    assert graph_cleanup_attempts == ["graph-new", "graph-query"]
    assert set(deleted_msg) == {"ack", "reply"}


def test_streaming_e2e_rejects_extra_bot_ids_and_cleans_only_correlated(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": f'<div style="border-left:1px">{reset_marker} 🤖</div>',
    }
    progress = {
        "id": "progress",
        "content": "Reading AGENTS.md",
        "_raw_content": '<div style="border-left:1px">Reading AGENTS.md 🤖</div>',
    }
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    footer = {
        "id": "footer",
        "content": "Hermes model footer",
        "_raw_content": '<div style="border-left:1px">Hermes model footer 🤖</div>',
    }
    readbacks = iter(
        [
            [old],
            [ack, old],
            [reply, progress, ack, old],
            [footer, reply, progress, ack, old],
        ]
    )
    deleted_msg = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args, **kwargs: "sent")
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is False
    assert "unexpected bot message ids=2" in evidence.lower()
    assert set(deleted_msg) == {"ack", "reply"}


def test_ui_readback_selects_chat_header_and_excludes_user_prompt(monkeypatch):
    e2e = _load_e2e_module()
    marker = "E2E_MODEL_ABC"
    calls = []

    def run_cua(tool, arguments):
        calls.append((tool, arguments))
        if tool == "list_windows":
            return {
                "windows": [
                    {
                        "app_name": "ms-teams.exe",
                        "pid": 1,
                        "window_id": 11,
                        "is_on_screen": True,
                        "bounds": {"width": 100, "height": 100},
                    },
                    {
                        "app_name": "ms-teams.exe",
                        "pid": 2,
                        "window_id": 22,
                        "is_on_screen": True,
                        "bounds": {"width": 90, "height": 90},
                    },
                ]
            }
        if arguments["window_id"] == 11:
            return {"elements": [{"label": "chat-header-other-chat"}]}
        return {
            "elements": [
                {"label": "chat-header-test-chat"},
                {"label": f"Reply with exactly {marker}"},
                {
                    "label": (
                        r"由 Test User 的 🤖 Hermes E2E\_MODEL\_ABC "
                        "— Hermes · 2026-07-25 12:00"
                    )
                },
                {
                    "label": (
                        r"由 Test User 的 🤖 Hermes prefix E2E\_MODEL\_ABC suffix "
                        "— Hermes · 2026-07-25 12:00"
                    )
                },
            ]
        }

    monkeypatch.setattr(e2e, "_run_cua_driver", run_cua)

    bot_labels = e2e.get_teams_ui_bot_card_labels("test-chat")
    assert len(bot_labels) == 2
    assert all("Reply with exactly" not in label for label in bot_labels)
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda _chat_id: bot_labels,
    )
    assert e2e.get_teams_ui_bot_marker_count("test-chat", marker) == 1
    assert [call[1].get("window_id") for call in calls[1:]] == [11, 22]


def test_streaming_e2e_falls_back_to_marker_matched_teams_ui(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    sent_contents = []
    deleted_graph = []
    deleted_msg = []
    counts = iter([1, 1])
    ui_labels = iter(
        [
            [],
            [
                f"由 Test User 的 🤖 Hermes {marker} "
                "— Hermes · 2026-07-25 12:00"
            ],
        ]
    )
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    readbacks = iter([RuntimeError("TLS unavailable"), [reply]])

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))

    def transient_sdk_readback(*_args, **_kwargs):
        result = next(readbacks)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(e2e, "get_messages_raw", transient_sdk_readback)
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda _chat, content: sent_contents.append(content) or "graph-query",
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_marker_count",
        lambda *_args, **_kwargs: next(counts),
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda *_args, **_kwargs: next(ui_labels),
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda _chat, message_id: deleted_graph.append(message_id),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is True
    assert "teams uia" in evidence.lower()
    assert len(sent_contents) == 1
    assert sent_contents[0].startswith("Reply with exactly E2EABCDEF123456")
    assert deleted_graph == ["graph-query"]
    assert deleted_msg == ["reply"]


def test_streaming_ui_fallback_rejects_extra_bot_card(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    snapshots = iter(
        [
            ["由 Test User 的 🤖 Hermes old — Hermes · 2026-07-25 11:59"],
            [
                "由 Test User 的 🤖 Hermes old — Hermes · 2026-07-25 11:59",
                f"由 Test User 的 🤖 Hermes {marker} — Hermes · 2026-07-25 12:00",
                "由 Test User 的 🤖 Hermes footer — Hermes · 2026-07-25 12:00",
            ],
        ]
    )

    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda *_args, **_kwargs: next(snapshots),
        raising=False,
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_marker_count",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args, **_kwargs: "graph-query",
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e._test_streaming_no_echo_duplication_via_ui(
        marker,
        [],
        reply_timeout=0,
        poll_interval=0,
        settle_seconds=0,
    )

    assert ok is False
    assert "unexpected bot" in evidence.lower()


def test_streaming_e2e_ui_fallback_requires_bot_cleanup_ids(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    counts = iter([1, 1])
    ui_labels = iter(
        [
            [],
            [
                f"由 Test User 的 🤖 Hermes {marker} "
                "— Hermes · 2026-07-25 12:00"
            ],
        ]
    )

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(
        e2e,
        "get_messages_raw",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("MSG read-back unavailable")
        ),
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args, **_kwargs: "graph-query",
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_marker_count",
        lambda *_args, **_kwargs: next(counts),
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda *_args, **_kwargs: next(ui_labels),
    )
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="cleanup message IDs"):
        e2e.test_streaming_no_echo_duplication(
            "unused.log", 0, settle_seconds=0
        )


def test_streaming_e2e_falls_back_after_new_before_query(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_properties": {"hermes_sender": "bot"},
    }
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    sent_contents = []
    deleted_graph = []
    deleted_msg = []
    graph_ids = iter(["graph-new", "graph-query"])
    readbacks = iter(
        [[old], RuntimeError("TLS unavailable after /new"), [reply, ack, old]]
    )
    counts = iter([1, 1])
    ui_labels = iter(
        [
            ["由 Test User 的 🤖 Hermes new-session — Hermes · 2026-07-25 11:59"],
            [
                "由 Test User 的 🤖 Hermes new-session — Hermes · 2026-07-25 11:59",
                f"由 Test User 的 🤖 Hermes {marker} "
                "— Hermes · 2026-07-25 12:00",
            ],
        ]
    )

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )

    def fail_after_initial_read(*_args, **_kwargs):
        result = next(readbacks)
        if isinstance(result, Exception):
            raise result
        return result

    def send_message(_chat, content):
        sent_contents.append(content)
        return next(graph_ids)

    monkeypatch.setattr(e2e, "get_messages_raw", fail_after_initial_read)
    monkeypatch.setattr(e2e, "send_chat_message", send_message)
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_marker_count",
        lambda *_args, **_kwargs: next(counts),
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda *_args, **_kwargs: next(ui_labels),
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda _chat, message_id: deleted_graph.append(message_id),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is True
    assert "teams uia" in evidence.lower()
    assert sent_contents == [
        f"/new {reset_marker}",
        f"Reply with exactly {marker}. Do not add other text and do not use tools.",
    ]
    assert deleted_graph == ["graph-new", "graph-query"]
    assert set(deleted_msg) == {"ack", "reply"}


def test_streaming_e2e_falls_back_after_query_without_resending(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_properties": {"hermes_sender": "bot"},
    }
    reply = {
        "id": "reply",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    sent_contents = []
    deleted_graph = []
    deleted_msg = []
    graph_ids = iter(["graph-new", "graph-query"])
    readbacks = iter(
        [
            [old],
            [ack, old],
            RuntimeError("TLS unavailable after query"),
            [reply, ack, old],
        ]
    )

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )

    def fail_after_ack_read(*_args, **_kwargs):
        result = next(readbacks)
        if isinstance(result, Exception):
            raise result
        return result

    def send_message(_chat, content):
        sent_contents.append(content)
        return next(graph_ids)

    monkeypatch.setattr(e2e, "get_messages_raw", fail_after_ack_read)
    monkeypatch.setattr(e2e, "send_chat_message", send_message)
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_marker_count",
        lambda *_args, **_kwargs: pytest.fail(
            "post-query UI marker count must not substitute for a missing baseline"
        ),
    )
    monkeypatch.setattr(
        e2e,
        "get_teams_ui_bot_card_labels",
        lambda *_args, **_kwargs: pytest.fail(
            "post-query UI labels must not substitute for a missing baseline"
        ),
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda _chat, message_id: deleted_graph.append(message_id),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is False
    assert "pre-query" in evidence.lower()
    assert "baseline" in evidence.lower()
    assert sent_contents == [
        f"/new {reset_marker}",
        f"Reply with exactly {marker}. Do not add other text and do not use tools.",
    ]
    assert deleted_graph == ["graph-new", "graph-query"]
    assert set(deleted_msg) == {"ack", "reply"}


def test_streaming_e2e_rejects_multiple_bot_message_ids(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    marker = "E2EABCDEF123456"
    reset_marker = "E2ERESETABCDEF123456"
    old = {"id": "old", "content": "old"}
    ack = {
        "id": "ack",
        "content": f"新的工作階段「{reset_marker}」已啟動",
        "_raw_content": f'<div style="border-left:1px">{reset_marker} 🤖</div>',
    }
    reply1 = {
        "id": "reply-1",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
    }
    reply2 = {
        "id": "reply-2",
        "content": f"**🤖 Hermes**\n\n{marker}\n\n— Hermes · 2026-07-25 12:00",
        "_raw_content": _branded_bot_html(marker),
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
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(e2e, "delete_msg_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_streaming_no_echo_duplication(
        "unused.log", 0, settle_seconds=0
    )

    assert ok is False
    assert "duplicate" in evidence.lower()


def test_e2e_readback_discards_failed_and_reuses_successful_transport(monkeypatch):
    e2e = _load_e2e_module()
    auth = SimpleNamespace(
        msg_base="https://msg.example/v1/users/ME",
        _inject_truststore=lambda: None,
    )
    setattr(e2e, "_gateway_auth", auth)
    attempts = []
    created = []
    closed = []
    sleeps = []

    class FakeSession:
        def close(self):
            closed.append(True)

    class FakeHttp:
        def __init__(self):
            self._session = FakeSession()

    class FakeMessagesService:
        def __init__(self, _http):
            pass

        def get_page(self, chat_id, *, page_size, msg_base):
            attempts.append((chat_id, page_size, msg_base))
            if len(attempts) < 3:
                raise RuntimeError("transient TLS failure")
            return [{"id": "reply", "content": "marker 🤖"}]

    def make_http(actual, verify_ssl):
        assert actual is auth
        assert verify_ssl is True
        created.append(True)
        return FakeHttp()

    messages_module = importlib.import_module("teams_skype_sdk.api._messages")
    monkeypatch.setattr(messages_module, "MessagesService", FakeMessagesService)
    monkeypatch.setattr(e2e, "_SDKAuthAdapter", lambda actual: actual)
    monkeypatch.setattr(e2e, "_SDKHTTPLayer", make_http)
    monkeypatch.setattr(e2e.time, "sleep", lambda seconds: sleeps.append(seconds))

    first = e2e.get_messages_raw("test-chat", page_size=50)
    second = e2e.get_messages_raw("test-chat", page_size=50)

    assert first == second == [{"id": "reply", "content": "marker 🤖"}]
    assert len(attempts) == 4
    assert len(created) == 3
    assert len(closed) == 2
    assert sleeps == [1, 2]


def test_e2e_readback_error_does_not_leak_conversation_url(monkeypatch):
    e2e = _load_e2e_module()
    auth = SimpleNamespace(
        msg_base="https://msg.example/v1/users/ME",
        _inject_truststore=lambda: None,
    )
    setattr(e2e, "_gateway_auth", auth)

    class FakeMessagesService:
        def __init__(self, _http):
            pass

        def get_page(self, *_args, **_kwargs):
            raise RuntimeError("https://msg.example/conversations/private-chat-id/messages")

    messages_module = importlib.import_module("teams_skype_sdk.api._messages")
    monkeypatch.setattr(messages_module, "MessagesService", FakeMessagesService)
    monkeypatch.setattr(e2e, "_SDKAuthAdapter", lambda actual: actual)
    monkeypatch.setattr(
        e2e, "_SDKHTTPLayer", lambda _actual, verify_ssl: SimpleNamespace()
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError) as caught:
        e2e.get_messages_raw("private-chat-id")

    assert "private-chat-id" not in str(caught.value)
    assert "RuntimeError" in str(caught.value)


def test_e2e_graph_token_uses_gateway_atomic_auth(monkeypatch):
    """Live E2E scope exchanges must share the gateway's atomic token writer."""
    e2e = _load_e2e_module()
    gateway_auth = object()
    seen_auth = []

    class FakeGraphToken:
        def __init__(self, auth):
            seen_auth.append(auth)

        def get_token(self):
            return "graph-token"

    def _legacy_sdk_auth_must_not_run():
        raise AssertionError("legacy SDK TeamsAuth would truncate the live cache")

    monkeypatch.setattr(e2e, "_TeamsAuth", lambda: gateway_auth, raising=False)
    monkeypatch.setattr(
        e2e, "TeamsAuth", _legacy_sdk_auth_must_not_run, raising=False
    )
    monkeypatch.setattr(e2e, "GraphToken", FakeGraphToken)
    setattr(e2e, "_gateway_auth", None)
    setattr(e2e, "_graph_token", None)

    assert e2e.get_graph_token() == "graph-token"
    assert seen_auth == [gateway_auth]


def test_e2e_readback_uses_gateway_atomic_auth(monkeypatch):
    e2e = _load_e2e_module()
    gateway_auth = SimpleNamespace(skype_token=lambda: "skype-token")
    setattr(e2e, "_gateway_auth", gateway_auth)

    assert e2e.get_skype_token() == "skype-token"


def test_e2e_sdk_send_uses_gateway_auth_adapter(monkeypatch):
    e2e = _load_e2e_module()
    gateway_auth = object()
    adapter = object()
    http = object()
    observed = {}

    class FakeMessagesService:
        def __init__(self, actual_http):
            observed["http"] = actual_http

        def send(self, *, conversation_id, content):
            observed["send"] = (conversation_id, content)
            return {"OriginalArrivalTime": 12345}

    messages_module = importlib.import_module("teams_skype_sdk.api._messages")

    monkeypatch.setattr(messages_module, "MessagesService", FakeMessagesService)
    monkeypatch.setattr(
        e2e, "_SDKAuthAdapter", lambda actual_auth: adapter if actual_auth is gateway_auth else None
    )
    monkeypatch.setattr(
        e2e, "_SDKHTTPLayer", lambda actual_adapter: http if actual_adapter is adapter else None
    )
    setattr(e2e, "_gateway_auth", gateway_auth)

    result = e2e.send_via_sdk("chat-id", "marker")

    assert result == "12345"
    assert observed == {"http": http, "send": ("chat-id", "marker")}
