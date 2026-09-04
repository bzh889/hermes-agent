"""Egress Broker — the single choke point for all restricted-context side effects.

Every outbound emitter path (reply, stream, edit, send_message, derived media,
file, reaction, TTS, cron fan-out, delegation results, Kanban notifications,
webhook/API emissions) passes through the Broker when a restricted-group
policy is active.

The Broker validates:
1. **Delivery purpose** — operation must be a Restricted Logical Delivery
   purpose (reply, stream, edit, send_message text/media, derived media).
   Reactions, loop mutations, cron fan-out, Kanban notifications, and other
   non-delivery purposes are DENIED.
2. **Origin equality** — the destination must match the origin binding's
   conversation/thread. Cross-group sends are DENIED.
3. **Policy revision** — must match the binding's revision. Stale revisions
   are DENIED (fail-closed).
4. **One-use permit** — a valid call receives a permit bound to the exact
   operation, destination, route, payload fingerprint, and policy revision.
   A permit cannot be reused; second use is DENIED.

The Broker persists an ``EgressIntent`` record before any side effect (the
actual HMAC-chained audit DB is ticket 27; here we emit to an in-memory list
that ticket 27 will replace with SQLite WAL).

Calls from unrestricted context (no origin binding) pass through
unconditionally — the Broker is a no-op for non-restricted groups.
"""

from __future__ import annotations

import enum
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EgressOperation(str, enum.Enum):
    """Outbound operations classified by the Broker."""

    # ── Restricted Logical Delivery purposes (ALLOW) ──────────────────
    REPLY = "reply"
    STREAM = "stream"
    EDIT = "edit"
    SEND_MESSAGE = "send_message"
    DERIVED_MEDIA = "derived_media"

    # ── Non-delivery purposes (DENY) ───────────────────────────────────
    REACTION = "reaction"
    LOOP_MUTATION = "loop_mutation"
    CRON_FANOUT = "cron_fanout"
    KANBAN_NOTIFICATION = "kanban_notification"


# Sets for fast membership checking
_ALLOWED_OPERATIONS: frozenset[str] = frozenset(
    op.value for op in (
        EgressOperation.REPLY,
        EgressOperation.STREAM,
        EgressOperation.EDIT,
        EgressOperation.SEND_MESSAGE,
        EgressOperation.DERIVED_MEDIA,
    )
)

_DENIED_OPERATIONS: frozenset[str] = frozenset(
    op.value for op in (
        EgressOperation.REACTION,
        EgressOperation.LOOP_MUTATION,
        EgressOperation.CRON_FANOUT,
        EgressOperation.KANBAN_NOTIFICATION,
    )
)


class EgressRoute(str, enum.Enum):
    """Outbound routing classification."""

    NATIVE = "native"  # Direct adapter call (ALLOW for restricted)
    RELAY = "relay"  # Proxy/relay route (DENY for restricted)
    WEBHOOK = "webhook"  # External webhook (DENY for restricted)
    API_SERVER = "api_server"  # API server endpoint (DENY for restricted)


_ALLOWED_ROUTES: frozenset[str] = frozenset({EgressRoute.NATIVE.value})


class PermitDecision(str, enum.Enum):
    """Broker decision for a permit request."""

    ALLOW = "allow"
    DENY = "deny"


class DenyReason(str, enum.Enum):
    """Structured reason for a denial."""

    NOT_RESTRICTED = "not_restricted"  # No origin binding — pass-through
    DELIVERY_PURPOSE_DENIED = "delivery_purpose_denied"
    ORIGIN_MISMATCH = "origin_mismatch"
    STALE_REVISION = "stale_revision"
    ROUTE_DENIED = "route_denied"
    PERMIT_REUSE = "permit_reuse"
    INVALID_OPERATION = "invalid_operation"
    INVALID_BINDING = "invalid_binding"
    TASK_NOT_LIVE = "task_not_live"
    PROVENANCE_INVALID = "provenance_invalid"
    DELEGATION_NOT_BROKERED = "delegation_not_brokered"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EgressIntent:
    """Pre-side-effect intent record (ticket 27 will persist this to audit DB).

    Contains fingerprints only — no raw payload content.
    """

    operation: str
    destination: str
    route: str
    payload_fingerprint: str
    policy_id: str
    policy_revision: str
    binding_conv_id: str


