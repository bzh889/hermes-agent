"""Unit tests for the Egress Broker core (ticket 26).

Covers the 8 acceptance criteria:

1. `request_permit(operation, destination, route, payload, binding)` interface
2. Delivery purpose classifier: ALLOW reply/stream/edit/send_message/derived_media; DENY reaction/loop/cron/kanban
3. Origin equality: destination must match binding's conv_id/thread
4. Policy revision check: stale revision denied
5. One-use permit: second use denied
6. Permit binds exact operation, destination, route, payload fingerprint, policy revision
7. EgressIntent persisted before any side effect
8. Unit tests for each deny path + valid permit → ALLOW
"""

from __future__ import annotations

from typing import Any

import pytest

from gateway.egress_broker import (
    BrokerResult,
    DenyReason,
    EgressBroker,
    EgressIntent,
    EgressOperation,
    EgressPermit,
    PermitDecision,
    _payload_fingerprint,
    get_egress_broker,
    reset_egress_broker,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_context():
    """Clean ContextVar + broker singleton per test."""
    saved_binding = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    reset_egress_broker()
    try:
        yield
    finally:
        _ORIGIN_BINDING.set(saved_binding)
        ro._origin_context_engaged = saved_engaged
        reset_egress_broker()


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


# ---------------------------------------------------------------------------
# 1. Unrestricted context — pass-through (no-op)
# ---------------------------------------------------------------------------

class TestUnrestrictedPassthrough:
    """No origin binding → Broker is a no-op (ALLOW, NOT_RESTRICTED)."""

    def test_no_binding_returns_allow_not_restricted(self):
        broker = EgressBroker()
        result = broker.request_permit(
            operation="reply",
            destination="19:any@thread.v2",
            route="native",
            payload="hello",
        )
        assert result.decision == PermitDecision.ALLOW
        assert result.reason == DenyReason.NOT_RESTRICTED.value
        assert result.permit is None

    def test_no_binding_allows_any_operation(self):
        """Even denied operations pass through when unrestricted."""
        broker = EgressBroker()
        result = broker.request_permit(
            operation="reaction",
            destination="19:any@thread.v2",
            route="webhook",
            payload={":)": "thumbs"},
        )
        assert result.decision == PermitDecision.ALLOW


# ---------------------------------------------------------------------------
# 2. Delivery purpose classifier
# ---------------------------------------------------------------------------

class TestDeliveryPurpose:
    """ALLOW reply/stream/edit/send_message/derived_media; DENY others."""

    @pytest.mark.parametrize("op", [
        EgressOperation.REPLY.value,
        EgressOperation.STREAM.value,
        EgressOperation.EDIT.value,
        EgressOperation.SEND_MESSAGE.value,
        EgressOperation.DERIVED_MEDIA.value,
    ])
    def test_allowed_delivery_purposes(self, op: str):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation=op,
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.ALLOW
        assert result.permit is not None

    @pytest.mark.parametrize("op", [
        EgressOperation.REACTION.value,
        EgressOperation.LOOP_MUTATION.value,
        EgressOperation.CRON_FANOUT.value,
        EgressOperation.KANBAN_NOTIFICATION.value,
    ])
    def test_denied_delivery_purposes(self, op: str):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation=op,
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.DELIVERY_PURPOSE_DENIED.value


# ---------------------------------------------------------------------------
# 3. Origin equality
# ---------------------------------------------------------------------------

class TestOriginEquality:
    """Destination must match the binding's conv_id (or thread_id)."""

    def test_matching_conv_id_allowed(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.ALLOW

    def test_cross_group_destination_denied(self):
        broker = EgressBroker()
        binding = _make_binding(conv_id="19:group-A@thread.v2")
        result = broker.request_permit(
            operation="reply",
            destination="19:group-B@thread.v2",
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.ORIGIN_MISMATCH.value

    def test_matching_thread_id_allowed(self):
        broker = EgressBroker()
        binding = _make_binding(
            conv_id="19:parent@thread.v2",
            thread_id="thread-456",
        )
        result = broker.request_permit(
            operation="reply",
            destination="thread-456",
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.ALLOW

    def test_empty_destination_denied(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination="",
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.ORIGIN_MISMATCH.value


# ---------------------------------------------------------------------------
# 4. Policy revision check
# ---------------------------------------------------------------------------

class TestPolicyRevision:
    """Stale/empty policy revision → DENY (fail-closed)."""

    def test_valid_revision_allowed(self):
        broker = EgressBroker()
        binding = _make_binding(policy_revision="rev-001")
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.ALLOW
        assert result.permit.policy_revision == "rev-001"

    def test_empty_revision_denied(self):
        broker = EgressBroker()
        binding = _make_binding(policy_revision="")
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.STALE_REVISION.value


# ---------------------------------------------------------------------------
# 5. Route check
# ---------------------------------------------------------------------------

class TestRouteCheck:
    """Only NATIVE route is allowed for restricted context."""

    @pytest.mark.parametrize("route", ["relay", "webhook", "api_server"])
    def test_non_native_routes_denied(self, route: str):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route=route,
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.ROUTE_DENIED.value


# ---------------------------------------------------------------------------
# 6. One-use permit
# ---------------------------------------------------------------------------

class TestOneUsePermit:
    """A permit can only be consumed once — second use is DENY."""

    def test_consume_permit_succeeds_first_time(self):
        broker = EgressBroker()
        result = broker.request_and_consume(
            operation="reply",
            destination=_make_binding().conv_id,
            route="native",
            payload="text",
            binding=_make_binding(),
        )
        assert result.decision == PermitDecision.ALLOW
        assert result.permit is not None
        assert broker.is_consumed(result.permit.permit_id)

    def test_consume_permit_fails_second_time(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert result.decision == PermitDecision.ALLOW
        permit = result.permit
        assert broker.consume_permit(permit.permit_id) is True
        assert broker.consume_permit(permit.permit_id) is False

    def test_check_permit_validity_after_consume_denied(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        permit = result.permit
        broker.consume_permit(permit.permit_id)
        check = broker.check_permit_validity(
            permit, "reply", binding.conv_id, "native", "text"
        )
        assert check.decision == PermitDecision.DENY
        assert check.reason == DenyReason.PERMIT_REUSE.value


# ---------------------------------------------------------------------------
# 7. Permit binds exact operation, destination, route, payload fingerprint
# ---------------------------------------------------------------------------

class TestPermitBinding:
    """Permit is bound to exact operation/destination/route/payload/revision."""

    def test_permit_fields_match_request(self):
        broker = EgressBroker()
        binding = _make_binding(policy_revision="rev-042")
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="exact-payload",
            binding=binding,
        )
        assert result.permit.operation == "reply"
        assert result.permit.destination == binding.conv_id
        assert result.permit.route == "native"
        assert result.permit.policy_revision == "rev-042"
        assert result.permit.payload_fingerprint == _payload_fingerprint("exact-payload")

    def test_permit_validity_mismatch_on_operation(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="payload",
            binding=binding,
        )
        permit = result.permit
        check = broker.check_permit_validity(
            permit, "edit", binding.conv_id, "native", "payload"
        )
        assert check.decision == PermitDecision.DENY
        assert check.reason == DenyReason.PERMIT_REUSE.value

    def test_permit_validity_mismatch_on_payload(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="original",
            binding=binding,
        )
        permit = result.permit
        check = broker.check_permit_validity(
            permit, "reply", binding.conv_id, "native", "tampered"
        )
        assert check.decision == PermitDecision.DENY
        assert check.reason == DenyReason.PERMIT_REUSE.value


# ---------------------------------------------------------------------------
# 8. EgressIntent persistence (before side effect)
# ---------------------------------------------------------------------------

class TestEgressIntent:
    """EgressIntent is recorded before any side effect."""

    def test_intent_recorded_on_valid_permit(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="hello",
            binding=binding,
        )
        assert result.intent is not None
        assert result.intent.operation == "reply"
        assert result.intent.destination == binding.conv_id
        assert result.intent.policy_id == binding.policy_id
        assert result.intent.policy_revision == binding.policy_revision
        assert len(broker.intent_log) == 1

    def test_intent_not_recorded_on_denied(self):
        broker = EgressBroker()
        binding = _make_binding()
        broker.request_permit(
            operation="reaction",
            destination=binding.conv_id,
            route="native",
            payload="text",
            binding=binding,
        )
        assert len(broker.intent_log) == 0

    def test_intent_contains_fingerprint_not_raw_payload(self):
        broker = EgressBroker()
        binding = _make_binding()
        result = broker.request_permit(
            operation="reply",
            destination=binding.conv_id,
            route="native",
            payload="secret-content-here",
            binding=binding,
        )
        intent = result.intent
        assert "secret-content-here" not in intent.payload_fingerprint
        assert intent.payload_fingerprint.startswith("sha256:")


# ---------------------------------------------------------------------------
# 9. ContextVar integration — binding from get_origin_binding()
# ---------------------------------------------------------------------------

class TestContextVarIntegration:
    """Broker reads binding from ContextVar when not passed explicitly."""

    def test_broker_reads_binding_from_contextvar(self):
        broker = EgressBroker()
        binding = _make_binding()
        token = set_origin_binding(binding)
        try:
            result = broker.request_permit(
                operation="reply",
                destination=binding.conv_id,
                route="native",
                payload="text",
            )
            assert result.decision == PermitDecision.ALLOW
            assert result.permit is not None
        finally:
            reset_origin_binding(token)

    def test_broker_no_binding_in_contextvar_passes_through(self):
        broker = EgressBroker()
        result = broker.request_permit(
            operation="reply",
            destination="19:any@thread.v2",
            route="native",
            payload="text",
        )
        assert result.decision == PermitDecision.ALLOW
        assert result.reason == DenyReason.NOT_RESTRICTED.value


# ---------------------------------------------------------------------------
# 10. Payload fingerprint — determinism
# ---------------------------------------------------------------------------

class TestPayloadFingerprint:
    """Payload fingerprints are deterministic and content-based."""

    def test_same_payload_same_fingerprint(self):
        assert _payload_fingerprint("hello") == _payload_fingerprint("hello")

    def test_different_payload_different_fingerprint(self):
        assert _payload_fingerprint("hello") != _payload_fingerprint("world")

    def test_none_payload_sentinel(self):
        assert _payload_fingerprint(None) == "sha256:none"

    def test_dict_payload_deterministic(self):
        pf1 = _payload_fingerprint({"a": 1, "b": 2})
        pf2 = _payload_fingerprint({"b": 2, "a": 1})
        assert pf1 == pf2  # sort_keys=True makes order-independent


# ---------------------------------------------------------------------------
# 11. Invalid binding type
# ---------------------------------------------------------------------------

class TestInvalidBinding:
    """Non-OriginEgressBinding passed as binding → DENY INVALID_BINDING."""

    def test_string_binding_denied(self):
        broker = EgressBroker()
        result = broker.request_permit(
            operation="reply",
            destination="conv",
            route="native",
            payload="text",
            binding="not-a-binding",  # type: ignore[arg-type]
        )
        assert result.decision == PermitDecision.DENY
        assert result.reason == DenyReason.INVALID_BINDING.value


# ---------------------------------------------------------------------------
# 12. Singleton access
# ---------------------------------------------------------------------------

class TestSingleton:
    """get_egress_broker returns a process-scoped singleton."""

    def test_singleton_returns_same_instance(self):
        reset_egress_broker()
        a = get_egress_broker()
        b = get_egress_broker()
        assert a is b
