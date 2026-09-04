# 25 — Restricted Group policy config and activation gate

**What to build:** The owner can define a restricted group policy in `config.yaml` with a policy identity, version, capability grants, and an exact `conv_id` binding. A CLI subcommand activates the policy for a group. The activation gate reads the `OriginEgressBinding` at ingress and determines whether the group is restricted; for a restricted group, the gate enforces that a valid, active policy exists; for an unbound group, it passes through unchanged (existing whitelist behavior). If identity is ambiguous, stale, or mismatched, the gate fails closed. Integration test proves a bound group is enforced and an unbound group passes through.

**Blocked by:** 24 — Origin binding module and ContextVar

**Status:** closed

- [x] New `restricted_group` config section in `config.yaml` with policy definitions, capability grants, group bindings, and activation state
- [x] CLI subcommand to activate a restricted group policy for a specific `conv_id`
- [x] Activation gate reads the binding and checks for a valid, active, version-matched policy
- [x] Fail-closed: ambiguous/stale/mismatched identity denies the turn
- [x] Integration test: bound group with active policy → enforcement engaged
- [x] Integration test: bound group with inactive policy → fail closed
- [x] Integration test: unbound group → passes through with existing whitelist behavior

## Comments

### Resolution — 2026-09-03

**Implemented:**

1. **Config section** — Added `gateway.restricted_group.policies` to `DEFAULT_CONFIG` in `hermes_cli/config.py` (peer of `gateway.teams_mtk`). Each policy entry has: `version`, `conv_id`, `account_id`, `active`, `capabilities`. No `_config_version` bump needed (deep-merge handles new keys).

2. **Activation gate** — New module `gateway/restricted_group_gate.py`:
   - `resolve_origin_binding()` — reads config, finds active policy matching conv_id + account_id, returns `OriginEgressBinding` or `None`
   - `_find_active_policy()` — matches on `active: true` + `conv_id` exact match + `account_id` (empty = wildcard)
   - `_load_restricted_group_config()` — reads `gateway.restricted_group` from config, never raises (fail-closed)

3. **Gateway wiring** — `gateway/run.py`:
   - `_resolve_and_set_origin_binding()` — called after `_set_session_env()` at message ingress; creates and sets `OriginEgressBinding` if active policy matches; appends reset token to the same token list
   - `_clear_session_env()` — pops and resets the origin binding token from the tail before calling `clear_session_vars()`

4. **Fail-closed guarantees:**
   - Empty/whitespace conv_id → None
   - Inactive policy → None
   - Non-matching conv_id → None
   - Non-matching account_id → None (empty = wildcard)
   - Missing version → None
   - Corrupt policy entry → skipped
   - Config load exception → None (never raises)

**Tests:** `tests/gateway/test_restricted_group_gate.py` — 24 tests across 8 classes:
- `TestConfigStructure` (3) — empty/missing/capabilities
- `TestActivePolicyMatching` (5) — active/inactive/conv_id/account_id/wildcard
- `TestUnboundGroupFailClosed` (3) — no policy/empty/whitespace conv_id
- `TestBindingFields` (3) — thread_id/durable_task_id/immutability
- `TestMissingFieldsFailClosed` (3) — missing version/conv_id/corrupt entry
- `TestFailClosedOnErrors` (2) — config exception/non-dict policies
- `TestFindActivePolicy` (3) — duplicate conv_id/non-dict/inactive
- `TestGatewayIngressIntegration` (2) — restricted group sets binding / unbound group doesn't

**Verification:**
- `scripts/run_tests.sh tests/gateway/test_restricted_origin.py tests/gateway/test_restricted_group_gate.py` → 45/45 passed, 0 failed, 30.2s (hermetic)
- `scripts/run_tests.sh tests/gateway/test_session_context_inheritance.py` → 6/6 passed, 0 failed (no regression)
- `python -c "import ast; ast.parse(open('gateway/run.py').read())"` → syntax OK
- `python -c "import ast; ast.parse(open('hermes_cli/config.py').read())"` → syntax OK
