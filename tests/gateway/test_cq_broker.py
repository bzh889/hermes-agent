"""Unit tests for CQ Read Broker (ticket 30)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from gateway.cq_broker import (
    CQDecision,
    CQDenyReason,
    CQReadBroker,
    CQResult,
    get_cq_broker,
    reset_cq_broker,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET


@pytest.fixture(autouse=True)
def _isolate():
    saved = _ORIGIN_BINDING.get()
    saved_eng = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    reset_cq_broker()
    yield
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_eng
    reset_cq_broker()


def _mock_backend(**kw: Any) -> Any:
    op = kw.get("operation", "")
    return [{"id": 1, "operation": op, "data": "query result"}]


# ---------------------------------------------------------------------------
# Seven read operations — ALLOW
# ---------------------------------------------------------------------------

class TestReadOperations:
    @pytest.mark.parametrize("op", [
        "query", "page", "export", "search", "filter", "sort", "aggregate",
    ])
    def test_read_operation_allowed(self, op: str):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute(op)
        assert result.decision == CQDecision.ALLOW
        assert result.data is not None

    @pytest.mark.parametrize("op", [
        "Query", "PAGE", "Export", "SEARCH", "Filter", "SORT", "Aggregate",
    ])
    def test_case_insensitive(self, op: str):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute(op)
        assert result.decision == CQDecision.ALLOW

    def test_no_backend_returns_empty(self):
        broker = CQReadBroker()
        result = broker.execute("query")
        assert result.decision == CQDecision.ALLOW
        assert result.data == []


# ---------------------------------------------------------------------------
# Write operations — DENY
# ---------------------------------------------------------------------------

class TestWriteDenied:
    @pytest.mark.parametrize("op", [
        "insert", "update", "delete", "drop", "alter", "grant", "execute",
        "create", "truncate", "merge",
    ])
    def test_write_operation_denied(self, op: str):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute(op)
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.WRITE_OPERATION_BLOCKED.value

    def test_write_denied_before_backend_called(self):
        called = []
        def tracking_backend(**kw):
            called.append(kw)
            return []
        broker = CQReadBroker(cq_backend=tracking_backend)
        broker.execute("insert", table="test")
        assert called == []  # backend never called


# ---------------------------------------------------------------------------
# Raw query — DENY
# ---------------------------------------------------------------------------

class TestRawQueryDenied:
    def test_raw_query_denied(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("raw_query")
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.RAW_QUERY_DENIED.value

    def test_raw_denied(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("raw")
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.RAW_QUERY_DENIED.value


# ---------------------------------------------------------------------------
# Credential access — DENY
# ---------------------------------------------------------------------------

class TestCredentialAccessDenied:
    @pytest.mark.parametrize("op", [
        "get_credentials", "credentials", "auth", "token",
    ])
    def test_credential_access_denied(self, op: str):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute(op)
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.CREDENTIAL_ACCESS_DENIED.value

    def test_credential_marker_not_in_data(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("query")
        # Ensure the credential marker string doesn't leak into results
        assert broker.credential_marker not in str(result.data)


# ---------------------------------------------------------------------------
# Unknown operation — DENY
# ---------------------------------------------------------------------------

class TestUnknownOperation:
    def test_unknown_op_denied(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("frobnicate")
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.UNKNOWN_OPERATION.value


# ---------------------------------------------------------------------------
# Backend error — DENY
# ---------------------------------------------------------------------------

class TestBackendError:
    def test_backend_error_returns_deny(self):
        def error_backend(**kw):
            raise ConnectionError("CQ system down")
        broker = CQReadBroker(cq_backend=error_backend)
        result = broker.execute("query")
        assert result.decision == CQDecision.DENY
        assert result.reason == CQDenyReason.CQ_BACKEND_ERROR.value


# ---------------------------------------------------------------------------
# Integration — broker authenticates and returns without exposing credentials
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_broker_returns_query_results(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("query", table="cr_list")
        assert result.decision == CQDecision.ALLOW
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    def test_credentials_not_in_result(self):
        broker = CQReadBroker(cq_backend=_mock_backend)
        result = broker.execute("export", format="json")
        # The credential marker should never appear in returned data
        assert broker.credential_marker not in str(result)

    def test_singleton(self):
        a = get_cq_broker()
        b = get_cq_broker()
        assert a is b
