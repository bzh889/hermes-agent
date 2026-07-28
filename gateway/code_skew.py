"""Detect when the gateway is running stale code after a hot ``git pull``.

The gateway is a single long-lived process; its ``sys.modules`` is frozen at
boot. If the checkout is updated underneath it (a manual ``git pull``, or the
window before ``hermes update``'s graceful restart fires), a first-time lazy
import on a new code path can resolve a freshly-pulled consumer module against a
stale cached dependency -> ImportError (see
``tests/test_stale_utils_module_import.py`` for the exact failure).

We snapshot the checkout revision at gateway startup and compare on demand, so
risky callers (e.g. ``/model`` switching) can refuse with a clear "restart the
gateway" message instead of crashing on a cryptic import error.

If the revision can't be read (non-git install, IO error), the boot snapshot
stays ``None`` and skew detection no-ops — it never produces a false positive.
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_boot_fingerprint: str | None = None


def _read_packed_ref(common_dir: Path, ref: str) -> str | None:
    """Read one packed Git reference without starting Git or the CLI."""
    try:
        text = (common_dir / "packed-refs").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        sha, separator, name = line.partition(" ")
        if separator and name.strip() == ref:
            return sha.strip()
    return None


def _fingerprint() -> str | None:
    """Return the current checkout fingerprint without importing the CLI.

    The detached Windows Gateway deliberately bypasses ``hermes_cli.main``.
    Importing it here merely to read a Git ref added roughly 24 seconds to
    every cold Gateway start, before its PID and state files existed.
    """
    try:
        git_dir = _PROJECT_ROOT / ".git"
        if git_dir.is_file():
            for line in git_dir.read_text(encoding="utf-8", errors="replace").splitlines():
                key, _, value = line.partition(":")
                if key.strip() == "gitdir" and value.strip():
                    git_dir = (_PROJECT_ROOT / value.strip()).resolve()
                    break
        common_dir = git_dir
        commondir_file = git_dir / "commondir"
        if commondir_file.exists():
            relative = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            if relative:
                common_dir = (git_dir / relative).resolve()
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
        if not head.startswith("ref:"):
            return f"git:HEAD:{head}"
        ref = head.split(":", 1)[1].strip()
        for candidate in (git_dir, common_dir):
            ref_file = candidate / ref
            if ref_file.exists():
                sha = ref_file.read_text(encoding="utf-8", errors="replace").strip()
                return f"git:{ref}:{sha}"
        packed_sha = _read_packed_ref(common_dir, ref)
        return f"git:{ref}:{packed_sha or 'unresolved'}"
    except OSError:
        return None


def record_boot_fingerprint() -> None:
    """Snapshot the checkout revision at gateway startup (idempotent)."""
    global _boot_fingerprint
    if _boot_fingerprint is None:
        _boot_fingerprint = _fingerprint()


def _short(fingerprint: str) -> str:
    """Render a ``git:<ref>:<sha>`` fingerprint as a compact label."""
    sha = fingerprint.rsplit(":", 1)[-1]
    if sha and sha != "unresolved" and len(sha) > 10:
        return sha[:10]
    return sha or fingerprint


def detect_code_skew() -> tuple[str, str] | None:
    """Return ``(boot_rev, disk_rev)`` short labels if the checkout drifted
    since boot, else ``None``."""
    if _boot_fingerprint is None:
        return None
    current = _fingerprint()
    if current is None or current == _boot_fingerprint:
        return None
    return _short(_boot_fingerprint), _short(current)
