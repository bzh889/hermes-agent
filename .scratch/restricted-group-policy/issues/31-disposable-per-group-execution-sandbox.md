# 31 — Disposable per-group execution sandbox

**What to build:** Each restricted task gets a fresh, policy-stamped sandbox for temporary storage and execution isolation. All credentialed access from the sandbox goes through the CQ Read Broker (or Egress Broker for output). The sandbox is destroyed at task end — no state persists between tasks. One task's sandbox cannot access another task's sandbox. The sandbox boundary is the Durable Task identity from the OriginEgressBinding. An integration test proves that after task A completes and its sandbox is destroyed, task B starts with a fresh sandbox and cannot read task A's remnants.

**Blocked by:** 25 — Restricted Group policy config and activation gate

**Status:** ready-for-agent

- [ ] Sandbox creation: each restricted task spawns a fresh sandbox stamped with the policy and binding
- [ ] Sandbox isolation: sandbox access is scoped to the Durable Task identity
- [ ] Sandbox destruction: sandbox is destroyed at task end
- [ ] All credentialed access from the sandbox goes through brokers (CQ Read Broker or Egress Broker)
- [ ] Integration test: task A's sandbox is destroyed after completion; task B cannot access task A's remnants
- [ ] Integration test: two concurrent tasks in different groups have isolated sandboxes
- [ ] Integration test: sandbox does not survive a gateway restart