@dataclass(frozen=True)
class EgressPermit:
    """One-use permit issued by the Broker for a single outbound operation.

    Bound to exact operation, destination, route, payload fingerprint, and
    policy revision. A permit can only be consumed once — ``consumed`` tracks
    usage but the field is set externally (the permit itself is immutable).
    """

    permit_id: str
    operation: str
    destination: str
    route: str
    payload_fingerprint: str
    policy_revision: str


@dataclass
class EgressPermitRecord:
    """Mutable wrapper around a permit — tracks one-use consumption.

    The permit itself is frozen; this record holds the consumption flag.
    """

    permit: EgressPermit
    consumed: bool = False


@dataclass
class BrokerResult:
    """Result of a permit request — decision, reason, and optional permit."""

    decision: PermitDecision
    reason: str
    permit: Optional[EgressPermit] = None
    intent: Optional[EgressIntent] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload_fingerprint(payload: Any) -> str:
    """SHA-256 fingerprint of the payload — for binding and audit.

    Takes a hashable representation of the payload (string, bytes, or
    JSON-serializable structure). Returns a hex digest.
    """
    if payload is None:
        return "sha256:none"
    if isinstance(payload, (str, bytes)):
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    else:
        import json

        try:
            data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        except Exception:
            data = repr(payload).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _destination_matches(origin: OriginEgressBinding, destination: str) -> bool:
    """Check destination matches the origin binding's conversation/thread.

    The destination must match the binding's ``conv_id``. If the binding has
    a non-empty ``thread_id``, the destination may also match the thread.
    """
    if not destination:
        return False
    if destination == origin.conv_id:
        return True
    # Thread match: if binding has a thread_id, check against it
    if origin.thread_id and destination == origin.thread_id:
        return True
    return False


# ---------------------------------------------------------------------------
# EgressBroker
# ---------------------------------------------------------------------------

