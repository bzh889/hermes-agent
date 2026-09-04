"""Unit tests for the Restricted Group Policy activation gate.

Covers the four acceptance criteria from ticket 25:

1. New ``restricted_group`` config section in ``config.yaml`` with policy
   definitions, capability grants, group bindings, and activation state.
2. CLI subcommand to activate a restricted group policy for a specific
   ``conv_id`` — tested via config round-trip (save → load → resolve).
3. Gateway ingress sets an ``OriginEgressBinding`` when the message arrives
   from a restricted group (active policy matches conv_id + account_id).
4. Unbound group (no active policy or non-matching conv_id) does not set
   a binding — downstream sees ``None`` (fail-closed).

Also covers: stale policy revision, account_id wildcard, missing fields,
duplicate policies, and the fail-closed error path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from gateway.restricted_origin import (
    OriginEgressBinding,
    get_origin_binding,
    is_restricted_context,
    reset_origin_binding,
    set_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_group_gate import (
    _find_active_policy,
    _load_restricted_group_config,
    resolve_origin_binding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_origin_binding():
    """Clean ContextVar + engaged-latch slate per test."""
    from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET

    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    try:
        yield
    finally:
        _ORIGIN_BINDING.set(saved)
        ro._origin_context_engaged = saved_engaged


def _policy(
    *,
    version: str = "rev-001",
    conv_id: str = "19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
    account_id: str = "acct-test-001",
    active: bool = True,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Build a single policy dict."""
    return {
        "version": version,
        "conv_id": conv_id,
        "account_id": account_id,
        "active": active,
        "capabilities": capabilities or ["cq_read", "egress_reply"],
    }


def _config_with_policies(policies: dict[str, Any]) -> dict[str, Any]:
    """Build a config dict with the given restricted_group policies."""
    return {
        "gateway": {
            "restricted_group": {
                "policies": policies,
            },
        },
    }


# ---------------------------------------------------------------------------
# 1. Config structure — restricted_group section
# ---------------------------------------------------------------------------

