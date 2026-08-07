"""Behavior contracts for the live Teams MTK E2E runner."""

from __future__ import annotations

import importlib.util
import json
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


def test_model_picker_parser_accepts_sdk_normalized_text():
    e2e = _load_e2e_module()
    provider_card = (
        "⚙️ Select ProviderCurrent: **model-5.6** via Provider B"
        "1Provider A (4)2Provider B ← (9)3Provider C (2)"
    )
    model_card = (
        "⚙️ Select ModelCurrent: **model-5.6** via Provider B"
        "1model-5.5 (old)2model-5.6 ✓3model-6.0"
    )

    assert e2e._picker_current_model(provider_card) == "model-5.6"
    assert e2e._picker_numbered_choice(provider_card, "←") == 2
    assert e2e._picker_numbered_choice(model_card, "model-5.6") == 2


def test_model_picker_parser_keeps_raw_html_compatibility():
    e2e = _load_e2e_module()
    provider_card = (
        'Current: <b>model-x</b> via Provider B'
        '<div style="margin:1px 0"><span>2</span>Provider B ←</div>'
    )

    assert e2e._picker_current_model(provider_card) == "model-x"
    assert e2e._picker_numbered_choice(provider_card, "←") == 2


def test_inbound_edit_revision_e2e_uses_ticket_registry_name():
    e2e = _load_e2e_module()

    assert (
        e2e.NAMED_TESTS["inbound-edit-revision-reopens-query"]
        is e2e.test_same_id_edit_reopens_exactly_one_revised_query
    )


def test_quoted_reply_e2e_uses_ticket_registry_name():
    e2e = _load_e2e_module()

    assert (
        e2e.NAMED_TESTS["quoted-reply-full-context-revises-query"]
        is e2e.test_quoted_reply_full_context_revises_query
    )


def test_outbound_native_reply_e2e_uses_ticket_registry_name():
    e2e = _load_e2e_module()

    assert (
        e2e.NAMED_TESTS["reply-to-native-thread-roundtrip"]
        is e2e.test_reply_to_native_thread_roundtrip
    )


def test_bot_classifier_accepts_sdk_raw_sender_marker():
    e2e = _load_e2e_module()

    assert e2e._is_hermes_bot_message(
        {
            "content": "session reset acknowledgement",
            "properties": {},
            "_raw_properties": {"hermes_sender": "bot"},
        }
    ) is True
    assert e2e._is_hermes_bot_message(
        {
            "content": "human-authored message",
            "properties": {},
            "_raw_properties": {"hermes_sender": "user"},
        }
    ) is False


def test_tail_log_reads_current_file_after_rotation(tmp_path):
    e2e = _load_e2e_module()
    log_path = tmp_path / "gateway.log"
    log_path.write_text("old-1\nold-2\nold-3\n", encoding="utf-8")
    baseline_lines = 3

    log_path.write_text("new-1\nnew-2\n", encoding="utf-8")

    assert e2e.tail_log(str(log_path), baseline_lines) == "new-1\nnew-2\n"


def test_send_text_allows_a_bounded_full_model_turn(monkeypatch):
    e2e = _load_e2e_module()
    calls = []
    sent = []
    deleted_graph = []
    deleted_msg = []
    marker = "E2ESENDABCDEF123456"
    bot_reply = {
        "id": "bot-reply",
        "content": "ack",
        "_raw_properties": {"hermes_sender": "bot"},
    }
    readbacks = iter([[], [bot_reply], []])

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(
        e2e,
        "get_messages_raw",
        lambda *args, **kwargs: next(readbacks),
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *args: sent.append(args) or "trigger",
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda *args: deleted_graph.append(args),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda *args: deleted_msg.append(args),
    )

    def _wait(log_path, baseline, patterns, wait_seconds):
        calls.append((log_path, baseline, patterns, wait_seconds))
        return True, "sent"

    monkeypatch.setattr(e2e, "wait_and_check_log", _wait)

    assert e2e.test_send_text("gateway.log", 17) == (True, "sent")
    assert calls == [
        ("gateway.log", 17, [r"TeamsMTK: sent message id="], 300)
    ]
    assert sent == [(e2e.DM_CHAT_ID, f"{marker} send test — hello")]
    assert deleted_graph == [(e2e.DM_CHAT_ID, "trigger")]
    assert deleted_msg == [
        (e2e.DM_CHAT_ID, "bot-reply"),
        (e2e.DM_CHAT_ID, "trigger"),
    ]


