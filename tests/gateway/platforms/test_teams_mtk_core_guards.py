"""Unit tests for TeamsMTKAdapter core guard features.

Covers: C-2 echo ownership, C-5 short-msg gating,
control command bypass, PLATFORM_HINTS injection, and poll adaptive logic.
"""

import ast
import asyncio
import inspect

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import gateway.platforms.teams_mtk as teams_mtk_module
from gateway.platforms.teams_mtk import TeamsMTKAdapter, _log_error, _log_ref


def _make_adapter():
    adapter = TeamsMTKAdapter(config=None)
    adapter._message_handler = AsyncMock()
    adapter._conv_ids = ["conv1"]
    adapter._last_sent_message_id = None
    return adapter


def test_http_calls_never_disable_tls_verification():
    """HTTP and WebSocket clients must keep certificate validation enabled."""
    source = inspect.getsource(teams_mtk_module)
    assert "verify=False" not in source
    assert "verify_ssl=False" not in source
    assert "ssl=False" not in source
    assert "CERT_NONE" not in source
    assert "check_hostname = False" not in source
    assert "disable_warnings" not in source
    assert "_sdk_download, url, _sk, _at, False" not in source


def test_log_refs_are_deterministic_and_non_reversible():
    raw = "sensitive-routing-id"
    ref = _log_ref(raw)

    assert ref == _log_ref(raw)
    assert ref.startswith("sha256:")
    assert raw not in ref


def test_log_error_drops_exception_message_but_keeps_status():
    error = RuntimeError("GET https://secret.example/path?token=super-secret")
    error.status_code = 401

    safe = _log_error(error)

    assert safe == "RuntimeError status=401"
    assert "secret" not in safe
    assert "http" not in safe


def test_logger_calls_never_emit_exception_text_or_tracebacks():
    source = inspect.getsource(teams_mtk_module)
    tree = ast.parse(source)
    exception_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and isinstance(node.name, str)
    }

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        ):
            continue
        direct_exception_args = []
        for arg in node.args:
            is_sanitized = (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "_log_error"
            )
            if is_sanitized:
                continue
            direct_exception_args.extend(
                child.id
                for child in ast.walk(arg)
                if isinstance(child, ast.Name) and child.id in exception_names
            )
        assert not direct_exception_args, (node.lineno, direct_exception_args)
        assert not any(
            keyword.arg == "exc_info"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        ), node.lineno


def test_source_does_not_log_message_text_or_raw_routing_ids():
    source = inspect.getsource(teams_mtk_module)

    assert "text[:60]" not in source
    assert "url=%.60s" not in source
    assert "chat_id[:30]" not in source
    assert "conv_id[:30]" not in source


# ── C-5: Short-message gating ──────────────────────────────────────────

class TestShortMessageGating:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("text,short_message_ignore,should_dispatch", [
        ("好", True, False),
        ("嗯", True, False),
        ("?", True, True),
        ("！", True, True),
        ("好了啊", True, True),
        ("好", False, True),
        ("@hermes 好", True, True),
    ])
    async def test_short_message_policy_dispatches_through_adapter(
        self, text, short_message_ignore, should_dispatch,
    ):
        adapter = _make_adapter()
        conv_id = "19:group@thread.v2"
        adapter._last_message_ids[conv_id] = "0"
        adapter._group_config = MagicMock(return_value={
            "require_mention": False,
            "short_message_ignore": short_message_ignore,
        })
        message = {
            "id": "1",
            "messagetype": "Text",
            "content": text,
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Test User",
            "from": "8:orgid:test-user",
        }

        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
            await adapter._process_new_messages(conv_id, [message])

        assert handle.await_count == int(should_dispatch)
        assert adapter._last_message_ids[conv_id] == "1"


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
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "health_sequence, expected_intervals",
        [
            ([True] * 5, [2, 2, 2, 2, 15]),
            ([True] * 20, [2, 2, 2, 2] + [15] * 15 + [30]),
            ([True] * 5 + [False], [2, 2, 2, 2, 15, 2]),
        ],
    )
    async def test_poll_loop_adapts_to_websocket_health(
        self,
        health_sequence,
        expected_intervals,
    ):
        """Drive the real loop and assert its observable sleep cadence."""
        adapter = _make_adapter()
        adapter._conv_ids = []
        adapter._poll_interval = 2
        adapter._running = True
        adapter._ws_listener = MagicMock()
        adapter._ws_listener.is_healthy.side_effect = health_sequence
        intervals = []

        async def record_sleep(interval):
            intervals.append(interval)
            if len(intervals) == len(health_sequence):
                adapter._running = False

        with patch(
            "gateway.platforms.teams_mtk.asyncio.sleep",
            side_effect=record_sleep,
        ):
            await adapter._poll_loop()

        assert intervals == expected_intervals