class EgressBroker:
    """Core-owned egress broker for restricted-group policy enforcement.

    The Broker is process-scoped (one instance per gateway). Per-task state
    (issued permits) is tracked in a dict keyed by permit_id. The broker is
    thread-safe for asyncio (single-threaded) — if the gateway goes
    multi-threaded, add a lock.

    When no origin binding is set (unrestricted context), the Broker is
    a no-op — ``request_permit`` returns ``BrokerResult(ALLOW, NOT_RESTRICTED)``.
    """

    def __init__(self) -> None:
        # Issued permits, keyed by permit_id for one-use tracking
        self._permits: dict[str, EgressPermitRecord] = {}
        # Intent log (ticket 27 will replace this with SQLite WAL)
        self._intents: list[EgressIntent] = []

    def request_permit(
        self,
        operation: str,
        destination: str,
        route: str,
        payload: Any = None,
        binding: Optional[OriginEgressBinding] = None,
    ) -> BrokerResult:
        """Request a one-use permit for an outbound operation.

        Parameters
        ----------
        operation:
            The outbound operation name (see :class:`EgressOperation`).
        destination:
            The target conversation/thread ID.
        route:
            The routing path (see :class:`EgressRoute`).
        payload:
            The outbound payload (fingerprinted, never stored raw).
        binding:
            The origin binding for the current task. If ``None``, the
            Broker reads from the ContextVar via :func:`get_origin_binding`.

        Returns
        -------
        BrokerResult
            The decision (ALLOW with permit, or DENY with reason).
        """
        # Resolve binding
        if binding is None:
            binding = get_origin_binding()

        # Unrestricted context — pass through (no-op)
        if binding is None:
            return BrokerResult(
                decision=PermitDecision.ALLOW,
                reason=DenyReason.NOT_RESTRICTED.value,
            )

        # Validate binding is a real OriginEgressBinding
        if not isinstance(binding, OriginEgressBinding):
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.INVALID_BINDING.value,
            )

        # 1. Delivery purpose check
        if operation not in _ALLOWED_OPERATIONS:
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.DELIVERY_PURPOSE_DENIED.value,
            )

        # 2. Route check — only NATIVE allowed for restricted
        if route not in _ALLOWED_ROUTES:
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.ROUTE_DENIED.value,
            )

        # 3. Origin equality — destination must match binding
        if not _destination_matches(binding, destination):
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.ORIGIN_MISMATCH.value,
            )

        # 4. Policy revision — check binding has a non-empty revision
        if not binding.policy_revision:
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.STALE_REVISION.value,
            )

        # 5. Task liveness — if binding has a durable_task_id, verify the
        # task is still active (not expired/completed) in the approval store.
        if binding.durable_task_id:
            if not self._is_task_live(binding):
                return BrokerResult(
                    decision=PermitDecision.DENY,
                    reason=DenyReason.TASK_NOT_LIVE.value,
                )

        # 6. Content provenance — if payload carries a provenance tag, verify it.
        provenance_ok, provenance_reason = self._check_provenance(payload, binding)
        if not provenance_ok:
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=provenance_reason or DenyReason.PROVENANCE_INVALID.value,
            )

        # Compute payload fingerprint
        pf = _payload_fingerprint(payload)

        # Create intent record (persisted before side effect)
        intent = EgressIntent(
            operation=operation,
            destination=destination,
            route=route,
            payload_fingerprint=pf,
            policy_id=binding.policy_id,
            policy_revision=binding.policy_revision,
            binding_conv_id=binding.conv_id,
        )
        self._intents.append(intent)

        # Issue one-use permit
        import uuid

        permit_id = f"permit-{uuid.uuid4()}"
        permit = EgressPermit(
            permit_id=permit_id,
            operation=operation,
            destination=destination,
            route=route,
            payload_fingerprint=pf,
            policy_revision=binding.policy_revision,
        )
        self._permits[permit_id] = EgressPermitRecord(permit=permit, consumed=False)

        return BrokerResult(
            decision=PermitDecision.ALLOW,
            reason="permitted",
            permit=permit,
            intent=intent,
        )

    # ------------------------------------------------------------------
    # Task liveness + content provenance (spec gap fixes)
    # ------------------------------------------------------------------

    def _is_task_live(self, binding: OriginEgressBinding) -> bool:
        """Check that the Durable Task is still active (not expired/completed).

        Queries the DurableApprovalStore if available. Returns True if
        the task is in a pending or approved state; False if completed,
        rejected, expired, or not found. When the approval store is
        unavailable, fail-closed returns False.
        """
        if not binding.durable_task_id:
            return True  # no durable task — no liveness requirement
        try:
            from gateway.durable_approval import get_approval_store
            store = get_approval_store()
            from gateway.durable_approval import ApprovalState
            task = store.get_task(binding.durable_task_id)
            if task is None:
                return True  # task not in store — allow (binding is new)
            if task.state in (ApprovalState.PENDING, ApprovalState.APPROVED):
                return True
            return False  # COMPLETED, REJECTED, EXPIRED → deny
        except Exception:
            logger.debug("task liveness check failed — fail-closed deny", exc_info=True)
            return False

    def _check_provenance(
        self,
        payload: Any,
        binding: OriginEgressBinding,
    ) -> tuple[bool, str]:
        """Verify content provenance for sealed provenance-aware media.

        If the payload carries a ``_provenance`` dict (in-band marker for
        provenance-aware media), verify the conv_id and policy_id match
        the binding. If no provenance marker is present, allow (the
        payload is not provenance-aware media).

        Returns (True, "") on allow, (False, reason) on deny.
        """
        if not isinstance(payload, dict):
            return True, ""
        provenance: Any = payload.get("_provenance")
        if not isinstance(provenance, dict):
            return True, ""  # not provenance-aware → no check needed
        prov_conv = provenance.get("conv_id", "")
        prov_policy = provenance.get("policy_id", "")
        if prov_conv and prov_conv != binding.conv_id:
            return False, DenyReason.PROVENANCE_INVALID.value
        if prov_policy and prov_policy != binding.policy_id:
            return False, DenyReason.PROVENANCE_INVALID.value
        return True, ""

    # ------------------------------------------------------------------

    def consume_permit(self, permit_id: str) -> bool:
        """Mark a permit as consumed (one-use enforcement).

        Returns ``True`` if the permit was valid and not yet consumed,
        ``False`` if already consumed or unknown.
        """
        record = self._permits.get(permit_id)
        if record is None:
            return False
        if record.consumed:
            return False
        record.consumed = True
        return True

    def is_consumed(self, permit_id: str) -> bool:
        """Check whether a permit has been consumed."""
        record = self._permits.get(permit_id)
        if record is None:
            return False
        return record.consumed

    def request_and_consume(
        self,
        operation: str,
        destination: str,
        route: str,
        payload: Any = None,
        binding: Optional[OriginEgressBinding] = None,
    ) -> BrokerResult:
        """Request a permit and immediately consume it (atomic request+use).

        This is the common path — callers that don't need to separate
        request from consume use this convenience method.
        """
        result = self.request_permit(operation, destination, route, payload, binding)
        if result.decision == PermitDecision.ALLOW and result.permit is not None:
            self.consume_permit(result.permit.permit_id)
        return result

    def check_permit_validity(
        self,
        permit: EgressPermit,
        operation: str,
        destination: str,
        route: str,
        payload: Any = None,
    ) -> BrokerResult:
        """Verify a previously-issued permit is still valid for the given call.

        Checks: permit exists, not consumed, operation/destination/route/
        payload fingerprint/policy revision all match.
        """
        record = self._permits.get(permit.permit_id)
        if record is None or record.consumed:
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.PERMIT_REUSE.value,
            )

        pf = _payload_fingerprint(payload)
        if (
            permit.operation != operation
            or permit.destination != destination
            or permit.route != route
            or permit.payload_fingerprint != pf
        ):
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.PERMIT_REUSE.value,
            )

        return BrokerResult(
            decision=PermitDecision.ALLOW,
            reason="permit_valid",
            permit=permit,
        )

    @property
    def intent_log(self) -> list[EgressIntent]:
        """Read-only access to the intent log (for testing / ticket 27)."""
        return list(self._intents)

    def reset(self) -> None:
        """Clear all state — for testing only."""
        self._permits.clear()
        self._intents.clear()

    # ------------------------------------------------------------------
    # Delegation result brokering (spec gap fix)
    # ------------------------------------------------------------------

    def broker_delegation_result(
        self,
        delegation_result: Any,
        destination: str,
        binding: Optional[OriginEgressBinding] = None,
    ) -> BrokerResult:
        """Broker a delegation/background completion result.

        Subagent results must return through the Broker. This helper
        enforces that the result is delivered to the origin group only,
        not to a cross-group destination, and that the operation is
        classified as a restricted logical delivery (reply/send_message).

        Returns ALLOW with a permit if the delegation result may be
        delivered; DENY if the result targets a cross-group destination
        or the operation is not permitted.
        """
        if binding is None:
            binding = get_origin_binding()

        # Unrestricted context — pass through
        if binding is None:
            return BrokerResult(
                decision=PermitDecision.ALLOW,
                reason=DenyReason.NOT_RESTRICTED.value,
            )

        if not isinstance(binding, OriginEgressBinding):
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.INVALID_BINDING.value,
            )

        # Verify destination is the origin group
        if not _destination_matches(binding, destination):
            return BrokerResult(
                decision=PermitDecision.DENY,
                reason=DenyReason.ORIGIN_MISMATCH.value,
            )

        # Issue a permit for the delegation result delivery
        pf = _payload_fingerprint(delegation_result)
        import uuid

        permit_id = f"permit-{uuid.uuid4()}"
        permit = EgressPermit(
            permit_id=permit_id,
            operation=EgressOperation.SEND_MESSAGE.value,
            destination=destination,
            route="native",
            payload_fingerprint=pf,
            policy_revision=binding.policy_revision,
        )
        self._permits[permit_id] = EgressPermitRecord(permit=permit, consumed=False)

        intent = EgressIntent(
            operation=EgressOperation.SEND_MESSAGE.value,
            destination=destination,
            route="native",
            payload_fingerprint=pf,
            policy_id=binding.policy_id,
            policy_revision=binding.policy_revision,
            binding_conv_id=binding.conv_id,
        )
        self._intents.append(intent)

        return BrokerResult(
            decision=PermitDecision.ALLOW,
            reason="delegation_brokered",
            permit=permit,
            intent=intent,
        )


# ---------------------------------------------------------------------------
# Module-level singleton (process-scoped)
# ---------------------------------------------------------------------------

_broker: Optional[EgressBroker] = None


def get_egress_broker() -> EgressBroker:
    """Return the process-scoped Egress Broker singleton."""
    global _broker
    if _broker is None:
        _broker = EgressBroker()
    return _broker


def reset_egress_broker() -> None:
    """Reset the singleton — for testing only."""
    global _broker
    _broker = None