def test_residual_markdown_e2e_cleans_marker_bearing_human_mirror(monkeypatch):
    e2e = _load_e2e_module()
    marker = "E2ERENDERABCDEF123456"
    baseline = {"id": "baseline", "content": "existing human message"}
    bot_reply = {
        "id": "bot-reply",
        "content": _branded_bot_html(f"rendered table {marker}"),
        "_raw_properties": {"hermes_sender": "bot"},
    }
    human_mirror = {
        "id": "human-mirror",
        "content": f"request {marker}",
        "_raw_properties": {"hermes_sender": "user"},
    }
    unrelated_human = {
        "id": "unrelated-human",
        "content": "concurrent human message",
        "_raw_properties": {"hermes_sender": "user"},
    }
    readbacks = iter(
        [
            [baseline],
            [baseline, bot_reply],
            [baseline, bot_reply, human_mirror, unrelated_human],
            [baseline, human_mirror, unrelated_human],
            [baseline, unrelated_human],
        ]
    )
    sent_ids = iter(["graph-reset", "graph-query"])
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(
        e2e,
        "get_messages_raw",
        lambda *args, **kwargs: next(readbacks),
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args: next(sent_ids),
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda *args: deleted_graph.append(args),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda *args: deleted_msg.append(args),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_no_residual_markdown_in_reply(
        "gateway.log",
        17,
        reply_timeout=1,
        poll_interval=0,
    )

    assert ok is True, evidence
    assert deleted_graph == [
        (e2e.DM_CHAT_ID, "graph-reset"),
        (e2e.DM_CHAT_ID, "graph-query"),
    ]
    assert set(deleted_msg) == {
        (e2e.DM_CHAT_ID, "bot-reply"),
        (e2e.DM_CHAT_ID, "human-mirror"),
    }
    assert (e2e.DM_CHAT_ID, "unrelated-human") not in deleted_msg


def test_residual_markdown_e2e_reports_cleanup_failure_without_masking_functional_failure(
    monkeypatch, capsys
):
    e2e = _load_e2e_module()
    readbacks = iter([[], [], []])
    sent_ids = iter(["graph-reset", "graph-query"])

    monkeypatch.setattr(
        e2e,
        "get_messages_raw",
        lambda *_args, **_kwargs: next(readbacks),
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args: next(sent_ids),
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )
    monkeypatch.setattr(e2e, "delete_msg_message", lambda *_args: None)
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    ok, evidence = e2e.test_no_residual_markdown_in_reply(
        "gateway.log",
        17,
        reply_timeout=0,
        poll_interval=0,
    )

    assert ok is False
    assert evidence == "No marker-correlated bot reply found within wait window"
    assert "cleanup failed (graph:RuntimeError, graph:RuntimeError)" in capsys.readouterr().err


def test_garbage_detector_e2e_correlates_and_cleans_up(monkeypatch):
    e2e = _load_e2e_module()
    marker = "E2EGARBAGEABCDEF123456"
    reset_reply = {
        "id": "bot-reset",
        "content": f"<div>{marker}RESET</div>",
        "_raw_properties": {"hermes_sender": "bot"},
    }
    query_reply = {
        "id": "bot-query",
        "content": f"<div>{'正確內容' * 30} {marker}DONE</div>",
        "_raw_properties": {"hermes_sender": "bot"},
    }
    readbacks = iter(
        [
            [],
            [reset_reply],
            [reset_reply, query_reply],
            [reset_reply, query_reply],
            [],
        ]
    )
    sent_ids = iter(["graph-reset", "graph-query"])
    sent = []
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(
        e2e.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )
    monkeypatch.setattr(
        e2e,
        "get_messages_raw",
        lambda *args, **kwargs: next(readbacks),
    )
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda chat_id, content: sent.append((chat_id, content)) or next(sent_ids),
    )
    monkeypatch.setattr(e2e, "tail_log", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda *args: deleted_graph.append(args),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda *args: deleted_msg.append(args),
    )
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)

    import agent.garbage_detector as garbage_detector

    monkeypatch.setattr(garbage_detector, "is_garbage", lambda _text: False)
    monkeypatch.setattr(garbage_detector, "_garbage_score", lambda _text: 0.0)

    ok, evidence = e2e.test_garbage_detector_no_false_positive_on_clean_output(
        "gateway.log", 23
    )

    assert ok is True, evidence
    assert sent[0] == (e2e.DM_CHAT_ID, f"/new {marker}RESET")
    assert marker in sent[1][1]
    assert deleted_graph == [
        (e2e.DM_CHAT_ID, "graph-reset"),
        (e2e.DM_CHAT_ID, "graph-query"),
    ]
    assert set(deleted_msg) == {
        (e2e.DM_CHAT_ID, "bot-reset"),
        (e2e.DM_CHAT_ID, "bot-query"),
        (e2e.DM_CHAT_ID, "graph-reset"),
        (e2e.DM_CHAT_ID, "graph-query"),
    }


