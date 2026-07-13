"""S2-3: Tests for gateway search_messages delegation and S1-3 _fetch_messages_by_date."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter():
    """Create a TeamsMTKAdapter with mocked auth."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    adapter = TeamsMTKAdapter.__new__(TeamsMTKAdapter)
    adapter._auth = MagicMock()
    adapter._auth.msg_base = "https://amer.ng.msg.teams.microsoft.com/v1/users/ME"
    adapter._auth._inject_truststore = MagicMock()
    return adapter


# ---------------------------------------------------------------------------
# S1-3: _fetch_messages_by_date
# ---------------------------------------------------------------------------

class TestFetchMessagesByDate:
    """_fetch_messages_by_date delegates to SDK get_by_date and normalises output."""

    def test_raises_when_sdk_unavailable(self):
        adapter = _make_adapter()
        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="teams_skype_sdk"):
                adapter._fetch_messages_by_date("conv1", date_from="2026-07-01")

    def test_returns_oldest_first(self):
        adapter = _make_adapter()
        sdk_msgs = [
            {"id": "200", "sender": "B", "content": "newer", "type": "Text",
             "timestamp": "2026-07-02 10:00:00", "_raw_properties": {}},
            {"id": "100", "sender": "A", "content": "older", "type": "Text",
             "timestamp": "2026-07-01 10:00:00", "_raw_properties": {}},
        ]
        mock_svc = MagicMock()
        mock_svc.get_by_date.return_value = sdk_msgs

        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKMessages", return_value=mock_svc):
            result = adapter._fetch_messages_by_date("conv1", date_from="2026-07-01", date_to="2026-07-02")

        # SDK returns newest-first; _fetch_messages_by_date reverses to oldest-first
        assert len(result) == 2
        assert result[0]["id"] == "100"
        assert result[1]["id"] == "200"

    def test_passes_date_params_to_sdk(self):
        adapter = _make_adapter()
        mock_svc = MagicMock()
        mock_svc.get_by_date.return_value = []

        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKMessages", return_value=mock_svc):
            adapter._fetch_messages_by_date("conv1", date_from="2026-07-01", date_to="2026-07-31", limit=50)

        mock_svc.get_by_date.assert_called_once_with(
            "conv1", date_from="2026-07-01", date_to="2026-07-31", limit=50
        )

    def test_backfills_imdisplayname(self):
        adapter = _make_adapter()
        sdk_msgs = [{"id": "1", "sender": "Alice", "content": "hi",
                     "type": "Text", "timestamp": "2026-07-01 09:00:00", "_raw_properties": {}}]
        mock_svc = MagicMock()
        mock_svc.get_by_date.return_value = sdk_msgs

        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKMessages", return_value=mock_svc):
            result = adapter._fetch_messages_by_date("conv1")

        assert result[0]["imdisplayname"] == "Alice"


# ---------------------------------------------------------------------------
# S1-1/S1-2: _fetch_messages limit=None vs limit=N
# ---------------------------------------------------------------------------

