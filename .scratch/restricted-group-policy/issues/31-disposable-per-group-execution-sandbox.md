# 31 — Disposable per-group execution sandbox

**What to build:** Each restricted task gets a fresh, policy-stamped sandbox for temporary storage and execution isolation. All credentialed access from the sandbox goes through the CQ Read Broker (or Egress Broker for output). The sandbox is destroyed at task end — no state persists between tasks. One task's sandbox cannot access another task's sandbox. The sandbox boundary is the Durable Task identity from the OriginEgressBinding. An integration test proves that after task A completes and its sandbox is destroyed, task B starts with a fresh sandbox and cannot read task A's remnants.

**Blocked by:** 25 — Restricted Group policy config and activation gate

**Status:** closed

- [x] Sandbox creation: each restricted task spawns a fresh sandbox stamped with the policy and binding
- [x] Sandbox isolation: sandbox access is scoped to the Durable Task identity
- [x] Sandbox destruction: sandbox is destroyed at task end
- [x] All credentialed access from the sandbox goes through brokers (CQ Read Broker or Egress Broker)
- [x] Integration test: task A's sandbox is destroyed after completion; task B cannot access task A's remnants
- [x] Integration test: two concurrent tasks in different groups have isolated sandboxes
- [x] Integration test: sandbox does not survive a gateway restart

## Comments

### Resolution — 2026-09-03

**Implemented:** `gateway/restricted_sandbox.py` — disposable per-group execution sandbox.
- `Sandbox` dataclass with context-manager support, `active` property, `destroy()`
- `create_sandbox(binding)` — creates temp dir under `get_hermes_home() / "sandboxes" / <id>`, stamps with policy/binding identity
- `destroy_sandbox(task_id)` — destroys by task ID, returns bool
- `destroy_all_sandboxes()` — gateway restart cleanup
- `get_sandbox(task_id)` — lookup by Durable Task identity
- `list_active_sandboxes()` — monitoring

**Tests:** `tests/gateway/test_restricted_sandbox.py` — 15 tests, 5.02s
**Verification:** 15/15 passed, 0 failed
