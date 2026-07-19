"""Tests for TeamsMTK per-group whitelist authorization and policy overrides.

Companion to test_relay_upstream_authz.py — same "bare GatewayRunner via
object.__new__" pattern. Background: TeamsMTK had no group-level whitelist;
group access could only be granted by adding every member's OID to the
global GATEWAY_ALLOWED_USERS, which authorizes them on every platform/chat,
not just the intended group. This adds a config-driven per-conv_id whitelist
(gateway.teams_mtk.groups in config.yaml) that authorizes any sender in a
listed group conversation, independent of the individual allowlist.

"""

from unittest.mock import patch

import pytest

from gateway.config import Platform
from gateway.session import SessionSource


def _clear_auth_env(monkeypatch) -> None:
    for key in ("GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS"):
        monkeypatch.delenv(key, raising=False)


def _make_runner():
    """Bare GatewayRunner with no adapters — group-whitelist path never
    touches self.adapters, so an empty map is fine here."""
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    return runner


def _group_source(chat_id: str, user_id: str = "some-user-oid", **kw) -> SessionSource:
    base = dict(
        platform=Platform.TEAMS_MTK,
        chat_id=chat_id,
        user_id=user_id,
        user_name="Someone",
        chat_type="group",
    )
    base.update(kw)
    return SessionSource(**base)


def _mock_config(groups: dict):
    """Patch hermes_cli.config.load_config_readonly to return a fixed groups map."""
    return patch(
        "hermes_cli.config.load_config_readonly",
        return_value={"gateway": {"teams_mtk": {"groups": groups}}},
    )


# ---------------------------------------------------------------------------
# _teams_mtk_group_is_whitelisted
# ---------------------------------------------------------------------------


def test_whitelisted_group_conv_id_returns_true():
    runner = _make_runner()
    with _mock_config({"19:abc@thread.v2": {"name": "Test"}}):
        assert runner._teams_mtk_group_is_whitelisted("19:abc@thread.v2") is True


def test_non_whitelisted_group_conv_id_returns_false():
    runner = _make_runner()
    with _mock_config({"19:abc@thread.v2": {"name": "Test"}}):
        assert runner._teams_mtk_group_is_whitelisted("19:other@thread.v2") is False


def test_none_chat_id_returns_false():
    runner = _make_runner()
    with _mock_config({"19:abc@thread.v2": {}}):
        assert runner._teams_mtk_group_is_whitelisted(None) is False


def test_empty_groups_returns_false():
    runner = _make_runner()
    with _mock_config({}):
        assert runner._teams_mtk_group_is_whitelisted("19:abc@thread.v2") is False


def test_config_read_failure_fails_closed():
    """A broken config.yaml must not silently authorize — fail-closed."""
    runner = _make_runner()
    with patch(
        "hermes_cli.config.load_config_readonly", side_effect=RuntimeError("boom")
    ):
        assert runner._teams_mtk_group_is_whitelisted("19:abc@thread.v2") is False


def test_non_dict_groups_value_returns_false():
    """A malformed groups value (e.g. a list from a YAML typo) must not crash."""
    runner = _make_runner()
    with patch(
        "hermes_cli.config.load_config_readonly",
        return_value={"gateway": {"teams_mtk": {"groups": ["not", "a", "dict"]}}},
    ):
        assert runner._teams_mtk_group_is_whitelisted("19:abc@thread.v2") is False


# ---------------------------------------------------------------------------
# _is_user_authorized integration: group whitelist bypasses GATEWAY_ALLOWED_USERS
# ---------------------------------------------------------------------------


def test_whitelisted_group_member_authorized_without_individual_allowlist(monkeypatch):
    """The core requirement: a sender NOT in GATEWAY_ALLOWED_USERS is still
    authorized because their conv_id is group-whitelisted."""
    _clear_auth_env(monkeypatch)
    runner = _make_runner()
    runner.pairing_store = None  # must not be reached — group whitelist short-circuits first
    with _mock_config({"19:abc@thread.v2": {"name": "Test"}}):
        src = _group_source("19:abc@thread.v2", user_id="not-in-any-allowlist")
        assert runner._is_user_authorized(src) is True


def test_non_whitelisted_group_falls_back_to_individual_allowlist(monkeypatch):
    """A group NOT in the whitelist must NOT be auto-authorized — it falls
    through to the existing GATEWAY_ALLOWED_USERS / default-deny path."""
    _clear_auth_env(monkeypatch)
    runner = _make_runner()
    from unittest.mock import MagicMock
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    with _mock_config({}):
        src = _group_source("19:other@thread.v2", user_id="random-user")
        assert runner._is_user_authorized(src) is False


