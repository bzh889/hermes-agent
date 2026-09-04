"""HMAC-SHA256-chained audit trail for Restricted Group Policy enforcement.

SQLite WAL database under ``get_hermes_home() / "audit" / "restricted_group.db"``.
Append-only, tamper-evident: each record's HMAC includes the previous record's
HMAC, so modifying any record breaks the chain.

Two phases per operation:
1. **Intent** — committed *before* any restricted side effect
2. **Outcome** — committed *after* the side effect (success or failure)

On restart, unmatched intent records (no corresponding outcome) are marked
``indeterminate``.

No raw content is stored — fingerprints only. The schema records:
sequence, prev_hmac, hmac, phase, decision, reason, operation_type,
destination_fingerprint, content_fingerprint, policy_revision, timestamp.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_chain (
    seq                    INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_hmac              TEXT NOT NULL DEFAULT '',
    hmac                   TEXT NOT NULL,
    phase                  TEXT NOT NULL,           -- 'intent' | 'outcome' | 'indeterminate'
    decision               TEXT NOT NULL,           -- 'allow' | 'deny' | 'indeterminate'
    reason                 TEXT NOT NULL DEFAULT '',
    operation_type         TEXT NOT NULL DEFAULT '',
    destination_fingerprint TEXT NOT NULL DEFAULT '',
    content_fingerprint    TEXT NOT NULL DEFAULT '',
    policy_id              TEXT NOT NULL DEFAULT '',
    policy_revision        TEXT NOT NULL DEFAULT '',
    permit_id              TEXT NOT NULL DEFAULT '',
    timestamp              REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_phase ON audit_chain(phase);
CREATE INDEX IF NOT EXISTS idx_audit_permit ON audit_chain(permit_id);
CREATE INDEX IF NOT EXISTS idx_audit_policy ON audit_chain(policy_id);
"""

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditRecord:
    """One record in the HMAC-chained audit trail."""

    seq: int
    prev_hmac: str
    hmac: str
    phase: str  # 'intent' | 'outcome' | 'indeterminate'
    decision: str  # 'allow' | 'deny' | 'indeterminate'
    reason: str
    operation_type: str
    destination_fingerprint: str
    content_fingerprint: str
    policy_id: str
    policy_revision: str
    permit_id: str
    timestamp: float


# ---------------------------------------------------------------------------
# HMAC chain computation
# ---------------------------------------------------------------------------

# Sentinel for the first record (no previous hmac)
_GENESIS_HMAC = "0000000000000000000000000000000000000000000000000000000000000000"

# HMAC key — in production this should be derived from a secret stored in
# the owner's .env. For now we use a per-profile static key derived from
# the HERMES_HOME path. Ticket 33 (durable approval) can upgrade this.
_HMAC_KEY: Optional[bytes] = None


def _get_hmac_key() -> bytes:
    """Return the HMAC key for the audit chain.

    Derived from the profile's HERMES_HOME path. In production this should
    be a proper secret; for now the key is deterministic per profile so the
    chain is verifiable across restarts within the same profile.
    """
    global _HMAC_KEY
    if _HMAC_KEY is not None:
        return _HMAC_KEY
    home = str(get_hermes_home())
    _HMAC_KEY = hashlib.sha256(home.encode("utf-8")).digest()
    return _HMAC_KEY


def _reset_hmac_key() -> None:
    """Reset the cached HMAC key — for testing."""
    global _HMAC_KEY
    _HMAC_KEY = None


