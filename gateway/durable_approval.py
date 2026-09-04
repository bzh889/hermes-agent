"""Durable approval state — metadata-only, first-wins, restart-safe resume.

Owner approval creates a metadata-only Durable Task: no raw sensitive content
is persisted, only fingerprints and metadata. First-wins: the first owner
decision is immutable; subsequent decisions for the same task are rejected.

On restart, the system reconciles by matching intent/outcome records from the
audit chain, not by replaying the approval flow.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


class ApprovalState(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    COMPLETED = "completed"


class ApprovalError(Exception):
    """Raised when an approval operation fails."""


class DuplicateDecisionError(ApprovalError):
    """Raised when a second decision is attempted on an already-decided task."""
    pass


@dataclass(frozen=True)
class DurableTask:
    """A metadata-only durable approval task.

    No raw sensitive content — only fingerprints and metadata.
    """
    task_id: str
    conv_id: str
    policy_id: str
    policy_revision: str
    operation_type: str
    content_fingerprint: str
    destination_fingerprint: str
    requester_id: str
    created_at: float
    state: ApprovalState = ApprovalState.PENDING
    decided_by: str = ""
    decided_at: float = 0.0
    decision_reason: str = ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS durable_tasks (
    task_id                TEXT PRIMARY KEY,
    conv_id                TEXT NOT NULL,
    policy_id              TEXT NOT NULL,
    policy_revision        TEXT NOT NULL,
    operation_type         TEXT NOT NULL,
    content_fingerprint    TEXT NOT NULL,
    destination_fingerprint TEXT NOT NULL DEFAULT '',
    requester_id           TEXT NOT NULL DEFAULT '',
    created_at             REAL NOT NULL,
    state                  TEXT NOT NULL DEFAULT 'pending',
    decided_by             TEXT NOT NULL DEFAULT '',
    decided_at             REAL NOT NULL DEFAULT 0,
    decision_reason        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_durable_conv ON durable_tasks(conv_id);
CREATE INDEX IF NOT EXISTS idx_durable_state ON durable_tasks(state);
"""


