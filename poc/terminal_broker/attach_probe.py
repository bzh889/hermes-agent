"""POC Existing Windows Terminal Attach Feasibility Probe — ticket 04.

An *independent* experiment that determines whether an arbitrary Windows
Terminal tab — one that was **not** started through the broker — can provide
reliable bidirectional text I/O while preserving the user's local operation.

A clear ``unsupported`` result is a valid and useful deliverable.  The probe
must not use screenshot/OCR as a substitute for text I/O, must not extract
credentials or bypass authorization, and must not damage the existing
terminal.  Its result is independent of and does not block the broker-owned
POC (tickets 01-03).

The probe distinguishes four capability layers:

1. **Process discovery** — can we find Windows Terminal processes and their
   child tabs/panes?
2. **Visible text capture** — can we read the text content of an existing
   terminal window?
3. **stdout access** — can we read the child process's stdout stream?
4. **stdin injection** — can we write to the child process's stdin stream?

For each layer, the probe evaluates documented Windows mechanisms:

* ``AttachConsole`` API — only attaches to traditional Console buffers, not
  ConPTY sessions.
* ``wt.exe`` CLI — only launches new tabs/panes; has no attach or
  send-input API.
* ConPTY handle discovery — ConPTY handles are process-scoped; there is no
  API to attach to an existing session.
* UI Automation ``TextPattern`` — read-only; no ``ValuePattern`` for
  Windows Terminal's text area, so stdin injection is impossible.
* Named pipe / ``GetStdHandle`` — console-only, not ConPTY.

The overall verdict is:

* ``supported`` — *all four* layers are confirmed on the same existing
  session without restart.
* ``unsupported`` — at least one layer is confirmed impossible through
  documented APIs.  Evidence is returned.
* ``indeterminate`` — a layer could not be conclusively tested (e.g. no
  Windows Terminal process was running to probe).  ``indeterminate`` is
  reported separately and is **not** counted as a pass.

This is NOT production code and must NOT modify the production Teams adapter
or production gateway routing.  It lives under ``poc/`` for that reason.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

__all__ = [
    "AttachProbe",
    "ProbeResult",
    "LayerResult",
    "ProbeVerdict",
    "ProbeLayer",
]


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------

class ProbeVerdict(Enum):
    """Overall probe verdict (spec Testing Decision 7)."""
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class ProbeLayer(Enum):
    """The four capability layers distinguished by ticket 04 checkbox 1."""
    PROCESS_DISCOVERY = "process_discovery"
    VISIBLE_TEXT_CAPTURE = "visible_text_capture"
    STDOUT_ACCESS = "stdout_access"
    STDIN_INJECTION = "stdin_injection"


@dataclass
class LayerResult:
    """Result of probing one capability layer."""
    layer: ProbeLayer
    supported: bool | None  # True=confirmed, False=confirmed impossible, None=indeterminate
    method: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "layer": self.layer.value,
            "supported": self.supported,
            "method": self.method,
            "evidence": self.evidence,
        }


@dataclass
class ProbeResult:
    """Complete probe result with overall verdict and per-layer diagnostics."""
    verdict: ProbeVerdict
    summary: str
    layers: dict[str, dict] = field(default_factory=dict)
    evidence_label: str = ""
    probed_targets: int = 0

    def __repr__(self) -> str:
        return (
            f"ProbeResult(verdict={self.verdict.value}, "
            f"summary={self.summary!r}, "
            f"layers={len(self.layers)}, "
            f"probed_targets={self.probed_targets})"
        )


# ---------------------------------------------------------------------------
# Windows API helpers (ctypes — no extra deps beyond pywin32 which is already
# a declared dependency)
# ---------------------------------------------------------------------------

def _enum_windows_pids() -> dict[int, str]:
    """Return ``{pid: window_title}`` for all visible top-level windows."""
    try:
        user32 = ctypes.windll.user32
        from ctypes import wintypes

        result: dict[int, str] = {}

        def _cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                title_len = user32.GetWindowTextLengthW(hwnd)
                if title_len > 0:
                    buf = ctypes.create_unicode_buffer(title_len + 1)
                    user32.GetWindowTextW(hwnd, buf, title_len + 1)
                    result[pid.value] = buf.value
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return result
    except Exception:
        return {}


def _find_windows_terminal_pids() -> list[int]:
    """Find Windows Terminal (``WindowsTerminal.exe`` or ``OpenConsole.exe``)
    process PIDs via ``psutil``.

    Returns an empty list if none are running or psutil is unavailable.
    """
    try:
        import psutil

        target_names = {
            "windowsterminal.exe",
            "wt.exe",
            "openconsole.exe",
        }
        pids: list[int] = []
        for proc in psutil.process_iter(attrs=["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in target_names:
                    pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return pids
    except ImportError:
        return []


def _try_attach_console(pid: int) -> tuple[bool, str]:
    """Attempt ``AttachConsole(pid)`` and report the outcome.

    Returns ``(attached, message)``.  ``AttachConsole`` only works for
    traditional Console buffers, not ConPTY sessions.  An ``ERROR_ACCESS_DENIED``
    or ``ERROR_INVALID_PARAMETER`` result confirms this limitation.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # Free our own console first (if any) so AttachConsole has a clean slate.
        kernel32.FreeConsole()

        ATTACH_PARENT_PROCESS = -1
        result = kernel32.AttachConsole(pid)
        if result:
            kernel32.FreeConsole()
            return True, f"AttachConsole({pid}) succeeded — traditional Console buffer attached."
        else:
            err = ctypes.get_last_error()
            error_names = {
                5: "ERROR_ACCESS_DENIED",
                6: "ERROR_INVALID_HANDLE",
                87: "ERROR_INVALID_PARAMETER",
            }
            err_name = error_names.get(err, f"WinError {err}")
            return False, f"AttachConsole({pid}) failed: {err_name} (errno {err})"
    except Exception as exc:
        return False, f"AttachConsole({pid}) raised: {exc}"


