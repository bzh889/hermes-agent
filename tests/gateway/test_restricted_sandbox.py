"""Unit tests for the disposable per-group execution sandbox (ticket 31)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from gateway.restricted_sandbox import (
    Sandbox,
    create_sandbox,
    destroy_all_sandboxes,
    destroy_sandbox,
    get_sandbox,
    list_active_sandboxes,
    reset_sandbox_registry,
)
from gateway.restricted_origin import (
    OriginEgressBinding,
    set_origin_binding,
    reset_origin_binding,
)
import gateway.restricted_origin as ro
from gateway.restricted_origin import _ORIGIN_BINDING, _UNSET


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    reset_sandbox_registry()
    yield
    reset_sandbox_registry()
    _ORIGIN_BINDING.set(saved)
    ro._origin_context_engaged = saved_engaged


def _make_binding(**overrides: Any) -> OriginEgressBinding:
    defaults = dict(
        profile="default",
        policy_id="rgp-test-v1",
        policy_revision="rev-001",
        platform="teams_mtk",
        adapter_identity="TeamsMTKAdapter",
        account_id="acct-test-001",
        conv_id="19:group-A@thread.v2",
        thread_id="",
        durable_task_id="task-001",
    )
    defaults.update(overrides)
    return OriginEgressBinding(**defaults)


# ---------------------------------------------------------------------------

class TestSandboxCreation:
    def test_sandbox_created_with_binding(self, tmp_path):
        binding = _make_binding()
        sandbox = create_sandbox(binding=binding)
        assert sandbox.active
        assert sandbox.path.exists()
        assert sandbox.conv_id == binding.conv_id
        assert sandbox.policy_id == binding.policy_id
        assert sandbox.policy_revision == binding.policy_revision

    def test_sandbox_directory_under_hermes_home(self, tmp_path):
        binding = _make_binding()
        sandbox = create_sandbox(binding=binding)
        assert "sandboxes" in str(sandbox.path)
        assert tmp_path in sandbox.path.parents

    def test_stamp_file_created(self, tmp_path):
        binding = _make_binding()
        sandbox = create_sandbox(binding=binding)
        stamp = sandbox.path / ".sandbox_stamp"
        assert stamp.exists()
        content = stamp.read_text()
        assert binding.policy_id in content
        assert binding.conv_id in content

    def test_no_binding_raises(self):
        with pytest.raises(ValueError, match="origin binding"):
            create_sandbox()


class TestSandboxIsolation:
    def test_two_concurrent_sandboxes_isolated(self):
        binding_a = _make_binding(durable_task_id="task-A", conv_id="19:group-A@thread.v2")
        binding_b = _make_binding(durable_task_id="task-B", conv_id="19:group-B@thread.v2")
        sandbox_a = create_sandbox(binding=binding_a)
        sandbox_b = create_sandbox(binding=binding_b)
        assert sandbox_a.path != sandbox_b.path
        assert sandbox_a.durable_task_id != sandbox_b.durable_task_id
        # Task A writes to its sandbox
        (sandbox_a.path / "secret.txt").write_text("task-a-secret")
        # Task B's sandbox does not contain task A's file
        assert not (sandbox_b.path / "secret.txt").exists()
        destroy_sandbox("task-A")
        destroy_sandbox("task-B")

    def test_get_sandbox_by_task_id(self):
        binding = _make_binding(durable_task_id="task-X")
        sandbox = create_sandbox(binding=binding)
        retrieved = get_sandbox("task-X")
        assert retrieved is not None
        assert retrieved.sandbox_id == sandbox.sandbox_id

    def test_get_nonexistent_sandbox_returns_none(self):
        assert get_sandbox("nonexistent") is None


class TestSandboxDestruction:
    def test_destroy_removes_directory(self):
        binding = _make_binding()
        sandbox = create_sandbox(binding=binding)
        path = sandbox.path
        assert path.exists()
        destroy_sandbox(binding.durable_task_id)
        assert not path.exists()
        assert not sandbox.active

    def test_destroy_twice_returns_false(self):
        binding = _make_binding()
        create_sandbox(binding=binding)
        assert destroy_sandbox(binding.durable_task_id) is True
        assert destroy_sandbox(binding.durable_task_id) is False

    def test_task_b_cannot_access_task_a_remnants(self):
        """After task A completes its sandbox is destroyed; task B starts fresh."""
        binding_a = _make_binding(durable_task_id="A", conv_id="19:group-A@thread.v2")
        sandbox_a = create_sandbox(binding=binding_a)
        (sandbox_a.path / "data.txt").write_text("A's private data")
        path_a = sandbox_a.path
        destroy_sandbox("A")
        # Task B starts
        binding_b = _make_binding(durable_task_id="B", conv_id="19:group-B@thread.v2")
        sandbox_b = create_sandbox(binding=binding_b)
        # Path A is gone
        assert not path_a.exists()
        # Task B cannot read task A's data
        assert not (sandbox_b.path / "data.txt").exists()
        destroy_sandbox("B")


class TestDestroyAll:
    def test_destroy_all_on_restart(self):
        for i in range(3):
            create_sandbox(binding=_make_binding(durable_task_id=f"task-{i}"))
        count = destroy_all_sandboxes()
        assert count == 3
        assert list_active_sandboxes() == []

    def test_destroy_all_idempotent(self):
        create_sandbox(binding=_make_binding())
        destroy_all_sandboxes()
        assert destroy_all_sandboxes() == 0


class TestContextManager:
    def test_context_manager_destroys_on_exit(self):
        binding = _make_binding()
        with create_sandbox(binding=binding) as sandbox:
            assert sandbox.active
        assert not sandbox.active


class TestRegistry:
    def test_list_active_sandboxes(self):
        for i in range(2):
            create_sandbox(binding=_make_binding(durable_task_id=f"t{i}"))
        active = list_active_sandboxes()
        assert len(active) == 2
        destroy_all_sandboxes()

    def test_sandbox_not_in_registry_after_destroy(self):
        binding = _make_binding()
        create_sandbox(binding=binding)
        assert get_sandbox(binding.durable_task_id) is not None
        destroy_sandbox(binding.durable_task_id)
        assert get_sandbox(binding.durable_task_id) is None