def test_native_reply_relation_parser_accepts_wire_shapes():
    e2e = _load_e2e_module()
    message = {
        "content": (
            '<blockquote itemtype="http://schema.skype.com/Reply">'
            '<span itemprop="time" itemid="target-alias"></span>'
            "</blockquote><p>reply</p>"
        ),
        "properties": json.dumps(
            {
                "replyChainMessageId": "target-alias",
                "qtdMsgs": json.dumps(
                    [{"messageId": "target-alias"}]
                ),
            }
        ),
    }

    assert e2e._native_reply_relation_ids(message) == {"target-alias"}


@pytest.mark.parametrize(
    "properties",
    [
        {"emotions": [{"key": "like", "users": ["user-a", "user-b"]}]},
        json.dumps(
            {"emotions": [{"key": "like", "users": ["user-a", "user-b"]}]}
        ),
    ],
)
def test_reaction_verifier_reads_exact_raw_properties_without_returning_identities(
    monkeypatch,
    properties,
):
    e2e = _load_e2e_module()
    calls = []

    def _exact(chat_id, message_id):
        calls.append((chat_id, message_id))
        return {"properties": properties}

    monkeypatch.setattr(e2e, "get_message_raw_exact", _exact)

    assert e2e._reaction_user_count("conversation-alias", "message-alias", "like") == 2
    assert calls == [("conversation-alias", "message-alias")]


@pytest.mark.parametrize(
    "properties",
    [
        {"deletetime": "123"},
        json.dumps({"deletetime": "123"}),
    ],
)
def test_tombstone_verifier_reads_exact_raw_state_without_returning_content(
    monkeypatch,
    properties,
):
    e2e = _load_e2e_module()

    monkeypatch.setattr(
        e2e,
        "get_message_raw_exact",
        lambda _chat_id, _message_id: {
            "content": "",
            "properties": properties,
        },
    )

    assert e2e._exact_tombstone_state("conversation-alias", "message-alias") == (
        True,
        0,
        True,
    )


def test_html_tag_verifier_reads_exact_raw_message(monkeypatch):
    e2e = _load_e2e_module()
    calls = []

    def _exact(chat_id, message_id):
        calls.append((chat_id, message_id))
        return {"content": '<p>caption</p><img src="redacted">'}

    monkeypatch.setattr(e2e, "get_message_raw_exact", _exact)

    assert e2e._exact_message_has_html_tag(
        "conversation-alias",
        "message-alias",
        "img",
    ) is True
    assert calls == [("conversation-alias", "message-alias")]


@pytest.mark.parametrize(
    "message",
    [
        {"content": '<p>caption</p><a href="https://redacted.invalid/share">file</a>'},
        {
            "content": "caption",
            "properties": {
                "files": json.dumps(
                    [{"fileInfo": {"shareUrl": "https://redacted.invalid/share"}}]
                )
            },
        },
    ],
)
def test_document_verifier_reads_exact_share_contract(monkeypatch, message):
    e2e = _load_e2e_module()
    monkeypatch.setattr(e2e, "get_message_raw_exact", lambda *_args: message)

    assert e2e._exact_document_has_share_link(
        "conversation-alias",
        "message-alias",
    ) is True