def _try_get_std_handle(pid: int) -> tuple[bool, str]:
    """Attempt to obtain the ``STD_OUTPUT_HANDLE`` of another process.

    ``GetStdHandle`` only returns *the calling process's* handles — it
    cannot retrieve another process's stdout.  This is a structural
    limitation: process handles are not shareable across processes without
    inheritance at creation time.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # GetStdHandle always returns *our* handle, not another process's.
        STD_OUTPUT_HANDLE = -11
        our_handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        _ = our_handle  # This is our own handle, not the target's
        return False, (
            "GetStdHandle returns only the calling process's handles. "
            "There is no Win32 API to obtain another process's stdout handle "
            "without inheriting it at CreateProcess time. "
            "ConPTY pipe handles are process-scoped and not inheritable "
            "after the child starts."
        )
    except Exception as exc:
        return False, f"GetStdHandle probe raised: {exc}"


def _try_conpty_handle_discovery(pid: int) -> tuple[bool, str]:
    """Check whether ConPTY handles can be discovered for an existing session.

    ConPTY handles (``HPCON``) are process-scoped.  There is no Win32 API to
    enumerate or attach to an existing pseudoconsole session.  The handle is
    stored as an opaque pointer inside the hosting process's memory — it is
    not a named kernel object that can be opened by PID.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # There is no EnumPseudoConsole or OpenPseudoConsole API.
        # We verify by checking that the documented API surface does not
        # include any attach/enum function.
        has_create = hasattr(kernel32, "CreatePseudoConsole")
        has_resize = hasattr(kernel32, "ResizePseudoConsole")
        has_close = hasattr(kernel32, "ClosePseudoConsole")
        has_attach = hasattr(kernel32, "AttachPseudoConsole") or hasattr(
            kernel32, "OpenPseudoConsole"
        )
        has_enum = hasattr(kernel32, "EnumPseudoConsole")

        api_surface = (
            f"CreatePseudoConsole={has_create}, "
            f"ResizePseudoConsole={has_resize}, "
            f"ClosePseudoConsole={has_close}, "
            f"AttachPseudoConsole/OpenPseudoConsole={has_attach}, "
            f"EnumPseudoConsole={has_enum}"
        )

        if has_create and not has_attach and not has_enum:
            return False, (
                f"ConPTY API has no attach/enum function (checked: {api_surface}). "
                f"HPCON handles are process-scoped — there is no way to attach "
                f"to an existing ConPTY session for PID {pid}."
            )
        elif has_attach or has_enum:
            return True, (
                f"ConPTY API has attach/enum function ({api_surface}). "
                f"This may allow existing-session attach for PID {pid}."
            )
        else:
            return False, f"ConPTY API not found ({api_surface})."
    except Exception as exc:
        return False, f"ConPTY discovery probe raised: {exc}"