class DurableApprovalStore:
    """SQLite-backed store for durable approval tasks.

    Metadata-only — fingerprints and metadata, no raw content.
    First-wins — the first decision is immutable.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            d = get_hermes_home() / "approval"
            d.mkdir(parents=True, exist_ok=True)
            db_path = d / "durable_tasks.db"
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            str(db_path), timeout=10.0, isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        self._conn.executescript(_SCHEMA)

    def request_approval(
        self,
        conv_id: str,
        policy_id: str,
        policy_revision: str,
        operation_type: str,
        content_fingerprint: str,
        destination_fingerprint: str = "",
        requester_id: str = "",
    ) -> DurableTask:
        """Create a new pending approval task."""
        assert self._conn is not None
        task_id = f"task-{uuid.uuid4()}"
        created_at = time.time()
        self._conn.execute(
            """INSERT INTO durable_tasks
               (task_id, conv_id, policy_id, policy_revision, operation_type,
                content_fingerprint, destination_fingerprint, requester_id,
                created_at, state)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (task_id, conv_id, policy_id, policy_revision, operation_type,
             content_fingerprint, destination_fingerprint, requester_id,
             created_at),
        )
        return DurableTask(
            task_id=task_id, conv_id=conv_id, policy_id=policy_id,
            policy_revision=policy_revision, operation_type=operation_type,
            content_fingerprint=content_fingerprint,
            destination_fingerprint=destination_fingerprint,
            requester_id=requester_id, created_at=created_at,
        )

    def decide(
        self,
        task_id: str,
        decision: ApprovalState,
        decided_by: str,
        reason: str = "",
    ) -> DurableTask:
        """Record an owner decision — first-wins.

        Raises :class:`DuplicateDecisionError` if the task already has a
        non-pending decision.
        """
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM durable_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise ApprovalError(f"task {task_id} not found")
        current_state = ApprovalState(row["state"])
        if current_state != ApprovalState.PENDING:
            raise DuplicateDecisionError(
                f"task {task_id} already decided: {current_state.value}"
            )
        if decision not in (ApprovalState.APPROVED, ApprovalState.REJECTED):
            raise ApprovalError(f"invalid decision: {decision}")
        decided_at = time.time()
        self._conn.execute(
            """UPDATE durable_tasks
               SET state = ?, decided_by = ?, decided_at = ?, decision_reason = ?
               WHERE task_id = ?""",
            (decision.value, decided_by, decided_at, reason, task_id),
        )
        return DurableTask(
            task_id=row["task_id"], conv_id=row["conv_id"],
            policy_id=row["policy_id"], policy_revision=row["policy_revision"],
            operation_type=row["operation_type"],
            content_fingerprint=row["content_fingerprint"],
            destination_fingerprint=row["destination_fingerprint"],
            requester_id=row["requester_id"], created_at=row["created_at"],
            state=decision, decided_by=decided_by,
            decided_at=decided_at, decision_reason=reason,
        )

    def get_task(self, task_id: str) -> Optional[DurableTask]:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM durable_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def get_pending_tasks(self, conv_id: str = "") -> list[DurableTask]:
        assert self._conn is not None
        if conv_id:
            rows = self._conn.execute(
                "SELECT * FROM durable_tasks WHERE state = 'pending' AND conv_id = ? ORDER BY created_at",
                (conv_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM durable_tasks WHERE state = 'pending' ORDER BY created_at"
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def reconcile_from_audit(self, audit_records: list[Any]) -> list[DurableTask]:
        """Reconcile completed tasks by matching audit intent/outcome records.

        Marks approved tasks as completed if their intent has a matching
        outcome. Does NOT replay the approval flow.
        """
        assert self._conn is not None
        # Build permit → outcome mapping from audit records
        completed_permits: set[str] = set()
        permits_with_outcomes: set[str] = set()
        for r in audit_records:
            permit_id = getattr(r, "permit_id", "")
            phase = getattr(r, "phase", "")
            if not permit_id:
                continue
            if phase == "outcome":
                permits_with_outcomes.add(permit_id)

        # Mark approved tasks as completed
        updated: list[DurableTask] = []
        rows = self._conn.execute(
            "SELECT * FROM durable_tasks WHERE state = 'approved'"
        ).fetchall()
        for row in rows:
            task_id = row["task_id"]
            content_fp = row["content_fingerprint"]
            matching_outcomes = [
                r for r in audit_records
                if getattr(r, "phase", "") == "outcome"
                and getattr(r, "content_fingerprint", "") == content_fp
                and getattr(r, "decision", "") == "allow"
            ]
            if matching_outcomes:
                self._conn.execute(
                    "UPDATE durable_tasks SET state = ? WHERE task_id = ?",
                    (ApprovalState.COMPLETED.value, task_id),
                )
                # Re-read the updated row to get the new state
                updated_row = self._conn.execute(
                    "SELECT * FROM durable_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                updated.append(self._row_to_task(updated_row))
        return updated

    def _row_to_task(self, row: sqlite3.Row) -> DurableTask:
        return DurableTask(
            task_id=row["task_id"], conv_id=row["conv_id"],
            policy_id=row["policy_id"], policy_revision=row["policy_revision"],
            operation_type=row["operation_type"],
            content_fingerprint=row["content_fingerprint"],
            destination_fingerprint=row["destination_fingerprint"],
            requester_id=row["requester_id"], created_at=row["created_at"],
            state=ApprovalState(row["state"]),
            decided_by=row["decided_by"], decided_at=row["decided_at"],
            decision_reason=row["decision_reason"],
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[DurableApprovalStore] = None


def get_approval_store() -> DurableApprovalStore:
    global _store
    if _store is None:
        _store = DurableApprovalStore()
    return _store


def reset_approval_store() -> None:
    global _store
    if _store:
        _store.close()
    _store = None
