"""Unit tests for Durable Approval State (ticket 33)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import pytest

from gateway.durable_approval import (
    ApprovalError,
    ApprovalState,
    DuplicateDecisionError,
    DurableApprovalStore,
    DurableTask,
    get_approval_store,
    reset_approval_store,
)
from gateway.audit_chain import AuditRecord


@pytest.fixture
def store(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    s = DurableApprovalStore(db_path=tmp_path / "test_approval.db")
    try:
        yield s
    finally:
        s.close()
        reset_approval_store()


@pytest.fixture(autouse=True)
def _auto():
    reset_approval_store()
    yield
    reset_approval_store()


def _create_task(store, **kw):
    defaults = dict(
        conv_id="19:conv@thread.v2",
        policy_id="rgp-1",
        policy_revision="rev-1",
        operation_type="reply",
        content_fingerprint="sha256:abc",
        destination_fingerprint="sha256:xyz",
        requester_id="user-1",
    )
    defaults.update(kw)
    return store.request_approval(**defaults)


# ---------------------------------------------------------------------------

class TestRequestApproval:
    def test_task_created_pending(self, store):
        task = _create_task(store)
        assert task.state == ApprovalState.PENDING
        assert task.task_id.startswith("task-")

    def test_task_has_fingerprints_not_content(self, store):
        task = _create_task(store, content_fingerprint="sha256:secret")
        assert task.content_fingerprint == "sha256:secret"
        # No raw content field exists
        assert not hasattr(task, "content")

    def test_no_raw_content_in_db(self, store, tmp_path):
        secret = "SUPER_SECRET_12345"
        import hashlib
        fp = "sha256:" + hashlib.sha256(secret.encode()).hexdigest()
        _create_task(store, content_fingerprint=fp)
        # Scan DB for raw secret
        conn = sqlite3.connect(str(tmp_path / "test_approval.db"))
        rows = conn.execute("SELECT * FROM durable_tasks").fetchall()
        conn.close()
        for row in rows:
            for val in row:
                assert secret not in str(val)


# ---------------------------------------------------------------------------

class TestFirstWins:
    def test_first_decision_honored(self, store):
        task = _create_task(store)
        result = store.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        assert result.state == ApprovalState.APPROVED
        assert result.decided_by == "owner-1"

    def test_second_decision_rejected(self, store):
        task = _create_task(store)
        store.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        with pytest.raises(DuplicateDecisionError, match="already decided"):
            store.decide(task.task_id, ApprovalState.REJECTED, "owner-2")

    def test_reject_then_approve_rejected(self, store):
        task = _create_task(store)
        store.decide(task.task_id, ApprovalState.REJECTED, "owner-1")
        with pytest.raises(DuplicateDecisionError):
            store.decide(task.task_id, ApprovalState.APPROVED, "owner-2")


# ---------------------------------------------------------------------------

class TestRestartReconciliation:
    def test_approved_task_marked_completed_after_restart(self, store):
        task = _create_task(store)
        store.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        # Simulate restart — audit chain has matching outcome
        audit_records = [
            AuditRecord(
                seq=1, prev_hmac="0"*64, hmac="h1", phase="intent",
                decision="allow", reason="ok", operation_type="reply",
                destination_fingerprint="sha256:xyz",
                content_fingerprint=task.content_fingerprint,
                policy_id="rgp-1", policy_revision="rev-1",
                permit_id="p1", timestamp=0.0,
            ),
            AuditRecord(
                seq=2, prev_hmac="h1", hmac="h2", phase="outcome",
                decision="allow", reason="ok", operation_type="reply",
                destination_fingerprint="sha256:xyz",
                content_fingerprint=task.content_fingerprint,
                policy_id="rgp-1", policy_revision="rev-1",
                permit_id="p1", timestamp=0.0,
            ),
        ]
        updated = store.reconcile_from_audit(audit_records)
        assert len(updated) == 1
        assert updated[0].state == ApprovalState.COMPLETED

    def test_no_outcome_no_completion(self, store):
        task = _create_task(store)
        store.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        # No audit records — nothing completed
        updated = store.reconcile_from_audit([])
        assert len(updated) == 0


# ---------------------------------------------------------------------------

class TestGetPendingTasks:
    def test_list_pending(self, store):
        _create_task(store)
        _create_task(store, content_fingerprint="sha256:def")
        pending = store.get_pending_tasks()
        assert len(pending) == 2

    def test_no_pending_after_decision(self, store):
        task = _create_task(store)
        store.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        pending = store.get_pending_tasks()
        assert len(pending) == 0


# ---------------------------------------------------------------------------

class TestMetadataOnly:
    def test_all_fields_are_fingerprints_or_identity(self, store):
        task = _create_task(store)
        # Every field is either identity (str id) or fingerprint, never raw content
        for field_name in ("content_fingerprint", "destination_fingerprint"):
            val = getattr(task, field_name)
            if val:
                assert val.startswith("sha256:")


# ---------------------------------------------------------------------------

class TestInterruptedFlowResume:
    """Simulate interruption between approval and execution."""

    def test_resume_after_restart(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        db_path = tmp_path / "resume_test.db"

        # Session 1: request approval
        store1 = DurableApprovalStore(db_path=db_path)
        task = _create_task(store1)
        store1.decide(task.task_id, ApprovalState.APPROVED, "owner-1")
        store1.close()

        # Session 2: restart — verify task is still approved
        store2 = DurableApprovalStore(db_path=db_path)
        recovered = store2.get_task(task.task_id)
        assert recovered is not None
        assert recovered.state == ApprovalState.APPROVED
        # Second decision for same task → rejected
        with pytest.raises(DuplicateDecisionError):
            store2.decide(task.task_id, ApprovalState.REJECTED, "owner-2")
        store2.close()