def test_dm_conversations_unaffected_by_group_whitelist(monkeypatch):
    """A DM (chat_type='dm') must never consult the group whitelist, even if
    its chat_id happens to collide with a whitelisted group's conv_id."""
    _clear_auth_env(monkeypatch)
    runner = _make_runner()
    from unittest.mock import MagicMock
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    with _mock_config({"19:abc@thread.v2": {"name": "Test"}}):
        src = _group_source("19:abc@thread.v2", user_id="someone", chat_type="dm")
        assert runner._is_user_authorized(src) is False


def test_individually_allowlisted_user_still_authorized_in_non_whitelisted_group(monkeypatch):
    """Regression guard: existing GATEWAY_ALLOWED_USERS behavior must survive
    unchanged for groups that are NOT in the new whitelist."""
    monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "my-oid")
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)
    runner = _make_runner()
    from unittest.mock import MagicMock
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    with _mock_config({}):
        src = _group_source("19:other@thread.v2", user_id="my-oid")
        assert runner._is_user_authorized(src) is True


# ---------------------------------------------------------------------------
# _merge_teams_mtk_group_disabled_toolsets
# ---------------------------------------------------------------------------


def test_merge_disabled_toolsets_group_level():
    runner = _make_runner()
    groups = {"19:abc@thread.v2": {"blocked_toolsets": ["terminal", "browser"]}}
    with _mock_config(groups):
        src = _group_source("19:abc@thread.v2", user_id="anyone")
        result = runner._merge_teams_mtk_group_disabled_toolsets(src, None)
        assert result == ["browser", "terminal"]


def test_merge_disabled_toolsets_per_user_only_affects_that_user():
    runner = _make_runner()
    groups = {
        "19:abc@thread.v2": {
            "per_user": {"user-a": {"blocked_toolsets": ["web"]}}
        }
    }
    with _mock_config(groups):
        src_a = _group_source("19:abc@thread.v2", user_id="user-a")
        src_b = _group_source("19:abc@thread.v2", user_id="user-b")
        assert runner._merge_teams_mtk_group_disabled_toolsets(src_a, None) == ["web"]
        assert runner._merge_teams_mtk_group_disabled_toolsets(src_b, None) is None


def test_merge_disabled_toolsets_group_and_per_user_union():
    runner = _make_runner()
    groups = {
        "19:abc@thread.v2": {
            "blocked_toolsets": ["terminal"],
            "per_user": {"user-a": {"blocked_toolsets": ["web"]}},
        }
    }
    with _mock_config(groups):
        src = _group_source("19:abc@thread.v2", user_id="user-a")
        result = runner._merge_teams_mtk_group_disabled_toolsets(src, None)
        assert result == ["terminal", "web"]


def test_merge_disabled_toolsets_unions_with_global_setting():
    """Group blocked_toolsets must ADD to (not replace) an existing global
    agent.disabled_toolsets list."""
    runner = _make_runner()
    groups = {"19:abc@thread.v2": {"blocked_toolsets": ["browser"]}}
    with _mock_config(groups):
        src = _group_source("19:abc@thread.v2", user_id="anyone")
        result = runner._merge_teams_mtk_group_disabled_toolsets(src, ["code_execution"])
        assert result == ["browser", "code_execution"]


def test_merge_disabled_toolsets_noop_for_non_group_chat():
    """DMs and non-TeamsMTK platforms must pass disabled_toolsets through unchanged."""
    runner = _make_runner()
    groups = {"19:abc@thread.v2": {"blocked_toolsets": ["browser"]}}
    with _mock_config(groups):
        dm_src = _group_source("19:abc@thread.v2", user_id="anyone", chat_type="dm")
        assert runner._merge_teams_mtk_group_disabled_toolsets(dm_src, ["x"]) == ["x"]

        other_platform_src = SessionSource(
            platform=Platform.DISCORD,
            chat_id="19:abc@thread.v2",
            user_id="anyone",
            chat_type="group",
        )
        assert runner._merge_teams_mtk_group_disabled_toolsets(other_platform_src, ["x"]) == ["x"]


def test_merge_disabled_toolsets_config_failure_returns_input_unchanged():
    runner = _make_runner()
    with patch("hermes_cli.config.load_config_readonly", side_effect=RuntimeError("boom")):
        src = _group_source("19:abc@thread.v2", user_id="anyone")
        assert runner._merge_teams_mtk_group_disabled_toolsets(src, ["x"]) == ["x"]


def test_merge_disabled_toolsets_unconfigured_group_returns_input_unchanged():
    runner = _make_runner()
    with _mock_config({}):
        src = _group_source("19:not-configured@thread.v2", user_id="anyone")
        assert runner._merge_teams_mtk_group_disabled_toolsets(src, ["x"]) == ["x"]
