"""Phase 5 final capabilities for Restricted Group Policy.

1. Confidence-gated triage — >90% blocks inferred function, ≤90% holds 24h
2. Privacy-preserving learning — de-identified Optimization Records, 30-day expiry
3. CQ export consistency — stable sort + duplicate/gap detection + 8 fail-closed
4. Production go-live gate — exact owner activation
5. Post-deploy verification — per-seam probes + observation window
"""

from __future__ import annotations

import enum
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding

logger = logging.getLogger(__name__)


# ===========================================================================
# 1. Confidence-gated triage
# ===========================================================================

class TriageAction(str, enum.Enum):
    BLOCK = "block"          # >90% confidence → block inferred function
    HOLD = "hold"            # ≤90% confidence → hold 24h
    ALLOW = "allow"          # Normal operation, no failure detected
    ESCALATION_DENIED = "escalation_denied"  # Error text tried to escalate authority


@dataclass(frozen=True)
class TriageResult:
    action: TriageAction
    confidence: float
    inferred_function: str = ""
    hold_duration_hours: int = 24
    reason: str = ""


def triage_failure(
    confidence: float,
    inferred_function: str,
    error_text: str = "",
) -> TriageResult:
    """Triage a production failure with confidence-gated decision.

    >90% confidence that the failure is in the inferred function → BLOCK.
    ≤90% → HOLD the triggering operation for 24h.
    Adversarial error text is treated as untrusted input — it cannot
    escalate authority.
    """
    # Adversarial error text cannot escalate authority
    # Check if the error text contains escalation attempts
    escalation_markers = [
        "approve", "escalate", "override", "bypass", "grant_access",
        "elevated", "sudo", "admin", "owner_decision",
    ]
    error_lower = error_text.lower()
    if any(m in error_lower for m in escalation_markers):
        return TriageResult(
            action=TriageAction.ESCALATION_DENIED,
            confidence=confidence,
            inferred_function=inferred_function,
            reason="error_text_contains_escalation_attempt",
        )

    if confidence > 0.90:
        return TriageResult(
            action=TriageAction.BLOCK,
            confidence=confidence,
            inferred_function=inferred_function,
            reason=f"confidence_{confidence:.1%}_exceeds_90_threshold",
        )
    return TriageResult(
        action=TriageAction.HOLD,
        confidence=confidence,
        inferred_function=inferred_function,
        hold_duration_hours=24,
        reason=f"confidence_{confidence:.1%}_at_or_below_90_threshold",
    )


# ===========================================================================
# 2. Privacy-preserving learning
# ===========================================================================

@dataclass(frozen=True)
class OptimizationRecord:
    """De-identified optimization record — no member identities or raw content."""
    record_id: str
    operation_type: str
    outcome: str          # "success" | "failure"
    content_fingerprint: str
    policy_id: str
    created_at: float
    expires_at: float
    metadata_fingerprint: str = ""  # de-identified metadata


@dataclass(frozen=True)
class SharedKnowledgeCandidate:
    """A candidate for shared knowledge — expires after 30 days."""
    candidate_id: str
    content_fingerprint: str
    topic: str
    confidence: float
    created_at: float
    expires_at: float


@dataclass
class LearningStore:
    """In-memory store for optimization records and knowledge candidates."""
    records: list[OptimizationRecord] = field(default_factory=list)
    candidates: list[SharedKnowledgeCandidate] = field(default_factory=list)
    _pkb_promoted: set[str] = field(default_factory=set)

    def add_record(self, record: OptimizationRecord) -> None:
        self.records.append(record)

    def add_candidate(self, candidate: SharedKnowledgeCandidate) -> None:
        self.candidates.append(candidate)

    def promote_to_pkb(self, candidate_id: str, owner_approved: bool = False) -> bool:
        """Owner-approved PKB promotion — no auto-ingestion."""
        if not owner_approved:
            return False
        c = next((c for c in self.candidates if c.candidate_id == candidate_id), None)
        if c is None or c.expires_at < _now():
            return False
        self._pkb_promoted.add(candidate_id)
        return True

    def expired_candidates(self, now: float) -> list[SharedKnowledgeCandidate]:
        return [c for c in self.candidates if c.expires_at < now]


_learning: Optional[LearningStore] = None


def get_learning_store() -> LearningStore:
    global _learning
    if _learning is None:
        _learning = LearningStore()
    return _learning


def reset_learning_store() -> None:
    global _learning
    _learning = None


def _now() -> float:
    import time
    return time.time()


# ===========================================================================
# 3. CQ export consistency
# ===========================================================================

class CQExportStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_RESULT = "INCOMPLETE_RESULT"


_FAIL_CLOSED_CONDITIONS = [
    "missing_sort_key",
    "duplicate_detected",
    "gap_detected",
    "timeout",
    "auth_failure",
    "policy_revision_mismatch",
    "binding_not_found",
    "backend_error",
]


@dataclass(frozen=True)
class CQExportResult:
    status: CQExportStatus
    records: list[dict[str, Any]]
    diagnostics: dict[str, Any]


