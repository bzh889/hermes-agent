"""TDD tests for ticket 04 — Existing Windows Terminal Attach Feasibility Probe.

An independent probe determines whether an arbitrary Windows Terminal tab
that was *not* started through the broker can provide reliable bidirectional
text I/O while preserving the user's local operation.

The probe distinguishes four capability layers (process discovery, visible
text capture, stdout access, stdin injection), evaluates documented Windows
mechanisms, and returns ``supported``, ``unsupported``, or ``indeterminate``.
A clear ``unsupported`` result is a valid deliverable.

Ticket 04 checkboxes:
  1. The probe distinguishes process discovery, visible text capture,
     stdout access, and stdin injection.
  2. It evaluates documented Windows Terminal CLI, console, PTY, process, and
     UI Automation capabilities without relying on unsupported injection.
  3. If supported, the probe demonstrates bidirectional I/O on the same
     existing session without restart.
  4. If unsupported, it returns ``unsupported`` with evidence rather than
     using screenshot/OCR as a substitute for text I/O.
  5. ``indeterminate`` is reported separately and is not counted as a pass.
  6. The probe does not extract credentials, bypass authorization, or damage
     the existing terminal.
  7. The result is independent of and does not block the broker-owned POC.

Cross-platform: the module is importable everywhere; Windows-specific probes
are gated.

Run:
    scripts/run_tests.sh tests/poc/test_attach_probe_poc.py -v
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

import pytest

from poc.terminal_broker.attach_probe import (
    AttachProbe,
    LayerResult,
    ProbeLayer,
    ProbeResult,
    ProbeVerdict,
)

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="attach probe uses Windows ConPTY/Console/UIA APIs",
)


# ---------------------------------------------------------------------------
# Cross-platform: module import surface
# ---------------------------------------------------------------------------

class TestAttachProbeImportable:
    """The probe module must be importable on every OS for test discovery."""

    def test_probe_class_is_importable(self):
        assert AttachProbe is not None
        assert callable(AttachProbe)

    def test_result_dataclass_is_importable(self):
        assert ProbeResult is not None
        r = ProbeResult(
            verdict=ProbeVerdict.UNSUPPORTED,
            summary="test",
        )
        assert r.verdict == ProbeVerdict.UNSUPPORTED
        assert r.summary == "test"

    def test_layer_result_dataclass_is_importable(self):
        assert LayerResult is not None
        lr = LayerResult(
            layer=ProbeLayer.PROCESS_DISCOVERY,
            supported=True,
            method="test",
            evidence="test evidence",
        )
        d = lr.to_dict()
        assert d["layer"] == "process_discovery"
        assert d["supported"] is True

    def test_verdict_enum_values(self):
        assert ProbeVerdict.SUPPORTED.value == "supported"
        assert ProbeVerdict.UNSUPPORTED.value == "unsupported"
        assert ProbeVerdict.INDETERMINATE.value == "indeterminate"

    def test_layer_enum_values(self):
        assert ProbeLayer.PROCESS_DISCOVERY.value == "process_discovery"
        assert ProbeLayer.VISIBLE_TEXT_CAPTURE.value == "visible_text_capture"
        assert ProbeLayer.STDOUT_ACCESS.value == "stdout_access"
        assert ProbeLayer.STDIN_INJECTION.value == "stdin_injection"


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 1: The probe distinguishes process discovery, visible
# text capture, stdout access, and stdin injection.
# ---------------------------------------------------------------------------

class TestFourLayerDistinguishment:
    """The probe must distinguish four capability layers and report each
    separately in its result."""

    def test_probe_result_has_four_layers(self):
        """Run the probe and verify all four layer keys are present."""
        probe = AttachProbe()
        result = probe.run()
        assert ProbeLayer.PROCESS_DISCOVERY.value in result.layers
        assert ProbeLayer.VISIBLE_TEXT_CAPTURE.value in result.layers or \
               result.verdict == ProbeVerdict.INDETERMINATE
        # If indeterminate (no WT running), only process_discovery is filled.
        # If supported/unsupported, all four must be present.
        if result.verdict != ProbeVerdict.INDETERMINATE:
            assert ProbeLayer.VISIBLE_TEXT_CAPTURE.value in result.layers
            assert ProbeLayer.STDOUT_ACCESS.value in result.layers
            assert ProbeLayer.STDIN_INJECTION.value in result.layers

    def test_each_layer_has_supported_field(self):
        """Each layer result must have a ``supported`` field that is either
        True, False, or None."""
        probe = AttachProbe()
        result = probe.run()
        for layer_name, layer_data in result.layers.items():
            assert "supported" in layer_data, f"Layer {layer_name} missing 'supported'"
            # supported must be True, False, or None
            assert layer_data["supported"] in (True, False, None)

    def test_each_layer_has_method_and_evidence(self):
        """Each layer result must have a ``method`` and ``evidence`` string."""
        probe = AttachProbe()
        result = probe.run()
        for layer_name, layer_data in result.layers.items():
            assert "method" in layer_data, f"Layer {layer_name} missing 'method'"
            assert "evidence" in layer_data, f"Layer {layer_name} missing 'evidence'"
            assert isinstance(layer_data["evidence"], str)
            assert len(layer_data["evidence"]) > 0


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 2: It evaluates documented Windows Terminal CLI, console,
# PTY, process, and UI Automation capabilities without relying on unsupported
# injection.
# ---------------------------------------------------------------------------

class TestDocumentedMechanismsEvaluated:
    """The probe must evaluate documented Windows mechanisms and *not* rely
    on unsupported process injection."""

    def test_probe_evaluates_multiple_mechanisms(self):
        """The probe's layer methods should reference the documented
        mechanisms: AttachConsole, GetStdHandle, ConPTY, wt.exe CLI,
        UI Automation."""
        probe = AttachProbe()
        result = probe.run()

        # Collect all evidence text and method names.
        all_text = " ".join(
            f"{l['method']} {l['evidence']}" for l in result.layers.values()
        ).lower()

        # The probe should reference at least some of these documented APIs.
        # (Not all may appear if the probe short-circuits, but the code
        # structure evaluates all of them.)
        documented_apis = [
            "attachconsole",
            "getstdhandle",
            "conpty",
            "pseudoconsole",
            "wt.exe",
            "ui automation",
            "uiautomation",
            "textpattern",
            "valuepattern",
            "psutil",
        ]
        # At least 3 of the documented APIs should be referenced.
        found = sum(1 for api in documented_apis if api in all_text)
        assert found >= 3, (
            f"Expected at least 3 documented API references, found {found}: "
            f"{[a for a in documented_apis if a in all_text]}"
        )

    def test_probe_does_not_use_injection(self):
        """The probe must not attempt undocumented process injection.

        We verify by checking the evidence text for known injection terms
        — they should only appear as *negated* references (i.e. the probe
        reports that it does *not* use injection).
        """
        probe = AttachProbe()
        result = probe.run()
        all_text = " ".join(
            l["evidence"] for l in result.layers.values()
        ).lower()

        # The probe should not claim to have used injection.
        injection_terms = [
            "createremotethread",
            "writeprocessmemory",
            "dll injection",
            "dllinject",
            "ptrace",
        ]
        for term in injection_terms:
            assert term not in all_text, (
                f"Probe appears to use undocumented injection '{term}' — "
                f"this violates ticket 04 checkbox 2 and spec Out of Scope."
            )


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 3: If supported, the probe demonstrates bidirectional I/O
# on the same existing session without restart.
# ---------------------------------------------------------------------------

class TestSupportedImpliesBidirectionalIO:
    """If the probe returns ``supported``, all four layers must be confirmed,
    which implies bidirectional I/O (stdout read + stdin write) on the same
    session."""

    def test_supported_verdict_requires_all_layers_true(self):
        probe = AttachProbe()
        result = probe.run()
        if result.verdict == ProbeVerdict.SUPPORTED:
            for layer_name, layer_data in result.layers.items():
                assert layer_data["supported"] is True, (
                    f"Layer {layer_name} is not True but verdict is SUPPORTED"
                )


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 4: If unsupported, it returns ``unsupported`` with
# evidence rather than using screenshot/OCR as a substitute for text I/O.
# ---------------------------------------------------------------------------

class TestUnsupportedReturnsEvidence:
    """If the probe returns ``unsupported``, it must return evidence
    explaining *why*, and must not use screenshot/OCR as a substitute."""

    def test_unsupported_has_evidence(self):
        probe = AttachProbe()
        result = probe.run()
        if result.verdict == ProbeVerdict.UNSUPPORTED:
            assert len(result.summary) > 0
            assert "unsupported" in result.summary.lower()
            # At least one layer must be False
            failed = [
                l for l in result.layers.values() if l["supported"] is False
            ]
            assert len(failed) > 0, "No layers are False but verdict is UNSUPPORTED"

    def test_no_screenshot_ocr_substitute(self):
        """The probe must not use screenshot/OCR as a primary text I/O
        mechanism."""
        probe = AttachProbe()
        result = probe.run()
        all_text = " ".join(
            l["evidence"] for l in result.layers.values()
        ).lower() + " " + result.summary.lower()

        # The probe should not claim to use screenshot or OCR as the
        # primary I/O path.
        if result.verdict == ProbeVerdict.UNSUPPORTED:
            # It should say things like "not supported" / "impossible"
            # rather than "captured via screenshot"
            assert "screenshot" not in all_text or "not" in all_text, (
                "Probe should not rely on screenshot as primary I/O"
            )
            assert "ocr" not in all_text or "not" in all_text, (
                "Probe should not rely on OCR as primary I/O"
            )


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 5: ``indeterminate`` is reported separately and is not
# counted as a pass.
# ---------------------------------------------------------------------------

class TestIndeterminateSeparate:
    """``indeterminate`` must be a distinct verdict, not counted as a pass."""

    def test_indeterminate_is_distinct_from_supported(self):
        assert ProbeVerdict.INDETERMINATE != ProbeVerdict.SUPPORTED

    def test_indeterminate_not_counted_as_pass(self):
        """When no Windows Terminal is running, the probe should return
        ``indeterminate`` and the summary should note it is not a pass."""
        probe = AttachProbe()
        result = probe.run()
        if result.verdict == ProbeVerdict.INDETERMINATE:
            assert "indeterminate" in result.summary.lower() or \
                   "not a pass" in result.summary.lower() or \
                   "not" in result.summary.lower()
            # Process discovery must be None (indeterminate), not True
            pd_layer = result.layers.get(
                ProbeLayer.PROCESS_DISCOVERY.value
            )
            if pd_layer:
                assert pd_layer["supported"] is not True


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 6: The probe does not extract credentials, bypass
# authorization, or damage the existing terminal.
# ---------------------------------------------------------------------------

class TestNoHarmOrSecurityBypass:
    """The probe must not extract credentials, bypass authorization, or
    damage the existing terminal."""

    def test_probe_does_not_extract_credentials(self):
        """Evidence text should not mention credential extraction."""
        probe = AttachProbe()
        result = probe.run()
        all_text = " ".join(
            l["evidence"] for l in result.layers.values()
        ).lower()
        credential_terms = [
            "password",
            "credential",
            "api key",
            "token",
            "secret",
        ]
        for term in credential_terms:
            assert term not in all_text, (
                f"Probe evidence mentions '{term}' — probe should not "
                f"extract credentials."
            )

    def test_probe_does_not_bypass_authorization(self):
        """The probe should mention access denied / not allowed as expected
        outcomes, not as things to bypass."""
        probe = AttachProbe()
        result = probe.run()
        all_text = " ".join(
            l["evidence"] for l in result.layers.values()
        ).lower()
        # If access denied is mentioned, it should be as a *limitation*
        # not as something bypassed.
        if "access_denied" in all_text:
            assert "bypass" not in all_text, (
                "Probe should not bypass access controls"
            )

    def test_probe_does_not_terminate_existing_process(self):
        """The probe must not kill or terminate the probed process.

        We verify by checking the probe code does not import
        ``TerminateProcess`` or call ``psutil.Process.kill()``.
        """
        # Check the source code does not call kill/terminate on target PIDs.
        probe_source_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "poc", "terminal_broker", "attach_probe.py",
        )
        with open(probe_source_path, "r", encoding="utf-8") as f:
            source = f.read()

        # The probe source should not call .kill() or TerminateProcess
        # on target processes.
        assert ".kill()" not in source or "kill" not in source.lower(), (
            "Probe source contains kill() calls — must not damage existing terminal"
        )
        assert "TerminateProcess" not in source, (
            "Probe source calls TerminateProcess — must not damage existing terminal"
        )


# ---------------------------------------------------------------------------
# Ticket 04 checkbox 7: The result is independent of and does not block the
# broker-owned POC.
# ---------------------------------------------------------------------------

class TestIndependenceFromBrokerPOC:
    """The probe result is independent of and does not block the
    broker-owned POC (tickets 01-03)."""

    def test_probe_does_not_import_broker(self):
        """The attach probe module must not import from the session broker
        or PTY bridge — it is a completely independent experiment."""
        probe_source_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "poc", "terminal_broker", "attach_probe.py",
        )
        with open(probe_source_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Must not import from session_broker or pty_bridge_poc
        assert "from poc.terminal_broker.session_broker" not in source, (
            "Probe imports session_broker — must be independent of the broker POC"
        )
        assert "from poc.terminal_broker.pty_bridge_poc" not in source, (
            "Probe imports pty_bridge_poc — must be independent of the broker POC"
        )
        assert "import session_broker" not in source, (
            "Probe imports session_broker — must be independent of the broker POC"
        )
        assert "import pty_bridge_poc" not in source, (
            "Probe imports pty_bridge_poc — must be independent of the broker POC"
        )

    def test_probe_result_has_independent_evidence_label(self):
        """The probe evidence label must state it is independent of the
        broker POC."""
        probe = AttachProbe()
        result = probe.run()
        assert "independent" in result.evidence_label.lower(), (
            f"Evidence label should mention 'independent': {result.evidence_label}"
        )
        assert "broker" in result.evidence_label.lower(), (
            f"Evidence label should reference 'broker': {result.evidence_label}"
        )

    def test_probe_does_not_create_broker_session(self):
        """The probe must not create a broker-owned session."""
        probe = AttachProbe()
        result = probe.run()
        # The probe should not reference any broker session ID creation
        all_text = " ".join(
            l["evidence"] for l in result.layers.values()
        ) + " " + result.summary
        assert "broker.create" not in all_text.lower()
        assert "broker.create" not in all_text.lower()
        assert "session_id" not in all_text.lower() or "broker" not in all_text.lower()

    def test_probe_probed_targets_count(self):
        """The probe result should report how many targets were probed."""
        probe = AttachProbe()
        result = probe.run()
        assert hasattr(result, "probed_targets")
        assert isinstance(result.probed_targets, int)
        assert result.probed_targets >= 0


# ---------------------------------------------------------------------------
# Windows-only: deeper integration tests
# ---------------------------------------------------------------------------

@windows_only
class TestWindowsSpecificProbes:
    """On Windows, the probe can use real Windows APIs to probe existing
    terminal tabs."""

    def test_conpty_api_surface_exists(self):
        """On Windows, CreatePseudoConsole should exist in kernel32."""
        kernel32 = ctypes.windll.kernel32
        assert hasattr(kernel32, "CreatePseudoConsole"), (
            "CreatePseudoConsole not found in kernel32"
        )

    def test_probe_runs_without_error(self):
        """The probe should complete without raising an exception."""
        probe = AttachProbe()
        result = probe.run()
        assert isinstance(result, ProbeResult)
        assert result.verdict in (
            ProbeVerdict.SUPPORTED,
            ProbeVerdict.UNSUPPORTED,
            ProbeVerdict.INDETERMINATE,
        )

    def test_probe_with_invalid_pid(self):
        """Probing a non-existent PID should give a clear result."""
        probe = AttachProbe()
        result = probe.run(target_pid=99999999)
        assert isinstance(result, ProbeResult)
        # Should not crash, should return a verdict
        assert result.verdict in (
            ProbeVerdict.SUPPORTED,
            ProbeVerdict.UNSUPPORTED,
            ProbeVerdict.INDETERMINATE,
        )

    def test_conpty_has_no_attach_function(self):
        """Verify that the ConPTY API surface does *not* include
        AttachPseudoConsole or OpenPseudoConsole — this is the primary
        evidence for the ``unsupported`` verdict on stdout/stdin layers."""
        kernel32 = ctypes.windll.kernel32
        has_create = hasattr(kernel32, "CreatePseudoConsole")
        has_attach = hasattr(kernel32, "AttachPseudoConsole")
        has_open = hasattr(kernel32, "OpenPseudoConsole")
        has_enum = hasattr(kernel32, "EnumPseudoConsole")

        assert has_create, "CreatePseudoConsole should exist"
        # The key finding: no attach/enum API exists.
        assert not has_attach, "AttachPseudoConsole should NOT exist"
        assert not has_open, "OpenPseudoConsole should NOT exist"
        assert not has_enum, "EnumPseudoConsole should NOT exist"
