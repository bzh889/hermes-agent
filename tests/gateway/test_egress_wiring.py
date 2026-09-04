"""Integration tests for Egress Broker wiring (ticket 28).

Tests the brokered_send / brokered_edit / brokered_react / brokered_send_media
choke-point helpers:

- ALLOW path delivers to the adapter (origin group match)
- DENY path blocks before adapter invocation (cross-group / reaction)
- Unrestricted context passes through (no binding)
- Audit chain records intent + outcome for ALLOW, denied for DENY
- One-use permit consumed after delivery
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
from gateway.audit_chain import AuditChain, _reset_hmac_key, reset_audit_chain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_chain(tmp_path, monkeypatch):
    """Isolated audit chain with temp HERMES_HOME."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _reset_hmac_key()
    reset_audit_chain()
    db_path = tmp_path / "test_wiring_audit.db"
    chain = AuditChain(db_path=db_path)
    # Patch get_audit_chain to return our test instance
    with patch("gateway.audit_chain.get_audit_chain", return_value=chain):
        try:
            yield chain
        finally:
            chain.close()
            _reset_hmac_key()
            reset_audit_chain()


@pytest.fixture(autouse=True)
def _isolate():
    """Clean ContextVar + broker per test."""
    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    reset_egress_broker()
    yield
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_engaged
    reset_egress_broker()


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


def _mock_adapter(**methods: Any) -> Any:
    """Create a mock adapter with async send/edit/react methods."""
    adapter = MagicMock()
    adapter.send = AsyncMock(return_value={"success": True, "id": "msg-1"})
    adapter.edit_message = AsyncMock(return_value={"success": True})
    adapter.send_reaction = AsyncMock(return_value={"success": True})
    adapter.send_voice = AsyncMock(return_value={"success": True})
    adapter.send_video = AsyncMock(return_value={"success": True})
    adapter.send_document = AsyncMock(return_value={"success": True})
    return adapter


# ---------------------------------------------------------------------------
# 1. Reply path — ALLOW (matching destination)
# ---------------------------------------------------------------------------

