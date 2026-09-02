# 24 — Origin binding module and ContextVar

**What to build:** A message arriving from a restricted Teams group is bound to an immutable `OriginEgressBinding` at gateway ingress. The binding captures profile, policy identity, policy version, platform, adapter identity, account/tenant, chat/conversation ID, thread/topic ID, and Durable Task identity. Downstream code reads the binding via a new ContextVar set alongside the existing session_context ContextVars. The binding is immutable for the lifetime of the task. Unit tests prove that the binding cannot be modified after creation and that two concurrent tasks in different groups have isolated bindings.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] `OriginEgressBinding` is a frozen dataclass with all identity fields
- [x] New ContextVar in `gateway/restricted_origin.py` holds the binding for the current task
- [x] Gateway ingress can set the binding when a message arrives from a restricted group (API ready in `set_origin_binding()`)
- [x] Unit test: binding is immutable — mutation raises
- [x] Unit test: two simulated tasks in different groups have independent ContextVar values
- [x] Unit test: unbound group (no policy) does not set a binding — downstream code sees no binding

## Comments

### Resolution — 2026-09-02

**Implemented:**

- **New module:** `gateway/restricted_origin.py`
  - `OriginEgressBinding` — frozen dataclass with 10 identity fields (profile, policy_id, policy_revision, platform, adapter_identity, account_id, conv_id, thread_id, durable_task_id)
  - `_ORIGIN_BINDING` — `ContextVar[Any]` with `_UNSET` sentinel (same pattern as `session_context._SESSION_*`)
  - `set_origin_binding(binding)` — sets the ContextVar, latches `origin_context_engaged`, type-checks input
  - `reset_origin_binding(token)` — restores outer binding (stack-safe for nested handlers)
  - `get_origin_binding()` — returns the binding or `None` (no `os.environ` fallback — origin identity is never inherited from process-global state)
  - `is_restricted_context()` — convenience boolean
  - `origin_context_engaged()` — monotonic latch for subprocess-env bridges

- **Tests:** `tests/gateway/test_restricted_origin.py` — 21 tests across 6 classes:
  - `TestBindingImmutability` (5) — frozen dataclass: mutation raises, all fields present, equality
  - `TestContextVarLifecycle` (6) — set/get/reset, nested stack-safety, invalid token fallback
  - `TestCrossTaskIsolation` (2) — concurrent asyncio tasks have isolated bindings, sequential tasks don't leak
  - `TestUnboundGroup` (2) — no binding set → `None` → downstream pass-through
  - `TestTypeSafety` (3) — rejects string, dict, int
  - `TestEngagedLatch` (3) — monotonic latch behavior

**Verification:** `python -m pytest tests/gateway/test_restricted_origin.py -v` → 21 passed in 5.85s

**Key design decisions:**

1. **No `os.environ` fallback.** Unlike `session_context.get_session_env()`, origin binding has no process-global fallback. Origin identity must be explicitly set per task — it can never leak from a concurrent session's ContextVar.
2. **`_UNSET` sentinel pattern** matches `session_context` — distinguishes "never bound" from "explicitly set to None".
3. **Monotonic latch** (`origin_context_engaged`) mirrors `session_context_engaged()` — subprocess-env bridges can detect when origin bindings are task-local.
4. **Gateway ingress wiring** (actually calling `set_origin_binding` from `_set_session_env` in `gateway/run.py`) is deferred to ticket 25, which adds the policy config and activation gate that determines *when* to create a binding.
