"""Unit tests for TeamsMTKAdapter Phase 2 features.

Covers: S4 Activity, S5 Call logs, S10 Forward,
        S9-2 delete-only-own, S1-5 PKB landing, S2-4 Global search,
        PLATFORM_HINTS, WS-8~9 stability metrics.
"""

import os
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest

from gateway.platforms.teams_mtk import TeamsMTKAdapter, _POLL_INTERVAL


def _make_adapter():
    adapter = TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._conv_ids = ["conv1", "conv2"]
    return adapter


# ── S4: Activity feed ──────────────────────────────────────────────────

class TestGetActivity:
    @pytest.mark.asyncio
    async def test_invalid_kind(self):
        adapter = _make_adapter()
        result = await adapter.get_activity("nonexistent", limit=5)
        assert len(result) == 1
        assert "Unknown activity kind" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_sdk_path_spaces(self):
        adapter = _make_adapter()
        adapter._auth._skype_token = "fake"
        mock_items = [{"id": "s1", "type": "Space"}]
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKActivity") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            mock_svc = MagicMock()
            mock_svc.list_spaces.return_value = mock_items
            MockSvc.return_value = mock_svc
            result = await adapter.get_activity("spaces", limit=5)
            assert len(result) == 1
            assert result[0]["id"] == "s1"

    @pytest.mark.asyncio
    async def test_sdk_unavailable(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False):
            result = await adapter.get_activity("spaces", limit=5)
            assert "error" in result[0]


# ── S5: Call logs ──────────────────────────────────────────────────────

class TestGetCallLogs:
    @pytest.mark.asyncio
    async def test_delegates_to_get_activity(self):
        adapter = _make_adapter()
        with patch.object(adapter, "get_activity", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "call1"}]
            result = await adapter.get_call_logs(limit=10)
            mock.assert_called_once_with("call_logs", 10, 0)
            assert result == [{"id": "call1"}]


# ── S10: Forward ───────────────────────────────────────────────────────

class TestForwardMessage:
    @pytest.mark.asyncio
    async def test_whitelist_reject(self):
        adapter = _make_adapter()
        result = await adapter.forward_message(
            "src", "m1", "target",
            allowed_targets=["other_conv"]
        )
        assert result["status"] == "error"
        assert "not in allowed list" in result["error"]

    @pytest.mark.asyncio
    async def test_whitelist_allow(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKMessages") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            adapter._auth._skype_token = "fake"
            mock_svc = MagicMock()
            mock_svc.forward.return_value = {"status": "forwarded"}
            MockSvc.return_value = mock_svc
            result = await adapter.forward_message(
                "src", "m1", "target",
                allowed_targets=["target"]
            )
            assert result["status"] == "forwarded"

    @pytest.mark.asyncio
    async def test_no_whitelist_passes(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKMessages") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            adapter._auth._skype_token = "fake"
            mock_svc = MagicMock()
            mock_svc.forward.return_value = {"status": "forwarded"}
            MockSvc.return_value = mock_svc
            result = await adapter.forward_message("src", "m1", "target")
            assert result["status"] == "forwarded"


# ── S9-2: Delete-only-own ─────────────────────────────────────────────

class TestDeleteMessageSafe:
    @pytest.mark.asyncio
    async def test_delete_own_last_sent(self):
        adapter = _make_adapter()
        adapter._last_sent_message_id = "msg1"
        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "deleted"}
            result = await adapter.delete_message_safe("conv1", "msg1")
            mock.assert_called_once()
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_dedup_own(self):
        adapter = _make_adapter()
        adapter._last_sent_message_id = None
        adapter._sent_dedup.is_duplicate = MagicMock(return_value=True)
        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "deleted"}
            result = await adapter.delete_message_safe("conv1", "msg1")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_not_own(self):
        adapter = _make_adapter()
        adapter._last_sent_message_id = None
        adapter._sent_dedup.is_duplicate = MagicMock(return_value=False)
        # _fetch_messages returns a message not from agent
        adapter._fetch_messages = MagicMock(return_value=[
            {"id": "msg1", "properties": {"hermes_sender": "user"}}
        ])
        result = await adapter.delete_message_safe("conv1", "msg1")
        assert result["status"] == "error"
        assert "not your" in result["error"]


# ── S1-5: PKB instant landing ─────────────────────────────────────────

class TestPKBLanding:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_group_config", return_value={}):
            # Should not write anything
            await adapter.on_message_processed("conv_thread@thread.v2",
                                               {"content": "hi"}, "hello")
            # No error = pass (simply returns early)

    @pytest.mark.asyncio
    async def test_enabled_writes_file(self):
        adapter = _make_adapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {"pkb_instant_landing": True, "pkb_landing_dir": tmpdir}
            with patch.object(adapter, "_group_config", return_value=cfg):
                msg = {"content": "<p>hello</p>", "imdisplayname": "Alice",
                       "composetime": "2026-01-01T00:00:00Z"}
                await adapter.on_message_processed("conv_thread@thread.v2", msg, "hi back")
                # Check file was created
                files = os.listdir(tmpdir)
                assert len(files) == 1
                content = open(os.path.join(tmpdir, files[0]), encoding="utf-8").read()
                assert "Alice" in content
                assert "Hermes" in content


