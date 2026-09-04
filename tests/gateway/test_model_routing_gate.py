"""Unit tests for the model-routing gate (ticket 32).

Covers:
- AIDE provider with matching revision → ALLOW
- Non-AIDE provider → DENY (route_identity_mismatch)
- Stale revision (changed between permit and invoke) → DENY
- Race condition (provider switch between gate check and invoke) → DENY
- Unrestricted context → pass through
- Adversarial: forged route identity, stale revision, race condition
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from gateway.model_routing_gate import (
    RouteCheckResult,
    RouteDecision,
    RouteDenyReason,
    RouteDeniedError,
    RouteIdentity,
    _is_aide_route,
    authorize_and_invoke,
    authorize_route,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET


@pytest.fixture(autouse=True)
def _isolate():
    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    yield
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_engaged


def _make_binding(**overrides: Any) -> OriginEgressBinding:
    defaults = dict(
        profile="default",
        policy_id="rgp-test-v1",
        policy_revision="rev-001",
        platform="teams_mtk",
        adapter_identity="TeamsMTKAdapter",
        account_id="acct-test-001",
        conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
        thread_id="",
        durable_task_id="",
    )
    defaults.update(overrides)
    return OriginEgressBinding(**defaults)


def _aide_route(**overrides: Any) -> RouteIdentity:
    defaults = dict(
        provider="mtk",
        model="wfm-pro-glm5-2-744b",
        base_url="https://mlop-azure-gateway.mediatek.inc/v1",
        route_class="aide",
    )
    defaults.update(overrides)
    return RouteIdentity(**defaults)


def _non_aide_route(**overrides: Any) -> RouteIdentity:
    defaults = dict(
        provider="openrouter",
        model="anthropic/claude-sonnet-4",
        base_url="https://openrouter.ai/api/v1",
        route_class="relay",
    )
    defaults.update(overrides)
    return RouteIdentity(**defaults)


# ---------------------------------------------------------------------------
# 1. AIDE provider with matching revision → ALLOW
# ---------------------------------------------------------------------------

class TestAideAllow:
    def test_aide_route_allowed(self):
        binding = _make_binding()
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-001",
        ):
            result = authorize_route(_aide_route(), binding=binding)
        assert result.decision == RouteDecision.ALLOW

    def test_aide_route_allowed_with_permit_revision(self):
        binding = _make_binding()
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-001",
        ):
            result = authorize_route(
                _aide_route(), binding=binding, permit_revision="rev-001",
            )
        assert result.decision == RouteDecision.ALLOW


# ---------------------------------------------------------------------------
# 2. Non-AIDE provider → DENY
# ---------------------------------------------------------------------------

class TestNonAideDeny:
    def test_openrouter_denied(self):
        binding = _make_binding()
        result = authorize_route(_non_aide_route(), binding=binding)
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.ROUTE_IDENTITY_MISMATCH.value

    def test_non_aide_disguised_as_aide_denied(self):
        """Forged route identity: non-AIDE provider with route_class='aide' still denied."""
        binding = _make_binding()
        forged = RouteIdentity(
            provider="openrouter",
            model="claude-sonnet-4",
            base_url="https://openrouter.ai/api/v1",
            route_class="aide",  # forged
        )
        result = authorize_route(forged, binding=binding)
        # URL doesn't match AIDE pattern, so it's denied
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.ROUTE_IDENTITY_MISMATCH.value

    def test_aide_route_class_mismatch_denied(self):
        """AIDE provider but route_class='relay' → DENY."""
        binding = _make_binding()
        route = RouteIdentity(
            provider="mtk",
            model="glm5",
            base_url="https://mlop-azure-gateway.mediatek.inc/v1",
            route_class="relay",
        )
        result = authorize_route(route, binding=binding)
        assert result.decision == RouteDecision.DENY


# ---------------------------------------------------------------------------
# 3. Stale revision → DENY
# ---------------------------------------------------------------------------

class TestStaleRevision:
    def test_permit_revision_mismatch_denied(self):
        binding = _make_binding(policy_revision="rev-001")
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-002",  # changed
        ):
            result = authorize_route(
                _aide_route(), binding=binding, permit_revision="rev-001",
            )
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.STALE_REVISION.value

    def test_binding_revision_mismatch_denied(self):
        """Binding's revision doesn't match current config revision."""
        binding = _make_binding(policy_revision="rev-old")
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-new",
        ):
            result = authorize_route(_aide_route(), binding=binding)
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.PERMIT_INVALIDATED.value


# ---------------------------------------------------------------------------
# 4. Race condition — provider switch between gate check and invoke
# ---------------------------------------------------------------------------

class TestRaceCondition:
    def test_provider_switch_detected(self):
        """Simulate: gate checks rev-001, but binding has rev-002 (switched)."""
        binding = _make_binding(policy_revision="rev-002")
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-001",  # current config has rev-001
        ):
            result = authorize_route(
                _aide_route(),
                binding=binding,
                permit_revision="rev-001",
            )
        # Binding's revision (rev-002) != current (rev-001) → PERMIT_INVALIDATED
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.PERMIT_INVALIDATED.value


# ---------------------------------------------------------------------------
# 5. Unrestricted context → pass through
# ---------------------------------------------------------------------------

class TestUnrestrictedPassthrough:
    def test_no_binding_passes_through(self):
        result = authorize_route(_non_aide_route())
        assert result.decision == RouteDecision.ALLOW
        assert result.reason == RouteDenyReason.NOT_RESTRICTED.value


# ---------------------------------------------------------------------------
# 6. No policy revision → DENY
# ---------------------------------------------------------------------------

class TestNoPolicyRevision:
    def test_empty_current_revision_denied(self):
        binding = _make_binding()
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="",
        ):
            result = authorize_route(_aide_route(), binding=binding)
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.NO_POLICY_REVISION.value


# ---------------------------------------------------------------------------
# 7. authorize_and_invoke — function integration
# ---------------------------------------------------------------------------

class TestAuthorizeAndInvoke:
    def test_invoke_called_on_allow(self):
        binding = _make_binding()
        called = []

        def mock_invoke(**kwargs):
            called.append(kwargs)
            return {"response": "ok"}

        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-001",
        ):
            token = set_origin_binding(binding)
            try:
                result = authorize_and_invoke(
                    mock_invoke,
                    _aide_route(),
                    prompt="hello",
                )
            finally:
                reset_origin_binding(token)
        assert result == {"response": "ok"}
        assert called == [{"prompt": "hello"}]

    def test_invoke_raises_on_deny(self):
        binding = _make_binding()
        token = set_origin_binding(binding)
        try:
            with pytest.raises(RouteDeniedError) as exc:
                authorize_and_invoke(
                    lambda **kw: "should not be called",
                    _non_aide_route(),
                )
            assert exc.value.reason == RouteDenyReason.ROUTE_IDENTITY_MISMATCH.value
        finally:
            reset_origin_binding(token)


# ---------------------------------------------------------------------------
# 8. _is_aide_route — pattern matching
# ---------------------------------------------------------------------------

class TestIsAideRoute:
    def test_mtk_provider_aide_route(self):
        assert _is_aide_route(_aide_route(provider="mtk"))

    def test_aide_provider(self):
        assert _is_aide_route(_aide_route(provider="aide"))

    def test_non_aide_url_denied(self):
        assert not _is_aide_route(_aide_route(
            provider="fake",
            base_url="https://evil.example.com/v1",
        ))

    def test_wrong_route_class_denied(self):
        assert not _is_aide_route(_aide_route(route_class="relay"))


# ---------------------------------------------------------------------------
# 9. Adversarial — non-egress matrix rows 7-9
# ---------------------------------------------------------------------------

class TestAdversarialRows:
    """Non-egress matrix row 7: forged route identity.
    Row 8: stale policy revision.
    Row 9: gate-check-and-switch race.
    """

    def test_row7_forged_route_identity(self):
        """Non-AIDE provider disguised as AIDE → DENY."""
        binding = _make_binding()
        forged = RouteIdentity(
            provider="attacker",
            model="evil-model",
            base_url="https://evil.example.com/v1",
            route_class="aide",  # forged
        )
        result = authorize_route(forged, binding=binding)
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.ROUTE_IDENTITY_MISMATCH.value

    def test_row8_stale_policy_revision(self):
        """Direct policy revision modification → DENY."""
        binding = _make_binding(policy_revision="rev-001")
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-999",
        ):
            result = authorize_route(
                _aide_route(),
                binding=binding,
                permit_revision="rev-001",
            )
        assert result.decision == RouteDecision.DENY
        assert result.reason in (
            RouteDenyReason.STALE_REVISION.value,
            RouteDenyReason.PERMIT_INVALIDATED.value,
        )

    def test_row9_race_provider_switch(self):
        """Provider switch between gate check and invoke → DENY."""
        binding = _make_binding(policy_revision="rev-002")
        with patch(
            "gateway.model_routing_gate._reload_policy_revision",
            return_value="rev-001",
        ):
            result = authorize_route(
                _aide_route(),
                binding=binding,
                permit_revision="rev-001",
            )
        assert result.decision == RouteDecision.DENY
        assert result.reason == RouteDenyReason.PERMIT_INVALIDATED.value
