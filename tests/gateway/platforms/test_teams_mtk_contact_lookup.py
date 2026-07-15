"""Unit tests for TeamsMTKAdapter G13-A: read-only contact lookup.

Covers teams-mtk-hermes-native-parity change, G13-A (Phase A — read-only,
no new OAuth scope, no separate authorization gate by construction):
- list_conversations(): parses the Skype chatSvc /conversations response
- _find_conv_by_display_name(): case-insensitive match against title/members
- send_message_tool routing for "teams_mtk:contact:<name>" targets

See openspec/changes/teams-mtk-hermes-native-parity/design.md "G13".
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from gateway.platforms.teams_mtk import TeamsMTKAdapter


def _make_adapter():
    """Build a TeamsMTKAdapter without touching the real Teams token cache."""
    return TeamsMTKAdapter(config=None)


def _fake_conversations_response(convs):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"conversations": convs}
    return resp


# ── list_conversations ──────────────────────────────────────────────────

def test_list_conversations_parses_title_and_type():
    adapter = _make_adapter()
    fake_resp = _fake_conversations_response([
        {
            "id": "19:abc@thread.v2",
            "threadProperties": {"topic": "Project Alpha", "threadType": "group"},
            "members": [],
        }
    ])
    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("gateway.platforms.teams_mtk._TeamsAuth.skype_token", return_value="tok"), \
         patch("gateway.platforms.teams_mtk._TeamsAuth._inject_truststore"), \
         patch.object(type(adapter._auth), "msg_base", "https://msg.example/v1/users/ME", create=True), \
         patch("requests.Session.get", return_value=fake_resp):
        convs = adapter.list_conversations(limit=50)

    assert len(convs) == 1
    assert convs[0]["id"] == "19:abc@thread.v2"
    assert convs[0]["title"] == "Project Alpha"
    assert convs[0]["type"] == "group"


def test_list_conversations_falls_back_to_member_display_names():
    adapter = _make_adapter()
    fake_resp = _fake_conversations_response([
        {
            "id": "8:orgid:xyz",
            "threadProperties": {},  # no memberDisplayNames, no topic
            "members": [
                {"imdisplayname": "Example User"},
                {"friendlyName": "Sample User"},
            ],
        }
    ])
    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("gateway.platforms.teams_mtk._TeamsAuth.skype_token", return_value="tok"), \
         patch("gateway.platforms.teams_mtk._TeamsAuth._inject_truststore"), \
         patch.object(type(adapter._auth), "msg_base", "https://msg.example/v1/users/ME", create=True), \
         patch("requests.Session.get", return_value=fake_resp):
        convs = adapter.list_conversations(limit=50)

    assert convs[0]["title"] == ""
    assert "Example User" in convs[0]["member_names"]
    assert "Sample User" in convs[0]["member_names"]


def test_list_conversations_respects_limit():
    adapter = _make_adapter()
    fake_resp = _fake_conversations_response([
        {"id": f"conv{i}", "threadProperties": {"topic": f"T{i}"}, "members": []}
        for i in range(10)
    ])
    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("gateway.platforms.teams_mtk._TeamsAuth.skype_token", return_value="tok"), \
         patch("gateway.platforms.teams_mtk._TeamsAuth._inject_truststore"), \
         patch.object(type(adapter._auth), "msg_base", "https://msg.example/v1/users/ME", create=True), \
         patch("requests.Session.get", return_value=fake_resp):
        convs = adapter.list_conversations(limit=3)

    assert len(convs) == 3


def test_list_conversations_returns_empty_on_error():
    adapter = _make_adapter()
    with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False), \
         patch("gateway.platforms.teams_mtk._TeamsAuth.skype_token", side_effect=RuntimeError("boom")), \
         patch("gateway.platforms.teams_mtk._TeamsAuth._inject_truststore"):
        convs = adapter.list_conversations(limit=50)

    assert convs == []


# ── _find_conv_by_display_name ──────────────────────────────────────────

def test_find_conv_by_display_name_matches_title():
    adapter = _make_adapter()
    with patch.object(adapter, "list_conversations", return_value=[
        {"id": "conv1", "title": "Project Alpha", "member_names": ""},
        {"id": "conv2", "title": "Random Group", "member_names": ""},
    ]):
        result = adapter._find_conv_by_display_name("alpha")

    assert result == "conv1"


def test_find_conv_by_display_name_matches_member_names_case_insensitive():
    adapter = _make_adapter()
    with patch.object(adapter, "list_conversations", return_value=[
        {"id": "conv1", "title": "", "member_names": "Example User, Sample User"},
    ]):
        result = adapter._find_conv_by_display_name("EXAMPLE")

    assert result == "conv1"


def test_find_conv_by_display_name_returns_none_when_not_found():
    """A target outside existing conversations resolves to None — this is
    the whitelist-safety property G13 relies on (no separate gate needed
    because unknown contacts are simply unreachable via this path)."""
    adapter = _make_adapter()
    with patch.object(adapter, "list_conversations", return_value=[
        {"id": "conv1", "title": "Project Alpha", "member_names": ""},
    ]):
        result = adapter._find_conv_by_display_name("Someone Not In Any Chat")

    assert result is None


def test_find_conv_by_display_name_empty_name_returns_none():
    adapter = _make_adapter()
    with patch.object(adapter, "list_conversations", return_value=[]) as mocked:
        result = adapter._find_conv_by_display_name("   ")

    assert result is None
    # Should short-circuit before even calling list_conversations.
    mocked.assert_not_called()


# ── send_message_tool routing ───────────────────────────────────────────

def test_send_message_contact_target_resolves_and_routes(monkeypatch):
    from tools import send_message_tool

    fake_adapter = MagicMock()
    fake_adapter._find_conv_by_display_name.return_value = "19:resolved@thread.v2"

    def _get_adapter(platform):
        from gateway.config import Platform
        if platform == Platform.TEAMS_MTK:
            return fake_adapter
        return None

    fake_adapters = MagicMock()
    fake_adapters.get.side_effect = _get_adapter
    fake_runner = MagicMock()
    fake_runner.adapters = fake_adapters

    with patch("gateway.run._gateway_runner_ref", return_value=fake_runner), \
         patch("gateway.config.load_gateway_config") as mock_load_cfg, \
         patch("tools.send_message_tool._send_via_adapter") as mock_send:
        from gateway.config import Platform, PlatformConfig

        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TEAMS_MTK: PlatformConfig(enabled=True)}
        mock_load_cfg.return_value = mock_cfg

        async def _fake_send(*args, **kwargs):
            return {"success": True, "message_id": "1"}
        mock_send.side_effect = _fake_send

        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Example User", "message": "hi"}
        )

    fake_adapter._find_conv_by_display_name.assert_called_once_with("Example User")
    parsed = json.loads(result)
    assert parsed.get("success") is True


def test_send_message_contact_target_not_found_returns_error():
    from tools import send_message_tool

    fake_adapter = MagicMock()
    fake_adapter._find_conv_by_display_name.return_value = None

    def _get_adapter(platform):
        from gateway.config import Platform
        if platform == Platform.TEAMS_MTK:
            return fake_adapter
        return None

    fake_adapters = MagicMock()
    fake_adapters.get.side_effect = _get_adapter
    fake_runner = MagicMock()
    fake_runner.adapters = fake_adapters

    with patch("gateway.run._gateway_runner_ref", return_value=fake_runner):
        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Nobody Here", "message": "hi"}
        )

    parsed = json.loads(result)
    assert "error" in parsed
    assert "Nobody Here" in parsed["error"]


def test_send_message_contact_target_requires_name():
    from tools import send_message_tool

    result = send_message_tool.send_message_tool(
        {"action": "send", "target": "teams_mtk:contact:", "message": "hi"}
    )
    parsed = json.loads(result)
    assert "error" in parsed


def test_send_message_contact_target_no_live_gateway_returns_error():
    from tools import send_message_tool

    with patch("gateway.run._gateway_runner_ref", return_value=None):
        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Example User", "message": "hi"}
        )
    parsed = json.loads(result)
    assert "error" in parsed
    assert "live gateway" in parsed["error"]


# ── G13-B.2/B.3: people.py fallback + directory-enriched error ─────────

def test_send_message_contact_fallback_calls_people_and_enriches_error(monkeypatch):
    """When display-name match fails, people.py is consulted; if found in
    directory the error message includes the canonical name."""
    from tools import send_message_tool

    fake_adapter = MagicMock()
    fake_adapter._find_conv_by_display_name.return_value = None

    def _get_adapter(platform):
        from gateway.config import Platform
        if platform == Platform.TEAMS_MTK:
            return fake_adapter
        return None

    fake_adapters = MagicMock()
    fake_adapters.get.side_effect = _get_adapter
    fake_runner = MagicMock()
    fake_runner.adapters = fake_adapters

    _people_json = json.dumps({
        "people": [{"id": "oid-123", "displayName": "Sample User (測試使用者)"}]
    })

    with patch("gateway.run._gateway_runner_ref", return_value=fake_runner), \
         patch("subprocess.run") as mock_sub, \
         patch("os.path.expanduser", return_value="/home/u/.hermes/skills/m365/scripts/people.py"):
        mock_sub.return_value = MagicMock(returncode=0, stdout=_people_json, stderr="")
        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Sample", "message": "hi"}
        )

    parsed = json.loads(result)
    assert "error" in parsed
    # Directory name should appear in the enriched error
    assert "Sample User" in parsed["error"] or "測試使用者" in parsed["error"]


def test_send_message_contact_fallback_people_failure_still_errors(monkeypatch):
    """If people.py subprocess fails, the normal error is returned."""
    from tools import send_message_tool

    fake_adapter = MagicMock()
    fake_adapter._find_conv_by_display_name.return_value = None

    def _get_adapter(platform):
        from gateway.config import Platform
        if platform == Platform.TEAMS_MTK:
            return fake_adapter
        return None

    fake_adapters = MagicMock()
    fake_adapters.get.side_effect = _get_adapter
    fake_runner = MagicMock()
    fake_runner.adapters = fake_adapters

    with patch("gateway.run._gateway_runner_ref", return_value=fake_runner), \
         patch("subprocess.run", side_effect=RuntimeError("boom")):
        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Unknown", "message": "hi"}
        )

    parsed = json.loads(result)
    assert "error" in parsed
    assert "Unknown" in parsed["error"]


def test_send_message_contact_found_directly_skips_people():
    """When display-name match succeeds, people.py is NOT called."""
    from tools import send_message_tool

    fake_adapter = MagicMock()
    fake_adapter._find_conv_by_display_name.return_value = "19:found@unq.gbl.spaces"

    def _get_adapter(platform):
        from gateway.config import Platform
        if platform == Platform.TEAMS_MTK:
            return fake_adapter
        return None

    fake_adapters = MagicMock()
    fake_adapters.get.side_effect = _get_adapter
    fake_runner = MagicMock()
    fake_runner.adapters = fake_adapters

    with patch("gateway.run._gateway_runner_ref", return_value=fake_runner), \
         patch("gateway.config.load_gateway_config") as mock_load_cfg, \
         patch("tools.send_message_tool._send_via_adapter") as mock_send, \
         patch("subprocess.run") as mock_sub:
        from gateway.config import Platform, PlatformConfig

        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TEAMS_MTK: PlatformConfig(enabled=True)}
        mock_load_cfg.return_value = mock_cfg

        async def _fake_send(*args, **kwargs):
            return {"success": True, "message_id": "1"}
        mock_send.side_effect = _fake_send

        result = send_message_tool.send_message_tool(
            {"action": "send", "target": "teams_mtk:contact:Example User", "message": "hi"}
        )

    mock_sub.assert_not_called()
    parsed = json.loads(result)
    assert parsed.get("success") is True
