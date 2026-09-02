"""Contract tests for native Microsoft Loop support in TeamsMTK."""

from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest

import gateway.platforms.teams_mtk as teams_mtk


def test_loop_sdk_http_rewrites_default_msg_origin_to_live_region(monkeypatch):
    seen = {}

    def fake_request(_self, method, url, **kwargs):
        seen.update(method=method, url=url, kwargs=kwargs)
        return {"ok": True}

    monkeypatch.setattr(teams_mtk._SDKBaseHTTPLayer, "_request", fake_request)
    auth = SimpleNamespace(
        _gw=SimpleNamespace(
            msg_base="https://apac.ng.msg.teams.microsoft.com/v1/users/ME"
        ),
        get_skype_token=lambda: "token",
    )
    layer = teams_mtk._SDKHTTPLayer(auth, verify_ssl=True)
    try:
        result = layer._request(
            "POST",
            "https://amer.ng.msg.teams.microsoft.com/v1/users/ME/conversations/conv/messages",
            json={"content": "loop"},
        )
    finally:
        layer._session.close()

    assert result == {"ok": True}
    assert seen["url"] == (
        "https://apac.ng.msg.teams.microsoft.com/v1/users/ME/"
        "conversations/conv/messages"
    )


@pytest.fixture
def adapter():
    value = teams_mtk.TeamsMTKAdapter.__new__(teams_mtk.TeamsMTKAdapter)
    value._auth = MagicMock()
    value._remember_sent_message = MagicMock()
    return value


def test_sdk_auth_adapter_exposes_regional_msg_base_and_scope_exchange():
    gateway_auth = MagicMock()
    gateway_auth.msg_base = "https://emea.ng.msg.teams.microsoft.com/v1"
    token_result = {"access_token": "site-token", "expires_in": 3600}
    gateway_auth.exchange_for_scope.return_value = token_result

    sdk_auth = teams_mtk._SDKAuthAdapter(gateway_auth)

    assert sdk_auth.msg_base == gateway_auth.msg_base
    assert sdk_auth.exchange_for_scope("https://tenant.sharepoint.com/.default") == token_result
    gateway_auth.exchange_for_scope.assert_called_once_with(
        "https://tenant.sharepoint.com/.default"
    )
    sdk_auth._force_refresh()
    gateway_auth._force_refresh.assert_called_once_with()


@pytest.mark.asyncio
async def test_send_loop_component_uses_sdk_and_remembers_message(adapter):
    adapter._call_sdk_loop = MagicMock(
        return_value={
            "id": "1787195338017",
            "status": "sent",
            "component_url": "https://tenant.sharepoint.com/demo.loop",
        }
    )

    result = await adapter.send_loop_component(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/demo.loop",
    )

    adapter._call_sdk_loop.assert_called_once_with(
        "send_existing",
        conversation_id="19:test@thread.v2",
        component_url="https://tenant.sharepoint.com/demo.loop",
    )
    adapter._remember_sent_message.assert_called_once_with(
        "19:test@thread.v2", "1787195338017"
    )
    assert result["status"] == "ok"
    assert result["message"]["id"] == "1787195338017"


@pytest.mark.asyncio
async def test_create_loop_table_authors_then_sends_verified_component(adapter):
    adapter._create_loop_table_sync = MagicMock(
        return_value={
            "component": {
                "component_url": "https://tenant.sharepoint.com/new.loop",
                "item_id": "item-new",
                "verification": {
                    "rows": 2,
                    "columns": 2,
                    "content_match": True,
                },
            },
            "message": {"id": "1787195338018", "status": "sent"},
        }
    )

    result = await adapter.create_loop_table(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/template.loop",
        "Tracker.loop",
        ["A", "B"],
        [["1", "2"], ["3", "4"]],
        locale="zh-TW",
    )

    adapter._create_loop_table_sync.assert_called_once_with(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/template.loop",
        "Tracker.loop",
        ["A", "B"],
        [["1", "2"], ["3", "4"]],
        scope="organization",
        locale="zh-TW",
    )
    adapter._remember_sent_message.assert_called_once_with(
        "19:test@thread.v2", "1787195338018"
    )
    assert result["status"] == "ok"
    assert result["component"]["verification"]["content_match"] is True


@pytest.mark.asyncio
async def test_create_loop_table_reports_failure_without_second_send(adapter):
    adapter._create_loop_table_sync = MagicMock(
        side_effect=RuntimeError("ODSP readback verification failed")
    )

    result = await adapter.create_loop_table(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/template.loop",
        "Tracker.loop",
        ["A"],
        [["1"]],
    )

    assert result["status"] == "error"
    assert result["stage"] == "create_loop_table"
    assert "readback verification failed" in result["error"]
    adapter._create_loop_table_sync.assert_called_once()
    adapter._remember_sent_message.assert_not_called()


@pytest.mark.asyncio
async def test_create_loop_table_rejects_anonymous_scope_before_side_effect(adapter):
    adapter._create_loop_table_sync = MagicMock(return_value={})

    result = await adapter.create_loop_table(
        chat_id="19:test@thread.v2",
        template_url="https://tenant.sharepoint.com/:fl:/g/example",
        name="Unsafe",
        headers=["A"],
        rows=[["1"]],
        scope="anonymous",
    )

    assert result == {
        "status": "error",
        "stage": "validation",
        "error": "Loop scope must be 'organization' or 'users'",
    }
    adapter._create_loop_table_sync.assert_not_called()
    adapter._remember_sent_message.assert_not_called()


def test_create_loop_table_sync_preserves_component_when_card_send_fails(
    adapter, monkeypatch
):
    component = {
        "component_url": "https://tenant.sharepoint.com/:fl:/g/component",
        "item_id": "created-item",
        "content_match": True,
    }

    class Session:
        def close(self):
            return None

    class Graph:
        _session = Session()

    monkeypatch.setattr(teams_mtk, "_SDKGraphToken", lambda _auth: "graph-token")
    monkeypatch.setattr(
        teams_mtk,
        "_SDKGraph",
        lambda _token, verify_ssl: Graph(),
    )
    monkeypatch.setattr(
        teams_mtk,
        "_sdk_create_table_loop_component",
        lambda *_args, **_kwargs: component,
    )
    adapter._call_sdk_loop = MagicMock(side_effect=ConnectionError("send failed"))

    result = adapter._create_loop_table_sync(
        "19:test@thread.v2",
        "https://tenant.sharepoint.com/:fl:/g/template",
        "Roadmap.loop",
        ["Owner", "Status"],
        [["Alice", "Open"]],
    )

    assert result["status"] == "error"
    assert result["stage"] == "send_loop_component"
    assert result["component"] == component
    assert "send failed" in result["error"]
    adapter._call_sdk_loop.assert_called_once_with(
        "send_existing",
        conversation_id="19:test@thread.v2",
        component_url=component["component_url"],
    )


def test_platform_hints_advertise_loop_authoring(adapter):
    adapter._vip_config = {}

    hints = adapter.get_platform_hints()

    assert "create_loop_table" in hints
    assert "send_loop_component" in hints