@pytest.mark.parametrize(
    ("message", "property_key"),
    [
        ({"content": "E2E_MARKER"}, None),
        (
            {
                "content": "",
                "properties": {
                    "cards": json.dumps([{"content": {"text": "E2E_MARKER"}}])
                },
            },
            "cards",
        ),
    ],
)
def test_exact_marker_verifier_reads_content_or_named_property(
    monkeypatch,
    message,
    property_key,
):
    e2e = _load_e2e_module()
    monkeypatch.setattr(e2e, "get_message_raw_exact", lambda *_args: message)

    assert e2e._exact_message_contains_marker(
        "conversation-alias",
        "message-alias",
        "E2E_MARKER",
        property_key=property_key,
    ) is True


@pytest.mark.parametrize(
    "raw_html, expected",
    [
        (
            "<p><strong>Conclusion</strong></p><table><tr><td>ok</td></tr></table>",
            [],
        ),
        ("<p>**bold** `code` [link](https://example.invalid)</p>", [
            "**bold**",
            "`code`",
            "[text](url)",
        ]),
        ("- leaked bullet", ["- bullet"]),
        ("| name | state |", ["| pipe table |"]),
    ],
)
def test_residual_markdown_classifier_checks_raw_rendered_html(raw_html, expected):
    e2e = _load_e2e_module()

    assert e2e._residual_markdown_labels(raw_html) == expected


def test_busy_burst_addressing_respects_group_mention_policy():
    e2e = _load_e2e_module()

    assert e2e._address_busy_burst_prompt("correction", require_mention=False) == (
        "correction"
    )
    assert e2e._address_busy_burst_prompt("correction", require_mention=True) == (
        '<at id="0">Hermes</at>&nbsp;correction'
    )


def test_native_user_reply_uses_exact_source_relation_without_bot_marker(
    monkeypatch,
):
    e2e = _load_e2e_module()
    calls = []

    class _Auth:
        msg_base = "https://msg.example/v1/users/ME"

        @staticmethod
        def _inject_truststore():
            return None

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _HTTP:
        @staticmethod
        def _extract_mri_from_url(value):
            return str(value).rsplit("/", 1)[-1]

        def _request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if method == "GET":
                return _Response(
                    {
                        "id": "100",
                        "from": "https://sender.example/8:orgid:source-author",
                        "imdisplayname": "Source Author",
                        "content": "<p>early rule " + ("padding " * 50) + "late rule</p>",
                    }
                )
            return _Response({"OriginalArrivalTime": 200})

    http = _HTTP()
    monkeypatch.setattr(e2e, "_get_gateway_auth", lambda: _Auth())
    monkeypatch.setattr(e2e, "_get_readback_http_layer", lambda _auth: http)

    result = e2e.send_native_user_reply(
        "conversation/alias",
        "100",
        "apply the final rule",
    )

    assert result == "200"
    assert calls[0] == (
        "GET",
        "https://msg.example/v1/users/ME/conversations/conversation%2Falias/messages/100",
        {},
    )
    method, url, kwargs = calls[1]
    assert method == "POST"
    assert url.endswith("/conversations/conversation%2Falias/messages")
    properties = kwargs["json"]["properties"]
    assert properties["replyChainMessageId"] == "100"
    assert json.loads(properties["qtdMsgs"])[0]["messageId"] == "100"
    assert "hermes_sender" not in properties
    rendered = kwargs["json"]["content"]
    assert 'itemtype="http://schema.skype.com/Reply"' in rendered
    assert 'itemid="100"' in rendered
    assert "late rule" not in rendered
    assert "apply the final rule" in rendered


