"""Activation gate for Restricted Group Policy.

At gateway ingress, immediately after session context variables are bound,
:func:`resolve_origin_binding` checks whether the arriving message's
conversation has an active restricted-group policy. If it does, it creates
an :class:`OriginEgressBinding` from the policy and the session identity.
If it does not, it returns ``None`` — the turn is not restricted, and
downstream seams pass through.

Fail-closed: ambiguous, stale, or mismatched identity → no binding →
downstream enforcement seams that require a binding deny the operation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gateway.restricted_origin import OriginEgressBinding

logger = logging.getLogger(__name__)


def _load_restricted_group_config() -> Dict[str, Any]:
    """Read the ``gateway.restricted_group`` section from config.

    Returns an empty dict if the section is absent or config is unreadable.
    Never raises — the activation gate fails closed on any error.
    """
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly()
    except Exception:
        logger.debug("load_config_readonly failed in restricted_group gate", exc_info=True)
        return {}

    gateway = config.get("gateway")
    if not isinstance(gateway, dict):
        return {}

    rgp = gateway.get("restricted_group")
    if not isinstance(rgp, dict):
        return {}

    return rgp


def _find_active_policy(
    policies: Dict[str, Any],
    conv_id: str,
    account_id: str,
) -> Optional[Dict[str, Any]]:
    """Find the active policy matching *conv_id* and *account_id*.

    A policy matches when:
    - ``active`` is ``True``
    - ``conv_id`` equals *conv_id*
    - ``account_id`` is empty (wildcard) or equals *account_id*

    Returns the policy dict or ``None`` if no match.
    First match wins — duplicate policies with the same conv_id is a
    configuration error; the first one in dict order is used.
    """
    if not isinstance(policies, dict):
        return None

    for policy_id, policy in policies.items():
        if not isinstance(policy, dict):
            continue
        if not policy.get("active", False):
            continue
        policy_conv_id = policy.get("conv_id", "")
        if not isinstance(policy_conv_id, str) or policy_conv_id != conv_id:
            continue
        policy_account = policy.get("account_id", "")
        if not isinstance(policy_account, str):
            continue
        # Empty account_id = wildcard (match any account)
        if policy_account and policy_account != account_id:
            continue
        return policy

    return None


def resolve_origin_binding(
    conv_id: str,
    platform: str,
    adapter_identity: str,
    account_id: str,
    profile: str,
    thread_id: str = "",
    durable_task_id: str = "",
) -> Optional[OriginEgressBinding]:
    """Resolve the origin egress binding for an inbound message.

    Called at gateway ingress after ``set_session_vars``. If the message's
    *conv_id* has an active restricted-group policy, returns an
    :class:`OriginEgressBinding` capturing the full origin identity.

    Returns ``None`` when:
    - No restricted_group config exists
    - No active policy matches the conv_id
    - conv_id is empty or invalid
    - Any internal error occurs (fail-closed)

    Parameters
    ----------
    conv_id:
        Exact conversation/chat ID from the inbound message.
    platform:
        Platform enum value (e.g. ``"teams_mtk"``).
    adapter_identity:
        Adapter class or instance identifier.
    account_id:
        Authenticated account/tenant identity for this gateway session.
    profile:
        Hermes profile name.
    thread_id:
        Thread/topic ID (optional).
    durable_task_id:
        Durable Task ID (optional, usually empty at ingress).
    """
    if not conv_id or not conv_id.strip():
        return None

    try:
        rgp = _load_restricted_group_config()
        if not rgp:
            return None

        policies = rgp.get("policies")
        if not isinstance(policies, dict) or not policies:
            return None

        policy = _find_active_policy(policies, conv_id, account_id)
        if policy is None:
            return None

        # Extract policy fields. Missing required fields → fail closed.
        policy_id = policy.get("policy_id") or policy.get("id", "")
        if not policy_id:
            # Derive policy_id from the dict key if not explicitly set
            for pid, p in policies.items():
                if p is policy:
                    policy_id = pid
                    break
        if not policy_id:
            logger.warning("restricted_group: active policy for %s has no id", conv_id)
            return None

        policy_revision = str(policy.get("version", "") or "")
        if not policy_revision:
            logger.warning("restricted_group: policy %s has no version", policy_id)
            return None

        return OriginEgressBinding(
            profile=profile or "",
            policy_id=policy_id,
            policy_revision=policy_revision,
            platform=platform or "",
            adapter_identity=adapter_identity or "",
            account_id=account_id or "",
            conv_id=conv_id,
            thread_id=thread_id or "",
            durable_task_id=durable_task_id or "",
        )
    except Exception:
        logger.warning(
            "resolve_origin_binding failed for conv_id=%s — fail closed",
            conv_id,
            exc_info=True,
        )
        return None