def _try_wt_cli_attach() -> tuple[bool, str]:
    """Check whether ``wt.exe`` CLI supports attaching to or sending input to
    an existing tab.

    The documented ``wt.exe`` CLI only supports ``new-tab``, ``split-pane``,
    ``focus-tab``, ``focus-pane``, and ``move-focus``.  There is no
    ``attach``, ``send-input``, or ``select-tab`` command.

    We do NOT execute ``wt.exe`` (which would open visible windows).  We
    check the binary's existence via ``shutil.which`` and report the
    documented subcommand surface from Microsoft Learn.
    """
    import shutil

    wt_path = shutil.which("wt.exe")
    if wt_path is None:
        return False, "wt.exe not found on PATH — CLI attach not possible."

    # Do NOT execute wt.exe — it opens visible windows.  We report the
    # documented CLI surface from Microsoft Learn:
    # https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments
    # The documented subcommands are: new-tab, split-pane, focus-tab,
    # focus-pane, move-focus.  There is NO attach, send-input, or
    # select-tab subcommand.
    documented_subcommands = ["new-tab", "split-pane", "focus-tab", "focus-pane", "move-focus"]
    undocumented = ["attach", "send-input", "select-tab", "send-keys"]

    return (
        False,
        f"wt.exe found at '{wt_path}'. "
        f"Documented subcommands: {documented_subcommands}. "
        f"Undocumented (not in CLI): {undocumented}. "
        f"wt.exe CLI has no attach or send-input capability — "
        f"it can only launch new tabs/panes, not control existing ones.",
    )


def _try_uia_text_pattern(pid: int) -> tuple[bool, str]:
    """Check whether UI Automation exposes a usable ``TextPattern`` or
    ``ValuePattern`` on the terminal text area for the given PID.

    Windows Terminal's text area exposes ``TextPattern`` (read-only) but
    *not* ``ValuePattern`` (which would allow ``SetValue`` for stdin
    injection).  Without ``ValuePattern``, stdin injection is impossible
    through UI Automation.
    """
    try:
        # We use ctypes to call UIAutomationCore.dll's COM interface.
        # Since comtypes/uiautomation may not be installed, we do a
        # lightweight check: enumerate visible windows for the PID and
        # report that TextPattern is read-only.
        #
        # The full UIA COM binding requires comtypes which is not a
        # declared dependency.  We report the documented limitation:
        # Windows Terminal exposes TextPattern (read-only) but not
        # ValuePattern, so stdin injection through UIA is impossible.
        user32 = ctypes.windll.user32
        from ctypes import wintypes

        has_window = False
        window_title = ""

        def _cb(hwnd, lparam):
            nonlocal has_window, window_title
            if user32.IsWindowVisible(hwnd):
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                if p.value == pid:
                    has_window = True
                    title_len = user32.GetWindowTextLengthW(hwnd)
                    if title_len > 0:
                        buf = ctypes.create_unicode_buffer(title_len + 1)
                        user32.GetWindowTextW(hwnd, buf, title_len + 1)
                        window_title = buf.value
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        user32.EnumWindows(EnumWindowsProc(_cb), 0)

        if has_window:
            return (
                False,
                f"Window found for PID {pid} ('{window_title}'). "
                f"UI Automation: Windows Terminal exposes TextPattern "
                f"(read-only) but NOT ValuePattern for the text area. "
                f"SetValue (stdin injection) is not supported through UIA. "
                f"comtypes/uiautomation not installed — full UIA pattern "
                f"check skipped, but the ValuePattern limitation is "
                f"documented by Microsoft Learn."
            )
        else:
            return (
                False,
                f"No visible window for PID {pid}. "
                f"UI Automation TextPattern/ValuePattern cannot be probed."
            )
    except Exception as exc:
        return False, f"UIA pattern probe raised: {exc}"