# ── S2-4: Global search ───────────────────────────────────────────────

class TestSearchAllConversations:
    @pytest.mark.asyncio
    async def test_merges_results(self):
        adapter = _make_adapter()
        adapter._search_messages = MagicMock()
        adapter._search_messages.side_effect = [
            [{"id": "m1", "originalarrivaltime": "2026-01-01"}],
            [{"id": "m2", "originalarrivaltime": "2026-01-02"}],
        ]
        result = await adapter.search_all_conversations("test", limit=10)
        assert len(result) == 2
        assert result[0]["id"] == "m2"  # newer first

    @pytest.mark.asyncio
    async def test_limits_results(self):
        adapter = _make_adapter()
        adapter._search_messages = MagicMock()
        adapter._search_messages.return_value = [{"id": f"m{i}"} for i in range(5)]
        result = await adapter.search_all_conversations("test", limit=3)
        assert len(result) == 3


# ── PLATFORM_HINTS ─────────────────────────────────────────────────────

class TestPlatformHints:
    def test_contains_key_capabilities(self):
        adapter = _make_adapter()
        hints = adapter.get_platform_hints()
        assert "Platform: Microsoft Teams" in hints
        assert "send_reaction" in hints
        assert "delete_message" in hints
        assert "forward_message" in hints
        assert "get_activity" in hints
        assert "search_messages" in hints

    def test_vip_config_shows_targets(self):
        adapter = _make_adapter()
        adapter._vip_config = {"notify_targets": ["user1"]}
        hints = adapter.get_platform_hints()
        assert "VIP monitor" in hints


# ── WS-8~9: Stability metrics ──────────────────────────────────────────

class TestWSStabilityMetrics:
    def test_trouter_is_healthy(self):
        """_TrouterListener.is_healthy() returns True when connected + recent pong."""
        from gateway.platforms.teams_mtk import _TrouterListener
        listener = _TrouterListener.__new__(_TrouterListener)
        listener._ws = MagicMock()
        listener._ws.closed = False
        listener._last_pong_time = 9999999999.0  # far future
        listener._heartbeat_timeout = 30
        assert listener.is_healthy() is True

    def test_trouter_not_healthy_closed(self):
        from gateway.platforms.teams_mtk import _TrouterListener
        listener = _TrouterListener.__new__(_TrouterListener)
        listener._ws = MagicMock()
        listener._ws.closed = True
        listener._last_pong_time = 9999999999.0
        listener._heartbeat_timeout = 30
        assert listener.is_healthy() is False

    def test_trouter_not_healthy_no_pong(self):
        from gateway.platforms.teams_mtk import _TrouterListener
        listener = _TrouterListener.__new__(_TrouterListener)
        listener._ws = MagicMock()
        listener._ws.closed = False
        listener._last_pong_time = None
        listener._heartbeat_timeout = 30
        assert listener.is_healthy() is False

    def test_trouter_not_healthy_stale_pong(self):
        import time
        from gateway.platforms.teams_mtk import _TrouterListener
        listener = _TrouterListener.__new__(_TrouterListener)
        listener._ws = MagicMock()
        listener._ws.closed = False
        listener._last_pong_time = time.time() - 100  # 100s ago
        listener._heartbeat_timeout = 30
        assert listener.is_healthy() is False


# ── G15: Whitelist visibility ──────────────────────────────────────────

class TestListWhitelistedGroups:
    def test_returns_whitelisted_groups(self):
        adapter = _make_adapter()
        mock_config = {"gateway": {"teams_mtk": {"groups": {
            "conv1@thread.v2": {"require_mention": False, "label": "test-group"},
        }}}}
        with patch("hermes_cli.config.load_config_readonly", return_value=mock_config):
            result = adapter.list_whitelisted_groups()
        assert len(result) == 1
        assert result[0]["chat_id"] == "conv1@thread.v2"
        assert result[0]["require_mention"] is False
        assert result[0]["label"] == "test-group"

    def test_empty_when_no_groups(self):
        adapter = _make_adapter()
        mock_config = {"gateway": {"teams_mtk": {}}}
        with patch("hermes_cli.config.load_config_readonly", return_value=mock_config):
            result = adapter.list_whitelisted_groups()
        assert result == []

    def test_handles_config_error(self):
        adapter = _make_adapter()
        with patch("hermes_cli.config.load_config_readonly", side_effect=Exception("boom")):
            result = adapter.list_whitelisted_groups()
        assert result == []
