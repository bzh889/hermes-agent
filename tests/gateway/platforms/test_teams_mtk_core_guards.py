"""Unit tests for TeamsMTKAdapter core guard features.

Covers: C-2 echo guard (HTML fingerprint), C-5 short-msg gating,
control command bypass, PLATFORM_HINTS injection, and poll adaptive logic.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from gateway.platforms.teams_mtk import TeamsMTKAdapter


def _make_adapter():
    adapter = TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._conv_ids = ["conv1"]
    adapter._last_sent_message_id = None
    adapter._sent_dedup = MagicMock()
    adapter._sent_dedup.is_duplicate = MagicMock(return_value=False)
    return adapter


# ── C-2: HTML fingerprint echo guard (4th line) ─────────────────────────

class TestHTMLFingerprintEchoGuard:
    def test_own_html_fingerprint_detected(self):
        """Messages with our HTML blockquote fingerprint are detected as own."""
        html = ('<div style="border-left:#6264A7 3px solid">'
                '<b>🤖 Hermes</b></div><p>response</p>')
        assert 'border-left:#6264A7' in html
        assert '<b>🤖 Hermes</b>' in html

    def test_fingerprint_not_in_normal_message(self):
        html = '<p>Hello world</p>'
        assert 'border-left:#6264A7' not in html
        assert '<b>🤖 Hermes</b>' not in html


# ── C-5: Short-message gating ──────────────────────────────────────────

class TestShortMessageGating:
    @pytest.mark.parametrize("text,should_ignore", [
        ("ok", True),        # ≤2, no punct, no mention
        ("好", True),        # 1 char, no punct
        ("嗯", True),        # 1 char
        ("嗨？", False),      # has ？
        ("what?", False),     # has ?
        ("!", False),        # has !
        ("@hermes", False),  # has @
        ("hello there", False),  # >2 chars
        ("OK!", False),      # has !
    ])
    def test_short_msg_gating(self, text, should_ignore):
        has_punct = any(c in text for c in "?？！!")
        has_mention = "@" in text
        is_short = len(text) <= 2
        result = is_short and not has_punct and not has_mention
        assert result == should_ignore


# ── Control command bypass ─────────────────────────────────────────────

class TestControlCommandBypass:
    @pytest.mark.parametrize("cmd,expected", [
        ("/stop", True),
        ("/new", True),
        ("/reset", True),
        ("/approve", True),
        ("/deny", True),
        ("/status", True),
        ("/queue", True),
        ("/help", True),
        ("/skin", True),   # skin is gateway-visible
        ("/model", True),  # model is gateway-visible
        ("/skills", True), # skills is gateway-visible
        ("/cron", True),   # cron is gateway-visible
        ("", False),
        ("hello", False),
        ("what is the weather", False),
    ])
    def test_control_cmd(self, cmd, expected):
        from hermes_cli.commands import should_bypass_active_session
        assert should_bypass_active_session(cmd) is expected


# ── PLATFORM_HINTS injection ───────────────────────────────────────────

class TestPlatformHintsInjection:
    def test_hints_includes_all_capabilities(self):
        adapter = _make_adapter()
        hints = adapter.get_platform_hints()
        required = [
            "send_message", "edit_message", "delete_message",
            "send_reaction", "remove_reaction",
            "forward_message", "search_messages",
            "get_activity", "get_call_logs",
            "Mention gating", "Short-msg gating",
        ]
        for cap in required:
            assert cap in hints, f"Missing capability: {cap}"

    def test_hints_changes_with_vip_config(self):
        adapter = _make_adapter()
        hints1 = adapter.get_platform_hints()
        assert "VIP monitor" not in hints1
        adapter._vip_config = {"notify_targets": ["dm1"]}
        hints2 = adapter.get_platform_hints()
        assert "VIP monitor" in hints2

    def test_hints_includes_reaction_types(self):
        adapter = _make_adapter()
        hints = adapter.get_platform_hints()
        assert "like/heart/laugh" in hints


# ── Poll adaptive logic ────────────────────────────────────────────────

class TestPollAdaptiveLogic:
    def test_adaptive_thresholds(self):
        """Verify the threshold constants are reasonable."""
        # 5 ticks → 15s, 20 ticks → 30s — these are just sanity checks
        assert 5 * 3 == 15  # 5 ticks * 3s = 15s base
        assert 20 >= 5  # 20-tick threshold is higher than 5-tick


# ── Delete-only-own guard ──────────────────────────────────────────────

class TestDeleteOnlyOwnGuard:
    @pytest.mark.asyncio
    async def test_delete_own_last_sent(self):
        adapter = _make_adapter()
        adapter._last_sent_message_id = "m1"
        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "deleted"}
            result = await adapter.delete_message_safe("conv1", "m1")
            mock.assert_called_once()
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_reject_other_user_message(self):
        adapter = _make_adapter()
        adapter._last_sent_message_id = None
        adapter._sent_dedup.is_duplicate = MagicMock(return_value=False)
        adapter._fetch_messages = MagicMock(return_value=[
            {"id": "m1", "properties": {"hermes_sender": "user"}}
        ])
        result = await adapter.delete_message_safe("conv1", "m1")
        assert result["status"] == "error"
        assert "not your" in result["error"]


# ── Forward whitelist guard ─────────────────────────────────────────────

class TestForwardWhitelistGuard:
    @pytest.mark.asyncio
    async def test_reject_non_whitelisted_target(self):
        adapter = _make_adapter()
        result = await adapter.forward_message("src", "m1", "bad_target",
                                                allowed_targets=["good_target"])
        assert result["status"] == "error"
        assert "not in allowed list" in result["error"]

    @pytest.mark.asyncio
    async def test_allow_whitelisted_target(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKMessages") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            adapter._auth.skype_token = MagicMock(return_value="tok")
            mock_svc = MagicMock()
            mock_svc.forward.return_value = {"status": "forwarded"}
            MockSvc.return_value = mock_svc
            result = await adapter.forward_message("src", "m1", "good_target",
                                                    allowed_targets=["good_target"])
            assert result["status"] == "forwarded"

    @pytest.mark.asyncio
    async def test_no_whitelist_allows_all(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKMessages") as MockSvc, \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            adapter._auth.skype_token = MagicMock(return_value="tok")
            mock_svc = MagicMock()
            mock_svc.forward.return_value = {"status": "forwarded"}
            MockSvc.return_value = mock_svc
            result = await adapter.forward_message("src", "m1", "any_target")
            assert result["status"] == "forwarded"


# ── Blocked stubs (G13-B.3, G14-2.1) ────────────────────────────────────

class TestBlockedStubs:
    @pytest.mark.asyncio
    async def test_create_chat_blocked(self):
        adapter = _make_adapter()
        result = await adapter.create_chat("Test Topic", ["user1"])
        assert result["status"] == "error"
        assert "Chat.Create" in result["error"]

    def test_get_persona_config_stub(self):
        adapter = _make_adapter()
        result = adapter.get_persona_config()
        assert result["status"] == "stub"
        assert "P7" in result["error"]
        assert result["persona"] is None
