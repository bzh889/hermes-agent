# 32 — Model-routing gate: AIDE-only authorizeAndInvoke

**What to build:** Every model invocation in restricted context passes through an `authorizeAndInvoke` function that atomically reloads the current policy revision and matches the complete route identity (provider, model, base_url, route class) against the policy's allowed AIDE routes. Non-AIDE providers are denied. A revision change between permit issuance and invocation invalidates the permit. The gate is stateless — it holds no cached revision between invocations. Three adversarial test rows prove: (1) forged route identity (non-AIDE provider disguised as AIDE) → DENY; (2) direct policy revision modification to skip gate → DENY; (3) race condition — provider switch between gate check and invoke → DENY.

**Blocked by:** 26 — Egress Broker core: intent, permit, deny

**Status:** closed

- [x] `authorizeAndInvoke` function called before every model invocation in restricted context
- [x] Atomically reloads current policy revision (no cached revision)
- [x] Matches complete route identity: provider, model, base_url, route class
- [x] Non-AIDE provider → DENY with `reason=route_identity_mismatch`
- [x] Stale revision (changed between permit and invoke) → DENY with `reason=stale_revision`
- [x] Race condition (provider switch between gate check and invoke) → DENY with `reason=permit_invalidated`
- [x] Unit test: AIDE provider with matching revision → ALLOW
- [x] Unit test: non-AIDE provider → DENY
- [x] Integration test: revision change between permit and invoke → DENY
- [x] Adversarial test (non-egress matrix rows 7-9): forged route identity, stale revision, race condition all → DENY

## Comments

### Resolution — 2026-09-03

**Implemented:** `gateway/model_routing_gate.py` — stateless AIDE-only model-routing gate.
- `RouteIdentity` dataclass (provider, model, base_url, route_class)
- `authorize_route(route, binding, permit_revision)` → `RouteCheckResult(decision, reason)`
- `authorize_and_invoke(invoke_fn, route, binding, permit_revision)` → calls invoke_fn or raises `RouteDeniedError`
- `_is_aide_route(route)` — matches AIDE provider patterns (mtk, aide) + base_url (mlop-azure-gateway.mediatek.inc)
- `_reload_policy_revision(binding)` — atomically reloads from config, never cached

**Tests:** `tests/gateway/test_model_routing_gate.py` — 19 tests, 3.04s
**Verification:** 19/19 passed, 0 failed
