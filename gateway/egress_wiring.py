"""Integration helpers that wire the Egress Broker into adapter call sites.

This module provides the choke-point functions that sit between the gateway's
outbound emitter paths and the adapter edge. Each helper:

1. Resolves the origin binding (from ContextVar or explicit argument).
2. If restricted, calls the Egress Broker for a permit.
3. If denied, logs + records to audit chain, returns None (no adapter call).
4. If allowed (or unrestricted), invokes the adapter.
5. Records the outcome to the audit chain.

Call sites replace direct ``adapter.send(...)`` / ``adapter.send_voice(...)``
etc. with ``brokered_send(adapter, ...)`` / ``brokered_send_voice(adapter, ...)``
so the Broker is the single choke point for all restricted-context side effects.

For unrestricted context (no origin binding), the helpers are transparent
passthroughs — zero behavior change for non-restricted groups.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from gateway.egress_broker import (
    BrokerResult,
    DenyReason,
    EgressOperation,
    PermitDecision,
    get_egress_broker,
)
from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Choke-point helpers
# ---------------------------------------------------------------------------

async def brokered_send(
    adapter: Any,
    chat_id: str,
    content: str,
    *,
    metadata: Any = None,
    operation: str = EgressOperation.REPLY.value,
    route: str = "native",
    binding: Optional[OriginEgressBinding] = None,
    **send_kwargs: Any,
) -> Any:
    """Broker-gated ``adapter.send()`` — the primary reply/text delivery path.

    For restricted context: requests a permit from the Egress Broker; if
    denied, returns ``None`` without calling the adapter. If allowed, calls
    ``adapter.send(chat_id, content, metadata=metadata, **send_kwargs)``.

    For unrestricted context (no binding): transparent passthrough to
    ``adapter.send(...)`` — zero behavior change.
    """
    broker = get_egress_broker()
    result = broker.request_and_consume(
        operation=operation,
        destination=chat_id,
        route=route,
        payload=content,
        binding=binding,
    )
    if result.decision == PermitDecision.DENY:
        logger.info(
            "egress_broker DENY: op=%s dest=%s reason=%s",
            operation, chat_id[:40], result.reason,
        )
        _audit_deny(result, operation, chat_id, content, binding)
        return None

    # ALLOW — invoke the adapter
    _audit_allow_intent(result, operation, chat_id, content, binding)
    try:
        adapter_result = await adapter.send(
            chat_id, content, metadata=metadata, **send_kwargs,
        )
        _audit_outcome_allow(result, operation, chat_id, content, binding)
        return adapter_result
    except Exception as exc:
        _audit_outcome_error(result, operation, chat_id, content, binding, str(exc))
        raise


async def brokered_send_media(
    adapter: Any,
    method_name: str,
    chat_id: str,
    *,
    operation: str = EgressOperation.DERIVED_MEDIA.value,
    route: str = "native",
    binding: Optional[OriginEgressBinding] = None,
    payload_label: str = "",
    **send_kwargs: Any,
) -> Any:
    """Broker-gated media delivery (send_voice, send_video, send_document, etc.).

    Generic wrapper for any ``adapter.<method_name>(...)`` call.
    """
    broker = get_egress_broker()
    payload = payload_label or f"{method_name}:{chat_id}"
    result = broker.request_and_consume(
        operation=operation,
        destination=chat_id,
        route=route,
        payload=payload,
        binding=binding,
    )
    if result.decision == PermitDecision.DENY:
        logger.info(
            "egress_broker DENY media: method=%s dest=%s reason=%s",
            method_name, chat_id[:40], result.reason,
        )
        return None

    _audit_allow_intent(result, operation, chat_id, payload, binding)
    method = getattr(adapter, method_name)
    try:
        adapter_result = await method(chat_id=chat_id, **send_kwargs) \
            if not _is_positional_adapter(method_name) \
            else await method(chat_id, **send_kwargs)
        _audit_outcome_allow(result, operation, chat_id, payload, binding)
        return adapter_result
    except Exception as exc:
        _audit_outcome_error(result, operation, chat_id, payload, binding, str(exc))
        raise


async def brokered_edit(
    adapter: Any,
    chat_id: str,
    message_id: str,
    content: str,
    *,
    binding: Optional[OriginEgressBinding] = None,
    **edit_kwargs: Any,
) -> Any:
    """Broker-gated ``adapter.edit_message()`` — the stream/progress edit path."""
    broker = get_egress_broker()
    result = broker.request_and_consume(
        operation=EgressOperation.EDIT.value,
        destination=chat_id,
        route="native",
        payload=content,
        binding=binding,
    )
    if result.decision == PermitDecision.DENY:
        logger.info(
            "egress_broker DENY edit: dest=%s reason=%s",
            chat_id[:40], result.reason,
        )
        return None

    _audit_allow_intent(result, EgressOperation.EDIT.value, chat_id, content, binding)
    try:
        adapter_result = await adapter.edit_message(
            chat_id, message_id, content, **edit_kwargs,
        )
        _audit_outcome_allow(result, EgressOperation.EDIT.value, chat_id, content, binding)
        return adapter_result
    except Exception as exc:
        _audit_outcome_error(result, EgressOperation.EDIT.value, chat_id, content, binding, str(exc))
        raise


async def brokered_react(
    adapter: Any,
    chat_id: str,
    message_id: str,
    emoji: str,
    *,
    binding: Optional[OriginEgressBinding] = None,
) -> Any:
    """Broker-gated ``adapter.send_reaction()`` — DENY in restricted context.

    Reactions are not a Restricted Logical Delivery purpose. This helper
    always returns ``None`` in restricted context (no adapter call).
    In unrestricted context, it passes through.
    """
    broker = get_egress_broker()
    result = broker.request_and_consume(
        operation=EgressOperation.REACTION.value,
        destination=chat_id,
        route="native",
        payload=emoji,
        binding=binding,
    )
    if result.decision == PermitDecision.DENY:
        logger.info(
            "egress_broker DENY reaction: dest=%s reason=%s",
            chat_id[:40], result.reason,
        )
        return None

    _audit_allow_intent(result, "reaction", chat_id, emoji, binding)
    try:
        adapter_result = await adapter.send_reaction(chat_id, message_id, emoji)
        _audit_outcome_allow(result, "reaction", chat_id, emoji, binding)
        return adapter_result
    except Exception as exc:
        _audit_outcome_error(result, "reaction", chat_id, emoji, binding, str(exc))
        raise


# ---------------------------------------------------------------------------
# Audit integration (best-effort — never blocks the adapter call)
# ---------------------------------------------------------------------------

def _audit_deny(
    result: BrokerResult,
    operation: str,
    destination: str,
    content: Any,
    binding: Optional[OriginEgressBinding],
) -> None:
    """Record a denied permit to the audit chain."""
    try:
        from gateway.audit_chain import (
            content_fingerprint,
            destination_fingerprint,
            get_audit_chain,
        )
        from gateway.restricted_origin import get_origin_binding

        b = binding or get_origin_binding()
        if b is None:
            return  # unrestricted — no audit

        chain = get_audit_chain()
        chain.append_denied(
            reason=result.reason,
            operation_type=operation,
            destination_fingerprint=destination_fingerprint(destination),
            content_fingerprint=content_fingerprint(content),
            policy_id=b.policy_id,
            policy_revision=b.policy_revision,
        )
    except Exception:
        logger.debug("audit_deny failed (best-effort)", exc_info=True)


def _audit_allow_intent(
    result: BrokerResult,
    operation: str,
    destination: str,
    content: Any,
    binding: Optional[OriginEgressBinding],
) -> None:
    """Record an allowed intent to the audit chain."""
    try:
        from gateway.audit_chain import (
            content_fingerprint,
            destination_fingerprint,
            get_audit_chain,
        )
        from gateway.restricted_origin import get_origin_binding

        b = binding or get_origin_binding()
        if b is None:
            return

        chain = get_audit_chain()
        chain.append_intent(
            operation_type=operation,
            destination_fingerprint=destination_fingerprint(destination),
            content_fingerprint=content_fingerprint(content),
            policy_id=b.policy_id,
            policy_revision=b.policy_revision,
            permit_id=result.permit.permit_id if result.permit else "",
        )
    except Exception:
        logger.debug("audit_allow_intent failed (best-effort)", exc_info=True)


def _audit_outcome_allow(
    result: BrokerResult,
    operation: str,
    destination: str,
    content: Any,
    binding: Optional[OriginEgressBinding],
) -> None:
    """Record a successful outcome to the audit chain."""
    try:
        from gateway.audit_chain import (
            content_fingerprint,
            destination_fingerprint,
            get_audit_chain,
        )
        from gateway.restricted_origin import get_origin_binding

        b = binding or get_origin_binding()
        if b is None:
            return

        chain = get_audit_chain()
        chain.append_outcome(
            decision="allow",
            reason="ok",
            operation_type=operation,
            destination_fingerprint=destination_fingerprint(destination),
            content_fingerprint=content_fingerprint(content),
            policy_id=b.policy_id,
            policy_revision=b.policy_revision,
            permit_id=result.permit.permit_id if result.permit else "",
        )
    except Exception:
        logger.debug("audit_outcome_allow failed (best-effort)", exc_info=True)


def _audit_outcome_error(
    result: BrokerResult,
    operation: str,
    destination: str,
    content: Any,
    binding: Optional[OriginEgressBinding],
    error: str,
) -> None:
    """Record a failed outcome to the audit chain."""
    try:
        from gateway.audit_chain import (
            content_fingerprint,
            destination_fingerprint,
            get_audit_chain,
        )
        from gateway.restricted_origin import get_origin_binding

        b = binding or get_origin_binding()
        if b is None:
            return

        chain = get_audit_chain()
        chain.append_outcome(
            decision="deny",
            reason=f"adapter_error: {error[:200]}",
            operation_type=operation,
            destination_fingerprint=destination_fingerprint(destination),
            content_fingerprint=content_fingerprint(content),
            policy_id=b.policy_id,
            policy_revision=b.policy_revision,
            permit_id=result.permit.permit_id if result.permit else "",
        )
    except Exception:
        logger.debug("audit_outcome_error failed (best-effort)", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Methods that take the chat_id as the first positional argument
_POSITIONAL_METHODS = frozenset({
    "send", "send_voice", "send_video", "send_document",
    "send_image", "send_multiple_images", "edit_message",
    "send_reaction", "send_private_notice",
})


def _is_positional_adapter(method_name: str) -> bool:
    """Return True if the adapter method takes chat_id as first positional."""
    return method_name in _POSITIONAL_METHODS
