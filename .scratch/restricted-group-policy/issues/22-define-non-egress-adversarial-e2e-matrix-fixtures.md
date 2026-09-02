# Define non-egress adversarial E2E matrix fixtures

Type: grilling
Status: closed
Parent: [Design and launch reusable Restricted Group Policy](../map.md)
Blocked by: (none)

## Question

What non-egress adversarial E2E matrix rows are needed to prove that CQ Read Broker rejects all write/mutation operations, cross-group capability leakage is impossible, model-routing gate bypass attempts fail, and capability descriptor spoofing is detected? Define the exact matrix rows, fixtures, contract-test adapters for unsupported dimensions, readback principals, and pass/fail criteria — parallel to the egress escape matrix (ticket 18) but covering non-egress enforcement seams.

## Comments

### Resolution — 2026-09-01

**Decisions (6 items):**

1. **Matrix categories** — Four non-egress adversarial categories: (1) CQ broker unauthorized write, (2) cross-group capability leakage, (3) model-routing gate bypass, (4) capability descriptor spoofing.

2. **CQ broker unauthorized write rows (3 rows):**
   - Row 1: INSERT through CQ broker → **DENY**
   - Row 2: UPDATE through CQ broker → **DENY**
   - Row 3: DELETE through CQ broker → **DENY**
   Each row verifies: broker rejects before any CQ system interaction, audit records `decision=denied` with `reason=write_operation_blocked`, zero side effect on CQ system.

3. **Cross-group capability leakage rows (3 rows):**
   - Row 4: Group A member operation affects Group B restricted task → **DENY** (origin binding prevents cross-group task influence)
   - Row 5: Group A conversation history injected into Group B prompt → **DENY** (semantic history retrieval bound to exact conv_id per ticket 08)
   - Row 6: Group A capability descriptor read by Group B session → **DENY** (ContextVar isolation prevents cross-session descriptor access)
   Each row verifies: operation only affects the originating group, no state change or data exposure in the non-origin group, independent readback via audit query.

4. **Model-routing gate bypass rows (3 rows):**
   - Row 7: Forged route identity (non-AIDE provider disguised as AIDE) → **DENY** (authorizeAndInvoke gate matches complete route identity before every invocation)
   - Row 8: Direct policy revision modification to skip gate → **DENY** (gate reloads current policy revision atomically; stale revision fails closed)
   - Row 9: Race condition — provider switch between gate check and invoke → **DENY** (one-use permit pinned to exact revision; revision change invalidates permit)
   Each row verifies: gate denies before model invocation, audit records `decision=denied` with `reason=route_identity_mismatch` / `stale_revision` / `permit_invalidated`, zero tokens sent to unauthorized provider.

5. **Capability descriptor spoofing rows (2 rows):**
   - Row 10: Forged descriptor claiming unauthorized capability → **DENY** (descriptor fingerprint must match verified descriptor)
   - Row 11: Tampered descriptor fingerprint (mismatch with verified descriptor) → **DENY** (fingerprint binding invalidates on change per ticket 12)
   Each row verifies: adapter rejects descriptor, audit records `decision=denied` with `reason=descriptor_fingerprint_mismatch`, zero capability granted from forged descriptor.

6. **Fixtures** — Fully reuse ticket 18's fixture set: origin group `19:cbdcf6224c48469ea048147752ed92d9@thread.v2`, independent readback principals (source readback confirms intended state, state readback confirms no unintended state change), unique UUID markers with `NON-EGRESS-TEST-{uuid}:` prefix, contract-test adapters for unsupported dimensions (alternate platform, alternate account, simulated CQ system when live CQ is unavailable).

**Total: 11 non-egress adversarial matrix rows.**

### No protected content in tracker

- Test operations use only public markers (UUID prefix + `NON-EGRESS-TEST`)
- No PII, NDA, credentials, or CQ content in any test
- All test evidence is content-minimized per ticket 11 audit contract
