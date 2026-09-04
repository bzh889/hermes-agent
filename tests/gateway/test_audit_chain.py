"""Unit tests for the HMAC-SHA256-chained audit trail (ticket 27).

Covers the 4 acceptance criteria:

1. SQLite WAL audit DB under `get_hermes_home() / "audit" / "restricted_group.db"`
2. Append-only schema with HMAC-SHA256 chain (each record links to previous)
3. Intent phase before side effect, outcome phase after
4. Restart reconciliation: unmatched intents → `indeterminate`

Also covers: chain integrity, tamper detection, no raw content, fingerprint-only.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from gateway.audit_chain import (
    AuditChain,
    AuditRecord,
    _GENESIS_HMAC,
    _compute_hmac,
    _reset_hmac_key,
    content_fingerprint,
    destination_fingerprint,
    get_audit_chain,
    reset_audit_chain,
)
from hermes_constants import get_hermes_home


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_audit_db(tmp_path: Path, monkeypatch) -> AuditChain:
    """Create an AuditChain with a temp DB in an isolated HERMES_HOME."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _reset_hmac_key()
    chain = AuditChain(db_path=tmp_path / "test_audit.db")
    try:
        yield chain
    finally:
        chain.close()
        _reset_hmac_key()


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_audit_chain()
    _reset_hmac_key()
    yield
    reset_audit_chain()
    _reset_hmac_key()


def _fp(text: str) -> str:
    """Helper: content fingerprint."""
    return content_fingerprint(text)


# ---------------------------------------------------------------------------
# 1. SQLite WAL DB creation
# ---------------------------------------------------------------------------