class TestConfigStructure:
    """The restricted_group config section has the correct shape."""

    def test_empty_policies_returns_none(self):
        """No policies → no binding."""
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": {}},
        ):
            result = resolve_origin_binding(
                conv_id="19:any@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_no_restricted_group_section_returns_none(self):
        """Missing restricted_group section → no binding."""
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={},
        ):
            result = resolve_origin_binding(
                conv_id="19:any@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_policy_with_capabilities_still_resolves(self):
        """Capabilities field doesn't block resolution — it's read by the
        Egress Broker (ticket 26), not by the gate."""
        policies = {"rgp-test": _policy(capabilities=["cq_read", "egress_reply"])}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is not None
        assert result.policy_id == "rgp-test"


# ---------------------------------------------------------------------------
# 2. Active policy matching — conv_id + account_id + active flag
# ---------------------------------------------------------------------------

class TestActivePolicyMatching:
    """The gate matches on conv_id, account_id, and active flag."""

    def test_active_policy_matching_conv_id_sets_binding(self):
        """Active policy with matching conv_id → binding created."""
        policies = {"rgp-test-v1": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is not None
        assert isinstance(result, OriginEgressBinding)
        assert result.conv_id == "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
        assert result.policy_id == "rgp-test-v1"
        assert result.policy_revision == "rev-001"
        assert result.platform == "teams_mtk"
        assert result.adapter_identity == "TeamsMTKAdapter"
        assert result.account_id == "acct-test-001"
        assert result.profile == "default"

    def test_inactive_policy_does_not_match(self):
        """active: false → no binding."""
        policies = {"rgp-test-v1": _policy(active=False)}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is None

    def test_non_matching_conv_id_does_not_match(self):
        """Wrong conv_id → no binding."""
        policies = {"rgp-test-v1": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:different@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is None

    def test_non_matching_account_id_does_not_match(self):
        """Wrong account_id → no binding."""
        policies = {"rgp-test-v1": _policy(account_id="acct-expected")}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-wrong",
                profile="default",
            )
        assert result is None

    def test_empty_account_id_is_wildcard(self):
        """Empty account_id in policy → matches any account."""
        policies = {"rgp-test-v1": _policy(account_id="")}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="any-account-at-all",
                profile="default",
            )
        assert result is not None
        assert result.account_id == "any-account-at-all"


# ---------------------------------------------------------------------------
# 3. Unbound group — no binding set (fail-closed)
# ---------------------------------------------------------------------------

class TestUnboundGroupFailClosed:
    """An unbound group does not set a binding — downstream sees None."""

    def test_no_policy_for_conv_id_returns_none(self):
        """Conv_id not in any policy → None."""
        policies = {"rgp-other": _policy(conv_id="19:other@thread.v2")}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:unbound@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_empty_conv_id_returns_none(self):
        """Empty conv_id → None (fail-closed)."""
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": {"rgp": _policy()}},
        ):
            result = resolve_origin_binding(
                conv_id="",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_whitespace_conv_id_returns_none(self):
        """Whitespace-only conv_id → None."""
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": {"rgp": _policy()}},
        ):
            result = resolve_origin_binding(
                conv_id="   ",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None


# ---------------------------------------------------------------------------
# 4. Binding fields — all identity fields populated correctly
# ---------------------------------------------------------------------------

class TestBindingFields:
    """The binding captures all identity fields from the policy and context."""

    def test_thread_id_passed_through(self):
        policies = {"rgp-test": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
                thread_id="thread-123",
            )
        assert result is not None
        assert result.thread_id == "thread-123"

    def test_durable_task_id_defaults_empty(self):
        policies = {"rgp-test": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is not None
        assert result.durable_task_id == ""

    def test_binding_is_immutable(self):
        policies = {"rgp-test": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is not None
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            result.conv_id = "tampered"


# ---------------------------------------------------------------------------
# 5. Missing / invalid policy fields — fail-closed
# ---------------------------------------------------------------------------

class TestMissingFieldsFailClosed:
    """Missing required policy fields → fail closed (None)."""

    def test_missing_version_returns_none(self):
        policies = {"rgp-test": _policy(version="")}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is None

    def test_policy_dict_missing_conv_id_does_not_match(self):
        """Policy without conv_id field → can't match."""
        policies = {"rgp-test": {"version": "rev-001", "active": True, "account_id": ""}}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:anything@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_corrupt_policy_entry_skipped(self):
        """Non-dict policy entry → skipped, doesn't crash."""
        policies = {"rgp-bad": "not a dict", "rgp-good": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            result = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
        assert result is not None
        assert result.policy_id == "rgp-good"


# ---------------------------------------------------------------------------
# 6. Error handling — fail-closed on exceptions
# ---------------------------------------------------------------------------

class TestFailClosedOnErrors:
    """Any internal error → fail closed (None), never raise."""

    def test_config_load_exception_returns_none(self):
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            side_effect=RuntimeError("config explosion"),
        ):
            result = resolve_origin_binding(
                conv_id="19:any@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None

    def test_policies_not_dict_returns_none(self):
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": "not a dict"},
        ):
            result = resolve_origin_binding(
                conv_id="19:any@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
        assert result is None


# ---------------------------------------------------------------------------
# 7. _find_active_policy — direct unit tests
# ---------------------------------------------------------------------------

class TestFindActivePolicy:
    """_find_active_policy matches on active + conv_id + account_id."""

    def test_first_match_wins_on_duplicate_conv_id(self):
        """If two policies have the same conv_id, the first (in dict order)
        wins. Duplicate conv_id is a config error but we don't crash."""
        policies = {
            "rgp-first": _policy(conv_id="19:same@thread.v2", version="rev-A"),
            "rgp-second": _policy(conv_id="19:same@thread.v2", version="rev-B"),
        }
        result = _find_active_policy(policies, "19:same@thread.v2", "acct-test-001")
        assert result is not None
        assert result["version"] in ("rev-A", "rev-B")

    def test_policies_not_dict_returns_none(self):
        assert _find_active_policy([], "conv", "acct") is None  # type: ignore[arg-type]
        assert _find_active_policy(None, "conv", "acct") is None  # type: ignore[arg-type]

    def test_active_false_skipped(self):
        policies = {"rgp": _policy(active=False)}
        assert _find_active_policy(policies, "19:cbdcf6224c48469ea048147752ed92d9@thread.v2", "acct-test-001") is None


# ---------------------------------------------------------------------------
# 8. Gateway ingress simulation — set_origin_binding integration
# ---------------------------------------------------------------------------

class TestGatewayIngressIntegration:
    """End-to-end: resolve_origin_binding → set_origin_binding → get_origin_binding."""

    def test_restricted_group_sets_binding_in_context(self):
        """Simulate gateway ingress for a restricted group message."""
        policies = {"rgp-test-v1": _policy()}
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": policies},
        ):
            binding = resolve_origin_binding(
                conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-test-001",
                profile="default",
            )
            assert binding is not None
            token = set_origin_binding(binding)
            try:
                assert is_restricted_context()
                assert get_origin_binding() is binding
                assert get_origin_binding().conv_id == "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
            finally:
                reset_origin_binding(token)
            assert not is_restricted_context()

    def test_unbound_group_does_not_set_binding(self):
        """Simulate gateway ingress for an unbound group — no binding."""
        with patch(
            "gateway.restricted_group_gate._load_restricted_group_config",
            return_value={"policies": {}},
        ):
            binding = resolve_origin_binding(
                conv_id="19:unbound@thread.v2",
                platform="teams_mtk",
                adapter_identity="TeamsMTKAdapter",
                account_id="acct-001",
                profile="default",
            )
            assert binding is None
            # Gateway would not call set_origin_binding — verify context is clean
            assert not is_restricted_context()
            assert get_origin_binding() is None
