"""Unit tests for the OriginEgressBinding and its ContextVar.

Covers the four acceptance criteria from ticket 24:

1. ``OriginEgressBinding`` is a frozen dataclass with all identity fields.
2. New ContextVar holds the binding for the current task.
3. Two concurrent tasks in different groups have isolated bindings.
4. Unbound group does not set a binding — downstream sees ``None``.

Also covers the ContextVar lifecycle: set → get → reset → get returns None,
and the monotonic ``origin_context_engaged`` latch.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from gateway.restricted_origin import (
    OriginEgressBinding,
    _UNSET,
    get_origin_binding,
    is_restricted_context,
    origin_context_engaged,
    reset_origin_binding,
    set_origin_binding,
)
import gateway.restricted_origin as ro


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_origin_binding():
    """Clean ContextVar + engaged-latch slate per test, restored afterwards."""
    saved = _ORIGIN_BINDING.get()
    saved_engaged = ro._origin_context_engaged
    _ORIGIN_BINDING.set(_UNSET)
    ro._origin_context_engaged = False
    try:
        yield
    finally:
        _ORIGIN_BINDING.set(saved)
        ro._origin_context_engaged = saved_engaged


# Import the module-level ContextVar for the fixture
from gateway.restricted_origin import _ORIGIN_BINDING  # noqa: E402


def _make_binding(**overrides: Any) -> OriginEgressBinding:
    """Build a binding with defaults; override any field."""
    defaults = dict(
        profile="default",
        policy_id="rgp-test-v1",
        policy_revision="rev-001",
        platform="teams_mtk",
        adapter_identity="TeamsMTKAdapter",
        account_id="acct-test-001",
        conv_id="19:cbdcf6224c48469ea048147752ed92d9@thread.v2",
        thread_id="",
        durable_task_id="",
    )
    defaults.update(overrides)
    return OriginEgressBinding(**defaults)


# ---------------------------------------------------------------------------
# 1. Frozen dataclass — immutability
# ---------------------------------------------------------------------------

class TestBindingImmutability:
    """OriginEgressBinding is frozen — mutation must raise."""

    def test_cannot_set_field_after_creation(self):
        binding = _make_binding()
        with pytest.raises(FrozenInstanceError):
            binding.conv_id = "different-conv-id"

    def test_cannot_delete_field_after_creation(self):
        binding = _make_binding()
        with pytest.raises(FrozenInstanceError):
            del binding.policy_id

    def test_all_identity_fields_present(self):
        binding = _make_binding()
        # Every field from the ticket's acceptance criteria must exist.
        for field in (
            "profile",
            "policy_id",
            "policy_revision",
            "platform",
            "adapter_identity",
            "account_id",
            "conv_id",
            "thread_id",
            "durable_task_id",
        ):
            assert hasattr(binding, field), f"missing field: {field}"

    def test_two_distinct_bindings_are_not_equal(self):
        a = _make_binding(conv_id="group-A")
        b = _make_binding(conv_id="group-B")
        assert a != b
        assert a.conv_id != b.conv_id

    def test_same_args_produce_equal_bindings(self):
        a = _make_binding()
        b = _make_binding()
        assert a == b


# ---------------------------------------------------------------------------
# 2. ContextVar — set, get, reset lifecycle
# ---------------------------------------------------------------------------

class TestContextVarLifecycle:
    """The ContextVar follows set → get → reset → None."""

    def test_get_returns_none_when_unset(self):
        assert get_origin_binding() is None
        assert not is_restricted_context()

    def test_set_then_get_returns_binding(self):
        binding = _make_binding()
        token = set_origin_binding(binding)
        assert get_origin_binding() is binding
        assert is_restricted_context()
        reset_origin_binding(token)

    def test_reset_restores_none(self):
        binding = _make_binding()
        token = set_origin_binding(binding)
        reset_origin_binding(token)
        assert get_origin_binding() is None
        assert not is_restricted_context()

    def test_set_none_explicitly(self):
        """Setting None is explicit — still 'engaged' but not restricted."""
        token = set_origin_binding(None)
        assert get_origin_binding() is None
        assert not is_restricted_context()
        assert origin_context_engaged()  # latch latched
        reset_origin_binding(token)

    def test_reset_restores_outer_binding(self):
        """Nested set → reset restores the outer binding (stack-safe)."""
        outer = _make_binding(conv_id="outer-group")
        inner = _make_binding(conv_id="inner-group")

        outer_token = set_origin_binding(outer)
        assert get_origin_binding() is outer

        inner_token = set_origin_binding(inner)
        assert get_origin_binding() is inner

        reset_origin_binding(inner_token)
        assert get_origin_binding() is outer  # restored, not None

        reset_origin_binding(outer_token)
        assert get_origin_binding() is None

    def test_reset_with_invalid_token_falls_back_to_unset(self):
        """A bad token doesn't blow up — falls back to _UNSET."""
        reset_origin_binding(object())  # not a real token
        assert get_origin_binding() is None


