"""Model-routing gate — AIDE-only authorizeAndInvoke for restricted context.

Every model invocation in restricted context passes through
:func:`authorize_and_invoke`, which atomically reloads the current policy
revision and matches the complete route identity (provider, model, base_url,
route class) against the policy's allowed AIDE routes.

Non-AIDE providers are denied. A revision change between permit issuance and
invocation invalidates the permit. The gate is stateless — it holds no cached
revision between invocations.

Fail-closed: ambiguous, stale, or mismatched identity → DENY.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


class RouteDecision(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class RouteDenyReason(str, enum.Enum):
    NOT_RESTRICTED = "not_restricted"           # No origin binding — pass through
    ROUTE_IDENTITY_MISMATCH = "route_identity_mismatch"
    STALE_REVISION = "stale_revision"
    PERMIT_INVALIDATED = "permit_invalidated"
    NO_POLICY_REVISION = "no_policy_revision"
    INVALID_BINDING = "invalid_binding"


@dataclass(frozen=True)
class RouteIdentity:
    """Complete identity of a model route."""

    provider: str
    model: str
    base_url: str
    route_class: str  # "aide" | "relay" | "custom" | "openrouter" | ...


@dataclass(frozen=True)
class RouteCheckResult:
    """Result of an authorizeAndInvoke gate check."""

    decision: RouteDecision
    reason: str
    route_identity: Optional[RouteIdentity] = None
    policy_revision_at_check: str = ""


# ---------------------------------------------------------------------------
# Allowed route patterns
# ---------------------------------------------------------------------------

# AIDE route patterns — the allowed provider/base_url patterns for restricted context.
# The gate matches on provider name and base_url domain.
_AIDE_PROVIDER_PATTERNS: frozenset[str] = frozenset({
    "aide",
    "mtk",  # MTK AIDE gateway
})

_AIDE_BASE_URL_PATTERNS: tuple[str, ...] = (
    "mlop-azure-gateway.mediatek.inc",
    "aide",
)

_AIDE_ROUTE_CLASS: str = "aide"


def _is_aide_route(route: RouteIdentity) -> bool:
    """Check whether a route identity matches the AIDE pattern.

    Matches on:
    - provider in _AIDE_PROVIDER_PATTERNS, OR
    - base_url contains an AIDE pattern
    - AND route_class == "aide"
    """
    if route.route_class != _AIDE_ROUTE_CLASS:
        return False
    provider_lower = route.provider.lower()
    base_url_lower = route.base_url.lower()
    provider_match = any(
        pat in provider_lower for pat in _AIDE_PROVIDER_PATTERNS
    )
    url_match = any(
        pat in base_url_lower for pat in _AIDE_BASE_URL_PATTERNS
    )
    return provider_match or url_match


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def _reload_policy_revision(binding: OriginEgressBinding) -> str:
    """Atomically reload the current policy revision from config.

    The gate is stateless — this is called on every invocation.
    Returns the current revision string, or "" if unreadable.
    """
    try:
        from gateway.restricted_group_gate import _load_restricted_group_config

        rgp = _load_restricted_group_config()
        policies = rgp.get("policies")
        if not isinstance(policies, dict):
            return ""

        for policy_id, policy in policies.items():
            if not isinstance(policy, dict):
                continue
            if not policy.get("active", False):
                continue
            conv_id = policy.get("conv_id", "")
            if conv_id == binding.conv_id and policy_id == binding.policy_id:
                return str(policy.get("version", "") or "")
        return ""
    except Exception:
        logger.debug("policy revision reload failed", exc_info=True)
        return ""


def authorize_route(
    route: RouteIdentity,
    binding: Optional[OriginEgressBinding] = None,
    permit_revision: str = "",
) -> RouteCheckResult:
    """Check whether a model route is authorized for restricted context.

    This is the gate check — call before invoking the model. It:

    1. Resolves the origin binding (from ContextVar or explicit argument).
    2. If unrestricted (no binding) → ALLOW (pass through).
    3. Atomically reloads the current policy revision from config.
    4. Checks the route identity against AIDE patterns.
    5. Checks the permit revision matches the current revision.

    Parameters
    ----------
    route:
        The complete route identity of the model invocation.
    binding:
        The origin binding (from ContextVar if None).
    permit_revision:
        The policy revision at permit issuance time. If non-empty,
        the gate verifies it matches the current revision. If empty,
        the gate only checks the route identity.

    Returns
    -------
    RouteCheckResult
        The decision (ALLOW or DENY) with reason.
    """
    if binding is None:
        binding = get_origin_binding()

    # Unrestricted context — pass through
    if binding is None:
        return RouteCheckResult(
            decision=RouteDecision.ALLOW,
            reason=RouteDenyReason.NOT_RESTRICTED.value,
        )

    if not isinstance(binding, OriginEgressBinding):
        return RouteCheckResult(
            decision=RouteDecision.DENY,
            reason=RouteDenyReason.INVALID_BINDING.value,
        )

    # 1. Check route identity — must be AIDE
    if not _is_aide_route(route):
        return RouteCheckResult(
            decision=RouteDecision.DENY,
            reason=RouteDenyReason.ROUTE_IDENTITY_MISMATCH.value,
            route_identity=route,
        )

    # 2. Atomically reload current policy revision
    current_revision = _reload_policy_revision(binding)
    if not current_revision:
        return RouteCheckResult(
            decision=RouteDecision.DENY,
            reason=RouteDenyReason.NO_POLICY_REVISION.value,
            route_identity=route,
        )

    # 3. Check permit revision matches current revision
    if permit_revision:
        if permit_revision != current_revision:
            return RouteCheckResult(
                decision=RouteDecision.DENY,
                reason=RouteDenyReason.STALE_REVISION.value,
                route_identity=route,
                policy_revision_at_check=current_revision,
            )

    # 4. Check binding's revision matches current (stale binding)
    if binding.policy_revision != current_revision:
        return RouteCheckResult(
            decision=RouteDecision.DENY,
            reason=RouteDenyReason.PERMIT_INVALIDATED.value,
            route_identity=route,
            policy_revision_at_check=current_revision,
        )

    return RouteCheckResult(
        decision=RouteDecision.ALLOW,
        reason="authorized",
        route_identity=route,
        policy_revision_at_check=current_revision,
    )


def authorize_and_invoke(
    invoke_fn: Callable[..., Any],
    route: RouteIdentity,
    binding: Optional[OriginEgressBinding] = None,
    permit_revision: str = "",
    **invoke_kwargs: Any,
) -> Any:
    """Authorize a model route, then invoke the model if allowed.

    This is the synchronous gate + invoke function. If the route is denied,
    raises :class:`RouteDeniedError`. If allowed, calls ``invoke_fn(**invoke_kwargs)``.

    Parameters
    ----------
    invoke_fn:
        The function that performs the model invocation.
    route:
        The complete route identity.
    binding:
        The origin binding (from ContextVar if None).
    permit_revision:
        The revision at permit time (for stale-revision check).

    Returns
    -------
    The result of ``invoke_fn(**invoke_kwargs)``.

    Raises
    ------
    RouteDeniedError
        If the gate denies the route.
    """
    check = authorize_route(route, binding, permit_revision)
    if check.decision == RouteDecision.DENY:
        raise RouteDeniedError(
            reason=check.reason,
            route=route,
            revision=check.policy_revision_at_check,
        )
    return invoke_fn(**invoke_kwargs)


class RouteDeniedError(Exception):
    """Raised when the model-routing gate denies a route."""

    def __init__(
        self,
        reason: str,
        route: Optional[RouteIdentity] = None,
        revision: str = "",
    ) -> None:
        self.reason = reason
        self.route = route
        self.revision = revision
        super().__init__(
            f"model route denied: reason={reason}"
            + (f" provider={route.provider} model={route.model}" if route else "")
            + (f" revision={revision}" if revision else "")
        )
