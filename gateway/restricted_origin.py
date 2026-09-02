"""Origin-bound egress binding for restricted-group policy enforcement.

When a message arrives from a restricted Teams group, the gateway binds an
immutable :class:`OriginEgressBinding` into a task-local ContextVar at ingress.
Downstream enforcement seams (Egress Broker, CQ Read Broker, model-routing
gate, audit chain) read the binding via :func:`get_origin_binding` to make
per-operation policy decisions.

Design invariants
-----------------
- **Immutable.** ``OriginEgressBinding`` is a frozen dataclass — once set it
  cannot be modified for the lifetime of the task.
- **Task-local.** The binding lives in a ``ContextVar`` (like the existing
  ``HERMES_SESSION_*`` vars), so concurrent asyncio tasks for different groups
  have isolated bindings.
- **Opt-in.** An unbound group (no active restricted policy) does not set a
  binding — :func:`get_origin_binding` returns ``None``, and downstream seams
  treat ``None`` as "not restricted, pass through."
- **Fail-closed.** If identity is ambiguous, stale, or mismatched, the gateway
  does not set a binding at all (caller sees ``None``); enforcement seams that
  require a binding deny the operation.

This module is the single source of truth for origin identity. It does NOT
make policy decisions — it only carries the identity that the activation gate
(ticket 25) and the Egress Broker (ticket 26) use to enforce policy.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class OriginEgressBinding:
    """Immutable origin-identity binding for a restricted-group task.

    Set at gateway ingress when a restricted group policy is active for the
    arriving message's ``conv_id``. Read by enforcement seams via
    :func:`get_origin_binding`.

    All fields are fingerprints/identifiers — no raw message content,
    credentials, or CQ data.
    """

    # ── Profile & policy identity ──────────────────────────────────────
    profile: str
    """Hermes profile name under which this task runs."""

    policy_id: str
    """Unique identifier of the active restricted-group policy."""

    policy_revision: str
    """Monotonic revision of the policy at bind time. Stale revisions
    invalidate permits (ticket 26/32)."""

    # ── Platform & adapter identity ───────────────────────────────────
    platform: str
    """Platform enum value (e.g. ``"teams_mtk"``)."""

    adapter_identity: str
    """Adapter class or instance identifier (e.g. ``"TeamsMTKAdapter"``)."""

    # ── Account & tenant ───────────────────────────────────────────────
    account_id: str
    """Authenticated account/tenant identity owning this session."""

    # ── Conversation & thread ──────────────────────────────────────────
    conv_id: str
    """Exact conversation/chat ID — the origin group's ``conv_id``."""

    thread_id: str
    """Thread/topic ID within the conversation (empty string if none)."""

    # ── Durable Task identity ──────────────────────────────────────────
    durable_task_id: str
    """Unique ID for this task's durable approval trail (ticket 33).
    Empty string if no durable approval has been created yet."""


# ---------------------------------------------------------------------------
# ContextVar — task-local, same pattern as session_context._SESSION_*
# ---------------------------------------------------------------------------

_UNSET: Any = object()
"""Sentinel: distinguishes "never bound in this context" from "set to None"."""

_ORIGIN_BINDING: ContextVar[Any] = ContextVar(
    "HERMES_ORIGIN_EGRESS_BINDING",
    default=_UNSET,
)

_origin_context_engaged: bool = False
"""Monotonic latch — set True by the first :func:`set_origin_binding` call."""


def set_origin_binding(binding: Optional[OriginEgressBinding]):
    """Bind (or clear) the origin egress binding for the current task.

    Returns a reset token — pass it to :func:`reset_origin_binding` in a
    ``finally`` block so nested handlers restore the outer binding.

    Parameters
    ----------
    binding:
        The :class:`OriginEgressBinding` to set, or ``None`` to explicitly
        clear (for an unbound group).

    Raises
    ------
    TypeError
        If *binding* is not ``None`` and not an :class:`OriginEgressBinding`.
    """
    global _origin_context_engaged
    _origin_context_engaged = True
    if binding is not None and not isinstance(binding, OriginEgressBinding):
        raise TypeError(
            f"set_origin_binding expects OriginEgressBinding or None, "
            f"got {type(binding).__name__}"
        )
    return _ORIGIN_BINDING.set(binding)


def reset_origin_binding(token: Any) -> None:
    """Restore the previous binding (or ``_UNSET``) after a task handler exits.

    Mirrors :func:`gateway.session_context.clear_session_vars` —
    ``ContextVar.reset(token)`` makes nested scopes stack-safe.
    """
    try:
        _ORIGIN_BINDING.reset(token)
    except (RuntimeError, TypeError, ValueError, LookupError):
        _ORIGIN_BINDING.set(_UNSET)


def get_origin_binding() -> Optional[OriginEgressBinding]:
    """Return the origin binding for the current task, or ``None``.

    Resolution order:

    1. If the ContextVar was explicitly set (even to ``None``) via
       :func:`set_origin_binding`, return that value.
    2. Otherwise (``_UNSET``) return ``None`` — no binding in this context.
       This is the "not restricted, pass through" path.

    .. note::
       Unlike :func:`gateway.session_context.get_session_env`, there is **no**
       ``os.environ`` fallback. The origin binding is never inherited from a
       process-global variable — it must be explicitly set per task.
    """
    value: Any = _ORIGIN_BINDING.get()
    if value is _UNSET:
        return None
    return value  # type: ignore[return-value]


def is_restricted_context() -> bool:
    """True if the current task has an active origin egress binding.

    Convenience for enforcement seams that need a quick boolean check
    before deciding whether to consult the full binding.
    """
    return get_origin_binding() is not None


def origin_context_engaged() -> bool:
    """True if :func:`set_origin_binding` has been called in this process.

    Mirrors :func:`gateway.session_context.session_context_engaged` —
    a monotonic latch so subprocess-env bridges can detect whether origin
    bindings are task-local (must strip on fork) or process-global.
    """
    return _origin_context_engaged
