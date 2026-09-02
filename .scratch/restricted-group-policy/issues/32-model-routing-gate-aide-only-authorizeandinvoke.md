# 32 — Model-routing gate: AIDE-only authorizeAndInvoke

**What to build:** Every model invocation in restricted context passes through an `authorizeAndInvoke` function that atomically reloads the current policy revision and matches the complete route identity (provider, model, base_url, route class) against the policy's allowed AIDE routes. Non-AIDE providers are denied. A revision change between permit issuance and invocation invalidates the permit. The gate is stateless — it holds no cached revision between invocations. Three adversarial test rows prove: (1) forged route identity (non-AIDE provider disguised as AIDE) → DENY; (2) direct policy revision modification to skip gate → DENY; (3) race condition — provider switch between gate check and invoke → DENY.

**Blocked by:** 26 — Egress Broker core: intent, permit, deny

**Status:** ready-for-agent

- [ ] `authorizeAndInvoke` function called before every model invocation in restricted context
- [ ] Atomically reloads current policy revision (no cached revision)
- [ ] Matches complete route identity: provider, model, base_url, route class
- [ ] Non-AIDE provider → DENY with `reason=route_identity_mismatch`
- [ ] Stale revision (changed between permit and invoke) → DENY with `reason=stale_revision`
- [ ] Race condition (provider switch between gate check and invoke) → DENY with `reason=permit_invalidated`
- [ ] Unit test: AIDE provider with matching revision → ALLOW
- [ ] Unit test: non-AIDE provider → DENY
- [ ] Integration test: revision change between permit and invoke → DENY
- [ ] Adversarial test (non-egress matrix rows 7-9): forged route identity, stale revision, race condition all → DENY
