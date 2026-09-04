"""Disposable per-group execution sandbox for restricted-context tasks.

Each restricted task gets a fresh temp directory stamped with the policy and
binding identity. The sandbox is destroyed at task end — no state persists
between tasks. One task's sandbox cannot access another's.

The sandbox boundary is the Durable Task identity from the OriginEgressBinding.
All credentialed access from the sandbox goes through the CQ Read Broker (or
Egress Broker for output) — the sandbox never touches owner credentials.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from gateway.restricted_origin import OriginEgressBinding, get_origin_binding
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


@dataclass
class Sandbox:
    """A disposable execution sandbox for a single restricted task.

    Created at task start, destroyed at task end. The sandbox directory is
    a temp directory under ``get_hermes_home() / "sandboxes" / <sandbox_id>``.
    """

    sandbox_id: str
    durable_task_id: str
    conv_id: str
    policy_id: str
    policy_revision: str
    path: Path
    _active: bool = True

    @property
    def active(self) -> bool:
        """True if the sandbox has not been destroyed."""
        return self._active and self.path.exists()

    def destroy(self) -> None:
        """Destroy the sandbox — remove the directory and mark inactive."""
        if not self._active:
            return
        try:
            if self.path.exists():
                shutil.rmtree(self.path, ignore_errors=True)
        except Exception:
            logger.debug("sandbox destroy failed for %s", self.sandbox_id, exc_info=True)
        self._active = False

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *args: Any) -> None:
        self.destroy()


# ---------------------------------------------------------------------------
# Sandbox registry — tracks active sandboxes by task ID
# ---------------------------------------------------------------------------

_sandboxes: dict[str, Sandbox] = {}


def create_sandbox(
    binding: Optional[OriginEgressBinding] = None,
) -> Sandbox:
    """Create a fresh sandbox for a restricted task.

    The sandbox directory is created under ``get_hermes_home() / "sandboxes"
    / <sandbox_id>``. The sandbox is stamped with the binding's policy_id,
    policy_revision, conv_id, and durable_task_id.

    Parameters
    ----------
    binding:
        The origin binding for the task. If ``None``, reads from ContextVar.
        A binding is required — unrestricted context does not create sandboxes.

    Returns
    -------
    Sandbox
        The created sandbox.

    Raises
    ------
    ValueError
        If no origin binding is available (unrestricted context).
    """
    if binding is None:
        binding = get_origin_binding()

    if binding is None:
        raise ValueError(
            "Cannot create sandbox without an origin binding — "
            "sandbox is only for restricted-context tasks"
        )

    sandbox_id = f"sandbox-{uuid.uuid4()}"
    task_id = binding.durable_task_id or sandbox_id

    sandboxes_root = get_hermes_home() / "sandboxes"
    sandbox_dir = sandboxes_root / sandbox_id
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # Write a stamp file with the binding identity (for debugging only)
    stamp_path = sandbox_dir / ".sandbox_stamp"
    stamp_content = (
        f"sandbox_id: {sandbox_id}\n"
        f"durable_task_id: {task_id}\n"
        f"conv_id: {binding.conv_id}\n"
        f"policy_id: {binding.policy_id}\n"
        f"policy_revision: {binding.policy_revision}\n"
    )
    stamp_path.write_text(stamp_content, encoding="utf-8")

    sandbox = Sandbox(
        sandbox_id=sandbox_id,
        durable_task_id=task_id,
        conv_id=binding.conv_id,
        policy_id=binding.policy_id,
        policy_revision=binding.policy_revision,
        path=sandbox_dir,
    )

    _sandboxes[task_id] = sandbox
    logger.info(
        "sandbox created: id=%s task=%s conv=%s",
        sandbox_id, task_id, binding.conv_id[:40],
    )
    return sandbox


def get_sandbox(durable_task_id: str) -> Optional[Sandbox]:
    """Get the active sandbox for a Durable Task ID."""
    sandbox = _sandboxes.get(durable_task_id)
    if sandbox is None or not sandbox.active:
        return None
    return sandbox


def destroy_sandbox(durable_task_id: str) -> bool:
    """Destroy the sandbox for a Durable Task ID.

    Returns ``True`` if the sandbox was found and destroyed, ``False`` if
    no active sandbox exists for the given task ID.
    """
    sandbox = _sandboxes.pop(durable_task_id, None)
    if sandbox is None:
        return False
    sandbox.destroy()
    return True


def destroy_all_sandboxes() -> int:
    """Destroy all active sandboxes — for gateway restart.

    Returns the count of sandboxes destroyed.
    """
    count = 0
    for task_id in list(_sandboxes.keys()):
        if destroy_sandbox(task_id):
            count += 1
    return count


def list_active_sandboxes() -> list[Sandbox]:
    """Return all active sandboxes (for debugging / monitoring)."""
    return [s for s in _sandboxes.values() if s.active]


def reset_sandbox_registry() -> None:
    """Reset the sandbox registry — for testing only."""
    for task_id in list(_sandboxes.keys()):
        destroy_sandbox(task_id)
    _sandboxes.clear()