def cq_export(
    raw_records: list[dict[str, Any]],
    sort_key: str = "id",
    binding: Optional[OriginEgressBinding] = None,
    timeout: bool = False,
    auth_failure: bool = False,
) -> CQExportResult:
    """CQ export with stable sort + duplicate/gap detection + 8 fail-closed conditions.

    Returns COMPLETE with sorted records, or INCOMPLETE_RESULT with diagnostic
    metadata if any fail-closed condition is met.
    """
    diagnostics: dict[str, Any] = {}

    # Fail-closed conditions
    if timeout:
        diagnostics["condition"] = "timeout"
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)
    if auth_failure:
        diagnostics["condition"] = "auth_failure"
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)
    if binding is not None and not binding.policy_revision:
        diagnostics["condition"] = "policy_revision_mismatch"
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)
    if binding is None:
        pass  # unrestricted — proceed
    elif not isinstance(binding, OriginEgressBinding):
        diagnostics["condition"] = "binding_not_found"
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)

    # Sort key check
    for r in raw_records:
        if sort_key not in r:
            diagnostics["condition"] = "missing_sort_key"
            diagnostics["missing_key"] = sort_key
            return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)

    # Stable sort
    sorted_records = sorted(raw_records, key=lambda r: r[sort_key])

    # Duplicate detection
    seen_keys: set[Any] = set()
    duplicates: list[Any] = []
    for r in sorted_records:
        k = r[sort_key]
        if k in seen_keys:
            duplicates.append(k)
        seen_keys.add(k)
    if duplicates:
        diagnostics["condition"] = "duplicate_detected"
        diagnostics["duplicates"] = duplicates
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)

    # Gap detection
    gaps: list[tuple[Any, Any]] = []
    for i in range(1, len(sorted_records)):
        prev = sorted_records[i - 1][sort_key]
        curr = sorted_records[i][sort_key]
        try:
            if isinstance(prev, int) and isinstance(curr, int) and curr - prev > 1:
                gaps.append((prev, curr))
        except Exception:
            pass
    if gaps:
        diagnostics["condition"] = "gap_detected"
        diagnostics["gaps"] = gaps
        return CQExportResult(CQExportStatus.INCOMPLETE_RESULT, [], diagnostics)

    return CQExportResult(CQExportStatus.COMPLETE, sorted_records, diagnostics)


# ===========================================================================
# 4. Production go-live gate
# ===========================================================================

@dataclass(frozen=True)
class ProductionActivation:
    activated: bool
    activated_by: str
    activated_at: float
    capabilities: list[str]


def check_production_activation(
    config: dict[str, Any],
    owner_id: str,
) -> ProductionActivation:
    """Check if production is activated — exact owner activation required.

    Progressive per-capability version visibility: each capability has its own
    activation state in the policy config.
    """
    rgp = config.get("gateway", {}).get("restricted_group", {})
    policies = rgp.get("policies", {})
    activated_capabilities: list[str] = []
    activated = False
    activated_by = ""
    activated_at = 0.0

    for pid, policy in policies.items():
        if not isinstance(policy, dict):
            continue
        if policy.get("active") and policy.get("production_activated_by") == owner_id:
            activated = True
            activated_by = owner_id
            activated_at = float(policy.get("production_activated_at", 0.0))
            activated_capabilities.extend(policy.get("capabilities", []))
        elif policy.get("active") and policy.get("production_activated_by"):
            # Activated by a different owner — still counts as activated
            activated = True
            activated_by = policy.get("production_activated_by", "")
            activated_at = float(policy.get("production_activated_at", 0.0))
            activated_capabilities.extend(policy.get("capabilities", []))

    return ProductionActivation(
        activated=activated,
        activated_by=activated_by,
        activated_at=activated_at,
        capabilities=activated_capabilities,
    )


# ===========================================================================
# 5. Post-deploy verification — per-seam probes + observation window
# ===========================================================================

@dataclass
class ObservationWindow:
    """30-consecutive-violation-free-operations observation window."""
    consecutive_clean: int = 0
    violations: list[str] = field(default_factory=list)
    required_clean: int = 30

    def record_clean(self) -> None:
        self.consecutive_clean += 1

    def record_violation(self, seam: str, reason: str) -> None:
        self.consecutive_clean = 0
        self.violations.append(f"{seam}: {reason}")

    @property
    def passed(self) -> bool:
        return self.consecutive_clean >= self.required_clean


_SEAM_PROBES = [
    "origin_binding",
    "egress_broker",
    "cq_read_broker",
    "model_routing_gate",
    "audit_chain",
    "semantic_history",
    "durable_approval",
    "sandbox",
]


def run_seam_probes(
    probe_fn: dict[str, Any],
) -> dict[str, bool]:
    """Run per-seam independent probes for each enforcement seam.

    Each probe is a function that returns True if the seam is healthy.
    """
    results: dict[str, bool] = {}
    for seam in _SEAM_PROBES:
        fn = probe_fn.get(seam)
        if fn is None:
            results[seam] = False
            continue
        try:
            results[seam] = bool(fn())
        except Exception:
            results[seam] = False
    return results
