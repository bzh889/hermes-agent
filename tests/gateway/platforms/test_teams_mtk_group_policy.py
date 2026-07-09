"""Unit tests for TeamsMTKAdapter per-group config helpers and keyword filtering.

Covers the new methods added for the per-group whitelist/policy feature:
_group_config, _group_blocked_toolsets, _group_blocked_keyword_patterns,
_find_blocked_keyword, and the require_mention resolution order used inside
_process_new_messages (replicated here as a pure function, following the
existing test_teams_mtk_footer_picker.py convention of copying logic out of
the giant async method for isolated testing).

See openspec/changes/teams-mtk-group-whitelist/ for the design rationale.
"""
from unittest.mock import patch

import pytest


def _make_adapter():
    """Build a TeamsMTKAdapter without touching the real Teams token cache.

    __init__ only reads env vars and sets up _TeamsAuth() (lazy — no token
    cache access until connect()/send() actually calls skype_token()), so
    this is safe to construct directly in tests.
    """
    from gateway.platforms.teams_mtk import TeamsMTKAdapter

    return TeamsMTKAdapter(config=None)


def _mock_config(groups: dict):
    return patch(
        "hermes_cli.config.load_config_readonly",
        return_value={"gateway": {"teams_mtk": {"groups": groups}}},
    )


# ---------------------------------------------------------------------------
# _group_config
# ---------------------------------------------------------------------------


def test_group_config_returns_entry_for_known_conv_id():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"name": "Test", "require_mention": False}}):
        cfg = adapter._group_config("19:abc@thread.v2")
        assert cfg == {"name": "Test", "require_mention": False}


def test_group_config_returns_empty_dict_for_unknown_conv_id():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"name": "Test"}}):
        assert adapter._group_config("19:other@thread.v2") == {}


def test_group_config_returns_empty_dict_on_config_failure():
    adapter = _make_adapter()
    with patch("hermes_cli.config.load_config_readonly", side_effect=RuntimeError("boom")):
        assert adapter._group_config("19:abc@thread.v2") == {}


def test_group_config_returns_empty_dict_for_non_dict_entry():
    """A malformed YAML entry (e.g. a bare string) must not crash callers."""
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": "oops-not-a-dict"}):
        assert adapter._group_config("19:abc@thread.v2") == {}


# ---------------------------------------------------------------------------
# _group_blocked_toolsets
# ---------------------------------------------------------------------------


def test_blocked_toolsets_group_level_only():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"blocked_toolsets": ["terminal", "browser"]}}):
        assert adapter._group_blocked_toolsets("19:abc@thread.v2", "any-user") == [
            "browser",
            "terminal",
        ]


def test_blocked_toolsets_per_user_union_with_group():
    adapter = _make_adapter()
    groups = {
        "19:abc@thread.v2": {
            "blocked_toolsets": ["terminal"],
            "per_user": {"user-a": {"blocked_toolsets": ["web"]}},
        }
    }
    with _mock_config(groups):
        assert adapter._group_blocked_toolsets("19:abc@thread.v2", "user-a") == [
            "terminal",
            "web",
        ]
        # A different user in the same group only gets the group-level block.
        assert adapter._group_blocked_toolsets("19:abc@thread.v2", "user-b") == ["terminal"]


def test_blocked_toolsets_no_user_id_still_applies_group_level():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"blocked_toolsets": ["terminal"]}}):
        assert adapter._group_blocked_toolsets("19:abc@thread.v2", None) == ["terminal"]


def test_blocked_toolsets_empty_for_unconfigured_group():
    adapter = _make_adapter()
    with _mock_config({}):
        assert adapter._group_blocked_toolsets("19:abc@thread.v2", "anyone") == []


# ---------------------------------------------------------------------------
# _group_blocked_keyword_patterns
# ---------------------------------------------------------------------------


def test_blocked_keyword_patterns_returns_configured_list():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"blocked_keywords": ["密碼", "API_KEY"]}}):
        assert adapter._group_blocked_keyword_patterns("19:abc@thread.v2") == [
            "密碼",
            "API_KEY",
        ]


def test_blocked_keyword_patterns_filters_non_string_and_empty():
    adapter = _make_adapter()
    with _mock_config({"19:abc@thread.v2": {"blocked_keywords": ["ok", "", "  ", 123, None]}}):
        assert adapter._group_blocked_keyword_patterns("19:abc@thread.v2") == ["ok"]


def test_blocked_keyword_patterns_empty_for_unconfigured_group():
    adapter = _make_adapter()
    with _mock_config({}):
        assert adapter._group_blocked_keyword_patterns("19:abc@thread.v2") == []


# ---------------------------------------------------------------------------
# _find_blocked_keyword
# ---------------------------------------------------------------------------


def test_find_blocked_keyword_matches_case_insensitive():
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("my API_KEY is exposed", ["api_key"]) == "api_key"


def test_find_blocked_keyword_no_match_returns_none():
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("hello world", ["密碼", "API_KEY"]) is None


def test_find_blocked_keyword_empty_text_returns_none():
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("", ["anything"]) is None


def test_find_blocked_keyword_empty_patterns_returns_none():
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("some text", []) is None


def test_find_blocked_keyword_returns_first_match():
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("薪資 and 密碼", ["薪資", "密碼"]) == "薪資"


def test_find_blocked_keyword_skips_invalid_regex_without_raising():
    """A malformed regex in one group's config must not break the whole filter."""
    adapter = _make_adapter()
    # "[" is an unterminated character class — invalid regex.
    result = adapter._find_blocked_keyword("some text with 密碼 in it", ["[", "密碼"])
    assert result == "密碼"


def test_find_blocked_keyword_regex_pattern_matches():
    """Patterns are real regex, not literal substrings."""
    adapter = _make_adapter()
    assert adapter._find_blocked_keyword("call 0912345678 now", [r"\d{10}"]) == r"\d{10}"


# ---------------------------------------------------------------------------
# require_mention resolution order (replicated pure logic — see module
# docstring; mirrors the resolution block inside _process_new_messages)
# ---------------------------------------------------------------------------


def _resolve_require_mention(group_cfg: dict, no_mention_convs: set, conv_id: str, global_default: bool) -> bool:
    """Pure replica of the resolution order added to _process_new_messages."""
    cfg_value = group_cfg.get("require_mention")
    if cfg_value is not None:
        return bool(cfg_value)
    if conv_id in no_mention_convs:
        return False
    return global_default


class TestRequireMentionResolutionOrder:
    def test_group_config_override_wins_over_everything(self):
        assert _resolve_require_mention(
            {"require_mention": True}, no_mention_convs={"19:abc@thread.v2"}, conv_id="19:abc@thread.v2", global_default=False
        ) is True

    def test_legacy_env_fallback_when_no_group_config(self):
        assert _resolve_require_mention(
            {}, no_mention_convs={"19:abc@thread.v2"}, conv_id="19:abc@thread.v2", global_default=True
        ) is False

    def test_global_default_when_neither_configured(self):
        assert _resolve_require_mention(
            {}, no_mention_convs=set(), conv_id="19:abc@thread.v2", global_default=True
        ) is True

    def test_group_config_false_overrides_legacy_env_true_membership(self):
        """Even if the conv_id happens to ALSO be in the legacy env list,
        an explicit group config value of False -> resolves to False either way,
        but this asserts the group config path is checked first (not OR'd)."""
        assert _resolve_require_mention(
            {"require_mention": False}, no_mention_convs=set(), conv_id="19:abc@thread.v2", global_default=True
        ) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
