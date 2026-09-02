# 25 — Restricted Group policy config and activation gate

**What to build:** The owner can define a restricted group policy in `config.yaml` with a policy identity, version, capability grants, and an exact `conv_id` binding. A CLI subcommand activates the policy for a group. The activation gate reads the `OriginEgressBinding` at ingress and determines whether the group is restricted; for a restricted group, the gate enforces that a valid, active policy exists; for an unbound group, it passes through unchanged (existing whitelist behavior). If identity is ambiguous, stale, or mismatched, the gate fails closed. Integration test proves a bound group is enforced and an unbound group passes through.

**Blocked by:** 24 — Origin binding module and ContextVar

**Status:** claimed

- [ ] New `restricted_group` config section in `config.yaml` with policy definitions, capability grants, group bindings, and activation state
- [ ] CLI subcommand to activate a restricted group policy for a specific `conv_id`
- [ ] Activation gate reads the binding and checks for a valid, active, version-matched policy
- [ ] Fail-closed: ambiguous/stale/mismatched identity denies the turn
- [ ] Integration test: bound group with active policy → enforcement engaged
- [ ] Integration test: bound group with inactive policy → fail closed
- [ ] Integration test: unbound group → passes through with existing whitelist behavior