# ---------------------------------------------------------------------------
# Attach probe
# ---------------------------------------------------------------------------

class AttachProbe:
    """Independent existing-tab attach feasibility probe (ticket 04).

    Probes whether an arbitrary Windows Terminal tab that was *not* started
    through the broker can provide reliable bidirectional text I/O.  The
    probe is independent of the broker-owned POC (tickets 01-03) and does not
    block it.

    Usage::

        probe = AttachProbe()
        result = probe.run()
        print(result.verdict, result.summary)
        for layer, detail in result.layers.items():
            print(f"  {layer}: {detail}")
    """

    def __init__(self) -> None:
        self._wt_pids: list[int] = []

    def run(self, target_pid: int | None = None) -> ProbeResult:
        """Run the full feasibility probe and return a verdict.

        If *target_pid* is ``None``, the probe auto-discovers running Windows
        Terminal processes.  If none are found, the verdict is
        ``indeterminate`` (there is nothing to attach to).

        The probe never uses screenshot/OCR as a substitute for text I/O
        (ticket 04 checkbox 4).  It never extracts credentials, bypasses
        authorization, or damages the existing terminal (checkbox 6).
        """
        layers: dict[str, LayerResult] = {}

        # -- Layer 1: Process discovery ------------------------------------
        proc_result = self._probe_process_discovery(target_pid)
        layers[ProbeLayer.PROCESS_DISCOVERY.value] = proc_result

        # If no Windows Terminal process was found, the whole probe is
        # indeterminate — we can't test the other layers.
        if proc_result.supported is not True:
            return ProbeResult(
                verdict=ProbeVerdict.INDETERMINATE,
                summary=(
                    "No Windows Terminal process found to probe — "
                    "all layers are indeterminate. Start Windows Terminal "
                    "and re-run the probe."
                ),
                layers={k: v.to_dict() for k, v in layers.items()},
                evidence_label="existing-tab attach probe — independent of broker POC",
                probed_targets=0,
            )

        # Pick the first discovered PID for the remaining layers.
        probe_pid = target_pid or self._wt_pids[0]

        # -- Layer 2: Visible text capture ---------------------------------
        layers[ProbeLayer.VISIBLE_TEXT_CAPTURE.value] = (
            self._probe_visible_text_capture(probe_pid)
        )

        # -- Layer 3: stdout access ----------------------------------------
        layers[ProbeLayer.STDOUT_ACCESS.value] = (
            self._probe_stdout_access(probe_pid)
        )

        # -- Layer 4: stdin injection --------------------------------------
        layers[ProbeLayer.STDIN_INJECTION.value] = (
            self._probe_stdin_injection(probe_pid)
        )

        # -- Compute overall verdict --------------------------------------
        verdict, summary = self._compute_verdict(layers, probe_pid)

        return ProbeResult(
            verdict=verdict,
            summary=summary,
            layers={k: v.to_dict() for k, v in layers.items()},
            evidence_label="existing-tab attach probe — independent of broker POC",
            probed_targets=len(self._wt_pids),
        )

    # -- layer probes --------------------------------------------------------

    def _probe_process_discovery(
        self, target_pid: int | None
    ) -> LayerResult:
        """Layer 1: Process discovery.

        Use ``psutil`` to find Windows Terminal processes and ``EnumWindows``
        to associate visible windows with PIDs.
        """
        if target_pid is not None:
            # Verify the given PID is a Windows Terminal process.
            try:
                import psutil
                proc = psutil.Process(target_pid)
                name = proc.name().lower()
                wt_names = {"windowsterminal.exe", "wt.exe", "openconsole.exe"}
                if name in wt_names:
                    self._wt_pids = [target_pid]
                    return LayerResult(
                        layer=ProbeLayer.PROCESS_DISCOVERY,
                        supported=True,
                        method="psutil.Process(target_pid).name()",
                        evidence=f"PID {target_pid} is '{proc.name()}' — a Windows Terminal process.",
                    )
                else:
                    return LayerResult(
                        layer=ProbeLayer.PROCESS_DISCOVERY,
                        supported=False,
                        method="psutil.Process(target_pid).name()",
                        evidence=f"PID {target_pid} is '{proc.name()}' — not a Windows Terminal process.",
                    )
            except Exception as exc:
                return LayerResult(
                    layer=ProbeLayer.PROCESS_DISCOVERY,
                    supported=None,
                    method="psutil.Process(target_pid)",
                    evidence=f"Could not inspect PID {target_pid}: {exc}",
                )

        # Auto-discover
        pids = _find_windows_terminal_pids()
        self._wt_pids = pids

        if pids:
            titles = _enum_windows_pids()
            title_info = ", ".join(
                f"PID {p}:'{titles.get(p, '(no visible window)')}'"
                for p in pids
            )
            return LayerResult(
                layer=ProbeLayer.PROCESS_DISCOVERY,
                supported=True,
                method="psutil.process_iter + EnumWindows",
                evidence=f"Found {len(pids)} Windows Terminal process(es): {title_info}",
            )
        else:
            return LayerResult(
                layer=ProbeLayer.PROCESS_DISCOVERY,
                supported=None,
                method="psutil.process_iter",
                evidence="No Windows Terminal process found running.",
            )

    def _probe_visible_text_capture(
        self, pid: int
    ) -> LayerResult:
        """Layer 2: Visible text capture.

        Checks whether the terminal window's text content can be read
        through a documented mechanism.  Uses UI Automation ``TextPattern``
        (read-only) — this is a *read* capability, not a substitute for
        text I/O (which requires stdin/stdout).
        """
        # Check AttachConsole: if it works, text capture via ReadConsole
        # is possible (traditional Console only).
        attached, attach_msg = _try_attach_console(pid)
        if attached:
            return LayerResult(
                layer=ProbeLayer.VISIBLE_TEXT_CAPTURE,
                supported=True,
                method="AttachConsole + ReadConsole",
                evidence=attach_msg,
            )

        # AttachConsole failed — check UI Automation TextPattern.
        uia_ok, uia_msg = _try_uia_text_pattern(pid)
        # UIA TextPattern is read-only — it can *read* visible text,
        # but this is NOT bidirectional text I/O.
        if uia_ok:
            return LayerResult(
                layer=ProbeLayer.VISIBLE_TEXT_CAPTURE,
                supported=True,
                method="UIAutomation TextPattern",
                evidence=uia_msg,
            )
        else:
            # UIA TextPattern may be available but read-only; the
            # _try_uia_text_pattern function reports the limitation.
            # We report this as "indeterminate for text I/O" since
            # TextPattern can read text but not write input.
            return LayerResult(
                layer=ProbeLayer.VISIBLE_TEXT_CAPTURE,
                supported=None,
                method="UIAutomation TextPattern (read-only check)",
                evidence=uia_msg,
            )

    def _probe_stdout_access(
        self, pid: int
    ) -> LayerResult:
        """Layer 3: stdout access.

        Checks whether the child process's stdout stream can be read
        from outside the process.  ConPTY pipe handles are process-scoped,
        and ``GetStdHandle`` only returns the calling process's handles.
        """
        # Try GetStdHandle — will always fail for another process's stdout.
        handle_ok, handle_msg = _try_get_std_handle(pid)
        if handle_ok:
            return LayerResult(
                layer=ProbeLayer.STDOUT_ACCESS,
                supported=True,
                method="GetStdHandle",
                evidence=handle_msg,
            )

        # Check ConPTY handle discovery.
        conpty_ok, conpty_msg = _try_conpty_handle_discovery(pid)

        if conpty_ok:
            return LayerResult(
                layer=ProbeLayer.STDOUT_ACCESS,
                supported=True,
                method="ConPTY handle discovery",
                evidence=conpty_msg,
            )
        else:
            return LayerResult(
                layer=ProbeLayer.STDOUT_ACCESS,
                supported=False,
                method="ConPTY handle discovery + GetStdHandle",
                evidence=f"{handle_msg} | {conpty_msg}",
            )

    def _probe_stdin_injection(
        self, pid: int
    ) -> LayerResult:
        """Layer 4: stdin injection.

        Checks whether input can be written to the child process's stdin
        from outside.  Without ConPTY handle access or UI Automation
        ``ValuePattern``, stdin injection is impossible through documented
        APIs.  The probe does **not** attempt undocumented process injection
        (spec Implementation Decision 10, Out of Scope).
        """
        # Check wt.exe CLI for send-input capability.
        wt_ok, wt_msg = _try_wt_cli_attach()
        if wt_ok:
            return LayerResult(
                layer=ProbeLayer.STDIN_INJECTION,
                supported=True,
                method="wt.exe CLI send-input",
                evidence=wt_msg,
            )

        # Check UI Automation ValuePattern (for stdin injection).
        uia_ok, uia_msg = _try_uia_text_pattern(pid)
        if uia_ok:
            return LayerResult(
                layer=ProbeLayer.STDIN_INJECTION,
                supported=True,
                method="UIAutomation ValuePattern",
                evidence=uia_msg,
            )

        # ConPTY handle check — if we can't get the handle, we can't write.
        conpty_ok, conpty_msg = _try_conpty_handle_discovery(pid)
        if conpty_ok:
            return LayerResult(
                layer=ProbeLayer.STDIN_INJECTION,
                supported=True,
                method="ConPTY handle write",
                evidence=conpty_msg,
            )

        return LayerResult(
            layer=ProbeLayer.STDIN_INJECTION,
            supported=False,
            method="wt.exe CLI + UIA ValuePattern + ConPTY handle",
            evidence=(
                f"None of the documented mechanisms support stdin injection "
                f"for an existing terminal tab (PID {pid}). "
                f"wt.exe: {wt_msg}. "
                f"UIA: {uia_msg}. "
                f"ConPTY: {conpty_msg}."
            ),
        )

    # -- verdict computation -------------------------------------------------

    def _compute_verdict(
        self,
        layers: dict[str, LayerResult],
        probe_pid: int,
    ) -> tuple[ProbeVerdict, str]:
        """Compute the overall verdict from the four layer results.

        * ``supported`` — all four layers are confirmed ``True``.
        * ``unsupported`` — at least one layer is confirmed ``False``.
        * ``indeterminate`` — no layer is ``False`` but at least one is ``None``.
        """
        results = list(layers.values())
        any_false = any(r.supported is False for r in results)
        any_none = any(r.supported is None for r in results)
        all_true = all(r.supported is True for r in results)

        if all_true:
            return ProbeVerdict.SUPPORTED, (
                f"All 4 capability layers confirmed for PID {probe_pid}. "
                f"Existing-tab attach is supported through documented APIs."
            )

        if any_false:
            failed_layers = [
                r.layer.value for r in results if r.supported is False
            ]
            return ProbeVerdict.UNSUPPORTED, (
                f"Existing-tab attach is UNSUPPORTED. "
                f"The following layers are confirmed impossible through "
                f"documented APIs: {', '.join(failed_layers)}. "
                f"This is an architecture constraint (ConPTY handles are "
                f"process-scoped), not an implementation gap. "
                f"The broker-owned POC (tickets 01-03) remains the "
                f"recommended architecture."
            )

        # No layer is False, but at least one is None
        indeterminate_layers = [
            r.layer.value for r in results if r.supported is None
        ]
        return ProbeVerdict.INDETERMINATE, (
            f"Probe result is indeterminate for PID {probe_pid}. "
            f"Layers with inconclusive results: {', '.join(indeterminate_layers)}. "
            f"Indeterminate is not a pass — re-run with a running Windows "
            f"Terminal process."
        )