def test_dm_echo_guard_uses_active_sdk_auth_and_exact_cleanup(monkeypatch):
    e2e = _load_e2e_module()
    marker = "E2EECHOABCDEF123456"
    reply = {
        "id": "reply",
        "content": marker,
        "_raw_content": _branded_bot_html(marker),
    }
    readbacks = iter([[], [reply], [reply], []])
    sent = []
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(e2e, "send_chat_message", lambda *args: sent.append(args) or "query")
    monkeypatch.setattr(e2e, "wait_and_check_log", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda chat_id, message_id: deleted_graph.append((chat_id, message_id)),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda chat_id, message_id: deleted_msg.append((chat_id, message_id)),
    )

    ok, evidence = e2e.test_dm_echo_guard("unused.log", 0)

    assert ok is True
    assert evidence == "ok"
    assert sent == [(e2e.DM_CHAT_ID, f"/new {marker}")]
    assert deleted_graph == [(e2e.DM_CHAT_ID, "query")]
    assert deleted_msg == [(e2e.DM_CHAT_ID, "reply")]


def test_mention_gate_process_uses_exact_readback_and_cleanup(monkeypatch):
    e2e = _load_e2e_module()
    monkeypatch.setattr(
        e2e,
        "_busy_burst_group_idle_preflight",
        lambda: (True, "control group idle", set()),
    )
    marker = "E2EMENTIONABCDEF123456"
    reply = {
        "id": "reply",
        "content": marker,
        "_raw_content": _branded_bot_html(marker),
    }
    reply_revision = {
        "id": "reply",
        "content": marker,
        "_raw_content": _branded_bot_html(marker),
        "version": "2",
    }
    readbacks = iter([[], [reply, reply_revision], [reply, reply_revision], []])
    sent = []
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda chat_id, content: sent.append((chat_id, content)) or "graph-message",
    )
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda chat_id, message_id: deleted_graph.append((chat_id, message_id)),
    )
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda chat_id, message_id: deleted_msg.append((chat_id, message_id)),
    )

    ok, evidence = e2e.test_mention_gating_process("unused.log", 0)

    assert ok is True
    assert evidence == "mention_dispatch=1; duplicate_dispatch=0"
    assert marker in sent[0][1]
    assert deleted_graph == [(e2e.GROUP_CHAT_ID, "graph-message")]
    assert deleted_msg == [(e2e.GROUP_CHAT_ID, "reply")]