class TestDBCreation:
    """Audit DB is created at the correct path in WAL mode."""

    def test_db_file_created(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        _reset_hmac_key()
        chain = AuditChain()
        db_path = tmp_path / "audit" / "restricted_group.db"
        assert db_path.exists()
        chain.close()

    def test_db_uses_wal_mode(self, tmp_audit_db: AuditChain):
        mode = tmp_audit_db._conn.execute("PRAGMA journal_mode").fetchone()
        # WAL might fall back to DELETE on some filesystems, but should be WAL
        # in a normal tmp_path.
        assert mode[0] in ("wal", "memory")

    def test_schema_created(self, tmp_audit_db: AuditChain):
        tables = tmp_audit_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert "audit_chain" in table_names

    def test_indexes_created(self, tmp_audit_db: AuditChain):
        indexes = tmp_audit_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {row[0] for row in indexes}
        assert "idx_audit_phase" in index_names
        assert "idx_audit_permit" in index_names
        assert "idx_audit_policy" in index_names


# ---------------------------------------------------------------------------
# 2. HMAC chain integrity
# ---------------------------------------------------------------------------

class TestChainIntegrity:
    """Each record's HMAC chains to the previous — verify_chain returns True."""

    def test_empty_chain_verifies(self, tmp_audit_db: AuditChain):
        assert tmp_audit_db.verify_chain() is True

    def test_single_record_chain_verifies(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv-1"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        assert tmp_audit_db.verify_chain() is True

    def test_multiple_records_chain_verifies(self, tmp_audit_db: AuditChain):
        for i in range(5):
            tmp_audit_db.append_intent(
                operation_type="reply",
                destination_fingerprint=destination_fingerprint(f"conv-{i}"),
                content_fingerprint=_fp(f"payload-{i}"),
                policy_id="rgp-1",
                policy_revision="rev-1",
                permit_id=f"permit-{i}",
            )
        assert tmp_audit_db.verify_chain() is True

    def test_first_record_prev_hmac_is_genesis(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        records = tmp_audit_db.get_all_records()
        assert len(records) == 1
        assert records[0].prev_hmac == _GENESIS_HMAC

    def test_second_record_prev_hmac_matches_first(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        records = tmp_audit_db.get_all_records()
        assert len(records) == 2
        assert records[1].prev_hmac == records[0].hmac


# ---------------------------------------------------------------------------
# 3. Tamper detection
# ---------------------------------------------------------------------------

class TestTamperDetection:
    """Modifying a record breaks the chain — verify_chain returns False."""

    def test_tampered_hmac_detected(self, tmp_audit_db: AuditChain, tmp_path: Path):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Tamper: directly modify the hmac in the DB
        tmp_audit_db._conn.execute(
            "UPDATE audit_chain SET hmac = 'tampered' WHERE seq = 1"
        )
        assert tmp_audit_db.verify_chain() is False

    def test_tampered_prev_hmac_detected(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Tamper: modify prev_hmac of the second record
        tmp_audit_db._conn.execute(
            "UPDATE audit_chain SET prev_hmac = 'wrong' WHERE seq = 2"
        )
        assert tmp_audit_db.verify_chain() is False

    def test_tampered_decision_detected(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Tamper: change the decision from 'allow' to 'deny'
        tmp_audit_db._conn.execute(
            "UPDATE audit_chain SET decision = 'deny' WHERE seq = 1"
        )
        assert tmp_audit_db.verify_chain() is False

    def test_tampered_content_fingerprint_detected(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("original"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Tamper: change the content_fingerprint
        tmp_audit_db._conn.execute(
            "UPDATE audit_chain SET content_fingerprint = 'sha256:fake' WHERE seq = 1"
        )
        assert tmp_audit_db.verify_chain() is False


# ---------------------------------------------------------------------------
# 4. Intent and outcome phases
# ---------------------------------------------------------------------------

class TestIntentOutcomePhases:
    """Intent is recorded before side effect, outcome after."""

    def test_intent_recorded_before_outcome(self, tmp_audit_db: AuditChain):
        intent = tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        outcome = tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        assert intent.phase == "intent"
        assert intent.decision == "allow"
        assert outcome.phase == "outcome"
        assert outcome.decision == "allow"
        assert intent.seq < outcome.seq

    def test_denied_permit_recorded(self, tmp_audit_db: AuditChain):
        denied = tmp_audit_db.append_denied(
            reason="delivery_purpose_denied",
            operation_type="reaction",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
        )
        assert denied.phase == "intent"
        assert denied.decision == "deny"
        assert denied.reason == "delivery_purpose_denied"

    def test_outcome_can_be_failure(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        outcome = tmp_audit_db.append_outcome(
            decision="deny",
            reason="adapter_error",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        assert outcome.decision == "deny"
        assert outcome.reason == "adapter_error"


# ---------------------------------------------------------------------------
# 5. No raw content — fingerprints only
# ---------------------------------------------------------------------------

class TestNoRawContent:
    """No raw prompts, CQ content, or credentials in any record."""

    def test_destination_is_fingerprinted(self, tmp_audit_db: AuditChain):
        raw_dest = "19:cbdcf6224c48469ea048147752ed92d9@thread.v2"
        fp = destination_fingerprint(raw_dest)
        record = tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=fp,
            content_fingerprint=_fp("payload"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        assert raw_dest not in record.destination_fingerprint
        assert record.destination_fingerprint.startswith("sha256:")

    def test_content_is_fingerprinted(self, tmp_audit_db: AuditChain):
        raw_content = "Sensitive message content with secrets"
        fp = content_fingerprint(raw_content)
        record = tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=fp,
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        assert raw_content not in record.content_fingerprint
        assert record.content_fingerprint.startswith("sha256:")

    def test_no_raw_content_in_db(self, tmp_audit_db: AuditChain, tmp_path: Path):
        """Scan the entire DB for a known raw content string."""
        secret = "TOP_SECRET_RAW_PASSWORD_123"
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=content_fingerprint(secret),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Dump the entire DB and search for the raw secret
        conn = sqlite3.connect(str(tmp_path / "test_audit.db"))
        all_rows = conn.execute("SELECT * FROM audit_chain").fetchall()
        conn.close()
        for row in all_rows:
            for value in row:
                assert secret not in str(value), f"Raw content found in DB: {value}"


# ---------------------------------------------------------------------------
# 6. Restart reconciliation — indeterminate
# ---------------------------------------------------------------------------

class TestRestartReconciliation:
    """Unmatched intent records are marked indeterminate on restart."""

    def test_matched_intent_not_marked_indeterminate(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        results = tmp_audit_db.reconcile_indeterminate()
        assert len(results) == 0  # matched — no indeterminate

    def test_unmatched_intent_marked_indeterminate(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Simulate restart: no outcome was written, reconcile
        results = tmp_audit_db.reconcile_indeterminate()
        assert len(results) == 1
        assert results[0].phase == "indeterminate"
        assert results[0].decision == "indeterminate"
        assert results[0].reason == "unmatched_intent_after_restart"
        assert results[0].permit_id == "permit-1"

    def test_multiple_unmatched_intents(self, tmp_audit_db: AuditChain):
        for i in range(3):
            tmp_audit_db.append_intent(
                operation_type="reply",
                destination_fingerprint=destination_fingerprint(f"conv-{i}"),
                content_fingerprint=_fp(f"p{i}"),
                policy_id="rgp-1",
                policy_revision="rev-1",
                permit_id=f"permit-{i}",
            )
        results = tmp_audit_db.reconcile_indeterminate()
        assert len(results) == 3
        for r in results:
            assert r.phase == "indeterminate"

    def test_partial_match_some_indeterminate(self, tmp_audit_db: AuditChain):
        # Intent 1 — matched
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        # Intent 2 — unmatched (simulated crash)
        tmp_audit_db.append_intent(
            operation_type="edit",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p2"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-2",
        )
        results = tmp_audit_db.reconcile_indeterminate()
        assert len(results) == 1
        assert results[0].permit_id == "permit-2"

    def test_denied_intents_not_reconciled(self, tmp_audit_db: AuditChain):
        """Denied intents (decision=deny) don't need an outcome."""
        tmp_audit_db.append_denied(
            reason="delivery_purpose_denied",
            operation_type="reaction",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
        )
        results = tmp_audit_db.reconcile_indeterminate()
        assert len(results) == 0

    def test_chain_intact_after_reconciliation(self, tmp_audit_db: AuditChain):
        tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("conv"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp-1",
            policy_revision="rev-1",
            permit_id="permit-1",
        )
        tmp_audit_db.reconcile_indeterminate()
        assert tmp_audit_db.verify_chain() is True


# ---------------------------------------------------------------------------
# 7. Append-only — no updates or deletes
# ---------------------------------------------------------------------------

class TestAppendOnly:
    """Records are append-only — no update/delete API surface."""

    def test_no_update_method_on_chain(self):
        assert not hasattr(AuditChain, "update_record")
        assert not hasattr(AuditChain, "delete_record")

    def test_seq_auto_increments(self, tmp_audit_db: AuditChain):
        r1 = tmp_audit_db.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("c"),
            content_fingerprint=_fp("p"),
            policy_id="rgp",
            policy_revision="r",
            permit_id="p1",
        )
        r2 = tmp_audit_db.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("c"),
            content_fingerprint=_fp("p"),
            policy_id="rgp",
            policy_revision="r",
            permit_id="p1",
        )
        assert r2.seq == r1.seq + 1


# ---------------------------------------------------------------------------
# 8. Singleton access
# ---------------------------------------------------------------------------

class TestSingleton:
    """get_audit_chain returns a process-scoped singleton."""

    def test_singleton_returns_same_instance(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        _reset_hmac_key()
        reset_audit_chain()
        a = get_audit_chain()
        b = get_audit_chain()
        assert a is b
        a.close()
        reset_audit_chain()
        _reset_hmac_key()


# ---------------------------------------------------------------------------
# 9. Fingerprint helpers
# ---------------------------------------------------------------------------

class TestFingerprintHelpers:
    """destination_fingerprint and content_fingerprint are deterministic."""

    def test_destination_fingerprint_deterministic(self):
        assert destination_fingerprint("conv-1") == destination_fingerprint("conv-1")

    def test_destination_fingerprint_different(self):
        assert destination_fingerprint("conv-1") != destination_fingerprint("conv-2")

    def test_content_fingerprint_deterministic(self):
        assert content_fingerprint("hello") == content_fingerprint("hello")

    def test_content_fingerprint_different(self):
        assert content_fingerprint("hello") != content_fingerprint("world")

    def test_empty_destination_sentinel(self):
        assert destination_fingerprint("") == "sha256:none"

    def test_none_content_sentinel(self):
        assert content_fingerprint(None) == "sha256:none"

    def test_dict_content_order_independent(self):
        pf1 = content_fingerprint({"a": 1, "b": 2})
        pf2 = content_fingerprint({"b": 2, "a": 1})
        assert pf1 == pf2


# ---------------------------------------------------------------------------
# 10. Cross-restart chain continuity
# ---------------------------------------------------------------------------

class TestCrossRestartContinuity:
    """The chain continues across a simulated restart (new connection)."""

    def test_chain_continues_after_reopen(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        _reset_hmac_key()
        db_path = tmp_path / "test_audit.db"

        # First session: write 2 records
        chain1 = AuditChain(db_path=db_path)
        chain1.append_intent(
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("c"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp",
            policy_revision="r",
            permit_id="p1",
        )
        chain1.append_outcome(
            decision="allow",
            reason="ok",
            operation_type="reply",
            destination_fingerprint=destination_fingerprint("c"),
            content_fingerprint=_fp("p1"),
            policy_id="rgp",
            policy_revision="r",
            permit_id="p1",
        )
        last_hmac = chain1.get_all_records()[-1].hmac
        chain1.close()

        # Second session: reopen and write another record
        _reset_hmac_key()  # re-derive key from same HERMES_HOME
        chain2 = AuditChain(db_path=db_path)
        chain2.append_intent(
            operation_type="edit",
            destination_fingerprint=destination_fingerprint("c2"),
            content_fingerprint=_fp("p2"),
            policy_id="rgp",
            policy_revision="r",
            permit_id="p2",
        )
        records = chain2.get_all_records()
        assert len(records) == 3
        # The third record's prev_hmac should match the second record's hmac
        assert records[2].prev_hmac == records[1].hmac
        # Chain should verify
        assert chain2.verify_chain() is True
        chain2.close()
        _reset_hmac_key()