class TestFetchMessagesLimitBehaviour:
    """_fetch_messages routes to get() (full) or get_page() (bounded) based on limit."""

    def test_limit_none_uses_get(self):
        adapter = _make_adapter()
        mock_svc = MagicMock()
        mock_svc.get.return_value = []

        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKMessages", return_value=mock_svc):
            adapter._conv_id = "conv1"
            adapter._fetch_messages("conv1", limit=None)

        mock_svc.get.assert_called_once_with("conv1")
        mock_svc.get_page.assert_not_called()

    def test_limit_int_uses_get_page(self):
        adapter = _make_adapter()
        mock_svc = MagicMock()
        mock_svc.get_page.return_value = []

        with patch("gateway.platforms.teams_mtk._SDK_AVAILABLE", True), \
             patch("gateway.platforms.teams_mtk._SDKAuthAdapter", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKHTTPLayer", return_value=MagicMock()), \
             patch("gateway.platforms.teams_mtk._SDKMessages", return_value=mock_svc):
            adapter._fetch_messages("conv1", limit=20)

        mock_svc.get_page.assert_called_once()
        mock_svc.get.assert_not_called()


# ---------------------------------------------------------------------------
# S3-1: _search_users
# ---------------------------------------------------------------------------

class TestSearchUsers:
    """_search_users delegates to Graph API and normalises output."""

    def test_returns_normalised_list(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.return_value = "tok"
        graph_resp = {
            "value": [
                {"id": "abc123", "displayName": "Alice Chen", "mail": "alice@mtk.com"},
                {"id": "def456", "displayName": "Alice Wang", "userPrincipalName": "awang@mtk.com"},
            ]
        }
        import requests as _req
        mock_resp = MagicMock()
        mock_resp.json.return_value = graph_resp
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = adapter._search_users("Alice")

        assert len(result) == 2
        assert result[0] == {"display_name": "Alice Chen", "email": "alice@mtk.com", "oid": "abc123"}
        assert result[1]["email"] == "awang@mtk.com"

    def test_returns_empty_on_error(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.side_effect = Exception("auth failed")
        result = adapter._search_users("Bob")
        assert result == []

    def test_passes_filter_to_graph(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp) as mock_get:
            adapter._search_users("hsuanchang")

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
        assert "startswith(displayName,'hsuanchang')" in params["$filter"]
        assert "startswith(mail,'hsuanchang')" in params["$filter"]


# ---------------------------------------------------------------------------
# S3-2/S3-3: Calendar operations
# ---------------------------------------------------------------------------

class TestGetSchedule:
    """_get_schedule delegates to Graph /me/calendar/getSchedule."""

    def test_returns_schedule_on_success(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [
                {"availabilityView": "002200", "scheduleId": "alice@co.com"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = adapter._get_schedule(["alice@co.com"], date_str="2026-07-14")

        assert len(result) == 1
        assert result[0]["availabilityView"] == "002200"
        # Verify POST body contains schedules
        call_kwargs = mock_post.call_args
        body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert "alice@co.com" in body["schedules"]

    def test_returns_empty_on_error(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.side_effect = Exception("no token")
        result = adapter._get_schedule(["alice@co.com"])
        assert result == []


class TestFindCommonAvailability:
    """_find_common_availability resolves names, fetches schedules, computes free slots."""

    def test_finds_free_slot(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.return_value = "tok"

        # _search_users returns 1 match for "Alice"
        with patch.object(adapter, "_search_users", return_value=[
            {"display_name": "Alice Chen", "email": "alice@co.com", "oid": "abc"},
        ]):
            # _get_schedule returns both-free view (0000 = 4 free slots)
            with patch.object(adapter, "_get_schedule", return_value=[
                {"availabilityView": "0000", "scheduleId": "alice@co.com"},
                {"availabilityView": "0000", "scheduleId": "bob@co.com"},
            ]):
                result = adapter._find_common_availability(["Alice", "bob@co.com"], date_str="2026-07-14")

        assert result["available_slots"] == [{"start": "09:00", "end": "11:00"}]
        assert len(result["resolved_users"]) == 2

    def test_ambiguity_guard(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_search_users", return_value=[
            {"display_name": "Alice Chen", "email": "alice1@co.com", "oid": "a"},
            {"display_name": "Alice Wang", "email": "alice2@co.com", "oid": "b"},
        ]):
            result = adapter._find_common_availability(["Alice"], date_str="2026-07-14")

        assert result["available_slots"] == []
        assert any("Ambiguous" in n for n in result["notes"])

    def test_user_not_found(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_search_users", return_value=[]):
            result = adapter._find_common_availability(["Ghost"], date_str="2026-07-14")

        assert result["available_slots"] == []
        assert any("not found" in n for n in result["notes"])

    def test_merges_adjacent_free_slots(self):
        adapter = _make_adapter()
        adapter._auth.graph_token.return_value = "tok"

        with patch.object(adapter, "_search_users", return_value=[
            {"display_name": "A", "email": "a@co.com", "oid": "a"},
        ]):
            with patch.object(adapter, "_get_schedule", return_value=[
                {"availabilityView": "000", "scheduleId": "a@co.com"},
            ]):
                result = adapter._find_common_availability(["a@co.com"], date_str="2026-07-14")

        # 3 × 30min free slots (09:00–10:30) should merge into 1 slot
        assert len(result["available_slots"]) == 1
        assert result["available_slots"][0] == {"start": "09:00", "end": "10:30"}