def test_mention_gate_ignore_uses_unique_marker_and_exact_cleanup(monkeypatch):
    e2e = _load_e2e_module()
    monkeypatch.setattr(
        e2e,
        "_busy_burst_group_idle_preflight",
        lambda: (True, "control group idle", set()),
    )
    marker = "E2EIGNOREABCDEF123456"
    readbacks = iter([[], [], []])
    sent = []
    deleted_graph = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda chat_id, content: sent.append((chat_id, content)) or "graph-message",
    )
    monkeypatch.setattr(e2e, "wait_and_check_log", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(e2e, "tail_log", lambda *args, **kwargs: "")
    monkeypatch.setattr(e2e.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        e2e,
        "delete_graph_message",
        lambda chat_id, message_id: deleted_graph.append((chat_id, message_id)),
    )

    ok, evidence = e2e.test_mention_gating_ignore("unused.log", 0)

    assert ok is True
    assert evidence == "mention_ignored=True; dispatch_count=0; reply_count=0"
    assert marker in sent[0][1]
    assert deleted_graph == [(e2e.GROUP_CHAT_ID, "graph-message")]


@pytest.mark.parametrize("duplicate", [False, True], ids=["one-reply", "duplicate"])
def test_same_id_revision_e2e_counts_revised_dispatches_and_cleans_up(
    monkeypatch,
    duplicate,
):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    prefix = "E2EEDITABCDEF123456"
    reset_marker = f"{prefix}RESET"
    original_marker = f"{prefix}ORIGINAL"
    revised_body = f"{prefix}REVISEDA|{prefix}REVISEDB"
    old = {"id": "old", "content": "old"}
    reset_ack = {
        "id": "ack",
        "content": f"session {reset_marker}",
        "_raw_content": _branded_bot_html(f"session {reset_marker}"),
    }
    query = {
        "id": "query",
        "content": (
            f"Reply with exactly {original_marker}. Do not add other text or use tools."
        ),
    }
    edited_query = {
        "id": "query",
        "content": (
            f"Reply with exactly {revised_body}. Do not add other text or use tools."
        ),
    }
    original_reply = {
        "id": "original-reply",
        "content": original_marker,
        "_raw_content": _branded_bot_html(original_marker),
    }
    revised_reply = {
        "id": "revised-reply",
        "content": revised_body,
        "_raw_content": _branded_bot_html(revised_body),
    }
    revised_replies = [revised_reply]
    if duplicate:
        revised_replies.append(
            {
                "id": "revised-reply-duplicate",
                "content": revised_body,
                "_raw_content": _branded_bot_html(revised_body),
            }
        )
    before_edit = [original_reply, query, reset_ack, old]
    after_edit = [*revised_replies, original_reply, edited_query, reset_ack, old]
    readbacks = iter(
        [
            [old],
            [reset_ack, old],
            [reset_ack, old],
            before_edit,
            before_edit,
            after_edit,
            after_edit,
            after_edit,
            [],
        ]
    )
    sent_ids = iter(["graph-reset", "graph-query"])
    sent_contents = []
    edited = []
    deleted_graph = []
    deleted_msg = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda _chat, content: sent_contents.append(content) or next(sent_ids),
    )
    monkeypatch.setattr(
        e2e,
        "edit_msg_message",
        lambda _chat, message_id, content: edited.append((message_id, content))
        or message_id,
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

    ok, evidence = e2e.test_same_id_edit_reopens_exactly_one_revised_query(
        "unused.log",
        0,
        reply_timeout=0,
        settle_seconds=0,
    )

    assert ok is not duplicate
    assert f"revised_dispatch={2 if duplicate else 1}" in evidence
    assert f"duplicate_dispatch={1 if duplicate else 0}" in evidence
    assert "original_replay=0" in evidence
    assert sent_contents == [
        f"/new {reset_marker}",
        f"Reply with exactly {original_marker}. Do not add other text or use tools.",
    ]
    assert edited == [
        (
            "query",
            f"Reply with exactly {revised_body}. Do not add other text or use tools.",
        )
    ]
    assert deleted_graph == ["graph-reset", "graph-query"]
    expected_deleted = {"ack", "query", "original-reply", "revised-reply"}
    if duplicate:
        expected_deleted.add("revised-reply-duplicate")
    assert set(deleted_msg) == expected_deleted


def test_same_id_revision_e2e_cleans_artifact_after_malformed_send_response(
    monkeypatch,
):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    prefix = "E2EEDITABCDEF123456"
    remote_reset = {"id": "remote-reset", "content": f"/new {prefix}RESET"}
    readbacks = iter([[{"id": "old", "content": "old"}], [remote_reset], []])
    deleted_msg = []

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))

    def malformed_send(_chat, _content):
        raise KeyError("missing response id")

    monkeypatch.setattr(e2e, "send_chat_message", malformed_send)
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda _chat, message_id: deleted_msg.append(message_id),
    )

    with pytest.raises(KeyError, match="missing response id"):
        e2e.test_same_id_edit_reopens_exactly_one_revised_query("unused.log", 0)

    assert deleted_msg == ["remote-reset"]


