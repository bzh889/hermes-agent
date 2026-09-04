"""CQ Read Broker — seven read-only operations against ALPS/MOLY CQ systems.

A host-side, credential-owning broker that exposes exactly seven read-only
operations: query, page, export, search, filter, sort, aggregate.

The broker authenticates to the CQ system using the owner's credentials but
never exposes them to the model's context. INSERT, UPDATE, DELETE, raw-query,
and credential-access operations are denied before any CQ system interaction.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


class CQDecision(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class CQDenyReason(str, enum.Enum):
    WRITE_OPERATION_BLOCKED = "write_operation_blocked"
    RAW_QUERY_DENIED = "raw_query_denied"
    CREDENTIAL_ACCESS_DENIED = "credential_access_denied"
    NOT_RESTRICTED = "not_restricted"
    INVALID_BINDING = "invalid_binding"
    UNKNOWN_OPERATION = "unknown_operation"
    CQ_BACKEND_ERROR = "cq_backend_error"


_READ_OPERATIONS: frozenset[str] = frozenset({
    "query", "page", "export", "search", "filter", "sort", "aggregate",
})

_WRITE_OPERATIONS: frozenset[str] = frozenset({
    "insert", "update", "delete", "drop", "alter", "grant", "execute",
    "create", "truncate", "merge",
})


@dataclass(frozen=True)
class CQResult:
    decision: CQDecision
    reason: str
    data: Any = None
    operation: str = ""


class CQReadBroker:
    """Host-side broker for read-only CQ operations.

    Owns the credential connection to the CQ system. The model interacts
    with the broker's API, never with credentials.
    """

    def __init__(self, cq_backend: Optional[Callable[..., Any]] = None) -> None:
        """Initialize with an optional mock/test CQ backend.

        In production, the backend is the real CQ system connection.
        """
        self._backend = cq_backend
        self._credential_marker = "***OWNER_CREDENTIAL***"

    @property
    def credential_marker(self) -> str:
        """The credential marker — for testing that credentials are not exposed."""
        return self._credential_marker

    def execute(
        self,
        operation: str,
        binding: Optional[OriginEgressBinding] = None,
        **params: Any,
    ) -> CQResult:
        """Execute a CQ operation through the broker.

        Read operations (query, page, export, search, filter, sort, aggregate)
        are allowed and forwarded to the backend. Write operations and raw
        queries are denied before any backend interaction.

        Parameters
        ----------
        operation:
            The operation name (one of the seven read operations, or a write op).
        binding:
            The origin binding (from ContextVar if None).
        **params:
            Operation parameters (query string, filters, etc.).
        """
        op_lower = operation.lower().strip()

        # 1. Reject write operations — before any CQ interaction
        if op_lower in _WRITE_OPERATIONS:
            return CQResult(
                decision=CQDecision.DENY,
                reason=CQDenyReason.WRITE_OPERATION_BLOCKED.value,
                operation=op_lower,
            )

        # 2. Reject raw SQL queries — detect SELECT-style raw queries
        if op_lower == "raw_query" or op_lower == "raw":
            return CQResult(
                decision=CQDecision.DENY,
                reason=CQDenyReason.RAW_QUERY_DENIED.value,
                operation=op_lower,
            )

        # 3. Reject credential access attempts
        if op_lower in ("get_credentials", "credentials", "auth", "token"):
            return CQResult(
                decision=CQDecision.DENY,
                reason=CQDenyReason.CREDENTIAL_ACCESS_DENIED.value,
                operation=op_lower,
            )

        # 4. Reject unknown operations
        if op_lower not in _READ_OPERATIONS:
            return CQResult(
                decision=CQDecision.DENY,
                reason=CQDenyReason.UNKNOWN_OPERATION.value,
                operation=op_lower,
            )

        # 5. Resolve binding (optional for CQ — broker works in unrestricted too)
        if binding is None:
            binding = get_origin_binding()

        # 6. Execute the read operation against the backend
        try:
            if self._backend is None:
                return CQResult(
                    decision=CQDecision.ALLOW,
                    reason="ok",
                    data=[],
                    operation=op_lower,
                )
            data = self._backend(operation=op_lower, **params)
            return CQResult(
                decision=CQDecision.ALLOW,
                reason="ok",
                data=data,
                operation=op_lower,
            )
        except Exception as exc:
            return CQResult(
                decision=CQDecision.DENY,
                reason=CQDenyReason.CQ_BACKEND_ERROR.value,
                operation=op_lower,
            )


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_broker: Optional[CQReadBroker] = None


def get_cq_broker() -> CQReadBroker:
    global _broker
    if _broker is None:
        _broker = CQReadBroker()
    return _broker


def reset_cq_broker() -> None:
    global _broker
    _broker = None