# ---------------------------------------------------------------------------
# 3. Cross-task isolation — concurrent tasks in different groups
# ---------------------------------------------------------------------------

class TestCrossTaskIsolation:
    """Two tasks in different groups have independent ContextVar values."""

    def test_concurrent_tasks_isolate_bindings(self):
        """Simulate two concurrent asyncio tasks with different bindings."""
        import asyncio

        group_a = _make_binding(conv_id="19:group-a@thread.v2")
        group_b = _make_binding(conv_id="19:group-b@thread.v2")

        results: dict[str, str] = {}

        async def task(binding, label):
            token = set_origin_binding(binding)
            await asyncio.sleep(0.001)  # yield to let the other task run
            actual = get_origin_binding()
            results[label] = actual.conv_id if actual else "none"
            reset_origin_binding(token)

        async def main():
            await asyncio.gather(
                task(group_a, "A"),
                task(group_b, "B"),
            )

        asyncio.run(main())

        # Each task saw its own binding, not the other's.
        assert results["A"] == "19:group-a@thread.v2"
        assert results["B"] == "19:group-b@thread.v2"
        # After both tasks finished, the outer context sees None.
        assert get_origin_binding() is None

    def test_sequential_tasks_dont_leak(self):
        """A binding set in task 1 is not visible in task 2 after reset."""
        binding_a = _make_binding(conv_id="group-A")

        token = set_origin_binding(binding_a)
        assert get_origin_binding() is binding_a
        reset_origin_binding(token)

        # Task 2 starts fresh — no binding from task 1.
        assert get_origin_binding() is None


# ---------------------------------------------------------------------------
# 4. Unbound group — no binding set
# ---------------------------------------------------------------------------

class TestUnboundGroup:
    """An unbound group does not set a binding — downstream sees None."""

    def test_no_binding_set_for_unbound_group(self):
        # Simulate: gateway ingress for an unbound group simply doesn't call
        # set_origin_binding. Downstream code calls get_origin_binding()
        # and gets None — "not restricted, pass through."
        assert get_origin_binding() is None
        assert not is_restricted_context()

    def test_downstream_treats_none_as_pass_through(self):
        # Pattern that downstream seams will use:
        binding = get_origin_binding()
        if binding is None:
            pass  # not restricted — pass through
        else:
            pytest.fail("should not reach restricted path for unbound group")


# ---------------------------------------------------------------------------
# 5. Type safety — wrong type rejected
# ---------------------------------------------------------------------------

class TestTypeSafety:
    """set_origin_binding rejects non-OriginEgressBinding, non-None values."""

    def test_rejects_string(self):
        with pytest.raises(TypeError, match="OriginEgressBinding or None"):
            set_origin_binding("not-a-binding")  # type: ignore[arg-type]

    def test_rejects_dict(self):
        with pytest.raises(TypeError, match="OriginEgressBinding or None"):
            set_origin_binding({"conv_id": "fake"})  # type: ignore[arg-type]

    def test_rejects_int(self):
        with pytest.raises(TypeError, match="OriginEgressBinding or None"):
            set_origin_binding(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Monotonic latch — origin_context_engaged
# ---------------------------------------------------------------------------

class TestEngagedLatch:
    """origin_context_engaged is a monotonic latch — once True, stays True."""

    def test_not_engaged_before_first_set(self):
        # The autouse fixture resets the latch, so it should be False here.
        # But if a prior test set it, the fixture restored it — check that.
        # We can at least verify that after a set, it becomes True.
        assert origin_context_engaged() is False

    def test_engaged_after_first_set(self):
        binding = _make_binding()
        token = set_origin_binding(binding)
        assert origin_context_engaged() is True
        reset_origin_binding(token)
        # Still True even after reset — monotonic latch.
        assert origin_context_engaged() is True

    def test_engaged_even_for_none(self):
        token = set_origin_binding(None)
        assert origin_context_engaged() is True
        reset_origin_binding(token)