# ── Model picker authorization ─────────────────────────────────────────

class TestModelPickerAuthorization:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sender_id, should_select",
        [("picker-owner", True), ("other-member", False)],
    )
    async def test_group_picker_accepts_only_the_authorized_user(
        self,
        sender_id,
        should_select,
    ):
        adapter = _make_adapter()
        conv_id = "19:group@thread.v2"
        adapter._last_message_ids[conv_id] = "0"
        adapter._group_config = MagicMock(return_value={"require_mention": True})
        adapter._model_picker_states[conv_id] = {
            "step": "provider",
            "prov_entries": [("openai", "OpenAI", 1, True)],
            "allowed_user_id": "picker-owner",
        }
        adapter._send_model_sub_picker = AsyncMock()
        adapter.handle_message = AsyncMock()
        message = {
            "id": "1",
            "messagetype": "Text",
            "content": "@hermes 1",
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Member",
            "from": f"8:orgid:{sender_id}",
        }

        await adapter._process_new_messages(conv_id, [message])

        assert adapter._send_model_sub_picker.await_count == int(should_select)
        assert adapter.handle_message.await_count == int(not should_select)


# ── Poll/WS cursor serialization ───────────────────────────────────────

class TestMessageCursorSerialization:
    @staticmethod
    def _message(message_id, content):
        return {
            "id": message_id,
            "messagetype": "Text",
            "content": content,
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Member",
            "from": "8:orgid:member",
        }

    @pytest.mark.asyncio
    async def test_numeric_ids_are_processed_oldest_first_without_cursor_regression(self):
        adapter = _make_adapter()
        adapter._last_message_ids["conv1"] = "8"
        received = []

        async def capture(event):
            received.append(event.text)

        adapter.handle_message = AsyncMock(side_effect=capture)
        messages = [
            self._message("10", "ten"),
            self._message("9", "nine"),
        ]

        await adapter._process_new_messages("conv1", messages)
        await adapter._process_new_messages("conv1", messages)

        assert received == ["nine", "ten"]
        assert adapter._last_message_ids["conv1"] == "10"

    @pytest.mark.asyncio
    async def test_concurrent_ws_and_poll_fetches_dispatch_once(self):
        adapter = _make_adapter()
        adapter._last_message_ids["conv1"] = "8"
        entered = asyncio.Event()
        release = asyncio.Event()

        async def block_first_dispatch(event):
            entered.set()
            await release.wait()

        adapter.handle_message = AsyncMock(side_effect=block_first_dispatch)
        message = [self._message("9", "once")]

        first = asyncio.create_task(adapter._process_new_messages("conv1", message))
        await entered.wait()
        second = asyncio.create_task(adapter._process_new_messages("conv1", message))
        release.set()
        await asyncio.gather(first, second)

        adapter.handle_message.assert_awaited_once()
        assert adapter._last_message_ids["conv1"] == "9"


# ── Delete-only-own guard ──────────────────────────────────────────────

class TestDeleteOnlyOwnGuard:
    @pytest.mark.asyncio
    async def test_delete_owned_message_for_same_chat(self):
        adapter = _make_adapter()
        adapter._remember_sent_message("conv1", "m1")
        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "deleted"}
            result = await adapter.delete_message_safe("conv1", "m1")
            mock.assert_called_once()
            assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_same_message_id_in_other_chat_is_not_owned(self):
        adapter = _make_adapter()
        adapter._remember_sent_message("conv1", "m1")
        adapter._fetch_messages = MagicMock(return_value=[
            {"id": "m1", "properties": {"hermes_sender": "user"}}
        ])
        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as mock:
            result = await adapter.delete_message_safe("conv2", "m1")
        mock.assert_not_awaited()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_reject_other_user_message(self):
        adapter = _make_adapter()
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
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
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
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter"):
            adapter._auth.skype_token = MagicMock(return_value="tok")
            mock_svc = MagicMock()
            mock_svc.forward.return_value = {"status": "forwarded"}
            MockSvc.return_value = mock_svc
            result = await adapter.forward_message("src", "m1", "any_target")
            assert result["status"] == "forwarded"


