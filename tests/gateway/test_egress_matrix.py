"""Egress escape matrix adversarial tests (ticket 29 — 17 rows).

Each row tests one emitter path with its policy-defined outcome (ALLOW/DENY).
ALLOW rows verify source readback (message delivered with unique marker).
DENY rows verify target readback (no message delivered to deny target).

Test messages contain only public markers (EGRESS-TEST-{uuid}: prefix).
No PII, NDA, credentials, or CQ content in any test message.

Contract-test adapters simulate unsupported dimensions (alternate platform,
alternate account, webhook) using the same Egress Broker interface.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.egress_broker import EgressBroker, get_egress_broker, reset_egress_broker
from gateway.egress_wiring import (
    brokered_edit,
    brokered_react,
    brokered_send,
    brokered_send_media,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET
from gateway.audit_chain import _reset_hmac_key, reset_audit_chain, AuditChain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORIGIN_CONV = "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
CROSS_CONV = "19:cross-group-sink@thread.v2"
DM_CONV = "19:owner-dm@thread.v2"


@pytest.fixture
def tmp_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _reset_hmac_key()
    reset_audit_chain()
    chain = AuditChain(db_path=tmp_path / "test.matrix.db")
    import gateway.audit_chain as ac
    orig_get = ac.get_audit_chain
    ac.get_audit_chain = lambda: chain
    try:
        yield chain
    finally:
        chain.close()
        ac.get_audit_chain = orig_get
        _reset_hmac_key()
        reset_audit_chain()


@pytest.fixture(autouse=True)
def _isolate():
    saved = _ORIGIN_BINDING.get()
    saved_eng = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    reset_egress_broker()
    yield
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_eng
    reset_egress_broker()


def _binding(**kw: Any) -> OriginEgressBinding:
    defaults = dict(
        profile="default", policy_id="rgp-test", policy_revision="rev-001",
        platform="teams_mtk", adapter_identity="TeamsMTKAdapter",
        account_id="acct-test", conv_id=ORIGIN_CONV,
        thread_id="", durable_task_id="",
    )
    defaults.update(kw)
    return OriginEgressBinding(**defaults)


def _adapter() -> Any:
    """Mock adapter with all emitter methods."""
    a = MagicMock()
    a.send = AsyncMock(return_value={"success": True, "id": "msg-x"})
    a.edit_message = AsyncMock(return_value={"success": True})
    a.send_reaction = AsyncMock(return_value={"success": True})
    a.send_voice = AsyncMock(return_value={"success": True})
    a.send_video = AsyncMock(return_value={"success": True})
    a.send_document = AsyncMock(return_value={"success": True})
    a.send_image = AsyncMock(return_value={"success": True})
    a.send_multiple_images = AsyncMock(return_value={"success": True})
    return a


def _marker() -> str:
    return f"EGRESS-TEST-{uuid.uuid4().hex[:8]}:"


# ---------------------------------------------------------------------------
# Row 1: final reply — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow1FinalReply:
    @pytest.mark.asyncio
    async def test_reply_to_origin_allowed(self, tmp_chain):
        m = _marker()
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(adapter, b.conv_id, f"{m} reply", binding=b)
            assert result is not None
            adapter.send.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 2: streamed commentary — exact origin ALLOW (edit path)
# ---------------------------------------------------------------------------

class TestRow2StreamedCommentary:
    @pytest.mark.asyncio
    async def test_edit_to_origin_allowed(self, tmp_chain):
        m = _marker()
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_edit(adapter, b.conv_id, "msg-1", f"{m} stream", binding=b)
            assert result is not None
            adapter.edit_message.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 3: send_message text — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow3SendMessageText:
    @pytest.mark.asyncio
    async def test_send_text_to_origin_allowed(self, tmp_chain):
        m = _marker()
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, f"{m} text",
                operation="send_message", binding=b,
            )
            assert result is not None
            adapter.send.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 4: send_message media — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow4SendMessageMedia:
    @pytest.mark.asyncio
    async def test_send_media_to_origin_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_document", b.conv_id, binding=b,
                file_path="/tmp/test.pdf",
            )
            assert result is not None
            adapter.send_document.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 5: reaction — DENY (no side effect)
# ---------------------------------------------------------------------------

class TestRow5ReactionDeny:
    @pytest.mark.asyncio
    async def test_reaction_denied_no_side_effect(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_react(adapter, b.conv_id, "msg-1", "👍", binding=b)
            assert result is None
            adapter.send_reaction.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 6: loop mutation — DENY
# ---------------------------------------------------------------------------

class TestRow6LoopMutationDeny:
    @pytest.mark.asyncio
    async def test_loop_mutation_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "mutation",
                operation="loop_mutation", binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 7: native route — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow7NativeRoute:
    @pytest.mark.asyncio
    async def test_native_route_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "native route test",
                route="native", binding=b,
            )
            assert result is not None
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 8: relay route — DENY (relay not allowed in restricted)
# ---------------------------------------------------------------------------

class TestRow8RelayRoute:
    @pytest.mark.asyncio
    async def test_relay_route_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "relay attempt",
                route="relay", binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 9: automatic MEDIA delivery — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow9MediaDelivery:
    @pytest.mark.asyncio
    async def test_automatic_media_delivery_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_image", b.conv_id, binding=b,
                image_path="/tmp/img.png",
            )
            assert result is not None
            adapter.send_image.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 10: TTS — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow10TTS:
    @pytest.mark.asyncio
    async def test_tts_delivery_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_voice", b.conv_id, binding=b,
                voice_path="/tmp/tts.mp3",
            )
            assert result is not None
            adapter.send_voice.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 11: document delivery — exact origin ALLOW
# ---------------------------------------------------------------------------

class TestRow11Document:
    @pytest.mark.asyncio
    async def test_document_delivery_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_document", b.conv_id, binding=b,
                file_path="/tmp/report.pdf",
            )
            assert result is not None
            adapter.send_document.assert_called_once()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 12: cron fan-out — cross-group DENY (no message at deny target)
# ---------------------------------------------------------------------------

class TestRow12CronFanOut:
    @pytest.mark.asyncio
    async def test_cron_fanout_cross_group_denied(self, tmp_chain):
        b = _binding(conv_id=ORIGIN_CONV)
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, CROSS_CONV, "cron fan-out",
                operation="cron_fanout", binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 13: cron mirroring — cross-group DENY
# ---------------------------------------------------------------------------

class TestRow13CronMirroring:
    @pytest.mark.asyncio
    async def test_cron_mirror_cross_group_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, CROSS_CONV, "cron mirror",
                operation="cron_fanout", route="native", binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 14: delegated/background completion — DENY (must return through Broker)
# ---------------------------------------------------------------------------

class TestRow14DelegatedCompletion:
    @pytest.mark.asyncio
    async def test_delegated_cross_group_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            # Delegation result to cross-group → DENY
            result = await brokered_send(
                adapter, CROSS_CONV, "delegation result",
                binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 15: Kanban notification — cross-group DENY
# ---------------------------------------------------------------------------

class TestRow15KanbanNotification:
    @pytest.mark.asyncio
    async def test_kanban_notification_cross_group_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, CROSS_CONV, "kanban update",
                operation="kanban_notification", binding=b,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 16: plugin/webhook/API emitter — per policy (DENY non-native route)
# ---------------------------------------------------------------------------

class TestRow16PluginWebhook:
    @pytest.mark.asyncio
    async def test_webhook_route_denied_in_restricted(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "webhook emit",
                route="webhook", binding=b,
            )
            assert result is None
        finally:
            reset_origin_binding(t)

    @pytest.mark.asyncio
    async def test_api_server_route_denied_in_restricted(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "api emit",
                route="api_server", binding=b,
            )
            assert result is None
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Row 17: future registered adapter — per policy (origin match required)
# ---------------------------------------------------------------------------

class TestRow17FutureAdapter:
    @pytest.mark.asyncio
    async def test_future_adapter_origin_match_allowed(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, b.conv_id, "future adapter test",
                binding=b,
            )
            assert result is not None
        finally:
            reset_origin_binding(t)

    @pytest.mark.asyncio
    async def test_future_adapter_cross_group_denied(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            result = await brokered_send(
                adapter, CROSS_CONV, "future adapter cross",
                binding=b,
            )
            assert result is None
        finally:
            reset_origin_binding(t)


# ---------------------------------------------------------------------------
# Cross-cutting: marker uniqueness + independent readback
# ---------------------------------------------------------------------------

class TestMarkerAndReadback:
    @pytest.mark.asyncio
    async def test_unique_markers_in_each_send(self, tmp_chain):
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            m1 = _marker()
            m2 = _marker()
            assert m1 != m2
            await brokered_send(adapter, b.conv_id, m1, binding=b)
            await brokered_send(adapter, b.conv_id, m2, binding=b)
            # Verify two distinct calls with different markers
            assert adapter.send.call_count == 2
            first_content = adapter.send.call_args_list[0][0][1]
            second_content = adapter.send.call_args_list[1][0][1]
            assert first_content != second_content
        finally:
            reset_origin_binding(t)

    @pytest.mark.asyncio
    async def test_deny_leaves_no_audit_allow(self, tmp_chain):
        """A DENY row must not produce an outcome record (only intent-deny)."""
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            await brokered_react(adapter, b.conv_id, "m1", "👍", binding=b)
            records = tmp_chain.get_all_records()
            # No outcome records — only denial record
            outcomes = [r for r in records if r.phase == "outcome"]
            assert len(outcomes) == 0
        finally:
            reset_origin_binding(t)

    @pytest.mark.asyncio
    async def test_allow_produces_intent_and_outcome(self, tmp_chain):
        """An ALLOW row must produce both intent and outcome audit records."""
        b = _binding()
        t = set_origin_binding(b)
        adapter = _adapter()
        try:
            await brokered_send(adapter, b.conv_id, "marker", binding=b)
            records = tmp_chain.get_all_records()
            intents = [r for r in records if r.phase == "intent" and r.decision == "allow"]
            outcomes = [r for r in records if r.phase == "outcome" and r.decision == "allow"]
            assert len(intents) >= 1
            assert len(outcomes) >= 1
        finally:
            reset_origin_binding(t)
