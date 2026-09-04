"""Unit tests for exact-group semantic history retrieval (ticket 34)."""

from __future__ import annotations

from typing import Any

import pytest

from gateway.restricted_history import (
    CrossConversationError,
    HistoryMessage,
    HistoryResult,
    format_history_for_injection,
    retrieve_history,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET


@pytest.fixture(autouse=True)
def _isolate():
    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    yield
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_engaged


def _make_binding(**overrides: Any) -> OriginEgressBinding:
    defaults = dict(
        profile="default",
        policy_id="rgp-test-v1",
        policy_revision="rev-001",
        platform="teams_mtk",
        adapter_identity="TeamsMTKAdapter",
        account_id="acct-test-001",
        conv_id="19:origin-group@thread.v2",
        thread_id="",
        durable_task_id="",
    )
    defaults.update(overrides)
    return OriginEgressBinding(**defaults)


def _mock_msg(mid: str, content: str = "hello", reply_to: str = "") -> dict:
    return {
        "message_id": mid,
        "sender_id": "user-1",
        "sender_name": "Alice",
        "content": content,
        "timestamp": "2026-09-03T10:00:00Z",
        "reply_to": reply_to,
        "attachments": [],
    }


# ---------------------------------------------------------------------------

class TestReplyChainTraversal:
    def test_reply_chain_fetches_messages(self):
        binding = _make_binding()
        fetch = lambda cid, limit=50, backward_link="": [_mock_msg("m1"), _mock_msg("m2")]
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        assert len(result.messages) == 2
        assert result.retrieval_method in ("reply_chain", "combined")

    def test_empty_history_returns_empty_method(self):
        binding = _make_binding()
        fetch = lambda cid, limit=50, backward_link="": []
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        assert result.retrieval_method == "empty"
        assert len(result.messages) == 0


class TestSlidingWindow:
    def test_sliding_window_supplements_reply_chain(self):
        binding = _make_binding()
        # Reply-chain returns 1 message, sliding window returns 2 more
        call_count = [0]
        def fetch(cid, limit=50, backward_link=""):
            call_count[0] += 1
            if call_count[0] == 1:
                return [_mock_msg("m1")]
            return [_mock_msg("m2"), _mock_msg("m3")]
        result = retrieve_history(fetch, binding.conv_id, binding=binding, window_size=5)
        assert len(result.messages) == 3


class TestCrossConversationGuard:
    def test_cross_conversation_denied(self):
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        fetch = lambda cid, limit=50, backward_link="": []
        with pytest.raises(CrossConversationError, match="mismatch"):
            retrieve_history(fetch, "19:group-B@thread.v2", binding=binding)

    def test_no_binding_allows_any_conv_id(self):
        fetch = lambda cid, limit=50, backward_link="": [_mock_msg("m1")]
        result = retrieve_history(fetch, "19:any@thread.v2")
        assert len(result.messages) == 1


class TestNoRedaction:
    def test_content_not_redacted(self):
        binding = _make_binding()
        sensitive = "TOP_SECRET_DATA_12345"
        fetch = lambda cid, limit=50, backward_link="": [
            _mock_msg("m1", content=sensitive)
        ]
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        assert any(sensitive in msg.content for msg in result.messages)


class TestNoPreFilter:
    def test_all_messages_returned_no_filter(self):
        binding = _make_binding()
        msgs = [_mock_msg(f"m{i}", content=f"message {i}") for i in range(10)]
        fetch = lambda cid, limit=50, backward_link="": msgs[:5]
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        assert len(result.messages) >= 5


class TestFormatForInjection:
    def test_role_alternation_preserved(self):
        result = HistoryResult(
            messages=[HistoryMessage(
                message_id="m1",
                sender_id="u1",
                sender_name="Alice",
                content="Hello",
                timestamp="2026-09-03T10:00:00Z",
            )],
            conv_id="19:conv@thread.v2",
            retrieval_method="reply_chain",
        )
        user_msg, ack = format_history_for_injection(result)
        # user_msg is the history block
        assert "Alice" in user_msg
        assert "Hello" in user_msg
        # ack is the assistant separator
        assert ack  # non-empty
        assert "Understood" in ack

    def test_attachments_rendered_as_previews(self):
        result = HistoryResult(
            messages=[HistoryMessage(
                message_id="m1",
                sender_id="u1",
                sender_name="Bob",
                content="See attached",
                timestamp="2026-09-03T10:00:00Z",
                attachments=[{"name": "report.pdf", "preview": "page 1"}],
            )],
            conv_id="conv",
            retrieval_method="reply_chain",
        )
        user_msg, _ = format_history_for_injection(result)
        assert "📎" in user_msg
        assert "report.pdf" in user_msg
        assert "page 1" in user_msg


# ---------------------------------------------------------------------------
# Forced marker tests (3 layers)
# ---------------------------------------------------------------------------

class TestForcedMarkerLayer1:
    """Layer 1: API-level marker present in correct conversation only."""
    def test_marker_in_correct_conversation(self):
        binding = _make_binding(conv_id="19:marked@thread.v2")
        MARKER = "UUID-MARKER-AAA"
        fetch = lambda cid, limit=50, backward_link="": [
            _mock_msg("m1", content=f"normal {MARKER} text"),
        ]
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        assert any(MARKER in msg.content for msg in result.messages)

    def test_marker_not_in_wrong_conversation(self):
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        fetch = lambda cid, limit=50, backward_link="": []
        with pytest.raises(CrossConversationError):
            retrieve_history(fetch, "19:group-B@thread.v2", binding=binding)


class TestForcedMarkerLayer2:
    """Layer 2: red marker visible in origin group, absent in cross-group."""
    def test_marker_visible_in_origin(self):
        binding = _make_binding(conv_id="19:origin@thread.v2")
        fetch = lambda cid, limit=50, backward_link="": [
            _mock_msg("m1", content="RED-MARKER-XYZ"),
        ]
        result = retrieve_history(fetch, binding.conv_id, binding=binding)
        contents = [m.content for m in result.messages]
        assert any("RED-MARKER-XYZ" in c for c in contents)

    def test_cross_group_injection_denied(self):
        binding = _make_binding(conv_id="19:origin@thread.v2")
        fetch_A = lambda cid, limit=50, backward_link="": [
            _mock_msg("m1", content="RED-MARKER-XYZ"),
        ]
        # Attempt retrieval from a different conv_id → denied
        with pytest.raises(CrossConversationError):
            retrieve_history(fetch_A, "19:cross@thread.v2", binding=binding)


class TestForcedMarkerLayer3:
    """Layer 3: dual-group cross-injection attempt → DENY."""
    def test_dual_group_cross_injection_denied(self):
        binding_A = _make_binding(conv_id="19:group-A@thread.v2")
        binding_B = _make_binding(conv_id="19:group-B@thread.v2")
        fetch_A = lambda cid, limit=50, backward_link="": [
            _mock_msg("m1", content="MARKER-A"),
        ]
        # Group A retrieves its own history — OK
        result_A = retrieve_history(fetch_A, binding_A.conv_id, binding=binding_A)
        assert any("MARKER-A" in m.content for m in result_A.messages)

        # Attempt to inject group A's markers into group B → DENY
        # Use binding_B but try to fetch from group-A's conv_id
        with pytest.raises(CrossConversationError):
            retrieve_history(fetch_A, binding_A.conv_id, binding=binding_B)