def _compute_hmac(
    seq: int,
    prev_hmac: str,
    phase: str,
    decision: str,
    reason: str,
    operation_type: str,
    destination_fingerprint: str,
    content_fingerprint: str,
    policy_id: str,
    policy_revision: str,
    permit_id: str,
    timestamp: float,
) -> str:
    """Compute the HMAC-SHA256 for one audit record.

    The HMAC covers every field of the record plus the previous record's HMAC,
    forming a tamper-evident chain.
    """
    payload = json.dumps(
        {
            "seq": seq,
            "prev_hmac": prev_hmac,
            "phase": phase,
            "decision": decision,
            "reason": reason,
            "operation_type": operation_type,
            "destination_fingerprint": destination_fingerprint,
            "content_fingerprint": content_fingerprint,
            "policy_id": policy_id,
            "policy_revision": policy_revision,
            "permit_id": permit_id,
            "timestamp": timestamp,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(_get_hmac_key(), payload, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# AuditChain DB
# ---------------------------------------------------------------------------

class AuditChain:
    """SQLite WAL audit DB for Restricted Group Policy enforcement.

    Append-only, HMAC-SHA256-chained. Each record links to the previous
    record's HMAC, forming a tamper-evident chain.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            audit_dir = get_hermes_home() / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            db_path = audit_dir / "restricted_group.db"
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self) -> None:
        """Open the SQLite connection in WAL mode."""
        self._conn = sqlite3.connect(
            str(self._db_path),
            timeout=10.0,
            isolation_level=None,  # autocommit mode
        )
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass  # WAL not supported (e.g. NFS) — fall back to default
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA_SQL)

    def _get_last_hmac(self) -> str:
        """Return the HMAC of the last record in the chain (or genesis)."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT hmac FROM audit_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return _GENESIS_HMAC
        return row["hmac"]

    def _get_next_seq(self) -> int:
        """Return the next sequence number."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT MAX(seq) FROM audit_chain"
        ).fetchone()
        if row is None or row[0] is None:
            return 1
        return row[0] + 1

    def append(
        self,
        phase: str,
        decision: str,
        reason: str,
        operation_type: str,
        destination_fingerprint: str,
        content_fingerprint: str,
        policy_id: str,
        policy_revision: str,
        permit_id: str = "",
    ) -> AuditRecord:
        """Append a record to the audit chain.

        The HMAC is computed over the record fields plus the previous record's
        HMAC. Returns the created :class:`AuditRecord`.
        """
        assert self._conn is not None
        seq = self._get_next_seq()
        prev_hmac = self._get_last_hmac()
        timestamp = time.time()

        hmac_value = _compute_hmac(
            seq=seq,
            prev_hmac=prev_hmac,
            phase=phase,
            decision=decision,
            reason=reason,
            operation_type=operation_type,
            destination_fingerprint=destination_fingerprint,
            content_fingerprint=content_fingerprint,
            policy_id=policy_id,
            policy_revision=policy_revision,
            permit_id=permit_id,
            timestamp=timestamp,
        )

        self._conn.execute(
            """
            INSERT INTO audit_chain
                (seq, prev_hmac, hmac, phase, decision, reason,
                 operation_type, destination_fingerprint, content_fingerprint,
                 policy_id, policy_revision, permit_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq, prev_hmac, hmac_value, phase, decision, reason,
                operation_type, destination_fingerprint, content_fingerprint,
                policy_id, policy_revision, permit_id, timestamp,
            ),
        )
        return AuditRecord(
            seq=seq,
            prev_hmac=prev_hmac,
            hmac=hmac_value,
            phase=phase,
            decision=decision,
            reason=reason,
            operation_type=operation_type,
            destination_fingerprint=destination_fingerprint,
            content_fingerprint=content_fingerprint,
            policy_id=policy_id,
            policy_revision=policy_revision,
            permit_id=permit_id,
            timestamp=timestamp,
        )

    def append_intent(
        self,
        operation_type: str,
        destination_fingerprint: str,
        content_fingerprint: str,
        policy_id: str,
        policy_revision: str,
        permit_id: str = "",
    ) -> AuditRecord:
        """Record the intent phase (before side effect)."""
        return self.append(
            phase="intent",
            decision="allow",
            reason="permitted",
            operation_type=operation_type,
            destination_fingerprint=destination_fingerprint,
            content_fingerprint=content_fingerprint,
            policy_id=policy_id,
            policy_revision=policy_revision,
            permit_id=permit_id,
        )

    def append_outcome(
        self,
        decision: str,
        reason: str,
        operation_type: str,
        destination_fingerprint: str,
        content_fingerprint: str,
        policy_id: str,
        policy_revision: str,
        permit_id: str = "",
    ) -> AuditRecord:
        """Record the outcome phase (after side effect)."""
        return self.append(
            phase="outcome",
            decision=decision,
            reason=reason,
            operation_type=operation_type,
            destination_fingerprint=destination_fingerprint,
            content_fingerprint=content_fingerprint,
            policy_id=policy_id,
            policy_revision=policy_revision,
            permit_id=permit_id,
        )

    def append_denied(
        self,
        reason: str,
        operation_type: str,
        destination_fingerprint: str,
        content_fingerprint: str,
        policy_id: str,
        policy_revision: str,
    ) -> AuditRecord:
        """Record a denied permit request (intent phase, decision=deny)."""
        return self.append(
            phase="intent",
            decision="deny",
            reason=reason,
            operation_type=operation_type,
            destination_fingerprint=destination_fingerprint,
            content_fingerprint=content_fingerprint,
            policy_id=policy_id,
            policy_revision=policy_revision,
        )

    def get_all_records(self) -> list[AuditRecord]:
        """Return all records in sequence order."""
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM audit_chain ORDER BY seq ASC"
        ).fetchall()
        return [
            AuditRecord(
                seq=row["seq"],
                prev_hmac=row["prev_hmac"],
                hmac=row["hmac"],
                phase=row["phase"],
                decision=row["decision"],
                reason=row["reason"],
                operation_type=row["operation_type"],
                destination_fingerprint=row["destination_fingerprint"],
                content_fingerprint=row["content_fingerprint"],
                policy_id=row["policy_id"],
                policy_revision=row["policy_revision"],
                permit_id=row["permit_id"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def verify_chain(self) -> bool:
        """Verify the HMAC chain integrity.

        Returns ``True`` if every record's HMAC matches the recomputed value
        and the chain is unbroken. Returns ``False`` if any record is tampered.
        """
        records = self.get_all_records()
        prev_hmac = _GENESIS_HMAC
        for record in records:
            if record.prev_hmac != prev_hmac:
                return False
            expected_hmac = _compute_hmac(
                seq=record.seq,
                prev_hmac=record.prev_hmac,
                phase=record.phase,
                decision=record.decision,
                reason=record.reason,
                operation_type=record.operation_type,
                destination_fingerprint=record.destination_fingerprint,
                content_fingerprint=record.content_fingerprint,
                policy_id=record.policy_id,
                policy_revision=record.policy_revision,
                permit_id=record.permit_id,
                timestamp=record.timestamp,
            )
            if not hmac.compare_digest(record.hmac, expected_hmac):
                return False
            prev_hmac = record.hmac
        return True

    def reconcile_indeterminate(self) -> list[AuditRecord]:
        """Mark unmatched intent records as ``indeterminate``.

        An intent record is unmatched if no outcome record with the same
        ``permit_id`` exists. Called on restart.

        Returns the list of newly created indeterminate records.
        """
        assert self._conn is not None
        # Find intent records with no matching outcome
        unmatched = self._conn.execute(
            """
            SELECT * FROM audit_chain
            WHERE phase = 'intent'
              AND decision = 'allow'
              AND permit_id != ''
              AND permit_id NOT IN (
                  SELECT permit_id FROM audit_chain
                  WHERE phase = 'outcome'
              )
            ORDER BY seq ASC
            """,
        ).fetchall()

        results: list[AuditRecord] = []
        for row in unmatched:
            # Append an indeterminate outcome record
            record = self.append(
                phase="indeterminate",
                decision="indeterminate",
                reason="unmatched_intent_after_restart",
                operation_type=row["operation_type"],
                destination_fingerprint=row["destination_fingerprint"],
                content_fingerprint=row["content_fingerprint"],
                policy_id=row["policy_id"],
                policy_revision=row["policy_revision"],
                permit_id=row["permit_id"],
            )
            results.append(record)
        return results

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Fingerprint helpers (used by Egress Broker integration in ticket 28)
# ---------------------------------------------------------------------------

def destination_fingerprint(destination: str) -> str:
    """SHA-256 fingerprint of an outbound destination."""
    if not destination:
        return "sha256:none"
    return "sha256:" + hashlib.sha256(destination.encode("utf-8")).hexdigest()


def content_fingerprint(payload: Any) -> str:
    """SHA-256 fingerprint of outbound content."""
    if payload is None:
        return "sha256:none"
    if isinstance(payload, (str, bytes)):
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    else:
        try:
            data = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        except Exception:
            data = repr(payload).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_chain: Optional[AuditChain] = None


def get_audit_chain() -> AuditChain:
    """Return the process-scoped AuditChain singleton."""
    global _chain
    if _chain is None:
        _chain = AuditChain()
    return _chain


def reset_audit_chain() -> None:
    """Reset the singleton — for testing only."""
    global _chain
    if _chain is not None:
        _chain.close()
    _chain = None
