"""Tests for the send_message native Teams Loop action."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gateway.config import Platform
from tools import send_message_tool


def _install_live_adapter(monkeypatch, adapter):
    runner = SimpleNamespace(adapters={Platform.TEAMS_MTK: adapter})
    monkeypatch.setattr("gateway.run._gateway_runner_ref", lambda: runner)


def test_schema_exposes_loop_action_and_inputs():
    props = send_message_tool.SEND_MESSAGE_SCHEMA["parameters"]["properties"]

    assert "loop" in props["action"]["enum"]
    for field in ("component_url", "template_url", "name", "headers", "rows"):
        assert field in props


def test_loop_action_sends_existing_component(monkeypatch):
    adapter = SimpleNamespace(
        send_loop_component=AsyncMock(
            return_value={"status": "ok", "message": {"id": "1787195338017"}}
        )
    )
    _install_live_adapter(monkeypatch, adapter)

    result = json.loads(
        send_message_tool.send_message_tool(
            {
                "action": "loop",
                "target": "teams_mtk:19:test@thread.v2",
                "component_url": "https://tenant.sharepoint.com/demo.loop",
            }
        )
    )

    assert result["status"] == "ok"
    adapter.send_loop_component.assert_awaited_once_with(
        chat_id="19:test@thread.v2",
        component_url="https://tenant.sharepoint.com/demo.loop",
    )


def test_loop_action_creates_table_component(monkeypatch):
    adapter = SimpleNamespace(
        create_loop_table=AsyncMock(
            return_value={
                "status": "ok",
                "component": {
                    "item_id": "item-new",
                    "verification": {"content_match": True},
                },
                "message": {"id": "1787195338018"},
            }
        )
    )
    _install_live_adapter(monkeypatch, adapter)

    result = json.loads(
        send_message_tool.send_message_tool(
            {
                "action": "loop",
                "target": "teams_mtk:19:test@thread.v2",
                "template_url": "https://tenant.sharepoint.com/template.loop",
                "name": "Tracker.loop",
                "headers": ["A", "B"],
                "rows": [["1", "2"]],
                "scope": "users",
                "locale": "zh-TW",
            }
        )
    )

    assert result["status"] == "ok"
    adapter.create_loop_table.assert_awaited_once_with(
        chat_id="19:test@thread.v2",
        template_url="https://tenant.sharepoint.com/template.loop",
        name="Tracker.loop",
        headers=["A", "B"],
        rows=[["1", "2"]],
        scope="users",
        locale="zh-TW",
    )


def test_loop_action_rejects_non_teams_target_before_lookup():
    result = json.loads(
        send_message_tool.send_message_tool(
            {
                "action": "loop",
                "target": "telegram:123",
                "component_url": "https://tenant.sharepoint.com/demo.loop",
            }
        )
    )

    assert "only supported for teams_mtk" in result["error"]


def test_loop_action_honors_interrupt_before_external_side_effect(monkeypatch):
    adapter = SimpleNamespace(send_loop_component=AsyncMock())
    _install_live_adapter(monkeypatch, adapter)
    monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: True)

    result = json.loads(
        send_message_tool.send_message_tool(
            {
                "action": "loop",
                "target": "teams_mtk:19:test@thread.v2",
                "component_url": "https://tenant.sharepoint.com/demo.loop",
            }
        )
    )

    assert "Interrupted" in result["error"]
    adapter.send_loop_component.assert_not_awaited()


def test_loop_action_requires_complete_rectangular_table_input(monkeypatch):
    adapter = SimpleNamespace(create_loop_table=AsyncMock())
    _install_live_adapter(monkeypatch, adapter)

    result = json.loads(
        send_message_tool.send_message_tool(
            {
                "action": "loop",
                "target": "teams_mtk:19:test@thread.v2",
                "template_url": "https://tenant.sharepoint.com/template.loop",
                "name": "Tracker.loop",
                "headers": ["A", "B"],
                "rows": [["1"]],
            }
        )
    )

    assert "same number of columns" in result["error"]
    adapter.create_loop_table.assert_not_awaited()