def test_same_id_revision_e2e_cleanup_failure_fails_the_item(monkeypatch):
    e2e = _load_e2e_module()
    e2e.DM_CHAT_ID = "test-chat"
    prefix = "E2EEDITABCDEF123456"
    remote_reset = {"id": "remote-reset", "content": f"/new {prefix}RESET"}
    readbacks = iter([[{"id": "old", "content": "old"}], [remote_reset], []])

    monkeypatch.setattr(e2e.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    monkeypatch.setattr(e2e, "get_messages_raw", lambda *args, **kwargs: next(readbacks))
    monkeypatch.setattr(
        e2e,
        "send_chat_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyError("missing response id")),
    )
    monkeypatch.setattr(e2e, "delete_graph_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        e2e,
        "delete_msg_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("delete failed")),
    )

    with pytest.raises(RuntimeError, match="cleanup failed"):
        e2e.test_same_id_edit_reopens_exactly_one_revised_query("unused.log", 0)


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

        def refresh(self):
            return "refreshed-graph-token"

    def _legacy_sdk_auth_must_not_run():
        raise AssertionError("legacy SDK TeamsAuth would truncate the live cache")

    monkeypatch.setattr(e2e, "_TeamsAuth", lambda: gateway_auth, raising=False)
    monkeypatch.setattr(
        e2e, "TeamsAuth", _legacy_sdk_auth_must_not_run, raising=False
    )
    monkeypatch.setattr(e2e, "GraphToken", FakeGraphToken)
    setattr(e2e, "_gateway_auth", None)
    setattr(e2e, "_graph_token", None)
    setattr(e2e, "_graph_token_manager", None)

    assert e2e.get_graph_token() == "graph-token"
    assert e2e.get_graph_token() == "graph-token"
    assert e2e.get_graph_token(force_refresh=True) == "refreshed-graph-token"
    assert seen_auth == [gateway_auth]


def test_e2e_graph_send_refreshes_once_on_401(monkeypatch):
    e2e = _load_e2e_module()
    responses = iter(
        [
            SimpleNamespace(status_code=401, text="expired"),
            SimpleNamespace(status_code=201, text="", json=lambda: {"id": "sent"}),
        ]
    )
    refreshes = []

    monkeypatch.setattr(
        e2e,
        "get_graph_token",
        lambda *, force_refresh=False: refreshes.append(force_refresh)
        or ("new" if force_refresh else "old"),
    )
    monkeypatch.setattr(e2e.requests, "post", lambda *args, **kwargs: next(responses))

    assert e2e.send_chat_message("chat", "hello") == "sent"
    assert refreshes == [False, True]


def test_e2e_graph_delete_refreshes_once_on_401(monkeypatch):
    e2e = _load_e2e_module()
    responses = iter(
        [
            SimpleNamespace(status_code=401, text="expired"),
            SimpleNamespace(status_code=204, text=""),
        ]
    )
    refreshes = []

    monkeypatch.setattr(
        e2e,
        "get_graph_token",
        lambda *, force_refresh=False: refreshes.append(force_refresh)
        or ("new" if force_refresh else "old"),
    )
    monkeypatch.setattr(e2e.requests, "delete", lambda *args, **kwargs: next(responses))

    e2e.delete_graph_message("chat", "message")
    assert refreshes == [False, True]


def test_e2e_readback_uses_gateway_atomic_auth(monkeypatch):
    e2e = _load_e2e_module()
    gateway_auth = SimpleNamespace(skype_token=lambda: "skype-token")
    setattr(e2e, "_gateway_auth", gateway_auth)

    assert e2e.get_skype_token() == "skype-token"


def test_e2e_sdk_send_uses_gateway_auth_and_shared_transport(monkeypatch):
    e2e = _load_e2e_module()
    truststore_injections = []
    gateway_auth = SimpleNamespace(
        _inject_truststore=lambda: truststore_injections.append(True),
        msg_base="https://msg.example.invalid/v1/users/ME",
    )
    http = object()
    observed = {}

    class FakeMessagesService:
        def __init__(self, actual_http):
            observed["http"] = actual_http

        def send(self, *, conversation_id, content):
            observed["send"] = (conversation_id, content)
            observed["msg_base"] = messages_module.MSG_BASE
            return {"OriginalArrivalTime": 12345}

    messages_module = importlib.import_module("teams_skype_sdk.api._messages")
    previous_msg_base = messages_module.MSG_BASE

    monkeypatch.setattr(messages_module, "MessagesService", FakeMessagesService)
    monkeypatch.setattr(
        e2e,
        "_get_readback_http_layer",
        lambda actual_auth: http if actual_auth is gateway_auth else None,
    )
    setattr(e2e, "_gateway_auth", gateway_auth)

    result = e2e.send_via_sdk("chat-id", "marker")

    assert result == "12345"
    assert truststore_injections == [True]
    assert observed == {
        "http": http,
        "send": ("chat-id", "marker"),
        "msg_base": gateway_auth.msg_base,
    }
    assert messages_module.MSG_BASE == previous_msg_base
