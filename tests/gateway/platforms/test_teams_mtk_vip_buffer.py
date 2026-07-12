"""Unit tests for TeamsMTKAdapter G14-Layer-1: VIP sender buffering.

Covers _VIPBuffer pure logic + adapter wiring.
"""

import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from gateway.platforms.teams_mtk import _VIPBuffer, TeamsMTKAdapter


def _make_buf(**overrides):
    """Create a _VIPBuffer with sensible defaults."""
    defaults = dict(
        conv_id="19:dm@unq",
        oids=["oid-vip-1", "oid-vip-2"],
        notify_targets=["19:target@thread.v2"],
        buffer_timeout_seconds=5.0,
    )
    defaults.update(overrides)
    return _VIPBuffer(**defaults)


def _make_adapter():
    return TeamsMTKAdapter(config=None)


# ── _VIPBuffer unit tests (pure logic, no I/O) ──────────────────────────

class TestVIPBufferLogic:
    def test_is_vip_true(self):
        buf = _make_buf()
        assert buf.is_vip("oid-vip-1") is True

    def test_is_vip_false(self):
        buf = _make_buf()
        assert buf.is_vip("oid-other") is False

    def test_add_immediate_flush_on_sentence_end(self):
        buf = _make_buf()
        msg = {"content": "Are you free tomorrow?"}
        assert buf.add(msg) == "immediate"

    def test_add_immediate_flush_on_long_message(self):
        buf = _make_buf()
        msg = {"content": "x" * 101}
        assert buf.add(msg) == "immediate"

    def test_add_buffered_short_fragment(self):
        buf = _make_buf()
        msg = {"content": "hey"}
        assert buf.add(msg) == "buffered"
        assert len(buf._messages) == 1

    def test_add_accumulates_across_calls(self):
        buf = _make_buf()
        buf.add({"content": "hey"})
        buf.add({"content": "there"})
        assert len(buf._messages) == 2

    def test_should_flush_empty_buffer(self):
        buf = _make_buf()
        assert buf.should_flush() is False

    def test_should_flush_stale_buffer(self):
        buf = _make_buf()
        buf.add({"content": "hey"})
        # Simulate time passing by adjusting _first_msg_at
        buf._first_msg_at = time.time() - 10  # 10s ago > 5s timeout
        assert buf.should_flush() is True

    def test_should_flush_fresh_buffer(self):
        buf = _make_buf()
        buf.add({"content": "hey"})
        assert buf.should_flush() is False

    def test_drain_resets_state(self):
        buf = _make_buf()
        buf.add({"content": "hey"})
        buf.add({"content": "there"})
        msgs = buf.drain()
        assert len(msgs) == 2
        assert buf._messages == []
        assert buf._first_msg_at is None

    def test_drain_empty(self):
        buf = _make_buf()
        assert buf.drain() == []

    def test_immediate_flush_chinese_punctuation(self):
        buf = _make_buf()
        assert buf.add({"content": "明天開會。"}) == "immediate"

    def test_immediate_flush_exclamation(self):
        buf = _make_buf()
        assert buf.add({"content": "快點！"}) == "immediate"


# ── TeamsMTKAdapter wiring ─────────────────────────────────────────────

class TestAdapterVIPWiring:
    def test_adapter_no_vip_config_by_default(self):
        adapter = _make_adapter()
        assert adapter._vip_config == {}

    def test_adapter_has_vip_buffers_dict(self):
        adapter = _make_adapter()
        assert hasattr(adapter, "_vip_buffers")
        assert isinstance(adapter._vip_buffers, dict)

    @pytest.mark.asyncio
    async def test_flush_vip_buffer_empty(self):
        adapter = _make_adapter()
        # Should not crash on empty or missing buffer
        await adapter._flush_vip_buffer("19:nonexistent@unq")

    @pytest.mark.asyncio
    async def test_flush_vip_buffer_with_messages(self):
        adapter = _make_adapter()
        conv_id = "19:dm@unq"
        buf = _make_buf(conv_id=conv_id)
        adapter._vip_buffers[conv_id] = buf
        buf.add({"content": "hey", "imdisplayname": "Boss"})
        buf.add({"content": "where?", "imdisplayname": "Boss"})

        with patch.object(adapter, "send", new_callable=AsyncMock) as mock_send:
            await adapter._flush_vip_buffer(conv_id)
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert "VIP buffered" in call_args[1]
            assert "2 msg" in call_args[1]

    @pytest.mark.asyncio
    async def test_vip_interception_in_process_new_messages(self):
        """VIP msg is intercepted and buffered, not dispatched to agent."""
        adapter = _make_adapter()
        conv_id = "19:dm@unq"
        adapter._last_message_ids[conv_id] = "0"
        adapter._vip_config = {
            "enabled": True,
            "oids": ["vip-oid"],
            "notify_targets": ["19:target@thread.v2"],
            "buffer_timeout_seconds": 60,
        }
        adapter._vip_buffers = {}
        # _process_new_messages early-returns if _message_handler is None
        adapter._message_handler = lambda *a, **k: None

        messages = [{
            "id": "1",
            "messagetype": "Text",
            "content": "<p>short msg</p>",
            "imdisplayname": "VIP User",
            "from": "8:orgid:vip-oid",
            "properties": {},
        }]

        # VIP msg should be buffered, handle_message should NOT be called
        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as mock_handle:
            await adapter._process_new_messages(conv_id, messages)
            mock_handle.assert_not_called()

        buf = adapter._vip_buffers.get(conv_id)
        assert buf is not None, f"VIP buffer not created; _vip_config={adapter._vip_config}"
        assert len(buf._messages) == 1