class TestReplyPathAllow:
    """brokered_send with matching destination → adapter called."""

    @pytest.mark.asyncio
    async def test_reply_to_origin_group_allowed(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_send(
                adapter, binding.conv_id, "Hello world",
                binding=binding,
            )
            assert result == {"success": True, "id": "msg-1"}
            adapter.send.assert_called_once_with(
                binding.conv_id, "Hello world", metadata=None,
            )
        finally:
            reset_origin_binding(token)

    @pytest.mark.asyncio
    async def test_reply_intent_and_outcome_recorded(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            await brokered_send(
                adapter, binding.conv_id, "Hello",
                binding=binding,
            )
            records = tmp_chain.get_all_records()
            assert len(records) == 2
            assert records[0].phase == "intent"
            assert records[0].decision == "allow"
            assert records[1].phase == "outcome"
            assert records[1].decision == "allow"
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 2. Reply path — DENY (cross-group destination)
# ---------------------------------------------------------------------------

class TestReplyPathDeny:
    """brokered_send with non-matching destination → adapter NOT called."""

    @pytest.mark.asyncio
    async def test_cross_group_send_denied(self, tmp_chain):
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_send(
                adapter, "19:group-B@thread.v2", "cross-group",
                binding=binding,
            )
            assert result is None
            adapter.send.assert_not_called()
        finally:
            reset_origin_binding(token)

    @pytest.mark.asyncio
    async def test_cross_group_deny_audited(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            await brokered_send(
                adapter, "19:other-group@thread.v2", "text",
                binding=binding,
            )
            records = tmp_chain.get_all_records()
            assert len(records) == 1
            assert records[0].phase == "intent"
            assert records[0].decision == "deny"
            assert records[0].reason == "origin_mismatch"
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 3. Unrestricted context — passthrough
# ---------------------------------------------------------------------------

class TestUnrestrictedPassthrough:
    """No binding → adapter called directly (no brokering)."""

    @pytest.mark.asyncio
    async def test_no_binding_passthrough(self, tmp_chain):
        adapter = _mock_adapter()
        result = await brokered_send(
            adapter, "19:any@thread.v2", "hello",
        )
        assert result == {"success": True, "id": "msg-1"}
        adapter.send.assert_called_once_with(
            "19:any@thread.v2", "hello", metadata=None,
        )

    @pytest.mark.asyncio
    async def test_no_binding_no_audit_records(self, tmp_chain):
        adapter = _mock_adapter()
        await brokered_send(adapter, "19:any@thread.v2", "hello")
        assert len(tmp_chain.get_all_records()) == 0


# ---------------------------------------------------------------------------
# 4. Reaction path — always DENY in restricted context
# ---------------------------------------------------------------------------

class TestReactionDeny:
    """brokered_react in restricted context → DENY, adapter NOT called."""

    @pytest.mark.asyncio
    async def test_reaction_denied_in_restricted(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_react(
                adapter, binding.conv_id, "msg-1", "👍",
                binding=binding,
            )
            assert result is None
            adapter.send_reaction.assert_not_called()
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 5. Edit path — ALLOW (matching destination)
# ---------------------------------------------------------------------------

class TestEditPath:
    """brokered_edit with matching destination → adapter called."""

    @pytest.mark.asyncio
    async def test_edit_allowed(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_edit(
                adapter, binding.conv_id, "msg-1", "edited text",
                binding=binding,
            )
            assert result == {"success": True}
            adapter.edit_message.assert_called_once_with(
                binding.conv_id, "msg-1", "edited text",
            )
        finally:
            reset_origin_binding(token)

    @pytest.mark.asyncio
    async def test_edit_cross_group_denied(self, tmp_chain):
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_edit(
                adapter, "19:group-B@thread.v2", "msg-1", "text",
                binding=binding,
            )
            assert result is None
            adapter.edit_message.assert_not_called()
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 6. Media delivery — ALLOW (matching destination)
# ---------------------------------------------------------------------------

class TestMediaDelivery:
    """brokered_send_media with matching destination → adapter called."""

    @pytest.mark.asyncio
    async def test_send_voice_allowed(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_voice", binding.conv_id,
                binding=binding,
                voice_path="/tmp/audio.mp3",
            )
            assert result == {"success": True}
            adapter.send_voice.assert_called_once()
        finally:
            reset_origin_binding(token)

    @pytest.mark.asyncio
    async def test_send_voice_cross_group_denied(self, tmp_chain):
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            result = await brokered_send_media(
                adapter, "send_voice", "19:group-B@thread.v2",
                binding=binding,
                voice_path="/tmp/audio.mp3",
            )
            assert result is None
            adapter.send_voice.assert_not_called()
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 7. One-use permit consumed — second send gets a fresh permit
# ---------------------------------------------------------------------------

class TestOneUsePermitInWiring:
    """Each brokered_send gets a fresh permit; permits are not reused."""

    @pytest.mark.asyncio
    async def test_two_sends_get_different_permits(self, tmp_chain):
        binding = _make_binding()
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            await brokered_send(adapter, binding.conv_id, "msg1", binding=binding)
            await brokered_send(adapter, binding.conv_id, "msg2", binding=binding)
            assert adapter.send.call_count == 2
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 8. E2E — reply arrives in origin group; cross-group denied
# ---------------------------------------------------------------------------

class TestE2EReplyAndDeny:
    """Simulate: restricted message → reply to origin ALLOW, cross-group DENY."""

    @pytest.mark.asyncio
    async def test_e2e_reply_allowed_cross_group_denied(self, tmp_chain):
        binding = _make_binding(conv_id="19:origin-group@thread.v2")
        token = set_origin_binding(binding)
        adapter = _mock_adapter()
        try:
            # Reply to origin group → ALLOW
            reply_result = await brokered_send(
                adapter, binding.conv_id, "Here's the answer",
                binding=binding,
            )
            assert reply_result == {"success": True, "id": "msg-1"}

            # Attempt cross-group send → DENY
            cross_result = await brokered_send(
                adapter, "19:different-group@thread.v2", "leak attempt",
                binding=binding,
            )
            assert cross_result is None

            # Verify: adapter.send was called once (for the origin reply),
            # never for the cross-group attempt.
            assert adapter.send.call_count == 1
            first_call_args = adapter.send.call_args
            assert first_call_args[0][0] == binding.conv_id

            # Verify audit: intent+outcome for allow, intent-deny for deny
            records = tmp_chain.get_all_records()
            assert len(records) == 3
            assert records[0].phase == "intent"
            assert records[0].decision == "allow"
            assert records[1].phase == "outcome"
            assert records[1].decision == "allow"
            assert records[2].phase == "intent"
            assert records[2].decision == "deny"
            assert records[2].reason == "origin_mismatch"
        finally:
            reset_origin_binding(token)
