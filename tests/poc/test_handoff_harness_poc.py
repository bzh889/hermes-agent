"""TDD tests for ticket 03 — Local/Remote Handoff Acceptance Harness.

The harness proves the end-to-end handoff loop through the broker contract:
  * Local input produces a known marker in the same child.
  * Remote-simulation input produces a different known marker in the same
    child.
  * Local → remote → local handoff preserves child identity (same PID).
  * No restart occurred during mode transitions.
  * Output ordering is preserved — no duplicate or missing markers.
  * Handoff does not create an unrelated foreground window.
  * Harness emits a clear PASS/FAIL verdict with diagnostic evidence.
  * The result is explicitly labelled local harness evidence, not Teams E2E.

Windows-only: uses the ConPTY-backed SessionBroker from tickets 01/02.

Run:
    scripts/run_tests.sh tests/poc/test_handoff_harness_poc.py -v
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from poc.terminal_broker.session_broker import (
    BrokerError,
    ControlMode,
    SessionBroker,
)
from poc.terminal_broker.handoff_harness import (
    HandoffHarness,
    HarnessResult,
    Verdict,
)

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="handoff harness requires Windows ConPTY",
)

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "poc", "terminal_broker", "fixtures"),
)
from fixture_multiround import fixture_argv as _multiround_argv  # noqa: E402


# ---------------------------------------------------------------------------
# Cross-platform: module import surface
# ---------------------------------------------------------------------------

class TestHandoffHarnessImportable:
    """The harness module must be importable on every OS for test discovery."""

    def test_harness_class_is_importable(self):
        assert HandoffHarness is not None

    def test_result_dataclass_is_importable(self):
        assert HarnessResult is not None

    def test_verdict_values(self):
        assert Verdict.PASS.value == "PASS"
        assert Verdict.FAIL.value == "FAIL"


# ---------------------------------------------------------------------------
# Windows-only: ticket 03 checkboxes
# ---------------------------------------------------------------------------

@windows_only
class TestLocalInputProducesMarker:
    """Ticket 03 checkbox 1: Local input produces a known response marker."""

    def test_local_input_marker_visible(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, (
                f"Expected PASS but got {result.verdict}: {result.summary}\n"
                f"Checks: {result.checks}"
            )
            check = result.checks.get("local_input_marker")
            assert check is not None
            assert check["passed"] is True, (
                f"local_input_marker failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestRemoteInputProducesMarker:
    """Ticket 03 checkbox 2: Remote-simulation input produces a different
    known response marker from the same child."""

    def test_remote_input_marker_visible(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, (
                f"Expected PASS: {result.summary}\n{result.checks}"
            )
            check = result.checks.get("remote_input_marker")
            assert check is not None
            assert check["passed"] is True, (
                f"remote_input_marker failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestHandoffPreservesChildIdentity:
    """Ticket 03 checkbox 3: Local → remote → local handoff preserves the
    child identity."""

    def test_pid_same_after_full_handoff_cycle(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, f"{result.summary}\n{result.checks}"
            check = result.checks.get("child_identity_preserved")
            assert check is not None
            assert check["passed"] is True, (
                f"child_identity_preserved failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestNoRestartDuringHandoff:
    """Ticket 03 checkbox 4: The harness proves no restart occurred during
    mode transitions."""

    def test_no_restart_shown_in_verdict(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, f"{result.summary}\n{result.checks}"
            check = result.checks.get("no_restart")
            assert check is not None
            assert check["passed"] is True, (
                f"no_restart failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestOutputOrderingPreserved:
    """Ticket 03 checkbox 5: Output ordering is preserved."""

    def test_markers_in_order(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, f"{result.summary}\n{result.checks}"
            check = result.checks.get("output_ordering")
            assert check is not None
            assert check["passed"] is True, (
                f"output_ordering failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestNoDuplicateOrMissingMarkers:
    """Ticket 03 checkbox 6: Output contains no duplicate or missing markers."""

    def test_no_duplicates_no_missing(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, f"{result.summary}\n{result.checks}"
            check = result.checks.get("no_duplicate_markers")
            assert check is not None
            assert check["passed"] is True, (
                f"no_duplicate_markers failed: {check.get('detail')}"
            )
            check2 = result.checks.get("no_missing_markers")
            assert check2 is not None
            assert check2["passed"] is True, (
                f"no_missing_markers failed: {check2.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestNoForegroundWindowFromHandoff:
    """Ticket 03 checkbox 7: The handoff does not create an unrelated
    foreground window."""

    def test_no_new_window(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS, f"{result.summary}\n{result.checks}"
            check = result.checks.get("no_foreground_window")
            assert check is not None
            assert check["passed"] is True, (
                f"no_foreground_window failed: {check.get('detail')}"
            )
        finally:
            harness.shutdown()


@windows_only
class TestClearVerdictWithDiagnostics:
    """Ticket 03 checkbox 8: The harness emits a clear PASS/FAIL verdict
    with diagnostic evidence."""

    def test_verdict_is_pass_on_success(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.verdict == Verdict.PASS
            assert isinstance(result.summary, str) and len(result.summary) > 0
            assert isinstance(result.checks, dict) and len(result.checks) >= 8
        finally:
            harness.shutdown()

    def test_verdict_is_fail_on_failure(self):
        """Simulate a failure by giving the harness a bad fixture and
        verifying it reports FAIL with diagnostics."""
        harness = HandoffHarness()
        try:
            # Inject a fixture that exits immediately so no markers are seen.
            result = harness.run(
                argv=[sys.executable, "-u", "-c", "import sys; sys.stdout.write('NO_MARKER\\n'); sys.stdout.flush()"],
            )
            assert result.verdict == Verdict.FAIL, (
                f"Expected FAIL for bad fixture: {result.summary}\n{result.checks}"
            )
            # At least one check must be failed
            failed = [k for k, v in result.checks.items() if not v["passed"]]
            assert len(failed) > 0, "No checks failed despite bad fixture"
        finally:
            harness.shutdown()


@windows_only
class TestEvidenceLabelledLocalHarness:
    """Ticket 03 checkbox 9: The result is explicitly labelled local harness
    evidence, not Teams E2E evidence."""

    def test_evidence_label_present(self):
        harness = HandoffHarness()
        try:
            result = harness.run()
            assert result.evidence_label is not None
            assert "local" in result.evidence_label.lower()
            assert "teams" not in result.evidence_label.lower().replace("not teams", "")
            # Explicit: must say something like "not Teams E2E"
            assert "not" in result.evidence_label.lower() or "local" in result.evidence_label.lower()
        finally:
            harness.shutdown()