# ── Echo guard across normalized/manual send paths ─────────────────────

class TestEchoGuardIntegration:
    @pytest.mark.asyncio
    async def test_tracked_sdk_message_skips_after_html_normalization(self):
        """A real outbound ID remains authoritative after SDK normalization."""
        adapter = _make_adapter()
        conv_id = "19:dm@unq.gbl.spaces"
        adapter._last_message_ids[conv_id] = "0"
        adapter._remember_sent_message(conv_id, "1")
        message = {
            "id": "1",
            "messagetype": "RichText/Html",
            "content": "⚙️ Select ProviderCurrent: gpt-5.6-sol",
            "_raw_content": (
                '<div style="border-left:3px solid #6264A7">'
                '<div>⚙️ Select Provider</div></div>'
            ),
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Unknown",
            "from": "8:orgid:self",
        }

        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
            await adapter._process_new_messages(conv_id, [message])

        handle.assert_not_awaited()
        assert adapter._last_message_ids[conv_id] == "1"

    @pytest.mark.asyncio
    async def test_foreign_hermes_html_quote_is_dispatched(self):
        """Presentation HTML alone must never prove outbound ownership."""
        adapter = _make_adapter()
        conv_id = "48:notes"
        adapter._last_message_ids[conv_id] = "0"
        message = {
            "id": "1",
            "messagetype": "RichText/Html",
            "content": "Please explain this quoted answer",
            "_raw_content": (
                '<blockquote><div style="border-left:3px solid #6264A7">'
                "<b>🤖 Hermes</b> quoted text</div></blockquote>"
            ),
            "properties": {},
            "_raw_properties": {},
            "imdisplayname": "Foreign User",
            "from": "8:orgid:foreign-user",
        }

        with patch.object(adapter, "handle_message", new_callable=AsyncMock) as handle:
            await adapter._process_new_messages(conv_id, [message])

        handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_foreign_inbound_does_not_gain_delete_ownership(self):
        """Processing inbound traffic must not mutate outbound ownership."""
        adapter = _make_adapter()
        conv_id = "48:notes"
        adapter._last_message_ids[conv_id] = "0"
        message = {
            "id": "foreign-1",
            "messagetype": "Text",
            "content": "foreign input",
            "properties": {"hermes_sender": "user"},
            "_raw_properties": {},
            "imdisplayname": "Foreign User",
            "from": "8:orgid:foreign-user",
        }
        with patch.object(adapter, "handle_message", new_callable=AsyncMock):
            await adapter._process_new_messages(conv_id, [message])
        adapter._fetch_messages = MagicMock(return_value=[message])

        with patch.object(adapter, "delete_message", new_callable=AsyncMock) as delete:
            result = await adapter.delete_message_safe(conv_id, "foreign-1")

        delete.assert_not_awaited()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_model_picker_uses_sdk_send_when_available(self):
        """The picker must use the same trusted SDK transport as normal sends."""
        from gateway.platforms.helpers import MessageDeduplicator

        adapter = TeamsMTKAdapter(config=None)
        adapter._sent_dedup = MessageDeduplicator()
        adapter._call_sdk_messages = MagicMock(
            return_value={"id": "picker-id"}
        )

        with (
            patch.object(teams_mtk_module, "_SDK_AVAILABLE", True),
            patch(
                "requests.Session",
                side_effect=AssertionError("picker bypassed SDK transport"),
            ),
        ):
            result = await adapter.send_model_picker(
                chat_id="19:dm@unq.gbl.spaces",
                providers=[{
                    "slug": "openai-codex",
                    "name": "OpenAI Codex",
                    "models": ["gpt-5.6-sol"],
                    "is_current": True,
                }],
                current_model="gpt-5.6-sol",
                current_provider="openai-codex",
                session_key="session",
                on_model_selected=AsyncMock(),
            )

        assert result.success is True
        assert result.message_id == "picker-id"
        adapter._call_sdk_messages.assert_called_once()
        operation = adapter._call_sdk_messages.call_args.args[0]
        kwargs = adapter._call_sdk_messages.call_args.kwargs
        assert operation == "send"
        assert kwargs["conversation_id"] == "19:dm@unq.gbl.spaces"
        assert kwargs["is_html"] is True
        assert kwargs["return_context"] is False
        assert "Select Provider" in kwargs["content"]
        assert adapter._model_picker_states["19:dm@unq.gbl.spaces"]["step"] == "provider"

    @pytest.mark.asyncio
    async def test_model_sub_picker_uses_sdk_send_when_available(self):
        """The second picker step must not fall back to a bare requests session."""
        adapter = TeamsMTKAdapter(config=None)
        adapter._call_sdk_messages = MagicMock(
            return_value={"id": "sub-picker-id"}
        )
        chat_id = "19:dm@unq.gbl.spaces"
        adapter._model_picker_states[chat_id] = {
            "step": "provider",
            "prov_entries": [("openai-codex", "OpenAI Codex", 1, True)],
            "prov_objects": [{
                "slug": "openai-codex",
                "name": "OpenAI Codex",
                "models": ["gpt-5.6-sol"],
                "is_current": True,
            }],
            "on_model_selected": AsyncMock(),
            "current_model": "gpt-5.6-sol",
            "current_provider": "openai-codex",
            "allowed_user_id": "picker-owner",
        }

        with (
            patch.object(teams_mtk_module, "_SDK_AVAILABLE", True),
            patch(
                "requests.Session",
                side_effect=AssertionError("sub-picker bypassed SDK transport"),
            ),
        ):
            await adapter._send_model_sub_picker(chat_id, 1)

        adapter._call_sdk_messages.assert_called_once()
        operation = adapter._call_sdk_messages.call_args.args[0]
        kwargs = adapter._call_sdk_messages.call_args.kwargs
        assert operation == "send"
        assert kwargs["conversation_id"] == chat_id
        assert kwargs["is_html"] is True
        assert kwargs["return_context"] is False
        assert "Select Model" in kwargs["content"]
        assert adapter._model_picker_states[chat_id]["step"] == "model"

    @pytest.mark.asyncio
    async def test_model_picker_id_stays_guarded_after_another_chat_send(self):
        """A picker ID must be in the TTL cache, not only the global last-ID slot."""
        from gateway.platforms.helpers import MessageDeduplicator

        adapter = TeamsMTKAdapter(config=None)
        adapter._sent_dedup = MessageDeduplicator()
        adapter._auth._inject_truststore = MagicMock()
        adapter._auth.skype_token = MagicMock(return_value="token")
        adapter._auth._msg_base = "https://example.invalid/v1/users/ME"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"OriginalArrivalTime": "picker-id"}
        session = MagicMock()
        session.post.return_value = response

        with (
            patch.object(teams_mtk_module, "_SDK_AVAILABLE", False),
            patch("requests.Session", return_value=session),
        ):
            result = await adapter.send_model_picker(
                chat_id="19:dm@unq.gbl.spaces",
                providers=[{
                    "slug": "openai-codex",
                    "name": "OpenAI Codex",
                    "models": ["gpt-5.6-sol"],
                    "is_current": True,
                }],
                current_model="gpt-5.6-sol",
                current_provider="openai-codex",
                session_key="session",
                on_model_selected=AsyncMock(),
            )

        assert result.message_id == "picker-id"
        adapter._last_sent_message_id = "other-chat-message-id"
        assert adapter._is_sent_message("19:dm@unq.gbl.spaces", "picker-id") is True


# ── G13-B.3 unblocked (Skype API) / G14-2.1 still blocked (P7) ─────────

class TestBlockedStubs:
    @pytest.mark.asyncio
    async def test_create_chat_empty_members_errors(self):
        """G13-B.3 no longer stubs Chat.Create; unresolvable members yield an error."""
        adapter = _make_adapter()
        result = await adapter.create_chat("Test Topic", [])
        assert result["status"] == "error"
        assert "No members resolved" in result["error"] or "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_leave_chat_no_msg_base_errors(self):
        """leave_chat gracefully errors when host/msg_base is unavailable."""
        adapter = _make_adapter()
        # _make_adapter's auth has no msg_base configured → host resolution fails
        result = await adapter.leave_chat("19:fake@thread.v2")
        assert result["status"] == "error"

    def test_get_persona_config_stub(self):
        adapter = _make_adapter()
        result = adapter.get_persona_config()
        assert result["status"] == "stub"
        assert "P7" in result["error"]
        assert result["persona"] is None
